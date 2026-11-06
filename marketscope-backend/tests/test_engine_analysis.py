"""
Tests for the final score, the verdict and the explanation behind perform_analysis.
No database needed: the map layers and market context are stubbed.
"""

import unittest
from unittest.mock import patch

from constants.engine import VERDICT_HIGH_MIN, VERDICT_MODERATE_MIN
from models.requests import AnalysisRequest
from services import analysis, hazard as hazard_service, zoning as zoning_service
from services.analysis import build_data_quality, combine_criteria, zoning_state_for
from services.reporting import build_scan_payload, generate_deterministic_scan_narrative
from services.verdict import classify_site, score_band

WEIGHTS_USED = {"competition": 0.4, "road": 0.2, "anchor": 0.2, "building": 0.2}


def factor(score, credited=None):
    available = score is not None
    made = {
        "available": available,
        "score": score,
        "raw_score": score,
        "status": "Status",
        "details": "Details.",
        "evidence": "Evidence.",
    }
    if credited is not None:
        made["credited_raw_score"] = credited
        made["credited_score"] = credited
    return made


def market_context(competition=20.0, road=20.0, anchor=20.0, building=20.0, market=20.0, weights=None, warnings=None, credited=None):
    saturation = factor(market)
    saturation["description"] = "Combined"
    return {
        "competitors": [],
        "competition_density": factor(competition, credited=credited),
        "road_access": factor(road),
        "anchor_proximity": factor(anchor),
        "building_density": factor(building),
        "saturation": saturation,
        "market_weights_used": WEIGHTS_USED if weights is None else weights,
        "warnings": warnings or [],
        "ahp_sub_criteria_methodology": {},
    }


def run_scan(context=None, zoning=(25, "Allowed in General Commercial Zone", "general_commercial"), hazard=(25, "Low Risk / Safe", []), hazard_cache=("layer",), radius=340):
    with patch.object(analysis, "evaluate_layered_market_context", lambda *a: context or market_context()), \
            patch.object(analysis, "evaluate_zoning", lambda *a: zoning), \
            patch.object(analysis, "evaluate_hazard", lambda *a: hazard), \
            patch.object(hazard_service, "HAZARD_LAYER_CACHE", list(hazard_cache)), \
            patch.object(hazard_service, "HAZARD_LAYER_SOURCE", "Test hazard layer"), \
            patch.object(zoning_service, "ZONING_LAYER_SOURCE", "Test zoning layer"), \
            patch.object(analysis, "get_ahp_weights", lambda *a: None):
        return analysis.perform_analysis(AnalysisRequest(lat=7.3, lon=125.68, business_type="coffee", radius=radius))


class ZoningConstraintTests(unittest.TestCase):
    NOT_ALLOWED = (0, "Not Allowed in Residential-1 (R-1)", "residential_1")

    def test_states(self):
        self.assertEqual(zoning_state_for(25, "general_commercial"), "permitted")
        self.assertEqual(zoning_state_for(0, "residential_1"), "not_permitted")
        self.assertEqual(zoning_state_for(0, None), "unverified")

    def test_banned_site_scores_zero_and_says_so(self):
        report = run_scan(zoning=self.NOT_ALLOWED)
        self.assertEqual(report["viability_score"], 0)
        self.assertEqual(report["verdict"]["key"], "not_permitted")
        self.assertIn("Not Permitted", report["insight"])

    def test_banned_site_still_reports_its_potential(self):
        banned = run_scan(zoning=self.NOT_ALLOWED)
        allowed = run_scan()
        self.assertEqual(banned["market_potential_score"], allowed["market_potential_score"])
        self.assertGreater(banned["market_potential_score"], 0)

    def test_zoning_gives_no_free_points(self):
        """Zoning used to add a flat 30 points to every allowed site."""
        report = run_scan(context=market_context(competition=0.0, road=0.0, anchor=0.0, building=0.0, market=0.0), hazard=(5, "Very High", []))
        self.assertEqual(report["viability_score"], 5)

    def test_outside_the_mapped_zones_is_not_a_ban(self):
        report = run_scan(zoning=(0, "Outside Mapped Zones", None))
        self.assertGreater(report["viability_score"], 0)
        self.assertNotEqual(report["verdict"]["key"], "not_permitted")
        self.assertEqual(report["breakdown"]["zoning"]["state"], "unverified")
        self.assertTrue(any("City Planning" in note for note in report["data_quality"]["notes"]))


class HazardTests(unittest.TestCase):
    def test_no_layer_is_not_called_safe(self):
        report = run_scan(hazard_cache=())
        self.assertIsNone(report["breakdown"]["hazard"]["score"])
        self.assertEqual(report["breakdown"]["hazard"]["status"], "Hazard Data Unavailable")

    def test_no_layer_rescales_to_market_only(self):
        self.assertEqual(run_scan(hazard_cache=())["market_potential_score"], 80)

    def test_a_worse_flood_zone_lowers_the_score(self):
        safe = run_scan(hazard=(25, "Low Risk / Safe", []))
        flooded = run_scan(hazard=(5, "Very High Flood Hazard (Flood)", ["Very High Flood Hazard (Flood)"]))
        self.assertGreater(safe["viability_score"], flooded["viability_score"])

    def test_very_high_flood_cannot_be_highly_suitable(self):
        report = run_scan(
            context=market_context(market=25.0, competition=25.0, road=25.0, anchor=25.0, building=25.0),
            hazard=(5, "Very High Flood Hazard (Flood)", ["Very High Flood Hazard (Flood)"]),
        )
        self.assertGreaterEqual(report["market_potential_score"], VERDICT_HIGH_MIN)
        self.assertEqual(report["verdict"]["key"], "moderately_suitable")
        self.assertIn("flood", report["verdict"]["reason"])


class CombineCriteriaTests(unittest.TestCase):
    def test_weighted(self):
        total, hazard, market = combine_criteria(25.0, 10.0, 0.25, 0.75)
        self.assertAlmostEqual(total, 55.0)
        self.assertEqual((hazard, market), (0.25, 0.75))

    def test_missing_one_uses_the_other(self):
        self.assertEqual(combine_criteria(None, 10.0, 0.25, 0.75), (40.0, 0.0, 1.0))
        self.assertEqual(combine_criteria(10.0, None, 0.25, 0.75), (40.0, 1.0, 0.0))

    def test_missing_both(self):
        self.assertEqual(combine_criteria(None, None, 0.25, 0.75), (None, 0.0, 0.0))


class ExplanationTests(unittest.TestCase):
    def test_points_add_up_to_the_score(self):
        for context in (
            market_context(),
            market_context(competition=13.3, road=7.7, anchor=21.1, building=3.9, market=11.86),
        ):
            report = run_scan(context=context)
            total_points = sum(row["points"] for row in report["score_explanation"])
            self.assertAlmostEqual(total_points, (25 * 0.25 + context["saturation"]["raw_score"] * 0.75) * 4, delta=0.1)

    def test_every_factor_is_listed_with_its_evidence(self):
        rows = run_scan()["score_explanation"]
        self.assertEqual([row["key"] for row in rows], ["hazard", "competition_density", "road_access", "anchor_proximity", "building_density"])
        self.assertTrue(all(row["evidence"] for row in rows))

    def test_weights_add_up_to_one(self):
        rows = run_scan()["score_explanation"]
        self.assertAlmostEqual(sum(row["weight"] for row in rows), 1.0, places=3)

    def test_competition_counts_at_its_credited_value(self):
        report = run_scan(context=market_context(competition=25.0, credited=5.0))
        row = next(item for item in report["score_explanation"] if item["key"] == "competition_density")
        self.assertEqual(row["score"], 5.0)
        self.assertEqual(report["breakdown"]["competition_density"]["score"], 25.0)
        self.assertEqual(report["breakdown"]["competition_density"]["credited_score"], 5.0)

    def test_a_missing_factor_adds_no_points(self):
        context = market_context(road=None, weights={"competition": 0.5, "anchor": 0.25, "building": 0.25})
        rows = {row["key"]: row for row in run_scan(context=context)["score_explanation"]}
        self.assertFalse(rows["road_access"]["available"])
        self.assertEqual(rows["road_access"]["points"], 0)

    def test_engine_version_is_reported(self):
        self.assertTrue(run_scan()["engine_version"])

    def test_the_radius_does_not_change_the_score(self):
        scores = {run_scan(radius=radius)["viability_score"] for radius in (100, 340, 500, 1500)}
        self.assertEqual(len(scores), 1)


class DataQualityTests(unittest.TestCase):
    def test_all_present_is_high(self):
        self.assertEqual(build_data_quality([], "permitted", [], "x")["confidence"], "high")

    def test_one_gap_is_medium(self):
        self.assertEqual(build_data_quality(["Road access"], "permitted", [], "x")["confidence"], "medium")
        self.assertEqual(build_data_quality([], "unverified", [], "x")["confidence"], "medium")

    def test_many_gaps_are_low(self):
        self.assertEqual(build_data_quality(["Road access", "Flood hazard"], "unverified", [], "x")["confidence"], "low")

    def test_gaps_are_explained(self):
        notes = build_data_quality(["Road access"], "permitted", ["A warning."], "x")["notes"]
        self.assertIn("A warning.", notes)
        self.assertTrue(any("Road access" in note for note in notes))

    def test_weight_source_is_reported(self):
        self.assertEqual(build_data_quality([], "permitted", [], "proponent-provisional")["weights_provenance"], "proponent-provisional")


class VerdictTests(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(score_band(VERDICT_HIGH_MIN), "high")
        self.assertEqual(score_band(VERDICT_HIGH_MIN - 1), "moderate")
        self.assertEqual(score_band(VERDICT_MODERATE_MIN), "moderate")
        self.assertEqual(score_band(VERDICT_MODERATE_MIN - 1), "low")
        self.assertEqual(score_band(None), "low")

    def test_labels_are_the_same_everywhere(self):
        self.assertEqual(classify_site(90, "permitted")["label"], "Highly Suitable")
        self.assertEqual(classify_site(50, "permitted")["label"], "Moderately Suitable")
        self.assertEqual(classify_site(10, "permitted")["label"], "Low Suitability")
        self.assertEqual(classify_site(90, "not_permitted")["label"], "Not Permitted")

    def test_no_data(self):
        self.assertEqual(classify_site(0, "permitted", has_data=False)["key"], "insufficient_data")

    def test_a_ban_outranks_missing_data(self):
        self.assertEqual(classify_site(0, "not_permitted", has_data=False)["key"], "not_permitted")

    def test_unverified_zoning_cannot_be_highly_suitable(self):
        result = classify_site(90, "unverified")
        self.assertEqual(result["key"], "moderately_suitable")
        self.assertIn("zoning", result["reason"])


class ReportingTests(unittest.TestCase):
    def test_the_narrative_handles_a_factor_with_no_data(self):
        narrative = generate_deterministic_scan_narrative(run_scan(hazard_cache=()))
        self.assertIn("not checked", narrative)
        self.assertNotIn("None/25", narrative)

    def test_the_narrative_says_when_zoning_blocks_a_site(self):
        narrative = generate_deterministic_scan_narrative(run_scan(zoning=ZoningConstraintTests.NOT_ALLOWED))
        self.assertIn("does not allow", narrative)

    def test_the_payload_carries_the_verdict(self):
        payload = build_scan_payload(run_scan())
        self.assertEqual(payload["verdict"], "Highly Suitable")
        self.assertIn("data_notes", payload)


if __name__ == "__main__":
    unittest.main()

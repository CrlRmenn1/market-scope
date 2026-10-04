"""
Unit tests for the trend analysis pure functions: profile fit, business-type
picking, and candidate spot building. No database needed.
"""

import unittest

from constants.geo import INDUSTRIAL_ZONE_BUSINESSES, PANABO_ANCHORS, ZONING_LAYERS
from services.trend_candidates import build_area_grid_points, build_scan_candidates
from services.trend_scoring import (
    MIN_FIT_SCORE_FOR_SUGGESTION,
    evaluate_business_fit,
    pick_trend_business_types,
    resolve_primary_business_key,
    summarize_spot,
)
from utils.geo import check_inside_bounds


COFFEE_PROFILE = {
    "primary_business": "coffee",
    "startup_capital": 200000,
    "preferred_setup": "storefront",
    "target_payback_months": 20,
}


class EvaluateBusinessFitTests(unittest.TestCase):
    def test_all_checks_pass(self):
        fit = evaluate_business_fit("coffee", COFFEE_PROFILE)
        self.assertEqual(fit["checks_passed"], 3)
        self.assertEqual(fit["fit_score"], 100)

    def test_capital_below_minimum_fails(self):
        fit = evaluate_business_fit("hardware", {**COFFEE_PROFILE, "startup_capital": 100000})
        capital = next(check for check in fit["checks"] if check["label"] == "Capital")
        self.assertFalse(capital["passed"])

    def test_setup_mismatch_fails(self):
        fit = evaluate_business_fit("carwash", COFFEE_PROFILE)
        setup = next(check for check in fit["checks"] if check["label"] == "Setup")
        self.assertFalse(setup["passed"])

    def test_payback_longer_than_target_fails(self):
        fit = evaluate_business_fit("pharmacy", COFFEE_PROFILE)
        payback = next(check for check in fit["checks"] if check["label"] == "Payback")
        self.assertFalse(payback["passed"])

    def test_handles_missing_values(self):
        fit = evaluate_business_fit("coffee", {})
        self.assertEqual(fit["fit_score"], 0)


class PickTrendBusinessTypesTests(unittest.TestCase):
    def test_primary_business_is_first(self):
        picks = pick_trend_business_types(COFFEE_PROFILE)
        self.assertEqual(picks[0], {"business_key": "coffee", "role": "primary"})

    def test_at_most_two_extra_and_no_duplicates(self):
        picks = pick_trend_business_types(COFFEE_PROFILE)
        keys = [pick["business_key"] for pick in picks]
        self.assertLessEqual(len(picks), 3)
        self.assertEqual(len(keys), len(set(keys)))

    def test_extras_meet_minimum_fit(self):
        for pick in pick_trend_business_types(COFFEE_PROFILE)[1:]:
            fit = evaluate_business_fit(pick["business_key"], COFFEE_PROFILE)
            self.assertGreaterEqual(fit["fit_score"], MIN_FIT_SCORE_FOR_SUGGESTION)
            self.assertEqual(pick["role"], "fit")

    def test_order_is_deterministic(self):
        self.assertEqual(pick_trend_business_types(COFFEE_PROFILE), pick_trend_business_types(COFFEE_PROFILE))

    def test_display_name_resolves_to_key(self):
        self.assertEqual(resolve_primary_business_key({"primary_business": "Coffee Shops"}), "coffee")

    def test_unknown_primary_business_is_skipped(self):
        picks = pick_trend_business_types({**COFFEE_PROFILE, "primary_business": "spaceships"})
        self.assertTrue(all(pick["role"] == "fit" for pick in picks))


class BuildScanCandidatesTests(unittest.TestCase):
    def test_listed_spaces_come_first(self):
        markers = [{"id": "admin-1", "title": "Corner lot", "latitude": 7.3101, "longitude": 125.6801}]
        candidates = build_scan_candidates("coffee", markers)
        self.assertEqual(candidates[0]["source"], "space")
        self.assertEqual(candidates[0]["space_id"], "admin-1")

    def test_includes_every_anchor(self):
        candidates = build_scan_candidates("coffee", [])
        landmarks = [c for c in candidates if c["source"] == "landmark"]
        self.assertEqual(len(landmarks), len(PANABO_ANCHORS))

    def test_area_points_stay_inside_allowed_zones(self):
        for business_key in ("coffee", "carwash"):
            zones = [ZONING_LAYERS["commercial_proper"]]
            if business_key in INDUSTRIAL_ZONE_BUSINESSES:
                zones.append(ZONING_LAYERS["industrial_anflo"])
            for candidate in build_scan_candidates(business_key, []):
                if candidate["source"] != "area":
                    continue
                self.assertTrue(
                    any(check_inside_bounds(candidate["lat"], candidate["lon"], zone) for zone in zones),
                    candidate,
                )

    def test_industrial_zone_only_for_industrial_businesses(self):
        coffee_areas = [c for c in build_scan_candidates("coffee", []) if c["source"] == "area"]
        carwash_areas = [c for c in build_scan_candidates("carwash", []) if c["source"] == "area"]
        self.assertGreater(len(carwash_areas), len(coffee_areas))

    def test_duplicate_spots_are_dropped(self):
        anchor = PANABO_ANCHORS[0]
        markers = [{"id": "user-9", "title": "Stall", "latitude": anchor["lat"], "longitude": anchor["lon"]}]
        candidates = build_scan_candidates("coffee", markers)
        at_anchor = [
            c for c in candidates
            if (round(c["lat"], 4), round(c["lon"], 4)) == (round(anchor["lat"], 4), round(anchor["lon"], 4))
        ]
        self.assertEqual(len(at_anchor), 1)
        self.assertEqual(at_anchor[0]["source"], "space")

    def test_markers_without_coordinates_are_skipped(self):
        candidates = build_scan_candidates("coffee", [{"id": "user-2", "title": "No coords"}])
        self.assertFalse(any(c["source"] == "space" for c in candidates))

    def test_grid_covers_zone_corners(self):
        min_lat, _, min_lon, _ = ZONING_LAYERS["commercial_proper"]
        points = build_area_grid_points("commercial_proper")
        self.assertIn((round(min_lat, 6), round(min_lon, 6)), {(p["lat"], p["lon"]) for p in points})


class SummarizeSpotTests(unittest.TestCase):
    def test_reads_breakdown_statuses(self):
        highlights = summarize_spot({
            "breakdown": {
                "zoning": {"status": "Compliant (Commercial Center)"},
                "hazard": {"status": "Low Risk / Safe"},
                "road_access": {"status": "Primary road frontage"},
            },
            "competitors_found": 1,
            "radius_meters": 340,
        })
        self.assertEqual(highlights, [
            "Zoning: Compliant (Commercial Center)",
            "Flood hazard: Low Risk / Safe",
            "1 competitor within 340 m",
            "Road access: Primary road frontage",
        ])


if __name__ == "__main__":
    unittest.main()

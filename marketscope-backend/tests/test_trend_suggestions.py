"""
Unit tests for business trend suggestions and the scan's failure handling.
No database needed.
"""

import unittest
from unittest.mock import MagicMock, patch

from constants.engine import TREND_GAP_MIN_DEMAND, TREND_MIN_KNOWN_COMPETITORS
from services import trend_scan
from services.trend_suggestions import (
    DATA_ADEQUATE,
    DATA_THIN,
    area_verdict,
    assign_area,
    best_areas_for_business,
    build_areas,
    competitor_data_status,
    is_market_gap,
    rank_area_suggestions,
    strongest_factor,
    summarize_business_in_area,
)


HIGHLY = {"key": "highly_suitable", "label": "Highly Suitable", "tone": "high", "reason": None}
MIN_SCORE = 68
ENOUGH = TREND_MIN_KNOWN_COMPETITORS
TOO_FEW = TREND_MIN_KNOWN_COMPETITORS - 1

GREDU = {"name": "Gredu", "lat": 7.2967, "lon": 125.6787}
SAN_PEDRO = {"name": "San Pedro", "lat": 7.2972, "lon": 125.7100}


def spot(row_id, score, lat=7.2967, lon=125.6787, verdict=HIGHLY, **extra):
    return {
        "id": row_id,
        "viability_score": score,
        "lat": lat,
        "lon": lon,
        "verdict": verdict,
        "candidate_source": "area",
        "candidate_label": f"Spot {row_id}",
        **extra,
    }


def summarize(rows, known=ENOUGH, key="coffee", name="Coffee Shops"):
    return summarize_business_in_area(key, name, rows, known, MIN_SCORE)


class AssignAreaTests(unittest.TestCase):
    def test_picks_the_nearest_place(self):
        self.assertEqual(assign_area(7.2970, 125.7050, [GREDU, SAN_PEDRO])["name"], "San Pedro")
        self.assertEqual(assign_area(7.2970, 125.6800, [GREDU, SAN_PEDRO])["name"], "Gredu")

    def test_no_places_means_no_area(self):
        self.assertIsNone(assign_area(7.3, 125.68, []))


class CompetitorDataStatusTests(unittest.TestCase):
    def test_threshold(self):
        self.assertEqual(competitor_data_status(ENOUGH), DATA_ADEQUATE)
        self.assertEqual(competitor_data_status(TOO_FEW), DATA_THIN)


class StrongestFactorTests(unittest.TestCase):
    def test_market_factor_closest_to_its_maximum_and_never_hazard(self):
        explanation = [
            {"key": "hazard", "label": "Flood hazard", "available": True, "points": 25.0, "max_points": 25.0, "status": "Safe"},
            {"key": "road", "label": "Road access", "available": True, "points": 9.0, "max_points": 10.0, "status": "Good"},
            {"key": "competition", "label": "Competition", "available": True, "points": 18.0, "max_points": 30.0, "status": "Light"},
            {"key": "anchor", "label": "Anchors", "available": False, "points": 0.0, "max_points": 0.0, "status": None},
        ]
        self.assertEqual(strongest_factor(explanation)["label"], "Road access")

    def test_nothing_usable(self):
        self.assertIsNone(strongest_factor(None))
        self.assertIsNone(strongest_factor([{"key": "hazard", "available": True, "points": 25.0, "max_points": 25.0}]))


class MarketGapTests(unittest.TestCase):
    def test_gap_needs_low_competition_real_demand_and_enough_data(self):
        self.assertTrue(is_market_gap(1, TREND_GAP_MIN_DEMAND, DATA_ADEQUATE))
        self.assertFalse(is_market_gap(2, TREND_GAP_MIN_DEMAND, DATA_ADEQUATE))
        self.assertFalse(is_market_gap(0, TREND_GAP_MIN_DEMAND - 0.01, DATA_ADEQUATE))

    def test_thin_data_is_never_a_gap(self):
        self.assertFalse(is_market_gap(0, 1.0, DATA_THIN))

    def test_missing_values_are_not_a_gap(self):
        self.assertFalse(is_market_gap(None, 1.0, DATA_ADEQUATE))
        self.assertFalse(is_market_gap(0, None, DATA_ADEQUATE))


class AreaVerdictTests(unittest.TestCase):
    def test_follows_the_area_score(self):
        self.assertEqual(area_verdict(80, HIGHLY)["key"], "highly_suitable")
        self.assertEqual(area_verdict(60, HIGHLY)["key"], "moderately_suitable")
        self.assertEqual(area_verdict(30, HIGHLY)["key"], "low_suitability")

    def test_a_cap_on_the_best_spot_still_applies(self):
        capped = {"key": "moderately_suitable", "label": "Moderately Suitable", "tone": "medium", "reason": "Very high flood hazard."}
        self.assertEqual(area_verdict(80, capped), capped)

    def test_older_scan_has_no_verdict(self):
        self.assertIsNone(area_verdict(80, None))


class SummarizeBusinessTests(unittest.TestCase):
    def test_score_is_the_average_of_the_top_three(self):
        entry = summarize([spot(1, 90), spot(2, 80), spot(3, 70), spot(4, 10)])
        self.assertEqual(entry["score"], 80)
        self.assertEqual(entry["spots_checked"], 4)
        self.assertEqual(entry["best_spot"]["result_id"], 1)

    def test_one_lucky_spot_does_not_make_a_suggestion(self):
        entry = summarize([spot(1, 90), spot(2, 50), spot(3, 40)])
        self.assertEqual(entry["score"], 60)
        self.assertFalse(entry["is_suggestion"])
        self.assertEqual(entry["verdict"]["key"], "moderately_suitable")

    def test_fewer_spots_than_the_top_count(self):
        self.assertEqual(summarize([spot(1, 80), spot(2, 70)])["score"], 75)

    def test_no_permitted_spots_means_no_entry(self):
        self.assertIsNone(summarize([]))

    def test_older_scan_is_not_a_suggestion(self):
        entry = summarize([spot(1, 90, verdict=None)])
        self.assertFalse(entry["is_suggestion"])
        self.assertIsNone(entry["verdict"])

    def test_gap_uses_the_best_spots_values(self):
        rows = [spot(1, 90, competitor_count=0, demand_share=0.9), spot(2, 80, competitor_count=5, demand_share=0.2)]
        self.assertTrue(summarize(rows)["market_gap"])
        self.assertFalse(summarize(rows, known=TOO_FEW)["market_gap"])

    def test_saved_row_without_a_count_shows_no_gap(self):
        entry = summarize([spot(1, 90, demand_share=0.9)])
        self.assertIsNone(entry["competitor_count"])
        self.assertFalse(entry["market_gap"])

    def test_counts_listed_spaces(self):
        rows = [spot(1, 90), {**spot(2, 80), "candidate_source": "space"}]
        self.assertEqual(summarize(rows)["listed_spaces"], 1)


class RankingTests(unittest.TestCase):
    def test_thin_data_ranks_below_adequate_even_with_a_higher_score(self):
        ranked = rank_area_suggestions([
            summarize([spot(1, 99)], known=TOO_FEW, key="barber", name="Barbershops"),
            summarize([spot(2, 80)], key="print", name="Print"),
        ])
        self.assertEqual([entry["business_key"] for entry in ranked], ["print", "barber"])
        self.assertEqual(ranked[1]["competitor_data"], DATA_THIN)

    def test_thin_suggestion_stays_above_a_non_suggestion(self):
        ranked = rank_area_suggestions([
            summarize([spot(1, 60)], key="print", name="Print"),
            summarize([spot(2, 99)], known=TOO_FEW, key="barber", name="Barbershops"),
        ])
        self.assertEqual([entry["business_key"] for entry in ranked], ["barber", "print"])

    def test_score_then_name(self):
        ranked = rank_area_suggestions([
            summarize([spot(1, 80)], key="water", name="Water"),
            summarize([spot(2, 90)], key="print", name="Print"),
            summarize([spot(3, 80)], key="bakery", name="Bakeries"),
        ])
        self.assertEqual([entry["business_key"] for entry in ranked], ["print", "bakery", "water"])


class BuildAreasTests(unittest.TestCase):
    def _areas(self, rows_by_business, known=None):
        names = {key: key.title() for key in rows_by_business}
        counts = known or {key: ENOUGH for key in rows_by_business}
        return build_areas(rows_by_business, names, counts, [SAN_PEDRO, GREDU], MIN_SCORE)

    def test_groups_by_nearest_place(self):
        areas = self._areas({
            "coffee": [spot(1, 90), spot(2, 70, lat=SAN_PEDRO["lat"], lon=SAN_PEDRO["lon"])],
        })
        self.assertEqual([area["name"] for area in areas], ["Gredu", "San Pedro"])
        self.assertEqual(areas[0]["businesses"][0]["score"], 90)
        self.assertEqual(areas[1]["businesses"][0]["score"], 70)

    def test_a_business_with_no_spot_in_an_area_is_not_listed_there(self):
        areas = self._areas({
            "coffee": [spot(1, 90)],
            "water": [spot(2, 70, lat=SAN_PEDRO["lat"], lon=SAN_PEDRO["lon"])],
        })
        gredu = next(area for area in areas if area["name"] == "Gredu")
        self.assertEqual([entry["business_key"] for entry in gredu["businesses"]], ["coffee"])

    def test_same_point_for_two_businesses_counts_as_one_spot(self):
        areas = self._areas({"coffee": [spot(1, 90)], "water": [spot(2, 70)]})
        self.assertEqual(areas[0]["spots"], 1)

    def test_area_without_permitted_spots_is_left_out(self):
        self.assertEqual([area["name"] for area in self._areas({"coffee": [spot(1, 90)]})], ["Gredu"])

    def test_no_places_means_no_areas(self):
        self.assertEqual(build_areas({"coffee": [spot(1, 90)]}, {"coffee": "Coffee"}, {"coffee": ENOUGH}, [], MIN_SCORE), [])

    def test_best_areas_for_a_business(self):
        areas = self._areas({
            "coffee": [spot(1, 90), spot(2, 75, lat=SAN_PEDRO["lat"], lon=SAN_PEDRO["lon"])],
        })
        picks = best_areas_for_business(areas, "coffee", limit=1)
        self.assertEqual([pick["area_name"] for pick in picks], ["Gredu"])
        self.assertEqual(best_areas_for_business(areas, "water", limit=3), [])


class FailureRuleTests(unittest.TestCase):
    def test_more_than_a_fifth_failed_is_too_many(self):
        self.assertFalse(trend_scan.too_many_failed_spots(20, 100))
        self.assertTrue(trend_scan.too_many_failed_spots(21, 100))
        self.assertTrue(trend_scan.too_many_failed_spots(5, 5))

    def test_no_spots_is_not_a_failure(self):
        self.assertFalse(trend_scan.too_many_failed_spots(0, 0))

    def test_cool_down_only_applies_to_recent_failures(self):
        limit = trend_scan.FAILED_RETRY_COOLDOWN_SECONDS
        self.assertTrue(trend_scan.is_cooling_down({"status": "failed", "age_seconds": limit - 1}))
        self.assertFalse(trend_scan.is_cooling_down({"status": "failed", "age_seconds": limit}))
        self.assertFalse(trend_scan.is_cooling_down({"status": "interrupted", "age_seconds": 1}))
        self.assertFalse(trend_scan.is_cooling_down(None))


class RequestScansTests(unittest.TestCase):
    """request_trend_scans with the database and worker thread replaced."""

    def setUp(self):
        for target, value in (
            ("start_trend_scan_worker", MagicMock()),
            ("open_trend_cursor", MagicMock()),
            ("get_latest_done_run", MagicMock(return_value=None)),
            ("_SCAN_QUEUE", MagicMock()),
            ("_IN_FLIGHT", set()),
        ):
            patcher = patch.object(trend_scan, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _request(self, latest_run, force=False):
        with patch.object(trend_scan, "get_latest_run", return_value=latest_run):
            return trend_scan.request_trend_scans(["coffee"], "page", force=force)

    def test_recent_failure_is_not_retried_on_its_own(self):
        self.assertEqual(self._request({"id": 1, "status": "failed", "age_seconds": 60}), [])
        trend_scan._SCAN_QUEUE.put.assert_not_called()

    def test_rescan_now_ignores_the_cool_down(self):
        self.assertEqual(self._request({"id": 1, "status": "failed", "age_seconds": 60}, force=True), ["coffee"])

    def test_old_failure_is_retried(self):
        old = trend_scan.FAILED_RETRY_COOLDOWN_SECONDS + 1
        self.assertEqual(self._request({"id": 1, "status": "failed", "age_seconds": old}), ["coffee"])

    def test_never_scanned_is_queued(self):
        self.assertEqual(self._request(None), ["coffee"])


class ScanStateTests(unittest.TestCase):
    def _state(self, latest_run, done_run=None, in_flight=False):
        with (
            patch.object(trend_scan, "get_latest_run", return_value=latest_run),
            patch.object(trend_scan, "get_latest_done_run", return_value=done_run),
            patch.object(trend_scan, "is_run_fresh", return_value=True),
            patch.object(trend_scan, "_IN_FLIGHT", {"coffee"} if in_flight else set()),
        ):
            return trend_scan.get_business_scan_state(MagicMock(), "coffee")

    def test_failure_with_nothing_older_shows_as_failed(self):
        state = self._state({"status": "failed", "error": "boom"})
        self.assertEqual(state["state"], "failed")
        self.assertEqual(state["error"], "boom")

    def test_failure_is_reported_while_older_results_are_shown(self):
        state = self._state({"status": "failed", "error": "boom"}, done_run={"id": 1, "age_seconds": 10})
        self.assertEqual(state["state"], "ready")
        self.assertEqual(state["error"], "boom")

    def test_no_error_once_a_retry_is_under_way(self):
        self.assertIsNone(self._state({"status": "failed", "error": "boom"}, in_flight=True)["error"])


if __name__ == "__main__":
    unittest.main()

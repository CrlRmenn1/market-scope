"""
Unit tests for the trend analysis pure functions: which business types get
scanned, candidate spot building, spot highlights and setup-match ranking.
No database needed.
"""

import unittest

from constants.geo import INDUSTRIAL_ZONE_BUSINESSES, PANABO_ANCHORS, ZONING_LAYERS
from constants.map_layers import builtin_zoning_feature_collection
from constants.msme import SME_DATABASE, TYPICAL_SETUP
from services.trend_candidates import build_area_grid_points, build_scan_candidates
from services.zoning import features_to_zoning_cache
from services.trend_preferences import (
    describe_setup_match,
    get_same_setup_business_keys,
    get_trend_scan_business_keys,
    resolve_primary_business_key,
)
from services.trend_recommendations import rank_setup_matches, summarize_spot
from utils.geo import check_inside_bounds
from utils.geo_libs import Point


PHARMACY_STOREFRONT = {"primary_business": "pharmacy", "preferred_setup": "storefront"}

# The built-in zoning layer (the old ZONING_LAYERS boxes), so no database is needed.
BUILTIN_ZONING = features_to_zoning_cache(builtin_zoning_feature_collection()["features"])


def candidates_for(business_key, markers=()):
    return build_scan_candidates(business_key, list(markers), zoning_features=BUILTIN_ZONING)


class TypicalSetupTests(unittest.TestCase):
    def test_every_business_has_a_setup(self):
        self.assertEqual(set(TYPICAL_SETUP), set(SME_DATABASE))


class SameSetupBusinessKeysTests(unittest.TestCase):
    def test_matches_setup_and_excludes_primary(self):
        keys = get_same_setup_business_keys(PHARMACY_STOREFRONT, exclude="pharmacy")
        self.assertNotIn("pharmacy", keys)
        self.assertTrue(keys)
        self.assertTrue(all(TYPICAL_SETUP[key] == "storefront" for key in keys))

    def test_no_setup_means_no_matches(self):
        self.assertEqual(get_same_setup_business_keys({"primary_business": "coffee"}), [])

    def test_setup_is_case_insensitive(self):
        keys = get_same_setup_business_keys({"preferred_setup": " Roadside "})
        self.assertEqual(keys, ["carwash", "moto"])


class TrendScanBusinessKeysTests(unittest.TestCase):
    def test_primary_comes_first_without_duplicates(self):
        keys = get_trend_scan_business_keys(PHARMACY_STOREFRONT)
        self.assertEqual(keys[0], "pharmacy")
        self.assertEqual(len(keys), len(set(keys)))

    def test_primary_outside_setup_is_still_scanned(self):
        keys = get_trend_scan_business_keys({"primary_business": "pharmacy", "preferred_setup": "kiosk"})
        self.assertEqual(keys, ["pharmacy", "kiosk"])

    def test_display_name_resolves_to_key(self):
        self.assertEqual(resolve_primary_business_key({"primary_business": "Coffee Shops"}), "coffee")

    def test_unknown_primary_business_is_skipped(self):
        keys = get_trend_scan_business_keys({"primary_business": "spaceships", "preferred_setup": "warehouse"})
        self.assertEqual(keys, ["hardware"])


class DescribeSetupMatchTests(unittest.TestCase):
    def test_match(self):
        self.assertTrue(describe_setup_match("pharmacy", PHARMACY_STOREFRONT)["matches"])

    def test_mismatch(self):
        result = describe_setup_match("pharmacy", {"preferred_setup": "kiosk"})
        self.assertFalse(result["matches"])
        self.assertIn("kiosk", result["detail"])


class RankSetupMatchesTests(unittest.TestCase):
    def _section(self, name, best_score=None):
        spots = [] if best_score is None else [{"viability_score": best_score}]
        return {"business_name": name, "spots": spots}

    def test_best_spot_score_first_and_limited(self):
        ranked = rank_setup_matches([
            self._section("Bakeries", 80),
            self._section("Coffee Shops", 92),
            self._section("Laundry Shops", 88),
        ])
        self.assertEqual([s["business_name"] for s in ranked], ["Coffee Shops", "Laundry Shops"])

    def test_ties_break_by_name_and_unscanned_are_skipped(self):
        ranked = rank_setup_matches([
            self._section("Water Refilling Stations", 90),
            self._section("Bakeries", 90),
            self._section("Internet Cafes"),
        ])
        self.assertEqual([s["business_name"] for s in ranked], ["Bakeries", "Water Refilling Stations"])


class BuildScanCandidatesTests(unittest.TestCase):
    def test_listed_spaces_come_first(self):
        markers = [{"id": "admin-1", "title": "Corner lot", "latitude": 7.3101, "longitude": 125.6801}]
        candidates = candidates_for("coffee", markers)
        self.assertEqual(candidates[0]["source"], "space")
        self.assertEqual(candidates[0]["space_id"], "admin-1")

    def test_includes_every_anchor(self):
        candidates = candidates_for("coffee")
        landmarks = [c for c in candidates if c["source"] == "landmark"]
        self.assertEqual(len(landmarks), len(PANABO_ANCHORS))

    def test_area_points_stay_inside_allowed_zones(self):
        for business_key in ("coffee", "carwash"):
            zones = [ZONING_LAYERS["commercial_proper"]]
            if business_key in INDUSTRIAL_ZONE_BUSINESSES:
                zones.append(ZONING_LAYERS["industrial_anflo"])
            for candidate in candidates_for(business_key):
                if candidate["source"] != "area":
                    continue
                self.assertTrue(
                    any(check_inside_bounds(candidate["lat"], candidate["lon"], zone) for zone in zones),
                    candidate,
                )

    def test_industrial_zone_only_for_industrial_businesses(self):
        coffee_areas = [c for c in candidates_for("coffee") if c["source"] == "area"]
        carwash_areas = [c for c in candidates_for("carwash") if c["source"] == "area"]
        self.assertGreater(len(carwash_areas), len(coffee_areas))

    def test_duplicate_spots_are_dropped(self):
        anchor = PANABO_ANCHORS[0]
        markers = [{"id": "user-9", "title": "Stall", "latitude": anchor["lat"], "longitude": anchor["lon"]}]
        candidates = candidates_for("coffee", markers)
        at_anchor = [
            c for c in candidates
            if (round(c["lat"], 4), round(c["lon"], 4)) == (round(anchor["lat"], 4), round(anchor["lon"], 4))
        ]
        self.assertEqual(len(at_anchor), 1)
        self.assertEqual(at_anchor[0]["source"], "space")

    def test_markers_without_coordinates_are_skipped(self):
        candidates = candidates_for("coffee", [{"id": "user-2", "title": "No coords"}])
        self.assertFalse(any(c["source"] == "space" for c in candidates))

    def test_grid_covers_zone_corners(self):
        min_lat, _, min_lon, _ = ZONING_LAYERS["commercial_proper"]
        commercial = next(f for f in BUILTIN_ZONING if f["zone_class"] == "commercial")
        points = build_area_grid_points(commercial)
        self.assertIn((round(min_lat, 6), round(min_lon, 6)), {(p["lat"], p["lon"]) for p in points})
        self.assertEqual(points[0]["label"], "Commercial center spot 1")

    def test_grid_skips_points_outside_a_polygon(self):
        triangle = features_to_zoning_cache([{
            "type": "Feature",
            "properties": {"zone_class": "commercial"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [125.67, 7.30], [125.69, 7.30], [125.67, 7.315], [125.67, 7.30],
            ]]},
        }])[0]
        points = build_area_grid_points(triangle)
        self.assertTrue(points)
        self.assertTrue(all(triangle["geometry"].covers(Point(p["lon"], p["lat"])) for p in points))
        self.assertNotIn((7.315, 125.69), {(p["lat"], p["lon"]) for p in points})


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

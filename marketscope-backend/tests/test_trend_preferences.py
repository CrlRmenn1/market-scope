"""
Unit tests for the trend analysis pure functions: which business types get
scanned and candidate spot building. No database needed.
"""

import unittest

from constants.geo import INDUSTRIAL_ZONE_BUSINESSES, PANABO_ANCHORS, ZONING_LAYERS
from constants.map_layers import builtin_zoning_feature_collection
from constants.msme import SME_DATABASE, TYPICAL_SETUP
from services.trend_candidates import build_area_grid_points, build_scan_candidates
from services.zoning import features_to_zoning_cache
from services.trend_preferences import (
    describe_setup_match,
    fits_preferred_setup,
    get_all_scan_business_keys,
    get_same_setup_business_keys,
    get_trend_scan_business_keys,
    resolve_primary_business_key,
)
from utils.geo import check_inside_bounds
from utils.geo_libs import Point


PHARMACY_STOREFRONT = {"primary_business": "pharmacy", "preferred_setup": "storefront"}

# The built-in zoning layer (the old ZONING_LAYERS boxes), so no database is needed.
BUILTIN_ZONING = features_to_zoning_cache(builtin_zoning_feature_collection()["features"])


def candidates_for(business_key, markers=()):
    return build_scan_candidates(business_key, list(markers), zoning_features=BUILTIN_ZONING, landmarks=PANABO_ANCHORS)


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


class AllScanBusinessKeysTests(unittest.TestCase):
    def test_covers_every_business_once_with_the_users_first(self):
        keys = get_all_scan_business_keys({"primary_business": "meat", "preferred_setup": "roadside"})
        self.assertEqual(keys[:3], ["meat", "carwash", "moto"])
        self.assertEqual(sorted(keys), sorted(SME_DATABASE))

    def test_fits_preferred_setup(self):
        self.assertTrue(fits_preferred_setup("carwash", {"preferred_setup": " Roadside "}))
        self.assertFalse(fits_preferred_setup("coffee", {"preferred_setup": "roadside"}))
        self.assertFalse(fits_preferred_setup("coffee", {}))


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
        commercial = next(f for f in BUILTIN_ZONING if f["zone_class"] == "general_commercial")
        points = build_area_grid_points(commercial)
        self.assertIn((round(min_lat, 6), round(min_lon, 6)), {(p["lat"], p["lon"]) for p in points})
        self.assertEqual(points[0]["label"], "Commercial center spot 1")

    def test_grid_skips_points_outside_a_polygon(self):
        triangle = features_to_zoning_cache([{
            "type": "Feature",
            "properties": {"zone_class": "general_commercial"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [125.67, 7.30], [125.69, 7.30], [125.67, 7.315], [125.67, 7.30],
            ]]},
        }])[0]
        points = build_area_grid_points(triangle)
        self.assertTrue(points)
        self.assertTrue(all(triangle["geometry"].covers(Point(p["lon"], p["lat"])) for p in points))
        self.assertNotIn((7.315, 125.69), {(p["lat"], p["lon"]) for p in points})


if __name__ == "__main__":
    unittest.main()

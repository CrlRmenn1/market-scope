"""
Validates the engine against real places, on the real Panabo map file.

The reference study checked its map against known growth areas. This does the same:
sites anyone would call good must outrank sites anyone would call bad. The sites are in
tests/fixtures/engine_benchmark.json, so more can be added without touching this file.

Skipped when data/panabo.pbf isn't there (it is too big for git). No database needed.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from constants.geo import ZONING_LAYERS
from core.paths import PBF_PATH
from services import osm_data, scoring
from services.anchors import merge_anchors

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "engine_benchmark.json").read_text(encoding="utf-8"))
METERS_PER_DEGREE = 111195.0


def market_score(lat, lon, business, radius=340):
    """The market score with no database: OSM data and the original anchor list."""

    def refuse(**_):
        raise RuntimeError("no database in this test")

    osm_anchors = merge_anchors([], osm_data.get_osm_anchor_features())
    with patch.object(scoring.psycopg2, "connect", refuse), \
            patch.object(scoring, "fetch_verified_local_features", lambda *a, **k: []), \
            patch.object(scoring, "fetch_custom_msmes", lambda *a, **k: []), \
            patch.object(scoring, "get_scoring_anchors", lambda *_: (osm_anchors, [])), \
            patch.object(scoring, "get_ahp_weights", lambda *_: None):
        return scoring.evaluate_layered_market_context(lat, lon, radius, business)


@unittest.skipUnless(PBF_PATH.exists(), "data/panabo.pbf is not available")
class BenchmarkTests(unittest.TestCase):
    def test_good_sites_outrank_bad_sites_for_every_business(self):
        for business in FIXTURE["businesses"]:
            good = {site["name"]: market_score(site["lat"], site["lon"], business)["saturation"]["raw_score"] for site in FIXTURE["good_sites"]}
            bad = {site["name"]: market_score(site["lat"], site["lon"], business)["saturation"]["raw_score"] for site in FIXTURE["bad_sites"]}
            self.assertGreater(min(good.values()), max(bad.values()), f"{business}: good {good}, bad {bad}")

    def test_empty_land_has_no_market(self):
        for site in FIXTURE["bad_sites"]:
            if site.get("empty"):
                self.assertLess(market_score(site["lat"], site["lon"], "coffee")["saturation"]["raw_score"], 1.0, site["name"])

    def test_gaisano_grand_counts_as_an_anchor(self):
        """It wasn't on the old hard-coded list, so a site beside the mall got no credit for it."""
        site = next(item for item in FIXTURE["good_sites"] if item["name"] == "Gaisano Grand Panabo")
        result = market_score(site["lat"], site["lon"], "coffee")["anchor_proximity"]
        self.assertIn("Gaisano Grand Panabo", result["anchors_found"])
        self.assertGreater(result["score"], 0)

    def test_osm_shops_mapped_as_points_are_found(self):
        """The old loader skipped these, so most businesses looked like they had no competition."""
        coffee_shops = sum(len(osm_data.get_cached_pbf_competitors(key, value)) for key, value in [("amenity", "cafe"), ("shop", "coffee")])
        self.assertGreaterEqual(coffee_shops, 5)


@unittest.skipUnless(PBF_PATH.exists(), "data/panabo.pbf is not available")
class StabilityTests(unittest.TestCase):
    """The same 154 commercial-area points the old engine was measured on. There, moving
    a pin 25 m changed the road score by 5 or more at 36% of the points."""

    @classmethod
    def setUpClass(cls):
        min_lat, _, min_lon, _ = ZONING_LAYERS["commercial_proper"]
        cls.points = [
            (min_lat + lat_step * 0.0015, min_lon + lon_step * 0.0015)
            for lat_step in range(11)
            for lon_step in range(14)
        ]
        osm_data.preload_pbf_spatial_context_cache()

    def test_a_small_pin_move_cannot_swing_road_access(self):
        shift = 25.0 / METERS_PER_DEGREE
        for lat, lon in self.points:
            scores = [
                scoring._score_road_access(lat + d_lat, lon + d_lon)["raw_score"]
                for d_lat, d_lon in ((0, 0), (shift, 0), (-shift, 0), (0, shift), (0, -shift))
            ]
            self.assertLess(max(scores) - min(scores), 5.0, (lat, lon))

    def test_the_view_radius_never_changes_the_market_score(self):
        for lat, lon in self.points[::20]:
            scores = {round(market_score(lat, lon, "coffee", radius=radius)["saturation"]["raw_score"], 6) for radius in (100, 340, 500, 1500)}
            self.assertEqual(len(scores), 1, (lat, lon))

    def test_repeat_scans_give_the_same_score(self):
        lat, lon = self.points[len(self.points) // 2]
        scores = {market_score(lat, lon, "coffee")["saturation"]["raw_score"] for _ in range(3)}
        self.assertEqual(len(scores), 1)


if __name__ == "__main__":
    unittest.main()

"""
Tests for the scoring engine's factors and how they combine. No database or map file
needed: roads and buildings are small hand-made indexes around a test point.
"""

import math
import unittest
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import LineString

from constants.engine import ANCHOR_ZERO_FACTOR, FACTOR_MAX, ROAD_FRONTAGE_BANDS_M, ROAD_MAJOR_BANDS_M
from constants.msme import MSME_CATEGORY_PROFILES
from services import osm_data, scoring
from services.anchors import STATUS_ACTIVE, STATUS_DUPLICATE, STATUS_HIDDEN, merge_anchors
from services.osm_data import BuildingIndex, RoadIndex, anchor_tag_for
from services.value_functions import anchor_value, band_membership, competitor_pull

LAT, LON = 7.30, 125.68
M_PER_DEG_LAT = 111194.9
COFFEE = MSME_CATEGORY_PROFILES["coffee"]


def north(meters):
    return LAT + meters / M_PER_DEG_LAT


def east_west_road(road_class, meters_north, name=None):
    """A long straight east-west road, this many metres north of the test point."""
    line = LineString([(LON - 0.05, north(meters_north)), (LON + 0.05, north(meters_north))])
    return line, road_class, name


def road_index(*roads):
    lines, classes, names = zip(*roads)
    return RoadIndex(lines, classes, names)


def anchor(name, meters_north, power=25, category="market", **extra):
    return {"name": name, "lat": north(meters_north), "lon": LON, "power": power, "category": category, **extra}


def road_score_with(*roads, verified=None):
    index = road_index(*roads) if roads else None
    with patch.object(osm_data, "ROAD_INDEX", index):
        return scoring._score_road_access(LAT, LON, verified_roads=verified)


class ValueFunctionTests(unittest.TestCase):
    def test_band_points(self):
        self.assertEqual(band_membership(100, 250, 500, 1000), 1.0)
        self.assertEqual(band_membership(250, 250, 500, 1000), 1.0)
        self.assertAlmostEqual(band_membership(500, 250, 500, 1000), 0.5)
        self.assertEqual(band_membership(1000, 250, 500, 1000), 0.0)

    def test_small_moves_make_small_changes(self):
        previous = band_membership(0, 250, 500, 1000)
        for meters in range(1, 1200):
            current = band_membership(meters, 250, 500, 1000)
            self.assertLess(abs(current - previous), 0.005, meters)
            previous = current

    def test_anchor_fades_out_instead_of_cutting_off(self):
        self.assertEqual(anchor_value(100, "market"), 1.0)
        self.assertAlmostEqual(anchor_value(800, "market"), 0.5)
        self.assertGreater(anchor_value(1100, "market"), 0.0)
        self.assertEqual(anchor_value(800 * ANCHOR_ZERO_FACTOR, "market"), 0.0)

    def test_unknown_anchor_category_still_has_a_band(self):
        self.assertEqual(anchor_value(100, "something else"), 1.0)

    def test_competitor_pull(self):
        self.assertEqual(competitor_pull(0), 1.0)
        self.assertAlmostEqual(competitor_pull(400), 0.5)
        self.assertEqual(competitor_pull(900), 0.0)


class RoadAccessTests(unittest.TestCase):
    def test_a_footpath_does_not_hide_a_highway(self):
        """The old engine scored only the nearest road, footpaths included."""
        lines = [east_west_road("footway", 5)[0], east_west_road("trunk", 30)[0]]
        gdf = gpd.GeoDataFrame({"highway": ["footway", "trunk"], "name": [None, "Highway"]}, geometry=lines)
        index = osm_data._build_road_index(gdf)
        self.assertEqual(len(index), 1)
        with patch.object(osm_data, "ROAD_INDEX", index):
            self.assertEqual(scoring._score_road_access(LAT, LON)["score"], FACTOR_MAX)

    def test_best_road_wins_not_the_nearest(self):
        with_alley = road_score_with(east_west_road("service", 5), east_west_road("trunk", 40))
        without_alley = road_score_with(east_west_road("trunk", 40))
        self.assertGreaterEqual(with_alley["score"], without_alley["score"])

    def test_highway_counts_for_every_business(self):
        """Trunk used to lose points for most business types; it has no profile penalty now."""
        self.assertEqual(road_score_with(east_west_road("trunk", 10))["score"], FACTOR_MAX)

    def test_major_road_bands_from_the_study(self):
        full = road_score_with(east_west_road("primary", ROAD_MAJOR_BANDS_M[0]))
        half = road_score_with(east_west_road("primary", ROAD_MAJOR_BANDS_M[1]))
        self.assertGreater(full["raw_score"], half["raw_score"])
        # Half the major-road share is lost; 250 m is also still just in frontage range.
        frontage_at_250 = 0.5 * (300 - 250) / (300 - 100)
        self.assertAlmostEqual(full["raw_score"] - half["raw_score"], FACTOR_MAX * (0.6 * 0.5 + 0.4 * frontage_at_250), places=2)

    def test_frontage_counts_at_the_door(self):
        at_door = road_score_with(east_west_road("residential", ROAD_FRONTAGE_BANDS_M[0] - 5))
        far_back = road_score_with(east_west_road("residential", 290))
        self.assertGreater(at_door["score"], far_back["score"])

    def test_no_road_in_range_is_a_real_zero(self):
        result = road_score_with(east_west_road("trunk", 1500))
        self.assertTrue(result["available"])
        self.assertEqual(result["score"], 0)

    def test_score_moves_gently_with_the_pin(self):
        index = road_index(east_west_road("trunk", 300, "Highway"), east_west_road("residential", 80))
        with patch.object(osm_data, "ROAD_INDEX", index):
            scores = [scoring._score_road_access(north(meters), LON)["raw_score"] for meters in range(-400, 400, 5)]
        for before, after in zip(scores, scores[1:]):
            self.assertLess(abs(after - before), 1.0)

    def test_verified_road_joins_the_pool_instead_of_overriding(self):
        weak_verified = [{"latitude": north(200), "longitude": LON, "road_class": "track", "name": "Old track"}]
        result = road_score_with(east_west_road("trunk", 20, "Highway"), verified=weak_verified)
        self.assertEqual(result["score"], FACTOR_MAX)

    def test_verified_road_alone_is_enough(self):
        verified = [{"latitude": north(20), "longitude": LON, "road_class": "primary", "name": "New road"}]
        self.assertEqual(road_score_with(verified=verified)["score"], FACTOR_MAX)

    def test_missing_road_data_is_not_a_score(self):
        result = road_score_with()
        self.assertFalse(result["available"])
        self.assertIsNone(result["score"])

    def test_evidence_names_the_road(self):
        result = road_score_with(east_west_road("trunk", 180, "National Highway"))
        self.assertIn("National Highway (trunk) 180 m", result["evidence"])


class AnchorTests(unittest.TestCase):
    def test_no_anchors_nearby(self):
        result = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("Far", 5000)])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["nearby_anchors"], [])

    def test_more_anchors_add_less_and_less(self):
        one = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("A", 100)])["raw_score"]
        two = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("A", 100), anchor("B", 100)])["raw_score"]
        three = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("A", 100), anchor("B", 100), anchor("C", 100)])["raw_score"]
        self.assertGreater(two - one, three - two)
        self.assertLess(three, FACTOR_MAX)

    def test_a_stronger_anchor_counts_for_more(self):
        strong = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("Mall", 100, power=25)])
        weak = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("Office", 100, power=5)])
        self.assertGreater(strong["score"], weak["score"])

    def test_no_cliff_at_the_edge(self):
        just_inside = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("A", 1190)])["raw_score"]
        just_outside = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("A", 1210)])["raw_score"]
        self.assertLess(just_inside - just_outside, 0.5)

    def test_unavailable_when_the_list_cannot_load(self):
        result = scoring._score_anchor_proximity(LAT, LON, COFFEE, None)
        self.assertFalse(result["available"])

    def test_evidence_names_the_anchor(self):
        result = scoring._score_anchor_proximity(LAT, LON, COFFEE, [anchor("Gaisano Grand", 210)])
        self.assertIn("Gaisano Grand (210 m)", result["evidence"])


class AnchorMergeTests(unittest.TestCase):
    OSM = {"osm_ref": "way/1", "name": "Some Market", "category": "market", "power": 25, "lat": north(500), "lon": LON, "tag": "amenity=marketplace"}

    def row(self, **overrides):
        row = {
            "id": 1, "name": "Added Anchor", "feature_subtype": "market", "power": 15,
            "latitude": north(50), "longitude": LON, "is_active": True, "osm_ref": None,
            "created_by_admin_email": "admin@example.test",
        }
        row.update(overrides)
        return row

    def test_database_rows_use_latitude_and_longitude(self):
        """The bug this fixes: rows have latitude/longitude, and the scorer read lat/lon."""
        merged = merge_anchors([self.row()], [])
        result = scoring._score_anchor_proximity(LAT, LON, COFFEE, merged)
        self.assertGreater(result["score"], 0)
        self.assertEqual(result["nearby_anchors"][0]["name"], "Added Anchor")

    def test_all_sources_are_counted(self):
        merged = merge_anchors([self.row()], [self.OSM])
        self.assertEqual({item["origin"] for item in merged}, {"admin", "osm"})
        self.assertTrue(all(item["status"] == STATUS_ACTIVE for item in merged))

    def test_seeded_rows_are_marked(self):
        merged = merge_anchors([self.row(created_by_admin_email="system-seed")], [])
        self.assertEqual(merged[0]["origin"], "seed")

    def test_osm_anchor_can_be_hidden(self):
        merged = merge_anchors([self.row(osm_ref="way/1", is_active=False)], [self.OSM])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["status"], STATUS_HIDDEN)

    def test_osm_anchor_can_be_corrected(self):
        merged = merge_anchors([self.row(osm_ref="way/1", name="Corrected Name", power=5)], [self.OSM])
        self.assertEqual(merged[0]["name"], "Corrected Name")
        self.assertEqual(merged[0]["power"], 5)
        self.assertEqual(merged[0]["origin"], "osm")
        self.assertTrue(merged[0]["edited"])

    def test_same_place_is_not_counted_twice(self):
        nearby_osm = {**self.OSM, "lat": north(90)}
        merged = merge_anchors([self.row()], [nearby_osm])
        osm_item = next(item for item in merged if item["origin"] == "osm")
        self.assertEqual(osm_item["status"], STATUS_DUPLICATE)
        self.assertEqual(osm_item["duplicate_of"], "Added Anchor")

    def test_a_hidden_anchor_does_not_mark_others_as_duplicates(self):
        nearby_osm = {**self.OSM, "lat": north(90)}
        merged = merge_anchors([self.row(is_active=False)], [nearby_osm])
        osm_item = next(item for item in merged if item["origin"] == "osm")
        self.assertEqual(osm_item["status"], STATUS_ACTIVE)

    def test_a_different_category_nearby_is_a_different_place(self):
        nearby_school = {**self.OSM, "lat": north(90), "category": "education"}
        merged = merge_anchors([self.row()], [nearby_school])
        self.assertEqual(next(item for item in merged if item["origin"] == "osm")["status"], STATUS_ACTIVE)


class OsmTagTests(unittest.TestCase):
    def test_other_tags_are_read(self):
        """GDAL leaves amenity and shop in other_tags on the points layer."""
        row = {"other_tags": '"amenity"=>"cafe","cuisine"=>"coffee_shop"', "name": "A Cafe"}
        self.assertEqual(osm_data._feature_tags(row)["amenity"], "cafe")

    def test_columns_are_read_too(self):
        self.assertEqual(osm_data._feature_tags({"shop": "mall"})["shop"], "mall")

    def test_anchor_tags(self):
        self.assertEqual(anchor_tag_for({"shop": "mall"}, "Gaisano")[0], "commercial")
        self.assertIsNone(anchor_tag_for({"amenity": "atm"}, "An ATM"))
        self.assertIsNone(anchor_tag_for({"amenity": "place_of_worship"}, "A Church"))

    def test_barangay_halls_count_less_than_city_hall(self):
        city_hall = anchor_tag_for({"amenity": "townhall"}, "Panabo City Hall")
        barangay = anchor_tag_for({"amenity": "townhall"}, "Gredu Barangay Hall")
        self.assertGreater(city_hall[1], barangay[1])

    def test_keywords_match_whole_words(self):
        pattern = osm_data._KEYWORD_PATTERNS["laundry"]
        self.assertIsNone(pattern.search("John & Jai Carwash"))
        self.assertIsNotNone(pattern.search("Sunshine Laundry"))

    def test_same_place_mapped_twice_is_kept_once(self):
        first = {"name": "Aces College", "lat": 7.31156, "lon": 125.67691}
        second = {"name": "aces college", "lat": 7.3117, "lon": 125.67689}
        self.assertEqual(len(osm_data._dedupe_anchor_features([first, second])), 1)


class CompetitionTests(unittest.TestCase):
    def score(self, competitors):
        return scoring._score_competitor_density(LAT, LON, competitors, COFFEE)

    def shop(self, meters, name="Shop", source="osm"):
        return {"lat": north(meters), "lon": LON, "name": name, "source": source}

    def test_none_is_the_maximum(self):
        self.assertEqual(self.score([])["score"], FACTOR_MAX)

    def test_more_competitors_score_lower(self):
        scores = [self.score([self.shop(100, f"S{i}") for i in range(count)])["score"] for count in (1, 3, 8)]
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[1], scores[2])

    def test_closer_competitors_count_for_more(self):
        self.assertLess(self.score([self.shop(50)])["score"], self.score([self.shop(600)])["score"])

    def test_every_source_counts_the_same(self):
        verified = self.score([self.shop(100, source="verified_local")])["score"]
        self.assertEqual(verified, self.score([self.shop(100, source="osm")])["score"])

    def test_competitors_beyond_reach_do_not_count(self):
        self.assertEqual(self.score([self.shop(900)])["score"], FACTOR_MAX)

    def test_same_shop_from_two_sources_counts_once(self):
        found = []
        scoring._add_competitor(found, {"latitude": north(100), "longitude": LON, "name": "Bean House"}, LAT, LON, 800, "verified_local")
        scoring._add_competitor(found, {"lat": north(110), "lon": LON, "name": "bean house"}, LAT, LON, 800, "osm")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["source"], "verified_local")

    def test_different_shops_side_by_side_both_count(self):
        found = []
        scoring._add_competitor(found, {"lat": north(100), "lon": LON, "name": "Bean House"}, LAT, LON, 800, "osm")
        scoring._add_competitor(found, {"lat": north(110), "lon": LON, "name": "Cup of Joe"}, LAT, LON, 800, "osm")
        self.assertEqual(len(found), 2)


class DemandCreditTests(unittest.TestCase):
    WEIGHTS = {"competition": 0.4, "road": 0.2, "anchor": 0.2, "building": 0.2}

    def factor(self, score, available=True):
        return {"available": available, "raw_score": score if available else None, "score": score, "evidence": "Evidence."}

    def components(self, competition=25.0, road=25.0, anchor_score=25.0, building=25.0):
        return {
            "competition": self.factor(competition),
            "road": self.factor(road),
            "anchor": self.factor(anchor_score),
            "building": self.factor(building),
        }

    def test_full_demand_keeps_full_credit(self):
        self.assertEqual(scoring.demand_share(self.components(), self.WEIGHTS), 1.0)

    def test_empty_land_gets_no_credit_for_having_no_competitors(self):
        parts = self.components(road=0.0, anchor_score=0.0, building=0.0)
        share = scoring.demand_share(parts, self.WEIGHTS)
        scoring.apply_demand_credit(parts["competition"], share)
        self.assertEqual(parts["competition"]["credited_score"], 0.0)
        market, _ = scoring.combine_market_factors(parts, self.WEIGHTS)
        self.assertEqual(market, 0.0)

    def test_busy_area_with_rivals_beats_empty_land(self):
        busy = self.components(competition=12.0)
        scoring.apply_demand_credit(busy["competition"], scoring.demand_share(busy, self.WEIGHTS))
        empty = self.components(road=0.0, anchor_score=0.0, building=0.0)
        scoring.apply_demand_credit(empty["competition"], scoring.demand_share(empty, self.WEIGHTS))
        self.assertGreater(scoring.combine_market_factors(busy, self.WEIGHTS)[0], scoring.combine_market_factors(empty, self.WEIGHTS)[0])

    def test_road_alone_is_not_demand(self):
        parts = self.components(road=25.0, anchor_score=0.0, building=0.0)
        self.assertEqual(scoring.demand_share(parts, self.WEIGHTS), 0.0)

    def test_missing_demand_data_does_not_cut_the_credit(self):
        parts = self.components()
        parts["anchor"] = self.factor(0, available=False)
        parts["building"] = self.factor(0, available=False)
        self.assertEqual(scoring.demand_share(parts, self.WEIGHTS), 1.0)

    def test_the_factor_itself_still_says_how_crowded_it_is(self):
        parts = self.components(anchor_score=10.0, building=10.0)
        scoring.apply_demand_credit(parts["competition"], scoring.demand_share(parts, self.WEIGHTS))
        self.assertEqual(parts["competition"]["raw_score"], 25.0)
        self.assertEqual(parts["competition"]["credited_score"], 10.0)
        self.assertIn("Counted at 40%", parts["competition"]["evidence"])


class CombineMarketTests(unittest.TestCase):
    WEIGHTS = {"competition": 0.4, "road": 0.2, "anchor": 0.2, "building": 0.2}

    def component(self, score, available=True):
        return {"available": available, "raw_score": score if available else None}

    def test_weighted_average(self):
        parts = {key: self.component(10.0) for key in self.WEIGHTS}
        parts["competition"] = self.component(20.0)
        market, used = scoring.combine_market_factors(parts, self.WEIGHTS)
        self.assertAlmostEqual(market, 14.0)
        self.assertAlmostEqual(sum(used.values()), 1.0)

    def test_a_missing_factor_is_left_out_and_the_rest_rescaled(self):
        parts = {key: self.component(10.0) for key in self.WEIGHTS}
        parts["road"] = self.component(None, available=False)
        market, used = scoring.combine_market_factors(parts, self.WEIGHTS)
        self.assertAlmostEqual(market, 10.0)
        self.assertNotIn("road", used)
        self.assertAlmostEqual(used["competition"], 0.5)

    def test_nothing_available(self):
        parts = {key: self.component(None, available=False) for key in self.WEIGHTS}
        self.assertEqual(scoring.combine_market_factors(parts, self.WEIGHTS), (None, {}))


class BuildingTests(unittest.TestCase):
    def test_nearer_buildings_count_for_more(self):
        x, y = 0.0, 0.0
        index = BuildingIndex([x], [y], [1.0], [1.0])
        near, near_count = index.intensity(7.30, 125.68, 400)
        far, far_count = index.intensity(north(200), LON, 400)
        self.assertGreater(near, far)
        self.assertEqual((near_count, far_count), (1, 1))

    def test_buildings_beyond_reach_do_not_count(self):
        index = BuildingIndex([0.0], [0.0], [1.0], [1.0])
        self.assertEqual(index.intensity(north(500), LON, 400), (0.0, 0))

    def test_empty_area_scores_zero(self):
        with patch.object(osm_data, "BUILDING_INDEX", BuildingIndex([0.0], [0.0], [1.0], [1.0])):
            self.assertEqual(scoring._score_building_density(north(5000), LON)["score"], 0)

    def test_missing_data_is_not_a_score(self):
        with patch.object(osm_data, "BUILDING_INDEX", None):
            self.assertFalse(scoring._score_building_density(LAT, LON)["available"])


class LocalMetresTests(unittest.TestCase):
    def test_road_distance_is_in_real_metres(self):
        index = road_index(east_west_road("trunk", 300))
        distance_m, _ = index.nearest_by_class(LAT, LON, 1000)["trunk"]
        self.assertTrue(math.isclose(distance_m, 300, abs_tol=1.0), distance_m)

    def test_only_roads_in_range_are_returned(self):
        index = road_index(east_west_road("trunk", 300))
        self.assertEqual(index.nearest_by_class(LAT, LON, 100), {})


if __name__ == "__main__":
    unittest.main()

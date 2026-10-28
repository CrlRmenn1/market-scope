"""
Unit tests for map layer stacking (services/layer_stack.py): the shape on top
wins its area, shapes are stored whole, and old layers keep their old results.
No database needed.
"""

import unittest

from services.layer_stack import flatten_feature_collection, flatten_features, order_by_old_priority
from services.zoning import evaluate_zoning, features_to_zoning_cache
from services import zoning as zoning_service
from utils.geo_libs import Point, shape


def square(zone_class, west, south, east, north, label=None):
    properties = {"zone_class": zone_class}
    if label:
        properties["label"] = label
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]},
    }


BIG_HIGH = square("high", 125.66, 7.29, 125.70, 7.32)
SMALL_MODERATE = square("moderate", 125.67, 7.30, 125.68, 7.31)
INSIDE_SMALL = Point(125.675, 7.305)
INSIDE_BIG_ONLY = Point(125.69, 7.315)


def class_at(flattened, point):
    matches = [item["zone_class"] for item in flattened if item["geometry"].intersects(point)]
    return matches


class FlattenFeaturesTests(unittest.TestCase):
    def test_shape_on_top_wins_its_area(self):
        flattened = flatten_features([BIG_HIGH, SMALL_MODERATE])
        self.assertEqual(class_at(flattened, INSIDE_SMALL), ["moderate"])
        self.assertEqual(class_at(flattened, INSIDE_BIG_ONLY), ["high"])

    def test_shape_underneath_wins_when_it_is_on_top(self):
        flattened = flatten_features([SMALL_MODERATE, BIG_HIGH])
        self.assertEqual(class_at(flattened, INSIDE_SMALL), ["high"])
        self.assertEqual([item["zone_class"] for item in flattened], ["high"])  # the small one is fully covered

    def test_removing_the_top_shape_restores_the_one_below(self):
        flattened = flatten_features([BIG_HIGH])
        self.assertEqual(class_at(flattened, INSIDE_SMALL), ["high"])
        self.assertAlmostEqual(flattened[0]["geometry"].area, shape(BIG_HIGH["geometry"]).area)

    def test_same_class_stacking_keeps_full_coverage(self):
        flattened = flatten_features([BIG_HIGH, square("high", 125.67, 7.30, 125.68, 7.31)])
        self.assertEqual(class_at(flattened, INSIDE_SMALL), ["high"])
        self.assertAlmostEqual(sum(item["geometry"].area for item in flattened), shape(BIG_HIGH["geometry"]).area)

    def test_flattened_shapes_never_overlap(self):
        stack = [BIG_HIGH, SMALL_MODERATE, square("very_high", 125.675, 7.305, 125.69, 7.315)]
        flattened = flatten_features(stack)
        for index, first in enumerate(flattened):
            for second in flattened[index + 1:]:
                self.assertAlmostEqual(first["geometry"].intersection(second["geometry"]).area, 0.0, places=12)

    def test_feature_collection_keeps_labels_and_order(self):
        collection = flatten_feature_collection({"type": "FeatureCollection", "features": [BIG_HIGH, square("moderate", 125.67, 7.30, 125.68, 7.31, label="Riverside")]})
        self.assertEqual([feature["properties"] for feature in collection["features"]], [{"zone_class": "high"}, {"zone_class": "moderate", "label": "Riverside"}])
        self.assertEqual(collection["features"][0]["geometry"]["type"], "Polygon")  # the big square now has a hole


class OldPriorityOrderTests(unittest.TestCase):
    def test_hazard_puts_most_severe_on_top(self):
        features = [square("very_high", 0, 0, 1, 1), square("moderate", 0, 0, 1, 1), square("high", 0, 0, 1, 1)]
        ordered = [feature["properties"]["zone_class"] for feature in order_by_old_priority("hazard", features)]
        self.assertEqual(ordered, ["moderate", "high", "very_high"])

    def test_zoning_puts_best_old_score_on_top(self):
        features = [square("commercial", 0, 0, 1, 1), square("residential", 0, 0, 1, 1), square("mixed_use", 0, 0, 1, 1)]
        ordered = [feature["properties"]["zone_class"] for feature in order_by_old_priority("zoning", features)]
        self.assertEqual(ordered, ["residential", "mixed_use", "commercial"])

    def test_sort_is_stable(self):
        first, second = square("high", 0, 0, 1, 1, label="first"), square("high", 0, 0, 1, 1, label="second")
        self.assertEqual(order_by_old_priority("hazard", [first, second]), [first, second])


class ZoningStackTests(unittest.TestCase):
    def setUp(self):
        self._saved = (zoning_service.ZONING_LAYER_CACHE, zoning_service.ZONING_LAYER_CACHE_LOADED, zoning_service.ZONING_LAYER_SOURCE)

    def tearDown(self):
        zoning_service.ZONING_LAYER_CACHE, zoning_service.ZONING_LAYER_CACHE_LOADED, zoning_service.ZONING_LAYER_SOURCE = self._saved

    def use_layer(self, features):
        zoning_service.ZONING_LAYER_CACHE = features_to_zoning_cache(features)
        zoning_service.ZONING_LAYER_CACHE_LOADED = True
        zoning_service.ZONING_LAYER_SOURCE = "test layer"

    def test_residential_inside_commercial_is_read(self):
        self.use_layer([square("general_commercial", 125.66, 7.29, 125.70, 7.32), square("general_residential", 125.67, 7.30, 125.68, 7.31)])
        # Hardware stores are allowed in commercial zones but not residential ones (default table).
        self.assertEqual(evaluate_zoning(7.305, 125.675, "hardware")[:2], (0, "Not Allowed in General Residential Zone"))
        self.assertEqual(evaluate_zoning(7.315, 125.69, "hardware")[:2], (25, "Allowed in General Commercial Zone"))


if __name__ == "__main__":
    unittest.main()

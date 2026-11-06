"""
Tests for what the admin Anchors page can save, and for the scan's bounds check.
No database needed.
"""

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import HTTPException

from constants.engine import ANCHOR_CATEGORIES, ENGINE_VERSION
from constants.geo import PANABO_ANCHORS
from models.requests import AdminAnchorRequest, AnalysisRequest
from routers.analysis import _check_scan_request
from routers.anchors import validate_anchor_payload
from services import map_layers
from services.anchors import _builtin_anchor_rows, merge_anchors


def payload(**overrides):
    values = {"name": "New Mall", "category": "commercial", "latitude": 7.30, "longitude": 125.68, "power": 25}
    values.update(overrides)
    return AdminAnchorRequest(**values)


class AnchorValidationTests(unittest.TestCase):
    def assert_rejected(self, **overrides):
        with self.assertRaises(HTTPException) as caught:
            validate_anchor_payload(payload(**overrides))
        self.assertEqual(caught.exception.status_code, 400)

    def test_a_good_anchor_is_accepted(self):
        self.assertEqual(validate_anchor_payload(payload(name="  New Mall  ")), "New Mall")

    def test_needs_a_name(self):
        self.assert_rejected(name="   ")

    def test_long_names_are_rejected(self):
        self.assert_rejected(name="x" * 201)

    def test_must_be_a_known_category(self):
        self.assert_rejected(category="spaceport")

    def test_importance_has_a_range(self):
        self.assert_rejected(power=0)
        self.assert_rejected(power=26)
        validate_anchor_payload(payload(power=20))

    def test_must_be_inside_panabo(self):
        self.assert_rejected(latitude=7.0)
        self.assert_rejected(longitude=126.5)


class BuiltinAnchorTests(unittest.TestCase):
    def test_every_original_anchor_has_a_valid_category(self):
        for anchor in PANABO_ANCHORS:
            self.assertIn(anchor["category"], ANCHOR_CATEGORIES, anchor["name"])

    def test_original_list_survives_a_database_failure(self):
        merged = merge_anchors(_builtin_anchor_rows(), [])
        self.assertEqual(len(merged), len(PANABO_ANCHORS))
        self.assertTrue(all(item["origin"] == "seed" and item["lat"] for item in merged))


class EngineVersionFlagTests(unittest.TestCase):
    def run_check(self, saved_flag):
        @contextmanager
        def fake_cursor():
            yield object()

        writes = []
        with patch.object(map_layers, "open_map_layer_cursor", fake_cursor), \
                patch.object(map_layers, "get_flag", lambda cursor, key: saved_flag), \
                patch.object(map_layers, "set_flag", lambda cursor, key, value=None: writes.append((key, value))):
            map_layers.mark_stale_if_engine_changed()
        return writes

    def test_a_new_engine_marks_saved_trend_scans_stale(self):
        writes = self.run_check({"value": "1.0"})
        self.assertIn((map_layers.ENGINE_VERSION_FLAG, ENGINE_VERSION), writes)
        self.assertIn((map_layers.CHANGED_FLAG, None), writes)

    def test_the_same_engine_leaves_them_alone(self):
        self.assertEqual(self.run_check({"value": ENGINE_VERSION}), [])


class ScanRequestTests(unittest.TestCase):
    def test_inside_panabo_is_fine(self):
        _check_scan_request(AnalysisRequest(lat=7.30, lon=125.68, business_type="coffee", radius=340))

    def test_outside_panabo_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            _check_scan_request(AnalysisRequest(lat=14.6, lon=121.0, business_type="coffee", radius=340))
        self.assertEqual(caught.exception.status_code, 400)

    def test_silly_radius_is_rejected(self):
        with self.assertRaises(HTTPException):
            _check_scan_request(AnalysisRequest(lat=7.30, lon=125.68, business_type="coffee", radius=100000))


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for pass/fail zoning against the LGU zones (services/zoning.py) and
the conversion of the old zoning class names. No database needed.
"""

import unittest

from constants.map_layers import DEFAULT_ZONING_ALLOWED_USES, LEGACY_ZONE_CLASSES, ZONING_CLASSES
from constants.msme import SME_DATABASE
from services import zoning as zoning_service
from services.map_layers import resolve_zone_class
from services.zoning import allowed_uses_from_rows, allowed_zone_classes, zoning_class_score


class ZoningAllowedTests(unittest.TestCase):
    def setUp(self):
        self._saved = zoning_service.ZONING_ALLOWED_USES

    def tearDown(self):
        zoning_service.ZONING_ALLOWED_USES = self._saved

    def test_allowed_scores_full_and_not_allowed_scores_zero(self):
        zoning_service.ZONING_ALLOWED_USES = {"tourism": frozenset({"coffee"})}
        self.assertEqual(zoning_class_score("tourism", "coffee"), (25, "Allowed in Tourism Zone"))
        self.assertEqual(zoning_class_score("tourism", "hardware"), (0, "Not Allowed in Tourism Zone"))
        self.assertEqual(zoning_class_score("quarry", "coffee"), (0, "Not Allowed in Quarry Sub-Zone"))

    def test_allowed_zone_classes(self):
        zoning_service.ZONING_ALLOWED_USES = allowed_uses_from_rows([
            {"zone_class": "tourism", "business_type": "coffee"},
            {"zone_class": "general_commercial", "business_type": "coffee"},
            {"zone_class": "industrial_1", "business_type": "hardware"},
        ])
        self.assertEqual(allowed_zone_classes("coffee"), {"tourism", "general_commercial"})
        self.assertEqual(allowed_zone_classes("meat"), set())


class DefaultTableTests(unittest.TestCase):
    def test_defaults_only_use_known_zones_and_businesses(self):
        for zone_class, businesses in DEFAULT_ZONING_ALLOWED_USES.items():
            self.assertIn(zone_class, ZONING_CLASSES)
            for business in businesses:
                self.assertIn(business, SME_DATABASE)

    def test_the_lgu_legend_has_23_zones(self):
        self.assertEqual(len(ZONING_CLASSES), 23)


class LegacyClassTests(unittest.TestCase):
    def test_old_class_names_become_lgu_zones(self):
        for old, new in LEGACY_ZONE_CLASSES.items():
            self.assertIn(new, ZONING_CLASSES)
            self.assertEqual(resolve_zone_class("zoning", {"zone_class": old}), new)

    def test_unknown_class_falls_back_to_default(self):
        self.assertEqual(resolve_zone_class("zoning", {"zone_class": "nope"}, "general_commercial"), "general_commercial")


if __name__ == "__main__":
    unittest.main()

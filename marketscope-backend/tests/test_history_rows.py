"""
Unit tests for normalize_history_row (services/user_service.py): saved history rows
come back from asyncpg with json/jsonb columns as text. No database needed.
"""

import json
import unittest

from services.user_service import normalize_history_row

SAVED_BREAKDOWN = {
    "zoning": {"score": 25, "status": "Allowed in General Commercial Zone"},
    "hazard": {"score": 25, "status": "Low Risk / Safe"},
    "road_access": {"score": 7, "status": "Limited Road Access"},
    "saturation": {"score": 20, "status": "Market Gap Available"},
}
SAVED_COMPETITORS = [{"name": "Kiosk A", "lat": 7.2986, "lon": 125.6804}]


def history_row(**overrides):
    row = {
        "history_id": 1,
        "viability_score": 90,
        "competitors_found": 1,
        "target_lat": 7.2985,
        "target_lng": 125.6803,
        "radius_meters": 340,
        "breakdown": json.dumps(SAVED_BREAKDOWN),
        "competitor_locations": json.dumps(SAVED_COMPETITORS),
    }
    row.update(overrides)
    return row


class NormalizeHistoryRowTests(unittest.TestCase):
    def test_text_json_columns_are_decoded(self):
        row = normalize_history_row(history_row())
        self.assertEqual(row["breakdown"], SAVED_BREAKDOWN)
        self.assertEqual(row["competitor_locations"], SAVED_COMPETITORS)

    def test_already_decoded_columns_are_kept(self):
        row = normalize_history_row(history_row(breakdown=dict(SAVED_BREAKDOWN), competitor_locations=list(SAVED_COMPETITORS)))
        self.assertEqual(row["breakdown"], SAVED_BREAKDOWN)
        self.assertEqual(row["competitor_locations"], SAVED_COMPETITORS)

    def test_missing_breakdown_gets_legacy_estimate(self):
        row = normalize_history_row(history_row(breakdown=None))
        self.assertEqual(row["breakdown"]["zoning"]["status"], "Legacy Estimate")

    def test_unreadable_breakdown_gets_legacy_estimate(self):
        row = normalize_history_row(history_row(breakdown="{not json"))
        self.assertEqual(row["breakdown"]["zoning"]["status"], "Legacy Estimate")

    def test_competitor_count_from_text_locations(self):
        row = normalize_history_row(history_row(competitors_found=None))
        self.assertEqual(row["competitors_found"], 1)


if __name__ == "__main__":
    unittest.main()

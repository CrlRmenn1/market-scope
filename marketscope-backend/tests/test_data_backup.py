"""
Unit tests for the admin data backup file format (services/data_backup.py).
"""

import datetime
import decimal
import unittest

from psycopg2.extras import Json

from services.data_backup import (
    DataBackupError,
    check_columns,
    decode_value,
    encode_value,
    validate_backup,
)


def make_backup(dataset="msmes", tables=None, **overrides):
    backup = {
        "format": "marketscope-backup",
        "version": 1,
        "dataset": dataset,
        "tables": tables if tables is not None else {
            "custom_msme": {"columns": ["id", "name"], "rows": [[1, "Sari-sari"], [2, "Bakery"]]},
        },
    }
    backup.update(overrides)
    return backup


class ValueEncodingTests(unittest.TestCase):
    def test_bytea_round_trips_through_base64(self):
        data = bytes(range(256))
        encoded = encode_value(memoryview(data), "bytea")
        self.assertIsInstance(encoded, str)
        self.assertEqual(decode_value(encoded, "bytea"), data)

    def test_bad_base64_is_rejected(self):
        with self.assertRaises(DataBackupError):
            decode_value("not base64!", "bytea")

    def test_dates_and_times_become_iso_strings(self):
        moment = datetime.datetime(2026, 10, 28, 9, 12, 30, 500)
        self.assertEqual(encode_value(moment, "timestamp without time zone"), "2026-10-28T09:12:30.000500")
        self.assertEqual(encode_value(datetime.date(2001, 2, 3), "date"), "2001-02-03")

    def test_decimal_keeps_its_digits(self):
        self.assertEqual(encode_value(decimal.Decimal("12.50"), "numeric"), "12.50")

    def test_json_columns_are_wrapped_for_psycopg2(self):
        decoded = decode_value(["a.jpg", "b.jpg"], "jsonb")
        self.assertIsInstance(decoded, Json)
        self.assertEqual(decoded.adapted, ["a.jpg", "b.jpg"])

    def test_plain_values_and_nulls_pass_through(self):
        for value, data_type in [(None, "jsonb"), (None, "bytea"), (7, "integer"), (True, "boolean"), ("x", "text")]:
            self.assertEqual(encode_value(value, data_type), value)
            self.assertEqual(decode_value(value, data_type), value)


class ValidateBackupTests(unittest.TestCase):
    def test_valid_backup_returns_its_tables(self):
        tables = validate_backup("msmes", make_backup())
        self.assertEqual(len(tables["custom_msme"]["rows"]), 2)

    def test_empty_table_is_allowed(self):
        validate_backup("msmes", make_backup(tables={"custom_msme": {"columns": ["id"], "rows": []}}))

    def test_rejects_other_files(self):
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", {"hello": "world"})
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", make_backup(format="something-else"))
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", make_backup(version=2))

    def test_rejects_file_from_another_page(self):
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", make_backup(dataset="users"))

    def test_rejects_missing_or_extra_tables(self):
        with self.assertRaises(DataBackupError):
            validate_backup("spaces", make_backup(dataset="spaces", tables={
                "user_space_submissions": {"columns": ["id"], "rows": []},
            }))
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", make_backup(tables={
                "custom_msme": {"columns": ["id"], "rows": []},
                "users": {"columns": ["user_id"], "rows": []},
            }))

    def test_rejects_rows_that_dont_match_columns(self):
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", make_backup(tables={"custom_msme": {"columns": ["id", "name"], "rows": [[1]]}}))

    def test_rejects_duplicate_columns(self):
        with self.assertRaises(DataBackupError):
            validate_backup("msmes", make_backup(tables={"custom_msme": {"columns": ["id", "id"], "rows": []}}))


class CheckColumnsTests(unittest.TestCase):
    LIVE = {"id": "integer", "name": "character varying", "created_at": "timestamp without time zone"}

    def test_subset_of_live_columns_is_fine(self):
        check_columns("custom_msme", ["id", "name"], self.LIVE, "id")

    def test_unknown_column_is_rejected(self):
        with self.assertRaises(DataBackupError):
            check_columns("custom_msme", ["id", "name", "rating"], self.LIVE, "id")

    def test_missing_primary_key_is_rejected(self):
        with self.assertRaises(DataBackupError):
            check_columns("custom_msme", ["name"], self.LIVE, "id")


if __name__ == "__main__":
    unittest.main()

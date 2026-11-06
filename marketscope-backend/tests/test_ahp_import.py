"""
Tests for importing respondents' AHP answers and for the check on saved weights.
No database needed.
"""

import os
import tempfile
import unittest

from services.ahp_import import (
    JudgmentFileError,
    combine_matrices,
    is_placeholder,
    matrices_by_expert,
    parse_judgment_value,
    read_judgments,
    solve_level,
)
from services.ahp_weights import reject_reason


def row(expert, level, first, second, value, category=""):
    return {"expert_id": expert, "level": level, "criterion_i": first, "criterion_j": second, "value": value, "category": category}


def market_answers(expert, competition_road, competition_anchor, competition_building, road_anchor, road_building, anchor_building):
    return [
        row(expert, "saturation", "competition", "road", competition_road),
        row(expert, "saturation", "competition", "anchor", competition_anchor),
        row(expert, "saturation", "competition", "building", competition_building),
        row(expert, "saturation", "road", "anchor", road_anchor),
        row(expert, "saturation", "road", "building", road_building),
        row(expert, "saturation", "anchor", "building", anchor_building),
    ]


class ParseValueTests(unittest.TestCase):
    def test_numbers_and_fractions(self):
        self.assertEqual(parse_judgment_value("3"), 3.0)
        self.assertAlmostEqual(parse_judgment_value("1/3"), 1 / 3)
        self.assertEqual(parse_judgment_value("0.5"), 0.5)

    def test_rejects_values_off_the_scale(self):
        for bad in ("10", "1/10", "0", "-2", "high"):
            with self.assertRaises(JudgmentFileError):
                parse_judgment_value(bad)


class CombineTests(unittest.TestCase):
    def test_hand_worked_two_by_two(self):
        """Answers of 2 and 8 combine to 4 (the geometric mean), giving weights of 0.8 and 0.2."""
        matrices, _ = matrices_by_expert(
            [row("E1", "criteria", "market", "hazard", "2"), row("E2", "criteria", "market", "hazard", "8")],
            "criteria",
        )
        result = solve_level(matrices)
        hazard, market = result["solved"]["priority_vector"]
        self.assertAlmostEqual(market, 0.8)
        self.assertAlmostEqual(hazard, 0.2)

    def test_combined_matrix_stays_reciprocal(self):
        combined = combine_matrices([[[1, 2], [1 / 2, 1]], [[1, 8], [1 / 8, 1]]])
        self.assertAlmostEqual(combined[0][1] * combined[1][0], 1.0)

    def test_answers_can_be_in_either_order(self):
        first, _ = matrices_by_expert([row("E1", "criteria", "hazard", "market", "1/3")], "criteria")
        second, _ = matrices_by_expert([row("E1", "criteria", "market", "hazard", "3")], "criteria")
        self.assertAlmostEqual(first["E1"][0][1], second["E1"][0][1])

    def test_old_questionnaire_wording_is_understood(self):
        matrices, _ = matrices_by_expert([row("E1", "criteria", "hazard", "saturation", "1/3")], "criteria")
        self.assertAlmostEqual(matrices["E1"][1][0], 3.0)

    def test_old_zoning_questions_are_skipped_with_a_note(self):
        matrices, notes = matrices_by_expert(
            [row("E1", "criteria", "zoning", "hazard", "2"), row("E1", "criteria", "hazard", "market", "1/3")],
            "criteria",
        )
        self.assertIn("E1", matrices)
        self.assertTrue(any("zoning" in note for note in notes))


class ScreeningTests(unittest.TestCase):
    CONSISTENT = ("2", "2", "4", "1", "2", "2")
    # Says A beats B, B beats C, and C beats A, all strongly.
    INCONSISTENT = ("9", "1/9", "9", "9", "1/9", "9")

    def test_inconsistent_respondents_are_left_out(self):
        rows = market_answers("E1", *self.CONSISTENT) + market_answers("E2", *self.INCONSISTENT)
        matrices, _ = matrices_by_expert(rows, "saturation")
        result = solve_level(matrices)
        self.assertEqual(result["respondents_kept"], ["E1"])
        self.assertIn("E2", result["respondents_dropped"])
        self.assertGreaterEqual(result["respondents_dropped"]["E2"], 0.10)

    def test_nobody_consistent_is_an_error(self):
        matrices, _ = matrices_by_expert(market_answers("E2", *self.INCONSISTENT), "saturation")
        with self.assertRaises(JudgmentFileError):
            solve_level(matrices)

    def test_incomplete_answers_are_left_out_with_a_note(self):
        rows = market_answers("E1", *self.CONSISTENT) + market_answers("E3", *self.CONSISTENT)[:3]
        matrices, notes = matrices_by_expert(rows, "saturation")
        self.assertNotIn("E3", matrices)
        self.assertTrue(any("E3" in note for note in notes))

    def test_leave_one_out_shows_who_moves_the_result(self):
        similar = market_answers("E1", *self.CONSISTENT) + market_answers("E2", *self.CONSISTENT)
        matrices, _ = matrices_by_expert(similar, "saturation")
        self.assertAlmostEqual(max(solve_level(matrices)["leave_one_out_max_shift"]), 0.0)

        different = market_answers("E1", *self.CONSISTENT) + market_answers("E2", "1/2", "1/2", "1/4", "1", "1/2", "1/2")
        matrices, _ = matrices_by_expert(different, "saturation")
        self.assertGreater(max(solve_level(matrices)["leave_one_out_max_shift"]), 0.0)


class FileTests(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_notes_are_ignored(self):
        path = self.write("# A note\nexpert_id,level,criterion_i,criterion_j,value\nE1,criteria,hazard,market,1/3\n")
        self.assertEqual(len(read_judgments(path)), 1)

    def test_missing_columns_are_an_error(self):
        with self.assertRaises(JudgmentFileError):
            read_judgments(self.write("expert_id,value\nE1,3\n"))

    def test_placeholders_are_recognised(self):
        self.assertTrue(is_placeholder("DUMMY_1"))
        self.assertTrue(is_placeholder("dummy_2"))
        self.assertFalse(is_placeholder("E1"))


class SavedWeightCheckTests(unittest.TestCase):
    GOOD_MARKET = [[1, 2, 2, 3], [1 / 2, 1, 1, 1], [1 / 2, 1, 1, 1], [1 / 3, 1, 1, 1]]

    def test_a_good_matrix_passes(self):
        self.assertIsNone(reject_reason({
            "level": "saturation",
            "criteria_labels": ["competition", "road", "anchor", "building"],
            "pairwise_matrix": self.GOOD_MARKET,
        }))

    def test_an_inconsistent_matrix_is_rejected(self):
        inconsistent = [[1, 9, 1 / 9, 9], [1 / 9, 1, 9, 1 / 9], [9, 1 / 9, 1, 9], [1 / 9, 9, 1 / 9, 1]]
        reason = reject_reason({
            "level": "saturation",
            "criteria_labels": ["competition", "road", "anchor", "building"],
            "pairwise_matrix": inconsistent,
        })
        self.assertIn("inconsistent", reason)

    def test_the_old_criteria_are_rejected(self):
        reason = reject_reason({
            "level": "criteria",
            "criteria_labels": ["zoning", "hazard", "saturation"],
            "pairwise_matrix": [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
        })
        self.assertIn("unexpected criteria", reason)

    def test_a_broken_matrix_is_rejected(self):
        reason = reject_reason({"level": "criteria", "criteria_labels": ["hazard", "market"], "pairwise_matrix": [[1, 0], [0, 1]]})
        self.assertIn("invalid", reason)


if __name__ == "__main__":
    unittest.main()

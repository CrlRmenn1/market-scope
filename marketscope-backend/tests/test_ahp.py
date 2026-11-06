"""
Unit tests for the AHP math core (ahp.py) against known textbook examples.
"""

import math
import unittest

from services.ahp import (
    AHPValidationError,
    CONSISTENCY_RATIO_THRESHOLD,
    build_reciprocal_matrix,
    build_saaty_matrix_from_weights,
    compute_priority_vector,
    nearest_saaty_judgment,
    solve_ahp,
    validate_pairwise_matrix,
)


class ValidatePairwiseMatrixTests(unittest.TestCase):
    def test_accepts_well_formed_matrix(self):
        matrix = [
            [1, 3, 5],
            [1 / 3, 1, 2],
            [1 / 5, 1 / 2, 1],
        ]
        validate_pairwise_matrix(matrix)  # should not raise

    def test_rejects_non_square(self):
        with self.assertRaises(AHPValidationError):
            validate_pairwise_matrix([[1, 2], [0.5, 1, 3]])

    def test_rejects_bad_diagonal(self):
        with self.assertRaises(AHPValidationError):
            validate_pairwise_matrix([[1, 2], [0.5, 2]])

    def test_rejects_non_reciprocal(self):
        with self.assertRaises(AHPValidationError):
            validate_pairwise_matrix([[1, 2], [0.7, 1]])

    def test_rejects_non_positive_entries(self):
        with self.assertRaises(AHPValidationError):
            validate_pairwise_matrix([[1, -2], [-0.5, 1]])

    def test_rejects_unsupported_size(self):
        big = [[1.0 if i == j else 2.0 for j in range(11)] for i in range(11)]
        with self.assertRaises(AHPValidationError):
            validate_pairwise_matrix(big)


class SolveAhpTests(unittest.TestCase):
    def test_identity_like_matrix_is_perfectly_consistent(self):
        # All criteria judged equally important -> uniform weights, CR = 0.
        matrix = [
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1],
        ]
        result = solve_ahp(matrix)
        for weight in result["priority_vector"]:
            self.assertAlmostEqual(weight, 1 / 3, places=6)
        self.assertAlmostEqual(result["cr"], 0.0, places=6)
        self.assertTrue(result["is_consistent"])

    def test_saaty_textbook_example_3x3(self):
        # Classic Saaty 3x3 example (criteria weighting), known to be consistent.
        matrix = [
            [1, 5, 3],
            [1 / 5, 1, 1 / 2],
            [1 / 3, 2, 1],
        ]
        result = solve_ahp(matrix)
        self.assertEqual(result["n"], 3)
        self.assertAlmostEqual(sum(result["priority_vector"]), 1.0, places=6)
        # This matrix is reasonably consistent (small CR), not necessarily exactly 0.
        self.assertLess(result["cr"], CONSISTENCY_RATIO_THRESHOLD)
        self.assertTrue(result["is_consistent"])

    def test_two_by_two_always_consistent(self):
        matrix = [[1, 7], [1 / 7, 1]]
        result = solve_ahp(matrix)
        self.assertEqual(result["cr"], 0.0)
        self.assertTrue(result["is_consistent"])

    def test_inconsistent_matrix_flagged(self):
        # Deliberately contradictory judgments: A>>B, B>>C, but C>>A.
        matrix = [
            [1, 9, 1 / 9],
            [1 / 9, 1, 9],
            [9, 1 / 9, 1],
        ]
        result = solve_ahp(matrix)
        self.assertGreaterEqual(result["cr"], CONSISTENCY_RATIO_THRESHOLD)
        self.assertFalse(result["is_consistent"])

    def test_raises_on_invalid_matrix(self):
        with self.assertRaises(AHPValidationError):
            solve_ahp([[1, 2], [3, 1]])  # not reciprocal


class BuildReciprocalMatrixTests(unittest.TestCase):
    def test_builds_full_matrix_from_upper_triangle(self):
        judgments = {(0, 1): 3.0, (0, 2): 5.0, (1, 2): 2.0}
        matrix = build_reciprocal_matrix(judgments, 3)
        self.assertEqual(matrix[0][0], 1.0)
        self.assertEqual(matrix[1][1], 1.0)
        self.assertEqual(matrix[2][2], 1.0)
        self.assertEqual(matrix[0][1], 3.0)
        self.assertAlmostEqual(matrix[1][0], 1 / 3)
        self.assertEqual(matrix[0][2], 5.0)
        self.assertAlmostEqual(matrix[2][0], 1 / 5)
        self.assertEqual(matrix[1][2], 2.0)
        self.assertAlmostEqual(matrix[2][1], 1 / 2)
        validate_pairwise_matrix(matrix)  # round-trips to a valid matrix

    def test_missing_judgment_raises(self):
        judgments = {(0, 1): 3.0}  # missing (0,2) and (1,2)
        with self.assertRaises(AHPValidationError):
            build_reciprocal_matrix(judgments, 3)


class BuildSaatyMatrixFromWeightsTests(unittest.TestCase):
    def test_judgments_stay_on_the_saaty_scale(self):
        allowed = {float(n) for n in range(1, 10)} | {1.0 / n for n in range(2, 10)}
        matrix = build_saaty_matrix_from_weights([0.47, 0.20, 0.19, 0.14])
        validate_pairwise_matrix(matrix)
        for row in matrix:
            for value in row:
                self.assertTrue(any(math.isclose(value, option) for option in allowed), value)

    def test_rounds_to_the_nearest_judgment(self):
        self.assertEqual(nearest_saaty_judgment(2.47), 2.0)
        self.assertEqual(nearest_saaty_judgment(2.5), 3.0)
        self.assertEqual(nearest_saaty_judgment(40.0), 9.0)
        self.assertAlmostEqual(nearest_saaty_judgment(1 / 3.2), 1 / 3)

    def test_keeps_the_order_of_the_weights(self):
        result = solve_ahp(build_saaty_matrix_from_weights([0.47, 0.20, 0.19, 0.14]))
        vector = result["priority_vector"]
        self.assertGreater(vector[0], vector[1])
        self.assertGreaterEqual(vector[1], vector[3])


class ComputePriorityVectorTests(unittest.TestCase):
    def test_sums_to_one(self):
        matrix = [
            [1, 3, 5],
            [1 / 3, 1, 2],
            [1 / 5, 1 / 2, 1],
        ]
        vector = compute_priority_vector(matrix)
        self.assertTrue(math.isclose(sum(vector), 1.0, abs_tol=1e-9))


if __name__ == "__main__":
    unittest.main()

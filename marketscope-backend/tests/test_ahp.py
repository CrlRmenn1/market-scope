"""
Unit tests for the AHP math core (ahp.py) against known textbook examples.
"""

import math
import unittest

from ahp import (
    AHPValidationError,
    CONSISTENCY_RATIO_THRESHOLD,
    build_consistent_matrix_from_weights,
    build_reciprocal_matrix,
    compute_priority_vector,
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


class BuildConsistentMatrixFromWeightsTests(unittest.TestCase):
    def test_reconstructs_exact_weights(self):
        # This is the seed-migration technique: rebuild a perfectly consistent
        # matrix from today's static weights (e.g. zoning/hazard/saturation).
        weights = [0.30, 0.20, 0.50]
        matrix = build_consistent_matrix_from_weights(weights)
        validate_pairwise_matrix(matrix)
        result = solve_ahp(matrix)
        self.assertAlmostEqual(result["cr"], 0.0, places=6)
        for original, recovered in zip(weights, result["priority_vector"]):
            self.assertAlmostEqual(original, recovered, places=6)

    def test_reconstructs_four_way_category_weights(self):
        # e.g. coffee: competition=0.47, road=0.20, anchor=0.19, building=0.14
        weights = [0.47, 0.20, 0.19, 0.14]
        matrix = build_consistent_matrix_from_weights(weights)
        validate_pairwise_matrix(matrix)
        result = solve_ahp(matrix)
        self.assertAlmostEqual(result["cr"], 0.0, places=6)
        for original, recovered in zip(weights, result["priority_vector"]):
            self.assertAlmostEqual(original, recovered, places=6)


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

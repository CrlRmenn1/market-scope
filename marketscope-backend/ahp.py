"""
Analytic Hierarchy Process (AHP) math core.

Implements the standard Saaty pairwise-comparison workflow:
pairwise comparison matrix -> priority vector (normalized-column-average
eigenvector approximation) -> lambda_max -> Consistency Index (CI) ->
Consistency Ratio (CR), checked against the Random Index (RI) table.

Pure Python, no numpy dependency -- matrices in this application are at
most 4x4, so plain nested lists are sufficient and trivially testable.
"""

SAATY_RI_TABLE = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}

CONSISTENCY_RATIO_THRESHOLD = 0.10


class AHPValidationError(ValueError):
    """Raised when a pairwise comparison matrix fails structural validation."""


def validate_pairwise_matrix(matrix, *, tolerance: float = 1e-6) -> None:
    """Validates that `matrix` is a well-formed Saaty reciprocal matrix.

    Raises AHPValidationError if:
      - matrix is empty or not square
      - n is outside the supported Random Index table range (1..10)
      - any element is not strictly positive
      - any diagonal element is not 1 (within tolerance)
      - matrix[i][j] * matrix[j][i] != 1 (within tolerance) for any i != j
    """
    if not matrix:
        raise AHPValidationError("Matrix must not be empty.")

    n = len(matrix)
    if n not in SAATY_RI_TABLE:
        raise AHPValidationError(
            f"Matrix size {n} is unsupported; must be between 1 and {max(SAATY_RI_TABLE)}."
        )

    for row in matrix:
        if len(row) != n:
            raise AHPValidationError("Matrix must be square.")

    for i in range(n):
        for j in range(n):
            value = matrix[i][j]
            if value is None or value <= 0:
                raise AHPValidationError(
                    f"Matrix entry at ({i},{j}) must be a positive number, got {value!r}."
                )

        if abs(matrix[i][i] - 1.0) > tolerance:
            raise AHPValidationError(
                f"Diagonal entry at ({i},{i}) must be 1, got {matrix[i][i]!r}."
            )

    for i in range(n):
        for j in range(i + 1, n):
            product = matrix[i][j] * matrix[j][i]
            if abs(product - 1.0) > tolerance:
                raise AHPValidationError(
                    f"Matrix entries at ({i},{j})/({j},{i}) are not reciprocal "
                    f"(product={product!r}, expected 1.0)."
                )


def compute_priority_vector(matrix) -> list:
    """Normalized-column-average eigenvector approximation.

    1. Normalize each column by dividing every entry by its column sum.
    2. The priority vector entry for row i is the average of row i across
       the normalized columns.

    Returns weights that sum to 1.0. Does NOT validate the input -- callers
    must call validate_pairwise_matrix first.
    """
    n = len(matrix)
    column_sums = [sum(matrix[i][j] for i in range(n)) for j in range(n)]
    normalized = [
        [matrix[i][j] / column_sums[j] for j in range(n)]
        for i in range(n)
    ]
    return [sum(row) / n for row in normalized]


def compute_lambda_max(matrix, priority_vector) -> float:
    """lambda_max = average_i( (matrix @ priority_vector)[i] / priority_vector[i] )."""
    n = len(matrix)
    weighted_sums = [
        sum(matrix[i][j] * priority_vector[j] for j in range(n))
        for i in range(n)
    ]
    ratios = [weighted_sums[i] / priority_vector[i] for i in range(n)]
    return sum(ratios) / n


def compute_consistency(matrix, priority_vector) -> dict:
    """Returns {"lambda_max", "ci", "ri", "cr", "n"} for the given matrix/priority vector."""
    n = len(matrix)
    lambda_max = compute_lambda_max(matrix, priority_vector)
    ri = SAATY_RI_TABLE[n]

    if n <= 2:
        # A 1x1 or 2x2 reciprocal matrix is always perfectly consistent.
        ci = 0.0
        cr = 0.0
    else:
        ci = (lambda_max - n) / (n - 1)
        cr = ci / ri if ri else 0.0

    return {"lambda_max": lambda_max, "ci": ci, "ri": ri, "cr": cr, "n": n}


def solve_ahp(matrix) -> dict:
    """Top-level convenience function: validate, derive weights, check consistency.

    Returns:
        {
          "priority_vector": [...],  # weights, sum to 1.0, order matches matrix rows
          "lambda_max": float,
          "ci": float,
          "ri": float,
          "cr": float,
          "n": int,
          "is_consistent": bool,     # cr < CONSISTENCY_RATIO_THRESHOLD
        }

    Raises AHPValidationError on malformed input.
    """
    validate_pairwise_matrix(matrix)
    priority_vector = compute_priority_vector(matrix)
    consistency = compute_consistency(matrix, priority_vector)
    return {
        "priority_vector": priority_vector,
        "lambda_max": consistency["lambda_max"],
        "ci": consistency["ci"],
        "ri": consistency["ri"],
        "cr": consistency["cr"],
        "n": consistency["n"],
        "is_consistent": consistency["cr"] < CONSISTENCY_RATIO_THRESHOLD,
    }


def build_reciprocal_matrix(upper_triangle_values: dict, n: int) -> list:
    """Builds a full NxN reciprocal matrix from upper-triangle Saaty judgments.

    `upper_triangle_values` maps (i, j) tuples with i < j to a positive
    Saaty-scale judgment (matrix[i][j]). The diagonal is fixed at 1, and the
    lower triangle is filled with the reciprocal: matrix[j][i] = 1 / matrix[i][j].

    Raises AHPValidationError if a required upper-triangle entry is missing
    or non-positive.
    """
    matrix = [[1.0 for _ in range(n)] for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            key = (i, j)
            if key not in upper_triangle_values:
                raise AHPValidationError(
                    f"Missing pairwise judgment for ({i},{j})."
                )
            value = upper_triangle_values[key]
            if value is None or value <= 0:
                raise AHPValidationError(
                    f"Pairwise judgment for ({i},{j}) must be a positive number, got {value!r}."
                )
            matrix[i][j] = float(value)
            matrix[j][i] = 1.0 / float(value)

    return matrix


def build_consistent_matrix_from_weights(weights: list) -> list:
    """Builds a perfectly consistent (CR=0) reciprocal matrix from target weights.

    matrix[i][j] = weights[i] / weights[j]. This is the standard technique for
    reconstructing a pairwise comparison matrix whose eigenvector exactly
    reproduces a known set of target weights -- used to seed AHP config rows
    from this application's pre-existing static weights so that behavior is
    unchanged until an admin enters real judgments.
    """
    n = len(weights)
    return [
        [weights[i] / weights[j] for j in range(n)]
        for i in range(n)
    ]

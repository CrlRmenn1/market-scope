"""Turns respondents' pairwise answers into AHP weights.

Follows the reference study (Carrido et al., 2026): respondents whose own answers
aren't consistent (CR >= 0.10) are left out, the rest are combined, and a leave-one-out
check shows whether any one person drives the result. Answers are combined with the
geometric mean, the standard way to aggregate individual AHP judgments (Saaty's
reciprocal property is kept).

The CSV has one row per answer, in the format of the expert questionnaire:

    expert_id,level,criterion_i,criterion_j,value
    E1,criteria,hazard,market,1/3
    E1,saturation,competition,road,2

An optional "category" column limits a saturation row to one business type.
"""
import csv
import math
from fractions import Fraction

from constants.engine import AHP_CRITERIA_LABELS, AHP_MARKET_LABELS
from services.ahp import CONSISTENCY_RATIO_THRESHOLD, build_reciprocal_matrix, solve_ahp


LEVEL_LABELS = {"criteria": AHP_CRITERIA_LABELS, "saturation": AHP_MARKET_LABELS}

# The older questionnaire called the market criterion "saturation".
CRITERION_ALIASES = {"saturation": "market"}

MIN_JUDGMENT, MAX_JUDGMENT = 1 / 9, 9


class JudgmentFileError(ValueError):
    """The answers file can't be used, with a message saying why."""


def parse_judgment_value(text):
    """A 1-9 Saaty answer such as 3, 1/3 or 0.5."""
    try:
        value = float(Fraction(str(text).strip()))
    except (ValueError, ZeroDivisionError):
        raise JudgmentFileError(f"{text!r} isn't a number or fraction.")
    if not MIN_JUDGMENT - 1e-9 <= value <= MAX_JUDGMENT + 1e-9:
        raise JudgmentFileError(f"{text!r} is outside the 1/9 to 9 scale.")
    return value


def read_judgments(path):
    """Rows from the CSV. Lines starting with # are notes."""
    with open(path, encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    required = {"expert_id", "level", "criterion_i", "criterion_j", "value"}
    if not required.issubset(reader.fieldnames or []):
        raise JudgmentFileError(f"The file needs these columns: {', '.join(sorted(required))}.")
    return list(reader)


def is_placeholder(expert_id):
    return str(expert_id).strip().upper().startswith("DUMMY")


def matrices_by_expert(rows, level, category=None):
    """{expert: matrix} for one level, and a list of notes about anything left out."""
    labels = LEVEL_LABELS[level]
    index = {label: position for position, label in enumerate(labels)}
    answers = {}
    notes = []

    for row in rows:
        if row["level"].strip() != level:
            continue
        row_category = (row.get("category") or "").strip() or None
        if row_category != category:
            continue
        first = CRITERION_ALIASES.get(row["criterion_i"].strip(), row["criterion_i"].strip())
        second = CRITERION_ALIASES.get(row["criterion_j"].strip(), row["criterion_j"].strip())
        if first not in index or second not in index:
            notes.append(f"Skipped a {level} answer about {first}/{second}: not a criterion here.")
            continue
        value = parse_judgment_value(row["value"])
        i, j = index[first], index[second]
        if i > j:
            i, j, value = j, i, 1.0 / value
        answers.setdefault(row["expert_id"].strip(), {})[(i, j)] = value

    expected = len(labels) * (len(labels) - 1) // 2
    matrices = {}
    for expert, judgments in answers.items():
        if len(judgments) < expected:
            notes.append(f"{expert}: left out of {level}, answered {len(judgments)} of {expected} questions.")
            continue
        matrices[expert] = build_reciprocal_matrix(judgments, len(labels))
    return matrices, notes


def combine_matrices(matrices):
    """The geometric mean of each cell, which keeps the matrix reciprocal."""
    size = len(matrices[0])
    return [
        [math.exp(sum(math.log(matrix[i][j]) for matrix in matrices) / len(matrices)) for j in range(size)]
        for i in range(size)
    ]


def solve_level(matrices):
    """Screens respondents by CR and combines the rest."""
    per_expert = {expert: solve_ahp(matrix) for expert, matrix in matrices.items()}
    kept = {expert: matrices[expert] for expert, solved in per_expert.items() if solved["cr"] < CONSISTENCY_RATIO_THRESHOLD}
    dropped = {expert: per_expert[expert]["cr"] for expert in matrices if expert not in kept}
    if not kept:
        raise JudgmentFileError("No respondent passed the consistency check (CR below 0.10).")

    combined = combine_matrices(list(kept.values()))
    solved = solve_ahp(combined)

    # Leave-one-out: how far each weight moves when one person is removed.
    largest_shift = [0.0] * len(combined)
    if len(kept) > 1:
        for expert in kept:
            others = [matrix for name, matrix in kept.items() if name != expert]
            vector = solve_ahp(combine_matrices(others))["priority_vector"]
            largest_shift = [
                max(shift, abs(value - full))
                for shift, value, full in zip(largest_shift, vector, solved["priority_vector"])
            ]

    return {
        "matrix": combined,
        "solved": solved,
        "respondents_kept": sorted(kept),
        "respondents_dropped": dropped,
        "per_expert_cr": {expert: solution["cr"] for expert, solution in per_expert.items()},
        "leave_one_out_max_shift": largest_shift,
    }

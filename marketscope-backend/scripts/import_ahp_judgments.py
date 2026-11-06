"""Imports respondents' pairwise answers as the AHP weights the engine uses.

    python scripts/import_ahp_judgments.py answers.csv            # shows the result only
    python scripts/import_ahp_judgments.py answers.csv --apply    # saves it

Restart the backend afterwards, then re-run scripts/calibrate_engine.py: new weights
can move the citywide score distribution, and with it the verdict cut-offs.

Rows whose expert_id starts with DUMMY are placeholders, not answers. They are refused
unless --allow-dummy is given, and are then saved with a label that says so.
"""
import argparse
import os
import sys

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)
os.chdir(BACKEND_ROOT)

import psycopg2  # noqa: E402

from constants.engine import AHP_DUMMY_LABEL, AHP_EXPERT_LABEL_PREFIX  # noqa: E402
from constants.msme import MSME_CATEGORY_PROFILES  # noqa: E402
from core.database import DB_CONFIG  # noqa: E402
from db.schema import AHP_GLOBAL_CATEGORY_SENTINEL, write_ahp_weight_config  # noqa: E402
from services.ahp_import import (  # noqa: E402
    LEVEL_LABELS,
    JudgmentFileError,
    is_placeholder,
    matrices_by_expert,
    read_judgments,
    solve_level,
)


def show(title, labels, result):
    solved = result["solved"]
    print(f"\n{title}")
    print(f"  Respondents used: {', '.join(result['respondents_kept'])}")
    for expert, cr in result["respondents_dropped"].items():
        print(f"  Left out {expert}: CR {cr:.3f} is not below 0.10")
    for label, weight, shift in zip(labels, solved["priority_vector"], result["leave_one_out_max_shift"]):
        print(f"  {label:<12} weight {weight:.3f}   largest change if one respondent is removed: {shift:.3f}")
    print(f"  Combined CR: {solved['cr']:.4f}")


def main():
    parser = argparse.ArgumentParser(description="Import AHP pairwise answers.")
    parser.add_argument("csv_path")
    parser.add_argument("--apply", action="store_true", help="save the weights (default is to only show them)")
    parser.add_argument("--allow-dummy", action="store_true", help="accept DUMMY placeholder rows, for testing only")
    args = parser.parse_args()

    try:
        rows = read_judgments(args.csv_path)
        placeholders = sorted({row["expert_id"] for row in rows if is_placeholder(row["expert_id"])})
        if placeholders and not args.allow_dummy:
            raise JudgmentFileError(
                f"These are placeholder respondents, not real answers: {', '.join(placeholders)}. "
                "Use real respondents, or --allow-dummy for a test."
            )

        criteria_matrices, notes = matrices_by_expert(rows, "criteria")
        market_matrices, market_notes = matrices_by_expert(rows, "saturation")
        notes += market_notes
        if not criteria_matrices or not market_matrices:
            raise JudgmentFileError("The file needs complete answers for both the criteria and the saturation level.")

        criteria = solve_level(criteria_matrices)
        market = solve_level(market_matrices)

        category_results = {}
        for category in MSME_CATEGORY_PROFILES:
            matrices, category_notes = matrices_by_expert(rows, "saturation", category=category)
            notes += category_notes
            if matrices:
                category_results[category] = solve_level(matrices)
    except JudgmentFileError as error:
        print(f"Can't use this file: {error}")
        return 1

    for note in notes:
        print(f"Note: {note}")
    show("Criteria (hazard vs market)", LEVEL_LABELS["criteria"], criteria)
    show("Market factors (all business types)", LEVEL_LABELS["saturation"], market)
    for category, result in category_results.items():
        show(f"Market factors ({category})", LEVEL_LABELS["saturation"], result)

    if not args.apply:
        print("\nNothing saved. Add --apply to save these weights.")
        return 0

    label = AHP_DUMMY_LABEL if placeholders else f"{AHP_EXPERT_LABEL_PREFIX}:n={len(market['respondents_kept'])}"
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            write_ahp_weight_config(
                cursor, "criteria", AHP_GLOBAL_CATEGORY_SENTINEL, LEVEL_LABELS["criteria"], criteria["matrix"], label,
            )
            for category in MSME_CATEGORY_PROFILES:
                result = category_results.get(category, market)
                write_ahp_weight_config(cursor, "saturation", category, LEVEL_LABELS["saturation"], result["matrix"], label)
        conn.commit()
    finally:
        conn.close()

    print(f"\nSaved, labelled {label}. Restart the backend, then re-run scripts/calibrate_engine.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

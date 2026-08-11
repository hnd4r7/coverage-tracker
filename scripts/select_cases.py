"""Greedy set-cover: pick the subset of cases (rows) from a coverage report
DataFrame that covers the most (file, line) targets, using as few cases as
possible. Works on the exact shape `report_to_dataframe` produces --
one row per unit, a `lines_by_file` JSON cell holding that unit's full
(order-independent) line coverage.

Greedy max-coverage: each round, pick whichever remaining row adds the most
lines not yet covered by anything already selected. This is the standard
approximation algorithm for maximum coverage -- provably within (1 - 1/e)
~= 63% of the optimal selection in the worst case, and in practice much
closer to it whenever coverage clusters (which real test/call cases do).
"""
import argparse
import json

import pandas as pd


def row_targets(lines_by_file_json: str) -> set:
    """Parse a `lines_by_file` cell into a flat set of (file, line) targets."""
    lines_by_file = json.loads(lines_by_file_json)
    return {(file, line) for file, lines in lines_by_file.items() for line in lines}


def greedy_select(df: pd.DataFrame, budget: int | None = None) -> pd.DataFrame:
    """Return the rows of `df` (in selection order) that greedily maximize
    combined line coverage. `budget` caps the number of rows picked; omit it
    to run until no remaining row would add anything new (minimal set for
    100% of the coverage reachable by any row in `df`).
    """
    remaining = {i: row_targets(df.loc[i, "lines_by_file"]) for i in df.index}
    covered = set()
    order, new_lines_added, cumulative = [], [], []

    limit = budget if budget is not None else len(df)
    for _ in range(limit):
        best_idx, best_new = None, set()
        for i, targets in remaining.items():
            if i in order:
                continue
            new = targets - covered
            if len(new) > len(best_new):
                best_idx, best_new = i, new
        if best_idx is None or not best_new:
            break
        covered |= best_new
        order.append(best_idx)
        new_lines_added.append(len(best_new))
        cumulative.append(len(covered))

    selected = df.loc[order].copy()
    selected["new_lines_added"] = new_lines_added
    selected["cumulative_lines_covered"] = cumulative
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_file", help="xlsx produced by test_run_report.py / live_client_report.py")
    parser.add_argument("--budget", type=int, default=None, help="max cases to select; omit for minimal full-coverage set")
    parser.add_argument("-o", "--output", default="selected_cases.xlsx")
    args = parser.parse_args()

    df = pd.read_excel(args.report_file)
    selected = greedy_select(df, budget=args.budget)

    all_targets = set().union(*(row_targets(v) for v in df["lines_by_file"]))
    covered_targets = set().union(*(row_targets(v) for v in selected["lines_by_file"])) if len(selected) else set()

    print(f"{len(selected)} / {len(df)} cases selected")
    print(f"covers {len(covered_targets)} / {len(all_targets)} lines "
          f"({round(100 * len(covered_targets) / len(all_targets), 2) if all_targets else 0.0}% "
          f"of what the full set covers)")
    for _, row in selected.iterrows():
        print(f"  {row['unit']}  (+{row['new_lines_added']} new, {row['cumulative_lines_covered']} cumulative)")

    selected.to_excel(args.output, index=False)


if __name__ == "__main__":
    main()

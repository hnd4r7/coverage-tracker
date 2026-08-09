"""Cumulative coverage report for a pytest suite.

Runs the suite once with per-test coverage contexts (coverage.py records
which lines each test executed), then computes cumulative coverage as an
in-memory prefix union over test order. O(n) test execution + O(n * lines)
aggregation -- independent of suite size, unlike re-running the suite once
per prefix.
"""
import argparse
import json
import sqlite3
import subprocess
import sys

import coverage.numbits as numbits_mod

DEFAULT_COVERAGE_DB = ".coverage"


def run_suite_with_contexts(test_path: str, source: str) -> None:
    subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q",
            f"--cov={source}", "--cov-context=test", "--cov-report=",
            test_path,
        ],
        check=False,
    )


def collect_contexts(db_path: str):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute("SELECT id, context FROM context")
    contexts = dict(cur.fetchall())  # context_id -> name; "" = import-time/collection

    cur.execute("SELECT context_id, file_id, numbits FROM line_bits")
    hits_by_context = {}
    for context_id, file_id, numbits in cur.fetchall():
        lines = numbits_mod.numbits_to_nums(numbits)
        hits_by_context.setdefault(context_id, set()).update((file_id, ln) for ln in lines)

    con.close()
    return contexts, hits_by_context


def collection_order(test_path: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", test_path],
        capture_output=True, text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if "::" in line]


def total_statements(source: str) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "json", "-o", "-"],
        capture_output=True, text=True,
    )
    return sum(f["summary"]["num_statements"] for f in json.loads(result.stdout)["files"].values())


def build_report(test_path: str, source: str) -> list[dict]:
    run_suite_with_contexts(test_path, source)
    contexts, hits_by_context = collect_contexts(DEFAULT_COVERAGE_DB)

    import_time_lines = set()
    for context_id, name in contexts.items():
        if not name:
            import_time_lines |= hits_by_context.get(context_id, set())

    name_to_context = {name: context_id for context_id, name in contexts.items() if name}
    denominator = total_statements(source)

    report = []
    seen = set(import_time_lines)
    for test_name in collection_order(test_path):
        context_id = next((cid for name, cid in name_to_context.items() if name.startswith(test_name)), None)
        if context_id is not None:
            seen |= hits_by_context.get(context_id, set())
        percent = round(100 * len(seen) / denominator, 2) if denominator else 0.0
        report.append({"test": test_name, "cumulative_percent": percent})

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_path", help="pytest target, e.g. tests/ or tests/test_x.py")
    parser.add_argument("--source", required=True, help="package/module to measure coverage of")
    parser.add_argument("-o", "--output", default="test_coverage_report.json")
    args = parser.parse_args()

    report = build_report(args.test_path, args.source)
    for entry in report:
        print(entry["test"], entry["cumulative_percent"])

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()

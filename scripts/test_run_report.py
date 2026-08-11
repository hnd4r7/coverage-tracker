"""Per-test line coverage report for a pytest suite.

Runs the suite once with per-test coverage contexts (coverage.py records
which lines each test executed), then reports each test's own *full* line
coverage -- not diffed against other tests, not tied to collection order.
That raw per-test data is what a set-cover/greedy algorithm needs to later
work out which subset of tests to keep for maximum coverage; baking in one
particular ordering's marginal contribution up front would throw away
information a different ordering could use.
"""
import argparse
import subprocess
import sys

from coverage_tracker.context_report import (
    build_unit_coverage,
    import_time_lines,
    overall_percent,
    read_context_data,
    report_to_dataframe,
    total_statements,
)

DEFAULT_DATA_FILE = ".coverage"


def run_suite_with_contexts(test_path: str, source: str) -> None:
    subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q",
            f"--cov={source}", "--cov-context=test", "--cov-report=",
            test_path,
        ],
        check=False,
    )


def collection_order(test_path: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", test_path],
        capture_output=True, text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if "::" in line]


def build_report(test_path: str, source: str) -> tuple[list[dict], float]:
    run_suite_with_contexts(test_path, source)

    contexts, files, hits_by_context = read_context_data(DEFAULT_DATA_FILE)
    seed = import_time_lines(contexts, hits_by_context)
    denominator = total_statements(DEFAULT_DATA_FILE, source)

    name_to_context = {name: context_id for context_id, name in contexts.items() if name}
    test_names = collection_order(test_path)
    ordered_ids = [
        name_to_context.get(next((n for n in name_to_context if n.startswith(test_name)), None))
        for test_name in test_names
    ]

    series = build_unit_coverage(ordered_ids, hits_by_context, files)
    report = [{"test": test_name, **stats} for test_name, stats in zip(test_names, series)]
    total_pct = overall_percent(hits_by_context, seed, denominator)
    return report, total_pct


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_path", help="pytest target, e.g. tests/ or tests/test_x.py")
    parser.add_argument("--source", required=True, help="package/module to measure coverage of")
    parser.add_argument("-o", "--output", default="test_coverage_report.xlsx")
    args = parser.parse_args()

    report, total_pct = build_report(args.test_path, args.source)
    for entry in report:
        print(f"{entry['test']}  {entry['lines_covered']} lines")
    print(f"\ntotal coverage across all tests combined: {total_pct}%")

    report_to_dataframe(report, unit_key="test").to_excel(args.output, index=False)


if __name__ == "__main__":
    main()

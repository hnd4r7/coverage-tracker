"""Convert a coverage.py data file directly to an Excel report.

One row per recorded context, each with its own full line coverage. No
dependency on pytest, a live server, or any calls/tests list -- everything
needed is already in the data file.
"""
import argparse

from coverage_tracker.context_report import coverage_db_to_excel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_file", help="coverage.py data file, e.g. .coverage or .coverage.db")
    parser.add_argument("--source", required=True, help="package/module the data was measured against")
    parser.add_argument("-o", "--output", default="coverage_report.xlsx")
    args = parser.parse_args()

    df = coverage_db_to_excel(args.data_file, args.source, args.output)
    print(f"wrote {args.output} ({len(df)} contexts)")


if __name__ == "__main__":
    main()

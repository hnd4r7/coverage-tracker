"""Export line-level coverage detail from a coverage.py data file.

Works against either mode's data (pytest's default `.coverage`, or the live
server's `.coverage.server`, or any other coverage.py data file):

- lcov / xml: for editor integration, e.g. the VS Code "Coverage Gutters"
  extension, which watches a coverage file (lcov.info, coverage.xml, ...)
  and paints covered/missed lines in the gutter directly in the source view.
- html: a standalone browsable report (open htmlcov/index.html) -- includes
  a per-file percent-covered overview table, not just line-level detail.
"""
import argparse

import coverage


def export(data_file: str, source: list[str] | str, lcov_path: str, xml_path: str, html_dir: str) -> None:
    if isinstance(source, str):
        source = [source]
    cov = coverage.Coverage(data_file=data_file, source=source)
    cov.load()
    cov.lcov_report(outfile=lcov_path)
    cov.xml_report(outfile=xml_path)
    cov.html_report(directory=html_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-file", default=".coverage", help="coverage.py data file to read")
    parser.add_argument("--source", required=True, help="package/module the data was measured against")
    parser.add_argument("--lcov-out", default="lcov.info", help="Coverage Gutters auto-watches this name")
    parser.add_argument("--xml-out", default="coverage.xml", help="Cobertura XML; Coverage Gutters auto-watches this name")
    parser.add_argument("--html-out", default="htmlcov")
    args = parser.parse_args()

    export(args.data_file, args.source, args.lcov_out, args.xml_out, args.html_out)
    print(f"wrote {args.lcov_out} (VS Code Coverage Gutters)")
    print(f"wrote {args.xml_out} (VS Code Coverage Gutters, Cobertura format)")
    print(f"wrote {args.html_out}/index.html (per-file % overview + line detail, open in a browser)")


if __name__ == "__main__":
    main()

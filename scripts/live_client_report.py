"""Per-call line coverage report driven by real HTTP calls against a live server.

The target server must be instrumented with `coverage_tracker.middleware.install`,
which tags each request with a coverage context and saves coverage data
(awaited before the response returns) to `data_file`. This tool assigns each
call in the calls file its own unique ID and sends it as the
`X-Coverage-Unit` header, so the server uses that exact ID as the context
name -- no guessing which recorded context belongs to which call from
arrival order, which breaks under concurrency or any traffic this client
didn't originate. After firing all calls, it reads `data_file` once and
reports each call's own *full* line coverage -- not diffed against other
calls, not tied to call order -- which is what a set-cover/greedy algorithm
needs later to work out which subset of calls to keep for maximum coverage.

Calls file format (JSON array), e.g.:
[
  {"method": "GET", "path": "/health"},
  {"method": "POST", "path": "/items", "json": {"name": "Widget", "price": 9.99}},
  {"method": "GET", "path": "/items", "params": {"in_stock": true}}
]
An optional "id" per call gives it a stable, human-readable unit ID; calls
without one get an auto-generated "<method> <path> #<index>".
"""
import argparse
import json
import uuid

import httpx

from coverage_tracker.context_report import (
    build_unit_coverage,
    import_time_lines,
    overall_percent,
    read_context_data,
    report_to_dataframe,
    total_statements,
)

DEFAULT_DATA_FILE = ".coverage.db"
UNIT_ID_HEADER = "X-Coverage-Unit"


def load_calls(calls_file: str) -> list[dict]:
    with open(calls_file) as f:
        return json.load(f)


def assign_unit_ids(calls: list[dict]) -> list[dict]:
    """Give every call a stable, unique unit ID -- its own "id" field if
    present, else an auto label. A random suffix guards against two calls
    sharing the same auto label (which would merge their coverage contexts).
    """
    labeled = []
    for i, call in enumerate(calls):
        unit_id = call.get("id") or f"{call['method']} {call['path']} #{i}-{uuid.uuid4().hex[:8]}"
        labeled.append({**call, "id": unit_id})
    return labeled


def issue_calls(base_url: str, calls: list[dict]) -> list[dict]:
    """Fire each call for real, tagged with its unit ID; return per-call
    {call, unit_id, status}, in order.
    """
    results = []
    with httpx.Client() as client:
        for call in calls:
            method, path, unit_id = call["method"], call["path"], call["id"]
            kwargs = {k: v for k, v in call.items() if k not in ("method", "path", "id")}
            headers = {**kwargs.pop("headers", {}), UNIT_ID_HEADER: unit_id}
            response = client.request(method, base_url + path, headers=headers, **kwargs)
            results.append({"call": f"{method} {path}", "unit_id": unit_id, "status": response.status_code})
    return results


def build_report(base_url: str, calls: list[dict], data_file: str, source: str) -> tuple[list[dict], float]:
    labeled_calls = assign_unit_ids(calls)
    call_results = issue_calls(base_url, labeled_calls)

    contexts, files, hits_by_context = read_context_data(data_file)
    seed = import_time_lines(contexts, hits_by_context)
    denominator = total_statements(data_file, source)

    unit_id_to_context = {name: context_id for context_id, name in contexts.items() if name}
    ordered_ids = [unit_id_to_context.get(c["unit_id"]) for c in call_results]

    series = build_unit_coverage(ordered_ids, hits_by_context, files)
    report = [{**call, **stats} for call, stats in zip(call_results, series)]

    for entry in report:
        print(f"{entry['call']} -> {entry['status']}  {entry['lines_covered']} lines")

    total_pct = overall_percent(hits_by_context, seed, denominator)
    print(f"\ntotal coverage across all calls combined: {total_pct}%")

    return report, total_pct


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calls_file", help="JSON file listing calls to make, in order")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--data-file", default=DEFAULT_DATA_FILE, help="coverage.py data file the server writes to")
    parser.add_argument("--source", required=True, help="package/module the server measures coverage of")
    parser.add_argument("-o", "--output", default="live_coverage_report.xlsx")
    args = parser.parse_args()

    report, _ = build_report(args.base_url, load_calls(args.calls_file), args.data_file, args.source)
    report_to_dataframe(report, unit_key="call").to_excel(args.output, index=False)


if __name__ == "__main__":
    main()

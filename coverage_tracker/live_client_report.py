"""Cumulative coverage report driven by real HTTP calls against a live server.

The target server must be instrumented with `coverage_tracker.middleware.install`
so it exposes GET /_coverage/stats. Each call in the calls file is issued for
real, then the server's own running coverage snapshot is polled -- no
re-execution, no separate test process.

Calls file format (JSON array), e.g.:
[
  {"method": "GET", "path": "/health"},
  {"method": "POST", "path": "/items", "json": {"name": "Widget", "price": 9.99}},
  {"method": "GET", "path": "/items", "params": {"in_stock": true}}
]
"""
import argparse
import json

import httpx


def load_calls(calls_file: str) -> list[dict]:
    with open(calls_file) as f:
        return json.load(f)


def run_calls(base_url: str, calls: list[dict]) -> list[dict]:
    report = []
    with httpx.Client() as client:
        for call in calls:
            method, path = call["method"], call["path"]
            kwargs = {k: v for k, v in call.items() if k not in ("method", "path")}
            response = client.request(method, base_url + path, **kwargs)
            stats = client.get(base_url + "/_coverage/stats").json()
            entry = {"call": f"{method} {path}", "status": response.status_code, **stats}
            report.append(entry)
            print(entry["call"], "->", response.status_code, "| cumulative coverage:", stats["percent_covered"], "%")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calls_file", help="JSON file listing calls to make, in order")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("-o", "--output", default="live_coverage_report.json")
    args = parser.parse_args()

    report = run_calls(args.base_url, load_calls(args.calls_file))
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()

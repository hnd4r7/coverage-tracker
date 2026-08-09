# coverage-tracker

Cumulative code coverage tracking for a FastAPI application, in two modes:

- **Test-run coverage** — coverage accumulated as a pytest suite executes, in
  test order.
- **Live-server coverage** — coverage accumulated as real HTTP requests hit a
  running server, in request order.

Both modes report cumulative percent covered after each unit (test / request)
without re-running prior work, so cost stays proportional to suite/traffic
size rather than growing quadratically.

## Layout

- `coverage_tracker/` — the generic, app-agnostic library.
  - `middleware.py` — `install(app, source=...)` starts in-process
    `coverage.py` measurement on any ASGI app, tags each request with its own
    coverage context, and mounts `GET /_coverage/stats`.
  - `test_run_report.py` — runs a pytest suite once with per-test coverage
    contexts, then computes a cumulative-coverage-by-test report from the
    recorded contexts (no re-running the suite per prefix). Takes `test_path`
    and `--source` — not tied to any specific app.
  - `live_client_report.py` — drives a live server with real HTTP calls read
    from a JSON calls file, polling `/_coverage/stats` after each one.
- `sample_api/` — a demo FastAPI app used to exercise the tools above.
  - `main.py` — item CRUD API; calls `coverage_tracker.middleware.install`
    when `COVERAGE_LIVE=1`.
  - `example_calls.json` — this app's own example call sequence, consumed by
    `live_client_report.py`.
- `tests/` — pytest suite for `sample_api`, consumed by `test_run_report.py`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Test-run coverage

```bash
.venv/bin/python -m coverage_tracker.test_run_report tests/ --source sample_api
```

Writes `test_coverage_report.json`: cumulative `%` covered after each test,
in collection order. `test_path` and `--source` point at any pytest target
and package — nothing here is specific to `sample_api`.

## Live-server coverage

```bash
COVERAGE_LIVE=1 .venv/bin/uvicorn sample_api.main:app --port 8000 &
.venv/bin/python -m coverage_tracker.live_client_report sample_api/example_calls.json
```

Writes `live_coverage_report.json`: cumulative `%` covered after each real
HTTP call. The calls file is plain JSON (`method`, `path`, plus any `httpx`
request kwargs like `json`/`params`) — write your own for any other app.

## How the cumulative report stays cheap

`coverage.py` supports per-context line recording (`--cov-context=test` for
pytest, `Coverage.switch_context()` for the live server). Both tools run the
target **once**, tag every executed line with the test or request that hit
it, then compute the cumulative series as an in-memory running union over
that per-unit data — O(n · lines) instead of O(n²) from re-executing a
growing prefix of the suite for every data point.

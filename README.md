# coverage-tracker

Per-case code coverage tracking for a FastAPI application, in two modes:

- **Test-run coverage** — which lines each pytest test covers.
- **Live-server coverage** — which lines each real HTTP request covers,
  against a running server.

Both modes report each case's own *full* line coverage (not a diff against
other cases, not tied to run order), which a downstream sampling algorithm
can use to select a minimal high-coverage subset of cases.

## Layout

```
coverage_tracker/     generic, app-agnostic library
  middleware.py         in-process coverage instrumentation for any ASGI app
  context_report.py     shared analysis: read coverage.py's per-context data,
                         group by unit, flatten to a DataFrame

scripts/              CLI entrypoints, installed as console scripts
  test_run_report.py    per-test coverage report for a pytest suite
  live_client_report.py per-call coverage report against a live server
  export_report.py      export lcov / Cobertura XML / HTML from a data file
  select_cases.py       greedy max-coverage case selection over a report

sample_api/           demo FastAPI app the tools above are exercised against
  main.py                item CRUD API
  example_calls.json     example call sequence for live_client_report

tests/                pytest suite for sample_api
```

### `coverage_tracker/middleware.py`

`install(app, source=...)` starts in-process `coverage.py` measurement on
any ASGI app. Each request is tagged with its own coverage context (see
"Unit identity" below) and a coverage snapshot is appended to `stats_file`
(JSON Lines) after every request completes, awaited before the response
returns — no admin endpoint to poll, no separate report step needed to see
current totals.

### `coverage_tracker/context_report.py`

Shared analysis used by both CLI report tools:

- `read_context_data` — reads coverage.py's SQLite data file directly
  (`context`, `file`, `line_bits` tables) and decodes the `numbits` bitmap
  encoding into plain `(file, line)` pairs.
- `build_unit_coverage` — each unit's (test's / call's) own full line
  coverage, independent of order.
- `overall_percent` — total % covered across every recorded unit combined.
- `report_to_dataframe` — one row per unit; the file→lines detail is packed
  into a single compact-JSON cell rather than exploded into multiple rows.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This registers four console scripts in `.venv/bin/`:
`coverage-tracker-test-report`, `coverage-tracker-live-report`,
`coverage-tracker-export`, `coverage-tracker-select`.

## Using this against a FastAPI project

The steps below work identically for the bundled `sample_api` demo (just
substitute `sample_api` for `myapp`) or any other FastAPI project.

### 1. Install coverage-tracker as a dependency

```bash
cd /path/to/myapp
python3 -m venv .venv   # if you don't already have one
.venv/bin/pip install -e /path/to/coverage-tracker
.venv/bin/pip install pytest pytest-cov httpx   # if you'll use test-run mode too
```

This installs the `coverage_tracker` library and the four console commands
into `myapp/.venv/bin/`.

### 2a. Test-run coverage (if you have a pytest suite)

Nothing to wire into the app — just point the tool at your tests and
package:

```bash
.venv/bin/coverage-tracker-test-report tests/ --source myapp
```

Writes `test_coverage_report.xlsx`, one row per test with its full line
coverage.

### 2b. Live-server coverage (real HTTP traffic)

**Wire the middleware in** — one line, guarded so it's opt-in:

```python
# myapp/main.py
import os
from fastapi import FastAPI

app = FastAPI()

if os.environ.get("COVERAGE_LIVE"):
    from coverage_tracker.middleware import install as install_coverage
    install_coverage(app, source="myapp")
```

`source="myapp"` should match your actual top-level importable package
name.

**Write a calls file** — plain JSON, one object per call:

```json
[
  {"method": "GET", "path": "/health"},
  {"method": "POST", "path": "/users", "json": {"name": "Alice"}},
  {"method": "GET", "path": "/users/1"}
]
```

Optional per-call fields: `"id"` (a stable label — otherwise
auto-generated), plus any `httpx` request kwarg (`params`, `headers`, etc.).

**Run the server with measurement on, then drive it:**

```bash
COVERAGE_LIVE=1 .venv/bin/uvicorn myapp.main:app --port 8000 &
.venv/bin/coverage-tracker-live-report myapp/example_calls.json --base-url http://127.0.0.1:8000 --source myapp
```

Writes `live_coverage_report.xlsx` in the same per-call shape. Run uvicorn
as a single process — no `--workers > 1`, no `--reload` (see Limits below).

**Unit identity**: each call is assigned a unique ID (`call["id"]` if
provided, else an auto-generated label) and sent as the `X-Coverage-Unit`
header. The middleware uses that exact value as the coverage context name,
so the report tool matches results back by exact ID rather than guessing
from arrival order — correct even if other traffic hits the server, though
not under genuine concurrency (see Limits below).

### 3. Select a minimal high-coverage subset (optional)

```bash
.venv/bin/coverage-tracker-select test_coverage_report.xlsx
.venv/bin/coverage-tracker-select live_coverage_report.xlsx --budget 10
```

Greedy maximum-coverage selection: each round picks whichever remaining
case adds the most lines not already covered by the selection so far, until
either no case would add anything new (default — the minimal set for 100%
of the coverage reachable by any case in the report) or `--budget` caps the
count. This is the standard approximation algorithm for max coverage,
provably within `(1 - 1/e) ≈ 63%` of optimal in the worst case.

### 4. Editor/browser visualization (optional)

From either data file (`.coverage` after test-run, or whatever
`--data-file` the middleware wrote for live-server — default
`.coverage.db`):

```bash
.venv/bin/coverage-tracker-export --source myapp --data-file .coverage --lcov-out lcov.info --xml-out coverage.xml --html-out htmlcov
```

- `lcov.info` / `coverage.xml` → VS Code's Coverage Gutters extension
  (`Coverage Gutters: Watch`) for inline gutter highlighting.
- `htmlcov/index.html` → standalone browsable per-file coverage report.

## Why this stays cheap at scale

`coverage.py` supports per-context line recording (`--cov-context=test` for
pytest, `Coverage.switch_context()` for the live server). Both report tools
run the target **once**, tag every executed line with the unit that hit it,
then compute per-unit coverage as a lookup over that already-recorded
data — no re-running the suite (or re-issuing calls) per data point.

## Limits of the live-server mode

- **Single process only.** Each worker/reload-subprocess has its own
  `Coverage()` instance; running with `--workers > 1` or `--reload` means
  requests can land on a process the client never reads coverage data from.
  Measure with a single process.
- **Concurrent requests can cross-contaminate.** The current coverage
  context is a single value on the thread's tracer; interleaved `async def`
  handlers on the same event-loop thread can attribute a line to the wrong
  request. Sequential calls (as `live_client_report.py` makes) don't hit
  this — it's a real limit only under genuine concurrent load.

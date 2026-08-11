"""In-process coverage instrumentation for any ASGI app.

Call `install(app, source=...)` at app startup to start `coverage.py`
measurement, tag every incoming request with its own coverage context, and
write a fresh stats snapshot to `stats_file` after every request completes --
no admin endpoint to poll, no server restart, no stopping measurement.

Request identity: the caller should send a `unit_id_header` header (default
`X-Coverage-Unit`) with a value it chooses -- a test name, a call label,
anything unique to that logical unit of work. That value becomes the
coverage context name directly, so a reporting tool can look up "the lines
this specific unit covered" by exact ID instead of guessing from arrival
order. Without the header, falls back to an auto-incrementing counter, which
only works correctly for a single sequential client with no concurrency and
no other traffic hitting the server.
"""
import asyncio
import itertools
import json

import coverage


def install(
    app,
    source: list[str] | str,
    data_file: str = ".coverage.db",
    stats_file: str = "coverage_stats.jsonl",
    unit_id_header: str = "X-Coverage-Unit",
):
    """Wire coverage measurement into `app`. Returns the `coverage.Coverage` instance."""
    if isinstance(source, str):
        source = [source]

    cov = coverage.Coverage(source=source, data_file=data_file)
    cov.start()

    fallback_counter = itertools.count(1)

    async def coverage_context_middleware(request, call_next):
        unit_id = request.headers.get(unit_id_header)
        if not unit_id:
            unit_id = f"{request.method} {request.url.path} #{next(fallback_counter)}"
        cov.switch_context(unit_id)
        response = await call_next(request)

        await asyncio.to_thread(append_stats, cov, stats_file)
        return response

    app.middleware("http")(coverage_context_middleware)

    return cov


def snapshot_stats(cov: coverage.Coverage) -> dict:
    """Save in-memory coverage to disk and compute totals across measured files."""
    cov.save()
    data = cov.get_data()

    total_statements = 0
    total_covered = 0
    for filename in data.measured_files():
        _, statements, _, missing, _ = cov.analysis2(filename)
        total_statements += len(statements)
        total_covered += len(statements) - len(missing)

    requests_seen = len([c for c in data.measured_contexts() if c])
    percent = round(100 * total_covered / total_statements, 2) if total_statements else 0.0

    return {
        "percent_covered": percent,
        "statements_covered": total_covered,
        "statements_total": total_statements,
        "requests_seen": requests_seen,
    }


def append_stats(cov: coverage.Coverage, stats_file: str) -> dict:
    """Compute the current snapshot and append it to `stats_file` as one JSON
    Lines record (compact, single line, newline-terminated) -- so the file
    accumulates a readable history instead of being overwritten each time.

    Runs synchronously (SQLite I/O via cov.save()/analysis2() plus a file
    write) -- call via asyncio.to_thread from async code so it doesn't block
    the event loop.
    """
    stats = snapshot_stats(cov)
    with open(stats_file, "a") as f:
        f.write(json.dumps(stats) + "\n")
    return stats

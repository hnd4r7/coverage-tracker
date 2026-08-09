"""In-process coverage instrumentation for any ASGI app.

Call `install(app, source=...)` at app startup to start `coverage.py`
measurement, tag every incoming request with its own coverage context, and
mount a `GET /_coverage/stats` route that snapshots current totals on
demand -- no server restart, no stopping measurement.
"""
import itertools

import coverage


def install(app, source: list[str] | str, data_file: str = ".coverage.server", path: str = "/_coverage/stats"):
    """Wire coverage measurement into `app`. Returns the `coverage.Coverage` instance."""
    if isinstance(source, str):
        source = [source]

    cov = coverage.Coverage(source=source, data_file=data_file)
    cov.start()

    call_counter = itertools.count(1)

    async def coverage_context_middleware(request, call_next):
        call_id = next(call_counter)
        cov.switch_context(f"{request.method} {request.url.path} #{call_id}")
        return await call_next(request)

    app.middleware("http")(coverage_context_middleware)

    @app.get(path)
    def coverage_stats():
        return snapshot_stats(cov)

    return cov


def snapshot_stats(cov: coverage.Coverage) -> dict:
    """Save in-memory coverage to disk and report totals across measured files."""
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

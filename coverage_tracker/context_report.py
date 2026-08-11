"""Shared helpers for turning coverage.py per-context data into
marginal-contribution reports -- used by both the pytest-based and
live-server-based reporting tools so the analysis logic lives in one place.
"""
import json
import sqlite3

import coverage
import coverage.numbits as numbits_mod
import pandas as pd


def read_context_data(data_file: str):
    """Return (contexts: {id: name}, files: {id: path}, hits_by_context: {id: {(file_id, lineno)}})."""
    con = sqlite3.connect(data_file)
    cur = con.cursor()

    cur.execute("SELECT id, context FROM context")
    contexts = dict(cur.fetchall())  # "" = import-time / pre-context code

    cur.execute("SELECT id, path FROM file")
    files = dict(cur.fetchall())

    cur.execute("SELECT context_id, file_id, numbits FROM line_bits")
    hits_by_context = {}
    for context_id, file_id, numbits in cur.fetchall():
        lines = numbits_mod.numbits_to_nums(numbits)
        hits_by_context.setdefault(context_id, set()).update((file_id, ln) for ln in lines)

    con.close()
    return contexts, files, hits_by_context


def import_time_lines(contexts: dict, hits_by_context: dict) -> set:
    """Lines hit under the empty '' context -- executed before any unit-specific context was set."""
    lines = set()
    for context_id, name in contexts.items():
        if not name:
            lines |= hits_by_context.get(context_id, set())
    return lines


def group_by_file(hits: set, files: dict) -> dict:
    by_file = {}
    for file_id, lineno in hits:
        by_file.setdefault(files[file_id], []).append(lineno)
    return {path: sorted(lines) for path, lines in sorted(by_file.items())}


def total_statements(data_file: str, source: list[str] | str) -> int:
    if isinstance(source, str):
        source = [source]
    cov = coverage.Coverage(data_file=data_file, source=source)
    cov.load()
    total = 0
    for filename in cov.get_data().measured_files():
        _, statements, _, _, _ = cov.analysis2(filename)
        total += len(statements)
    return total


def build_unit_coverage(ordered_context_ids: list, hits_by_context: dict, files: dict) -> list[dict]:
    """Given context ids in unit order, return each unit's own *full* line
    coverage -- not diffed against what earlier units already covered. This
    is order-independent and strictly more information than a marginal
    (new-lines-only) series: which case to add for maximum coverage gain is
    a set-cover problem best solved afterward, over this raw per-unit data,
    rather than baked in up front by a single fixed ordering.
    """
    series = []
    for context_id in ordered_context_ids:
        hits = hits_by_context.get(context_id, set()) if context_id is not None else set()
        series.append({
            "lines_covered": len(hits),
            "lines_by_file": group_by_file(hits, files),
        })
    return series


def overall_percent(hits_by_context: dict, seed_lines: set, denominator: int) -> float:
    """Total % covered across ALL recorded contexts combined (order-independent)."""
    seen = set(seed_lines)
    for hits in hits_by_context.values():
        seen |= hits
    return round(100 * len(seen) / denominator, 2) if denominator else 0.0


def report_to_dataframe(report: list[dict], unit_key: str) -> pd.DataFrame:
    """One row per unit (test / call). The file->lines detail stays a single
    cell -- a compact JSON string like {"main.py": [12, 13, 40]} -- rather
    than exploding into one row per line.
    """
    rows = []
    for entry in report:
        row = {k: v for k, v in entry.items() if k != "lines_by_file"}
        row = {"unit": row.pop(unit_key), **row}
        row["lines_by_file"] = json.dumps(entry["lines_by_file"])
        rows.append(row)
    return pd.DataFrame(rows)

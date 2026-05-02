"""SQLite persistence layer.

Why SQLite: single-file, zero-ops, perfectly fits the "<2 minute CI run" budget.
Schema is intentionally narrow — runs and per-case results, that's it. Anything
fancier belongs in a downstream warehouse, not in the regression harness.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    CaseResult,
    CaseScores,
    DriftPoint,
    Run,
    RunMetadata,
    RunSummary,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    prompt_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    judge_model TEXT NOT NULL,
    git_sha TEXT,
    git_branch TEXT,
    pr_number INTEGER,
    notes TEXT,
    summary_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS runs_prompt_idx ON runs (prompt_name, created_at DESC);

CREATE TABLE IF NOT EXISTS case_results (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    output TEXT NOT NULL,
    exact_match REAL NOT NULL,
    judge_score REAL NOT NULL,
    composite REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    error TEXT,
    PRIMARY KEY (run_id, case_id),
    FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
);
"""


class RunStore:
    """Tiny DAO around SQLite. Every public method is a single transaction."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn: sqlite3.Connection = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    def save_run(self, run: Run) -> None:
        """Persist a Run atomically (run row + all case rows in one transaction)."""
        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs
                    (run_id, created_at, prompt_name, prompt_version, model, judge_model,
                     git_sha, git_branch, pr_number, notes, summary_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.metadata.run_id,
                        run.metadata.created_at.isoformat(),
                        run.metadata.prompt_name,
                        run.metadata.prompt_version,
                        run.metadata.model,
                        run.metadata.judge_model,
                        run.metadata.git_sha,
                        run.metadata.git_branch,
                        run.metadata.pr_number,
                        run.metadata.notes,
                        run.summary.model_dump_json(),
                    ),
                )
                conn.execute(
                    "DELETE FROM case_results WHERE run_id = ?", (run.metadata.run_id,)
                )
                conn.executemany(
                    """
                    INSERT INTO case_results
                    (run_id, case_id, output, exact_match, judge_score, composite,
                     latency_ms, cost_usd, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run.metadata.run_id,
                            c.case_id,
                            c.output,
                            c.scores.exact_match,
                            c.scores.judge_score,
                            c.scores.composite,
                            c.latency_ms,
                            c.cost_usd,
                            c.error,
                        )
                        for c in run.cases
                    ],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_run(self, run_id: str) -> Run | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            cases = [
                _row_to_case(c)
                for c in conn.execute(
                    "SELECT * FROM case_results WHERE run_id = ? ORDER BY case_id",
                    (run_id,),
                ).fetchall()
            ]
        return _row_to_run(row, cases)

    def latest_run(self, prompt_name: str, before_run_id: str | None = None) -> Run | None:
        """Return the most recent run for `prompt_name`. If `before_run_id` is given,
        only consider runs strictly older. Useful to fetch the baseline for a new candidate.
        """
        sql = "SELECT run_id FROM runs WHERE prompt_name = ?"
        params: list[Any] = [prompt_name]
        if before_run_id is not None:
            sql += (
                " AND created_at < (SELECT created_at FROM runs WHERE run_id = ?)"
            )
            params.append(before_run_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if row is None:
            return None
        return self.get_run(row[0])

    def drift_window(self, prompt_name: str, n: int) -> list[DriftPoint]:
        """Return the last `n` runs (oldest first) as DriftPoints."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, created_at, summary_json FROM runs
                WHERE prompt_name = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (prompt_name, n),
            ).fetchall()
        points: list[DriftPoint] = []
        for run_id, created_at, summary_json in reversed(rows):
            summary = RunSummary.model_validate_json(summary_json)
            points.append(
                DriftPoint(
                    run_id=run_id,
                    created_at=datetime.fromisoformat(created_at),
                    avg_composite=summary.avg_composite,
                )
            )
        return points


def _row_to_case(row: tuple[Any, ...]) -> CaseResult:
    _, case_id, output, exact_match, judge_score, composite, latency_ms, cost_usd, error = row
    return CaseResult(
        case_id=case_id,
        output=output,
        scores=CaseScores(
            exact_match=exact_match, judge_score=judge_score, composite=composite
        ),
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        error=error,
    )


def _row_to_run(row: tuple[Any, ...], cases: list[CaseResult]) -> Run:
    (
        run_id,
        created_at,
        prompt_name,
        prompt_version,
        model,
        judge_model,
        git_sha,
        git_branch,
        pr_number,
        notes,
        summary_json,
    ) = row
    summary_data: dict[str, Any] = json.loads(summary_json)
    metadata = RunMetadata(
        run_id=run_id,
        created_at=datetime.fromisoformat(created_at),
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        model=model,
        judge_model=judge_model,
        git_sha=git_sha,
        git_branch=git_branch,
        pr_number=pr_number,
        notes=notes,
    )
    return Run(metadata=metadata, summary=RunSummary(**summary_data), cases=cases)

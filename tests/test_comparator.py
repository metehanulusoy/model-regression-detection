from __future__ import annotations

from datetime import UTC, datetime

import pytest

from model_regression.models import (
    CaseResult,
    CaseScores,
    Run,
    RunMetadata,
    RunSummary,
    Severity,
    Verdict,
)
from model_regression.reporting.comparator import compare_runs

from .conftest import make_run


def _build_run(run_id: str, scores: dict[str, float]) -> Run:
    cases = [
        CaseResult(
            case_id=cid,
            output=f"out-{cid}",
            scores=CaseScores(exact_match=s, judge_score=s, composite=s),
            latency_ms=100,
            cost_usd=0.0,
        )
        for cid, s in scores.items()
    ]
    avg = sum(scores.values()) / max(len(scores), 1)
    return Run(
        metadata=RunMetadata(
            run_id=run_id,
            created_at=datetime.now(UTC),
            prompt_name="p",
            prompt_version="v1",
            model="gpt-4o-mini",
            judge_model="gpt-4o",
        ),
        summary=RunSummary(
            n_cases=len(scores),
            n_errors=0,
            avg_composite=avg,
            avg_exact_match=avg,
            avg_judge_score=avg,
            p50_latency_ms=100,
            p95_latency_ms=100,
            total_cost_usd=0.0,
        ),
        cases=cases,
    )


def test_compare_detects_regressions_and_improvements() -> None:
    baseline = _build_run("b", {"a": 1.0, "b": 1.0, "c": 1.0})
    candidate = _build_run("c", {"a": 1.0, "b": 0.5, "c": 1.0})  # b regresses
    report = compare_runs(baseline=baseline, candidate=candidate)
    verdicts = {d.case_id: d.verdict for d in report.diffs}
    assert verdicts["b"] is Verdict.REGRESSION
    assert verdicts["a"] is Verdict.UNCHANGED
    assert report.n_regressions == 1
    assert report.n_unchanged == 2


def test_compare_severity_critical_when_aggregate_drop_large() -> None:
    baseline = make_run(run_id="b", avg=0.95)
    candidate = make_run(run_id="c", avg=0.80)  # 15pp drop
    report = compare_runs(
        baseline=baseline, candidate=candidate, warning_pct=3, critical_pct=8
    )
    assert report.severity is Severity.CRITICAL


def test_compare_severity_warning_when_drop_above_warning_below_critical() -> None:
    baseline = make_run(run_id="b", avg=0.90)
    candidate = make_run(run_id="c", avg=0.86)  # 4pp drop
    report = compare_runs(
        baseline=baseline, candidate=candidate, warning_pct=3, critical_pct=8
    )
    assert report.severity is Severity.WARNING


def test_compare_handles_new_and_removed_cases() -> None:
    baseline = _build_run("b", {"a": 1.0, "b": 1.0})
    candidate = _build_run("c", {"a": 1.0, "z": 1.0})
    report = compare_runs(baseline=baseline, candidate=candidate)
    verdicts = {d.case_id: d.verdict for d in report.diffs}
    assert verdicts["z"] is Verdict.NEW
    assert verdicts["b"] is Verdict.REMOVED


def test_compare_avg_delta_uses_pp_units() -> None:
    baseline = make_run(run_id="b", avg=0.85)
    candidate = make_run(run_id="c", avg=0.80)
    report = compare_runs(baseline=baseline, candidate=candidate)
    assert report.avg_composite_delta_pct == pytest.approx(-5.0, abs=1e-6)

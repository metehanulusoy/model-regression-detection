from __future__ import annotations

import pytest
from pydantic import ValidationError

from model_regression.models import CaseScores, RunSummary, Severity, Verdict


def test_case_scores_blend_default_weight() -> None:
    s = CaseScores.from_parts(exact_match=0.0, judge_score=1.0)
    assert s.composite == pytest.approx(0.7)


def test_case_scores_blend_custom_weight() -> None:
    s = CaseScores.from_parts(exact_match=0.0, judge_score=1.0, judge_weight=0.5)
    assert s.composite == pytest.approx(0.5)


def test_case_scores_rejects_out_of_range_weight() -> None:
    with pytest.raises(ValueError):
        CaseScores.from_parts(exact_match=0.0, judge_score=1.0, judge_weight=1.5)


def test_case_scores_rejects_out_of_range_score() -> None:
    with pytest.raises(ValidationError):
        CaseScores(exact_match=1.5, judge_score=0.5, composite=0.5)


def test_run_summary_rejects_more_errors_than_cases() -> None:
    with pytest.raises(ValidationError):
        RunSummary(
            n_cases=2,
            n_errors=3,
            avg_composite=1.0,
            avg_exact_match=1.0,
            avg_judge_score=1.0,
            p50_latency_ms=10,
            p95_latency_ms=10,
            total_cost_usd=0.0,
        )


def test_severity_and_verdict_are_strenum() -> None:
    assert Severity.OK.value == "ok"
    assert Verdict.REGRESSION.value == "regression"

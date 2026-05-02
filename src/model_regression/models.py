"""Pydantic v2 domain models. Single source of truth for the on-disk and on-wire schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Verdict(StrEnum):
    """Outcome category for a comparison between two runs of the same case."""

    PASS = "pass"
    REGRESSION = "regression"
    IMPROVEMENT = "improvement"
    UNCHANGED = "unchanged"
    NEW = "new"
    REMOVED = "removed"


class Severity(StrEnum):
    """Reporting severity bucket. Drives Slack color and CI merge-blocking."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


class TestCase(BaseModel):
    """Single golden-dataset entry. Stable `id` allows tracking across runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected: str | None = None
    expected_label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseScores(BaseModel):
    """Per-dimension scores for a single case execution. All values in [0, 1]."""

    model_config = ConfigDict(extra="forbid")

    exact_match: float = Field(ge=0.0, le=1.0)
    judge_score: float = Field(ge=0.0, le=1.0)
    composite: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_parts(cls, exact_match: float, judge_score: float, judge_weight: float = 0.7) -> Self:
        """Compose a `composite` from exact match and LLM-judge score.

        Why blend: exact_match catches deterministic format breaks; the judge handles
        paraphrase-equivalent answers. A weighted mean is robust enough; we expose the
        weight so teams can tune toward stricter or looser scoring.
        """
        if not 0.0 <= judge_weight <= 1.0:
            raise ValueError("judge_weight must be in [0, 1]")
        composite = judge_weight * judge_score + (1.0 - judge_weight) * exact_match
        return cls(exact_match=exact_match, judge_score=judge_score, composite=composite)


class CaseResult(BaseModel):
    """Outcome of evaluating one TestCase under one prompt+model combination."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    output: str
    scores: CaseScores
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    error: str | None = None


class RunMetadata(BaseModel):
    """Identity card for a single eval run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prompt_name: str
    prompt_version: str
    model: str
    judge_model: str
    git_sha: str | None = None
    git_branch: str | None = None
    pr_number: int | None = None
    notes: str | None = None


class RunSummary(BaseModel):
    """Aggregate stats across all cases in a run."""

    model_config = ConfigDict(extra="forbid")

    n_cases: int = Field(ge=0)
    n_errors: int = Field(ge=0)
    avg_composite: float = Field(ge=0.0, le=1.0)
    avg_exact_match: float = Field(ge=0.0, le=1.0)
    avg_judge_score: float = Field(ge=0.0, le=1.0)
    p50_latency_ms: int = Field(ge=0)
    p95_latency_ms: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _check_errors_le_cases(self) -> RunSummary:
        if self.n_errors > self.n_cases:
            raise ValueError("n_errors cannot exceed n_cases")
        return self


class Run(BaseModel):
    """A complete eval run: metadata + per-case results + aggregates."""

    model_config = ConfigDict(extra="forbid")

    metadata: RunMetadata
    summary: RunSummary
    cases: list[CaseResult]


class CaseDiff(BaseModel):
    """Per-case comparison between a baseline and candidate run."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    verdict: Verdict
    baseline: CaseResult | None = None
    candidate: CaseResult | None = None
    composite_delta: float = 0.0


class ComparisonReport(BaseModel):
    """Full comparison between two runs. Drives the HTML report and Slack alert."""

    model_config = ConfigDict(extra="forbid")

    baseline: RunMetadata
    candidate: RunMetadata
    severity: Severity
    avg_composite_delta_pct: float
    n_regressions: int = Field(ge=0)
    n_improvements: int = Field(ge=0)
    n_unchanged: int = Field(ge=0)
    diffs: list[CaseDiff]


class DriftPoint(BaseModel):
    """One bucket inside the rolling drift window."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: datetime
    avg_composite: float


class DriftReport(BaseModel):
    """Rolling-average drift over the last N runs (window from settings)."""

    model_config = ConfigDict(extra="forbid")

    window: int = Field(ge=2)
    points: list[DriftPoint]
    rolling_avg: float
    latest_avg: float
    drift_pct: float
    severity: Severity

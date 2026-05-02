"""Compare two runs of the same prompt and produce a structured ComparisonReport."""

from __future__ import annotations

from ..models import (
    CaseDiff,
    ComparisonReport,
    Run,
    Severity,
    Verdict,
)


def compare_runs(
    *,
    baseline: Run,
    candidate: Run,
    warning_pct: float = 3.0,
    critical_pct: float = 8.0,
    per_case_regression_threshold: float = 0.10,
) -> ComparisonReport:
    """Diff two runs.

    Args:
        baseline: The "what we had before" run.
        candidate: The "what we're proposing" run.
        warning_pct: Aggregate composite-score drop (in percentage points of [0,1])
            above which the report is tagged WARNING.
        critical_pct: Same as above for CRITICAL. CI should block on CRITICAL.
        per_case_regression_threshold: Per-case composite drop above which a
            single case is labeled REGRESSION (independent of aggregate).

    The aggregate severity is computed in *delta percentage points*, i.e. if the
    baseline avg was 0.85 and the candidate is 0.80, the delta is 5pp — even
    though that's a ~5.9% relative drop, the CI threshold knob is intentionally
    in absolute terms because it's easier to reason about.
    """
    baseline_by_id = {c.case_id: c for c in baseline.cases}
    candidate_by_id = {c.case_id: c for c in candidate.cases}

    diffs: list[CaseDiff] = []
    n_reg = n_imp = n_unc = 0

    for case_id in sorted(set(baseline_by_id) | set(candidate_by_id)):
        b = baseline_by_id.get(case_id)
        c = candidate_by_id.get(case_id)

        if b is None and c is not None:
            diffs.append(CaseDiff(case_id=case_id, verdict=Verdict.NEW, candidate=c))
            continue
        if c is None and b is not None:
            diffs.append(CaseDiff(case_id=case_id, verdict=Verdict.REMOVED, baseline=b))
            continue
        assert b is not None and c is not None  # for the type checker

        delta = c.scores.composite - b.scores.composite
        if delta <= -per_case_regression_threshold:
            verdict = Verdict.REGRESSION
            n_reg += 1
        elif delta >= per_case_regression_threshold:
            verdict = Verdict.IMPROVEMENT
            n_imp += 1
        else:
            verdict = Verdict.UNCHANGED
            n_unc += 1

        diffs.append(
            CaseDiff(
                case_id=case_id,
                verdict=verdict,
                baseline=b,
                candidate=c,
                composite_delta=delta,
            )
        )

    avg_delta_pp = (candidate.summary.avg_composite - baseline.summary.avg_composite) * 100.0
    severity = _classify(avg_delta_pp, warning_pct, critical_pct)

    return ComparisonReport(
        baseline=baseline.metadata,
        candidate=candidate.metadata,
        severity=severity,
        avg_composite_delta_pct=avg_delta_pp,
        n_regressions=n_reg,
        n_improvements=n_imp,
        n_unchanged=n_unc,
        diffs=diffs,
    )


def _classify(delta_pp: float, warning_pct: float, critical_pct: float) -> Severity:
    drop = -delta_pp  # positive = worse
    if drop >= critical_pct:
        return Severity.CRITICAL
    if drop >= warning_pct:
        return Severity.WARNING
    return Severity.OK

"""Rolling-average drift detection.

A single PR's regression check (run-vs-run delta) catches sudden quality cliffs.
Drift detection catches the slow leak: if `avg_composite` has been quietly
sliding down across the last N runs, the rolling window will spot it even when
no single PR crosses the per-run threshold.
"""

from __future__ import annotations

from ..models import DriftPoint, DriftReport, Severity


def analyze_drift(
    points: list[DriftPoint],
    *,
    window: int = 7,
    warning_pct: float = 3.0,
    critical_pct: float = 8.0,
) -> DriftReport:
    """Compare the most recent run to the rolling average of the prior N-1 runs.

    Returns a DriftReport with severity OK by default if fewer than 2 points
    are available — drift detection requires history to be meaningful.
    """
    if not points:
        return DriftReport(
            window=window,
            points=[],
            rolling_avg=0.0,
            latest_avg=0.0,
            drift_pct=0.0,
            severity=Severity.OK,
        )

    truncated = points[-window:]
    latest = truncated[-1]
    prior = truncated[:-1]
    if not prior:
        return DriftReport(
            window=window,
            points=truncated,
            rolling_avg=latest.avg_composite,
            latest_avg=latest.avg_composite,
            drift_pct=0.0,
            severity=Severity.OK,
        )

    rolling = sum(p.avg_composite for p in prior) / len(prior)
    drift_pp = (latest.avg_composite - rolling) * 100.0
    severity = _classify(drift_pp, warning_pct, critical_pct)
    return DriftReport(
        window=window,
        points=truncated,
        rolling_avg=rolling,
        latest_avg=latest.avg_composite,
        drift_pct=drift_pp,
        severity=severity,
    )


def _classify(drift_pp: float, warning_pct: float, critical_pct: float) -> Severity:
    drop = -drift_pp
    if drop >= critical_pct:
        return Severity.CRITICAL
    if drop >= warning_pct:
        return Severity.WARNING
    return Severity.OK

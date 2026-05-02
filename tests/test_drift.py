from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from model_regression.models import DriftPoint, Severity
from model_regression.reporting.drift import analyze_drift


def _points(values: list[float]) -> list[DriftPoint]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        DriftPoint(run_id=f"r{i}", created_at=base + timedelta(days=i), avg_composite=v)
        for i, v in enumerate(values)
    ]


def test_drift_empty_history_is_ok() -> None:
    rep = analyze_drift([])
    assert rep.severity is Severity.OK
    assert rep.points == []


def test_drift_single_point_ok() -> None:
    rep = analyze_drift(_points([0.9]))
    assert rep.severity is Severity.OK
    assert rep.drift_pct == 0.0


def test_drift_critical_when_latest_far_below_rolling_avg() -> None:
    rep = analyze_drift(
        _points([0.95, 0.94, 0.95, 0.93, 0.95, 0.94, 0.80]),
        window=7,
        warning_pct=3,
        critical_pct=8,
    )
    assert rep.severity is Severity.CRITICAL


def test_drift_warning_zone() -> None:
    rep = analyze_drift(
        _points([0.95, 0.95, 0.95, 0.91]), window=7, warning_pct=3, critical_pct=8
    )
    assert rep.severity is Severity.WARNING


def test_drift_clamps_to_window() -> None:
    rep = analyze_drift(_points([0.5, 0.6, 0.7, 0.8, 0.9, 1.0]), window=3)
    assert len(rep.points) == 3
    assert rep.latest_avg == pytest.approx(1.0)

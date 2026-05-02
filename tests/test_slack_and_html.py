from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from model_regression.models import DriftPoint, DriftReport, Severity
from model_regression.reporting import (
    build_slack_message,
    compare_runs,
    post_slack_alert,
)
from model_regression.reporting.html_report import write_html

from .conftest import make_run


def _drift(severity: Severity = Severity.WARNING) -> DriftReport:
    return DriftReport(
        window=7,
        points=[
            DriftPoint(run_id="a", created_at=__import__("datetime").datetime.now(__import__("datetime").UTC), avg_composite=0.9),
            DriftPoint(run_id="b", created_at=__import__("datetime").datetime.now(__import__("datetime").UTC), avg_composite=0.8),
        ],
        rolling_avg=0.9,
        latest_avg=0.8,
        drift_pct=-10.0,
        severity=severity,
    )


def test_slack_payload_includes_drift_when_provided() -> None:
    baseline = make_run(run_id="b", avg=0.95)
    candidate = make_run(run_id="c", avg=0.85)
    report = compare_runs(baseline=baseline, candidate=candidate)
    payload = build_slack_message(report, drift=_drift())
    [att] = payload["attachments"]
    field_titles = [f["title"] for f in att["fields"]]
    assert "Drift (7-run)" in field_titles


def test_slack_payload_includes_report_url() -> None:
    baseline = make_run(run_id="b", avg=0.9)
    candidate = make_run(run_id="c", avg=0.91)
    report = compare_runs(baseline=baseline, candidate=candidate)
    payload = build_slack_message(report, report_url="https://example.com/r")
    assert payload["attachments"][0]["title_link"] == "https://example.com/r"


@pytest.mark.asyncio
async def test_post_slack_alert_calls_webhook() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read()
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await post_slack_alert("https://hooks.example/x", {"hello": "world"}, client=client)
    assert "hello" in captured["body"].decode()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_post_slack_alert_rejects_empty_url() -> None:
    with pytest.raises(ValueError):
        await post_slack_alert("", {})


def test_write_html_persists_file(tmp_path: Path) -> None:
    baseline = make_run(run_id="b", avg=0.95)
    candidate = make_run(run_id="c", avg=0.80)
    report = compare_runs(baseline=baseline, candidate=candidate)
    out = write_html(report, tmp_path / "sub" / "report.html")
    assert out.exists()
    assert "Regression Report" in out.read_text()

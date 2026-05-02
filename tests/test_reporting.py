from __future__ import annotations

from model_regression.models import Severity, Verdict
from model_regression.reporting.comparator import compare_runs
from model_regression.reporting.html_report import render_html
from model_regression.reporting.slack import build_slack_message

from .conftest import make_run


def test_html_report_contains_severity_and_run_ids() -> None:
    baseline = make_run(run_id="base-1", avg=0.95)
    candidate = make_run(run_id="cand-1", avg=0.80)
    report = compare_runs(baseline=baseline, candidate=candidate)
    html = render_html(report)
    assert report.severity.value in html
    assert "cand-1" in html
    assert "base-1" in html


def test_slack_payload_uses_severity_color() -> None:
    baseline = make_run(run_id="base-1", avg=0.95)
    candidate = make_run(run_id="cand-1", avg=0.80)
    report = compare_runs(baseline=baseline, candidate=candidate)
    payload = build_slack_message(report)
    [attachment] = payload["attachments"]
    assert attachment["color"] == "#ef4444"  # critical
    assert "CRITICAL" in attachment["title"]


def test_slack_payload_ok_color() -> None:
    baseline = make_run(run_id="b", avg=0.90)
    candidate = make_run(run_id="c", avg=0.91)
    report = compare_runs(baseline=baseline, candidate=candidate)
    payload = build_slack_message(report)
    [attachment] = payload["attachments"]
    assert attachment["color"] == "#22c55e"
    assert report.severity is Severity.OK


def test_pr_comment_lists_regressions() -> None:
    from model_regression.ci.github import build_pr_comment

    baseline = make_run(run_id="b", avg=0.95, n_cases=2)
    candidate = make_run(run_id="c", avg=0.50, n_cases=2)
    report = compare_runs(baseline=baseline, candidate=candidate)
    md = build_pr_comment(report)
    assert "Regression report" in md
    assert any(d.verdict is Verdict.REGRESSION for d in report.diffs)
    assert "CRITICAL" in md

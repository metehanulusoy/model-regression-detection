"""Slack incoming-webhook dispatcher.

Two responsibilities, deliberately split:

- `build_slack_message`: pure function, no I/O. Trivially testable.
- `post_slack_alert`: thin async wrapper that POSTs the payload.

Severity colors map to Slack's standard hex codes ("good", "warning", "danger").
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import ComparisonReport, DriftReport, Severity

_SEVERITY_COLORS: dict[Severity, str] = {
    Severity.OK: "#22c55e",
    Severity.WARNING: "#f59e0b",
    Severity.CRITICAL: "#ef4444",
}


def build_slack_message(
    report: ComparisonReport,
    *,
    drift: DriftReport | None = None,
    report_url: str | None = None,
) -> dict[str, Any]:
    """Build a Slack-attachment-style payload from a ComparisonReport.

    Format follows Slack's legacy attachments because they render reliably
    inside both webhooks and channels' "Apps" picker.
    """
    color = _SEVERITY_COLORS[report.severity]
    delta = report.avg_composite_delta_pct
    delta_str = f"{delta:+.2f}pp"
    title = (
        f"[{report.severity.value.upper()}] "
        f"{report.candidate.prompt_name}@{report.candidate.prompt_version} "
        f"→ {delta_str}"
    )

    fields: list[dict[str, Any]] = [
        {"title": "Regressions", "value": str(report.n_regressions), "short": True},
        {"title": "Improvements", "value": str(report.n_improvements), "short": True},
        {"title": "Unchanged", "value": str(report.n_unchanged), "short": True},
        {"title": "Model", "value": report.candidate.model, "short": True},
    ]
    if drift is not None and len(drift.points) >= 2:
        fields.append(
            {
                "title": f"Drift ({drift.window}-run)",
                "value": f"{drift.drift_pct:+.2f}pp ({drift.severity.value})",
                "short": True,
            }
        )

    attachment: dict[str, Any] = {
        "color": color,
        "title": title,
        "fields": fields,
        "footer": "model-regression-detection",
        "mrkdwn_in": ["text"],
    }
    if report_url:
        attachment["title_link"] = report_url

    return {"attachments": [attachment]}


async def post_slack_alert(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> None:
    """POST the payload to a Slack incoming webhook. Raises on non-2xx."""
    if not webhook_url:
        raise ValueError("webhook_url is empty")

    if client is None:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            resp = await c.post(webhook_url, json=payload)
    else:
        resp = await client.post(webhook_url, json=payload, timeout=timeout_s)
    resp.raise_for_status()

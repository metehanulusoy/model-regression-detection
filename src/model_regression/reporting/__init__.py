"""Reporting layer: comparator, drift, HTML, Slack."""

from .comparator import compare_runs
from .drift import analyze_drift
from .html_report import render_html
from .slack import build_slack_message, post_slack_alert

__all__ = [
    "analyze_drift",
    "build_slack_message",
    "compare_runs",
    "post_slack_alert",
    "render_html",
]

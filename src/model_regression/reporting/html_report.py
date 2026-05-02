"""Render a ComparisonReport to a single self-contained HTML file."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, StrictUndefined, select_autoescape

from ..models import ComparisonReport
from ._template import HTML_TEMPLATE

_ENV = Environment(
    autoescape=select_autoescape(["html", "xml"]),
    undefined=StrictUndefined,
)


def render_html(report: ComparisonReport) -> str:
    """Return the HTML report as a string."""
    template = _ENV.from_string(HTML_TEMPLATE)
    return template.render(report=report)


def write_html(report: ComparisonReport, out_path: Path) -> Path:
    """Write the HTML report to disk and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(report), encoding="utf-8")
    return out_path

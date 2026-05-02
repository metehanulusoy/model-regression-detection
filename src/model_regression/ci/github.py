"""GitHub helpers: PR comment markdown + exit-code mapping for merge-blocking."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..models import ComparisonReport, DriftReport, Severity, Verdict

EXIT_OK: int = 0
EXIT_WARNING: int = 0  # warnings should NOT block merge
EXIT_CRITICAL: int = 2  # CRITICAL blocks the merge gate


def severity_to_exit_code(severity: Severity) -> int:
    """Map ComparisonReport severity to a CI exit code.

    OK and WARNING return 0 (don't block merge — humans see the warning in PR
    comments / Slack). CRITICAL returns 2 (the convention for "real failure"
    distinct from an internal error which would be 1).
    """
    if severity is Severity.CRITICAL:
        return EXIT_CRITICAL
    return EXIT_OK


_HEADER = "<!-- model-regression-detection: do-not-edit -->"


def build_pr_comment(
    report: ComparisonReport,
    *,
    drift: DriftReport | None = None,
    report_url: str | None = None,
    max_diffs_shown: int = 8,
) -> str:
    """Render a markdown comment for the PR.

    The leading HTML comment is a stable marker so repeated runs can update an
    existing comment instead of stacking new ones.
    """
    sev = report.severity.value.upper()
    icon = {Severity.OK: "✅", Severity.WARNING: "⚠️", Severity.CRITICAL: "🛑"}[report.severity]
    parts = [
        _HEADER,
        f"### {icon} Regression report — `{sev}`",
        "",
        f"**Prompt:** `{report.candidate.prompt_name}@{report.candidate.prompt_version}` &nbsp; "
        f"**Model:** `{report.candidate.model}`",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Composite Δ | **{report.avg_composite_delta_pct:+.2f}pp** |",
        f"| Regressions | {report.n_regressions} |",
        f"| Improvements | {report.n_improvements} |",
        f"| Unchanged | {report.n_unchanged} |",
    ]
    if drift is not None and len(drift.points) >= 2:
        parts.append(
            f"| Drift ({drift.window}-run) | {drift.drift_pct:+.2f}pp "
            f"({drift.severity.value}) |"
        )

    regressions = [d for d in report.diffs if d.verdict is Verdict.REGRESSION]
    if regressions:
        parts.extend(["", "#### Top regressions"])
        parts.append("| Case | Δ | Baseline | Candidate |")
        parts.append("|---|---|---|---|")
        for d in regressions[:max_diffs_shown]:
            b_out = (d.baseline.output if d.baseline else "—").replace("\n", " ").replace("|", "\\|")
            c_out = (d.candidate.output if d.candidate else "—").replace("\n", " ").replace("|", "\\|")
            parts.append(
                f"| `{d.case_id}` | {d.composite_delta:+.3f} | "
                f"{_truncate(b_out, 80)} | {_truncate(c_out, 80)} |"
            )
        if len(regressions) > max_diffs_shown:
            parts.append(f"_…and {len(regressions) - max_diffs_shown} more._")

    if report_url:
        parts.extend(["", f"[View full HTML report]({report_url})"])

    return "\n".join(parts)


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def post_or_update_pr_comment(
    *,
    repository: str,
    pr_number: int,
    body: str,
    token: str,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """Best-effort PR comment poster. Updates an existing bot comment in place
    (matched by `_HEADER` marker) or creates a new one. Returns the API JSON.

    Synchronous on purpose: this is invoked once per CI run after the eval is
    done, so adding asyncio buys nothing.
    """
    if not token:
        raise ValueError("token is empty")
    if "/" not in repository:
        raise ValueError("repository must be in 'owner/repo' form")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{repository}"
    with httpx.Client(timeout=timeout_s) as client:
        existing = _find_existing(client, base, pr_number, headers)
        if existing is not None:
            resp = client.patch(
                f"{base}/issues/comments/{existing}", headers=headers, json={"body": body}
            )
        else:
            resp = client.post(
                f"{base}/issues/{pr_number}/comments", headers=headers, json={"body": body}
            )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def _find_existing(
    client: httpx.Client, base: str, pr_number: int, headers: dict[str, str]
) -> int | None:
    page = 1
    while True:
        resp = client.get(
            f"{base}/issues/{pr_number}/comments",
            headers=headers,
            params={"per_page": 100, "page": page},
        )
        resp.raise_for_status()
        items = resp.json()
        for c in items:
            if isinstance(c.get("body"), str) and _HEADER in c["body"]:
                return int(c["id"])
        if len(items) < 100:
            return None
        page += 1


def in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"

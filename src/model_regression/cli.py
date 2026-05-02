"""Command-line entry point.

Three subcommands:

- `mrd run`     : execute an eval run, persist it, optionally compare to baseline.
- `mrd compare` : compare two existing run_ids and emit HTML/Slack/PR comment.
- `mrd drift`   : print the rolling-drift report for a prompt.

Designed to be the single entry called from CI: `mrd run --prompt classifier
--dataset golden/customer_support.jsonl --baseline auto --report ./reports`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click

from .ci.github import (
    build_pr_comment,
    in_github_actions,
    post_or_update_pr_comment,
    severity_to_exit_code,
)
from .config import load_settings
from .dataset import load_dataset
from .db import RunStore
from .eval import EvalRunner, LLMClient
from .logging import configure as configure_logging
from .logging import get_logger
from .prompts import PromptManager
from .reporting import (
    analyze_drift,
    build_slack_message,
    compare_runs,
    post_slack_alert,
)
from .reporting.html_report import write_html


@click.group()
@click.option(
    "--log-level",
    default=os.environ.get("MRD_LOG_LEVEL", "INFO"),
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
)
def main(log_level: str) -> None:
    """Model Regression Detection CLI."""
    configure_logging(log_level)


@main.command("run")
@click.option("--prompt", "prompt_name", required=True, help="Prompt name (file or dir under --prompts-dir)")
@click.option("--prompt-version", default=None, help="Prompt version. If omitted, latest is used.")
@click.option("--dataset", "dataset_path", required=True, type=click.Path(path_type=Path, exists=True))
@click.option("--baseline", default=None, help="Baseline run_id, 'auto' for latest, or omit to skip comparison.")
@click.option("--no-judge", is_flag=True, help="Disable LLM-as-judge scoring (exact match only).")
@click.option("--report-dir", "report_dir", default=None, type=click.Path(path_type=Path))
@click.option("--git-sha", default=None)
@click.option("--git-branch", default=None)
@click.option("--pr-number", default=None, type=int)
def run_cmd(
    prompt_name: str,
    prompt_version: str | None,
    dataset_path: Path,
    baseline: str | None,
    no_judge: bool,
    report_dir: Path | None,
    git_sha: str | None,
    git_branch: str | None,
    pr_number: int | None,
) -> None:
    """Run an eval; optionally compare to baseline."""
    settings = load_settings()
    log = get_logger("mrd.cli")

    if not settings.openai_api_key:
        click.echo("MRD_OPENAI_API_KEY is required", err=True)
        sys.exit(1)

    pm = PromptManager(settings.prompts_dir if not Path("prompts").is_dir() else Path("prompts"))
    prompt = pm.load(prompt_name, version=prompt_version)
    cases = load_dataset(dataset_path)
    log.info("cli.run.loaded", n_cases=len(cases), prompt=prompt.name, version=prompt.version)

    store = RunStore(settings.db_path)

    async def _execute() -> int:
        async with LLMClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout_s=settings.request_timeout_s,
            max_retries=settings.max_retries,
        ) as client:
            runner = EvalRunner(
                client=client,
                target_model=settings.target_model,
                judge_model=None if no_judge else settings.judge_model,
                max_concurrency=settings.max_concurrency,
            )
            run = await runner.run(
                prompt=prompt,
                cases=cases,
                git_sha=git_sha or os.environ.get("GITHUB_SHA"),
                git_branch=git_branch or os.environ.get("GITHUB_REF_NAME"),
                pr_number=pr_number or settings.github_pr_number or None,
            )
            store.save_run(run)
            click.echo(
                f"Run {run.metadata.run_id}: avg_composite={run.summary.avg_composite:.3f} "
                f"errors={run.summary.n_errors} cost=${run.summary.total_cost_usd:.4f}"
            )

            if baseline is None:
                return 0

            base = (
                store.latest_run(prompt.name, before_run_id=run.metadata.run_id)
                if baseline == "auto"
                else store.get_run(baseline)
            )
            if base is None:
                click.echo("No baseline available — skipping comparison.", err=True)
                return 0

            report = compare_runs(
                baseline=base,
                candidate=run,
                warning_pct=settings.warning_delta_pct,
                critical_pct=settings.critical_delta_pct,
            )
            drift = analyze_drift(
                store.drift_window(prompt.name, settings.drift_window),
                window=settings.drift_window,
                warning_pct=settings.warning_delta_pct,
                critical_pct=settings.critical_delta_pct,
            )

            html_path = None
            if report_dir is not None:
                html_path = write_html(report, report_dir / f"{run.metadata.run_id}.html")
                click.echo(f"HTML report: {html_path}")

            click.echo(
                f"Comparison: severity={report.severity.value} "
                f"Δ={report.avg_composite_delta_pct:+.2f}pp "
                f"reg={report.n_regressions} imp={report.n_improvements} unc={report.n_unchanged}"
            )

            if settings.slack_webhook_url:
                payload = build_slack_message(report, drift=drift)
                try:
                    await post_slack_alert(settings.slack_webhook_url, payload)
                except Exception as exc:
                    log.warning("slack.post.error", error=str(exc))

            if (
                in_github_actions()
                and settings.github_token
                and settings.github_repository
                and settings.github_pr_number
            ):
                comment = build_pr_comment(report, drift=drift)
                try:
                    post_or_update_pr_comment(
                        repository=settings.github_repository,
                        pr_number=settings.github_pr_number,
                        body=comment,
                        token=settings.github_token,
                    )
                except Exception as exc:
                    log.warning("github.comment.error", error=str(exc))

            return severity_to_exit_code(report.severity)

    sys.exit(asyncio.run(_execute()))


@main.command("compare")
@click.option("--baseline", "baseline_id", required=True)
@click.option("--candidate", "candidate_id", required=True)
@click.option("--report-dir", default="reports", type=click.Path(path_type=Path))
def compare_cmd(baseline_id: str, candidate_id: str, report_dir: Path) -> None:
    """Compare two existing runs by ID."""
    settings = load_settings()
    store = RunStore(settings.db_path)
    base = store.get_run(baseline_id)
    cand = store.get_run(candidate_id)
    if base is None or cand is None:
        click.echo("baseline or candidate run_id not found", err=True)
        sys.exit(1)
    report = compare_runs(
        baseline=base,
        candidate=cand,
        warning_pct=settings.warning_delta_pct,
        critical_pct=settings.critical_delta_pct,
    )
    out = write_html(report, report_dir / f"{candidate_id}-vs-{baseline_id}.html")
    click.echo(f"Severity: {report.severity.value}")
    click.echo(f"HTML: {out}")
    sys.exit(severity_to_exit_code(report.severity))


@main.command("drift")
@click.option("--prompt", "prompt_name", required=True)
def drift_cmd(prompt_name: str) -> None:
    """Print rolling-drift summary for a prompt."""
    settings = load_settings()
    store = RunStore(settings.db_path)
    points = store.drift_window(prompt_name, settings.drift_window)
    drift = analyze_drift(
        points,
        window=settings.drift_window,
        warning_pct=settings.warning_delta_pct,
        critical_pct=settings.critical_delta_pct,
    )
    click.echo(f"Prompt: {prompt_name}")
    click.echo(f"Window: {drift.window}, Points: {len(drift.points)}")
    click.echo(f"Rolling avg: {drift.rolling_avg:.3f}, Latest: {drift.latest_avg:.3f}")
    click.echo(f"Drift: {drift.drift_pct:+.2f}pp ({drift.severity.value})")


if __name__ == "__main__":  # pragma: no cover
    main()

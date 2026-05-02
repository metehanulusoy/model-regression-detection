"""Standalone example: run a regression eval against a tiny in-memory dataset.

Useful for kicking the tires without a real CI workflow:

    export MRD_OPENAI_API_KEY=sk-...
    python examples/example_run.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from model_regression.config import load_settings
from model_regression.db import RunStore
from model_regression.eval import EvalRunner, LLMClient
from model_regression.logging import configure
from model_regression.models import TestCase
from model_regression.prompts import PromptManager
from model_regression.reporting import compare_runs
from model_regression.reporting.html_report import write_html


async def main() -> None:
    configure("INFO")
    settings = load_settings()
    if not settings.openai_api_key:
        raise SystemExit("Set MRD_OPENAI_API_KEY in your environment first.")

    pm = PromptManager(Path("prompts"))
    prompt = pm.load("customer_support")

    cases = [
        TestCase(
            id="example-1",
            input="My credit card was charged twice this month",
            expected="billing",
            expected_label="billing",
            metadata={"subject": "Duplicate charge"},
        ),
        TestCase(
            id="example-2",
            input="The export to CSV button does nothing in Chrome",
            expected="bug_report",
            expected_label="bug_report",
            metadata={"subject": "CSV export broken"},
        ),
    ]

    store = RunStore(settings.db_path)
    async with LLMClient(api_key=settings.openai_api_key) as client:
        runner = EvalRunner(
            client=client,
            target_model=settings.target_model,
            judge_model=settings.judge_model,
            max_concurrency=settings.max_concurrency,
        )
        run = await runner.run(prompt=prompt, cases=cases)
        store.save_run(run)
        print(
            f"Run {run.metadata.run_id}: avg_composite={run.summary.avg_composite:.3f} "
            f"cost=${run.summary.total_cost_usd:.4f}"
        )

        baseline = store.latest_run("customer_support", before_run_id=run.metadata.run_id)
        if baseline is not None:
            report = compare_runs(baseline=baseline, candidate=run)
            out = write_html(report, Path("reports") / f"{run.metadata.run_id}.html")
            print(f"Severity={report.severity.value}; report at {out}")


if __name__ == "__main__":
    asyncio.run(main())

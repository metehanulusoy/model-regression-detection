"""Async eval runner.

Orchestrates: for each TestCase →
  1. Render prompt → call target model.
  2. Score output: exact_match + (optional) LLM-as-judge.
  3. Return a CaseResult.

Concurrency is bounded by an asyncio.Semaphore to respect API rate limits and
keep wall-clock predictable. We never let one bad case fail the whole run —
exceptions become CaseResult.error and the run continues.
"""

from __future__ import annotations

import asyncio
import statistics
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from ..logging import get_logger
from ..models import (
    CaseResult,
    CaseScores,
    Run,
    RunMetadata,
    RunSummary,
    TestCase,
)
from ..prompts import Prompt
from .llm_client import ChatMessage, LLMClient
from .scorers import judge_score_async, score_exact_match

log = get_logger(__name__)


class EvalRunner:
    """Stateless runner. Build once per process, reuse across runs."""

    def __init__(
        self,
        *,
        client: LLMClient,
        target_model: str,
        judge_model: str | None,
        max_concurrency: int = 10,
    ):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._client = client
        self._target_model = target_model
        self._judge_model = judge_model
        self._sem = asyncio.Semaphore(max_concurrency)

    async def run(
        self,
        *,
        prompt: Prompt,
        cases: Iterable[TestCase],
        run_id: str | None = None,
        git_sha: str | None = None,
        git_branch: str | None = None,
        pr_number: int | None = None,
        notes: str | None = None,
    ) -> Run:
        cases_list = list(cases)
        if not cases_list:
            raise ValueError("cases must be non-empty")

        run_id = run_id or _new_run_id(prompt.name, prompt.version)
        log.info(
            "eval.run.start",
            run_id=run_id,
            n_cases=len(cases_list),
            prompt=prompt.name,
            version=prompt.version,
            model=self._target_model,
        )

        results = await asyncio.gather(
            *[self._eval_case(prompt, c) for c in cases_list],
            return_exceptions=False,
        )

        summary = _summarize(results)
        metadata = RunMetadata(
            run_id=run_id,
            created_at=datetime.now(UTC),
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            model=self._target_model,
            judge_model=self._judge_model or "none",
            git_sha=git_sha,
            git_branch=git_branch,
            pr_number=pr_number,
            notes=notes,
        )
        log.info(
            "eval.run.done",
            run_id=run_id,
            avg_composite=summary.avg_composite,
            n_errors=summary.n_errors,
            total_cost_usd=summary.total_cost_usd,
        )
        return Run(metadata=metadata, summary=summary, cases=results)

    async def _eval_case(self, prompt: Prompt, case: TestCase) -> CaseResult:
        async with self._sem:
            try:
                rendered_user = prompt.render_user({"input": case.input, **case.metadata})
                resp = await self._client.chat(
                    model=self._target_model,
                    messages=[
                        ChatMessage(role="system", content=prompt.system),
                        ChatMessage(role="user", content=rendered_user),
                    ],
                    temperature=prompt.temperature,
                    max_tokens=prompt.max_output_tokens,
                )
            except Exception as exc:
                log.warning("eval.case.error", case_id=case.id, error=str(exc))
                return CaseResult(
                    case_id=case.id,
                    output="",
                    scores=CaseScores(exact_match=0.0, judge_score=0.0, composite=0.0),
                    latency_ms=0,
                    cost_usd=0.0,
                    error=str(exc),
                )

            exact = score_exact_match(resp.content, case.expected, case.expected_label)
            judge = exact  # default: trust exact match when judge is disabled
            if self._judge_model is not None and case.expected is not None:
                try:
                    judge, _reason = await judge_score_async(
                        client=self._client,
                        judge_model=self._judge_model,
                        question=case.input,
                        expected=case.expected,
                        candidate=resp.content,
                    )
                except Exception as exc:
                    log.warning("eval.judge.error", case_id=case.id, error=str(exc))
                    judge = exact

            scores = CaseScores.from_parts(exact_match=exact, judge_score=judge)
            return CaseResult(
                case_id=case.id,
                output=resp.content,
                scores=scores,
                latency_ms=resp.latency_ms,
                cost_usd=resp.cost_usd,
                error=None,
            )


def _summarize(results: list[CaseResult]) -> RunSummary:
    n = len(results)
    n_err = sum(1 for r in results if r.error is not None)
    composites = [r.scores.composite for r in results]
    exacts = [r.scores.exact_match for r in results]
    judges = [r.scores.judge_score for r in results]
    latencies = sorted(r.latency_ms for r in results)
    return RunSummary(
        n_cases=n,
        n_errors=n_err,
        avg_composite=_mean(composites),
        avg_exact_match=_mean(exacts),
        avg_judge_score=_mean(judges),
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
        total_cost_usd=sum(r.cost_usd for r in results),
    )


def _mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _percentile(sorted_values: list[int], pct: int) -> int:
    if not sorted_values:
        return 0
    if pct <= 0:
        return sorted_values[0]
    if pct >= 100:
        return sorted_values[-1]
    k = max(0, min(len(sorted_values) - 1, (len(sorted_values) * pct) // 100))
    return sorted_values[k]


def _new_run_id(prompt_name: str, version: str) -> str:
    return f"{prompt_name}-{version}-{uuid.uuid4().hex[:10]}"

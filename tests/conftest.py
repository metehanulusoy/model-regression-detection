"""Shared fixtures.

Tests never hit a real network. The httpx client used by LLMClient is replaced
with a respx-mocked transport for everything that goes through OpenAI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from model_regression.eval import LLMClient
from model_regression.models import (
    CaseResult,
    CaseScores,
    Run,
    RunMetadata,
    RunSummary,
)
from model_regression.models import TestCase as _TestCase


@pytest.fixture
def respx_mock() -> respx.MockRouter:
    with respx.mock(assert_all_called=False, base_url="https://api.openai.com/v1") as router:
        yield router


@pytest.fixture
async def llm_client(respx_mock: respx.MockRouter) -> LLMClient:
    transport = httpx.AsyncClient(transport=httpx.MockTransport(_dispatch_to_respx))
    async with LLMClient(api_key="test-key", client=transport, max_retries=0) as c:
        yield c
    await transport.aclose()


def _dispatch_to_respx(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise RuntimeError("respx should have intercepted this request")


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "mrd.sqlite3"


def make_run(
    *,
    run_id: str,
    prompt_name: str = "test",
    prompt_version: str = "v1",
    avg: float,
    n_cases: int = 4,
) -> Run:
    """Build a synthetic Run with `n_cases` cases all scoring `avg`."""
    cases = [
        CaseResult(
            case_id=f"c{i}",
            output=f"out-{i}",
            scores=CaseScores(exact_match=avg, judge_score=avg, composite=avg),
            latency_ms=100,
            cost_usd=0.0001,
            error=None,
        )
        for i in range(n_cases)
    ]
    return Run(
        metadata=RunMetadata(
            run_id=run_id,
            created_at=datetime.now(UTC),
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            model="gpt-4o-mini",
            judge_model="gpt-4o",
        ),
        summary=RunSummary(
            n_cases=n_cases,
            n_errors=0,
            avg_composite=avg,
            avg_exact_match=avg,
            avg_judge_score=avg,
            p50_latency_ms=100,
            p95_latency_ms=100,
            total_cost_usd=0.0004,
        ),
        cases=cases,
    )


def make_case(case_id: str, expected: str | None = "billing") -> _TestCase:
    return _TestCase(
        id=case_id,
        input=f"input for {case_id}",
        expected=expected,
        expected_label=expected,
    )

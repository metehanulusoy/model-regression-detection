from __future__ import annotations

import httpx
import pytest
import respx

from model_regression.eval.llm_client import LLMClient
from model_regression.eval.scorers import (
    _parse_judge_response,
    judge_score_async,
    score_exact_match,
)


def test_exact_match_normalizes_whitespace_and_case() -> None:
    assert score_exact_match("  Billing\n", expected="billing", expected_label=None) == 1.0


def test_exact_match_falls_back_to_label_substring() -> None:
    assert score_exact_match("This is a BILLING issue", expected=None, expected_label="billing") == 1.0


def test_exact_match_zero_when_no_match() -> None:
    assert score_exact_match("bug_report", expected="billing", expected_label="billing") == 0.0


def test_exact_match_zero_when_no_expectations() -> None:
    assert score_exact_match("anything", expected=None, expected_label=None) == 0.0


def test_parse_judge_response_clamps_to_unit() -> None:
    score, reason = _parse_judge_response('{"score": 1.7, "reason": "too high"}')
    assert score == 1.0
    assert reason == "too high"


def test_parse_judge_response_handles_invalid_json() -> None:
    score, reason = _parse_judge_response("not json at all")
    assert score == 0.0
    assert reason.startswith("judge: parse error")


def test_parse_judge_response_handles_non_numeric_score() -> None:
    score, reason = _parse_judge_response('{"score": "high", "reason": "x"}')
    assert score == 0.0
    assert "invalid score type" in reason


@pytest.mark.asyncio
async def test_judge_score_async_uses_provided_judge_model(respx_mock: respx.MockRouter) -> None:
    respx_mock.post("/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"score": 0.8, "reason": "close enough"}'}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )

    transport = httpx.AsyncClient(timeout=5.0)
    try:
        async with LLMClient(api_key="k", client=transport, max_retries=0) as client:
            score, reason = await judge_score_async(
                client=client,
                judge_model="gpt-4o",
                question="q?",
                expected="yes",
                candidate="yep",
            )
    finally:
        await transport.aclose()

    assert score == pytest.approx(0.8)
    assert "close enough" in reason
    assert respx_mock.calls.last.request.url.path.endswith("/chat/completions")

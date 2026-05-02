from __future__ import annotations

import httpx
import pytest
import respx

from model_regression.eval import EvalRunner, LLMClient
from model_regression.models import TestCase as Case
from model_regression.prompts import Prompt


@pytest.fixture
def classifier_prompt() -> Prompt:
    return Prompt(
        name="cls",
        version="v1",
        system="Classify into billing, bug_report, feature_request.",
        user_template="Body: ${input}",
        temperature=0.0,
        max_output_tokens=16,
    )


def _mock_chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )


@pytest.mark.asyncio
async def test_runner_scores_correct_label_as_one(
    respx_mock: respx.MockRouter, classifier_prompt: Prompt
) -> None:
    respx_mock.post("/chat/completions").mock(return_value=_mock_chat_response("billing"))

    transport = httpx.AsyncClient()
    try:
        async with LLMClient(api_key="k", client=transport, max_retries=0) as client:
            runner = EvalRunner(
                client=client,
                target_model="gpt-4o-mini",
                judge_model=None,
                max_concurrency=2,
            )
            run = await runner.run(
                prompt=classifier_prompt,
                cases=[Case(id="c1", input="charged twice", expected="billing")],
            )
    finally:
        await transport.aclose()

    assert run.summary.n_cases == 1
    assert run.summary.n_errors == 0
    assert run.cases[0].scores.exact_match == 1.0
    assert run.cases[0].scores.composite == 1.0


@pytest.mark.asyncio
async def test_runner_records_error_when_api_raises(
    respx_mock: respx.MockRouter, classifier_prompt: Prompt
) -> None:
    respx_mock.post("/chat/completions").mock(return_value=httpx.Response(400, text="bad"))

    transport = httpx.AsyncClient()
    try:
        async with LLMClient(api_key="k", client=transport, max_retries=0) as client:
            runner = EvalRunner(
                client=client,
                target_model="gpt-4o-mini",
                judge_model=None,
                max_concurrency=2,
            )
            run = await runner.run(
                prompt=classifier_prompt,
                cases=[Case(id="c1", input="x", expected="billing")],
            )
    finally:
        await transport.aclose()

    assert run.summary.n_errors == 1
    assert run.cases[0].error is not None
    assert run.cases[0].scores.composite == 0.0


@pytest.mark.asyncio
async def test_runner_rejects_empty_dataset(classifier_prompt: Prompt) -> None:
    transport = httpx.AsyncClient()
    try:
        async with LLMClient(api_key="k", client=transport, max_retries=0) as client:
            runner = EvalRunner(
                client=client, target_model="gpt-4o-mini", judge_model=None
            )
            with pytest.raises(ValueError, match="non-empty"):
                await runner.run(prompt=classifier_prompt, cases=[])
    finally:
        await transport.aclose()

"""Scoring dimensions.

Two complementary signals:

1. **Exact match** (cheap, deterministic) — catches format breakage and
   case-sensitive label drift. Returns 1.0 only when the candidate exactly
   matches the expected output (after normalization). For label-style cases
   we also accept `expected_label` substring matching.

2. **LLM-as-judge** (expensive, robust to paraphrase) — asks a stronger model
   to grade the candidate against the expected reference on a 0-1 scale.
   Prompt forces the model to emit JSON `{"score": float, "reason": str}`
   so callers never have to parse free-form text.
"""

from __future__ import annotations

import json
import re
from typing import Final

from .llm_client import ChatMessage, LLMClient

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def score_exact_match(output: str, expected: str | None, expected_label: str | None) -> float:
    """Deterministic scorer.

    - Returns 1.0 if normalized output equals normalized expected.
    - Returns 1.0 if expected is None and expected_label appears anywhere in output.
    - Returns 0.0 otherwise.

    Why this shape: most production "classifier"-style features have either a
    canonical answer or a label list. Tagging the latter case with substring
    match is a reasonable cheap heuristic; the LLM judge handles ambiguity.
    """
    if expected is not None:
        return 1.0 if _normalize(output) == _normalize(expected) else 0.0
    if expected_label is not None:
        return 1.0 if _normalize(expected_label) in _normalize(output) else 0.0
    return 0.0


_JUDGE_SYSTEM = (
    "You are a strict but fair grading assistant. Given a USER QUESTION, an "
    "EXPECTED ANSWER, and a CANDIDATE ANSWER, return a single JSON object with "
    "two keys: `score` (a float in [0,1] where 1 means semantically equivalent "
    "to the expected answer and 0 means clearly wrong) and `reason` (a short "
    "string). Be strict on factual or numeric errors. Tolerate paraphrase. "
    "Output ONLY the JSON object, no prose."
)

_JUDGE_USER_TEMPLATE = (
    "USER QUESTION:\n{question}\n\n"
    "EXPECTED ANSWER:\n{expected}\n\n"
    "CANDIDATE ANSWER:\n{candidate}\n\n"
    "Return JSON now."
)


_JSON_OBJ_RE: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)


async def judge_score_async(
    *,
    client: LLMClient,
    judge_model: str,
    question: str,
    expected: str,
    candidate: str,
) -> tuple[float, str]:
    """Run the LLM-as-judge. Returns (score, reason). Score is clamped to [0,1].

    On parse failure, returns (0.0, reason="judge: parse error: ...") rather
    than raising. A failing judge call shouldn't blow up the entire eval run —
    we'd rather record the bad case and keep going.
    """
    response = await client.chat(
        model=judge_model,
        messages=[
            ChatMessage(role="system", content=_JUDGE_SYSTEM),
            ChatMessage(
                role="user",
                content=_JUDGE_USER_TEMPLATE.format(
                    question=question.strip(),
                    expected=expected.strip(),
                    candidate=candidate.strip(),
                ),
            ),
        ],
        temperature=0.0,
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    return _parse_judge_response(response.content)


def _parse_judge_response(raw: str) -> tuple[float, str]:
    match = _JSON_OBJ_RE.search(raw)
    if match is None:
        return 0.0, f"judge: parse error: no JSON object in response: {raw[:120]}"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return 0.0, f"judge: parse error: {exc}"

    score_raw = data.get("score")
    reason = str(data.get("reason", "")).strip() or "no reason given"
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        return 0.0, f"judge: invalid score type: {score_raw!r}"

    return max(0.0, min(1.0, score)), reason

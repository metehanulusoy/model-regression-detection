# ADR-002: Two-dimensional scoring (exact match + LLM-as-judge), blended into a composite

**Status:** Accepted

## Context

Eval frameworks for LLM features split, broadly, into three camps:

1. **Deterministic** — exact match, regex, ROUGE/BLEU, embedding similarity.
2. **Model-graded** — LLM-as-judge, RAGAS-style faithfulness/answer-relevance.
3. **Human-graded** — gold rater agreement, adjudication.

Each catches a different failure mode and misses others. Exact match misses paraphrase. LLM judges can be flaky on numerical or factual questions. Embedding similarity is hard to threshold and hides label-style breakage. Pure human grading doesn't fit a CI loop.

## Decision

Score every case along **two** axes and blend them into a single `composite ∈ [0, 1]`:

- `exact_match` — 1.0 iff the normalized output equals `expected`, or contains `expected_label` as a substring; else 0.0.
- `judge_score` — A separate, stronger model (`gpt-4o` by default) grades the candidate answer against the expected on a 0–1 scale, returning JSON with a short reason.
- `composite = 0.7 * judge_score + 0.3 * exact_match` by default; `judge_weight` is configurable.

When `--no-judge` is passed (or no `expected` is provided), `judge_score` falls back to `exact_match`, so composite is well-defined for every case.

## Consequences

**Why this works:**

- **Exact match is the canary for format breakage.** When a prompt edit accidentally adds a leading newline or changes the casing of labels, exact match drops to zero immediately. Embedding similarity wouldn't notice; a forgiving judge wouldn't either.
- **The judge is the canary for semantic regressions.** When a prompt edit turns "billing" into "billing-related question" or starts emitting verbose explanations, exact match flags it as broken even though the answer is still correct. The judge reverses that verdict.
- **The blend means neither dimension can hide the other's failure.** A composite of 0.5 from `(1.0, 0.0)` looks the same in aggregate as `(0.0, 1.0)`, but the per-case diff in the HTML report shows both numbers, so a reviewer can tell which scorer disagreed.
- **JSON-only judge prompt.** We force a `{"score": float, "reason": str}` schema and use the OpenAI `response_format: json_object` flag. Free-form judge outputs are unparseable in practice — every grader project I've seen gets bitten by this.

**Trade-offs:**

- The judge call doubles the run cost. For 100 cases at the default models, the judge is ~$0.05 per run vs. ~$0.02 for the target. We accept this; it's still well under the $0.50 PR budget in the spec.
- A judge that drifts (model upgrades silently) will skew historical comparisons. We pin the judge model in `RunMetadata.judge_model`, so post-hoc analysis can detect "this run used a different judge than that run".
- Numeric questions are harder for the judge. We do not currently have a dedicated numeric scorer; if that becomes a recurring pain, we'll add one as a third dimension behind the same `CaseScores` interface.

## Alternatives considered

- **RAGAS / DeepEval out of the box.** Both are excellent for RAG-specific metrics (faithfulness, context recall) but heavier than the harness needs for a classifier-style use case. We may import RAGAS for RAG projects later, but it's a poor default here.
- **Embedding cosine similarity as the second dimension.** Rejected: cosine doesn't penalize verbose-but-correct outputs, which is a common regression pattern from prompt edits.
- **Single LLM judge, no exact match.** Rejected: judges hallucinate confidence on format breaks. The deterministic floor is cheap insurance.

## Revisit if

- A team reports that the judge is the dominant failure mode (false positives or false negatives).
- We start running on prompts where every output is structured JSON — at that point, schema validation should be a first-class scorer.

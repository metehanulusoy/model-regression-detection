# model-regression-detection

> A CI/CD-style regression detection pipeline for LLM-powered features. Catches quality drops on every prompt or model change before they reach users.

[![Tests](https://github.com/metehanulusoy/model-regression-detection/actions/workflows/test.yml/badge.svg)](https://github.com/metehanulusoy/model-regression-detection/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/typed-mypy%20strict-blueviolet.svg)](https://mypy-lang.org/)

`model-regression-detection` (CLI: `mrd`) is a small, opinionated tool that turns LLM evaluation into a normal CI gate. Point it at a versioned prompt and a golden dataset of input/expected pairs; it runs the prompt against your model, scores each case (exact match + LLM-as-judge), compares the result to the previous run, and either fails the build, posts a Slack alert, or comments on the PR — based on configurable severity thresholds.

It also tracks **slow drift**: a 7-run rolling average that catches the kind of quality regression no single PR is responsible for.

---

## Why this exists

Traditional unit tests don't work for LLM features:

- A prompt change that "looks fine" can drop classifier accuracy by 12 points.
- A model upgrade (e.g. `gpt-4o-mini` → newer snapshot) silently shifts behavior.
- Quality erodes gradually as small prompt edits stack up.

This project wraps those failure modes in something that fits the developer workflow you already have — one CI job, one PR comment, one Slack message.

---

## Architecture

```
┌────────────────────────┐    ┌─────────────────────────┐    ┌────────────────────────┐
│   Eval Engine          │    │  Reporting Layer        │    │   CI/CD Integration    │
│                        │    │                         │    │                        │
│  • async runner        │ ─► │  • per-case comparator  │ ─► │  • GitHub Action       │
│  • multi-dim scorers   │    │  • drift analyzer       │    │  • PR comment bot      │
│    (exact + judge)     │    │  • HTML report          │    │  • merge-block on      │
│  • SQLite persistence  │    │  • Slack webhook        │    │    CRITICAL            │
└────────────────────────┘    └─────────────────────────┘    └────────────────────────┘
```

Three layers, each independently testable:

1. **Eval Engine** — `EvalRunner` fans out to your target model with a bounded `asyncio.Semaphore`, scores each output along two dimensions (deterministic exact match + LLM-as-judge), and persists the run as a single transaction in SQLite.
2. **Reporting Layer** — `compare_runs` produces a typed `ComparisonReport` with per-case verdicts (regression / improvement / unchanged / new / removed). The HTML renderer turns that into a self-contained, color-coded report; the Slack module turns it into a webhook payload; the drift analyzer rolls a configurable window of historical runs into a single score.
3. **CI/CD Integration** — A turnkey GitHub Actions workflow (`.github/workflows/eval.yml`) runs on every PR that touches `prompts/` or `golden/`, posts/updates a single PR comment, and exits with code `2` when the report is `CRITICAL` so the merge gate fails.

Prompts are versioned YAML in `/prompts`. The golden dataset is JSONL or YAML in `/golden`. Both are reviewable in PRs by non-engineers.

---

## Quickstart

```bash
git clone https://github.com/metehanulusoy/model-regression-detection
cd model-regression-detection
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export MRD_OPENAI_API_KEY="sk-..."

mrd run \
  --prompt customer_support \
  --dataset golden/customer_support.jsonl \
  --baseline auto \
  --report-dir reports
```

You'll get something like:

```
Run customer_support-v1-9f4a8b2c01: avg_composite=0.875 errors=0 cost=$0.0021
HTML report: reports/customer_support-v1-9f4a8b2c01.html
Comparison: severity=warning Δ=-3.20pp reg=1 imp=0 unc=7
```

Open the HTML report for a side-by-side per-case diff. Run `mrd drift --prompt customer_support` to see the rolling-average drift across recent runs.

### Without an OpenAI key

The whole test suite mocks the OpenAI HTTP layer with `respx`. To verify the pipeline shape without spending money:

```bash
pytest
```

---

## Configuration

All settings are driven by env vars (or a `.env` file). Defaults match the project's stated targets: 50–100 cases per PR, < 2 min per run, < $0.50 per PR.

| Variable | Default | Purpose |
|---|---|---|
| `MRD_OPENAI_API_KEY` | _(required)_ | OpenAI API key. Read by both target and judge calls. |
| `MRD_TARGET_MODEL` | `gpt-4o-mini` | Model under test. |
| `MRD_JUDGE_MODEL` | `gpt-4o` | Model used by the LLM-as-judge scorer. |
| `MRD_DB_PATH` | `./mrd.sqlite3` | SQLite file. Persisted between runs and CI invocations. |
| `MRD_PROMPTS_DIR` | `./prompts` | Where versioned prompt YAML lives. |
| `MRD_GOLDEN_DIR` | `./golden` | Where the golden datasets live. |
| `MRD_MAX_CONCURRENCY` | `10` | Bounded by `asyncio.Semaphore`. |
| `MRD_REQUEST_TIMEOUT_S` | `60` | Per-request timeout for OpenAI calls. |
| `MRD_MAX_RETRIES` | `3` | Exponential backoff on 429/5xx and network errors. |
| `MRD_WARNING_DELTA_PCT` | `3.0` | Aggregate composite drop above which the report is `WARNING`. |
| `MRD_CRITICAL_DELTA_PCT` | `8.0` | Aggregate composite drop above which the report is `CRITICAL` (blocks merge). |
| `MRD_DRIFT_WINDOW` | `7` | Rolling-average window size for drift detection. |
| `MRD_SLACK_WEBHOOK_URL` | _(optional)_ | Slack incoming webhook. If set, every comparison posts an alert. |
| `MRD_GITHUB_TOKEN` | _(optional)_ | Used by the PR comment bot. The Action passes `GITHUB_TOKEN` automatically. |
| `MRD_GITHUB_REPOSITORY` | _(optional)_ | `owner/repo`. Auto-populated in CI. |
| `MRD_GITHUB_PR_NUMBER` | _(optional)_ | Pull request number. Auto-populated in CI. |

---

## Prompt format

```yaml
# prompts/customer_support.yaml
version: v1
description: Classifies a support email into one of four labels.
temperature: 0.0
max_output_tokens: 32
system: |
  You are an email classifier. Reply with EXACTLY ONE label from:
  billing, bug_report, feature_request, general_inquiry.
user_template: |
  Subject: ${subject}
  Body: ${input}
  Label:
```

For prompts with multiple historical versions, switch to a directory:

```
prompts/customer_support/
├── v1.yaml
├── v2.yaml
└── v3.yaml          # latest is auto-selected
```

`render_user(...)` uses Python's `string.Template` substitution, so `${var}` placeholders are replaced from each test case's `input` plus any `metadata` keys.

---

## Golden dataset format

JSONL is the canonical format because it diffs cleanly in PRs. Each line is one `TestCase`:

```jsonl
{"id": "case-001", "input": "Charged twice this month", "expected": "billing", "expected_label": "billing", "metadata": {"subject": "Duplicate charge"}}
```

YAML and JSON list formats are also accepted. `id` must be stable across runs — that's how the comparator pairs baseline and candidate cases. Renaming an `id` shows up as one `REMOVED` and one `NEW`.

---

## Scoring

Every case gets three numbers in `[0, 1]`:

- **`exact_match`** — 1.0 if the (normalized) output equals `expected`, or contains `expected_label` as a substring; else 0.0. Cheap, deterministic, catches format breaks.
- **`judge_score`** — A second LLM grades the candidate against the expected answer with a JSON-only prompt. Robust to paraphrase. Skipped if `--no-judge` or if the case has no `expected`.
- **`composite`** — Weighted blend. Default is 0.7 × judge + 0.3 × exact, configurable via `CaseScores.from_parts(judge_weight=...)`.

Aggregate severity is computed in **percentage points** of the composite (so a 4pp drop means the average composite went from, e.g., 0.90 to 0.86 — not a 4% relative change). This is intentional: developers reason about absolute thresholds more reliably than relative ones at a glance.

---

## Drift detection

Per-PR comparison catches sudden cliffs. Drift catches the slow leak. After each run is persisted, `mrd drift --prompt <name>` (and the GitHub Action automatically) compares the latest `avg_composite` to the rolling mean of the prior `MRD_DRIFT_WINDOW − 1` runs. The same `WARNING` / `CRITICAL` thresholds apply, so a 4pp drift over a week is treated the same as a 4pp drop in one PR.

---

## GitHub Actions

`.github/workflows/eval.yml` wires the full pipeline. Set two repository secrets:

- `OPENAI_API_KEY`
- `SLACK_WEBHOOK_URL` _(optional)_

The workflow runs on every PR that touches `prompts/`, `golden/`, or `src/`, comments (or updates) a single PR comment with the diff summary, uploads the HTML report as an artifact, and exits non-zero on `CRITICAL` so branch protection blocks the merge.

---

## CLI reference

```text
mrd run         Execute an eval run, persist it, optionally compare to baseline.
mrd compare     Compare two existing run_ids and emit HTML/Slack/PR comment.
mrd drift       Print the rolling-drift report for a prompt.
```

`mrd run --baseline auto` automatically pulls the most recent run for the same prompt name. Use `--baseline <run_id>` to pin against a specific historical run.

---

## Project standards

- **Type-safe.** `mypy --strict` with the `pydantic.mypy` plugin. No untyped public API.
- **Tested.** `pytest` with `respx`-mocked HTTP, asyncio mode, ≥ 80% line+branch coverage enforced in CI.
- **Linted.** `ruff` for style and correctness (`E`, `F`, `B`, `UP`, `SIM`, `RUF`, `ASYNC`).
- **Logged.** `structlog` JSON output to stderr, with stable event names (`eval.run.start`, `eval.case.error`, …).
- **Conventional commits.** Squash-merged PRs.

---

## Architecture decision records

- [`docs/ADR-001-modular-monolith.md`](docs/ADR-001-modular-monolith.md) — Why a single Python package instead of microservices.
- [`docs/ADR-002-scoring.md`](docs/ADR-002-scoring.md) — Why exact-match + LLM-as-judge instead of, e.g., embedding similarity or RAGAS.
- [`docs/ADR-003-thresholds-in-pp.md`](docs/ADR-003-thresholds-in-pp.md) — Why severity is computed in percentage points of the composite, not relative changes.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Acknowledgments

Built collaboratively with **Claude Opus 4.7** as a co-author. The architecture and code review benefited from Anthropic's models throughout.

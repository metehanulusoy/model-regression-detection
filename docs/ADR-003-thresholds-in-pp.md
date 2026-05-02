# ADR-003: Severity thresholds expressed in percentage points, not relative percentages

**Status:** Accepted

## Context

When a prompt edit drops average composite from 0.85 to 0.80, is that a:

- 5 percentage-point drop (absolute), or
- ~5.9 % relative drop?

Both are correct; the report has to pick a single number to threshold against. The spec says "warning > 3 %, critical > 8 %", which doesn't disambiguate.

## Decision

`avg_composite_delta_pct` and the warning/critical thresholds are **percentage points** of the composite score. A baseline of 0.90 → candidate of 0.86 is reported as `-4.00pp` and triggers `WARNING` at the default threshold of `3.0`.

## Consequences

- **Thresholds are stable across prompts.** A prompt that lives at composite 0.95 and another at composite 0.65 use the same 3pp / 8pp thresholds. With relative percentages, the lower-quality prompt would be much more sensitive (a 3 % relative drop from 0.65 is only 0.02pp absolute — basically noise).
- **Reviewers reason about it more reliably.** "We lost 4 percentage points" is concrete; "a 4.7 % relative regression" needs a calculator.
- **The CI exit code is binary at CRITICAL.** WARNING is intentionally non-blocking — humans see the warning in the PR comment / Slack message and can decide. CRITICAL exits with code 2 and trips the merge gate.

**Trade-offs:**

- Teams running prompts with very low absolute composite (say, 0.40 because the task is genuinely hard) will find absolute thresholds too loose. They can either tune `MRD_WARNING_DELTA_PCT` / `MRD_CRITICAL_DELTA_PCT` per repo or weight the scorers differently. We document the knob in the README.
- Internally we still convert to a relative percentage in some Slack copy. The variable name is `avg_composite_delta_pct` and the print uses `pp` to make the unit explicit; we accept that mild internal naming/format inconsistency.

## Alternatives considered

- **Relative percentages.** Rejected for the prompt-stability reason above.
- **Z-score against the rolling window.** Tempting, and we may add it as an alternate severity mode later. But it's hard to communicate to a casual PR reviewer ("3.2 standard deviations below mean") and the rolling window is short enough that variance estimates are noisy.

## Revisit if

- Multiple teams independently tune the thresholds in the same direction; the default is wrong.
- We grow into running thousands of prompts and absolute thresholds become per-prompt toil.

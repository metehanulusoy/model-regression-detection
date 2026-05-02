# ADR-001: Modular monolith, not microservices

**Status:** Accepted

## Context

The original spec describes three layers — Eval Engine, Reporting Layer, CI/CD Integration — and a target end-to-end runtime under two minutes per PR with 50–100 cases. The natural design question: do those layers want to be separate services, or is one Python package enough?

## Decision

Ship a single Python package (`model_regression`) with three internal subpackages (`eval/`, `reporting/`, `ci/`). The CLI wires them together. There is no message queue, no inter-service HTTP, no separate worker pool.

## Consequences

**Why this is the right choice for now:**

- **Latency budget is small (< 2 min).** Adding even a single network hop between layers eats meaningful time and adds failure modes (queue backpressure, broker outages) that the use case doesn't justify.
- **State is tiny.** Per run we store ~50 case rows; even a year's history fits in a single SQLite file. There's nothing for a Postgres or warehouse to do that SQLite can't.
- **Operational simplicity matters more than horizontal scale.** The whole pipeline runs inside one CI job. Microservices would force a separate deploy story for every layer.
- **Testability is better.** Each subpackage is independently importable and unit-testable. We get most of the benefit of service boundaries — clear interfaces, no leakage — without paying the deployment tax.

**Trade-offs:**

- A team that wants a hosted dashboard with always-on history will outgrow SQLite. The DB layer is intentionally narrow (`RunStore`) so migrating to Postgres is a < 200-line change.
- We can't independently scale the judge calls separately from the target calls. That would matter at 10K+ cases per PR; we're targeting 100.
- The eval engine, the reporter, and the CI integration share one process. If any one of them is buggy enough to crash, the whole run fails. We mitigate by keeping each layer pure (no global state, no shared mutable singletons).

## Alternatives considered

- **Microservices (FastAPI + Celery + Redis).** Rejected: ~5× the operational surface for no real benefit at the target scale.
- **Plugin-style framework (drop-in scorer modules, pluggable reporters).** Deferred: today's scoring needs are well-served by two strategies; we'll add a plugin interface when a third or fourth scorer materializes.

## Revisit if

- A user reports that a CI run regularly takes more than 5 minutes.
- Run history grows past a few hundred MB on disk.
- A second product wants to share the eval engine independently of the reporting layer.

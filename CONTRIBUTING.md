# Contributing

Contributions welcome — bug reports, feature requests, PRs.

## Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make check
```

`make check` runs `ruff` + `mypy --strict` + `pytest --cov`. CI runs the same matrix on Python 3.11 and 3.12; PRs are blocked until coverage stays at or above **80 %**.

## Conventions

- **Conventional commits.** Examples: `feat(eval): add custom scorer plugin`, `fix(reporting): escape HTML in case outputs`, `docs(readme): clarify drift behavior`.
- **No unannotated public API.** `mypy --strict` will reject it.
- **Tests are mandatory** for any new public function. Unit tests should not hit the network — use `respx` to mock the OpenAI HTTP layer.
- **Golden dataset edits go in their own PR** with rationale, separate from prompt or code changes. The eval pipeline relies on `id` stability, so renames are first-class events.

## Triage of LLM-related failures

Please attach:
1. The exact prompt YAML.
2. A minimal reproducible `golden/` JSONL (`mrd run --prompt ... --dataset ...`).
3. The HTML report (or a screenshot).

PRs that include a regression test for the bug they fix will land much faster.

## Releasing

This repo is small enough to use plain `git tag` releases. Bump `version` in `pyproject.toml` in the same commit, tag `vX.Y.Z`, and push.

## Code of conduct

Be kind. Disagreements about technical direction are welcome; personal attacks are not.

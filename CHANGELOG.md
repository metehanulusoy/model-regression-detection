# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Initial release

### Added
- Async eval runner (`EvalRunner`) with bounded concurrency and graceful per-case error handling.
- Multi-dimensional scorer: deterministic exact match plus JSON-only LLM-as-judge.
- Versioned prompt manager: single-file or directory-of-versions YAML format.
- SQLite persistence layer (`RunStore`) with WAL mode and atomic per-run writes.
- Per-case comparator producing typed `ComparisonReport` with regression / improvement / unchanged / new / removed verdicts.
- 7-run rolling drift analyzer (`analyze_drift`).
- Self-contained HTML diff report with color-coded per-case panel.
- Slack incoming-webhook dispatcher (`build_slack_message`, `post_slack_alert`).
- GitHub Actions integration: PR comment bot (`build_pr_comment`, `post_or_update_pr_comment`) and merge-blocking exit codes.
- Click-based CLI: `mrd run`, `mrd compare`, `mrd drift`.
- 66-test pytest suite, 80%+ coverage gate, mypy strict, ruff lint.
- GitHub Actions workflows: `test.yml` (matrix py3.11 / py3.12) and `eval.yml` (turnkey regression gate).
- Dockerfile, docker-compose.yml, Makefile, three architecture decision records.

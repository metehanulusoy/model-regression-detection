from __future__ import annotations

import httpx
import pytest

from model_regression.ci.github import (
    EXIT_CRITICAL,
    EXIT_OK,
    build_pr_comment,
    in_github_actions,
    post_or_update_pr_comment,
    severity_to_exit_code,
)
from model_regression.models import Severity
from model_regression.reporting.comparator import compare_runs

from .conftest import make_run


def test_severity_to_exit_code_blocks_only_critical() -> None:
    assert severity_to_exit_code(Severity.OK) == EXIT_OK
    assert severity_to_exit_code(Severity.WARNING) == EXIT_OK  # do NOT block on warning
    assert severity_to_exit_code(Severity.CRITICAL) == EXIT_CRITICAL


def test_in_github_actions_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert in_github_actions() is True
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    assert in_github_actions() is False
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert in_github_actions() is False


def test_pr_comment_truncates_long_outputs() -> None:
    baseline = make_run(run_id="b", avg=0.95, n_cases=2)
    candidate = make_run(run_id="c", avg=0.50, n_cases=2)
    candidate.cases[0].output = "x" * 500
    report = compare_runs(baseline=baseline, candidate=candidate)
    md = build_pr_comment(report, max_diffs_shown=5)
    assert "…" in md or len(md) < 5000


def _patch_client(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.pop("timeout", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr("model_regression.ci.github.httpx.Client", factory)


def test_post_or_update_pr_comment_creates_when_no_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.method == "POST":
            return httpx.Response(201, json={"id": 42, "body": "created"})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    result = post_or_update_pr_comment(
        repository="owner/repo", pr_number=10, body="hi", token="t"
    )
    assert result["id"] == 42
    assert any(m == "POST" for m, _ in seen_calls)


def test_post_or_update_pr_comment_updates_when_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 99,
                        "body": "<!-- model-regression-detection: do-not-edit -->\n old",
                    }
                ],
            )
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": 99, "body": "updated"})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    result = post_or_update_pr_comment(
        repository="owner/repo", pr_number=10, body="new", token="t"
    )
    assert result["id"] == 99
    assert "PATCH" in seen_methods


def test_post_or_update_requires_owner_slash_repo() -> None:
    with pytest.raises(ValueError, match="owner/repo"):
        post_or_update_pr_comment(repository="bare", pr_number=1, body="x", token="t")


def test_post_or_update_requires_token() -> None:
    with pytest.raises(ValueError, match="token"):
        post_or_update_pr_comment(repository="owner/repo", pr_number=1, body="x", token="")

from __future__ import annotations

from pathlib import Path

import pytest

from model_regression.config import load_settings


def test_defaults_apply_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in list(_env_keys()):
        monkeypatch.delenv(k, raising=False)
    s = load_settings()
    assert s.target_model == "gpt-4o-mini"
    assert s.judge_model == "gpt-4o"
    assert s.warning_delta_pct == 3.0
    assert s.critical_delta_pct == 8.0


def test_overrides_take_precedence(tmp_path: Path) -> None:
    s = load_settings(target_model="gpt-4.1-mini", db_path=tmp_path / "x.sqlite3")
    assert s.target_model == "gpt-4.1-mini"
    assert s.db_path == tmp_path / "x.sqlite3"


def test_critical_must_be_at_least_warning() -> None:
    with pytest.raises(ValueError, match="critical_delta_pct"):
        load_settings(warning_delta_pct=10.0, critical_delta_pct=5.0)


def test_max_concurrency_bounded() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_settings(max_concurrency=0)


def _env_keys() -> list[str]:
    return [
        "MRD_OPENAI_API_KEY",
        "MRD_TARGET_MODEL",
        "MRD_JUDGE_MODEL",
        "MRD_DB_PATH",
        "MRD_WARNING_DELTA_PCT",
        "MRD_CRITICAL_DELTA_PCT",
    ]

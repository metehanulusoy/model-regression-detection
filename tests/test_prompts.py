from __future__ import annotations

from pathlib import Path

import pytest

from model_regression.prompts import PromptManager


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_single_file_prompt(tmp_path: Path) -> None:
    _write(
        tmp_path / "cls.yaml",
        "version: v3\nsystem: hi\nuser_template: ${input}\ntemperature: 0.1\nmax_output_tokens: 64\n",
    )
    pm = PromptManager(tmp_path)
    p = pm.load("cls")
    assert p.version == "v3"
    assert p.system == "hi"
    assert p.render_user({"input": "world"}) == "world"
    assert p.temperature == 0.1
    assert p.max_output_tokens == 64


def test_load_versioned_directory_picks_latest(tmp_path: Path) -> None:
    _write(tmp_path / "cls" / "v1.yaml", "system: a\nuser_template: ${input}\n")
    _write(tmp_path / "cls" / "v2.yaml", "system: b\nuser_template: ${input}\n")
    pm = PromptManager(tmp_path)
    p = pm.load("cls")
    assert p.version == "v2"
    assert p.system == "b"


def test_load_specific_version(tmp_path: Path) -> None:
    _write(tmp_path / "cls" / "v1.yaml", "system: a\nuser_template: ${input}\n")
    _write(tmp_path / "cls" / "v2.yaml", "system: b\nuser_template: ${input}\n")
    pm = PromptManager(tmp_path)
    p = pm.load("cls", version="v1")
    assert p.system == "a"


def test_render_user_raises_on_missing_var(tmp_path: Path) -> None:
    _write(tmp_path / "cls.yaml", "system: x\nuser_template: ${input} ${missing}\n")
    pm = PromptManager(tmp_path)
    p = pm.load("cls")
    with pytest.raises(KeyError):
        p.render_user({"input": "ok"})


def test_fingerprint_changes_with_content(tmp_path: Path) -> None:
    _write(tmp_path / "a.yaml", "system: x\nuser_template: ${input}\n")
    _write(tmp_path / "b.yaml", "system: y\nuser_template: ${input}\n")
    pm = PromptManager(tmp_path)
    assert pm.load("a").fingerprint() != pm.load("b").fingerprint()

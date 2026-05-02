from __future__ import annotations

from pathlib import Path

import pytest

from model_regression.dataset import load_dataset


def test_load_json_list(tmp_path: Path) -> None:
    p = tmp_path / "cases.json"
    p.write_text('[{"id":"a","input":"x","expected":"y"}]', encoding="utf-8")
    cases = load_dataset(p)
    assert cases[0].id == "a"


def test_load_json_rejects_top_level_object(tmp_path: Path) -> None:
    p = tmp_path / "cases.json"
    p.write_text('{"id":"a"}', encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        load_dataset(p)


def test_load_yaml_rejects_top_level_object(tmp_path: Path) -> None:
    p = tmp_path / "cases.yaml"
    p.write_text("id: a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        load_dataset(p)


def test_load_dataset_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path / "nope.jsonl")

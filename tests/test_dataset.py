from __future__ import annotations

from pathlib import Path

import pytest

from model_regression.dataset import load_dataset


def test_load_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    p.write_text(
        '{"id": "a", "input": "x", "expected": "y"}\n'
        '{"id": "b", "input": "x2", "expected_label": "billing"}\n',
        encoding="utf-8",
    )
    cases = load_dataset(p)
    assert [c.id for c in cases] == ["a", "b"]
    assert cases[0].expected == "y"
    assert cases[1].expected_label == "billing"


def test_load_yaml(tmp_path: Path) -> None:
    p = tmp_path / "cases.yaml"
    p.write_text(
        "- id: a\n  input: hello\n  expected: world\n"
        "- id: b\n  input: foo\n  expected_label: bar\n",
        encoding="utf-8",
    )
    cases = load_dataset(p)
    assert len(cases) == 2


def test_load_rejects_unknown_format(tmp_path: Path) -> None:
    p = tmp_path / "cases.txt"
    p.write_text("nope")
    with pytest.raises(ValueError, match="Unsupported"):
        load_dataset(p)


def test_load_jsonl_reports_line_number_on_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "cases.jsonl"
    p.write_text('{"id":"a","input":"x"}\n{not json}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=":2:"):
        load_dataset(p)

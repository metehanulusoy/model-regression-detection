"""Golden-dataset loader.

Supports JSONL (one TestCase JSON per line) and YAML (a top-level list of TestCases).
The format is intentionally minimal — anything richer (per-case tags, severity
weights) belongs in the TestCase.metadata dict, which is opaque here.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .models import TestCase


def load_dataset(path: Path) -> list[TestCase]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return _load_jsonl(path)
    if suffix in {".yaml", ".yml"}:
        return _load_yaml(path)
    if suffix == ".json":
        return _load_json(path)
    raise ValueError(f"Unsupported dataset format: {suffix}")


def _load_jsonl(path: Path) -> list[TestCase]:
    cases: list[TestCase] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{i}: invalid JSON ({exc})") from exc
            cases.append(TestCase.model_validate(obj))
    return cases


def _load_json(path: Path) -> list[TestCase]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: top-level JSON must be a list of test cases")
    return [TestCase.model_validate(d) for d in data]


def _load_yaml(path: Path) -> list[TestCase]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: top-level YAML must be a list of test cases")
    return [TestCase.model_validate(d) for d in data]

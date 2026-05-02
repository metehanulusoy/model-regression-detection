from __future__ import annotations

import time
from pathlib import Path

import pytest

from model_regression.db import RunStore

from .conftest import make_run


def test_save_and_get_run_roundtrips(tmp_db_path: Path) -> None:
    store = RunStore(tmp_db_path)
    run = make_run(run_id="r1", avg=0.9)
    store.save_run(run)
    loaded = store.get_run("r1")
    assert loaded is not None
    assert loaded.metadata.run_id == "r1"
    assert loaded.summary.avg_composite == pytest.approx(0.9)
    assert len(loaded.cases) == len(run.cases)


def test_latest_run_returns_most_recent(tmp_db_path: Path) -> None:
    store = RunStore(tmp_db_path)
    store.save_run(make_run(run_id="old", avg=0.7))
    time.sleep(0.01)
    store.save_run(make_run(run_id="new", avg=0.8))
    latest = store.latest_run("test")
    assert latest is not None
    assert latest.metadata.run_id == "new"


def test_latest_run_with_before_excludes_self(tmp_db_path: Path) -> None:
    store = RunStore(tmp_db_path)
    store.save_run(make_run(run_id="r1", avg=0.7))
    time.sleep(0.01)
    store.save_run(make_run(run_id="r2", avg=0.8))
    prior = store.latest_run("test", before_run_id="r2")
    assert prior is not None
    assert prior.metadata.run_id == "r1"


def test_drift_window_returns_chronological_order(tmp_db_path: Path) -> None:
    store = RunStore(tmp_db_path)
    for i, avg in enumerate([0.6, 0.7, 0.8, 0.9]):
        store.save_run(make_run(run_id=f"r{i}", avg=avg))
        time.sleep(0.01)
    points = store.drift_window("test", n=3)
    assert [p.run_id for p in points] == ["r1", "r2", "r3"]
    assert [p.avg_composite for p in points] == pytest.approx([0.7, 0.8, 0.9])

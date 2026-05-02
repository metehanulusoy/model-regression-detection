from __future__ import annotations

from model_regression.logging import configure, get_logger


def test_configure_is_idempotent() -> None:
    configure("INFO")
    configure("DEBUG")  # second call is a no-op
    log = get_logger("test")
    log.info("hello", x=1)  # smoke: no exception


def test_configure_accepts_lowercase_level() -> None:
    configure("warning")
    log = get_logger("test")
    log.warning("ok")

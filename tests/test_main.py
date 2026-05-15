"""Tests for src/main.py — sample entry point."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

import main


@pytest.fixture(autouse=True)
def _isolate_root_logger() -> Iterator[None]:
    """Snapshot root logger state and restore after each test.

    `main._configure_logging()` mutates global state (adds handlers,
    sets level). Without this fixture, that state leaks across tests
    in the same session.
    """
    root = logging.getLogger()
    initial_handlers = list(root.handlers)
    initial_level = root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in initial_handlers:
        root.addHandler(handler)
    root.setLevel(initial_level)


def test_stdout_filter_passes_below_warning() -> None:
    """DEBUG/INFO records should pass the stdout filter."""
    for level in (logging.DEBUG, logging.INFO):
        record = logging.LogRecord(
            name='test', level=level, pathname='', lineno=0,
            msg='', args=(), exc_info=None,
        )
        assert main._stdout_filter(record) is True


def test_stdout_filter_blocks_warning_and_above() -> None:
    """WARNING/ERROR/CRITICAL records should be blocked from stdout."""
    for level in (logging.WARNING, logging.ERROR, logging.CRITICAL):
        record = logging.LogRecord(
            name='test', level=level, pathname='', lineno=0,
            msg='', args=(), exc_info=None,
        )
        assert main._stdout_filter(record) is False


def test_configure_logging_attaches_two_handlers() -> None:
    """Root logger gets two StreamHandler-s (stdout + stderr) after configure."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    main._configure_logging()
    assert len(root.handlers) == 2
    assert all(isinstance(h, logging.StreamHandler) for h in root.handlers)


def test_main_logs_hello(caplog: pytest.LogCaptureFixture) -> None:
    """main() emits the INFO greeting."""
    with caplog.at_level(logging.INFO):
        main.main()
    assert any(
        'Hello from efactory!' in record.message
        for record in caplog.records
    )

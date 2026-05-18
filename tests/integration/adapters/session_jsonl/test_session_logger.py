"""Integration: FilesystemJsonlSessionLogger через tmp_path (T010)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from adapters.outbound.session_jsonl.session_logger import (
    FilesystemJsonlSessionLogger,
)
from ports.outbound.session_logger import SessionEventStatus

if TYPE_CHECKING:
    import pytest


def _read_lines(log_path: Path) -> list[dict]:
    text = log_path.read_text(encoding='utf-8')
    return [json.loads(line) for line in text.strip().split('\n') if line]


async def test_log_event_writes_jsonl_with_required_fields(tmp_path: Path) -> None:
    logger = FilesystemJsonlSessionLogger(tmp_path, '20260518-120000-aabbcc')

    await logger.log_event(
        'project.create',
        status=SessionEventStatus.OK,
        project='demo',
        payload={'name': 'demo'},
    )

    records = _read_lines(logger.log_path)
    assert len(records) == 1
    record = records[0]
    assert record['event'] == 'project.create'
    assert record['status'] == 'ok'
    assert record['project'] == 'demo'
    assert record['payload'] == {'name': 'demo'}
    assert 'ts' in record
    assert 'error' not in record


async def test_log_event_writes_error_field(tmp_path: Path) -> None:
    logger = FilesystemJsonlSessionLogger(tmp_path, 'sess')

    await logger.log_event(
        'decision.add',
        status=SessionEventStatus.ERROR,
        project='ghost',
        payload={'project': 'ghost', 'title': 'x'},
        error="ProjectNotFoundError: Project 'ghost' not found",
    )

    record = _read_lines(logger.log_path)[0]
    assert record['status'] == 'error'
    assert record['error'].startswith('ProjectNotFoundError')


async def test_log_event_creates_session_dir_lazily(tmp_path: Path) -> None:
    logger = FilesystemJsonlSessionLogger(tmp_path, 'lazy')
    assert not (tmp_path / 'lazy').exists()

    await logger.log_event(
        'project.list', status=SessionEventStatus.OK,
    )

    assert (tmp_path / 'lazy' / 'log.jsonl').is_file()


async def test_log_event_appends_multiple_records(tmp_path: Path) -> None:
    logger = FilesystemJsonlSessionLogger(tmp_path, 'multi')

    for i in range(3):
        await logger.log_event(
            'project.list',
            status=SessionEventStatus.OK,
            payload={'i': i},
        )

    records = _read_lines(logger.log_path)
    assert len(records) == 3
    assert [r['payload']['i'] for r in records] == [0, 1, 2]


async def test_log_event_omits_none_fields_keeps_record_compact(tmp_path: Path) -> None:
    logger = FilesystemJsonlSessionLogger(tmp_path, 'minimal')

    await logger.log_event('project.list', status=SessionEventStatus.OK)

    record = _read_lines(logger.log_path)[0]
    assert set(record.keys()) == {'ts', 'event', 'status'}


async def test_log_event_handles_cyrillic_payload(tmp_path: Path) -> None:
    logger = FilesystemJsonlSessionLogger(tmp_path, 'unicode')

    await logger.log_event(
        'decision.add',
        status=SessionEventStatus.OK,
        project='усилитель',
        payload={'title': 'Выбор SE-топологии'},
    )

    raw = logger.log_path.read_text(encoding='utf-8')
    assert 'усилитель' in raw  # ensure_ascii=False
    assert 'Выбор SE-топологии' in raw


async def test_log_event_does_not_raise_on_io_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Resolved #8: best-effort, основной CLI flow не прерывается."""
    logger = FilesystemJsonlSessionLogger(tmp_path, 'fail')

    def _broken_mkdir(*_args: object, **_kwargs: object) -> None:
        msg = 'simulated disk full'
        raise OSError(msg)

    monkeypatch.setattr(Path, 'mkdir', _broken_mkdir)

    # Не должно бросать.
    await logger.log_event('project.list', status=SessionEventStatus.OK)

    captured = capsys.readouterr()
    assert 'session-log: failed' in captured.err
    assert 'simulated disk full' in captured.err

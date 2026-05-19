"""Unit-тесты на SchematicSnapshot (T004b Phase 1 atomic multi-edit)."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.schematic_snapshot import SchematicSnapshot


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding='utf-8')


def test_commit_keeps_modifications(tmp_path: Path) -> None:
    sch = tmp_path / 'x.kicad_sch'
    _write(sch, 'original')

    with SchematicSnapshot(sch) as snap:
        _write(sch, 'modified')
        snap.commit()

    assert sch.read_text(encoding='utf-8') == 'modified'


def test_no_commit_rolls_back_on_normal_exit(tmp_path: Path) -> None:
    sch = tmp_path / 'x.kicad_sch'
    _write(sch, 'original')

    with SchematicSnapshot(sch):
        _write(sch, 'modified')
        # без commit() — rollback на exit

    assert sch.read_text(encoding='utf-8') == 'original'


def test_exception_during_block_rolls_back(tmp_path: Path) -> None:
    sch = tmp_path / 'x.kicad_sch'
    _write(sch, 'original')

    with pytest.raises(RuntimeError):
        with SchematicSnapshot(sch) as snap:
            _write(sch, 'modified')
            snap.commit()       # commit before exception ↓
            raise RuntimeError('boom')

    # Если exception ПОСЛЕ commit — rollback всё равно (защита от частичного
    # commit). Этот же кейс.
    assert sch.read_text(encoding='utf-8') == 'original'


def test_exception_before_commit_rolls_back(tmp_path: Path) -> None:
    sch = tmp_path / 'x.kicad_sch'
    _write(sch, 'original')

    with pytest.raises(ValueError):
        with SchematicSnapshot(sch):
            _write(sch, 'modified')
            raise ValueError('mid-edit failure')

    assert sch.read_text(encoding='utf-8') == 'original'


def test_backup_cleanup_after_commit(tmp_path: Path) -> None:
    """После successful commit — нет orphan .bak файлов рядом с schematic."""
    sch = tmp_path / 'x.kicad_sch'
    _write(sch, 'original')

    with SchematicSnapshot(sch) as snap:
        _write(sch, 'modified')
        snap.commit()

    bak_files = list(tmp_path.glob('.x.kicad_sch.snapshot.*.bak'))
    assert bak_files == []

"""Unit-тесты `KicadLockDetector` (T026 Phase 1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.outbound.schematic_kicad.lock_detector import KicadLockDetector

if TYPE_CHECKING:
    from pathlib import Path


def test_no_lock_file_reports_not_held(tmp_path: Path) -> None:
    active = tmp_path / 'se_amp.kicad_sch'
    active.write_text('(kicad_sch ...)\n', encoding='utf-8')
    assert KicadLockDetector().is_held_by_kicad(active) is False


def test_lock_file_present_reports_held(tmp_path: Path) -> None:
    active = tmp_path / 'se_amp.kicad_sch'
    active.write_text('(kicad_sch ...)\n', encoding='utf-8')
    (tmp_path / '~se_amp.kicad_sch.lck').write_text(
        '{"hostname":"h","username":"u"}', encoding='utf-8',
    )
    assert KicadLockDetector().is_held_by_kicad(active) is True


def test_active_missing_no_lock_reports_not_held(tmp_path: Path) -> None:
    """Сценарий первой записи — active не существует, lock тоже."""
    assert KicadLockDetector().is_held_by_kicad(tmp_path / 'fresh.kicad_sch') is False


def test_active_missing_but_lock_present_reports_held(tmp_path: Path) -> None:
    """Stale-lock без active — встречается; detector работает по lock-existence."""
    (tmp_path / '~ghost.kicad_sch.lck').write_text(
        '{"hostname":"h","username":"u"}', encoding='utf-8',
    )
    assert KicadLockDetector().is_held_by_kicad(tmp_path / 'ghost.kicad_sch') is True

"""Unit-тесты для `render_doctor_report` (T036)."""

from __future__ import annotations

from adapters.inbound.cli.doctor_renderer import render_doctor_report
from domain.doctor import (
    CATEGORY_GUI,
    CATEGORY_MOUNTS,
    CATEGORY_RUNTIME,
    CATEGORY_TOOLCHAIN,
    CheckStatus,
    DoctorCheck,
    DoctorReport,
)


def _ok(name: str, detail: str, category: str) -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status=CheckStatus.OK,
        detail=detail,
        category=category,
    )


def test_render_emits_header() -> None:
    out = render_doctor_report(DoctorReport(checks=()))
    assert 'efactory doctor' in out


def test_render_groups_in_canonical_order() -> None:
    report = DoctorReport(
        checks=(
            _ok('ulimit', '1024', CATEGORY_RUNTIME),
            _ok('kicad-cli', '9.0.0', CATEGORY_TOOLCHAIN),
            _ok('display', ':0', CATEGORY_GUI),
            _ok('/workspace', 'dir, writable', CATEGORY_MOUNTS),
        ),
    )
    out = render_doctor_report(report)
    idx_tc = out.find('Toolchain versions')
    idx_gui = out.find('GUI passthrough')
    idx_mounts = out.find('Mounts')
    idx_runtime = out.find('Runtime constraints')
    assert -1 < idx_tc < idx_gui < idx_mounts < idx_runtime


def test_render_status_markers() -> None:
    report = DoctorReport(
        checks=(
            DoctorCheck(
                name='good',
                status=CheckStatus.OK,
                detail='ok',
                category=CATEGORY_TOOLCHAIN,
            ),
            DoctorCheck(
                name='soso',
                status=CheckStatus.WARN,
                detail='warn',
                category=CATEGORY_TOOLCHAIN,
            ),
            DoctorCheck(
                name='bad',
                status=CheckStatus.FAIL,
                detail='fail',
                category=CATEGORY_TOOLCHAIN,
            ),
        ),
    )
    out = render_doctor_report(report)
    assert '[OK]' in out
    assert '[WARN]' in out
    assert '[FAIL]' in out


def test_render_summary_counts() -> None:
    report = DoctorReport(
        checks=(
            DoctorCheck(
                name='a',
                status=CheckStatus.OK,
                detail='-',
                category=CATEGORY_TOOLCHAIN,
            ),
            DoctorCheck(
                name='b',
                status=CheckStatus.OK,
                detail='-',
                category=CATEGORY_TOOLCHAIN,
            ),
            DoctorCheck(
                name='c',
                status=CheckStatus.WARN,
                detail='-',
                category=CATEGORY_TOOLCHAIN,
            ),
            DoctorCheck(
                name='d',
                status=CheckStatus.FAIL,
                detail='-',
                category=CATEGORY_TOOLCHAIN,
            ),
        ),
    )
    out = render_doctor_report(report)
    assert 'Summary: 2 OK, 1 WARN, 1 FAIL' in out
    assert 'worst=FAIL' in out


def test_render_unknown_category_uses_raw_name() -> None:
    report = DoctorReport(
        checks=(
            _ok('custom', 'value', 'experimental'),
        ),
    )
    out = render_doctor_report(report)
    assert '## experimental' in out

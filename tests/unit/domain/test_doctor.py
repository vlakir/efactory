"""Unit-тесты для domain VOs `efactory doctor` (T036)."""

from __future__ import annotations

import pytest

from domain.doctor import (
    CANONICAL_CATEGORY_ORDER,
    CATEGORY_GUI,
    CATEGORY_HOST,
    CATEGORY_MOUNTS,
    CATEGORY_RUNTIME,
    CATEGORY_TOOLCHAIN,
    CheckStatus,
    DoctorCheck,
    DoctorReport,
)


def _check(
    name: str = 'python',
    status: CheckStatus = CheckStatus.OK,
    detail: str = '3.13.0',
    category: str = CATEGORY_TOOLCHAIN,
) -> DoctorCheck:
    return DoctorCheck(
        name=name,
        status=status,
        detail=detail,
        category=category,
    )


def test_check_status_members() -> None:
    assert {s.value for s in CheckStatus} == {'OK', 'WARN', 'FAIL'}


def test_check_status_ordering() -> None:
    # Канонический порядок «severity»: FAIL > WARN > OK.
    assert CheckStatus.FAIL.severity > CheckStatus.WARN.severity
    assert CheckStatus.WARN.severity > CheckStatus.OK.severity


def test_canonical_category_order_contains_five_groups() -> None:
    assert CANONICAL_CATEGORY_ORDER == (
        CATEGORY_TOOLCHAIN,
        CATEGORY_GUI,
        CATEGORY_MOUNTS,
        CATEGORY_RUNTIME,
        CATEGORY_HOST,
    )


def test_doctor_check_minimal() -> None:
    c = _check()
    assert c.name == 'python'
    assert c.status == CheckStatus.OK
    assert c.detail == '3.13.0'
    assert c.category == CATEGORY_TOOLCHAIN


def test_doctor_check_empty_name_rejected() -> None:
    with pytest.raises(ValueError, match='at least 1'):
        _check(name='')


def test_doctor_check_empty_category_rejected() -> None:
    with pytest.raises(ValueError, match='at least 1'):
        _check(category='')


def test_doctor_check_frozen() -> None:
    c = _check()
    with pytest.raises(ValueError, match='[Ff]rozen|immutable'):
        c.status = CheckStatus.FAIL  # type: ignore[misc]


def test_doctor_report_empty_worst_status_is_ok() -> None:
    r = DoctorReport(checks=())
    assert r.worst_status == CheckStatus.OK


def test_doctor_report_all_ok() -> None:
    r = DoctorReport(checks=(_check(), _check(name='git', detail='2.43')))
    assert r.worst_status == CheckStatus.OK


def test_doctor_report_warn_dominates_ok() -> None:
    r = DoctorReport(
        checks=(
            _check(),
            _check(name='image', status=CheckStatus.WARN, detail='32 days old'),
        ),
    )
    assert r.worst_status == CheckStatus.WARN


def test_doctor_report_fail_dominates_warn() -> None:
    r = DoctorReport(
        checks=(
            _check(status=CheckStatus.WARN, detail='old'),
            _check(
                name='ngspice',
                status=CheckStatus.FAIL,
                detail='not found',
            ),
        ),
    )
    assert r.worst_status == CheckStatus.FAIL


def test_doctor_report_iter_categories_canonical_order() -> None:
    r = DoctorReport(
        checks=(
            _check(name='ulimit', category=CATEGORY_RUNTIME, detail='1024'),
            _check(name='kicad-cli', category=CATEGORY_TOOLCHAIN, detail='9.0'),
            _check(name='display', category=CATEGORY_GUI, detail=':0'),
        ),
    )
    cats = [cat for cat, _ in r.iter_categories()]
    assert cats == [CATEGORY_TOOLCHAIN, CATEGORY_GUI, CATEGORY_RUNTIME]


def test_doctor_report_iter_categories_unknown_at_end() -> None:
    r = DoctorReport(
        checks=(
            _check(name='custom', category='zzz_unknown', detail='?'),
            _check(name='python', category=CATEGORY_TOOLCHAIN, detail='3.13'),
        ),
    )
    cats = [cat for cat, _ in r.iter_categories()]
    assert cats == [CATEGORY_TOOLCHAIN, 'zzz_unknown']


def test_doctor_report_iter_categories_stable_within_group() -> None:
    a = _check(name='a', category=CATEGORY_TOOLCHAIN, detail='1')
    b = _check(name='b', category=CATEGORY_TOOLCHAIN, detail='2')
    c = _check(name='c', category=CATEGORY_TOOLCHAIN, detail='3')
    r = DoctorReport(checks=(a, b, c))
    [(_, checks)] = list(r.iter_categories())
    assert [c.name for c in checks] == ['a', 'b', 'c']


def test_doctor_report_frozen() -> None:
    r = DoctorReport(checks=())
    with pytest.raises(ValueError, match='[Ff]rozen|immutable'):
        r.checks = (_check(),)  # type: ignore[misc]

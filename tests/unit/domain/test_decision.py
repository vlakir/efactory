"""Domain: Decision aggregate (T099)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.decision import (
    Decision,
    DecisionRef,
    DecisionStatus,
)


def test_decision_minimum_fields() -> None:
    d = Decision(
        id='D001',
        title='Выбор SE-топологии',
        date=date(2026, 5, 17),
        status=DecisionStatus.ACCEPTED,
        summary='SE даёт меньше искажений',
        rationale='Для наушников достаточно мощности SE-каскада',
    )
    assert d.id == 'D001'
    assert d.status is DecisionStatus.ACCEPTED
    assert d.evidence is None
    assert d.session is None


def test_decision_with_evidence_relative_path() -> None:
    d = Decision(
        id='D002',
        title='Increase C2',
        date=date(2026, 5, 18),
        status=DecisionStatus.ACCEPTED,
        summary='C2 = 1uF',
        rationale='Wider bass response',
        evidence=Path('sim/ac_final.json'),
        session=Path('sessions/session_003.json'),
    )
    assert d.evidence == Path('sim/ac_final.json')


def test_decision_evidence_absolute_path_rejected() -> None:
    with pytest.raises(ValidationError, match='must be relative'):
        Decision(
            id='D003',
            title='Test',
            date=date(2026, 5, 18),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
            evidence=Path('/absolute/path.json'),
        )


def test_decision_session_absolute_path_rejected() -> None:
    with pytest.raises(ValidationError, match='must be relative'):
        Decision(
            id='D004',
            title='Test',
            date=date(2026, 5, 18),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
            session=Path('/absolute/sessions/x.json'),
        )


@pytest.mark.parametrize(
    'bad_id',
    ['', 'foo', 'D', 'd001', '001', 'D00A', 'D-1'],
)
def test_decision_id_format_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        Decision(
            id=bad_id,
            title='x',
            date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
        )


@pytest.mark.parametrize('good_id', ['D001', 'D010', 'D999', 'D1000', 'D12345'])
def test_decision_id_format_accepted(good_id: str) -> None:
    d = Decision(
        id=good_id,
        title='x',
        date=date(2026, 5, 17),
        status=DecisionStatus.ACCEPTED,
        summary='s',
        rationale='r',
    )
    assert d.id == good_id


def test_decision_title_path_traversal_rejected() -> None:
    """ProjectName validator (T092) переиспользован — `..` запрещён в title."""
    with pytest.raises(ValidationError):
        Decision(
            id='D005',
            title='../etc',
            date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='r',
        )


def test_decision_empty_summary_rejected() -> None:
    with pytest.raises(ValidationError):
        Decision(
            id='D006',
            title='x',
            date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='',
            rationale='r',
        )


def test_decision_empty_rationale_rejected() -> None:
    with pytest.raises(ValidationError):
        Decision(
            id='D007',
            title='x',
            date=date(2026, 5, 17),
            status=DecisionStatus.ACCEPTED,
            summary='s',
            rationale='',
        )


def test_decision_is_frozen() -> None:
    d = Decision(
        id='D008',
        title='x',
        date=date(2026, 5, 17),
        status=DecisionStatus.ACCEPTED,
        summary='s',
        rationale='r',
    )
    with pytest.raises(ValidationError):
        d.status = DecisionStatus.REJECTED  # type: ignore[misc]


def test_decision_ref_minimum_fields() -> None:
    ref = DecisionRef(
        id='D001',
        date=date(2026, 5, 17),
        summary='s',
        rationale='r',
    )
    assert ref.id == 'D001'
    assert ref.evidence is None


def test_decision_ref_with_evidence_relative() -> None:
    ref = DecisionRef(
        id='D002',
        date=date(2026, 5, 18),
        summary='s',
        rationale='r',
        evidence=Path('sim/x.json'),
    )
    assert ref.evidence == Path('sim/x.json')


def test_decision_ref_evidence_absolute_rejected() -> None:
    with pytest.raises(ValidationError, match='must be relative'):
        DecisionRef(
            id='D003',
            date=date(2026, 5, 18),
            summary='s',
            rationale='r',
            evidence=Path('/abs/x.json'),
        )

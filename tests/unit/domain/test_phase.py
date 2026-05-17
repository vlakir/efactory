"""Phase VO — инварианты переходов, поведение методов и transitioned_to."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.phase import Phase, PhaseName, PhaseStatus


def test_phase_default_is_pending_with_no_timestamps() -> None:
    phase = Phase(name=PhaseName.SCHEMATIC)

    assert phase.status is PhaseStatus.PENDING
    assert phase.started_at is None
    assert phase.completed_at is None


def test_phase_is_frozen() -> None:
    phase = Phase(name=PhaseName.SCHEMATIC)

    with pytest.raises(ValidationError):
        phase.status = PhaseStatus.DONE  # type: ignore[misc]


def test_phase_start_transitions_pending_to_in_progress_and_sets_started_at() -> None:
    phase = Phase(name=PhaseName.SCHEMATIC)

    started = phase.start()

    assert started.status is PhaseStatus.IN_PROGRESS
    assert started.started_at is not None
    assert started.completed_at is None
    assert phase.status is PhaseStatus.PENDING


@pytest.mark.parametrize(
    'bad_status',
    [PhaseStatus.IN_PROGRESS, PhaseStatus.DONE, PhaseStatus.SKIPPED],
)
def test_phase_start_from_non_pending_raises(bad_status: PhaseStatus) -> None:
    phase = Phase(name=PhaseName.SCHEMATIC, status=bad_status)

    with pytest.raises(ValueError, match='Cannot start'):
        phase.start()


def test_phase_complete_after_start_sets_done_and_completed_at() -> None:
    phase = Phase(name=PhaseName.SCHEMATIC).start()

    completed = phase.complete()

    assert completed.status is PhaseStatus.DONE
    assert completed.started_at is not None
    assert completed.completed_at is not None


@pytest.mark.parametrize(
    'bad_status',
    [PhaseStatus.PENDING, PhaseStatus.DONE, PhaseStatus.SKIPPED],
)
def test_phase_complete_from_non_in_progress_raises(
    bad_status: PhaseStatus,
) -> None:
    phase = Phase(name=PhaseName.SCHEMATIC, status=bad_status)

    with pytest.raises(ValueError, match='Cannot complete'):
        phase.complete()


def test_phase_skip_from_pending_sets_skipped_without_timestamps() -> None:
    phase = Phase(name=PhaseName.MAGNETICS)

    skipped = phase.skip()

    assert skipped.status is PhaseStatus.SKIPPED
    assert skipped.started_at is None
    assert skipped.completed_at is None


def test_phase_skip_from_in_progress_keeps_started_at_no_completed_at() -> None:
    phase = Phase(name=PhaseName.SCHEMATIC).start()

    skipped = phase.skip()

    assert skipped.status is PhaseStatus.SKIPPED
    assert skipped.started_at == phase.started_at
    assert skipped.completed_at is None


@pytest.mark.parametrize(
    'bad_status',
    [PhaseStatus.DONE, PhaseStatus.SKIPPED],
)
def test_phase_skip_from_done_or_skipped_raises(bad_status: PhaseStatus) -> None:
    phase = Phase(name=PhaseName.SCHEMATIC, status=bad_status)

    with pytest.raises(ValueError, match='Cannot skip'):
        phase.skip()


def test_phase_unskip_from_skipped_resets_timestamps_to_none() -> None:
    started_skipped = Phase(name=PhaseName.SCHEMATIC).start().skip()
    assert started_skipped.started_at is not None  # sanity

    unskipped = started_skipped.unskip()

    assert unskipped.status is PhaseStatus.PENDING
    assert unskipped.started_at is None
    assert unskipped.completed_at is None


@pytest.mark.parametrize(
    'bad_status',
    [PhaseStatus.PENDING, PhaseStatus.IN_PROGRESS, PhaseStatus.DONE],
)
def test_phase_unskip_from_non_skipped_raises(bad_status: PhaseStatus) -> None:
    phase = Phase(name=PhaseName.SCHEMATIC, status=bad_status)

    with pytest.raises(ValueError, match='Cannot unskip'):
        phase.unskip()


# --- transitioned_to: матрица C2 из спеки T097 ---


@pytest.mark.parametrize(
    ('current', 'target', 'expected'),
    [
        (PhaseStatus.PENDING, PhaseStatus.IN_PROGRESS, PhaseStatus.IN_PROGRESS),
        (PhaseStatus.IN_PROGRESS, PhaseStatus.DONE, PhaseStatus.DONE),
        (PhaseStatus.PENDING, PhaseStatus.SKIPPED, PhaseStatus.SKIPPED),
        (PhaseStatus.IN_PROGRESS, PhaseStatus.SKIPPED, PhaseStatus.SKIPPED),
        (PhaseStatus.SKIPPED, PhaseStatus.PENDING, PhaseStatus.PENDING),
    ],
)
def test_transitioned_to_allows_valid_transitions(
    current: PhaseStatus, target: PhaseStatus, expected: PhaseStatus,
) -> None:
    phase = Phase(name=PhaseName.PCB, status=current)

    moved = phase.transitioned_to(target)

    assert moved.status is expected


@pytest.mark.parametrize(
    ('current', 'target'),
    [
        # noop в любом статусе → ValueError
        (PhaseStatus.PENDING, PhaseStatus.PENDING),
        (PhaseStatus.IN_PROGRESS, PhaseStatus.IN_PROGRESS),
        (PhaseStatus.DONE, PhaseStatus.DONE),
        (PhaseStatus.SKIPPED, PhaseStatus.SKIPPED),
        # прыжки через статус
        (PhaseStatus.PENDING, PhaseStatus.DONE),
        (PhaseStatus.IN_PROGRESS, PhaseStatus.PENDING),
        # reopen done запрещён в T097 (Resolved #3)
        (PhaseStatus.DONE, PhaseStatus.IN_PROGRESS),
        (PhaseStatus.DONE, PhaseStatus.PENDING),
        (PhaseStatus.DONE, PhaseStatus.SKIPPED),
        # unskip только в pending
        (PhaseStatus.SKIPPED, PhaseStatus.IN_PROGRESS),
        (PhaseStatus.SKIPPED, PhaseStatus.DONE),
    ],
)
def test_transitioned_to_rejects_forbidden_transitions(
    current: PhaseStatus, target: PhaseStatus,
) -> None:
    phase = Phase(name=PhaseName.PCB, status=current)

    with pytest.raises(ValueError, match='Forbidden phase transition'):
        phase.transitioned_to(target)

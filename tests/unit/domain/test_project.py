"""Tests for domain.Project — Pydantic aggregate root."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from domain.phase import Phase, PhaseName, PhaseStatus
from domain.project import Project, ProjectStatus


def test_project_creates_with_required_fields() -> None:
    project = Project(name='my-amp', path=Path('/projects/my-amp'))

    assert project.name == 'my-amp'
    assert project.path == Path('/projects/my-amp')
    assert isinstance(project.id, UUID)
    assert project.created_at.tzinfo is not None
    assert project.updated_at.tzinfo is not None


def test_project_updated_at_close_to_created_at_on_fresh_create() -> None:
    """On fresh create оба timestamp'а — `now()`; разница в микросекунды."""
    project = Project(name='p', path=Path('/p'))

    delta = abs((project.updated_at - project.created_at).total_seconds())
    assert delta < 1.0


def test_project_uuid_unique_per_instance() -> None:
    p1 = Project(name='a', path=Path('/p/a'))
    p2 = Project(name='b', path=Path('/p/b'))

    assert p1.id != p2.id


def test_project_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Project(name='', path=Path('/p/x'))


def test_project_rejects_whitespace_only_name() -> None:
    with pytest.raises(ValidationError):
        Project(name='   ', path=Path('/p/x'))


@pytest.mark.parametrize(
    'bad_name',
    [
        '..',
        '.',
        '../etc',
        '../../etc/passwd',
        '..\\etc',
        '/absolute',
        '/etc/passwd',
        'a/b',
        'a\\b',
        'name/with/slashes',
        'name\\with\\backslashes',
        'trailing/',
        '\\leading',
        './rel',
    ],
)
def test_project_rejects_path_traversal_in_name(bad_name: str) -> None:
    """Имена не должны позволять выйти за пределы projects_root.

    Critical для DeleteProject (T090): shutil.rmtree(projects_root /
    name) с name='../../etc' разнесёт хост-FS. Defence в domain,
    чтобы все use cases (create, delete, любой будущий) защищены
    автоматически.
    """
    with pytest.raises(ValidationError):
        Project(name=bad_name, path=Path('/p/x'))


@pytest.mark.parametrize(
    'good_name',
    [
        'my-amp',
        'se_amp',
        'pre.amp.v2',
        'SE-OPT-6P14P',
        'project1',
        'a',
        'тёплый-усилитель',
    ],
)
def test_project_accepts_human_names(good_name: str) -> None:
    project = Project(name=good_name, path=Path('/p/x'))
    assert project.name == good_name


# --- Phases default + canonical order (T097) ---


def test_default_phases_are_six_pending_in_canonical_order() -> None:
    project = Project(name='p', path=Path('/p'))

    expected = (
        PhaseName.SCHEMATIC,
        PhaseName.SIMULATION,
        PhaseName.PCB,
        PhaseName.MAGNETICS,
        PhaseName.ENCLOSURE,
        PhaseName.DOCUMENTATION,
    )
    assert tuple(p.name for p in project.phases) == expected
    assert all(p.status is PhaseStatus.PENDING for p in project.phases)


def test_phases_with_wrong_length_rejected() -> None:
    with pytest.raises(ValidationError, match='exactly 6 phases'):
        Project(
            name='p',
            path=Path('/p'),
            phases=(Phase(name=PhaseName.SCHEMATIC),),
        )


def test_phases_with_wrong_order_rejected() -> None:
    wrong_order = (
        Phase(name=PhaseName.SIMULATION),
        Phase(name=PhaseName.SCHEMATIC),
        Phase(name=PhaseName.PCB),
        Phase(name=PhaseName.MAGNETICS),
        Phase(name=PhaseName.ENCLOSURE),
        Phase(name=PhaseName.DOCUMENTATION),
    )
    with pytest.raises(ValidationError, match='canonical order'):
        Project(name='p', path=Path('/p'), phases=wrong_order)


# --- Derived Project.status ---


def test_status_idea_when_all_phases_pending() -> None:
    project = Project(name='p', path=Path('/p'))
    assert project.status is ProjectStatus.IDEA


def _project_with_phase_done(*names: PhaseName) -> Project:
    project = Project(name='p', path=Path('/p'))
    for name in names:
        project.transition_phase(name, PhaseStatus.IN_PROGRESS)
        project.transition_phase(name, PhaseStatus.DONE)
    return project


@pytest.mark.parametrize(
    ('done_phases', 'expected'),
    [
        ((PhaseName.SCHEMATIC,), ProjectStatus.SCHEMATIC),
        (
            (PhaseName.SCHEMATIC, PhaseName.SIMULATION),
            ProjectStatus.SIMULATED,
        ),
        (
            (PhaseName.SCHEMATIC, PhaseName.SIMULATION, PhaseName.PCB),
            ProjectStatus.PCB_DESIGNED,
        ),
        (
            (
                PhaseName.SCHEMATIC,
                PhaseName.SIMULATION,
                PhaseName.PCB,
                PhaseName.MAGNETICS,
            ),
            ProjectStatus.MAGNETICS_DONE,
        ),
        (
            (
                PhaseName.SCHEMATIC,
                PhaseName.SIMULATION,
                PhaseName.PCB,
                PhaseName.MAGNETICS,
                PhaseName.ENCLOSURE,
            ),
            ProjectStatus.ENCLOSURE_DONE,
        ),
        (
            (
                PhaseName.SCHEMATIC,
                PhaseName.SIMULATION,
                PhaseName.PCB,
                PhaseName.MAGNETICS,
                PhaseName.ENCLOSURE,
                PhaseName.DOCUMENTATION,
            ),
            ProjectStatus.PRODUCTION_READY,
        ),
    ],
)
def test_status_progresses_with_each_done_phase(
    done_phases: tuple[PhaseName, ...], expected: ProjectStatus,
) -> None:
    project = _project_with_phase_done(*done_phases)
    assert project.status is expected


def test_status_chain_breaks_on_gap() -> None:
    """Прыжок через фазу — chain прерывается, status остаётся idea.

    pcb done + simulation pending → status = idea (Resolved #4).
    """
    project = Project(name='p', path=Path('/p'))
    project.transition_phase(PhaseName.PCB, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.PCB, PhaseStatus.DONE)

    assert project.status is ProjectStatus.IDEA


def test_status_skipped_counts_as_closed_for_chain() -> None:
    """Skipped считается «закрытой» фазой → chain не прерывается."""
    project = Project(name='p', path=Path('/p'))
    project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.DONE)
    project.transition_phase(PhaseName.SIMULATION, PhaseStatus.SKIPPED)
    project.transition_phase(PhaseName.PCB, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.PCB, PhaseStatus.DONE)

    assert project.status is ProjectStatus.PCB_DESIGNED


def test_status_production_ready_with_skipped_middle_phases() -> None:
    """Гибкий скоуп §4.1: skipped magnetics/enclosure не блокируют production_ready."""
    project = Project(name='p', path=Path('/p'))
    project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.DONE)
    project.transition_phase(PhaseName.SIMULATION, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.SIMULATION, PhaseStatus.DONE)
    project.transition_phase(PhaseName.PCB, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.PCB, PhaseStatus.DONE)
    project.transition_phase(PhaseName.MAGNETICS, PhaseStatus.SKIPPED)
    project.transition_phase(PhaseName.ENCLOSURE, PhaseStatus.SKIPPED)
    project.transition_phase(PhaseName.DOCUMENTATION, PhaseStatus.IN_PROGRESS)
    project.transition_phase(PhaseName.DOCUMENTATION, PhaseStatus.DONE)

    assert project.status is ProjectStatus.PRODUCTION_READY


# --- rename + transition_phase aggregate methods ---


def test_rename_updates_name_via_validator() -> None:
    project = Project(name='old-name', path=Path('/p'))

    project.rename('new-name')

    assert project.name == 'new-name'


def test_rename_rejects_invalid_name() -> None:
    project = Project(name='ok', path=Path('/p'))

    with pytest.raises(ValidationError):
        project.rename('../etc')

    assert project.name == 'ok'


def test_transition_phase_in_place_updates_target_phase() -> None:
    project = Project(name='p', path=Path('/p'))

    project.transition_phase(PhaseName.PCB, PhaseStatus.IN_PROGRESS)

    pcb_phase = project.phases[2]
    assert pcb_phase.name is PhaseName.PCB
    assert pcb_phase.status is PhaseStatus.IN_PROGRESS
    assert pcb_phase.started_at is not None


def test_transition_phase_propagates_value_error_on_forbidden() -> None:
    project = Project(name='p', path=Path('/p'))

    with pytest.raises(ValueError, match='Forbidden phase transition'):
        project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.DONE)

"""Tests for domain.Project — Pydantic aggregate root."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from domain.project import Project, ProjectStatus


def test_project_creates_with_required_fields() -> None:
    project = Project(name='my-amp', path=Path('/projects/my-amp'))

    assert project.name == 'my-amp'
    assert project.path == Path('/projects/my-amp')
    assert isinstance(project.id, UUID)
    assert project.created_at.tzinfo is not None
    assert project.status is ProjectStatus.CREATED


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

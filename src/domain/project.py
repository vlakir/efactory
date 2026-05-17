"""Project — корневой агрегат предметной области efactory."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


class ProjectStatus(StrEnum):
    CREATED = 'created'


def _validate_name(value: str) -> str:
    if not value.strip():
        msg = 'Project name must not be empty or whitespace-only'
        raise ValueError(msg)
    if value in {'.', '..'}:
        msg = 'Project name must not be "." or ".."'
        raise ValueError(msg)
    if '/' in value or '\\' in value:
        msg = 'Project name must not contain path separators ("/" or "\\")'
        raise ValueError(msg)
    return value


ProjectName = Annotated[str, AfterValidator(_validate_name)]


class Project(BaseModel):
    """Aggregate root: один проект РЭА (схема, плата, корпус, документация)."""

    model_config = ConfigDict(frozen=False)

    id: UUID = Field(default_factory=uuid4)
    name: ProjectName
    path: Path
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: ProjectStatus = ProjectStatus.CREATED

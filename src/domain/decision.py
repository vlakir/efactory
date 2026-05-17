"""Decision — aggregate журнала проектных решений (T099, CONCEPT §4.4)."""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from domain._name import validate_name as _validate_title_name

_ID_RE = re.compile(r'^D\d{3,}$')


def _validate_id(value: str) -> str:
    if not _ID_RE.match(value):
        msg = f"Decision id must match 'D' + 3+ digits, got '{value}'"
        raise ValueError(msg)
    return value


def _validate_relative_path(value: Path | None) -> Path | None:
    if value is not None and value.is_absolute():
        msg = f'Path must be relative to project, got absolute: {value}'
        raise ValueError(msg)
    return value


DecisionId = Annotated[str, AfterValidator(_validate_id)]
"""Формат `D###` (минимум 3 цифры; D1000+ допустимы)."""

DecisionTitle = Annotated[str, AfterValidator(_validate_title_name)]
"""Path-safe заголовок (T092 валидатор: не пустой, без `/\\`, не `..`)."""

RelativePath = Annotated[Path | None, AfterValidator(_validate_relative_path)]


class DecisionStatus(StrEnum):
    PROPOSED = 'proposed'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'


class Decision(BaseModel):
    """Полная сущность решения (детали хранятся в markdown файле)."""

    model_config = ConfigDict(frozen=True, extra='ignore')

    id: DecisionId
    title: DecisionTitle
    date: date
    status: DecisionStatus
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: RelativePath = None
    session: RelativePath = None


class DecisionRef(BaseModel):
    """Компактная запись для manifest YAML (`project.yaml → decisions`)."""

    model_config = ConfigDict(frozen=True, extra='ignore')

    id: DecisionId
    date: date
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: RelativePath = None
    session: RelativePath = None

    @classmethod
    def from_decision(cls, decision: Decision) -> DecisionRef:
        return cls(
            id=decision.id,
            date=decision.date,
            summary=decision.summary,
            rationale=decision.rationale,
            evidence=decision.evidence,
            session=decision.session,
        )

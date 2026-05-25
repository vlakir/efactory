"""
SimResult — externalized JSON snapshot одного запуска симуляции (T016).

Канонический путь хранения — `<PROJECT_ROOT>/.efactory/sim-results/
<TIMESTAMP>-<analysis>.json`, schema_version=1. SimResult читается
SessionStart hook'ом для динамического project context (T016 Phase A)
и записывается `FileSystemSimResults` adapter'ом (Phase B), который
вызывают use cases с симуляциями (Phase C, начиная с `sim_run`).

Domain-уровень — без знания о FS layout или формате JSON-сериализации:
оба находятся на уровне adapter'а.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SIM_RESULTS_SCHEMA_VERSION: Literal[1] = 1

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class AnalysisType(StrEnum):
    """
    Виды симуляций, оборачиваемых в SimResult.

    Open list — `OTHER` для use cases, которые ещё не получили
    отдельного значения. Расширение — отдельный PR (BACKLOG).
    """

    TRAN = 'tran'
    AC = 'ac'
    DC = 'dc'
    OP = 'op'
    FOUR = 'four'
    THD = 'thd'
    FEM_FIELD = 'fem_field'
    LEAKAGE = 'leakage'
    BRACKET_SHEET_METAL = 'bracket_sheet_metal'
    OTHER = 'other'


class SimResult(BaseModel):
    """JSON snapshot одного запуска симуляции для записи в проект."""

    model_config = _FROZEN

    schema_version: Literal[1] = SIM_RESULTS_SCHEMA_VERSION
    timestamp: str
    analysis_type: AnalysisType
    source_file: str
    tool: str
    tool_version: str | None = None
    duration_seconds: Annotated[float, Field(ge=0)]
    summary: str
    metrics: dict[str, Any] | None = None
    artefacts: tuple[str, ...] = ()

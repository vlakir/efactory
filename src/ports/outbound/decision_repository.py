"""DecisionRepository — outbound port для markdown-сериализации решений (T099)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.decision import Decision


class DecisionNotFoundError(Exception):
    """
    `decisions/D###_*.md` для запрошенного id отсутствует.

    Контрактное исключение порта: бросается реализацией `load()`.
    """


class DecisionInvalidError(Exception):
    """
    Markdown файл повреждён или не парсится по фиксированному шаблону.

    Контрактное исключение порта.
    """


class DecisionRepository(Protocol):
    """
    Markdown как primary storage decisions (T099, CONCEPT §4.4).

    Каждое решение — отдельный `<project>/decisions/D###_<slug>.md`.
    Reference в `project.yaml → decisions:` — индекс, синхронизируется
    через `ReindexProjects`.
    """

    async def save(self, project_path: Path, decision: Decision) -> Path: ...

    async def load(self, project_path: Path, decision_id: str) -> Decision: ...

    async def list_all(self, project_path: Path) -> list[Decision]: ...

    async def next_id(self, project_path: Path) -> str: ...

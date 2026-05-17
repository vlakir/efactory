"""ProjectFileRepository — outbound-порт файловых операций над проектом."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class ProjectFileRepository(Protocol):
    """
    Чтение/запись файлов проекта на диске.

    На Walking Skeleton — только создание директории нового проекта.
    Дополнительные методы (чтение `.kicad_pro`, запись YAML/JSON, list)
    добавляются по мере появления use cases.
    """

    async def create_project_directory(self, path: Path) -> None: ...

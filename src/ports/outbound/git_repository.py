"""GitRepository — outbound port для VCS-инициализации проекта (T010)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class GitUnavailableError(Exception):
    """
    `git` CLI отсутствует на PATH.

    Контрактное исключение порта: бросается реализацией
    `init_with_initial_commit()`. CreateProject ловит этот случай,
    логирует warning и продолжает без VCS (проект всё равно создан).
    """


class GitOperationError(Exception):
    """
    `git` subprocess завершился ненулевым кодом.

    Контрактное исключение порта: например, отказ в доступе к
    каталогу, повреждение working tree, или другая ошибка git.
    """


class GitRepository(Protocol):
    """Минимальный VCS-протокол для Phase 1a: только initial commit."""

    async def init_with_initial_commit(
        self,
        project_path: Path,
        message: str,
    ) -> None: ...

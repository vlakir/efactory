"""
DeleteProject — use case (T157 filesystem-first refactor).

Удалить project directory из FS. Без SQL: directory existence —
единственный sign-of-presence.

При отсутствии каталога — `ProjectNotFoundError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.get_project import ProjectNotFoundError

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.project_file_repository import ProjectFileRepository


async def delete_project(
    *,
    name: str,
    projects_root: Path,
    file_repo: ProjectFileRepository,
) -> None:
    path = projects_root / name
    if not path.is_dir():
        raise ProjectNotFoundError(name)
    await file_repo.remove_project_directory(path)


__all__ = ['ProjectNotFoundError', 'delete_project']

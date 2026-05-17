"""
DeleteProject — use case: удалить проект из метаданных и из FS.

Порядок операций: get → delete DB → delete FS. Если адаптер БД упадёт,
проект остаётся в системе целиком — пользователь может повторить
вызов. Если упадёт FS-операция, метаданных уже нет (можно проверить
через `project show`), а каталог остался как orphan — это
относительно безопасное состояние, его легко вычистить вручную или
будущей `cleanup`-командой.

При отсутствии проекта поднимается `ProjectNotFoundError` (тот же
класс, что у `GetProject` T089 — общий для read-and-act use cases).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.get_project import ProjectNotFoundError, get_project

if TYPE_CHECKING:
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository


async def delete_project(
    *,
    name: str,
    repo: MetadataRepository,
    file_repo: ProjectFileRepository,
) -> None:
    project = await get_project(name=name, repo=repo)
    await repo.delete_by_name(name)
    await file_repo.remove_project_directory(project.path)


__all__ = ['ProjectNotFoundError', 'delete_project']

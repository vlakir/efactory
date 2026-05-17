"""
DeleteProject — use case: удалить проект из метаданных и из FS.

Порядок операций: SQL lookup (для path) → delete DB → delete FS.
Если adapter БД упадёт, проект остаётся в системе целиком — повтор
вызова безопасен. Если упадёт FS-операция, метаданных уже нет, а
каталог остался как orphan — безопасное состояние, чистится
вручную / будущим `cleanup`.

В отличие от Get/Update use case'ов, delete НЕ читает manifest:
нам нужна только `path` для `remove_project_directory`, а сам
manifest исчезнет вместе с папкой. Это и аккуратно работает в
случае отсутствующего manifest'а (desync до T098 → delete всё равно
очистит SQL-строку и пустую папку).

При отсутствии проекта поднимается `ProjectNotFoundError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.get_project import ProjectNotFoundError

if TYPE_CHECKING:
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository


async def delete_project(
    *,
    name: str,
    repo: MetadataRepository,
    file_repo: ProjectFileRepository,
) -> None:
    sql_row = await repo.get_by_name(name)
    if sql_row is None:
        raise ProjectNotFoundError(name)
    await repo.delete_by_name(name)
    await file_repo.remove_project_directory(sql_row.path)


__all__ = ['ProjectNotFoundError', 'delete_project']

"""
Application-уровень errors для manifest-primary write-path (T098).

`IndexPersistenceError` — partial-failure: manifest записан, SQL upsert
упал. Manifest = truth, SQL stale; reindex восстановит индекс.

`ProjectManifestMissingError` — SQL знает о проекте, но manifest на
диске отсутствует (например, удалён вручную). Use case'ы Get/Update
ловят и сигналят пользователю.

Оба сообщения содержат явную подсказку `reindex`, чтобы CLI просто
форвардил `str(err)` в stderr и пользователь видел recovery path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class IndexPersistenceError(Exception):
    """SQL upsert упал после успешного manifest.save (T098 C2)."""

    def __init__(self, project_name: str, cause: Exception) -> None:
        super().__init__(
            f"Failed to update SQL index for project '{project_name}': {cause}. "
            f'Manifest is saved; run `efactory project reindex` to recover.',
        )
        self.project_name = project_name
        self.__cause__ = cause


class ProjectManifestMissingError(Exception):
    """SQL знает о проекте, но `project.yaml` на диске отсутствует."""

    def __init__(self, project_name: str, project_path: Path) -> None:
        super().__init__(
            f"Manifest not found at {project_path} for project '{project_name}'. "
            f'Run `efactory project reindex` or restore the file from backup.',
        )
        self.project_name = project_name
        self.project_path = project_path


class DecisionPersistenceError(Exception):
    """Decision markdown сохранён, manifest sync упал (T099 N3)."""

    def __init__(self, project_name: str, decision_id: str, cause: Exception) -> None:
        super().__init__(
            f'Decision {decision_id} saved to markdown for project '
            f"'{project_name}'; failed to sync manifest: {cause}. "
            f'Run `efactory project reindex` to recover.',
        )
        self.project_name = project_name
        self.decision_id = decision_id
        self.__cause__ = cause

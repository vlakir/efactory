"""FilesystemProjectManifestRepository — YAML-сериализация Project (T098)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Final

import yaml
from pydantic import ValidationError

from domain.project import Project

if TYPE_CHECKING:
    from pathlib import Path


MANIFEST_FILENAME: Final = 'project.yaml'
SCHEMA_VERSION: Final = 1


class ManifestNotFoundError(Exception):
    """`project.yaml` отсутствует в каталоге проекта."""


class ManifestInvalidError(Exception):
    """`project.yaml` повреждён или не проходит Pydantic-валидацию."""


class FilesystemProjectManifestRepository:
    async def save(self, project: Project) -> None:
        manifest_path = project.path / MANIFEST_FILENAME
        # mode='json' → JSON-сериализуемые типы (UUID/datetime/Path → str);
        # PyYAML safe_dump UUID/datetime сам не умеет, через mode='json'
        # получаем чистые str. exclude={'path'} — портативность (W1):
        # путь определяется расположением файла, не вшит в YAML.
        data = project.model_dump(mode='json', exclude={'path'})
        ordered: dict[str, Any] = {'schema_version': SCHEMA_VERSION, **data}
        text = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True)

        def _atomic_write() -> None:
            tmp_path = manifest_path.with_suffix(manifest_path.suffix + '.tmp')
            tmp_path.write_text(text, encoding='utf-8')
            tmp_path.replace(manifest_path)

        await asyncio.to_thread(_atomic_write)

    async def load(self, project_path: Path) -> Project:
        manifest_path = project_path / MANIFEST_FILENAME

        def _read_and_parse() -> Project:
            if not manifest_path.is_file():
                msg = f'Manifest not found at {manifest_path}'
                raise ManifestNotFoundError(msg)
            try:
                raw = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
            except yaml.YAMLError as exc:
                msg = f'Invalid manifest at {manifest_path}: YAML syntax — {exc}'
                raise ManifestInvalidError(msg) from exc
            if not isinstance(raw, dict):
                msg = (
                    f'Invalid manifest at {manifest_path}: '
                    f'expected mapping, got {type(raw).__name__}'
                )
                raise ManifestInvalidError(msg)
            # status — computed_field (read-only, не валидируется на input);
            # schema_version — meta-поле адаптера. Оба удаляем перед validate.
            raw.pop('status', None)
            raw.pop('schema_version', None)
            raw['path'] = project_path  # подставляем from arg (W1)
            try:
                return Project.model_validate(raw)
            except ValidationError as exc:
                msg = f'Invalid manifest at {manifest_path}: {exc}'
                raise ManifestInvalidError(msg) from exc

        return await asyncio.to_thread(_read_and_parse)

    async def exists(self, project_path: Path) -> bool:
        manifest_path = project_path / MANIFEST_FILENAME
        return await asyncio.to_thread(manifest_path.is_file)

    async def discover_all(self, storage_root: Path) -> list[Path]:
        def _scan() -> list[Path]:
            matches = storage_root.glob(f'*/{MANIFEST_FILENAME}')
            return sorted(m.parent for m in matches)

        return await asyncio.to_thread(_scan)

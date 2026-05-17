"""Integration tests for FilesystemProjectManifestRepository (T098)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from adapters.outbound.manifest_yaml import (
    FilesystemProjectManifestRepository,
    ManifestInvalidError,
    ManifestNotFoundError,
)
from domain.phase import PhaseName, PhaseStatus
from domain.project import Project, ProjectStatus

if TYPE_CHECKING:
    from pathlib import Path


# --- Helpers ---


def _make_project(path: Path, name: str = 'demo') -> Project:
    path.mkdir(parents=True, exist_ok=True)
    return Project(name=name, path=path)


# --- save ---


async def test_save_writes_project_yaml_file(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()

    await repo.save(project)

    manifest = tmp_path / 'demo' / 'project.yaml'
    assert manifest.is_file()


async def test_save_uses_safe_yaml_human_readable(tmp_path: Path) -> None:
    """`sort_keys=False` + `allow_unicode=True`; читабельный YAML, не JSON-like."""
    project = _make_project(tmp_path / 'тёплый-усилитель', name='тёплый-усилитель')
    repo = FilesystemProjectManifestRepository()

    await repo.save(project)

    raw = (tmp_path / 'тёплый-усилитель' / 'project.yaml').read_text(encoding='utf-8')
    # Юникод сохранён as-is, не \u-escape.
    assert 'тёплый-усилитель' in raw
    # Первый ключ — `schema_version` (фиксированный порядок ключей).
    assert raw.startswith('schema_version:')


async def test_save_includes_schema_version_and_status(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()

    await repo.save(project)

    data = yaml.safe_load((tmp_path / 'demo' / 'project.yaml').read_text())
    assert data['schema_version'] == 1
    assert data['status'] == ProjectStatus.IDEA.value


async def test_save_excludes_path_field_for_portability(tmp_path: Path) -> None:
    """`path` не сериализуется (W1) — манифест портативен между машинами."""
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()

    await repo.save(project)

    data = yaml.safe_load((tmp_path / 'demo' / 'project.yaml').read_text())
    assert 'path' not in data


async def test_save_is_atomic_no_tmp_leftover(tmp_path: Path) -> None:
    """После save в каталоге проекта остаётся ровно один файл — project.yaml."""
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()

    await repo.save(project)

    entries = list((tmp_path / 'demo').iterdir())
    assert [e.name for e in entries] == ['project.yaml']


async def test_save_overwrites_existing_manifest(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()
    await repo.save(project)
    project.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.IN_PROGRESS)

    await repo.save(project)

    data = yaml.safe_load((tmp_path / 'demo' / 'project.yaml').read_text())
    schematic = next(p for p in data['phases'] if p['name'] == 'schematic')
    assert schematic['status'] == PhaseStatus.IN_PROGRESS.value


# --- load ---


async def test_round_trip_preserves_domain_fields(tmp_path: Path) -> None:
    """Round-trip `save → load` восстанавливает все доменные поля."""
    original = _make_project(tmp_path / 'demo')
    original.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.IN_PROGRESS)
    original.transition_phase(PhaseName.SCHEMATIC, PhaseStatus.DONE)
    repo = FilesystemProjectManifestRepository()
    await repo.save(original)

    loaded = await repo.load(tmp_path / 'demo')

    assert loaded.id == original.id
    assert loaded.name == original.name
    assert loaded.path == tmp_path / 'demo'  # подставлен из аргумента load
    assert loaded.created_at == original.created_at
    assert loaded.updated_at == original.updated_at
    assert loaded.phases == original.phases
    assert loaded.status is original.status


async def test_load_substitutes_path_from_argument_even_if_moved(
    tmp_path: Path,
) -> None:
    """Имитация переноса: каталог перенесён, manifest читается с нового пути."""
    original = _make_project(tmp_path / 'old-location')
    repo = FilesystemProjectManifestRepository()
    await repo.save(original)

    new_location = tmp_path / 'new-location'
    (tmp_path / 'old-location').rename(new_location)

    loaded = await repo.load(new_location)

    assert loaded.path == new_location
    assert loaded.name == original.name


async def test_load_raises_manifest_not_found_when_file_missing(
    tmp_path: Path,
) -> None:
    repo = FilesystemProjectManifestRepository()

    (tmp_path / 'demo').mkdir()
    with pytest.raises(ManifestNotFoundError):
        await repo.load(tmp_path / 'demo')


async def test_load_raises_manifest_invalid_on_yaml_syntax_error(
    tmp_path: Path,
) -> None:
    (tmp_path / 'demo').mkdir()
    (tmp_path / 'demo' / 'project.yaml').write_text(
        'name: demo\n  bad: indent\n: : :', encoding='utf-8',
    )
    repo = FilesystemProjectManifestRepository()

    with pytest.raises(ManifestInvalidError):
        await repo.load(tmp_path / 'demo')


async def test_load_raises_manifest_invalid_on_pydantic_validation_error(
    tmp_path: Path,
) -> None:
    """Malicious name '../etc/passwd' падает на ProjectName-валидаторе (W3)."""
    (tmp_path / 'demo').mkdir()
    (tmp_path / 'demo' / 'project.yaml').write_text(
        'schema_version: 1\nname: ../etc/passwd\nphases: []\n', encoding='utf-8',
    )
    repo = FilesystemProjectManifestRepository()

    with pytest.raises(ManifestInvalidError, match='Invalid manifest'):
        await repo.load(tmp_path / 'demo')


async def test_load_ignores_extra_fields(tmp_path: Path) -> None:
    """v1 manifest schema игнорирует поля будущих фич (Resolved #5)."""
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()
    await repo.save(project)
    manifest = tmp_path / 'demo' / 'project.yaml'
    data = yaml.safe_load(manifest.read_text())
    data['description'] = 'manually added comment'
    data['future_field'] = {'foo': 'bar'}
    manifest.write_text(yaml.safe_dump(data), encoding='utf-8')

    loaded = await repo.load(tmp_path / 'demo')

    assert loaded.name == project.name


async def test_load_strips_status_before_validate(tmp_path: Path) -> None:
    """`status` — computed_field; на load adapter должен явно его удалить."""
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()
    await repo.save(project)
    manifest = tmp_path / 'demo' / 'project.yaml'
    # вручную ставим status, не соответствующий phases — load должен
    # игнорировать (status derived, не stored).
    data = yaml.safe_load(manifest.read_text())
    data['status'] = ProjectStatus.PRODUCTION_READY.value
    manifest.write_text(yaml.safe_dump(data), encoding='utf-8')

    loaded = await repo.load(tmp_path / 'demo')

    assert loaded.status is ProjectStatus.IDEA  # derived от phases (все pending)


# --- exists ---


async def test_exists_true_when_manifest_present(tmp_path: Path) -> None:
    project = _make_project(tmp_path / 'demo')
    repo = FilesystemProjectManifestRepository()
    await repo.save(project)

    assert await repo.exists(tmp_path / 'demo') is True


async def test_exists_false_when_no_manifest(tmp_path: Path) -> None:
    (tmp_path / 'demo').mkdir()
    repo = FilesystemProjectManifestRepository()

    assert await repo.exists(tmp_path / 'demo') is False


async def test_exists_false_when_project_dir_missing(tmp_path: Path) -> None:
    repo = FilesystemProjectManifestRepository()

    assert await repo.exists(tmp_path / 'nonexistent') is False


# --- discover_all ---


async def test_discover_all_returns_sorted_project_paths(tmp_path: Path) -> None:
    """Сортировка — для детерминированного summary (N2)."""
    repo = FilesystemProjectManifestRepository()
    for name in ['charlie', 'alpha', 'bravo']:
        await repo.save(_make_project(tmp_path / name, name=name))

    found = await repo.discover_all(tmp_path)

    assert found == [tmp_path / 'alpha', tmp_path / 'bravo', tmp_path / 'charlie']


async def test_discover_all_empty_for_empty_storage(tmp_path: Path) -> None:
    repo = FilesystemProjectManifestRepository()

    found = await repo.discover_all(tmp_path)

    assert found == []


async def test_discover_all_skips_dirs_without_manifest(tmp_path: Path) -> None:
    """Папки без project.yaml — не проекты (например, временные)."""
    repo = FilesystemProjectManifestRepository()
    await repo.save(_make_project(tmp_path / 'real-project'))
    (tmp_path / 'empty-dir').mkdir()
    (tmp_path / 'another-empty').mkdir()

    found = await repo.discover_all(tmp_path)

    assert found == [tmp_path / 'real-project']


async def test_discover_all_does_not_recurse(tmp_path: Path) -> None:
    """Sub-projects не предусмотрены — только одноуровневый scan (Resolved #9)."""
    repo = FilesystemProjectManifestRepository()
    await repo.save(_make_project(tmp_path / 'top-level'))
    nested = tmp_path / 'top-level' / 'sub-project'
    nested.mkdir()
    await repo.save(_make_project(nested, name='sub-project'))

    found = await repo.discover_all(tmp_path)

    assert found == [tmp_path / 'top-level']

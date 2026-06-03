"""
T177 — create template из существующего project в user overlay.

Решение persistence-gap'а Phase 6: agent внутри efactory:linux мог
построить отличный template, но писать его в `data/templates/` (read-
only built-in в image) нельзя. T177 даёт persistent user overlay
(`<storage_root>/templates/<name>/`), который bind-mount'ится в
агент-контейнере, и CLI команду для **promotion** project → template.

Pure compute: orchestrates filesystem copy + filename-placeholder
substitution + metadata stub generation. Без DI portов — это локальная
filesystem operation.

Что копируется:
- `<project>/<project>.kicad_sch` → `<template>/{{PROJECT_NAME}}.kicad_sch`
- `<project>/<project>.kicad_pro` → `<template>/{{PROJECT_NAME}}.kicad_pro`
- `<project>/models/*.lib`        → `<template>/models/*.lib`

Не копируется:
- `<project>/project.yaml`        — runtime metadata, не template content.
- `<project>/sim/`                 — simulation runtime artefacts.
- `<project>/datasheets/`         — supporting documents.
- `<project>/.efactory/`          — runtime state.
- `*.kicad_prl`                   — KiCad GUI session state.

Stub `template.yaml` и `README.md` — placeholder; user может править
пост-фактом, или CLI `--description` / `--summary` указать.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

PROJECT_NAME_PLACEHOLDER = '{{PROJECT_NAME}}'

_SKIP_DIRS = frozenset({'sim', 'datasheets', '.efactory'})
_SKIP_FILES = frozenset({'project.yaml'})
_SKIP_EXTENSIONS = frozenset({'.kicad_prl'})


class CreateTemplateError(RuntimeError):
    """Не удалось создать template (источник отсутствует / target conflict)."""


@dataclass(frozen=True)
class CreateTemplateRequest:
    """CLI/use-case request."""

    project_dir: Path
    """Source project directory (e.g., `<projects_root>/<project>/`)."""

    template_name: str
    """Имя нового template (slug, ASCII lowercase, defines dir name)."""

    target_root: Path
    """Куда положить template (user overlay root: `<storage>/templates/`)."""

    description: str = ''
    """Optional. Многострочное описание для template.yaml."""

    summary: str = ''
    """Optional. Однострочное краткое description для list-templates."""

    force: bool = False
    """Перезаписать existing template same name."""


@dataclass(frozen=True)
class CreateTemplateResult:
    template_dir: Path
    files_copied: int
    """Число скопированных файлов (не считая stub yaml/README)."""


def create_template_from_project(
    request: CreateTemplateRequest,
) -> CreateTemplateResult:
    """
    Promote existing project as user-overlay template.

    Алгоритм:
    1. Validate source project structure (.kicad_sch + .kicad_pro по
       template-naming convention).
    2. Resolve target = `target_root / template_name/`.
    3. Conflict check: existing target_dir → error unless force=True.
    4. Copy files с placeholder rename `<project>` → `{{PROJECT_NAME}}`.
    5. Generate stub `template.yaml` и `README.md`.
    """
    project_dir = request.project_dir
    if not project_dir.is_dir():
        msg = f'project directory not found: {project_dir}'
        raise CreateTemplateError(msg)

    project_name = project_dir.name
    sch_path = project_dir / f'{project_name}.kicad_sch'
    if not sch_path.is_file():
        msg = (
            f'project schematic not found: {sch_path} '
            '(expected `<project>/<project>.kicad_sch`)'
        )
        raise CreateTemplateError(msg)

    target_dir = request.target_root / request.template_name
    if target_dir.exists() and not request.force:
        msg = f'template already exists: {target_dir} (use force=True to overwrite)'
        raise CreateTemplateError(msg)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=False)
    files_copied = _copy_project_files(
        src=project_dir,
        dst=target_dir,
        project_name=project_name,
    )

    _write_metadata_stubs(
        target_dir=target_dir,
        template_name=request.template_name,
        description=request.description,
        summary=request.summary,
    )

    return CreateTemplateResult(template_dir=target_dir, files_copied=files_copied)


def _copy_project_files(*, src: Path, dst: Path, project_name: str) -> int:
    """Walk src, копировать в dst с placeholder filename rename."""
    count = 0
    for item in src.iterdir():
        if item.name in _SKIP_FILES:
            continue
        if item.is_dir():
            if item.name in _SKIP_DIRS:
                continue
            sub_dst = dst / item.name
            sub_dst.mkdir(exist_ok=True)
            for inner in item.iterdir():
                if inner.suffix in _SKIP_EXTENSIONS:
                    continue
                shutil.copy2(inner, sub_dst / inner.name)
                count += 1
            continue
        if item.suffix in _SKIP_EXTENSIONS:
            continue
        renamed = _placeholder_rename(item.name, project_name)
        shutil.copy2(item, dst / renamed)
        count += 1
    return count


def _placeholder_rename(filename: str, project_name: str) -> str:
    """`<project_name>.kicad_sch` → `{{PROJECT_NAME}}.kicad_sch`."""
    if filename.startswith(project_name):
        suffix = filename[len(project_name) :]
        return f'{PROJECT_NAME_PLACEHOLDER}{suffix}'
    return filename


def _write_metadata_stubs(
    *,
    target_dir: Path,
    template_name: str,
    description: str,
    summary: str,
) -> None:
    desc_block = description or (
        '  Template создан через `efactory template create-from-project` '
        '(T177).\n  Описание — заполни вручную.'
    )
    summary_line = summary or f'{template_name} (created via T177)'
    yaml_text = (
        f'name: {template_name}\n'
        f'description: |\n'
        f'{_indent_block(desc_block, "  ")}\n'
        f'summary: {summary_line}\n'
    )
    (target_dir / 'template.yaml').write_text(yaml_text, encoding='utf-8')

    readme = (
        f'# {template_name} template\n\n'
        f'{description or "Описание шаблона — заполни вручную."}\n\n'
        f'Создан через `efactory template create-from-project` (T177).\n\n'
        f'## Файлы\n\n'
        f'- `{{PROJECT_NAME}}.kicad_sch` — схема.\n'
        f'- `{{PROJECT_NAME}}.kicad_pro` — KiCad project file.\n'
        f'- `models/*.lib` — SPICE модели (если были в исходном проекте).\n\n'
        f'## Запуск симуляции\n\n'
        f'    efactory project create --name <project> --template {template_name}\n'
        f'    /sim-run\n'
    )
    (target_dir / 'README.md').write_text(readme, encoding='utf-8')


def _indent_block(text: str, prefix: str) -> str:
    return '\n'.join(prefix + line if line else line for line in text.splitlines())

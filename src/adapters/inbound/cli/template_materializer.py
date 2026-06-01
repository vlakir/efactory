"""
TemplateMaterializer — overlay project-templates с substitution (T014 Phase A).

Шаблоны живут в ``data/templates/<name>/``. Materializer оверлеит
файлы шаблона на уже существующий каталог проекта (создан
``create_project`` use case'ом). Template НЕ содержит ``project.yaml``
— оно генерируется use case'ом; конфликты по другим файлам — fail.

Расположение ``data/templates/`` резолвится через ``parents[4]`` от
расположения этого модуля
(``src/adapters/inbound/cli/template_materializer.py`` →
``src`` → ``<repo>``). Аналогично ``composition.settings._default_
library_root`` (``data/models``), но без cross-layer импорта (hex-
contract запрещает adapters → composition). Работает для editable
install; при появлении non-editable wheel — переезд на
``importlib.resources`` с правкой wheel layout.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# parents[0]=cli, [1]=inbound, [2]=adapters, [3]=src, [4]=<repo>.
_REPO_ROOT = Path(__file__).resolve().parents[4]
TEMPLATES_ROOT = _REPO_ROOT / 'data' / 'templates'

PROJECT_NAME_PLACEHOLDER = '{{PROJECT_NAME}}'

# Расширения, в содержимом которых выполняется substitution
# PROJECT_NAME_PLACEHOLDER. Бинарные/неизвестные расширения копируются как есть.
_TEXT_EXTENSIONS = frozenset(
    {'.kicad_sch', '.kicad_pro', '.md', '.yaml', '.yml', '.txt', '.cir'}
)


class TemplateNotFoundError(Exception):
    """Шаблон с таким именем не найден в data/templates/."""


class TemplateConflictError(Exception):
    """В target_dir уже есть файл, который шаблон собирался создать."""


def _sanitize_filename(name: str) -> str:
    """Project name → безопасное filename: пробелы → '_', '/' → '_'."""
    return name.replace(' ', '_').replace('/', '_')


def list_templates() -> list[str]:
    """Список доступных шаблонов (имена subdir в data/templates/)."""
    if not TEMPLATES_ROOT.is_dir():
        return []
    return sorted(
        path.name
        for path in TEMPLATES_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith('.')
    )


def describe_templates() -> list[dict[str, str]]:
    """
    Метаданные всех шаблонов: name + summary из ``template.yaml``.

    Source-of-truth — `data/templates/<name>/template.yaml` (T027 Phase E
    Q12 resolution: data-driven, не hard-coded registry).

    Returns list of dicts sorted by name. Если template.yaml отсутствует
    или не парсится — summary = пустая строка (graceful degradation).
    """
    result: list[dict[str, str]] = []
    if not TEMPLATES_ROOT.is_dir():
        return result
    for name in list_templates():
        tpl_yaml = TEMPLATES_ROOT / name / 'template.yaml'
        summary = ''
        if tpl_yaml.is_file():
            text = tpl_yaml.read_text(encoding='utf-8')
            # Minimal `summary:` line parse — avoids yaml dependency
            # (no other CLI code uses yaml; keep import light).
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith('summary:'):
                    summary = stripped[len('summary:') :].strip()
                    break
        result.append({'name': name, 'summary': summary})
    return result


def materialize_template(
    template_name: str,
    target_dir: Path,
    project_name: str,
) -> None:
    """
    Overlay шаблон ``template_name`` в существующий ``target_dir``.

    - Filename substitution: ``{{PROJECT_NAME}}`` → sanitized project_name.
    - Content substitution в файлах с расширениями ``_TEXT_EXTENSIONS``:
      ``{{PROJECT_NAME}}`` → sanitized project_name.
    - Файлы ``template.yaml`` и ``README.md`` шаблона **не** копируются
      в проект — это metadata самого шаблона, не часть пользовательского
      проекта.
    - Конфликты по существующим файлам → ``TemplateConflictError`` ДО
      записи (pre-scan), чтобы не оставлять half-overlaid состояние.
    """
    src_dir = TEMPLATES_ROOT / template_name
    if not src_dir.is_dir():
        available = ', '.join(list_templates()) or '(none)'
        msg = (
            f'Template {template_name!r} not found in {TEMPLATES_ROOT}. '
            f'Available: {available}.'
        )
        raise TemplateNotFoundError(msg)
    if not target_dir.is_dir():
        msg = f'Target dir does not exist: {target_dir}'
        raise ValueError(msg)

    safe_name = _sanitize_filename(project_name)
    plan = _build_copy_plan(src_dir=src_dir, target_dir=target_dir, safe_name=safe_name)

    conflicts = [str(dest) for _, dest in plan if dest.exists()]
    if conflicts:
        msg = 'Template would overwrite existing files:\n  ' + '\n  '.join(conflicts)
        raise TemplateConflictError(msg)

    for src_path, dest_path in plan:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if src_path.suffix in _TEXT_EXTENSIONS:
            text = src_path.read_text(encoding='utf-8').replace(
                PROJECT_NAME_PLACEHOLDER, safe_name
            )
            dest_path.write_text(text, encoding='utf-8')
        else:
            shutil.copy2(src_path, dest_path)


# Файлы, остающиеся внутри шаблона как метаданные самого шаблона
# (не должны попадать в материализованный проект).
_TEMPLATE_METADATA_FILES = frozenset({'template.yaml', 'README.md'})


def _build_copy_plan(
    *,
    src_dir: Path,
    target_dir: Path,
    safe_name: str,
) -> list[tuple[Path, Path]]:
    """Вернуть список пар (src, dest) для копирования. Каталоги исключены."""
    plan: list[tuple[Path, Path]] = []
    for src_path in sorted(src_dir.rglob('*')):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(src_dir)
        # Skip template-own metadata at top-level
        if str(rel.parent) == '.' and rel.name in _TEMPLATE_METADATA_FILES:
            continue
        dest_name = rel.name.replace(PROJECT_NAME_PLACEHOLDER, safe_name)
        dest_path = target_dir / rel.parent / dest_name
        plan.append((src_path, dest_path))
    return plan

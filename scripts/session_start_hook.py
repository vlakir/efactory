#!/usr/bin/env python3
"""SessionStart hook для Claude Code (T016 Phase A).

Запускается из ``/efactory/.claude/settings.json`` при старте, resume,
clear, compact каждой сессии Claude Code. Читает stdin (метаданные
сессии, нам не нужны), определяет project root по cwd, формирует
markdown-блок с project name / файлами / последними sim-результатами,
выводит JSON в stdout по протоколу Claude Code SessionStart hook
(``hookSpecificOutput.additionalContext``).

Скрипт — stdlib-only (без зависимости от editable venv) и запускается
``/usr/bin/python3`` (Python 3.12 в ``efactory:linux``). Cold-start
~30-50 ms.

Acceptance / Issues (см. ``specs/T016-project-context/spec.md``):

- A4: target latency < 200 ms на demo-проектах (soft cap файлов Q6).
- A5: ``metrics`` поле sim-результатов в context не включается, чтобы
  output держался ≤ 2-4 KB.
- A6: cwd берётся из ``$CLAUDE_PROJECT_DIR`` (Claude Code placeholder),
  fallback на ``os.getcwd()``.

Non-zero exit ⇒ Claude Code graceful-degradate: сессия стартует без
дополнительного контекста (см. Claude Code hooks docs).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path('/workspace')

FILE_CATEGORIES: dict[str, tuple[str, ...]] = {
    'KiCad': ('.kicad_pro', '.kicad_sch', '.kicad_pcb'),
    'SPICE': ('.cir', '.spice', '.subckt', '.lib'),
    'FreeCAD': ('.FCStd',),
    'FEM': ('.geo', '.sif', '.pro'),
}

MAX_FILES_PER_CATEGORY = 20
MAX_SIM_RESULTS = 3
SIM_RESULTS_SUBDIR = '.efactory/sim-results'

# T134 Knowledge Base extension: built-in seed + host-mutated bind-mount.
KB_BUILT_IN_DIR = Path('/efactory/knowledge-base/built-in')
KB_HOST_MUTATED_DIR = Path('/efactory/knowledge-base/host-mutated')


def resolve_project_root(cwd: Path, *, workspace_root: Path) -> Path | None:
    """Вернуть ``<workspace_root>/<NAME>/`` для ``cwd`` под ним, иначе ``None``.

    Скрытые проекты (имя начинается с ``.``) трактуются как «нет проекта».
    """
    try:
        resolved_cwd = cwd.resolve()
        resolved_ws = workspace_root.resolve()
    except (OSError, RuntimeError):
        return None
    try:
        rel = resolved_cwd.relative_to(resolved_ws)
    except ValueError:
        return None
    if not rel.parts:
        return None
    project_name = rel.parts[0]
    if project_name.startswith('.'):
        return None
    return resolved_ws / project_name


def scan_project_files(
    project_root: Path,
    *,
    max_per_category: int = MAX_FILES_PER_CATEGORY,
) -> dict[str, list[Path]]:
    """Сгруппировать файлы проекта по категориям.

    Глубина — top-level + 1 уровень subdir. Скрытые файлы и каталоги
    игнорируются. Hard cap = ``max_per_category`` на категорию.
    """
    by_category: dict[str, list[Path]] = {name: [] for name in FILE_CATEGORIES}
    if not project_root.is_dir():
        return by_category

    candidates: list[Path] = []
    try:
        for entry in project_root.iterdir():
            if entry.name.startswith('.'):
                continue
            if entry.is_file():
                candidates.append(entry)
            elif entry.is_dir():
                try:
                    for sub_entry in entry.iterdir():
                        if sub_entry.name.startswith('.'):
                            continue
                        if sub_entry.is_file():
                            candidates.append(sub_entry)
                except OSError:
                    continue
    except OSError:
        return by_category

    for path in sorted(candidates):
        ext = path.suffix
        for category, exts in FILE_CATEGORIES.items():
            if ext in exts:
                if len(by_category[category]) < max_per_category:
                    by_category[category].append(path)
                break

    return by_category


def scan_sim_results(
    project_root: Path,
    *,
    max_results: int = MAX_SIM_RESULTS,
) -> list[dict[str, str]]:
    """Прочитать последние ``max_results`` sim-результатов (без metrics).

    Сортировка — по имени файла (timestamp в имени) убывающе.
    Сломанный JSON и не-dict содержимое — пропускаются.
    """
    sim_dir = project_root / SIM_RESULTS_SUBDIR
    if not sim_dir.is_dir():
        return []
    try:
        files = sorted(
            (p for p in sim_dir.iterdir() if p.is_file() and p.suffix == '.json'),
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return []

    summaries: list[dict[str, str]] = []
    for file_path in files:
        if len(summaries) >= max_results:
            break
        try:
            data = json.loads(file_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        summaries.append(
            {
                'filename': file_path.name,
                'timestamp': str(data.get('timestamp', '?')),
                'analysis_type': str(data.get('analysis_type', '?')),
                'tool': str(data.get('tool', '?')),
                'source_file': str(data.get('source_file', '?')),
                'summary': str(data.get('summary', '')),
            }
        )
    return summaries


def list_workspace_projects(workspace_root: Path) -> list[str]:
    """Subdir'ы workspace, отсортированные alphabetically. Hidden исключены."""
    if not workspace_root.is_dir():
        return []
    try:
        return sorted(
            p.name
            for p in workspace_root.iterdir()
            if p.is_dir() and not p.name.startswith('.')
        )
    except OSError:
        return []


def render_context(
    *,
    project_root: Path | None,
    cwd: Path,
    workspace_root: Path,
) -> str:
    """Сформировать markdown-блок ``additionalContext``."""
    if project_root is None:
        projects = list_workspace_projects(workspace_root)
        lines = [
            '## Current efactory project',
            '',
            f'No active project (cwd = `{cwd}`).',
            '',
        ]
        if projects:
            joined = ', '.join(f'`{name}`' for name in projects)
            lines.append(f'Available projects in `{workspace_root}/`: {joined}.')
            lines.append('')
            lines.append(
                'To start a session in a specific project, run on the host: '
                '`./efactory-up --agent <NAME>`.'
            )
        else:
            lines.append(f'Workspace `{workspace_root}/` is empty.')
        return '\n'.join(lines)

    files = scan_project_files(project_root)
    sim_results = scan_sim_results(project_root)

    lines = [
        '## Current efactory project',
        '',
        f'Project: **{project_root.name}**',
        f'Path: `{project_root}`',
        '',
    ]

    total_in_categories = {
        category: _count_category(project_root, exts)
        for category, exts in FILE_CATEGORIES.items()
    }

    any_files = False
    for category, paths in files.items():
        if not paths:
            continue
        any_files = True
        lines.append(f'### {category} files')
        for path in paths:
            try:
                rel = path.relative_to(project_root)
            except ValueError:
                rel = path
            lines.append(f'- `{rel}`')
        total = total_in_categories[category]
        if total > len(paths):
            lines.append(f'- (+{total - len(paths)} more)')
        lines.append('')
    if not any_files:
        lines.append('No KiCad/SPICE/FreeCAD/FEM files yet — empty project.')
        lines.append('')

    if sim_results:
        lines.append(f'### Recent sim results (last {len(sim_results)})')
        for entry in sim_results:
            short = entry['summary'][:120]
            line = (
                f'- `{entry["filename"]}` — {entry["analysis_type"]} '
                f'({entry["tool"]}) on `{entry["source_file"]}` '
                f'at {entry["timestamp"]}'
            )
            if short:
                line += f': {short}'
            lines.append(line)
        lines.append('')
        lines.append(
            f'Full sim-result JSON: `{project_root}/{SIM_RESULTS_SUBDIR}/`. '
            'Use `Read` for full metrics.'
        )
    else:
        lines.append(
            f'No sim results yet in `{project_root}/{SIM_RESULTS_SUBDIR}/`.'
        )

    kb_section = render_kb_section(
        built_in_dir=KB_BUILT_IN_DIR,
        host_mutated_dir=KB_HOST_MUTATED_DIR,
    )
    if kb_section:
        lines.append('')
        lines.append(kb_section)

    return '\n'.join(lines)


def render_kb_section(
    *,
    built_in_dir: Path,
    host_mutated_dir: Path,
) -> str:
    """T134: TOC секция для Knowledge Base (grouped by namespace, Q-C → c).

    stdlib-only frontmatter parsing — hook не зависит от efactory venv;
    парсим только `topic` + `description` (TOC fields), tags игнорируем.
    Возвращает пустую строку если KB пуста (skip section, Analyze A4).
    """
    entries = _load_kb_toc_entries(built_in_dir, host_mutated_dir)
    if not entries:
        return ''

    by_namespace: dict[str, list[tuple[str, str]]] = {}
    for topic, desc in entries:
        ns = topic.split('.', 1)[0]
        by_namespace.setdefault(ns, []).append((topic, desc))

    lines = [
        '## Agent Knowledge Base',
        '',
        (
            f'{len(entries)} topic(s) available. Read full body через '
            '`Read /efactory/knowledge-base/{built-in,host-mutated}/'
            '<topic>.md` либо `/kb-search <query>`. Add new entries '
            'через `/kb-add <topic>`.'
        ),
        '',
    ]
    for ns in sorted(by_namespace):
        lines.append(f'### {ns}')
        for topic, desc in sorted(by_namespace[ns]):
            lines.append(f'- **{topic}** — {desc}')
        lines.append('')
    return '\n'.join(lines).rstrip()


def _load_kb_toc_entries(
    built_in_dir: Path,
    host_mutated_dir: Path,
) -> list[tuple[str, str]]:
    """Загрузить TOC entries (topic, description) merged with host-wins."""
    by_topic: dict[str, str] = {}
    for directory in (built_in_dir, host_mutated_dir):
        for topic, desc in _scan_kb_dir(directory):
            by_topic[topic] = desc  # later overrides earlier (host wins)
    return sorted(by_topic.items())


def _scan_kb_dir(directory: Path) -> list[tuple[str, str]]:
    """List (topic, description) — bare frontmatter parser, stdlib only."""
    if not directory.is_dir():
        return []
    out: list[tuple[str, str]] = []
    try:
        for md_path in sorted(directory.glob('*.md')):
            # KB entries имеют namespaced slug — filename содержит точку.
            # README.md / NOTES.md и прочие — skip.
            if '.' not in md_path.stem:
                continue
            try:
                content = md_path.read_text(encoding='utf-8')
            except OSError:
                continue
            fields = _parse_kb_frontmatter_minimal(content)
            topic = fields.get('topic') or md_path.stem
            desc = fields.get('description') or '(no description)'
            out.append((topic, desc))
    except OSError:
        return out
    return out


def _parse_kb_frontmatter_minimal(content: str) -> dict[str, str]:
    """Минимальный frontmatter parser (`key: value` пары) без yaml-deps.

    Hook должен работать на голом Python 3 stdlib (`/usr/bin/python3`),
    pyyaml там нет. Извлекаем только `topic` и `description` — других
    полей для TOC не нужно. Списки (tags) пропускаем.
    """
    if not content.startswith('---\n'):
        return {}
    end = content.find('\n---\n', 4)
    if end == -1:
        return {}
    raw = content[4:end]
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith((' ', '\t', '#', '-')):
            continue
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip().strip('\'"')
        if key in ('topic', 'description'):
            fields[key] = value
    return fields


def _count_category(project_root: Path, exts: tuple[str, ...]) -> int:
    """Полный счёт файлов категории (до soft-cap) для «(+N more)» подписи."""
    count = 0
    if not project_root.is_dir():
        return 0
    try:
        for entry in project_root.iterdir():
            if entry.name.startswith('.'):
                continue
            if entry.is_file() and entry.suffix in exts:
                count += 1
            elif entry.is_dir():
                try:
                    for sub_entry in entry.iterdir():
                        if sub_entry.name.startswith('.'):
                            continue
                        if sub_entry.is_file() and sub_entry.suffix in exts:
                            count += 1
                except OSError:
                    continue
    except OSError:
        return count
    return count


def _resolve_cwd() -> Path:
    """``$CLAUDE_PROJECT_DIR`` → ``os.getcwd()`` → ``/``."""
    env_value = os.environ.get('CLAUDE_PROJECT_DIR')
    if env_value:
        return Path(env_value)
    try:
        return Path(os.getcwd())
    except OSError:
        return Path('/')


def main() -> int:
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass

    cwd = _resolve_cwd()
    project_root = resolve_project_root(cwd, workspace_root=WORKSPACE_ROOT)
    context = render_context(
        project_root=project_root, cwd=cwd, workspace_root=WORKSPACE_ROOT
    )

    payload = {
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': context,
        }
    }
    json.dump(payload, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())

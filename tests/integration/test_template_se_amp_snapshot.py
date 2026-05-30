"""Snapshot-тест: data/templates/se-amp/ должен быть в sync с builder'ом.

Регенерирует se-amp шаблон в tmp каталог через ``scripts/regenerate-
templates.py``, нормализует non-deterministic content (UUID-ы в
``.kicad_sch`` каждого entity) и сверяет с запечённым в репо
``data/templates/se-amp/``.

При несовпадении — fail с сообщением «run regenerate-templates.py».
Чинит ситуацию, когда `_build_se_amp` (или `data/models/`) обновили,
а шаблон не пересобрали.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / 'data' / 'templates' / 'se-amp'
_REGEN_SCRIPT = _REPO_ROOT / 'scripts' / 'regenerate-templates.py'

# Нормализация для diff'а: убираем источники non-determinism, не
# несущие семантической нагрузки:
# (1) UUID v4 `(uuid "...")` — каждый компонент/wire/label, генерируется
#     `uuid.uuid4()` per call.
# (2) `(path "/UUID" ...)` внутри instances блоков — то же.
# (3) Блок `(lib_symbols ...)` целиком — order subsymbols зависит от
#     PYTHONHASHSEED (set/dict iteration); это inline-кэш KiCad-
#     библиотек, не семантическая часть схемы. Семантические изменения
#     (новые компоненты) ловятся в body через `(symbol "ref:lib_id" ...)`
#     references.
_UUID_BARE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_UUID_FIELD_RE = re.compile(rf'\(uuid "{_UUID_BARE}"\)')
_PATH_UUID_RE = re.compile(rf'\(path "/{_UUID_BARE}"')


def _strip_lib_symbols(text: str) -> str:
    """Удалить (lib_symbols ...) блок целиком, считая parenthesis-balance."""
    marker = '\t(lib_symbols'
    start = text.find(marker)
    if start == -1:
        return text
    # Найти закрывающую скобку для (lib_symbols
    pos = start + len(marker)
    depth = 1  # уже внутри (lib_symbols
    while pos < len(text) and depth > 0:
        ch = text[pos]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        pos += 1
    return text[:start] + '\t(lib_symbols REMOVED)\n' + text[pos:].lstrip('\n')


def _normalize(text: str) -> str:
    text = _UUID_FIELD_RE.sub('(uuid "NORMALIZED")', text)
    text = _PATH_UUID_RE.sub('(path "/NORMALIZED"', text)
    return _strip_lib_symbols(text)


@pytest.fixture(scope='module')
def fresh_bake_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Прогон `regenerate-templates.py --template se-amp` в tmp."""
    work = tmp_path_factory.mktemp('regen')
    # Скрипт пишет в `data/templates/<name>`, путь хардкодом. Прогоняем
    # как subprocess с подменой `_TEMPLATES_DIR` через временный clone
    # репо — слишком тяжело. Простой путь: импортируем функцию и
    # переопределяем target.
    sys.path.insert(0, str(_REPO_ROOT / 'scripts'))
    import importlib.util

    spec = importlib.util.spec_from_file_location('regen_tpl', _REGEN_SCRIPT)
    if spec is None or spec.loader is None:
        msg = f'Cannot import {_REGEN_SCRIPT}'
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = work / 'se-amp'
    module._bake_se_amp(target)  # noqa: SLF001
    return target


def test_se_amp_template_in_sync_with_builder(fresh_bake_dir: Path) -> None:
    if not _TEMPLATE_DIR.is_dir():
        pytest.fail(
            f'Baked template missing: {_TEMPLATE_DIR}. '
            f'Run `uv run python {_REGEN_SCRIPT.relative_to(_REPO_ROOT)}`.'
        )

    fresh_files = sorted(
        p.relative_to(fresh_bake_dir)
        for p in fresh_bake_dir.rglob('*')
        if p.is_file()
    )
    baked_files = sorted(
        p.relative_to(_TEMPLATE_DIR)
        for p in _TEMPLATE_DIR.rglob('*')
        if p.is_file()
    )
    if fresh_files != baked_files:
        msg = (
            f'Template file set changed.\n'
            f'  baked: {baked_files}\n'
            f'  fresh: {fresh_files}\n'
            f'Run `uv run python {_REGEN_SCRIPT.relative_to(_REPO_ROOT)}`.'
        )
        pytest.fail(msg)

    differences: list[str] = []
    for rel_path in fresh_files:
        fresh_text = _normalize(
            (fresh_bake_dir / rel_path).read_text(encoding='utf-8')
        )
        baked_text = _normalize(
            (_TEMPLATE_DIR / rel_path).read_text(encoding='utf-8')
        )
        if fresh_text != baked_text:
            differences.append(str(rel_path))

    if differences:
        import difflib

        diff_dump = []
        for rel_path in differences:
            fresh_text = _normalize(
                (fresh_bake_dir / rel_path).read_text(encoding='utf-8')
            )
            baked_text = _normalize(
                (_TEMPLATE_DIR / rel_path).read_text(encoding='utf-8')
            )
            udiff = list(
                difflib.unified_diff(
                    baked_text.splitlines(keepends=True),
                    fresh_text.splitlines(keepends=True),
                    fromfile=f'baked/{rel_path}',
                    tofile=f'fresh/{rel_path}',
                    n=1,
                )
            )[:40]
            diff_dump.append(''.join(udiff))
        msg = (
            f'Template content drift in files: {differences}.\n'
            f'Run `uv run python {_REGEN_SCRIPT.relative_to(_REPO_ROOT)}`.\n'
            f'--- Unified diff (first 40 lines):\n'
            f'{chr(10).join(diff_dump)}'
        )
        pytest.fail(msg)


def test_regenerate_script_invokable_as_cli(tmp_path: Path) -> None:
    """Запуск скрипта через subprocess не падает (smoke на cli surface)."""
    # Прогоняем `--help` — не модифицирует репо.
    result = subprocess.run(
        [sys.executable, str(_REGEN_SCRIPT), '--help'],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert 'Rebake shipping templates' in result.stdout

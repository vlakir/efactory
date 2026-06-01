"""Snapshot-тест: data/templates/tube-phono-riaa/ — sync с builder'ом (T027 C)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / 'data' / 'templates' / 'tube-phono-riaa'
_REGEN_SCRIPT = _REPO_ROOT / 'scripts' / 'regenerate-templates.py'

_UUID_BARE = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_UUID_FIELD_RE = re.compile(rf'\(uuid "{_UUID_BARE}"\)')
_PATH_UUID_RE = re.compile(rf'\(path "/{_UUID_BARE}"')


def _strip_lib_symbols(text: str) -> str:
    marker = '\t(lib_symbols'
    start = text.find(marker)
    if start == -1:
        return text
    pos = start + len(marker)
    depth = 1
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
    work = tmp_path_factory.mktemp('regen-tube-phono-riaa')
    sys.path.insert(0, str(_REPO_ROOT / 'scripts'))
    import importlib.util

    spec = importlib.util.spec_from_file_location('regen_tpl', _REGEN_SCRIPT)
    if spec is None or spec.loader is None:
        msg = f'Cannot import {_REGEN_SCRIPT}'
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = work / 'tube-phono-riaa'
    module._reseed_uuid_rng_for_template('tube-phono-riaa')  # noqa: SLF001
    module._bake_tube_phono_riaa(target)  # noqa: SLF001
    return target


def test_tube_phono_riaa_template_in_sync_with_builder(
    fresh_bake_dir: Path,
) -> None:
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
        msg = (
            f'Template content drift in files: {differences}.\n'
            f'Run `uv run python {_REGEN_SCRIPT.relative_to(_REPO_ROOT)}`.'
        )
        pytest.fail(msg)

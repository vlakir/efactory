"""Статическая валидация slash-команд efactory (T014 Phase B).

Проверяет, что `docker/runtime-agent-commands/*.md` содержат корректный
YAML frontmatter с обязательными полями и body не пустой. TUI smoke
(`/help`, фактическое поведение в Claude Code) — manual acceptance
после rebuild + `--reset-claude-state`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMANDS_DIR = _REPO_ROOT / 'docker' / 'runtime-agent-commands'

_EXPECTED_COMMANDS = {
    'project-create',
    'project-use',
    'sim-run',
    'measure-gain',
    'measure-bandwidth',
    'measure-thd',
    'plot-ac',
    'plot-tran',
    'kb-search',
    'kb-add',
    'sweep',  # T022 Phase D
}
_REQUIRED_FRONTMATTER = {'description', 'argument-hint', 'allowed-tools'}


def _parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Разделить .md на frontmatter dict и body. ValueError если нет."""
    if not content.startswith('---\n'):
        msg = 'No frontmatter (file must start with `---\\n`).'
        raise ValueError(msg)
    end = content.find('\n---\n', 4)
    if end == -1:
        msg = 'Frontmatter not closed with `\\n---\\n`.'
        raise ValueError(msg)
    raw = content[4:end]
    body = content[end + 5 :]
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict):
        msg = f'Frontmatter is not a YAML mapping: {type(parsed).__name__}'
        raise TypeError(msg)
    return parsed, body


def test_commands_dir_exists() -> None:
    assert _COMMANDS_DIR.is_dir(), f'Missing: {_COMMANDS_DIR}'


def test_expected_command_set() -> None:
    actual = {
        path.stem for path in _COMMANDS_DIR.glob('*.md') if path.is_file()
    }
    assert actual == _EXPECTED_COMMANDS


@pytest.mark.parametrize('name', sorted(_EXPECTED_COMMANDS))
def test_each_command_has_valid_frontmatter_and_nonempty_body(
    name: str,
) -> None:
    path = _COMMANDS_DIR / f'{name}.md'
    content = path.read_text(encoding='utf-8')

    fm, body = _parse_frontmatter(content)

    missing = _REQUIRED_FRONTMATTER - fm.keys()
    assert not missing, f'{name}: missing frontmatter fields: {missing}'
    assert fm['description'], f'{name}: empty description'
    assert fm['argument-hint'], f'{name}: empty argument-hint'
    assert fm['allowed-tools'], f'{name}: empty allowed-tools'
    assert body.strip(), f'{name}: empty body'


@pytest.mark.parametrize('name', sorted(_EXPECTED_COMMANDS))
def test_each_command_body_mentions_arguments_placeholder(name: str) -> None:
    """Body должен использовать $ARGUMENTS для аргумент-substitution."""
    path = _COMMANDS_DIR / f'{name}.md'
    content = path.read_text(encoding='utf-8')
    _, body = _parse_frontmatter(content)
    assert '$ARGUMENTS' in body, (
        f'{name}: body does not reference $ARGUMENTS '
        '(Claude Code argument substitution)'
    )

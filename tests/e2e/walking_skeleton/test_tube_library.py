"""E2E: efactory tube list/show на built-in generic моделях (T006)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _setup_env(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    # tube_library_root: default из репо data/models/tubes/ — должны
    # подтянуться 2 generic примера.


def test_tube_list_shows_generic_examples(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['tube', 'list'])

    assert result.exit_code == 0, result.output
    assert 'GENERIC_PENTODE' in result.output
    assert 'GENERIC_TRIODE' in result.output
    # source/type tab-separated
    assert 'ayumi' in result.output
    assert 'koren' in result.output
    assert 'pentode' in result.output
    assert 'triode' in result.output


def test_tube_show_pentode_converts_caret_to_double_star(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance: Ayumi `^` → ngspice `**` через `read_subckt`."""
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', 'GENERIC_PENTODE'],
    )

    assert result.exit_code == 0, result.output
    assert 'id: GENERIC_PENTODE' in result.output
    assert 'source: ayumi' in result.output
    assert 'tube_type: pentode' in result.output
    assert '.SUBCKT GENERIC_PENTODE' in result.output
    assert '**1.5' in result.output
    # `^` не должно остаться в SUBCKT блоке (он начинается после метаданных)
    subckt_section = result.output.split('.SUBCKT', 1)[1]
    assert '^' not in subckt_section


def test_tube_show_triode_no_conversion_needed(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', 'GENERIC_TRIODE'],
    )

    assert result.exit_code == 0, result.output
    assert 'tube_type: triode' in result.output
    assert 'pins: P G K' in result.output
    assert '.SUBCKT GENERIC_TRIODE' in result.output


def test_tube_show_unknown_id_exits_one(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', 'NONEXISTENT'],
    )

    assert result.exit_code == 1
    assert 'NONEXISTENT' in result.output


def test_tube_list_empty_when_library_root_missing(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    monkeypatch.setenv(
        'EFACTORY_TUBE_LIBRARY_ROOT', str(tmp_path / 'empty_tubes'),
    )
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['tube', 'list'])

    assert result.exit_code == 0, result.output
    assert 'No tube models found.' in result.output

"""E2E: efactory transformer / load list+show (T007 generalization)."""

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


def test_transformer_list_shows_built_in_opts(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['transformer', 'list'])

    assert result.exit_code == 0, result.output
    assert 'OPT_SE_5K_8' in result.output
    assert 'OPT_PP_6K6_8' in result.output
    assert '\topt\t' in result.output
    assert 'generic' in result.output


def test_transformer_show_opt_se(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['transformer', 'show', '--id', 'OPT_SE_5K_8'],
    )

    assert result.exit_code == 0, result.output
    assert 'id: OPT_SE_5K_8' in result.output
    assert 'category: transformer' in result.output
    assert 'type: opt' in result.output
    assert 'pins: P1 P2 S1 S2' in result.output
    assert '.SUBCKT OPT_SE_5K_8' in result.output


def test_load_list_shows_built_in_speakers(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['load', 'list'])

    assert result.exit_code == 0, result.output
    for expected in (
        'SPEAKER_8OHM',
        'SPEAKER_8OHM_RES',
        'SPEAKER_4OHM',
        'DUMMY_LOAD_8R',
    ):
        assert expected in result.output, f'missing {expected}'
    assert '\tspeaker\t' in result.output
    assert '\tresistive\t' in result.output


def test_load_show_speaker_with_resonance(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['load', 'show', '--id', 'SPEAKER_8OHM'],
    )

    assert result.exit_code == 0, result.output
    assert 'category: load' in result.output
    assert 'type: speaker' in result.output
    assert 'pins: SP SN' in result.output
    assert 'Rdc' in result.output  # voice coil DCR
    assert 'Lcm' in result.output  # mechanical resonance inductor


def test_tube_show_does_not_match_transformer_id(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`efactory tube show --id OPT_SE_5K_8` → exit 1 (category mismatch)."""
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', 'OPT_SE_5K_8'],
    )

    assert result.exit_code == 1
    assert 'category=transformer' in result.output
    assert 'efactory transformer show' in result.output


def test_load_categories_disjoint_from_tubes(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load list` не показывает tube/transformer модели."""
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['load', 'list'])

    assert result.exit_code == 0
    assert 'EL34' not in result.output
    assert 'OPT_SE_5K_8' not in result.output
    assert '12AX7' not in result.output


def test_transformer_categories_disjoint_from_tubes(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['transformer', 'list'])

    assert result.exit_code == 0
    assert 'EL34' not in result.output
    assert 'SPEAKER_8OHM' not in result.output

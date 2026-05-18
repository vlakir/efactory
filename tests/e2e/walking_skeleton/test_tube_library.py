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


def test_tube_list_shows_built_in_set(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Built-in библиотека ≥10 моделей (T006 fix-up real models)."""
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['tube', 'list'])

    assert result.exit_code == 0, result.output
    # Koren-источник: классические триоды + пентоды.
    for expected in ('12AX7', '12AU7', '6SN7', 'EL34', '6L6', '6V6', 'KT88'):
        assert expected in result.output, f'missing {expected} in tube list'
    # Ayumi-источник: с `^` оператором.
    assert '300B' in result.output
    assert '6DJ8' in result.output
    # Советские (custom): аналоги западных.
    for expected in ('6N2P', '6N3P', '6P14P', '6P3S'):
        assert expected in result.output, f'missing {expected} in tube list'
    # Generic-форматы как documentation.
    assert 'GENERIC_TRIODE' in result.output
    assert 'GENERIC_PENTODE' in result.output
    # source/type tab-separated.
    assert 'ayumi' in result.output
    assert 'koren' in result.output
    assert 'custom' in result.output
    assert 'pentode' in result.output
    assert 'triode' in result.output


def test_tube_show_real_models_parse_correctly(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: каждая built-in модель парсится без ошибок (`tube show` exit 0)."""
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    builtin_ids = (
        '12AX7', '12AU7', '6SN7', 'EL34', '6L6', '6V6', 'KT88',
        '300B', '6DJ8',
        '6N2P', '6N3P', '6P14P', '6P3S',
        'GENERIC_TRIODE', 'GENERIC_PENTODE',
    )
    for model_id in builtin_ids:
        result = runner.invoke(
            build_cli_app(), ['tube', 'show', '--id', model_id],
        )
        assert result.exit_code == 0, f'show {model_id} failed: {result.output}'
        assert f'id: {model_id}' in result.output
        assert '.SUBCKT' in result.output


def test_tube_show_ayumi_converts_caret_to_double_star(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance: Ayumi `^` → ngspice `**` через `read_subckt` (на real 300B)."""
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', '300B'],
    )

    assert result.exit_code == 0, result.output
    assert 'id: 300B' in result.output
    assert 'source: ayumi' in result.output
    assert 'tube_type: triode' in result.output
    assert '.SUBCKT 300B' in result.output
    # 300B model содержит V(P,K)^2 → должно стать V(P,K)**2.
    assert '**2' in result.output
    # `^` не должно остаться в SUBCKT блоке.
    subckt_section = result.output.split('.SUBCKT', 1)[1]
    assert '^' not in subckt_section


def test_tube_show_koren_triode_no_conversion_needed(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', '12AX7'],
    )

    assert result.exit_code == 0, result.output
    assert 'source: koren' in result.output
    assert 'tube_type: triode' in result.output
    assert 'pins: P G K' in result.output
    assert '.SUBCKT 12AX7' in result.output


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
    monkeypatch.setenv(
        'EFACTORY_USER_TUBE_LIBRARY_ROOT', str(tmp_path / 'empty_user'),
    )
    runner = CliRunner()

    result = runner.invoke(build_cli_app(), ['tube', 'list'])

    assert result.exit_code == 0, result.output
    assert 'No tube models found.' in result.output


def test_tube_list_user_overlay_adds_custom_model(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-user сценарий: положил `.lib` в user-каталог → видно в list."""
    _setup_env(tmp_path, monkeypatch)
    user_lib = tmp_path / 'user_tubes'
    custom_dir = user_lib / 'custom'
    custom_dir.mkdir(parents=True)
    (custom_dir / 'MY_TUBE.lib').write_text(
        '.SUBCKT MY_TUBE P G K\n.ENDS\n', encoding='utf-8',
    )
    monkeypatch.setenv('EFACTORY_USER_TUBE_LIBRARY_ROOT', str(user_lib))
    runner = CliRunner()

    list_result = runner.invoke(build_cli_app(), ['tube', 'list'])
    assert list_result.exit_code == 0, list_result.output
    # Built-in 2 generic + user MY_TUBE
    assert 'GENERIC_TRIODE' in list_result.output
    assert 'GENERIC_PENTODE' in list_result.output
    assert 'MY_TUBE' in list_result.output
    # User-модель помечена `user`, built-in — `built-in`
    user_line = next(
        line for line in list_result.output.splitlines() if 'MY_TUBE' in line
    )
    assert '\tuser\t' in user_line

    show_result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', 'MY_TUBE'],
    )
    assert show_result.exit_code == 0
    assert 'library: user' in show_result.output


def test_tube_list_user_overlay_overrides_built_in(
    tmp_path: 'Path', monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User-id с тем же именем побеждает built-in (Q3 fix-up acceptance)."""
    _setup_env(tmp_path, monkeypatch)
    user_lib = tmp_path / 'user_tubes'
    custom_dir = user_lib / 'custom'
    custom_dir.mkdir(parents=True)
    (custom_dir / 'GENERIC_TRIODE.lib').write_text(
        '.SUBCKT TUNED_TRIODE P G K\n* my tuned variant\n.ENDS\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('EFACTORY_USER_TUBE_LIBRARY_ROOT', str(user_lib))
    runner = CliRunner()

    show_result = runner.invoke(
        build_cli_app(), ['tube', 'show', '--id', 'GENERIC_TRIODE'],
    )

    assert show_result.exit_code == 0, show_result.output
    assert 'library: user' in show_result.output
    assert 'TUNED_TRIODE' in show_result.output
    assert 'name: TUNED_TRIODE' in show_result.output

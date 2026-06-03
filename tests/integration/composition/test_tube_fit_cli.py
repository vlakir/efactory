"""CLI integration test: `efactory tube fit-from-points` (T031 Phase 2 SC#3)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app
from domain.tube_fitting import KorenTriodeParams, koren_triode_ia

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _synth_triode_json(path: 'Path') -> None:
    truth = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)
    payload = {
        'tube_name': '12AX7',
        'tube_type': 'triode',
        'source': 'synth-for-cli-test',
        'date_extracted': '2026-06-03',
        'curves': [
            {
                'vg': vg,
                'points': [
                    [va, koren_triode_ia(vg, va, truth)]
                    for va in (50.0, 100.0, 200.0, 300.0, 400.0)
                ],
            }
            for vg in (-0.5, -1.0, -2.0, -3.0)
        ],
    }
    path.write_text(json.dumps(payload), encoding='utf-8')


_ENV_VARS = ('EFACTORY_PROJECTS_ROOT', 'XDG_DATA_HOME')


def _setup_env(tmp_path: 'Path', monkeypatch: 'pytest.MonkeyPatch') -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_tube_fit_from_points_writes_lib_with_default_out(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """SC#3: exit 0 + .lib at expected default user-overlay path + stdout summary."""
    _setup_env(tmp_path, monkeypatch)
    json_path = tmp_path / 'triode_synth.json'
    _synth_triode_json(json_path)

    app = build_cli_app()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            'tube',
            'fit-from-points',
            'X12AX7',
            '--type',
            'triode',
            '--points',
            str(json_path),
        ],
    )

    assert result.exit_code == 0, result.output
    # Default out = user overlay (XDG_DATA_HOME defaults to ~/.local/share).
    expected_lib = (
        tmp_path
        / '.local'
        / 'share'
        / 'efactory'
        / 'models'
        / 'tubes'
        / 'custom'
        / 'X12AX7.lib'
    )
    assert expected_lib.is_file(), result.output
    content = expected_lib.read_text(encoding='utf-8')
    assert '* tube_type: triode' in content
    assert '.SUBCKT X12AX7 P G K' in content

    # Stdout summary (SC#3).
    assert f'lib: {expected_lib}' in result.output
    assert 'fit: n_points=20' in result.output
    assert 'rms=' in result.output
    assert 'params:' in result.output


def test_tube_fit_explicit_out_dir_and_force_overwrite(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _setup_env(tmp_path, monkeypatch)
    json_path = tmp_path / 'triode_synth.json'
    _synth_triode_json(json_path)
    out_dir = tmp_path / 'my-tubes'

    app = build_cli_app()
    runner = CliRunner()
    args = [
        'tube',
        'fit-from-points',
        'X12AX7',
        '--type',
        'triode',
        '--points',
        str(json_path),
        '--out',
        str(out_dir),
    ]
    # First write succeeds.
    r1 = runner.invoke(app, args)
    assert r1.exit_code == 0, r1.output
    assert (out_dir / 'X12AX7.lib').is_file()

    # Second write without --force fails.
    r2 = runner.invoke(app, args)
    assert r2.exit_code == 1, r2.output
    assert 'already exists' in r2.output

    # With --force succeeds.
    r3 = runner.invoke(app, [*args, '--force'])
    assert r3.exit_code == 0, r3.output


def test_tube_fit_rejects_include_vct_with_pentode(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """A-W1: --include-vct + --type pentode → exit 2."""
    _setup_env(tmp_path, monkeypatch)
    # JSON irrelevant — CLI rejects before reading.
    app = build_cli_app()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            'tube',
            'fit-from-points',
            'XEL34',
            '--type',
            'pentode',
            '--points',
            str(tmp_path / 'unused.json'),
            '--include-vct',
        ],
    )
    assert result.exit_code == 2
    assert 'include-vct' in result.output


def test_tube_fit_rejects_invalid_type(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _setup_env(tmp_path, monkeypatch)
    app = build_cli_app()
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            'tube',
            'fit-from-points',
            'X',
            '--type',
            'rectifier',  # invalid
            '--points',
            str(tmp_path / 'x.json'),
        ],
    )
    assert result.exit_code == 2
    assert 'triode' in result.output  # error message lists valid options

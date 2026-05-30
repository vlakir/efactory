"""E2E: defensive guard для пустого / несуществующего NETLIST в bridge CLI.

T161: `uv run efactory bridge sim-run op ""` ловил cryptic
`IsADirectoryError: '.'` с rich-traceback и exit=1. Аналогично для
nonexistent path — `FileNotFoundError`. Guard превращает оба случая
в человекочитаемое `Netlist file not found: <path>` + exit=2 во всех
netlist-принимающих subcommands (sim-run / measure / plot).

Тест не требует ngspice: guard срабатывает до запуска симулятора.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_NETLIST_PLACEHOLDER = '{netlist}'

_INVOCATIONS: list[tuple[str, list[str]]] = [
    ('sim-run-op', ['bridge', 'sim-run', 'op', _NETLIST_PLACEHOLDER]),
    (
        'sim-run-tran',
        [
            'bridge', 'sim-run', 'tran', _NETLIST_PLACEHOLDER,
            '--t-step', '1u', '--t-stop', '1m',
        ],
    ),
    (
        'sim-run-ac',
        [
            'bridge', 'sim-run', 'ac', _NETLIST_PLACEHOLDER,
            '--n-points', '10', '--f-start', '1', '--f-stop', '1k',
        ],
    ),
    (
        'measure-gain',
        ['bridge', 'measure', 'gain', _NETLIST_PLACEHOLDER, '--freq', '1k'],
    ),
    (
        'measure-bandwidth',
        ['bridge', 'measure', 'bandwidth', _NETLIST_PLACEHOLDER],
    ),
    (
        'measure-thd',
        [
            'bridge', 'measure', 'thd', _NETLIST_PLACEHOLDER,
            '--freq', '1k', '--v-in-peak', '0.1',
        ],
    ),
    ('plot-ac', ['bridge', 'plot', 'ac', _NETLIST_PLACEHOLDER]),
    (
        'plot-tran',
        [
            'bridge', 'plot', 'tran', _NETLIST_PLACEHOLDER,
            '--t-step', '1u', '--t-stop', '1m',
        ],
    ),
]


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))


def _invoke(args_template: list[str], netlist_arg: str) -> object:
    args = [
        netlist_arg if a == _NETLIST_PLACEHOLDER else a
        for a in args_template
    ]
    return CliRunner().invoke(build_cli_app(), args)


@pytest.mark.parametrize(
    'args_template',
    [args for _, args in _INVOCATIONS],
    ids=[label for label, _ in _INVOCATIONS],
)
def test_bridge_empty_netlist_exits_with_clear_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args_template: list[str],
) -> None:
    _setup_env(tmp_path, monkeypatch)

    result = _invoke(args_template, netlist_arg='')

    assert result.exit_code == 2, (
        f'expected exit=2, got {result.exit_code}; output={result.output!r}'
    )
    assert 'Netlist file not found' in result.output, (
        f'expected "Netlist file not found" in output; got {result.output!r}'
    )


@pytest.mark.parametrize(
    'args_template',
    [args for _, args in _INVOCATIONS],
    ids=[label for label, _ in _INVOCATIONS],
)
def test_bridge_nonexistent_netlist_exits_with_clear_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args_template: list[str],
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist_arg = str(tmp_path / 'does-not-exist.cir')

    result = _invoke(args_template, netlist_arg=netlist_arg)

    assert result.exit_code == 2, (
        f'expected exit=2, got {result.exit_code}; output={result.output!r}'
    )
    assert 'Netlist file not found' in result.output, (
        f'expected "Netlist file not found" in output; got {result.output!r}'
    )
    assert netlist_arg in result.output, (
        f'expected resolved path {netlist_arg!r} echoed in output; '
        f'got {result.output!r}'
    )

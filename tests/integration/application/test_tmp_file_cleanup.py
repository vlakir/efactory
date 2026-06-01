"""
T165: cleanup ngspice temp `.tmp_*` files после measurement use cases.

Parametrized leak test покрывает 4 measurement use cases (`measure_phase_margin`,
`measure_gain` small AC, `measure_bandwidth`, `measure_thd`) + отдельный
unit test для CLI helper `_prepare_ac_netlist`. Все они должны убирать за
собой `<stem>.tmp_*.cir`, `<stem>.tmp_*.raw`, `<stem>.tmp_*.wrapper.cir`
файлы (рядом с input netlist'ом), независимо от успеха или раннего exit'а
с domain error.

TDD Red: тесты падают на текущей implementation, потому что 4 use cases +
CLI helper пишут tmp файлы через `netlist.with_suffix('.tmp_*.cir')`
рядом с input'ом и никогда их не убирают. После refactor'а на
`tempfile.TemporaryDirectory(...)` (как в `bridge_sweep` /
`edit_and_resim_with_delta`) тесты пройдут.
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from adapters.inbound.cli.app import _prepare_ac_netlist
from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
)
from adapters.outbound.ngspice.netlist_substitution import NgspiceNetlistEditor
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import NativePlatformLayer
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from application.measure_bandwidth import measure_bandwidth
from application.measure_gain import measure_gain
from application.measure_phase_margin import measure_phase_margin
from application.measure_thd import measure_thd
from domain.phase_margin import (
    LoopGainAlwaysAboveUnityError,
    NoUnityGainCrossoverError,
)
from domain.phase_margin_injection import MiddlebrookVoltageStrategy

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path


_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)


# Op-amp inverting amp с output RC rolloff — для measure_phase_margin
# (нужен реальный feedback loop).
_OPAMP_FIXTURE = (
    '* op-amp inverting amp with output RC rolloff (T165 cleanup test)\n'
    'V_in vin 0 DC 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp v_open 0 0 in_neg 1e5\n'
    'R_amp v_open vout 1k\n'
    'C_amp vout 0 10u\n'
    'R_load vout 0 1Meg\n'
    '.end\n'
)

# Voltage divider с SIN source — для gain / bandwidth / thd (нужен SIN-
# source для THD; для gain/bandwidth source сам конвертится в AC).
_DIVIDER_FIXTURE = (
    '* voltage divider R1=R2=1k (T165 cleanup test)\n'
    'V_in in 0 SIN(0 0.1 1000)\n'
    'R1 in load 1k\n'
    'R_load load 0 1k\n'
    '.end\n'
)


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


def _tmp_artifacts(directory: Path) -> set[Path]:
    """Snapshot всех `.tmp_*` files (cir/raw/wrapper) в директории."""
    patterns = ('*.tmp_*.cir', '*.tmp_*.raw', '*.tmp_*.wrapper.cir')
    found: set[Path] = set()
    for pattern in patterns:
        found.update(directory.glob(pattern))
    return found


@dataclass(frozen=True)
class _LeakCase:
    """Один параметризованный сценарий для leak теста."""

    label: str
    netlist_text: str
    run: Callable[[Path], Awaitable[object]]


async def _run_measure_phase_margin(netlist: Path) -> object:
    strategy = MiddlebrookVoltageStrategy(NgspiceInjectionNetlistPatcher())
    return await measure_phase_margin(
        netlist=netlist,
        injection_strategy=strategy,
        break_node='vout',
        break_element_ref='R_fb',
        simulator=_make_simulator(),
        f_low=1.0,
        f_high=1e7,
        n_points_per_decade=50,
    )


async def _run_measure_gain_small(netlist: Path) -> object:
    return await measure_gain(
        netlist=netlist,
        frequency_hz=1000.0,
        mode='small',
        simulator=_make_simulator(),
        netlist_editor=NgspiceNetlistEditor(),
        output_signal='v(load)',
    )


async def _run_measure_bandwidth(netlist: Path) -> object:
    return await measure_bandwidth(
        netlist=netlist,
        simulator=_make_simulator(),
        netlist_editor=NgspiceNetlistEditor(),
        f_low=1.0,
        f_high=1e6,
        n_points_per_decade=50,
    )


async def _run_measure_thd(netlist: Path) -> object:
    return await measure_thd(
        netlist=netlist,
        frequency_hz=1000.0,
        v_in_peak=0.1,
        simulator=_make_simulator(),
        netlist_editor=NgspiceNetlistEditor(),
        signal='v(load)',
        load_ohm=1000.0,
    )


_CASES: tuple[_LeakCase, ...] = (
    _LeakCase(
        label='measure_phase_margin',
        netlist_text=_OPAMP_FIXTURE,
        run=_run_measure_phase_margin,
    ),
    _LeakCase(
        label='measure_gain_small',
        netlist_text=_DIVIDER_FIXTURE,
        run=_run_measure_gain_small,
    ),
    _LeakCase(
        label='measure_bandwidth',
        netlist_text=_DIVIDER_FIXTURE,
        run=_run_measure_bandwidth,
    ),
    _LeakCase(
        label='measure_thd',
        netlist_text=_DIVIDER_FIXTURE,
        run=_run_measure_thd,
    ),
)


@needs_ngspice
@pytest.mark.parametrize('case', _CASES, ids=lambda c: c.label)
async def test_measurement_use_case_does_not_leak_tmp_files(
    case: _LeakCase,
    tmp_path: Path,
) -> None:
    """T165 acceptance: после measurement use case в директории netlist'а
    не должно остаться `.tmp_*.cir/.raw/.wrapper.cir` файлов.

    Domain errors (например `NoUnityGainCrossoverError` на divider'е для
    PM) — acceptable: cleanup всё равно обязан случиться (это весь смысл
    `tempfile.TemporaryDirectory` context manager'а). Errors здесь
    suppress-ятся; assertion — только про cleanup.
    """
    netlist = tmp_path / 'fixture.cir'
    netlist.write_text(case.netlist_text)
    before = _tmp_artifacts(tmp_path)

    # Domain errors не интересуют — нас интересует cleanup на любом исходе.
    with contextlib.suppress(
        NoUnityGainCrossoverError,
        LoopGainAlwaysAboveUnityError,
        ValueError,
    ):
        await case.run(netlist)

    after = _tmp_artifacts(tmp_path)
    leaked = after - before
    assert not leaked, (
        f'{case.label} оставил temp файлы в '
        f'{tmp_path}: {sorted(p.name for p in leaked)}'
    )


def test_cli_prepare_ac_netlist_does_not_leak_tmp_files(
    tmp_path: Path,
) -> None:
    """CLI helper `_prepare_ac_netlist` пишет `.tmp_plot.cir` рядом с
    input netlist и возвращает path. После использования prepared
    netlist'а файл должен быть убран — CLI handler (или сам helper)
    обязан управлять lifecycle'ом.

    Acceptance T165 для CLI: после полного use cycle (т.е. после того
    как handler закончил работу с prepared netlist'ом) в директории
    netlist'а не должно остаться `.tmp_plot.cir`.
    """
    netlist = tmp_path / 'fixture.cir'
    netlist.write_text(_DIVIDER_FIXTURE)
    before = _tmp_artifacts(tmp_path)

    # После refactor'а helper'а в context manager — `with` block
    # моделирует жизненный цикл prepared netlist'а в CLI handler'е.
    with _prepare_ac_netlist(
        netlist_path=netlist,
        netlist_editor=NgspiceNetlistEditor(),
        explicit_source=None,
    ) as prepared:
        assert prepared.exists()

    after = _tmp_artifacts(tmp_path)
    leaked = after - before
    assert not leaked, (
        f'_prepare_ac_netlist оставил temp файлы в '
        f'{tmp_path}: {sorted(p.name for p in leaked)}'
    )

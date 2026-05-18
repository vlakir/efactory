"""NgspiceSimulator: wrapper-логика (unit с FakeAppManager) + integration с ngspice (T008)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.ngspice.wrapper import build_wrapper
from domain.application import ApplicationKind
from domain.simulation import (
    AcAnalysis,
    OpAnalysis,
    TranAnalysis,
)
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
    RunResult,
)
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed (apt install ngspice / brew install ngspice)',
)


class FakeAppManager:
    """AppManager double — фиксирует argv, возвращает заданный RunResult."""

    def __init__(
        self,
        *,
        result: RunResult | None = None,
        raises: Exception | None = None,
        side_effect: Callable[[], None] | None = None,
    ) -> None:
        self._result = result
        self._raises = raises
        self._side_effect = side_effect
        self.calls: list[tuple[ApplicationKind, list[str], float | None]] = []

    async def status(self, kind: ApplicationKind):  # noqa: ARG002,ANN201
        raise NotImplementedError

    async def launch(self, kind, args=None):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError

    async def run(
        self,
        kind: ApplicationKind,
        args: list[str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> RunResult:
        self.calls.append((kind, list(args or []), timeout_seconds))
        if self._side_effect is not None:
            self._side_effect()
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result

    async def stop(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError

    async def restart(self, kind):  # noqa: ARG002,ANN001,ANN201
        raise NotImplementedError


# ---------- wrapper generation (unit) ----------


def test_build_wrapper_op_directive() -> None:
    netlist = '* sample\nV1 in 0 1\nR1 in 0 1k\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(netlist, OpAnalysis(), raw)

    assert 'V1 in 0 1' in wrapper
    assert '.OP' in wrapper
    assert 'set filetype=ascii' in wrapper
    assert f'write {raw} all' in wrapper
    assert wrapper.rstrip().endswith('.END')


def test_build_wrapper_tran_directive_with_defaults() -> None:
    netlist = '* sample\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(
        netlist,
        TranAnalysis(t_step=1e-5, t_stop=20e-3),
        raw,
    )

    assert '.TRAN' in wrapper
    # t_step и t_stop обязательны
    assert '1e-05' in wrapper or '1e-5' in wrapper
    assert '0.02' in wrapper
    # t_start=0 не передаётся (default)
    # uic=False — нет ключевого слова
    assert 'UIC' not in wrapper


def test_build_wrapper_tran_with_t_start_and_uic() -> None:
    netlist = '* sample\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(
        netlist,
        TranAnalysis(t_step=1e-5, t_stop=20e-3, t_start=1e-3, uic=True),
        raw,
    )

    assert '.TRAN' in wrapper
    assert '0.001' in wrapper
    assert 'UIC' in wrapper


def test_build_wrapper_ac_directive() -> None:
    netlist = '* sample\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(
        netlist,
        AcAnalysis(sweep='dec', n_points=20, f_start=1.0, f_stop=1e6),
        raw,
    )

    assert '.AC dec 20 1' in wrapper
    assert '1000000' in wrapper or '1e+06' in wrapper or '1e6' in wrapper


def test_build_wrapper_strips_dot_end_from_netlist() -> None:
    netlist = '* sample\nV1 in 0 1\nR1 in 0 1k\n.end\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(netlist, OpAnalysis(), raw)

    # `.end` из netlist (отдельная строка) удалён; собственный `.END` обёртки
    # остался ровно один как последняя осмысленная строка.
    netlist_lines = [
        line for line in wrapper.splitlines() if line.strip().lower() == '.end'
    ]
    assert netlist_lines == ['.END']
    assert wrapper.rstrip().endswith('.END')


# ---------- adapter с FakeAppManager ----------


async def _write_netlist(tmp_path: Path) -> Path:
    netlist = tmp_path / 'rc.cir'
    netlist.write_text('* rc\nV1 in 0 1\nR1 in out 1k\nC1 out 0 1u\n')
    return netlist


async def test_run_invokes_app_manager_with_b_flag(tmp_path: Path) -> None:
    netlist = await _write_netlist(tmp_path)
    raw_text = (
        'Title: t\nDate: d\nCommand: c\nPlotname: Operating Point\n'
        'Flags: real\nNo. Variables: 1\nNo. Points: 1\n'
        'Variables:\n\t0\tv(in)\tvoltage\nValues:\n 0\t1.0\n'
    )

    def write_raw_side_effect() -> None:
        raw = netlist.parent / f'{netlist.stem}.raw'
        raw.write_text(raw_text)

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        side_effect=write_raw_side_effect,
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    result = await simulator.run(netlist, OpAnalysis())

    assert result.operating_points == {'v(in)': 1.0}
    assert len(app_manager.calls) == 1
    kind, args, timeout = app_manager.calls[0]
    assert kind is ApplicationKind.NGSPICE
    assert args[0] == '-b'
    assert args[1].endswith('.wrapper.cir')
    assert timeout == 60.0


async def test_run_raises_unavailable_when_ngspice_not_installed(
    tmp_path: Path,
) -> None:
    netlist = await _write_netlist(tmp_path)
    app_manager = FakeAppManager(
        raises=ApplicationNotInstalledError('no ngspice'),
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    with pytest.raises(SimulatorUnavailableError, match='ngspice'):
        await simulator.run(netlist, OpAnalysis())


async def test_run_raises_failed_on_non_zero_exit(tmp_path: Path) -> None:
    netlist = await _write_netlist(tmp_path)
    app_manager = FakeAppManager(
        result=RunResult(1, '', 'Error: parsing failed\n'),
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    with pytest.raises(SimulationFailedError, match='exit 1'):
        await simulator.run(netlist, OpAnalysis())


async def test_run_raises_failed_on_app_start_error(tmp_path: Path) -> None:
    netlist = await _write_netlist(tmp_path)
    app_manager = FakeAppManager(
        raises=ApplicationStartError('cannot start ngspice'),
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    with pytest.raises(SimulationFailedError, match='cannot start'):
        await simulator.run(netlist, OpAnalysis())


async def test_run_raises_failed_when_raw_missing(tmp_path: Path) -> None:
    netlist = await _write_netlist(tmp_path)
    # exit 0, но raw файл не создан — broken ngspice scenario.
    app_manager = FakeAppManager(result=RunResult(0, '', ''))
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    with pytest.raises(SimulationFailedError, match='raw'):
        await simulator.run(netlist, OpAnalysis())


async def test_run_propagates_custom_timeout(tmp_path: Path) -> None:
    netlist = await _write_netlist(tmp_path)
    raw_text = (
        'Title: t\nDate: d\nCommand: c\nPlotname: Operating Point\n'
        'Flags: real\nNo. Variables: 1\nNo. Points: 1\n'
        'Variables:\n\t0\tv(in)\tvoltage\nValues:\n 0\t1.0\n'
    )

    def write_raw_side_effect() -> None:
        (netlist.parent / f'{netlist.stem}.raw').write_text(raw_text)

    app_manager = FakeAppManager(
        result=RunResult(0, '', ''),
        side_effect=write_raw_side_effect,
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    await simulator.run(netlist, OpAnalysis(), timeout_seconds=5.0)

    _, _, timeout = app_manager.calls[0]
    assert timeout == 5.0


# ---------- integration с реальным ngspice ----------


@needs_ngspice
async def test_integration_op_on_rc_filter(tmp_path: Path) -> None:
    """RC: V(in)=1V → V(out)=1V в OP (без нагрузки на ёмкости в DC)."""
    from adapters.outbound.platform_native.platform_layer import (
        NativePlatformLayer,
    )
    from adapters.outbound.subprocess_apps.app_manager import (
        SubprocessAppManager,
    )

    netlist = tmp_path / 'rc.cir'
    netlist.write_text(
        '* rc filter\nV1 in 0 DC 1\nR1 in out 1k\nC1 out 0 1u\n',
    )
    app_manager = SubprocessAppManager(NativePlatformLayer())
    simulator = NgspiceSimulator(app_manager)

    result = await simulator.run(netlist, OpAnalysis())

    assert result.operating_points is not None
    assert result.operating_points['v(in)'] == pytest.approx(1.0, abs=1e-6)
    assert result.operating_points['v(out)'] == pytest.approx(1.0, abs=1e-6)


@needs_ngspice
async def test_integration_tran_on_rc_filter(tmp_path: Path) -> None:
    netlist = tmp_path / 'rc.cir'
    netlist.write_text(
        '* rc tran\nV1 in 0 DC 1\nR1 in out 1k\nC1 out 0 1u\n',
    )
    app_manager_local = _make_local_app_manager()
    simulator = NgspiceSimulator(app_manager_local)

    result = await simulator.run(
        netlist,
        TranAnalysis(t_step=5e-4, t_stop=2e-3),
    )

    assert result.time_series is not None
    ts = result.time_series
    assert ts.time[0] == pytest.approx(0.0, abs=1e-9)
    assert ts.time[-1] == pytest.approx(2e-3, abs=1e-9)
    assert 'v(in)' in ts.traces
    assert 'v(out)' in ts.traces
    # DC source → v(in) держится 1V на всём интервале
    for v in ts.traces['v(in)']:
        assert v == pytest.approx(1.0, abs=1e-6)


@needs_ngspice
async def test_integration_ac_on_rc_filter(tmp_path: Path) -> None:
    """RC AC: fc = 1/(2π·R·C) ≈ 159.15 Hz, |H(fc)| ≈ -3 dB."""
    netlist = tmp_path / 'rc.cir'
    # Для AC источник должен иметь AC-параметр
    netlist.write_text(
        '* rc ac\nV1 in 0 AC 1\nR1 in out 1k\nC1 out 0 1u\n',
    )
    app_manager_local = _make_local_app_manager()
    simulator = NgspiceSimulator(app_manager_local)

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=10, f_start=10.0, f_stop=10000.0),
    )

    assert result.ac_sweep is not None
    ac = result.ac_sweep
    assert ac.frequency[0] == pytest.approx(10.0, rel=1e-3)
    assert ac.frequency[-1] == pytest.approx(10000.0, rel=1e-3)
    assert 'v(out)' in ac.traces_real
    assert 'v(out)' in ac.traces_imag
    # Проверяем магнитуду V(out) на fc ≈ 159.15 Hz: |H| ≈ 1/√2 ≈ 0.707
    fc_idx = _closest_index(ac.frequency, 159.15)
    real = ac.traces_real['v(out)'][fc_idx]
    imag = ac.traces_imag['v(out)'][fc_idx]
    magnitude = (real * real + imag * imag) ** 0.5
    assert magnitude == pytest.approx(0.707, abs=0.05)


@needs_ngspice
async def test_integration_raises_failed_on_broken_netlist(
    tmp_path: Path,
) -> None:
    netlist = tmp_path / 'bad.cir'
    netlist.write_text('* invalid\nGARBAGE LINE HERE\n')
    app_manager_local = _make_local_app_manager()
    simulator = NgspiceSimulator(app_manager_local)

    with pytest.raises(SimulationFailedError):
        await simulator.run(netlist, OpAnalysis())


def _make_local_app_manager():  # noqa: ANN202
    from adapters.outbound.platform_native.platform_layer import (
        NativePlatformLayer,
    )
    from adapters.outbound.subprocess_apps.app_manager import (
        SubprocessAppManager,
    )

    return SubprocessAppManager(NativePlatformLayer())


def _closest_index(values: tuple[float, ...], target: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - target))

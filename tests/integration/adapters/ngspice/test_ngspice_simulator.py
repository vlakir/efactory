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
    FourierAnalysis,
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


def test_build_wrapper_fourier_directive() -> None:
    netlist = '* sample\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(
        netlist,
        FourierAnalysis(
            tran=TranAnalysis(t_step=1e-5, t_stop=10e-3),
            fundamental_hz=1000.0,
            n_harmonics=10,
            signal='v(load)',
        ),
        raw,
    )

    # ngspice требует .tran top-level + `fourier` interactive в .control
    # (top-level `.four` директива не процессится при наличии .control).
    assert '.TRAN' in wrapper
    assert 'set nfreqs=10' in wrapper
    assert 'fourier 1000' in wrapper
    assert 'v(load)' in wrapper
    # `fourier` команда должна идти после `run`, иначе ngspice не имеет
    # transient data для анализа.
    run_pos = wrapper.find('  run\n')
    fourier_pos = wrapper.find('fourier 1000')
    assert 0 < run_pos < fourier_pos


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


def test_build_wrapper_strips_embedded_analysis_directive(
    embedded: str,
) -> None:
    """
    T144 root-cause: KiCad SPICE export встраивает sim-command (`.tran`,
    `.ac` и т.п.) в netlist из `.kicad_sch` Simulator-секции. Если её
    оставить, ngspice выполнит **её** при `run`, а наш appended `.OP`
    (или другой override) останется в queue и `write all` напишет
    результаты не той analysis → operating_points={}.

    Фикс: стрипим **все** top-level analysis directives из netlist
    перед вставкой собственной.
    """
    netlist = (
        '* tube schematic with embedded directive\n'
        f'{embedded}\n'
        'V1 in 0 dc=1\nR1 in 0 1k\n'
    )
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(netlist, OpAnalysis(), raw)

    # Точная embedded строка не должна остаться (line-based, чтобы
    # не путаться с appended `.OP` от `OpAnalysis` в случае
    # embedded='.OP').
    wrapper_lines = [line.strip() for line in wrapper.splitlines()]
    assert embedded.strip() not in wrapper_lines
    # Наша `.OP` директива добавлена ровно одна.
    op_lines = [line for line in wrapper_lines if line == '.OP']
    assert op_lines == ['.OP']


# pytest.fixture parametrize: каждая директива, которую KiCad может встроить.
# `.op` без args вынесен в отдельный тест ниже — он collide'ит с appended
# `.OP` от `OpAnalysis()`, не distinguishable line-based assertion'ом.
@pytest.fixture(
    params=[
        '.tran 10u 80m 10m uic',
        '.tran 1us 1ms',
        '.ac dec 10 1 1Meg',
        '.AC dec 100 10 1k',
        '.dc V1 0 5 0.1',
        '.four 1000 v(out)',
        '.noise v(out) V1 dec 10 1 1Meg',
        '.tf v(out) V1',
        '.sens v(out)',
        '.disto dec 10 1k 10k',
        '  .tran 1u 1m',  # leading whitespace ignored
    ],
)
def embedded(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.mark.parametrize('embedded_op', ['.op', '.OP'])
def test_build_wrapper_strips_embedded_op_without_collision(
    embedded_op: str,
) -> None:
    """
    Edge: embedded `.op`/`.OP` collide с appended `.OP` от
    `OpAnalysis()`. Проверяем через `TranAnalysis` (appended `.TRAN`,
    не `.OP`) — тогда `.OP` в wrapper'е должен полностью отсутствовать.
    """
    netlist = f'* embedded {embedded_op}\n{embedded_op}\nV1 in 0 1\nR1 in 0 1k\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(
        netlist,
        TranAnalysis(t_step=1e-6, t_stop=1e-3),
        raw,
    )

    wrapper_lines = [line.strip().lower() for line in wrapper.splitlines()]
    assert '.op' not in wrapper_lines
    assert any(line.startswith('.tran') for line in wrapper_lines)


def test_build_wrapper_keeps_user_comments_and_components() -> None:
    """
    Стрип analysis directives не должен задеть комменты и компоненты,
    даже если их строка начинается с похожей подстроки (e.g. `.subckt`).
    """
    netlist = (
        '* .tran demo\n'  # comment упоминающий .tran
        '.subckt MY_BLOCK in out\n'
        '  R_internal in out 10k\n'
        '.ends MY_BLOCK\n'
        'V1 in 0 dc=1\nR1 in 0 1k\n'
        '.tran 1u 1m\n'  # actual directive — должна уйти
    )
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(netlist, OpAnalysis(), raw)

    # Комменты и subckt сохранены.
    assert '* .tran demo' in wrapper
    assert '.subckt MY_BLOCK' in wrapper
    assert '.ends MY_BLOCK' in wrapper
    # Реальная .tran директива удалена.
    tran_lines = [
        line for line in wrapper.splitlines()
        if line.strip().lower().startswith('.tran')
    ]
    assert tran_lines == []
    assert '.OP' in wrapper


def test_build_wrapper_substitutes_gnd_token_with_zero() -> None:
    """KiCad SPICE export даёт ground как `GND`; ngspice требует `0`."""
    netlist = '* rc\nV1 GND /in dc=1\nR1 /in /out 1k\nC1 /out GND 1u\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(netlist, OpAnalysis(), raw)

    assert 'V1 0 /in dc=1' in wrapper
    assert 'C1 /out 0 1u' in wrapper
    # Не должно остаться bare GND как net-токена.
    assert ' GND ' not in wrapper
    assert wrapper.count('GND') == 0  # nothing GND-related leftover


def test_build_wrapper_does_not_substitute_gnd_inside_other_words() -> None:
    """`AGND` / `DGND` / `IGNDR1` остаются неизменными — substitute только bare `GND`."""
    netlist = '* sample\nV1 AGND /in dc=1\nR1 /in DGND 1k\n'
    raw = Path('/tmp/out.raw')

    wrapper = build_wrapper(netlist, OpAnalysis(), raw)

    assert 'AGND' in wrapper
    assert 'DGND' in wrapper


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


async def test_run_fourier_parses_stdout_for_four_block(
    tmp_path: Path,
) -> None:
    netlist = await _write_netlist(tmp_path)
    raw_text = (
        'Title: t\nDate: d\nCommand: c\nPlotname: Transient Analysis\n'
        'Flags: real\nNo. Variables: 2\nNo. Points: 1\n'
        'Variables:\n\t0\ttime\ttime\n\t1\tv(load)\tvoltage\n'
        'Values:\n 0\t0.0\n\t1.0\n'
    )
    fourier_stdout = (
        'Fourier analysis for v(load):\n'
        '  No. Harmonics: 10, THD: 2.5 %, '
        'Gridsize: 200, Interpolation Degree: 1\n'
        '\n'
        'Harmonic  Frequency        Magnitude     Phase       '
        'Norm. Mag    Norm. Phase\n'
        '--------  ---------        ---------     -----       '
        '---------    -----------\n'
        '0         0                0.001         0           0            0\n'
        '1         1000             1.0           0           1            0\n'
        '2         2000             0.025         0           0.025        0\n'
        '3         3000             0.0125        0           0.0125       0\n'
        '4         4000             0.00625       0           0.00625      0\n'
        '5         5000             0.003125      0           0.003125     0\n'
        '6         6000             0.0015625     0           0.0015625    0\n'
        '7         7000             0.00078125    0           0.00078125   0\n'
        '8         8000             0.000390625   0           0.000390625  0\n'
        '9         9000             0.0001953125  0           0.0001953125 0\n'
    )

    def write_raw_side_effect() -> None:
        raw = netlist.parent / f'{netlist.stem}.raw'
        raw.write_text(raw_text)

    app_manager = FakeAppManager(
        result=RunResult(0, fourier_stdout, ''),
        side_effect=write_raw_side_effect,
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    analysis = FourierAnalysis(
        tran=TranAnalysis(t_step=1e-5, t_stop=10e-3),
        fundamental_hz=1000.0,
        n_harmonics=10,
        signal='v(load)',
    )
    result = await simulator.run(netlist, analysis)

    assert result.fourier_result is not None
    assert result.fourier_result.thd_percent == 2.5
    assert result.fourier_result.fundamental_hz == 1000.0
    assert len(result.fourier_result.harmonics) == 10
    assert result.time_series is None
    assert result.operating_points is None
    assert result.ac_sweep is None


async def test_run_fourier_raises_when_block_missing(tmp_path: Path) -> None:
    netlist = await _write_netlist(tmp_path)
    raw_text = (
        'Title: t\nDate: d\nCommand: c\nPlotname: Transient Analysis\n'
        'Flags: real\nNo. Variables: 2\nNo. Points: 1\n'
        'Variables:\n\t0\ttime\ttime\n\t1\tv(load)\tvoltage\n'
        'Values:\n 0\t0.0\n\t1.0\n'
    )

    def write_raw_side_effect() -> None:
        (netlist.parent / f'{netlist.stem}.raw').write_text(raw_text)

    app_manager = FakeAppManager(
        result=RunResult(0, 'ngspice ran but no .four block emitted', ''),
        side_effect=write_raw_side_effect,
    )
    simulator = NgspiceSimulator(app_manager)  # type: ignore[arg-type]

    analysis = FourierAnalysis(
        tran=TranAnalysis(t_step=1e-5, t_stop=10e-3),
        fundamental_hz=1000.0,
        n_harmonics=10,
        signal='v(load)',
    )

    with pytest.raises(SimulationFailedError, match='.four'):
        await simulator.run(netlist, analysis)


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
async def test_integration_fourier_on_pure_sine_returns_low_thd(
    tmp_path: Path,
) -> None:
    """Чистый sin-источник на R-нагрузке → THD ≈ 0 (numerical noise only)."""
    netlist = tmp_path / 'sine.cir'
    netlist.write_text(
        '* pure sine\n'
        'V1 in 0 SIN(0 1 1000)\n'
        'R1 in 0 1k\n',
    )
    app_manager_local = _make_local_app_manager()
    simulator = NgspiceSimulator(app_manager_local)

    analysis = FourierAnalysis(
        tran=TranAnalysis(t_step=1e-6, t_stop=10e-3),
        fundamental_hz=1000.0,
        n_harmonics=10,
        signal='v(in)',
    )
    result = await simulator.run(netlist, analysis)

    assert result.fourier_result is not None
    fr = result.fourier_result
    assert fr.fundamental_hz == pytest.approx(1000.0, rel=1e-3)
    # Чистый sin: только численный noise — THD < 1%.
    assert fr.thd_percent < 1.0
    assert len(fr.harmonics) == 10
    # n=1 — fundamental, должен быть ≈ 1V amplitude (peak).
    fundamental = next(h for h in fr.harmonics if h.n == 1)
    assert fundamental.magnitude == pytest.approx(1.0, abs=0.05)


@needs_ngspice
async def test_integration_fourier_on_clipped_sine_returns_high_thd(
    tmp_path: Path,
) -> None:
    """Hard-clipped sin (tanh ≈ saturation) → THD > 10%, нечётные гармоники."""
    netlist = tmp_path / 'clip.cir'
    netlist.write_text(
        '* tanh clipping\n'
        'V1 in 0 SIN(0 1 1000)\n'
        'B1 out 0 V = tanh(5*V(in))\n'
        'R1 out 0 1k\n',
    )
    app_manager_local = _make_local_app_manager()
    simulator = NgspiceSimulator(app_manager_local)

    analysis = FourierAnalysis(
        tran=TranAnalysis(t_step=1e-6, t_stop=10e-3),
        fundamental_hz=1000.0,
        n_harmonics=10,
        signal='v(out)',
    )
    result = await simulator.run(netlist, analysis)

    assert result.fourier_result is not None
    fr = result.fourier_result
    assert fr.thd_percent > 10.0
    # tanh-clip — symmetric нелинейность → доминируют нечётные гармоники
    # (n=3, 5). Чётные (n=2, 4) близки к нулю.
    h3 = next(h for h in fr.harmonics if h.n == 3)
    h2 = next(h for h in fr.harmonics if h.n == 2)
    assert h3.normalized > h2.normalized


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

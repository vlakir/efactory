"""T102 smoke: ngspice прогоняет патченные tube .lib без PWRS-ошибки.

Узкая интеграция — не зависит ни от фасада `efactory.schematic`, ни от
`kicad-cli`. Берём один из патченных файлов (`6N1P.lib`), кладём
минимальный inline netlist с `.include` на него и `.op`-анализом,
прогоняем `NgspiceSimulator`. Acceptance — нет `SimulationFailedError`
из-за `no such function 'pwrs'`. Plate-current сравниваем по знаку
(triode проводит → положительный V на нагрузке), но не по точной
величине — это smoke, не модельный verifier.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from domain.simulation import OpAnalysis

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed (apt install ngspice / brew install ngspice)',
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TUBE_LIB = _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6N1P.lib'


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


@needs_ngspice
async def test_ngspice_runs_patched_tube_subckt_without_pwrs_error(
    tmp_path: Path,
) -> None:
    """6N1P (T102-patched) парсится ngspice без `no such function 'pwrs'`."""
    assert _TUBE_LIB.is_file(), f'Missing tube .lib: {_TUBE_LIB}'

    # Triode 6N1P в diode-connected режиме (G замкнут на P через 0-Ω).
    # V_supply 100 V → R_p 10k → P/G → K → GND. С такой нагрузкой через
    # лампу должен течь анодный ток ~1-2 mA, V(p) сядет на 80-95 В.
    netlist = tmp_path / 'triode_smoke.cir'
    netlist.write_text(
        f"""\
* T102 smoke — patched 6N1P без PWRS
.include "{_TUBE_LIB}"
V1 vp 0 DC 100
R1 vp p 10k
XV1 p p k 6N1P
R2 k 0 1
.end
""",
    )
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(netlist, OpAnalysis())

    assert result.operating_points is not None, (
        'ngspice did not return DC OP — likely subckt parse failure'
    )
    op = result.operating_points
    # Лампа проводит → V(p) < V_supply (есть падение на R1).
    v_p = op.get('v(p)')
    assert v_p is not None, f'V(p) not present in OP: {op}'
    assert 5.0 < v_p < 99.5, (
        f'V(p)={v_p:.3f} V — за пределами разумного для diode-mode '
        f'6N1P (ожидаем заметное падение на R1=10k, но лампа не closed)'
    )

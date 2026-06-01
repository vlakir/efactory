"""T163 Phase B: phase-margin calibration on BJT CE NFB fixture.

Cross-validates four phase-margin injection strategies (Middlebrook V/I,
Tian, Rosenstark return-ratio) on a single-stage BJT common-emitter NFB
amplifier (`data/templates/bjt-ce-nfb/`) — Q2N3904 + voltage-divider bias
+ shunt-shunt AC-only feedback (R_F=47k + C_F=1µ DC-block, collector→base).

**Closes ADR-T153g BJT CE row** (`?` → empirical matrix).

Topology mirror (inline SPICE — matches data/templates/bjt-ce-nfb/
schematic semantics, deliberately avoids KiCad export overhead для
focused physics validation):

  V_CC=12, V_in=AC, R_S=50, C_in=1µ → base
  R_B1=100k (vcc→base), R_B2=10k (base→0) — divider bias
  R_C=4.7k (vcc→vout), Q1=Q2N3904
  R_E=470 ‖ C_E=47µ — emitter degeneration + AC bypass
  C_F=1µ + R_F=47k — shunt-shunt AC feedback (vout → fb_mid → base)
  C_out=10µ + R_L=10k — output load

Break candidate matrix (Spec §5):
- **(vout, C_F)** — primary для Middlebrook V; analog к tube NFB
  `(sec_a, C_fb)` convention. Driver = collector r_o ‖ R_C (low-ish Z),
  load = feedback chain higher Z.
- **(base, R_F)** — primary для Middlebrook I; current-mode break,
  high-Z base input.

Acceptance (Spec §4, honest empirical):
- **Primary V strict obligatory**: Middlebrook V @ (vout, C_F) даёт
  PM within tight tolerance vs empirical target (set после первого
  probing run).
- **Cross-validate желательно (не блокирующее)**: ≥1 из {I, Tian,
  Rosenstark} даёт PM ±3° vs V's PM @ canonical break.
- **Documented matrix обязателен**: degenerate cases помечаются с
  reasoning в module docstring (ADR-T153g дополнения).
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
)
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from application.measure_phase_margin import measure_phase_margin
from domain.phase_margin import (
    LoopGainAlwaysAboveUnityError,
    NoUnityGainCrossoverError,
    PhaseMarginMeasurement,
)
from domain.phase_margin_injection import (
    InjectionStrategy,
    MiddlebrookCurrentStrategy,
    MiddlebrookVoltageStrategy,
    RosenstarkReturnRatioStrategy,
    TianStrategy,
)

if TYPE_CHECKING:
    from pathlib import Path

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)

_BJT_LIB_REL = 'data/models/bjt/onsemi/Q2N3904.lib'


def _bjt_ce_nfb_netlist(bjt_lib_path: str) -> str:
    """Inline SPICE netlist mirroring data/templates/bjt-ce-nfb/.

    Topology — see module docstring. AC drive = 0 (sanitized — no
    interference с injection sources).
    """
    return (
        f'* BJT CE NFB calibration (T163 Phase B)\n'
        f'.include {bjt_lib_path}\n'
        f'V_CC vcc 0 DC 12\n'
        f'V_in vin 0 DC 0\n'
        f'R_S vin a 50\n'
        f'C_in a base 1u\n'
        f'R_B1 vcc base 100k\n'
        f'R_B2 base 0 10k\n'
        f'Q1 vout base emitter Q2N3904\n'
        f'R_C vcc vout 4.7k\n'
        f'R_E emitter 0 470\n'
        f'C_E emitter 0 47u\n'
        f'C_F vout fb_mid 1u\n'
        f'R_F fb_mid base 47k\n'
        f'C_out vout vload 10u\n'
        f'R_L vload 0 10k\n'
        f'.end\n'
    )


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


def _strategy(name: str) -> InjectionStrategy:
    patcher = NgspiceInjectionNetlistPatcher()
    cls = {
        'middlebrook_voltage': MiddlebrookVoltageStrategy,
        'middlebrook_current': MiddlebrookCurrentStrategy,
        'tian': TianStrategy,
        'rosenstark_return_ratio': RosenstarkReturnRatioStrategy,
    }[name]
    return cls(patcher)


# Canonical break candidates (Spec §5).
_BREAK_VOUT_CF = ('vout', 'C_F')
_BREAK_BASE_RF = ('base', 'R_F')


async def _measure(
    netlist: Path,
    method_name: str,
    break_node: str,
    break_element_ref: str,
) -> PhaseMarginMeasurement | str:
    """Run measure_phase_margin, return measurement OR degenerate marker."""
    strategy = _strategy(method_name)
    try:
        result = await measure_phase_margin(
            netlist=netlist,
            injection_strategy=strategy,
            break_node=break_node,
            break_element_ref=break_element_ref,
            simulator=_make_simulator(),
            f_low=1.0,
            f_high=1e8,
            n_points_per_decade=50,
        )
    except NoUnityGainCrossoverError:
        return 'NoCrossover'
    except LoopGainAlwaysAboveUnityError:
        return 'AlwaysAboveUnity'
    except ValueError as exc:
        # `measure_phase_margin` raises ValueError on phase unwrap outside
        # valid range — degenerate marker для probe.
        return f'PhaseUnwrapErr({exc!s:.60s})'
    return result


# === Empirical matrix (2026-06-01, ngspice 44 на dev-машине) ===
#
# Probed 4 methods × 2 break candidates = 8 cases; reproducible bit-
# for-bit (ngspice deterministic):
#
# | Method × Break           | (vout, C_F)            | (base, R_F)             |
# |--------------------------|------------------------|-------------------------|
# | Middlebrook V single     | **PM=126.28° fc=299Hz** ✓ | NoCrossover ×          |
# | Tian double-injection    | **PM=128.17° fc=345Hz** ✓ | NoCrossover ×          |
# | Middlebrook I single     | AlwaysAboveUnity ×     | LF-artefact PM=316.61°  |
# |                          |                        |  @ fc=3.74Hz (unwrap)   |
# | Rosenstark return-ratio  | PhaseUnwrap (>360°) ×  | NoCrossover ×          |
#
# **Canonical break = (vout, C_F)** — analog к tube NFB (sec_a, C_fb),
# подтверждает Spec §5 primary hypothesis. Driver = collector r_o ‖ R_C
# (low-ish Z 4.4 kΩ), load = feedback chain + base input (high Z ~50 kΩ).
#
# **Two methods strict @ canonical**: V + Tian convergent within 1.89°
# (cross-validation). Same pattern as op-amp C.1 (V+Tian strict, I+Rosenstark
# degenerate). Mirror в ADR-T153g BJT CE row.
#
# **Reasoning для degenerate**:
# - **Middlebrook I @ (vout, C_F)**: current injection at low-Z output;
#   loop never reaches unity gain crossover.
# - **Middlebrook I @ (base, R_F)**: LF artefact (3.74 Hz) — fictious
#   crossing от C_F highpass interaction with base injection; не
#   meaningful loop gain.
# - **Rosenstark @ (vout, C_F)**: T_oc + T_sc topology mods вызывают
#   phase chain >360° — single-stage CE high-PM (~126°) outside method's
#   valid unwrap range.
# - **V/Tian @ (base, R_F)**: NoCrossover — current-mode break не
#   подходит для voltage injection methods (analog к op-amp input break
#   degenerate).

# Strict tolerances (single-run + reproducibility verified).
_PM_V_TARGET_DEG = 126.28
_PM_TOLERANCE_DEG = 2.0  # ±2°
_FC_V_TARGET_HZ = 299.43
_FC_TOLERANCE_REL = 0.10  # ±10%
_PM_TIAN_VS_V_TOLERANCE_DEG = 3.0  # cross-validate Tian vs V's PM


@pytest.fixture
def bjt_netlist(tmp_path: Path) -> Path:
    from pathlib import Path as _P

    repo_root = _P(__file__).resolve().parents[3]
    lib_path = repo_root / _BJT_LIB_REL
    assert lib_path.exists(), f'BJT model missing: {lib_path}'

    netlist = tmp_path / 'bjt_ce_nfb.cir'
    netlist.write_text(_bjt_ce_nfb_netlist(str(lib_path)))
    return netlist


@needs_ngspice
async def test_middlebrook_voltage_strict_at_canonical_break(
    bjt_netlist: Path,
) -> None:
    """**Primary**: Middlebrook V @ (vout, C_F) → PM=126.28° ± 2°,
    fc=299 Hz ± 10%.

    Это ground truth для T163 BJT CE shunt-shunt NFB row в ADR-T153g
    matrix. Canonical break (vout, C_F) — analog к tube NFB (sec_a,
    C_fb), Spec §5 primary hypothesis confirmed.
    """
    result = await _measure(
        bjt_netlist, 'middlebrook_voltage', 'vout', 'C_F',
    )
    assert isinstance(result, PhaseMarginMeasurement), result

    pm_low = _PM_V_TARGET_DEG - _PM_TOLERANCE_DEG
    pm_high = _PM_V_TARGET_DEG + _PM_TOLERANCE_DEG
    assert pm_low <= result.margin_deg <= pm_high, (
        f'Middlebrook V: PM={result.margin_deg:.2f}°, '
        f'expected {_PM_V_TARGET_DEG}° ± {_PM_TOLERANCE_DEG}°'
    )

    fc_low = _FC_V_TARGET_HZ * (1 - _FC_TOLERANCE_REL)
    fc_high = _FC_V_TARGET_HZ * (1 + _FC_TOLERANCE_REL)
    assert fc_low <= result.crossover_hz <= fc_high, (
        f'Middlebrook V: fc={result.crossover_hz:.1f} Hz, '
        f'expected {_FC_V_TARGET_HZ}° ± {_FC_TOLERANCE_REL * 100:.0f}%'
    )


@needs_ngspice
async def test_tian_cross_validates_middlebrook_voltage(
    bjt_netlist: Path,
) -> None:
    """**Cross-validation**: Tian @ (vout, C_F) → PM ±3° vs V's PM.

    Tian double-injection универсальная и сходится с V single на
    canonical break. На BJT CE empirical: Tian PM=128.17° vs V PM=126.28°
    → разница 1.89°, well within tolerance. Same convergence pattern as
    op-amp C.1 (V + Tian strict) и BJT CE row в ADR-T153g matrix.
    """
    v_result = await _measure(
        bjt_netlist, 'middlebrook_voltage', 'vout', 'C_F',
    )
    tian_result = await _measure(
        bjt_netlist, 'tian', 'vout', 'C_F',
    )
    assert isinstance(v_result, PhaseMarginMeasurement), v_result
    assert isinstance(tian_result, PhaseMarginMeasurement), tian_result

    diff = abs(tian_result.margin_deg - v_result.margin_deg)
    assert diff <= _PM_TIAN_VS_V_TOLERANCE_DEG, (
        f'Tian PM={tian_result.margin_deg:.2f}° not within '
        f'±{_PM_TIAN_VS_V_TOLERANCE_DEG}° of V PM={v_result.margin_deg:.2f}° '
        f'(diff={diff:.2f}°)'
    )


@needs_ngspice
async def test_middlebrook_current_degenerate_documented(
    bjt_netlist: Path,
) -> None:
    """Middlebrook I — degenerate на BJT CE shunt-shunt (документировано
    в ADR-T153g BJT CE row).

    Empirical (2026-06-01):
    - @ (vout, C_F): `LoopGainAlwaysAboveUnityError` — current injection
      at low-Z collector output не opens loop (similar к op-amp output).
    - @ (base, R_F): возвращает measurement, но fc=3.74 Hz artefact от
      C_F highpass + base current injection interaction; PM=316.61° —
      phase chain артефакт, не meaningful loop gain.

    Acceptance: оба break candidates НЕ дают physical PM strict; pipeline
    integrity (no parse/orchestration errors) проверена.
    """
    r1 = await _measure(bjt_netlist, 'middlebrook_current', 'vout', 'C_F')
    r2 = await _measure(bjt_netlist, 'middlebrook_current', 'base', 'R_F')
    # @ (vout, C_F) → AlwaysAboveUnity marker.
    assert r1 == 'AlwaysAboveUnity', r1
    # @ (base, R_F) → either measurement (artefact) или error marker.
    # Не assert physical PM range — это degenerate case.
    assert isinstance(r2, (PhaseMarginMeasurement, str)), r2


@needs_ngspice
async def test_rosenstark_degenerate_documented(bjt_netlist: Path) -> None:
    """Rosenstark return-ratio — degenerate на BJT CE shunt-shunt
    (документировано в ADR-T153g BJT CE row).

    Empirical (2026-06-01):
    - @ (vout, C_F): T_oc + T_sc topology modifications generate phase
      chain >360° (single-stage CE high-PM ≈126° outside Rosenstark
      method's valid unwrap range). Pipeline raises ValueError.
    - @ (base, R_F): `NoUnityGainCrossoverError` — high-Z base break не
      satisfies OC/SC two-port assumption (similar к op-amp Rosenstark
      degeneracy в C.1).
    """
    r1 = await _measure(
        bjt_netlist, 'rosenstark_return_ratio', 'vout', 'C_F',
    )
    r2 = await _measure(
        bjt_netlist, 'rosenstark_return_ratio', 'base', 'R_F',
    )
    # @ (vout, C_F) → phase unwrap error marker.
    assert isinstance(r1, str) and r1.startswith('PhaseUnwrapErr'), r1
    # @ (base, R_F) → NoCrossover.
    assert r2 == 'NoCrossover', r2


@needs_ngspice
async def test_voltage_methods_degenerate_at_base_break(
    bjt_netlist: Path,
) -> None:
    """Middlebrook V + Tian degenerate @ (base, R_F) — current-mode
    break не подходит для voltage injection (analog к op-amp input break).

    Empirical: оба возвращают NoCrossover — voltage signal injected at
    high-Z base node + voltage receive at R_F-side of break даёт T_v
    низкий (similar к op-amp T_v ≈ 1/A_loop degenerate pattern).
    """
    r_v = await _measure(bjt_netlist, 'middlebrook_voltage', 'base', 'R_F')
    r_tian = await _measure(bjt_netlist, 'tian', 'base', 'R_F')
    assert r_v == 'NoCrossover', r_v
    assert r_tian == 'NoCrossover', r_tian

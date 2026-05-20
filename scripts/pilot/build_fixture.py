"""Build OPT 6П14П SE manual MAS skeleton + analytical Lp.

Host-safe: вызываем только лёгкие read-only / analytical функции PyOM
(get_core_shapes / get_core_materials / get_bobbins / calculate_core_data /
calculate_inductance_from_number_turns_and_gapping). Никаких
advisor-функций — они уезжают в pilot.Dockerfile под --memory=4g.

Параметры:
- Шейп: E 42/21/15 (близко к ШЛ16×16, есть готовый Bobbin E42/15).
- Материал: Nanoperm 8000 (nanocrystalline; современный аналог
  high-grade silicon-steel для audio band, μ_initial ≈ 7968).
- Витки: 2500 primary / 100 secondary (turns ratio 25:1 для 5kΩ:8Ω).
- Air gap: subtractive ~0.1 мм (компенсация DC bias класса A).
- Operating point: 1 kHz mid-band sine.
  Primary: 250 V peak (typical SE OPT swing), 50 mA DC + 10 mA AC
  (class-A 6П14П plate current).
  Secondary: 10 V peak, 1 A AC.

Waveforms — sampled time-data (32 точки на период), PyOM не принимает
строки типа "Sinusoidal" (см. AGENTS.md / llms.txt).

Записывает:
  tests/fixtures/magnetic/opt-6p14p-se/geometry.json  — MAS object
  tests/fixtures/magnetic/opt-6p14p-se/expected.json  — analytical Lp
"""

from __future__ import annotations

import glob
import importlib.util
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "magnetic" / "opt-6p14p-se"

SHAPE_NAME = "E 42/21/15"
BOBBIN_NAME = "Bobbin E42/15"
MATERIAL_NAME = "Nanoperm 8000"
PRIMARY_TURNS = 2500
SECONDARY_TURNS = 100
GAP_LENGTH_M = 0.0001  # 0.1 mm subtractive
OPERATING_FREQ_HZ = 1000.0
PRIMARY_PEAK_V = 250.0
SECONDARY_PEAK_V = PRIMARY_PEAK_V * SECONDARY_TURNS / PRIMARY_TURNS
PRIMARY_DC_BIAS_A = 0.05  # 50 mA DC plate current (class A)
PRIMARY_AC_PEAK_A = 0.01  # 10 mA AC swing
SECONDARY_AC_PEAK_A = 1.0  # 1 A AC into 8 Ω load
AMBIENT_C = 25.0
WAVEFORM_SAMPLES = 32

PRIMARY_WIRE = "Round 0.212 - Grade 1"
SECONDARY_WIRE = "Round 0.90 - Grade 1"
RELUCTANCE_MODELS = ["ZHANG", "MUEHLETHALER", "BALAKRISHNAN", "STENGLEIN", "EFFECTIVE_AREA"]


def _load_pyom() -> Any:
    """Load PyOpenMagnetics via importlib (no __init__.py)."""
    pkg_dir = os.path.join(
        os.path.dirname(__import__("PyOpenMagnetics").__path__[0]),
        "PyOpenMagnetics",
    )
    so_files = glob.glob(os.path.join(pkg_dir, "PyOpenMagnetics.cpython-*"))
    if not so_files:
        msg = f"No .so found in {pkg_dir}"
        raise RuntimeError(msg)
    spec = importlib.util.spec_from_file_location("PyOpenMagnetics", so_files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load_databases({})
    return mod


def _sine_waveform(
    freq_hz: float, peak: float, dc: float = 0.0, n: int = WAVEFORM_SAMPLES,
) -> dict[str, list[float]]:
    period = 1.0 / freq_hz
    times = [period * i / n for i in range(n + 1)]
    data = [dc + peak * math.sin(2.0 * math.pi * freq_hz * t) for t in times]
    return {"data": data, "time": times}


def _find_bobbin(pyom: Any, name: str) -> dict[str, Any]:
    for b in pyom.get_bobbins():
        if b.get("name") == name:
            return b
    msg = f"bobbin {name!r} not in catalogue"
    raise LookupError(msg)


def build_mas(pyom: Any) -> dict[str, Any]:
    """Build a full MAS object for OPT 6П14П SE.

    Returns a MAS-style dict with `magnetic` (core + coil with bobbin)
    and `inputs` (designRequirements + operatingPoints).
    """
    core_fd = {
        "functionalDescription": {
            "type": "two-piece set",
            "material": MATERIAL_NAME,
            "shape": SHAPE_NAME,
            "gapping": [{"type": "subtractive", "length": GAP_LENGTH_M}],
            "numberStacks": 1,
        },
    }
    core_full = pyom.calculate_core_data(core_fd, True)
    bobbin = _find_bobbin(pyom, BOBBIN_NAME)

    coil = {
        "functionalDescription": [
            {
                "name": "primary",
                "numberTurns": PRIMARY_TURNS,
                "numberParallels": 1,
                "isolationSide": "primary",
                "wire": PRIMARY_WIRE,
            },
            {
                "name": "secondary",
                "numberTurns": SECONDARY_TURNS,
                "numberParallels": 1,
                "isolationSide": "secondary",
                "wire": SECONDARY_WIRE,
            },
        ],
        "bobbin": bobbin,
    }

    magnetic = {"core": core_full, "coil": coil}

    operating_point = {
        "name": "1 kHz mid-band",
        "conditions": {"ambientTemperature": AMBIENT_C},
        "excitationsPerWinding": [
            {
                "frequency": OPERATING_FREQ_HZ,
                "voltage": {"waveform": _sine_waveform(OPERATING_FREQ_HZ, PRIMARY_PEAK_V)},
                "current": {
                    "waveform": _sine_waveform(
                        OPERATING_FREQ_HZ, PRIMARY_AC_PEAK_A, dc=PRIMARY_DC_BIAS_A,
                    ),
                },
            },
            {
                "frequency": OPERATING_FREQ_HZ,
                "voltage": {"waveform": _sine_waveform(OPERATING_FREQ_HZ, SECONDARY_PEAK_V)},
                "current": {
                    "waveform": _sine_waveform(OPERATING_FREQ_HZ, SECONDARY_AC_PEAK_A),
                },
            },
        ],
    }

    inputs = {
        "designRequirements": {
            "magnetizingInductance": {"nominal": 6.0},
            "turnsRatios": [{"nominal": PRIMARY_TURNS / SECONDARY_TURNS}],
            "name": "OPT 6П14П SE pilot",
            "topology": "push_pull",
        },
        "operatingPoints": [operating_point],
    }

    return {"magnetic": magnetic, "inputs": inputs}


def compute_inductance(pyom: Any, mas: dict[str, Any]) -> dict[str, float]:
    """Compute Lp across all reluctance models — host-safe."""
    core = mas["magnetic"]["core"]
    coil = mas["magnetic"]["coil"]
    op = mas["inputs"]["operatingPoints"][0]
    out: dict[str, float] = {}
    for model in RELUCTANCE_MODELS:
        out[model] = float(
            pyom.calculate_inductance_from_number_turns_and_gapping(
                core, coil, op, {"reluctance": model},
            ),
        )
    return out


def main() -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    pyom = _load_pyom()
    print(f"PyOM loaded: {len(dir(pyom))} symbols")

    mas = build_mas(pyom)
    ep = mas["magnetic"]["core"]["processedDescription"]["effectiveParameters"]
    print(
        f"shape={SHAPE_NAME}  material={MATERIAL_NAME}  "
        f"N1={PRIMARY_TURNS} N2={SECONDARY_TURNS}  gap={GAP_LENGTH_M * 1000:.2f} mm",
    )
    print(
        f"effective Ae={ep['effectiveArea'] * 1e6:.3g} mm²  "
        f"le={ep['effectiveLength'] * 1000:.3g} mm  "
        f"Ve={ep['effectiveVolume'] * 1e6:.3g} cm³",
    )

    lps = compute_inductance(pyom, mas)
    for m, lp in lps.items():
        print(f"  {m:<16}  Lp = {lp:.6g} H")
    lp_nominal = lps["ZHANG"]

    (FIXTURE_DIR / "geometry.json").write_text(json.dumps(mas, indent=2))
    (FIXTURE_DIR / "expected.json").write_text(
        json.dumps(
            {
                "primaryInductance_H": lp_nominal,
                "reluctanceModel_default": "ZHANG",
                "primaryInductance_H_per_model": lps,
                "method": "PyOpenMagnetics.calculate_inductance_from_number_turns_and_gapping",
                "shape": SHAPE_NAME,
                "bobbin": BOBBIN_NAME,
                "material": MATERIAL_NAME,
                "primaryTurns": PRIMARY_TURNS,
                "secondaryTurns": SECONDARY_TURNS,
                "gapLength_m": GAP_LENGTH_M,
                "operatingFrequency_Hz": OPERATING_FREQ_HZ,
                "primaryPeakVoltage_V": PRIMARY_PEAK_V,
                "primaryDcBias_A": PRIMARY_DC_BIAS_A,
                "effectiveArea_m2": ep["effectiveArea"],
                "effectiveLength_m": ep["effectiveLength"],
                "effectiveVolume_m3": ep["effectiveVolume"],
            },
            indent=2,
        ),
    )
    print(f"wrote {FIXTURE_DIR}/geometry.json and expected.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

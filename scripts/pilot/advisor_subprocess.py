"""T113 Phase 1 pilot Stage E — PyOpenMagnetics advisor heavy run (subprocess).

Запускается из run_pilot.py.stage_advisor_heavy() как ОТДЕЛЬНЫЙ child
процесс под /usr/bin/time -v. Цель — изолировать тяжёлый advisor от
orchestrator: при OOM (Docker --memory=4g) Linux OOM-killer выбирает
самый жирный процесс (advisor), parent run_pilot.py выживает и записывает
diagnostic "killed by SIGKILL after N seconds, peak RSS Y MB" в
results.json. Уже собранные данные analytical/mesh/GetDP/Elmer не теряются.

Использует converter spec Flyback с canonical AGENTS.md §6.1 параметрами
(offline 220V → 12V/2A, 100 kHz). Spec на pilot изначально просит
push_pull, но push_pull в PyOM 1.3.10 возвращает `data: []` (advisor
не находит подходящих cores) на любых разумных параметрах
SMPS-уровня — изучено через probe 2026-05-20. Flyback с canonical
spec'ом — гарантированно даёт real result, stress-test цель
(advisor под нагрузкой) сохраняется.

Дополнительно: в PyOM 1.3.10 wheel НЕ забандлен libngspice (вопреки
AGENTS.md, которая описывает старую версию) — pilot.Dockerfile
устанавливает `ngspice` apt-пакет. PyOM шеллит к binary
/usr/bin/ngspice (a не dlopen libngspice.so — флаг `ENABLE_NGSPICE`
не определён в этой сборке, см. strings PyOpenMagnetics.cpython).

Core mode по умолчанию — "standard cores" (~1250 magnetics
catalog, ~70-90s, ~1 GB peak RSS), помещается в pilot --memory=4g
докер-лимит. "available cores" (~1301+ shapes) на нашем host'е
выходит за 6 GB peak RSS → OOM-kill (проверено 2026-05-20).

Usage:
    python advisor_subprocess.py <output_json_path>

Output JSON в <output_json_path>:
    {"elapsed_s": float, "data_count": int, "core_shape": str, ...} on success
    {"elapsed_s": float, "data_count": 0, ...} if advisor returned empty
    {"elapsed_s": float, "error": str} on schema/runtime error
    (нет файла) — если процесс убит SIGKILL до записи
"""

from __future__ import annotations

import glob
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Canonical AGENTS.md §6.1 flyback spec — offline 220V AC mains → 12V/2A DC,
# 100 kHz switching, 24W output. Гарантированно даёт result после
# 70-90s advisor optimization на 'standard cores'.
TOPOLOGY = 'flyback'
CORE_MODE = 'standard cores'    # см. docstring про "available cores" OOM
CONVERTER_SPEC: dict[str, Any] = {
    'currentRippleRatio': 0.4,
    'diodeVoltageDrop': 0.5,
    'efficiency': 0.88,
    'inputVoltage': {'minimum': 185.0, 'nominal': 220.0, 'maximum': 265.0},
    'maximumDutyCycle': 0.45,
    'operatingPoints': [
        {
            'ambientTemperature': 25.0,
            'outputVoltages': [12.0],
            'outputCurrents': [2.0],
            'switchingFrequency': 100000.0,
        },
    ],
}


def _load_pyom() -> Any:  # noqa: ANN401  - PyOM is dynamic .so module
    """Mirror run_pilot.py._load_pyom (no __init__.py — нужен importlib)."""
    pkg_dir = os.path.join(
        os.path.dirname(__import__('PyOpenMagnetics').__path__[0]),
        'PyOpenMagnetics',
    )
    so_files = glob.glob(os.path.join(pkg_dir, 'PyOpenMagnetics.cpython-*'))
    if not so_files:
        msg = f'No .so found in {pkg_dir}'
        raise RuntimeError(msg)
    spec = importlib.util.spec_from_file_location('PyOpenMagnetics', so_files[0])
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load_databases({})
    return mod


def _summarize_result(result: Any) -> dict[str, Any]:  # noqa: ANN401
    """Extract Lp + core + windings + scoring из advisor result.

    PyOM 1.3.10 формат (отличается от AGENTS.md):
        {"data": [{"mas": {...}, "scoring": float, "scoringPerFilter": {...}}, ...]}
    """
    out: dict[str, Any] = {'raw_type': type(result).__name__}
    if isinstance(result, dict) and 'error' in result:
        out['error'] = str(result['error'])
        return out
    if not isinstance(result, dict) or 'data' not in result:
        out['error'] = f'unexpected result shape: {type(result).__name__}'
        return out

    data = result['data']
    out['data_count'] = len(data)
    if not data:
        # Advisor отработал, но не нашёл подходящих cores. Для stress-test
        # это OK: всё ещё измеряем elapsed + RSS.
        return out

    entry = data[0]
    if not isinstance(entry, dict) or 'mas' not in entry:
        out['error'] = f'unexpected entry shape: {type(entry).__name__}'
        return out

    mas_obj = entry['mas']
    out['scoring'] = entry.get('scoring')
    core = mas_obj['magnetic']['core']['functionalDescription']
    coil = mas_obj['magnetic']['coil']['functionalDescription']
    dr = mas_obj['inputs']['designRequirements']

    def _name_of(x: Any) -> Any:  # noqa: ANN401
        return x.get('name') if isinstance(x, dict) else x

    out['core_shape'] = _name_of(core.get('shape'))
    out['core_material'] = _name_of(core.get('material'))
    out['core_gapping'] = core.get('gapping')
    out['windings'] = [
        {
            'name': w.get('name'),
            'turns': w.get('numberTurns'),
            'parallels': w.get('numberParallels', 1),
        }
        for w in coil
    ]
    out['magnetizing_inductance_H'] = dr.get('magnetizingInductance')
    out['turns_ratios'] = dr.get('turnsRatios')
    return out


def main() -> int:
    if len(sys.argv) != 2:
        sys.stderr.write('usage: advisor_subprocess.py <output_json>\n')
        return 2

    out_path = Path(sys.argv[1])

    pyom = _load_pyom()
    sys.stdout.write(f'PyOM loaded: {len(dir(pyom))} symbols\n')
    sys.stdout.flush()

    t0 = time.monotonic()
    try:
        # POSITIONAL args обязательны (per AGENTS.md §3 — .pyi keyword
        # names неправильные). max_results=1 — нам нужен один best
        # design для Pilot table, не топ-N. Топология/core mode/спецификация
        # фиксированы вверху файла (см. docstring про выбор).
        result = pyom.design_magnetics_from_converter(
            TOPOLOGY, CONVERTER_SPEC, 1, CORE_MODE, True, None,
        )
    except (RuntimeError, ValueError) as exc:
        elapsed = time.monotonic() - t0
        out_path.write_text(
            json.dumps(
                {
                    'elapsed_s': elapsed,
                    'error': f'{type(exc).__name__}: {exc}',
                },
                indent=2,
            ),
        )
        return 1

    elapsed = time.monotonic() - t0
    summary = _summarize_result(result)
    summary['elapsed_s'] = elapsed
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    sys.stdout.write(f'advisor done: {elapsed:.1f}s, wrote {out_path}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())

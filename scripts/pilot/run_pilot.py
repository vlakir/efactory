"""T113 Phase 1 pilot orchestrator — runs analytical + advisor + 2 FEM solvers.

Этот скрипт работает ВНУТРИ pilot.Dockerfile (efactory-pilot:linux) при
запуске `docker run --rm --memory=4g ...`. Хост-окружение Владимира не
трогаем — advisor может улететь в OOM (см. memory: PyOM advisor host-OOM).

Шаги (каждый — отдельная stage с замером времени и peak RSS):

  1. PyOM analytical sanity — calculate_inductance_from_number_turns_and_gapping
     на manual MAS skeleton; должен совпасть с expected.json fixture
     (in-container reproducibility check).
  2. PyOM advisor heavy — design_magnetics_from_converter("push_pull", ...,
     "available cores") — тяжёлая optimization для stress-test
     (information-only colonna в Pilot table).
  3. Gmsh mesh — geometry.geo → geometry.msh.
  4. Elmer FEM — magnetostatic 2D, primary energized; L_p = 2W/I².
  5. GetDP FEM — то же на той же mesh.
  6. Сохраняем /work/results.json + /work/pilot_report.txt (Markdown табличка
     для копирования в spec'у).

Sub-steps вызываются как subprocesses через `/usr/bin/time -v` — peak
RSS читаем из stderr ("Maximum resident set size (kbytes): NNN").

Stage 1 уже работает; Stage 2-5 — следующие коммиты на ветке T113-fem.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import re
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path('/pilot/fixtures/opt-6p14p-se')


def _load_pyom() -> Any:
    """Load PyOpenMagnetics via importlib (no __init__.py)."""
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


def _peak_rss_mb() -> float:
    """Current process peak RSS in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _parse_time_v(stderr: str) -> dict[str, float]:
    """Parse `/usr/bin/time -v` output for peak RSS + wall time."""
    rss_match = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', stderr)
    wall_match = re.search(r'Elapsed \(wall clock\) time \([^)]+\):\s*([\d:.]+)', stderr)
    return {
        'peak_rss_mb': int(rss_match.group(1)) / 1024.0 if rss_match else 0.0,
        'wall_clock': wall_match.group(1) if wall_match else '?',
    }


# Stage 1: PyOM analytical sanity in container
def stage_analytical_sanity(pyom: Any) -> dict[str, Any]:
    """Re-run analytical Lp on fixture; verify matches expected.json."""
    expected = json.loads((FIXTURE_DIR / 'expected.json').read_text())
    mas = json.loads((FIXTURE_DIR / 'geometry.json').read_text())

    core = mas['magnetic']['core']
    coil = mas['magnetic']['coil']
    op = mas['inputs']['operatingPoints'][0]

    t0 = time.monotonic()
    lps = {}
    for model in expected['primaryInductance_H_per_model']:
        lps[model] = float(
            pyom.calculate_inductance_from_number_turns_and_gapping(
                core, coil, op, {'reluctance': model},
            ),
        )
    elapsed = time.monotonic() - t0

    # Tolerance: 0.1% (we're not changing inputs, just re-running)
    diffs = {
        m: abs(lps[m] - expected['primaryInductance_H_per_model'][m])
        / expected['primaryInductance_H_per_model'][m]
        for m in lps
    }
    max_diff = max(diffs.values())
    ok = max_diff < 1e-3

    return {
        'ok': ok,
        'elapsed_s': elapsed,
        'peak_rss_mb': _peak_rss_mb(),
        'lp_h_per_model': lps,
        'lp_h_expected': expected['primaryInductance_H_per_model'],
        'max_rel_diff': max_diff,
    }


# Stage 2: PyOM advisor heavy run — placeholder for next commit
def stage_advisor_heavy(pyom: Any) -> dict[str, Any]:  # noqa: ARG001  - pending
    """TODO: design_magnetics_from_converter('push_pull', ..., 'available cores')."""
    return {'status': 'pending', 'note': 'to be implemented in next commit'}


# Stage 3-5 placeholders
def stage_mesh() -> dict[str, Any]:
    return {'status': 'pending'}


def stage_elmer() -> dict[str, Any]:
    return {'status': 'pending'}


def stage_getdp() -> dict[str, Any]:
    return {'status': 'pending'}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'work_dir', type=Path, default=Path('/work'), nargs='?',
        help='Host-mounted output directory for results.json + report.',
    )
    parser.add_argument(
        '--skip-advisor', action='store_true',
        help='Skip PyOM advisor heavy run (e.g. CI smoke).',
    )
    args = parser.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)

    print('=== T113 Phase 1 pilot ===')
    print(f'fixture dir: {FIXTURE_DIR}')
    print(f'output dir:  {args.work_dir}')
    print()

    pyom = _load_pyom()
    print(f'PyOM loaded: {len(dir(pyom))} symbols')

    results: dict[str, Any] = {}

    print('\n--- Stage 1: PyOM analytical sanity ---')
    r1 = stage_analytical_sanity(pyom)
    results['analytical_sanity'] = r1
    print(f"  elapsed: {r1['elapsed_s']:.3f}s   peak RSS: {r1['peak_rss_mb']:.1f} MB")
    print(f"  max rel diff vs fixture: {r1['max_rel_diff']:.2e}   ok={r1['ok']}")
    for model, lp in r1['lp_h_per_model'].items():
        print(f'    {model:<16} Lp = {lp:.6g} H')
    if not r1['ok']:
        print('  FAIL: analytical mismatch — fixture not reproducible in container')
        results_file = args.work_dir / 'results.json'
        results_file.write_text(json.dumps(results, indent=2))
        return 1

    print('\n--- Stage 2-5: pending (next commit on T113-fem) ---')
    results['advisor_heavy'] = stage_advisor_heavy(pyom) if not args.skip_advisor else {'status': 'skipped'}
    results['mesh'] = stage_mesh()
    results['elmer'] = stage_elmer()
    results['getdp'] = stage_getdp()

    results_file = args.work_dir / 'results.json'
    results_file.write_text(json.dumps(results, indent=2))
    print(f'\nwrote {results_file}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

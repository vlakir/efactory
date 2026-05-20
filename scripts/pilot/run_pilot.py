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
GETDP_PRO_SRC = Path('/pilot/scripts/pilot/getdp/magnetostatic.pro')
PRIMARY_TURNS = 2500       # consistency с build_fixture.py
I_REF_GETDP = 1.0          # ток через primary в GetDP physics


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


def _run_timed(cmd: list[str], cwd: Path | None = None) -> dict[str, Any]:
    """Run cmd via /usr/bin/time -v; return stdout/stderr/return + peak RSS."""
    full = ['/usr/bin/time', '-v', *cmd]
    res = subprocess.run(  # noqa: S603
        full, cwd=cwd, capture_output=True, text=True, check=False,
    )
    parsed = _parse_time_v(res.stderr)
    return {
        'cmd': cmd,
        'returncode': res.returncode,
        'stdout': res.stdout,
        'stderr': res.stderr,
        'peak_rss_mb': parsed['peak_rss_mb'],
        'wall_clock': parsed['wall_clock'],
    }


# Stage 3: Gmsh mesh
def stage_mesh(work_dir: Path) -> dict[str, Any]:
    """Convert geometry.geo to geometry.msh (Gmsh msh2.2 format for FEM solvers)."""
    geo_src = FIXTURE_DIR / 'geometry.geo'
    geo_local = work_dir / 'geometry.geo'
    msh_local = work_dir / 'geometry.msh'
    geo_local.write_text(geo_src.read_text())

    t0 = time.monotonic()
    r = _run_timed(
        [
            'gmsh', '-2',
            '-format', 'msh22',
            str(geo_local),
            '-o', str(msh_local),
        ],
        cwd=work_dir,
    )
    elapsed = time.monotonic() - t0
    ok = r['returncode'] == 0 and msh_local.exists() and msh_local.stat().st_size > 0
    return {
        'ok': ok,
        'elapsed_s': elapsed,
        'peak_rss_mb': r['peak_rss_mb'],
        'msh_path': str(msh_local),
        'msh_size_kb': msh_local.stat().st_size / 1024.0 if msh_local.exists() else 0,
        'returncode': r['returncode'],
        'stderr_tail': r['stderr'].splitlines()[-5:],
    }


# Stage 4: GetDP FEM
def stage_getdp(work_dir: Path, depth_m: float) -> dict[str, Any]:
    """Run GetDP magnetostatic 2D and compute L_primary = 2W/I²."""
    msh_local = work_dir / 'geometry.msh'
    pro_local = work_dir / 'magnetostatic.pro'
    pro_local.write_text(GETDP_PRO_SRC.read_text())

    t0 = time.monotonic()
    r = _run_timed(
        [
            'getdp', str(pro_local),
            '-msh', str(msh_local),
            '-solve', 'Mag2D',
        ],
        cwd=work_dir,
    )
    elapsed = time.monotonic() - t0

    energy_file = work_dir / 'energy_per_depth.txt'
    energy_per_depth = None
    lp_henry = None
    if energy_file.exists():
        # GetDP "Format Table" emits "<elem_tag> <value>" per line; for
        # OnGlobal scalar — single line "<elem_tag> <value>".
        # Take first valid float in last non-empty line.
        for line in reversed(energy_file.read_text().splitlines()):
            tokens = line.split()
            if not tokens:
                continue
            for tok in reversed(tokens):
                try:
                    energy_per_depth = float(tok)
                    break
                except ValueError:
                    continue
            if energy_per_depth is not None:
                break

    if energy_per_depth is not None:
        # 3D energy = energy_per_depth × core depth
        # L = 2W / I_ref²
        total_energy = energy_per_depth * depth_m
        lp_henry = 2.0 * total_energy / (I_REF_GETDP ** 2)

    ok = r['returncode'] == 0 and lp_henry is not None
    return {
        'ok': ok,
        'elapsed_s': elapsed,
        'peak_rss_mb': r['peak_rss_mb'],
        'returncode': r['returncode'],
        'energy_per_depth_J_per_m': energy_per_depth,
        'lp_henry': lp_henry,
        'stderr_tail': r['stderr'].splitlines()[-5:],
        'stdout_tail': r['stdout'].splitlines()[-5:],
    }


def stage_elmer(work_dir: Path, depth_m: float) -> dict[str, Any]:  # noqa: ARG001
    """TODO Stage D: Elmer FEM magnetostatic 2D."""
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

    # depth from fixture (used for L = 2W × depth) — extract once
    mas = json.loads((FIXTURE_DIR / 'geometry.json').read_text())
    depth_m = float(mas['magnetic']['core']['processedDescription']['depth'])
    print(f'\ncore depth (for L = 2 × W_per_depth × depth): {depth_m * 1000:.2f} mm')

    print('\n--- Stage 3: Gmsh mesh ---')
    rm = stage_mesh(args.work_dir)
    results['mesh'] = rm
    print(f"  elapsed: {rm['elapsed_s']:.3f}s   peak RSS: {rm['peak_rss_mb']:.1f} MB")
    print(f"  msh: {rm['msh_size_kb']:.1f} KB   ok={rm['ok']}   rc={rm['returncode']}")
    if not rm['ok']:
        for line in rm['stderr_tail']:
            print(f'    | {line}')
        (args.work_dir / 'results.json').write_text(json.dumps(results, indent=2))
        return 2

    print('\n--- Stage 4: GetDP FEM ---')
    rg = stage_getdp(args.work_dir, depth_m)
    results['getdp'] = rg
    print(f"  elapsed: {rg['elapsed_s']:.3f}s   peak RSS: {rg['peak_rss_mb']:.1f} MB")
    print(f"  rc={rg['returncode']}   energy_per_depth={rg['energy_per_depth_J_per_m']!r}")
    if rg['lp_henry'] is not None:
        print(f"  Lp (GetDP) = {rg['lp_henry']:.6g} H")
        analytical_ref = r1['lp_h_per_model']['ZHANG']
        rel = abs(rg['lp_henry'] - analytical_ref) / analytical_ref
        print(f"  vs analytical ZHANG ({analytical_ref:.6g} H): {rel * 100:.2f}% diff")
    else:
        print('  Lp not computed — see stdout/stderr tails:')
        for line in rg['stdout_tail']:
            print(f'    out| {line}')
        for line in rg['stderr_tail']:
            print(f'    err| {line}')

    print('\n--- Stage 2, 5: pending (next commits on T113-fem) ---')
    results['advisor_heavy'] = (
        stage_advisor_heavy(pyom) if not args.skip_advisor else {'status': 'skipped'}
    )
    results['elmer'] = stage_elmer(args.work_dir, depth_m)

    results_file = args.work_dir / 'results.json'
    results_file.write_text(json.dumps(results, indent=2))
    print(f'\nwrote {results_file}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

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
ELMER_SIF_SRC = Path('/pilot/scripts/pilot/elmer/magnetostatic.sif')
ADVISOR_SUBPROCESS = Path('/pilot/scripts/pilot/advisor_subprocess.py')
PRIMARY_TURNS = 2500       # consistency с build_fixture.py
I_REF_FEM = 1.0            # ток через primary, общий для GetDP и Elmer
# J_density для Elmer (hard-coded в .sif как Body Force; держим тут для J·A
# метода расчёта Lp в Python — должен совпадать с константой в .sif).
J_DENSITY_ELMER = 9.09182e6  # 2500 * 1.0 / (9.075e-3 * 30.3e-3)
# OOM-detection: SIGKILL → rc=-9 (Python signal) или 137 (128+9, shell convention)
OOM_RETURNCODES = (-9, 137)


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


# Stage 2: PyOM advisor heavy run (subprocess, OOM-safe)
def stage_advisor_heavy(work_dir: Path) -> dict[str, Any]:
    """Run PyOM design_magnetics_from_converter('push_pull') as subprocess.

    Subprocess isolation критична — advisor реально тяжёлый
    (`available cores` advisor search 1301+ shapes, 60-180s per
    AGENTS.md, ~hundreds of MB peak RSS). Docker --memory=4g лимит на
    контейнер: при превышении OOM-killer выбирает самый жирный процесс
    (advisor), parent orchestrator выживает и фиксирует diagnostic.

    Логика подсчёта в child скрипте (scripts/pilot/advisor_subprocess.py):
    realistic push-pull SMPS spec (50W, 100 kHz), Forward schema (push_pull
    использует ту же что Forward, см. AGENTS.md §5.5+5.7).

    Returns dict с status (ok/oom/error/timeout), elapsed, peak RSS,
    advisor summary (core shape/material, turns, magnetizing Lp).
    """
    out_path = work_dir / 'advisor_result.json'
    out_path.unlink(missing_ok=True)

    t0 = time.monotonic()
    r = _run_timed(
        ['python', str(ADVISOR_SUBPROCESS), str(out_path)],
        cwd=work_dir,
    )
    elapsed = time.monotonic() - t0

    summary: dict[str, Any] = {}
    if out_path.exists():
        try:
            summary = json.loads(out_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            summary = {'error': f'unparseable advisor_result.json: {exc}'}

    rc = r['returncode']
    oom = rc in OOM_RETURNCODES
    success = (
        rc == 0
        and 'error' not in summary
        and summary.get('data_count', 0) > 0
    )

    # Persist полный subprocess вывод — диагностика OOM/schema errors.
    (work_dir / 'advisor_stdout.log').write_text(r['stdout'])
    (work_dir / 'advisor_stderr.log').write_text(r['stderr'])

    return {
        'ok': success,
        'oom': oom,
        'returncode': rc,
        'elapsed_s': elapsed,
        'peak_rss_mb': r['peak_rss_mb'],
        'wall_clock': r['wall_clock'],
        'summary': summary,
        'stdout_tail': r['stdout'].splitlines()[-10:],
        'stderr_tail': r['stderr'].splitlines()[-10:],
    }


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
        lp_henry = 2.0 * total_energy / (I_REF_FEM ** 2)

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


def _parse_elmer_scalars(scalars_path: Path) -> dict[str, Any]:
    """Parse Elmer SaveScalars `body int` + `Mask Name` output.

    SaveScalars writes one row per steady-state step into ``scalars.dat`` and
    column descriptions into ``scalars.dat.names``. Для нашего solver'а
    (Variable=A, Operator='body int', Mask Name=Primary/Secondary) ждём
    одну row из N float'ов. .names описывает columns строкой формата:

        1: body int: a mask primary
        2: body int: a mask secondary

    Returns dict with:
      - ``mask_to_int_A``: {mask_name_lower: ∫_body A dA} (float)
      - ``raw_floats``: все числа из последней строки (для диагностики)
      - ``names_text``: содержимое .names файла (для диагностики)
    """
    text = scalars_path.read_text()
    lines = [line for line in text.splitlines() if line.strip()]
    raw_floats: list[float] = []
    if lines:
        for tok in lines[-1].split():
            try:
                raw_floats.append(float(tok))
            except ValueError:
                continue

    names_text = ''
    mask_to_int: dict[str, float] = {}
    names_path = scalars_path.parent / (scalars_path.name + '.names')
    if names_path.exists():
        names_text = names_path.read_text()
        # Match "<col_idx>: <desc> mask <name>" (Elmer 26.2 формат для
        # Operator='body int' + Mask Name=<NameOfBodyProperty>).
        mask_pattern = re.compile(
            r'^\s*(\d+):.*?mask\s+(\w+)', re.IGNORECASE | re.MULTILINE,
        )
        for m in mask_pattern.finditer(names_text):
            col_idx = int(m.group(1))  # 1-based column в scalars.dat
            mask_name = m.group(2).lower()
            if 1 <= col_idx <= len(raw_floats):
                mask_to_int[mask_name] = raw_floats[col_idx - 1]

    return {
        'mask_to_int_A': mask_to_int,
        'raw_floats': raw_floats,
        'names_text': names_text,
    }


def stage_elmer(work_dir: Path, depth_m: float) -> dict[str, Any]:
    """Run Elmer FEM magnetostatic 2D on geometry.msh; compute L_p via J·A.

    Зеркалит stage_getdp (та же mesh, та же физика, тот же energy method;
    но через identity ½ ∫ B·H dV = ½ ∫ J·A dV для линейного материала):

      W_per_depth = ½ · J_density · (∫_Primary A − ∫_Secondary A)
      Lp          = 2 · W_per_depth · core_depth / I_ref²

    ElmerGrid конвертирует /work/geometry.msh → /work/mesh-elmer/, затем
    ElmerSolver на /work/magnetostatic.sif. ∫_body A берётся из
    /work/scalars.dat (SaveScalars body integral от Variable=A).
    """
    msh_local = work_dir / 'geometry.msh'
    sif_local = work_dir / 'magnetostatic.sif'
    sif_local.write_text(ELMER_SIF_SRC.read_text())

    # Stage D.1 — ElmerGrid: msh22 → Elmer mesh format
    t_grid = time.monotonic()
    r_grid = _run_timed(
        [
            'ElmerGrid', '14', '2', str(msh_local),
            '-autoclean',
            '-out', 'mesh-elmer',
        ],
        cwd=work_dir,
    )
    grid_elapsed = time.monotonic() - t_grid
    grid_ok = (
        r_grid['returncode'] == 0
        and (work_dir / 'mesh-elmer' / 'mesh.header').exists()
    )

    if not grid_ok:
        return {
            'ok': False,
            'stage': 'ElmerGrid',
            'grid_elapsed_s': grid_elapsed,
            'grid_returncode': r_grid['returncode'],
            'grid_stderr_tail': r_grid['stderr'].splitlines()[-10:],
            'grid_stdout_tail': r_grid['stdout'].splitlines()[-10:],
        }

    # Stage D.2 — ElmerSolver
    t_solve = time.monotonic()
    r_solve = _run_timed(
        ['ElmerSolver', str(sif_local)],
        cwd=work_dir,
    )
    solve_elapsed = time.monotonic() - t_solve

    # Persist полный Elmer stdout/stderr — критично для диагностики, т.к.
    # _tail (5 строк) показывает только хвост `/usr/bin/time -v`, не
    # содержательный output ElmerSolver.
    (work_dir / 'elmer_stdout.log').write_text(r_solve['stdout'])
    (work_dir / 'elmer_stderr.log').write_text(r_solve['stderr'])
    (work_dir / 'elmer_grid.log').write_text(
        f"=== STDOUT ===\n{r_grid['stdout']}\n=== STDERR ===\n{r_grid['stderr']}",
    )

    scalars_path = work_dir / 'scalars.dat'
    parsed = (
        _parse_elmer_scalars(scalars_path)
        if scalars_path.exists()
        else {'mask_to_int_A': {}, 'raw_floats': [], 'names_text': ''}
    )

    # .sif определяет Body Properties `Primary = Logical True` и
    # `Secondary = Logical True` на соответствующих bodies, использует их как
    # Mask Name для SaveScalars 'body int' — см. magnetostatic.sif Solver 2.
    mask_to_int = parsed['mask_to_int_A']
    int_a_primary = mask_to_int.get('primary')
    int_a_secondary = mask_to_int.get('secondary')

    energy_per_depth = None
    lp_henry = None
    if int_a_primary is not None and int_a_secondary is not None:
        energy_per_depth = 0.5 * J_DENSITY_ELMER * (
            int_a_primary - int_a_secondary
        )
        total_energy = energy_per_depth * depth_m
        lp_henry = 2.0 * total_energy / (I_REF_FEM ** 2)

    ok = r_solve['returncode'] == 0 and lp_henry is not None
    return {
        'ok': ok,
        'grid_elapsed_s': grid_elapsed,
        'grid_peak_rss_mb': r_grid['peak_rss_mb'],
        'solve_elapsed_s': solve_elapsed,
        'solve_peak_rss_mb': r_solve['peak_rss_mb'],
        # combined wall-time + peak (для таблицы pilot)
        'elapsed_s': grid_elapsed + solve_elapsed,
        'peak_rss_mb': max(r_grid['peak_rss_mb'], r_solve['peak_rss_mb']),
        'returncode': r_solve['returncode'],
        'int_a_primary': int_a_primary,
        'int_a_secondary': int_a_secondary,
        'energy_per_depth_J_per_m': energy_per_depth,
        'lp_henry': lp_henry,
        'raw_floats': parsed['raw_floats'],
        'names_text': parsed['names_text'],
        'solve_stderr_tail': r_solve['stderr'].splitlines()[-5:],
        'solve_stdout_tail': r_solve['stdout'].splitlines()[-5:],
    }


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

    print('\n--- Stage 5: Elmer FEM ---')
    re_ = stage_elmer(args.work_dir, depth_m)
    results['elmer'] = re_
    print(
        f"  grid: {re_.get('grid_elapsed_s', 0):.3f}s "
        f"({re_.get('grid_peak_rss_mb', 0):.1f} MB)   "
        f"solve: {re_.get('solve_elapsed_s', 0):.3f}s "
        f"({re_.get('solve_peak_rss_mb', 0):.1f} MB)",
    )
    if re_['ok']:
        print(f"  Lp (Elmer) = {re_['lp_henry']:.6g} H")
        analytical_ref = r1['lp_h_per_model']['ZHANG']
        rel_analytic = abs(re_['lp_henry'] - analytical_ref) / analytical_ref
        print(
            f"  vs analytical ZHANG ({analytical_ref:.6g} H): "
            f'{rel_analytic * 100:.2f}% diff',
        )
        if rg.get('lp_henry') is not None:
            rel_getdp = abs(re_['lp_henry'] - rg['lp_henry']) / rg['lp_henry']
            print(
                f"  vs GetDP ({rg['lp_henry']:.6g} H): "
                f'{rel_getdp * 100:.2f}% cross-check',
            )
    else:
        print('  Lp not computed — diagnostic:')
        if re_.get('stage') == 'ElmerGrid':
            print(f"    ElmerGrid rc={re_.get('grid_returncode')}")
            for line in re_.get('grid_stdout_tail', []):
                print(f'    out| {line}')
            for line in re_.get('grid_stderr_tail', []):
                print(f'    err| {line}')
        else:
            print(f"    ElmerSolver rc={re_.get('returncode')}")
            print(f"    int_A_primary   = {re_.get('int_a_primary')!r}")
            print(f"    int_A_secondary = {re_.get('int_a_secondary')!r}")
            print(f"    raw_floats      = {re_.get('raw_floats')!r}")
            if re_.get('names_text'):
                print('    .names content:')
                for line in re_['names_text'].splitlines():
                    print(f'      | {line}')
            for line in re_.get('solve_stdout_tail', []):
                print(f'    out| {line}')
            for line in re_.get('solve_stderr_tail', []):
                print(f'    err| {line}')

    # Checkpoint: persist FEM-результаты ДО запуска advisor — на случай
    # если advisor OOM-killer выбьет всю контейнерную сессию, и хост
    # увидел только partial-run.
    results_file = args.work_dir / 'results.json'
    results_file.write_text(json.dumps(results, indent=2))
    print(f'\ncheckpoint wrote {results_file} (pre-advisor)')

    print('\n--- Stage 2: PyOM advisor heavy (subprocess, OOM-safe) ---')
    if args.skip_advisor:
        ra = {'status': 'skipped', 'reason': '--skip-advisor flag'}
        print('  skipped via --skip-advisor flag')
    else:
        ra = stage_advisor_heavy(args.work_dir)
        print(
            f"  elapsed: {ra['elapsed_s']:.2f}s   "
            f"peak RSS: {ra['peak_rss_mb']:.1f} MB   "
            f"wall: {ra['wall_clock']}",
        )
        if ra['ok']:
            s = ra['summary']
            print(f"  ok=True (rc={ra['returncode']})")
            print(f"    data_count:    {s.get('data_count')!r}")
            print(f"    core_shape:    {s.get('core_shape')!r}")
            print(f"    core_material: {s.get('core_material')!r}")
            print(f"    scoring:       {s.get('scoring')!r}")
            for w in s.get('windings', []):
                print(
                    f"    winding {w.get('name','?')}: "
                    f"{w.get('turns','?')} turns "
                    f"(×{w.get('parallels',1)} parallel)",
                )
            mag_l = s.get('magnetizing_inductance_H')
            if isinstance(mag_l, dict):
                nominal = mag_l.get('nominal')
                if nominal is not None:
                    print(f'    magnetizing_inductance (nominal): {nominal} H')
            elif mag_l is not None:
                print(f'    magnetizing_inductance: {mag_l!r}')
        elif ra['oom']:
            print(f"  OOM-killed (rc={ra['returncode']}) — exceeded "
                  f"docker --memory limit at peak RSS "
                  f"{ra['peak_rss_mb']:.1f} MB")
            print('  → ADR должен зафиксировать, что advisor требует '
                  '> 4 GB на push-pull spec')
        elif (
            ra['returncode'] == 0
            and ra['summary'].get('data_count') == 0
        ):
            print(f"  rc=0, но advisor вернул empty data[] "
                  f"(elapsed {ra['elapsed_s']:.1f}s) — "
                  f"converter spec несовместим с PyOM каталогом")
        else:
            print(f"  FAILED (rc={ra['returncode']}, oom={ra['oom']})")
            if ra['summary'].get('error'):
                print(f"    error: {ra['summary']['error']}")
            for line in ra.get('stderr_tail', []):
                print(f'    err| {line}')
    results['advisor_heavy'] = ra

    results_file = args.work_dir / 'results.json'
    results_file.write_text(json.dumps(results, indent=2))
    print(f'\nwrote {results_file}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

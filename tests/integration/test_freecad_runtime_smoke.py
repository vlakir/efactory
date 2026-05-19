"""Runtime smoke для FreeCAD inside efactory:linux (T112 Phase 2).

Проверяет, что `freecadcmd` доступен в PATH и работает headless: вывод
версии, базовая Part-операция через bundled Python AppImage, наличие
Sheet Metal addon на штатном пути. Тесты пропускаются, если `freecadcmd`
не в PATH (host'овая среда без FreeCAD).

Не входит в обязанности этого smoke:
- GUI-запуск (X11 / `freecad` / AppRun) — covered manually через
  `./efactory-up --demo-freecad` (Vladimir's acceptance ритуал).
- freecad-mcp wrapper — отдельная задача T124.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_FREECADCMD_AVAILABLE = shutil.which('freecadcmd') is not None

needs_freecadcmd = pytest.mark.skipif(
    not _FREECADCMD_AVAILABLE,
    reason='freecadcmd not in PATH (host without FreeCAD)',
)


@needs_freecadcmd
def test_freecadcmd_version_is_1_1_1() -> None:
    result = subprocess.run(
        ['freecadcmd', '--version'],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert 'FreeCAD 1.1.1' in result.stdout, (
        f'unexpected version output: {result.stdout!r}'
    )


@needs_freecadcmd
def test_freecadcmd_runs_part_api_and_sees_sheetmetal_addon(
    tmp_path: Path,
) -> None:
    script = tmp_path / 'smoke.py'
    script.write_text(
        textwrap.dedent(
            """\
            import os
            import sys
            import FreeCAD
            import Part

            doc = FreeCAD.newDocument('smoke')
            obj = doc.addObject('Part::Feature', 'box')
            obj.Shape = Part.makeBox(10, 10, 10)
            doc.recompute()
            assert abs(obj.Shape.Volume - 1000.0) < 1e-6, obj.Shape.Volume

            addon = '/opt/freecad/usr/Mod/SheetMetal'
            assert os.path.isdir(addon), f'addon dir missing: {addon}'
            assert os.path.isfile(os.path.join(addon, 'InitGui.py')), (
                f'InitGui.py missing in {addon}'
            )

            print('SMOKE_OK')
            """,
        ),
        encoding='utf-8',
    )

    result = subprocess.run(
        ['freecadcmd', str(script)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert 'SMOKE_OK' in result.stdout, (
        f'smoke script did not print SMOKE_OK; stdout:\n{result.stdout}\n'
        f'stderr:\n{result.stderr}'
    )

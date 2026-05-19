"""gen-bracket-demo.py — материализует sheet-metal-bracket demo-модель
для ручного прогона в FreeCAD GUI (T112 acceptance ритуал).

Что делает:
    1. Создаёт directory `$EFACTORY_DEMO_DIR` (default
       `$HOME/efactory-projects/sheetmetal-bracket-demo/` на host'е, через
       mount соответствует `/workspace/sheetmetal-bracket-demo/` в
       контейнере).
    2. Строит простой L-bracket в Part workbench: горизонтальное дно
       50×30×1.5 mm + вертикальная стенка 1.5×30×30 mm, объединённые
       boolean fusion. Открывается в FreeCAD GUI как 3D-форма; Sheet
       Metal workbench доступен в Workbench-меню для ручного
       экспериментирования с bend/unfold операциями.
    3. Сохраняет `bracket.FCStd` в demo-dir.

Запуск:
    Не через `uv run python` — FreeCAD API недоступен в efactory venv.
    Запускать через `freecadcmd` внутри efactory:linux:

        docker run --rm \\
            -v $HOME/efactory-projects:/workspace:rw \\
            efactory:linux freecadcmd /opt/efactory/scripts/gen-bracket-demo.py

    Обычно вызывается автоматически из `./efactory-up --demo-freecad`.
"""

from __future__ import annotations

import os
from pathlib import Path

import FreeCAD  # type: ignore[import-not-found]
import Part  # type: ignore[import-not-found]

_BOTTOM_LEN_MM = 50.0
_BOTTOM_WIDTH_MM = 30.0
_WALL_HEIGHT_MM = 30.0
_SHEET_THICKNESS_MM = 1.5


def _build_bracket(doc: 'FreeCAD.Document') -> None:
    bottom = Part.makeBox(_BOTTOM_LEN_MM, _BOTTOM_WIDTH_MM, _SHEET_THICKNESS_MM)
    wall = Part.makeBox(_SHEET_THICKNESS_MM, _BOTTOM_WIDTH_MM, _WALL_HEIGHT_MM)
    fused = bottom.fuse(wall)

    obj = doc.addObject('Part::Feature', 'Bracket')
    obj.Shape = fused


def main() -> None:
    demo_dir = Path(
        os.environ.get('EFACTORY_DEMO_DIR')
        or '/workspace/sheetmetal-bracket-demo',
    )
    demo_dir.mkdir(parents=True, exist_ok=True)

    out_path = demo_dir / 'bracket.FCStd'

    doc = FreeCAD.newDocument('Bracket')
    _build_bracket(doc)
    doc.recompute()
    doc.saveAs(str(out_path))
    FreeCAD.closeDocument(doc.Name)

    print(f'demo-dir : {demo_dir}')
    print(f'model    : {out_path}')
    print()
    print('Открыть в контейнере:')
    print('    ./efactory-up --demo-freecad')


if __name__ == '__main__':
    main()

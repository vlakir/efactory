"""gen-se-amp-demo.py — материализует SE-amp 6П14П demo-проект для ручного
прогона в KiCad GUI / Simulator (T111 acceptance ритуал).

Что делает:
    1. Создаёт directory `$EFACTORY_DEMO_DIR` (default
       `$HOME/efactory-projects/se-amp-demo/`).
    2. Копирует `6P14P.lib` и `OPT_SE_5K_8.lib` из `data/models/` в demo-dir
       (плоско, рядом с `.kicad_sch`).
    3. Импортирует `_build_se_amp` из integration-теста, monkey-patch'ит
       `_TUBE_LIB`/`_OPT_LIB` на **относительные** имена `6P14P.lib` /
       `OPT_SE_5K_8.lib` — KiCad резолвит `Sim.Library` относительно
       расположения `.kicad_sch`, ngspice через `.include` — относительно
       `cwd`. Оба сценария работают, если запускать KiCad из demo-dir.
    4. Вызывает `_build_se_amp(demo_dir / 'se_amp.kicad_sch')` — строит
       schematic той же логикой, что и acceptance-тест T103.
    5. Создаёт минимальный `se_amp.kicad_pro` (нужен для GUI Simulator —
       см. KiCad ограничение: одиночный `.kicad_sch` не открывает
       Simulator menu).

Запуск:
    uv run python scripts/gen-se-amp-demo.py

Затем (host):
    ./scripts/run-kicad.sh --demo
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / 'src'
_TEST_FILE = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_se_amp_facade.py'
)
_TUBE_LIB_SRC = _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom' / '6P14P.lib'
_OPT_LIB_SRC = (
    _REPO_ROOT
    / 'data'
    / 'models'
    / 'transformers'
    / 'generic'
    / 'OPT_SE_5K_8.lib'
)


def _load_se_amp_builder():  # type: ignore[no-untyped-def]
    """Импортирует test_se_amp_facade.py как обычный модуль через importlib.

    Не используем pytest collection — нам нужна одна функция, а не
    набор тестов. `tests/` не на sys.path, поэтому загружаем по абсолютному
    пути; `src/` добавляем в sys.path заранее, чтобы `from adapters...`
    в модуле резолвился.
    """
    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))

    spec = importlib.util.spec_from_file_location(
        'test_se_amp_facade', _TEST_FILE,
    )
    if spec is None or spec.loader is None:  # pragma: no cover (defensive)
        msg = f'Не удалось загрузить spec для {_TEST_FILE}'
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    demo_dir = Path(
        os.environ.get('EFACTORY_DEMO_DIR')
        or (Path.home() / 'efactory-projects' / 'se-amp-demo'),
    ).resolve()
    demo_dir.mkdir(parents=True, exist_ok=True)

    tube_lib_dst = demo_dir / '6P14P.lib'
    opt_lib_dst = demo_dir / 'OPT_SE_5K_8.lib'
    shutil.copy2(_TUBE_LIB_SRC, tube_lib_dst)
    shutil.copy2(_OPT_LIB_SRC, opt_lib_dst)

    builder = _load_se_amp_builder()
    builder._TUBE_LIB = Path('6P14P.lib')  # noqa: SLF001  (monkey-patch)
    builder._OPT_LIB = Path('OPT_SE_5K_8.lib')  # noqa: SLF001

    # `_build_se_amp` использует `Path.save(...)` — путь должен быть
    # абсолютным, иначе он лезет в текущий CWD.
    sch_path = builder._build_se_amp(demo_dir / 'se_amp.kicad_sch')  # noqa: SLF001

    pro_path = demo_dir / 'se_amp.kicad_pro'
    # Минимальный `.kicad_pro`: KiCad GUI заполнит дефолты при первом save.
    # Без этого файла Simulator-menu в Eeschema не появляется (memory
    # `feedback_kicad_simulator_needs_pro`).
    pro_path.write_text(
        json.dumps(
            {
                'board': {'design_settings': {}},
                'meta': {'filename': pro_path.name, 'version': 3},
            },
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )

    print(f'demo-dir : {demo_dir}')
    print(f'schematic: {sch_path}')
    print(f'project  : {pro_path}')
    print()
    print('Открыть в контейнере:')
    print('    ./scripts/run-kicad.sh --demo')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

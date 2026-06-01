#!/usr/bin/env python3
"""regenerate-templates.py — пересобрать shipping templates из текущих builders.

Запускается вручную перед merge при изменении builder'а (например,
``_build_se_amp`` в ``tests/integration/.../test_se_amp_facade.py``) либо
при обновлении ``data/models/*``. Snapshot-test
(``tests/integration/test_template_se_amp_snapshot.py``) сравнивает
baked content с свежим прогоном (UUID/timestamp нормализуются) — при
расхождении ругается «run this script».

Usage:
    uv run python scripts/regenerate-templates.py [--template NAME]

Без ``--template`` — пересобирает все шаблоны.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import shutil
import sys
import uuid
from pathlib import Path

# Deterministic UUIDs: `Schematic` facade зовёт `uuid.uuid4()` для каждого
# wire/pin/symbol через `_new_uuid()` в writer'е (16 вызовов на симбол).
# Стандартный `uuid.uuid4()` использует `os.urandom` (через secrets) — не
# поддаётся seeding'у. Чтобы baked templates были bit-stable между
# `regenerate-templates.py` runs (иначе CI snapshot-check вечно ругается на
# UUID drift), monkey-patch'аем `uuid.uuid4` на функцию, использующую
# seeded `random.Random`. Re-seed выполняется перед каждым baker (см.
# `_reseed_uuid_rng_for_template`) — гарантирует, что partial run
# `--template <name>` даёт тот же output, что и full run, и что между
# templates UUIDs не collid'ят (seed = sha256(template_name)).
#
# Production code (`uuid.uuid4()` в runtime efactory) не затронут — patch
# действует только пока работает этот script.
_SEEDED_UUID_RNG = random.Random()


def _seeded_uuid4() -> uuid.UUID:
    return uuid.UUID(int=_SEEDED_UUID_RNG.getrandbits(128), version=4)


def _reseed_uuid_rng_for_template(template_name: str) -> None:
    digest = hashlib.sha256(template_name.encode('utf-8')).digest()
    seed = int.from_bytes(digest[:8], 'big')
    _SEEDED_UUID_RNG.seed(seed)


uuid.uuid4 = _seeded_uuid4  # type: ignore[assignment]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _REPO_ROOT / 'data' / 'templates'
_MODELS_DIR = _REPO_ROOT / 'data' / 'models'

PROJECT_NAME_PLACEHOLDER = '{{PROJECT_NAME}}'

_SE_AMP_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_se_amp_facade.py'
)
_NFB_SE_AMP_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_nfb_se_amp_facade.py'
)


def _import_builder(builder_path: Path, attr: str) -> object:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))
    spec = importlib.util.spec_from_file_location(builder_path.stem, builder_path)
    if spec is None or spec.loader is None:
        msg = f'Cannot import builder from {builder_path}'
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attr)


def _import_se_amp_builder() -> object:
    return _import_builder(_SE_AMP_BUILDER_PATH, '_build_se_amp')


def _import_nfb_se_amp_builder() -> object:
    return _import_builder(_NFB_SE_AMP_BUILDER_PATH, '_build_nfb_se_amp')


def _bake_se_amp(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_se_amp_builder()
    build(sch_path)  # type: ignore[operator]

    # Builder embed'ит абсолютные `Sim.Library "/dev-machine/.../X.lib"`
    # (берёт `_TUBE_LIB`/`_OPT_LIB` из dev-репо). В shipping template
    # это (a) leaks dev-path в репо — snapshot CI ловит drift между
    # машинами; (b) ломает materialized projects на другой машине.
    # Fix: пост-процесс replace `<repo>/data/models/.../X.lib` →
    # `models/X.lib` (relative к materialized project root, где baker
    # копирует models в `target/models/`).
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / '6P14P.lib'),
        'models/6P14P.lib',
    )
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'transformers' / 'generic' / 'OPT_SE_5K_8.lib'),
        'models/OPT_SE_5K_8.lib',
    )
    sch_path.write_text(sch_text, encoding='utf-8')

    pro_name = f'{PROJECT_NAME_PLACEHOLDER}.kicad_pro'
    pro_path = target_dir / pro_name
    pro_path.write_text(
        json.dumps(
            {
                'board': {'design_settings': {}},
                'meta': {'filename': pro_name, 'version': 3},
            },
            indent=2,
            sort_keys=True,
        )
        + '\n',
        encoding='utf-8',
    )

    models_target = target_dir / 'models'
    models_target.mkdir(exist_ok=True)
    shutil.copy(
        _MODELS_DIR / 'tubes' / 'custom' / '6P14P.lib',
        models_target / '6P14P.lib',
    )
    shutil.copy(
        _MODELS_DIR / 'transformers' / 'generic' / 'OPT_SE_5K_8.lib',
        models_target / 'OPT_SE_5K_8.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: se-amp\n'
        'description: |\n'
        '  Single-ended pentode amp на 6П14П (EL84-аналог)\n'
        '  с выходным трансформатором 5kΩ:8Ω и нагрузкой 8 Ω.\n'
        'summary: SE 6П14П + OPT 5k:8Ω — готовая фикстура для SPICE/THD.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# se-amp template\n\n'
        f'Single-ended pentode amplifier на 6П14П (EL84-аналог), выходной\n'
        f'трансформатор 5kΩ:8Ω, нагрузка 8 Ω.\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — схема\n'
        f'  (после материализации: `<имя_проекта>.kicad_sch`).\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (нужен для\n'
        f'  GUI Simulator).\n'
        f'- `models/6P14P.lib` — лампа.\n'
        f'- `models/OPT_SE_5K_8.lib` — выходной трансформатор.\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n',
        encoding='utf-8',
    )


def _bake_nfb_se_amp(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_nfb_se_amp_builder()
    build(sch_path)  # type: ignore[operator]

    # Тот же post-process replace `<repo>/data/models/.../X.lib` →
    # `models/X.lib` (см. `_bake_se_amp` для обоснования).
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / '6N1P.lib'),
        'models/6N1P.lib',
    )
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / '6P14P.lib'),
        'models/6P14P.lib',
    )
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'transformers' / 'generic' / 'OPT_SE_5K_8.lib'),
        'models/OPT_SE_5K_8.lib',
    )
    sch_path.write_text(sch_text, encoding='utf-8')

    pro_name = f'{PROJECT_NAME_PLACEHOLDER}.kicad_pro'
    pro_path = target_dir / pro_name
    pro_path.write_text(
        json.dumps(
            {
                'board': {'design_settings': {}},
                'meta': {'filename': pro_name, 'version': 3},
            },
            indent=2,
            sort_keys=True,
        )
        + '\n',
        encoding='utf-8',
    )

    models_target = target_dir / 'models'
    models_target.mkdir(exist_ok=True)
    shutil.copy(
        _MODELS_DIR / 'tubes' / 'custom' / '6N1P.lib',
        models_target / '6N1P.lib',
    )
    shutil.copy(
        _MODELS_DIR / 'tubes' / 'custom' / '6P14P.lib',
        models_target / '6P14P.lib',
    )
    shutil.copy(
        _MODELS_DIR / 'transformers' / 'generic' / 'OPT_SE_5K_8.lib',
        models_target / 'OPT_SE_5K_8.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: nfb-se-amp\n'
        'description: |\n'
        '  Двухкаскадный SE на 6Н1П (driver) + 6П14П (output) с global\n'
        '  voltage NFB из вторички OPT 5kΩ:8Ω в катод 1-го каскада через\n'
        '  Rfb (4.7 kΩ) + Cfb_block (10 µF). Target PM ~45-60° (T153 Phase A).\n'
        'summary: NFB SE 6Н1П+6П14П с global feedback — фикстура для phase-margin.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# nfb-se-amp template\n\n'
        f'Двухкаскадный single-ended audio amp с global voltage NFB:\n'
        f'6Н1П (driver, triode) → 6П14П (output, pentode) → OPT 5kΩ:8Ω →\n'
        f'нагрузка 8 Ω. Feedback (R_fb 4.7 kΩ + C_fb_block 10 µF) из\n'
        f'вторички OPT в катод 1-го каскада. Target phase margin ~45-60°\n'
        f'(analytical estimate, validate в Phase B PM-tool).\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — схема\n'
        f'  (после материализации: `<имя_проекта>.kicad_sch`).\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (нужен для\n'
        f'  GUI Simulator).\n'
        f'- `models/6N1P.lib` — driver tube.\n'
        f'- `models/6P14P.lib` — output tube.\n'
        f'- `models/OPT_SE_5K_8.lib` — выходной трансформатор.\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n\n'
        f'## Phase margin (T153 Phase B+, planned)\n\n'
        f'    /measure-phase-margin --loop-break-node /sec_a\n'
        f'    # break node — auto-detect heuristic выберет global loop\n',
        encoding='utf-8',
    )


_BAKERS: dict[str, object] = {
    'se-amp': _bake_se_amp,
    'nfb-se-amp': _bake_nfb_se_amp,
}


def main() -> int:
    parser = argparse.ArgumentParser(description='Rebake shipping templates.')
    parser.add_argument(
        '--template',
        choices=list(_BAKERS),
        default=None,
        help='Конкретный шаблон (по умолчанию — все).',
    )
    args = parser.parse_args()

    names = [args.template] if args.template else list(_BAKERS)
    for name in names:
        target = _TEMPLATES_DIR / name
        if target.exists():
            shutil.rmtree(target)
        _reseed_uuid_rng_for_template(name)
        baker = _BAKERS[name]
        baker(target)  # type: ignore[operator]
        print(f'Baked {name}: {target}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

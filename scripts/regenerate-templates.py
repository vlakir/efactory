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
_OP_AMP_INVERTING_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_op_amp_inverting_facade.py'
)
_BJT_CE_NFB_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_bjt_ce_nfb_facade.py'
)
_TUBE_PP_AMP_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_tube_pp_amp_facade.py'
)
_TUBE_LINE_PREAMP_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_tube_line_preamp_facade.py'
)
_TUBE_PHONO_RIAA_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_tube_phono_riaa_facade.py'
)
_ACTIVE_LPF_SALLEN_KEY_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_active_lpf_sallen_key_facade.py'
)
_PENTODE_SE_RESISTIVE_BUILDER_PATH = (
    _REPO_ROOT
    / 'tests'
    / 'integration'
    / 'adapters'
    / 'schematic_kicad'
    / 'test_pentode_se_resistive_facade.py'
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


def _import_op_amp_inverting_builder() -> object:
    return _import_builder(
        _OP_AMP_INVERTING_BUILDER_PATH,
        '_build_op_amp_inverting',
    )


def _import_bjt_ce_nfb_builder() -> object:
    return _import_builder(
        _BJT_CE_NFB_BUILDER_PATH,
        '_build_bjt_ce_nfb',
    )


def _import_tube_pp_amp_builder() -> object:
    return _import_builder(
        _TUBE_PP_AMP_BUILDER_PATH,
        '_build_tube_pp_amp',
    )


def _import_tube_line_preamp_builder() -> object:
    return _import_builder(
        _TUBE_LINE_PREAMP_BUILDER_PATH,
        '_build_tube_line_preamp',
    )


def _import_tube_phono_riaa_builder() -> object:
    return _import_builder(
        _TUBE_PHONO_RIAA_BUILDER_PATH,
        '_build_tube_phono_riaa',
    )


def _import_active_lpf_sallen_key_builder() -> object:
    return _import_builder(
        _ACTIVE_LPF_SALLEN_KEY_BUILDER_PATH,
        '_build_active_lpf_sallen_key',
    )


def _import_6p13s_se_resistive_builder() -> object:
    return _import_builder(
        _PENTODE_SE_RESISTIVE_BUILDER_PATH,
        '_build_6p13s_se_resistive',
    )


def _import_6zh32p_mic_preamp_builder() -> object:
    return _import_builder(
        _PENTODE_SE_RESISTIVE_BUILDER_PATH,
        '_build_6zh32p_mic_preamp',
    )


def _import_6zh38p_if_amp_builder() -> object:
    return _import_builder(
        _PENTODE_SE_RESISTIVE_BUILDER_PATH,
        '_build_6zh38p_if_amp',
    )


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


def _bake_op_amp_inverting(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_op_amp_inverting_builder()
    build(sch_path)  # type: ignore[operator]

    # Builder embeds absolute path `<repo>/data/models/opamps/generic/
    # GENERIC_OPAMP_2POLE.lib`. Заменяем на relative `models/...` для
    # shipping template (см. `_bake_se_amp` для обоснования pattern'а).
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'opamps' / 'generic' / 'GENERIC_OPAMP_2POLE.lib'),
        'models/GENERIC_OPAMP_2POLE.lib',
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
        _MODELS_DIR / 'opamps' / 'generic' / 'GENERIC_OPAMP_2POLE.lib',
        models_target / 'GENERIC_OPAMP_2POLE.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: op-amp-inverting\n'
        'description: |\n'
        '  Inverting op-amp с two-pole macromodel (GENERIC_OPAMP_2POLE):\n'
        '  R_in=1k, R_fb=10k → closed-loop gain -10 V/V (β=1/11). A0=1e5,\n'
        '  fp1=10 Hz, fp2≈66 kHz → analytical T_loop_DC ≈ 9091, crossover\n'
        '  ≈ 64 kHz, **phase margin ≈ 45°** на crossover. Reference fixture\n'
        '  для cross-validation 4 phase-margin injection methods (T153 Phase\n'
        '  C.1 calibration target).\n'
        'summary: Op-amp inverting amp 2-pole (PM≈45°) — calibration reference '
        'для phase-margin methods.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# op-amp-inverting template\n\n'
        f'Reference inverting-amp фикстура для **calibration** четырёх phase-\n'
        f'margin injection methods (Middlebrook V/I, Tian, Rosenstark) в\n'
        f'рамках T153 Phase C.\n\n'
        f'## Топология\n\n'
        f'```\n'
        f'Vin ──[R_in 1k]── in_neg ──┬── INN OPAMP OUT ── vout '
        f'──[R_load 1M]── GND\n'
        f'                           │                     │\n'
        f'                           └──[R_fb 10k]─────────┘\n'
        f'INP OPAMP → GND\n'
        f'```\n\n'
        f'Op-amp model `GENERIC_OPAMP_2POLE` (см. `models/`): A0=1e5,\n'
        f'fp1=10 Hz, fp2≈66 kHz, Rout=50 Ω.\n\n'
        f'## Analytical reference\n\n'
        f'* β = R_in / (R_in + R_fb) = 1 / 11\n'
        f'* T_loop_DC = A0 · β ≈ **9091** (79.2 dB)\n'
        f'* Unity-gain crossover `f_c` ≈ **64 kHz**\n'
        f'* **Phase margin ≈ 45°** (± 2° rounding для C2 = 24 pF)\n\n'
        f'## Файлы\n\n'
        f'* `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — KiCad-схема.\n'
        f'* `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (для GUI Simulator).\n'
        f'* `models/GENERIC_OPAMP_2POLE.lib` — SPICE subckt op-amp.\n\n'
        f'## Phase margin measurement\n\n'
        f'    # Explicit (правильный break point — на op-amp output side):\n'
        f'    efactory bridge measure phase-margin <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch \\\n'
        f'        --loop-break-node vout --loop-break-element R_fb\n\n'
        f'Ожидаемый результат: `PM ≈ 45° ± 2°, crossover ≈ 64 kHz ± 5%`.\n',
        encoding='utf-8',
    )


def _bake_bjt_ce_nfb(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_bjt_ce_nfb_builder()
    build(sch_path)  # type: ignore[operator]

    # Builder embeds absolute path в `.include` SPICE directive
    # (`<repo>/data/models/bjt/onsemi/Q2N3904.lib`). Заменяем на relative
    # `models/Q2N3904.lib` для shipping template (тот же pattern что
    # `_bake_se_amp` / `_bake_op_amp_inverting`).
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'bjt' / 'onsemi' / 'Q2N3904.lib'),
        'models/Q2N3904.lib',
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
        _MODELS_DIR / 'bjt' / 'onsemi' / 'Q2N3904.lib',
        models_target / 'Q2N3904.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: bjt-ce-nfb\n'
        'description: |\n'
        '  Single-stage common-emitter NPN (2N3904) amp с voltage-divider\n'
        '  bias + shunt-shunt AC feedback (R_F=47k + C_F=1µ DC-block,\n'
        '  collector→base). Q-point V_CE≈7.8V / I_C≈1mA. Reference fixture\n'
        '  для T153 phase-margin 4-method matrix (ADR-T153g BJT CE row).\n'
        'summary: BJT CE shunt-shunt NFB (2N3904) — фикстура для phase-margin '
        '4-method calibration.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# bjt-ce-nfb template\n\n'
        f'Single-stage common-emitter NPN amp (2N3904) с voltage-divider\n'
        f'bias (R_B1=100k / R_B2=10k), emitter degeneration (R_E=470Ω +\n'
        f'C_E=47µF bypass), и shunt-shunt AC-only feedback (R_F=47kΩ +\n'
        f'C_F=1µF DC-block, collector→base). Reference fixture для **T153\n'
        f'phase-margin 4-method calibration matrix** (ADR-T153g BJT CE row).\n\n'
        f'## Топология\n\n'
        f'```\n'
        f'Vin ──[R_S 50]── C_in ──┬── base\n'
        f'                        │           Q1 (2N3904)\n'
        f'         V_CC ──[R_B1 100k]┤    B          C ── vout\n'
        f'                       R_B2 10k        E\n'
        f'                          │            │\n'
        f'                        GND        [R_E 470] ‖ [C_E 47µ] → GND\n'
        f'         V_CC ──[R_C 4.7k]── vout ──[C_out 10µ]── vload\n'
        f'                                        │              │\n'
        f'              base ──[R_F 47k]──[C_F 1µ]┘          [R_L 10k] → GND\n'
        f'```\n\n'
        f'## Q-point (analytical / op-point validated)\n\n'
        f'* V_B ≈ 1.03 V, V_E ≈ 0.38 V, V_BE ≈ 0.66 V\n'
        f'* I_C ≈ 0.8-1.0 mA (active region)\n'
        f'* V_C ≈ 8.2 V, V_CE ≈ 7.8 V\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — KiCad-схема\n'
        f'  (после материализации: `<имя_проекта>.kicad_sch`).\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (для GUI Simulator).\n'
        f'- `models/Q2N3904.lib` — SPICE model card (ON Semi Gummel-Poon).\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n\n'
        f'## Phase margin (T153 4-method matrix)\n\n'
        f'    # Canonical break for V single — collector side (vout, C_F):\n'
        f'    efactory bridge measure phase-margin <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch \\\n'
        f'        --loop-break-node vout --loop-break-element C_F\n',
        encoding='utf-8',
    )


def _bake_tube_pp_amp(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_tube_pp_amp_builder()
    build(sch_path)  # type: ignore[operator]

    # Replace absolute model paths → relative `models/...` (тот же
    # post-process pattern что в _bake_se_amp / _bake_nfb_se_amp).
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / '6N2P.lib'),
        'models/6N2P.lib',
    )
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / '6P14P.lib'),
        'models/6P14P.lib',
    )
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'transformers' / 'generic' / 'OPT_PP_6K6_8.lib'),
        'models/OPT_PP_6K6_8.lib',
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
        _MODELS_DIR / 'tubes' / 'custom' / '6N2P.lib',
        models_target / '6N2P.lib',
    )
    shutil.copy(
        _MODELS_DIR / 'tubes' / 'custom' / '6P14P.lib',
        models_target / '6P14P.lib',
    )
    shutil.copy(
        _MODELS_DIR / 'transformers' / 'generic' / 'OPT_PP_6K6_8.lib',
        models_target / 'OPT_PP_6K6_8.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: tube-pp-amp\n'
        'description: |\n'
        '  Tube push-pull power amp на 6Н2П (long-tail-pair splitter,\n'
        '  обе половины ECC83) + пара 6П14П (Valve:EL84) в push-pull с\n'
        '  per-tube auto-bias (R_k=270Ω ‖ C_k=220µF) + OPT_PP_6K6_8\n'
        '  (6.6kΩ:8Ω, center-tapped primary) + 8 Ω load. Open-loop\n'
        '  (без global NFB). Mid-band Av ≈ 16.5 V/V (≈24 dB).\n'
        'summary: Push-pull 6П14П PP + LTP 6Н2П splitter — open-loop tube power amp.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# tube-pp-amp template\n\n'
        f'Двухкаскадный push-pull power amp с **long-tail-pair (LTP)**\n'
        f'phase splitter: обе половины 6Н2П (Valve:ECC83 unit 1 + unit 2),\n'
        f'shared cathode через R_tail=4.7 kΩ → пара 6П14П (Valve:EL84) в\n'
        f'push-pull с per-tube auto-bias (R_k=270 Ω ‖ C_k=220 µF) → выходной\n'
        f'трансформатор OPT_PP_6K6_8 (6.6 kΩ p-p : 8 Ω, center-tapped primary)\n'
        f'→ 8 Ω load. **Open-loop** (без global NFB) — NFB вариант остаётся\n'
        f'в BACKLOG отдельной задачей по аналогии с `se-amp` → `nfb-se-amp`.\n\n'
        f'**Phase splitter choice (ADR-T027a).** Изначальный план Round 2 был\n'
        f'concertina (split-load) на одной половине 6Н2П, но empirical-\n'
        f'валидация на Koren-style 6N2P model показала, что equal-resistance\n'
        f'concertina (Ra=Rk=47kΩ) biases tube near cutoff (I_a≈0.15 mA), и\n'
        f'plate-output gain атрофирует до 0.05 V/V. LTP — textbook-standard\n'
        f'для PP (Williamson 1947), robust к model parameter drift.\n\n'
        f'## Топология\n\n'
        f'```\n'
        f'                       ┌─[R_p1A 47k]─ B+ ─[R_p1B 47k]─┐\n'
        f'                       │                                │\n'
        f'  Vin ─[C_in]─[R_g 1M]─G                                G─[R_g 1M]─ GND\n'
        f'                       │  V1A         V1B  │\n'
        f'                       │ (6Н2П unit 1) (unit 2) │\n'
        f'                       K                       K\n'
        f'                        └──────┬────────┘ (common cathode rail)\n'
        f'                               R_tail 4.7k → GND\n'
        f'                       │                       │\n'
        f'                       P                       P (anti-phase outputs)\n'
        f'                       │                       │\n'
        f'              [C_couple_a 47n]            [C_couple_b 47n]\n'
        f'                       │                       │\n'
        f'                  G (V2a 6П14П)         G (V2b 6П14П)\n'
        f'                       G2 → B+                 G2 → B+\n'
        f'                       K ‖ R_k_C_k → GND       K ‖ R_k_C_k → GND\n'
        f'                       P                       P\n'
        f'                       │ ┌── PC center-tap → B+ ──┐ │\n'
        f'                       ├─[OPT.P1]               [OPT.P2]─┤\n'
        f'                       │                                  │\n'
        f'                     OPT.S1 ── [R_load 8Ω] ── OPT.S2 ── GND\n'
        f'```\n\n'
        f'## Q-point (DC operating, validated в op-point regression test)\n\n'
        f'* V_BB = 300 V; OPT.PC → B+ rail (DC primary impedance ≈ 0).\n'
        f'* V_plate_q (V2a, V2b) ≈ B+ (≈ 300 V — OPT primary DCR не critical).\n'
        f'* V_cathode_q (V2a, V2b) ≈ 10 V (auto-bias I_a · R_k = 37 mA · 270 Ω).\n'
        f'* I_a_q per output tube ≈ 37 mA (близко к 6П14П PP 12 W class A diss).\n'
        f'* LTP cathode tail ≈ 1-3 V (R_tail · 2·I_a_v1).\n'
        f'* Plate balance |V_plate_a − V_plate_b| / mean < 10% (PP symmetry).\n\n'
        f'## Mid-band gain (analytical hand-calc + ngspice empirical)\n\n'
        f'**Analytical estimate per stage:**\n\n'
        f'* LTP per-output: |A_v1| ≈ μ·R_p/(R_p+r_a) ≈ 100·47/(47+80) ≈ 37 V/V.\n'
        f'  Реально ~12 V/V — model parameter drift + downstream loading через\n'
        f'  C_couple + R_g2 (470k grid leak).\n'
        f'* 6П14П per-tube pentode gain: |A_v2| ≈ g_m·Z_a_per = 11mA/V · 1.65k\n'
        f'  ≈ 18 V/V. Реально ~28 V/V (g_m выше при V_a=300V, I_a=30mA).\n'
        f'* OPT step-down: V_sec/V_diff_prim = 1/N, N = √(R_aa/R_load) =\n'
        f'  √(6600/8) = 28.7 → 1/N = 0.035.\n'
        f'* Total: |A_v_open-loop| ≈ 12 · 28 · 0.035 ≈ 12 V/V (нижняя граница).\n\n'
        f'**Ngspice empirical (baseline):** |A_v| @ 1 kHz ≈ **16.5 V/V (24.4 dB)**.\n'
        f'Calibration regression test fails если drift > ±15%.\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — KiCad-схема\n'
        f'  (после материализации: `<имя_проекта>.kicad_sch`).\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (для GUI Simulator).\n'
        f'- `models/6N2P.lib` — splitter tubes (LTP pair, same SUBCKT).\n'
        f'- `models/6P14P.lib` — PP output tubes (pair, same model).\n'
        f'- `models/OPT_PP_6K6_8.lib` — center-tap PP output transformer.\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n\n'
        f'## Рекомендованные measurements\n\n'
        f'    # Mid-band voltage gain (open-loop, target ≈ 16.5 V/V):\n'
        f'    efactory bridge measure gain <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch --frequency 1000 --mode small\n\n'
        f'    # THD spectrum (PP топология cancels even-order distortion):\n'
        f'    efactory bridge measure thd <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch\n',
        encoding='utf-8',
    )


def _bake_tube_line_preamp(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_tube_line_preamp_builder()
    build(sch_path)  # type: ignore[operator]

    # Replace absolute model path → relative `models/...`.
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / '6N2P.lib'),
        'models/6N2P.lib',
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
        _MODELS_DIR / 'tubes' / 'custom' / '6N2P.lib',
        models_target / '6N2P.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: tube-line-preamp\n'
        'description: |\n'
        '  Two-stage all-triode line preamp на 6Н2П (обе половины ECC83):\n'
        '  Stage 1 — common-cathode voltage amp (R_p=100k, R_k=1.5k+bypass);\n'
        '  Stage 2 — cathode follower (no plate load, R_k=33k без bypass,\n'
        '  low output Z для драйва кабеля / next stage).\n'
        '  Capacitor-coupled output (C_out=0.47µF) к assumed 100kΩ load.\n'
        '  Mid-band Av ≈ 64 V/V (≈36 dB).\n'
        'summary: Tube line preamp 6Н2П CC+CF — двухкаскадный buffer-amplifier.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# tube-line-preamp template\n\n'
        f'Двухкаскадный all-triode line preamp на 6Н2П (обе половины\n'
        f'`Valve:ECC83` unit 1 + unit 2 = `Valve:ECC83B`):\n\n'
        f'- **Stage 1 (CC, common-cathode voltage amplifier):** V1A,\n'
        f'  R_p1=100 kΩ plate load, R_k1=1.5 kΩ ‖ C_k1=22 µF (standard\n'
        f'  auto-bias с bypass), C_in=100 nF input coupling.\n'
        f'- **Stage 1-2 coupling:** C_couple=47 nF inter-stage cap.\n'
        f'- **Stage 2 (CF, cathode follower):** V1B, V1B.P → directly\n'
        f'  к B+ (CF defining feature: NO plate load), R_k2=33 kΩ\n'
        f'  cathode load **без bypass** (CF inherently degenerative\n'
        f'  by design — gain ≈ 1, low output impedance).\n'
        f'- **Output:** C_out=0.47 µF к assumed next-stage 100 kΩ load\n'
        f'  (e.g., power amp grid leak).\n\n'
        f'## Топология\n\n'
        f'```\n'
        f'        ┌─[R_p1 100k]─ B+ ────────────────────────┐\n'
        f'        │                                          │\n'
        f'  Vin ─[C_in 100n]─[R_g1 1M]─G                     │\n'
        f'                              │ V1A (6Н2П unit 1)  │\n'
        f'                              K → R_k1 1.5k ‖ C_k1 22µ → GND\n'
        f'                              │\n'
        f'                              P (= V_plate1)\n'
        f'                              │\n'
        f'                       [C_couple 47n]\n'
        f'                              │\n'
        f'                       [R_g2 470k]──G\n'
        f'                                    │ V1B (6Н2П unit 2 — Cathode Follower)\n'
        f'                                    K (= V_cath2)\n'
        f'                                    │\n'
        f'                              [R_k2 33k] → GND (no bypass)\n'
        f'                                    │\n'
        f'                             [C_out 0.47µ]\n'
        f'                                    │\n'
        f'                            [R_load 100k] → GND\n'
        f'```\n\n'
        f'## Q-point (DC operating, validated в op-point regression test)\n\n'
        f'* V_BB = 250 V.\n'
        f'* Stage 1: V_plate1 ≈ 100-200 V (Stage 1 CC active region:\n'
        f'  V_a = V_BB - I_a·R_p1, I_a ≈ 0.5-1.5 mA).\n'
        f'* Stage 1: V_cathode1 ≈ 1-3 V (auto-bias через R_k1=1.5 kΩ).\n'
        f'* Stage 2: V_plate2 ≈ B+ (CF — direct supply, без plate load).\n'
        f'* Stage 2: V_cathode2 ≈ 30-100 V (CF auto-bias через R_k2=33 kΩ;\n'
        f'  large для high impedance, gain → 1).\n\n'
        f'## Mid-band gain (analytical + ngspice empirical)\n\n'
        f'**Analytical estimate (datasheet μ=100, r_a=80 kΩ):**\n\n'
        f'* Stage 1 (CC, R_k bypassed): A_v1 ≈ μ·R_p / (R_p + r_a) ≈\n'
        f'  100·100/(100+80) ≈ 55 V/V (≈ 34.8 dB).\n'
        f'* Stage 2 (CF): A_v2 ≈ (μ+1)·R_k2 / ((μ+1)·R_k2 + R_p + r_a)\n'
        f'  ≈ 0.98 (close to unity, large R_k2).\n'
        f'* Total: A_v_open-loop ≈ 55 · 0.98 ≈ 54 V/V (≈ 34.6 dB).\n\n'
        f'**Ngspice empirical:** |A_v| @ 1 kHz mid-band ≈ **64 V/V (36 dB)**\n'
        f'— на 16% выше analytical (Koren-style 6Н2П model gives g_m_eff\n'
        f'выше nominal datasheet g_m=1.6 mA/V). Calibration regression\n'
        f'fails если drift > ±15% к 64 V/V.\n\n'
        f'## Output impedance (преимущество CF stage)\n\n'
        f'Z_out_cf ≈ r_a / (μ+1) ≈ 80k / 101 ≈ **800 Ω** — низкий\n'
        f'output Z, способный драйвить кабель / power amp grid leak\n'
        f'(typical 100-470 kΩ) без HF roll-off.\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — KiCad-схема.\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (для GUI Simulator).\n'
        f'- `models/6N2P.lib` — оба stages (one tube, both halves).\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n\n'
        f'## Рекомендованные measurements\n\n'
        f'    # Mid-band voltage gain (target ≈ 64 V/V):\n'
        f'    efactory bridge measure gain <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch --frequency 1000 --mode small\n\n'
        f'    # Bandwidth (-3 dB points для CC+CF cascade):\n'
        f'    efactory bridge measure bandwidth <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch\n',
        encoding='utf-8',
    )


def _bake_tube_phono_riaa(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_tube_phono_riaa_builder()
    build(sch_path)  # type: ignore[operator]

    # Replace absolute model path → relative `models/...`.
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'koren' / '12AX7.lib'),
        'models/12AX7.lib',
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
        _MODELS_DIR / 'tubes' / 'koren' / '12AX7.lib',
        models_target / '12AX7.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: tube-phono-riaa\n'
        'description: |\n'
        '  Tube phono RIAA preamp на 12AX7 (Koren parametrization, обе\n'
        '  половины ECC83). Двухкаскадный CC + passive RIAA inter-stage\n'
        '  EQ network (Lipshitz-derived values для τ1=3180µs / τ2=318µs /\n'
        '  τ3=75µs стандартных RIAA time constants). MM cartridge input\n'
        '  ~5 mV @ 1 kHz → ~900 mV output (45 dB mid-band reference).\n'
        '  RIAA compliance ±1 dB в 20 Hz – 20 kHz audio band.\n'
        'summary: Phono preamp 12AX7 + passive RIAA — MM cartridge → line level.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# tube-phono-riaa template\n\n'
        f'Двухкаскадный all-triode phono preamp на 12AX7 (Koren\n'
        f'parametrization, `Valve:ECC83` unit 1 + unit 2 = ECC83B) с\n'
        f'**passive RIAA inter-stage EQ network**:\n\n'
        f'- **Stage 1 (CC):** R_p1=100 kΩ, R_k1=1.5 kΩ ‖ C_k1=100 µF.\n'
        f'- **C_couple_1:** 470 nF Stage 1 plate → RIAA network input.\n'
        f'- **Passive RIAA inter-stage** (Lipshitz-derived values):\n'
        f'  - R_riaa_1 = 68 kΩ (series)\n'
        f'  - C_riaa_1 = 11 nF (direct shunt to GND, τ3 contribution)\n'
        f'  - R_riaa_2 = 9.1 kΩ (series with C_riaa_2)\n'
        f'  - C_riaa_2 = 33 nF (LF/mid τ2 shunt)\n'
        f'  - R_g2 = 1 MΩ (V1B grid leak — safety reference к GND)\n'
        f'- **Stage 2 (CC):** R_p2=100 kΩ, R_k2=1.5 kΩ ‖ C_k2=100 µF.\n'
        f'- **C_out:** 0.47 µF к assumed 47 kΩ line-amp Rin.\n\n'
        f'**Mid-band reference gain @ 1 kHz: ≈ 180 V/V (≈ 45 dB)** — для\n'
        f'MM cartridge 5 mV → 900 mV line level.\n\n'
        f'## RIAA Compliance\n\n'
        f'Empirical AC sweep (ngspice 44, Koren 12AX7 patched к ngspice\n'
        f'syntax — T027 Phase C), worst error 0.65 dB @ 50 Hz:\n\n'
        f'| Freq    | Inverse RIAA target | Empirical relative | Error  |\n'
        f'|---------|---------------------|--------------------|--------|\n'
        f'| 20 Hz   | +19.27 dB           | +19.82 dB          | +0.55  |\n'
        f'| 50 Hz   | +16.95 dB           | +17.60 dB          | +0.65  |\n'
        f'| 100 Hz  | +13.09 dB           | +13.52 dB          | +0.43  |\n'
        f'| 200 Hz  | +8.22 dB            | +8.51 dB           | +0.29  |\n'
        f'| 500 Hz  | +2.65 dB            | +2.74 dB           | +0.09  |\n'
        f'| 1 kHz   | 0 dB (reference)    | 0 dB               | 0      |\n'
        f'| 2 kHz   | -2.59 dB            | -2.53 dB           | +0.06  |\n'
        f'| 5 kHz   | -8.22 dB            | -7.99 dB           | +0.23  |\n'
        f'| 10 kHz  | -13.74 dB           | -13.46 dB          | +0.28  |\n'
        f'| 20 kHz  | -19.62 dB           | -19.33 dB          | +0.29  |\n\n'
        f'**Compliance ±1 dB в 20 Hz – 20 kHz audio band ✓** (per spec §4).\n\n'
        f'## Lipshitz design math\n\n'
        f'Для inverse RIAA transfer function `H(s) = (1+sτ2)/((1+sτ1)(1+sτ3))`\n'
        f'на series-shunt topology (R1 series + (R2+C2)‖C1 shunt to GND):\n\n'
        f'- τ2 = R2·C2 = 318 µs\n'
        f'- τ_X = R1·(C1+C2) = τ1 + τ3 - τ2 = 2937 µs\n'
        f'- τb = R2·C1·C2/(C1+C2) = τ1·τ3/τ_X = 81.2 µs\n'
        f'- Solving: C1/C2 = 0.343, R1 = 66.3 kΩ\n\n'
        f'E12 nearest values: R1=68k, R2=9.1k, C1=11n, C2=33n. Resulting\n'
        f'effective τ1=3222 µs (target 3180, +1.3%), τ3=69.7 µs (target 75,\n'
        f'-7%). Within ±1 dB compliance budget.\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — KiCad-схема.\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project (для GUI Simulator).\n'
        f'- `models/12AX7.lib` — Koren parametrization (ngspice-syntax\n'
        f'  patched T027 Phase C 2026-06-02, original HSPICE `PWRS()` →\n'
        f'  `sgn·pwr·abs` equivalent).\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n\n'
        f'## Рекомендованные measurements\n\n'
        f'    # Mid-band reference gain (target ≈ 180 V/V = 45 dB):\n'
        f'    efactory bridge measure gain <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch --frequency 1000 --mode small\n\n'
        f'    # Bandwidth + RIAA compliance check (AC sweep 20Hz-20kHz):\n'
        f'    efactory bridge measure bandwidth <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch --f-low 20 --f-high 20000\n',
        encoding='utf-8',
    )


def _bake_active_lpf_sallen_key(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    build = _import_active_lpf_sallen_key_builder()
    build(sch_path)  # type: ignore[operator]

    # Replace absolute model path → relative `models/...`.
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'opamps' / 'generic' / 'TL072.lib'),
        'models/TL072.lib',
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
        _MODELS_DIR / 'opamps' / 'generic' / 'TL072.lib',
        models_target / 'TL072.lib',
    )

    (target_dir / 'template.yaml').write_text(
        'name: active-lpf-sallen-key\n'
        'description: |\n'
        '  2nd-order Butterworth Sallen-Key low-pass filter с unity-gain\n'
        '  VCVS на TL072 op-amp. Equal-R, unequal-C topology (C1/C2=2 strict\n'
        '  per Analyze W1) для proper Butterworth Q=0.707. f_c = 1024 Hz\n'
        '  (1 kHz default), HF rolloff -40 dB/decade.\n'
        'summary: Sallen-Key Butterworth LPF f_c=1kHz — TL072 VCVS reference.\n',
        encoding='utf-8',
    )

    (target_dir / 'README.md').write_text(
        f'# active-lpf-sallen-key template\n\n'
        f'**2nd-order Butterworth low-pass filter** в classic Sallen-Key\n'
        f'voltage-controlled voltage-source (VCVS) topology с unity-gain\n'
        f'op-amp follower (TL072).\n\n'
        f'## Component values\n\n'
        f'**Equal-R, unequal-C** (per spec Analyze W1 — exact Butterworth\n'
        f'Q=0.707 требует C1/C2=2 strict, не achievable с equal-C/equal-R):\n\n'
        f'- R1 = R2 = 10 kΩ (filter resistors)\n'
        f'- C1 = 22 nF (mid → vout feedback path)\n'
        f'- C2 = 11 nF (in_p → GND shunt) — *NOT standard E12, BOM = 10n + 1n parallel*\n'
        f'- R_load = 100 kΩ (assumed next-stage input impedance)\n'
        f'- TL072 op-amp (unity-gain follower: IN- tied to OUT)\n\n'
        f'## Filter parameters\n\n'
        f'- **Cutoff f₀** = 1/(2π·R·√(C1·C2)) = 1/(2π·10k·15.56n)\n'
        f'  = **1024 Hz** ≈ 1 kHz\n'
        f'- **Q** = 0.5·√(C1/C2) = 0.5·√2 = **0.707** (Butterworth ideal)\n'
        f'- Rolloff: **-40 dB/decade** above f_c (2nd-order)\n'
        f'- Passband: **unity gain** (0 dB), monotonic (no peaking)\n\n'
        f'## Топология\n\n'
        f'```\n'
        f'  Vin ──[R1 10k]──┬──[R2 10k]──┬── IN+ (TL072)\n'
        f'                  │             │\n'
        f'                  C1 22n        C2 11n\n'
        f'                  │             │\n'
        f'                 Vout          GND\n'
        f'                  ↑\n'
        f'                  │\n'
        f'   IN-(TL072) ────┤\n'
        f'                  │\n'
        f'   OUT(TL072) ────┴── Vout ──[R_load 100k]── GND\n'
        f'```\n\n'
        f'IN- tied to OUT — **unity-gain VCVS** (voltage follower).\n\n'
        f'## Empirical calibration (ngspice baseline)\n\n'
        f'| Freq    | Measured rel | Butterworth ideal | Error  |\n'
        f'|---------|--------------|-------------------|--------|\n'
        f'| 10 Hz   | 0.000 dB     | 0.000 dB          | 0.000  |\n'
        f'| 100 Hz  | 0.000 dB     | -0.004 dB         | +0.004 |\n'
        f'| 500 Hz  | -0.240 dB    | -0.281 dB         | +0.041 |\n'
        f'| 1024 Hz | -3.018 dB    | -3.010 dB         | -0.008 |\n'
        f'| 2 kHz   | -11.94 dB    | -12.31 dB         | +0.37  |\n'
        f'| 10 kHz  | -39.62 dB    | -39.74 dB         | +0.12  |\n\n'
        f'**Perfect Butterworth response — within 0.4 dB across все sweep.**\n\n'
        f'## TL072 macromodel\n\n'
        f'`models/TL072.lib` — minimal two-pole macromodel matching TL072\n'
        f'datasheet specs (A0=2e5, GBW=3 MHz, fp1=15 Hz, fp2≈5 MHz,\n'
        f'Rout=200 Ω). T027 Phase D bootstrap. Для high-fidelity\n'
        f'production simulation — заменить на full TI macromodel.\n\n'
        f'## Файлы\n\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_sch` — KiCad-схема.\n'
        f'- `{PROJECT_NAME_PLACEHOLDER}.kicad_pro` — KiCad project.\n'
        f'- `models/TL072.lib` — op-amp macromodel.\n\n'
        f'## Запуск симуляции\n\n'
        f'    /sim-run\n'
        f'    # или напрямую:\n'
        f'    efactory bridge sim-run --schematic <имя_проекта>.kicad_sch\n\n'
        f'## Рекомендованные measurements\n\n'
        f'    # Single-point gain @ passband (should be ≈ 0 dB):\n'
        f'    efactory bridge measure gain <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch --frequency 100 --mode small\n\n'
        f'    # Bandwidth (-3 dB cutoff verification):\n'
        f'    efactory bridge measure bandwidth <PROJECT> \\\n'
        f'        --schematic <PROJECT>.kicad_sch --f-low 10 --f-high 100000\n',
        encoding='utf-8',
    )


def _bake_pentode_se_resistive(
    target_dir: Path,
    *,
    template_name: str,
    tube_id: str,
    lib_filename: str,
    builder: object,
    template_yaml: str,
) -> None:
    """Shared baker для 3 T187 pentode SE-resistive templates.

    Снап координат в facade автоматически фиксит off-grid R3/C2
    (T187 Phase 4). Pattern по канве `_bake_se_amp`.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    sch_path = target_dir / f'{PROJECT_NAME_PLACEHOLDER}.kicad_sch'
    builder(sch_path)  # type: ignore[operator]

    # Builder embeds абсолютный путь `<repo>/data/models/tubes/custom/
    # <ID>.lib`. Заменяем на relative `models/...` для shipping.
    sch_text = sch_path.read_text(encoding='utf-8')
    sch_text = sch_text.replace(
        str(_MODELS_DIR / 'tubes' / 'custom' / lib_filename),
        f'models/{lib_filename}',
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
        _MODELS_DIR / 'tubes' / 'custom' / lib_filename,
        models_target / lib_filename,
    )

    (target_dir / 'template.yaml').write_text(template_yaml, encoding='utf-8')

    (target_dir / 'README.md').write_text(
        f'# {template_name} template\n\n'
        f'Single-stage class-A pentode SE-amp на {tube_id} с резистивной\n'
        f'нагрузкой Ra (без OPT). Pattern T031 Phase 5; builder восстановлен\n'
        f'в T187 Phase 4 как proper Python (`test_pentode_se_resistive_facade.py`).\n\n'
        '## Файлы\n\n'
        '- `{{PROJECT_NAME}}.kicad_sch` — схема.\n'
        '- `{{PROJECT_NAME}}.kicad_pro` — KiCad project.\n'
        f'- `models/{lib_filename}` — fitted Koren-pentode model.\n\n'
        '## Запуск симуляции\n\n'
        '    /sim-run\n',
        encoding='utf-8',
    )


_PENTODE_TEMPLATE_YAMLS: dict[str, str] = {
    '6p13s-se-resistive': (
        'name: 6p13s-se-resistive\n'
        'description: |\n'
        '  6П13С (Soviet beam tetrode, 14W Pa, TV line scan output) — SE-amp\n'
        '  с резистивной нагрузкой 5kΩ вместо OPT (per T031 spec A-W3).\n'
        '  Vbb=250V, Vg2=200V fixed, Rk=470Ω+bypass (T173 refined bias).\n'
        '  Typical op-point: Ia ≈ 25-30 mA, screen dissipation in bounds.\n'
        'summary: 6П13С SE-amp с резистивной нагрузкой (no OPT).\n'
    ),
    '6zh32p-mic-preamp': (
        'name: 6zh32p-mic-preamp\n'
        'description: |\n'
        '  Микрофонный преамп на 6Ж32П (Soviet low-noise audio pentode, '
        'аналог EF86).\n'
        '  Class A common-cathode pentode stage, gain ≈40 dB (×100) @ 1 kHz,\n'
        '  bandwidth 9.5 Hz – 87 kHz (flat 20-20k ±0.3 dB), питание 250 V.\n'
        '  Self-bias через Rk=2.7k‖100µF. EF86 noval pinout (2=K, 3=G, '
        '6=P, 8=G2)\n'
        '  — готов к разводке PCB. T031 Phase 6 agent-built (test scenario).\n'
        'summary: 6Ж32П микрофонный preamp 40 dB / 20-20k Hz, class A pentode.\n'
    ),
    '6zh38p-if-amp': (
        'name: 6zh38p-if-amp\n'
        'description: |\n'
        '  6Ж38П (= 6BH6 / EF190 western eq.) — resistance-coupled '
        'small-signal\n'
        '  pentode preamp. Vbb=150V, Vg2=150V fixed, Rp=10k, Rk=1k+bypass.\n'
        '  Typical op-point Vg=-1V: Ia ≈ 7 mA, Va_anode ≈ 80V, gain ≈ 100.\n'
        '  Pattern: GE 6BH6 datasheet ET-T525B Class A resistance-coupled amp.\n'
        'summary: 6Ж38П class A IF/AF preamp с резистивной нагрузкой.\n'
    ),
}


def _bake_6p13s_se_resistive(target_dir: Path) -> None:
    _bake_pentode_se_resistive(
        target_dir,
        template_name='6p13s-se-resistive',
        tube_id='6P13S',
        lib_filename='6P13S.lib',
        builder=_import_6p13s_se_resistive_builder(),
        template_yaml=_PENTODE_TEMPLATE_YAMLS['6p13s-se-resistive'],
    )


def _bake_6zh32p_mic_preamp(target_dir: Path) -> None:
    _bake_pentode_se_resistive(
        target_dir,
        template_name='6zh32p-mic-preamp',
        tube_id='6ZH32P',
        lib_filename='6ZH32P.lib',
        builder=_import_6zh32p_mic_preamp_builder(),
        template_yaml=_PENTODE_TEMPLATE_YAMLS['6zh32p-mic-preamp'],
    )


def _bake_6zh38p_if_amp(target_dir: Path) -> None:
    _bake_pentode_se_resistive(
        target_dir,
        template_name='6zh38p-if-amp',
        tube_id='6ZH38P',
        lib_filename='6ZH38P.lib',
        builder=_import_6zh38p_if_amp_builder(),
        template_yaml=_PENTODE_TEMPLATE_YAMLS['6zh38p-if-amp'],
    )


_BAKERS: dict[str, object] = {
    'se-amp': _bake_se_amp,
    'nfb-se-amp': _bake_nfb_se_amp,
    'op-amp-inverting': _bake_op_amp_inverting,
    'bjt-ce-nfb': _bake_bjt_ce_nfb,
    'tube-pp-amp': _bake_tube_pp_amp,
    'tube-line-preamp': _bake_tube_line_preamp,
    'tube-phono-riaa': _bake_tube_phono_riaa,
    'active-lpf-sallen-key': _bake_active_lpf_sallen_key,
    '6p13s-se-resistive': _bake_6p13s_se_resistive,
    '6zh32p-mic-preamp': _bake_6zh32p_mic_preamp,
    '6zh38p-if-amp': _bake_6zh38p_if_amp,
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

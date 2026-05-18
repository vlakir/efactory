# SPICE-моделей библиотека efactory (T006 + T007)

Built-in библиотека для CLI `efactory tube/transformer/load list/show`
и future bridges (T004+). Структура:

```
data/models/
├── tubes/          # category=tube — лампы (T006)
│   ├── koren/      # Norman Koren-style fits
│   ├── ayumi/      # Ayumi-style (`^` exponent → converted to `**`)
│   ├── duncan/     # Duncan/Cigna коллекция
│   └── custom/     # советские лампы + custom
├── transformers/   # category=transformer — OPT, IT, PT, choke (T007)
│   └── generic/    # generic typical-class fits
└── loads/          # category=load — speakers + dummy loads (T007)
    └── generic/
```

## Adapter контракт

Subdir1 = `category` (tubes / transformers / loads). Subdir2 = `source`
(koren/ayumi/duncan/custom для tubes; generic + vendor-specific для
других).

Каждый файл `.lib`/`.inc`/`.cir` содержит:
- header `* subcategory: <value>` (для transformers/loads **обязателен**;
  для tubes — legacy `* tube_type:` тоже работает, или header опциональный
  если pin-эвристики хватает).
- одну `.SUBCKT NAME P1 P2 ... .ENDS [NAME]` секцию.

`id` = uppercase filename stem. Duplicate id в одной категории → fail-fast.
User overlay (`<storage_root>/models/...`) перезаписывает built-in по id.

## CLI

```bash
efactory tube list                       # все лампы
efactory tube show --id 12AX7
efactory transformer list                # все трансформаторы
efactory transformer show --id OPT_SE_5K_8
efactory load list                       # speakers + dummy loads
efactory load show --id SPEAKER_8OHM
```

Каждый subapp фильтрует общий SpiceModelLibrary по category. Если
вызвать `tube show --id OPT_SE_5K_8` — exit 1 с подсказкой
правильного subapp.

## Каталоги

- [tubes/README.md](tubes/README.md) — таблица ~50 ламп
  (preamp / driver / DHT / pentodes / rectifiers / советские).
- **transformers/** (T007):
  - `OPT_SE_5K_8` — SE OPT 5kΩ:8Ω (для 300B/EL84/6P14P SE).
  - `OPT_PP_6K6_8` — PP OPT 6.6kΩ:8Ω center-tapped (для EL34/KT88 PP).
- **loads/** (T007):
  - `SPEAKER_8OHM` — 8Ω speaker с mechanical резонансом ~70 Hz.
  - `SPEAKER_8OHM_RES` — чисто 8Ω R (для AC sweep без артефактов).
  - `SPEAKER_4OHM` — 4Ω вариант с резонансом ~60 Hz.
  - `DUMMY_LOAD_8R` — power resistor 8Ω (для P_max / THD measurements).

## Качество параметров

Все built-in модели — **typical-sample** из открытых источников:
- Tubes: [Koren](http://www.normankoren.com/Audio/Tubemodspice_article.html),
  [Ayumi](http://www.duncanamps.com/technical/ayumi/),
  [Duncan/Cigna](http://tdsl.duncanamps.com/dcigna/tubes/spice/).
- Transformers / loads: Hammond 1627A/1650F class, generic hi-fi
  speaker.

Реальные параметры — ±20% по току / ±15% по gm для ламп; OPT /
speaker зависят от конкретного экземпляра. Для production designs:
- T031 — Tube-curve-fitting (per-batch fit).
- T052 — `mag_design_transformer` (расчёт OPT под лампу/выход).
- T055 — `mag_verify_femm` (FEMM-проверка).

## User overlay

Положить файл в `~/.local/share/efactory/models/<category>/<source>/<NAME>.<ext>`:

```bash
mkdir -p ~/.local/share/efactory/models/tubes/custom
cat > ~/.local/share/efactory/models/tubes/custom/MY_TUBE.lib <<'EOF'
* subcategory: triode
.SUBCKT MY_TUBE P G K
... model body ...
.ENDS MY_TUBE
EOF
```

`efactory tube list` покажет `MY_TUBE` рядом с built-in.

User-id с тем же именем переписывает built-in (полезно если у вас
кастомные параметры под конкретный экземпляр лампы).

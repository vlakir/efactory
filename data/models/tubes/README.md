# Built-in SPICE-моделей ламп (T006)

Структура каталога:

```
tubes/
├── koren/      # Norman Koren-style triode/pentode models
├── ayumi/      # Ayumi Nakabayashi style (`^` оператор; конвертируется в `**` на чтении)
├── duncan/     # Duncan's Amp Pages (заполняется bootstrap T002)
└── custom/     # советские лампы + наши custom — не входят в upstream-коллекции
```

## Что есть сейчас (~12 моделей)

| ID | Type | Аналог | Назначение |
|----|------|--------|-----------|
| `12AX7` | triode | ECC83 | preamp, high-gain |
| `12AU7` | triode | ECC82 | driver, cathode follower |
| `6SN7` | triode | — | audiophile driver / phase splitter |
| `6DJ8` | triode | ECC88, E88CC | RF, hi-gm preamp |
| `300B` | triode | — | SE power triode (legendary) |
| `EL34` | pentode | 6CA7 | output ~25 W |
| `6L6` | pentode (beam tetrode) | 6L6GC | output ~30 W |
| `6V6` | pentode (beam tetrode) | 6V6GT | output ~12 W |
| `KT88` | pentode (beam tetrode) | 6550 | output ~42 W premium |
| `6N2P` | triode | 12AX7 / ECC83 | советский preamp |
| `6N3P` | triode | 5670 / 2C51 | советский ВЧ-триод |
| `6P14P` | pentode | EL84 / 6BQ5 | советский output ~5 W |
| `6P3S` | pentode | 6L6G | советский output ~25 W |
| `GENERIC_TRIODE` | triode | — | пример формата (не реальная лампа) |
| `GENERIC_PENTODE` | pentode | — | пример формата (Ayumi с `^`) |

## Качество параметров

**Все built-in модели — typical-sample**: параметры из публичных
Koren / Ayumi datasets, отражают паспортные кривые усреднённой лампы.
Реальные образцы могут отличаться на ±20% по току / ±15% по gm.

Для production-grade designs используйте Tube-curve-fitting
(roadmap T031) против измерений ваших конкретных ламп.

## Как добавить свою

**Built-in (правка репо):** положить `.lib`/`.inc`/`.cir` файл в
один из subdir'ов. `id` = uppercase filename stem. Header
`* tube_type: triode|pentode|tetrode|dual_triode` приоритет над
автоматической эвристикой по числу пинов.

**User overlay (без правки репо):** `<storage_root>/models/tubes/`
(`~/.local/share/efactory/models/tubes/` по умолчанию). User-id
с тем же именем перезаписывает built-in. См. README efactory.

## Формат файла

```
* <Name> — <description>
* tube_type: triode | pentode | tetrode | dual_triode
* Pins: <P G K | P G2 G K | P1 G1 K1 P2 G2 K2>
.SUBCKT <NAME> <pin list>
... Koren / Ayumi equations ...
.ENDS <NAME>
```

См. `koren/GENERIC_TRIODE.lib` и `ayumi/GENERIC_PENTODE.inc` —
живой пример формата.

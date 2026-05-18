# Built-in SPICE-моделей ламп (T006)

Структура каталога:

```
tubes/
├── koren/      # Norman Koren-style triode/pentode/rectifier models
├── ayumi/      # Ayumi Nakabayashi style (`^` оператор; конвертируется в `**` на чтении)
├── duncan/     # Duncan / Cigna коллекция (альтернативные fits + уникальные)
└── custom/     # советские лампы + редкие; не входят в Koren/Ayumi/Duncan upstream
```

## Что есть (~50 моделей)

### Triodes — single section

| ID | Аналог | Назначение |
|----|--------|-----------|
| `12AX7`, `12AX7_DUNCAN` | ECC83 | preamp, high-gain |
| `12AU7` | ECC82 | driver, cathode follower |
| `12AT7` | ECC81 | RF / driver / phase splitter |
| `12BH7` | — | heavy-duty driver (для 300B/2A3) |
| `6SN7`, `6SN7_DUNCAN`, `6N8S` | — | audiophile driver / phase splitter |
| `6CG7` | 6SN7 noval | 9-pin вариант 6SN7 |
| `6SL7`, `6N9S` | — | high-mu octal preamp |
| `6DJ8` | ECC88 | RF / hi-gm preamp |
| `6N1P` | ECC85 / 6BQ7A | универсальный preamp |
| `6N6P` | 5687 | low-rp driver / cathode follower |

### Triodes — power / DHT

| ID | Pmax | Назначение |
|----|------|-----------|
| `300B`, `300B_DUNCAN` | 8 W SE | легендарный SE Hi-Fi |
| `2A3` | 3.5 W SE | классика 1930-х |
| `845` | 20 W SE | high-voltage DHT |
| `211` | 12 W SE | transmitting / hi-end |
| `6C33C` | 30 W SE | OTL Hi-Fi (Atma-Sphere) |
| `6080`, `6AS7G` | low-mu | OTL / power regulator |
| `GM70` | 125 W | советский transmitting DHT |

### Pentodes / Beam tetrodes — output

| ID | Pmax | Аналог | Применение |
|----|------|--------|-----------|
| `EL34`, `EL34_DUNCAN`, `6CA7` | 25 W | KT77 | Marshall / Hi-Fi |
| `6L6`, `6P3S`, `7027` | 30 W | — | Fender / RCA / Ampeg |
| `6V6`, `6V6_AYUMI` | 12 W | — | small combos |
| `KT88`, `KT90` | 42-50 W | 6550 | premium Hi-Fi |
| `KT66` | 25 W | "British 6L6" | McIntosh |
| `KT77` | 25 W | "British EL34" | hi-fi |
| `5881` | 23 W | mil-spec 6L6 | rugged PA |
| `7591` | 19 W | — | Fisher / Scott Hi-Fi |
| `6P14P` | 5 W | EL84 / 6BQ5 | советский SE |
| `6P1P` | 4 W | 6AQ5 | small Hi-Fi |
| `6P18P` | 6 W | EL83 | low-power audio |
| `6P15P` | — | EF184 | ВЧ pentode |
| `6P45S` | 60 W | — | hi-power audio |
| `GU50` | 40 W | LS50 | советский transmitting |
| `6BM8` | — | ECL82 | pentode секция compactron |

### Pentodes — small-signal / preamp

| ID | Назначение |
|----|-----------|
| `EF86` | low-noise preamp/microphone (Vox, EICO) |

### Rectifiers

| ID | Type | Imax | Назначение |
|----|------|------|-----------|
| `5AR4` / `GZ34` | indirectly-heated full-wave | 250 mA | premium Hi-Fi |
| `5U4G` | DH full-wave (soft sag) | 225 mA | guitar amps |
| `5Y3GT` | DH full-wave | 125 mA | Fender Champ |
| `EZ80` / `6V4` | IH full-wave 9-pin | 90 mA | preamp PSU |
| `EZ81` / `6CA4` | IH full-wave 9-pin | 150 mA | mid-power |
| `5C3S` | советский (= 5U4G) | 225 mA | — |
| `5C4S` | советский (= 5Y3) | 125 mA | — |
| `6C4P` | советский (= EZ81) | 150 mA | — |

### Formatting references (не реальные лампы)

| ID | Назначение |
|----|-----------|
| `GENERIC_TRIODE` | живой пример Koren-style формата |
| `GENERIC_PENTODE` | пример Ayumi-style с `^` оператором |

## Качество параметров

Все built-in модели — **typical-sample**: параметры из публичных
Koren / Ayumi / Duncan datasets, отражают паспортные кривые
усреднённой лампы. Реальные образцы могут отличаться на ±20% по току /
±15% по gm.

Для production-grade designs используйте Tube-curve-fitting
(roadmap T031) против измерений ваших конкретных ламп.

Источники:
- Norman Koren — http://www.normankoren.com/Audio/Tubemodspice_article.html
- Duncan's Amp Pages (Cigna) — http://tdsl.duncanamps.com/dcigna/tubes/spice/
- Ayumi Nakabayashi — http://www.duncanamps.com/technical/ayumi/

## Tube type detection

Adapter определяет `tube_type` в два шага:

1. **Header** (приоритет) — комментарий `* tube_type: <type>` перед `.SUBCKT`.
   Значения: `triode`, `tetrode`, `pentode`, `dual_triode`, `rectifier`.
2. **Pin-count fallback** — если header нет:
   - 2 пина → `rectifier` (half-wave)
   - 3 пина → `triode`
   - 4-5 пинов → `pentode`
   - 6+ пинов → `dual_triode`

**Важно для rectifier:** 3-pin full-wave rectifier неотличим по count от
триода — header `* tube_type: rectifier` **обязателен**.

## Rectifier model approach

Каждый плейт моделируется как ngspice `.MODEL D` с vacuum-style I-V:
- IS — saturation current (определяет knee).
- RS — series resistance (определяет forward drop).
- N — emission coefficient (~2.0 для vacuum diode).
- BV — breakdown voltage.

Игнорируется cathode warm-up delay (sag dynamics) — для design
simulation несущественно. Для точного моделирования sag — Duncan
DULEREC macromodel (отдельная задача).

## Как добавить свою модель

**Built-in (правка репо):** положить `.lib`/`.inc`/`.cir` файл в один
из subdir'ов. `id` = uppercase filename stem. Header
`* tube_type: <type>` приоритет над автоматической эвристикой.

**User overlay (без правки репо):** `<storage_root>/models/tubes/`
(`~/.local/share/efactory/models/tubes/` по умолчанию). User-id с тем же
именем перезаписывает built-in. См. README efactory.

## Формат файла

```
* <Name> — <description>
* Source: <reference>
* tube_type: triode | pentode | tetrode | dual_triode | rectifier
* Pins: <P G K | P G2 G K | A1 A2 K | P1 G1 K1 P2 G2 K2>
.SUBCKT <NAME> <pin list>
... Koren / Ayumi / ngspice equations ...
.ENDS <NAME>
```

См. `koren/GENERIC_TRIODE.lib`, `ayumi/GENERIC_PENTODE.inc`,
`koren/5AR4.lib` — живые примеры разных типов.

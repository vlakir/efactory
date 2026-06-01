---
topic: spice.ngspice-syntax-compat
description: PWRS/^ HSPICE-syntax incompatibilities в Koren/Ayumi tube models — converter usage и patching
tags: [spice, ngspice, hspice, pspice, syntax, converter, koren, ayumi, tube, pwrs, compatibility]
---
# ngspice-syntax-compat для tube models: PWRS, `^`, converters

## Когда смотреть в этот topic

- `Error: no such function 'pwrs' at line N` от ngspice при `.include`
  tube model.
- Чужой tube model файл с `PWRS(V(7), 1.4)` или `V(P,K)^2` в expression.
- Tube SUBCKT in Koren/Ayumi source format (HSPICE/PSpice convention)
  — нужно использовать в ngspice 44+.
- Adding new tube model file — выбор правильного syntax.

## Quick reference

| HSPICE/PSpice | ngspice 44 | Где fix |
|---------------|------------|---------|
| `PWRS(x, y)` | `sgn(x)*pwr(abs(x), y)` | data file patch ИЛИ `convert_pwrs_to_ngspice` |
| `V(P,K)^2` | `V(P,K)**2` | data file patch ИЛИ `convert_ayumi_to_ngspice` |
| `pow(x, y)` ↔ `pwr(x, y)` | both work | no change |

## Existing converters в efactory

`src/adapters/outbound/spice_models/conversion.py` exports две функции:

### `convert_ayumi_to_ngspice(text: str) -> str`

Заменяет `^` на `**` глобально. Idempotent. **Wired** в
`spice_library.read_subckt` только для models с `ModelSource.AYUMI`
(line 279-281 in `spice_library.py`).

### `convert_pwrs_to_ngspice(text: str) -> str`

Char-by-char parser с balanced-paren detection, поддерживает:
- Nested PWRS (recursive).
- Multiple PWRS в одном expression.
- Case-insensitive (`PWRS`, `pwrs`, `Pwrs`).
- `MYPWRS(` и подобные identifier-суффиксы НЕ матчатся (clean
  boundary detection через regex lookbehind).

Idempotent — после первого прохода result не содержит PWRS,
повторное применение → no-op.

**Status:** defined but **NOT wired** в production read pipeline.
То есть `spice_library.read_subckt` НЕ применяет converter автоматически
(только `convert_ayumi_to_ngspice` для Ayumi-source).

## Use cases для agent

### Case 1: Agent encounters ngspice PWRS error при `.include` tube model

**Симптом:** `Error: no such function 'pwrs' at line N from file <X.lib>`.

**Diagnosis:** model file использует HSPICE syntax. ngspice 44 без
compatibility-mode flag не разпознаёт `PWRS()`.

**Fix path:**
1. Check status — model в Koren collection (`data/models/tubes/koren/`)?
   - **Все 15 Koren models patched в T027 Phase C 2026-06-02** (ADR-T027c
     в `DECISIONS.md`). Already use ngspice syntax. Если PWRS error
     surface'ит — git pull missed.
2. Check Ayumi collection (`data/models/tubes/ayumi/`)?
   - **Ayumi files contain `PWRS()` + `^` оба.** Только если loaded
     через `spice_library.read_subckt` они auto-converted (Ayumi
     branch line 279-281). При `.include <abs_path>` direct embed —
     ngspice читает as-is, both bugs surface.
3. Direct fix data file: apply patch pattern
   `PWRS(<expr>, <power>) → sgn(<expr>)*pwr(abs(<expr>), <power>)`.
   Idempotent.

### Case 2: Adding new tube model file

**Pattern:** новые tube models в efactory **должны** использовать
ngspice-compatible syntax с самого начала:

```
G1 P K VALUE={(sgn(V(7))*pwr(abs(V(7)),1.4)+sgn(V(7))*pwr(abs(V(7)),1.4))/KG1}
```

а не HSPICE-style:

```
G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/KG1}
```

Working reference template — `data/models/tubes/custom/6N2P.lib`
(Koren-style triode, ngspice-syntax из коробки).

### Case 3: Programmatic patching multiple files (Phase C precedent)

T027 Phase C 2026-06-02 patched 15 Koren files через Python script:

```python
import re
from pathlib import Path

koren_dir = Path('data/models/tubes/koren')
pattern = re.compile(r'PWRS\(V\(7\),([\d.]+)\)')
for lib in sorted(koren_dir.glob('*.lib')):
    text = lib.read_text(encoding='utf-8')
    if 'PWRS' not in text:
        continue
    new_text = pattern.sub(r'sgn(V(7))*pwr(abs(V(7)),\1)', text)
    lib.write_text(new_text, encoding='utf-8')
```

**Better approach** для broader scope: import existing
`convert_pwrs_to_ngspice` and apply to file text — handles nested
PWRS, arbitrary expressions внутри PWRS args, etc. Simple regex only
works для `PWRS(V(N), <number>)` pattern.

```python
from adapters.outbound.spice_models.conversion import convert_pwrs_to_ngspice

for lib in koren_dir.glob('*.lib'):
    text = lib.read_text()
    patched = convert_pwrs_to_ngspice(text)
    if patched != text:
        lib.write_text(patched)
```

### Case 4: Wiring converter into production read pipeline

**Currently NOT done** — `convert_pwrs_to_ngspice` defined but unused
in `spice_library.read_subckt`. Future enhancement (T029+?) could
wire it universally:

```python
def _read() -> str:
    raw = model.file_path.read_text(encoding='utf-8')
    block = _extract_subckt_block(raw)
    # Apply converters universally (idempotent).
    block = convert_pwrs_to_ngspice(block)
    if model.source is ModelSource.AYUMI:
        block = convert_ayumi_to_ngspice(block)
    return block
```

**Benefits:**
- Tube libraries without manual patches.
- Adding 3rd-party PWRS-containing tube files JustWorks.
- Maintains data files в original "upstream" syntax for citation/sync
  с original sources (Koren/Ayumi/Duncan upstream).

**Drawbacks (why not done в Phase C):**
- Doesn't help `.include <abs_path>` workflow (used by current
  schematic builders). Builders embed `Sim.Library "/abs/path/to/.lib"`
  в KiCad component property → ngspice reads file directly, not
  через `spice_library`.
- Phase C precedent — patched data files instead (works for both
  paths).

## Two workflows для loading tube models в SPICE

efactory имеет TWO paths к SPICE-level tube model:

### Path A: `.include` directive via schematic builder

```python
# tests/integration/adapters/schematic_kicad/test_*_facade.py
xv1 = sch.add_tube(
    spice_model=SpiceModel(
        id='12AX7',
        file_path=Path('data/models/tubes/koren/12AX7.lib'),
        ...
    ),
    at=(88.9, 88.9),
    symbol='Valve:ECC83',
)
```

`add_tube` embeds `Sim.Library "<absolute path>"` в KiCad component
property. `kicad-cli sch export spice` пишет `.include <abs path>`
directive в .cir. ngspice reads file **as-is** при simulation start.

**Implication:** model file должен быть ngspice-syntax-clean. Phase C
patched 15 Koren files именно для этого workflow.

### Path B: `read_subckt()` API через library

```python
# src/adapters/outbound/spice_models/spice_library.py
library = FilesystemSpiceModelLibrary(...)
subckt_text = await library.read_subckt('12AX7')
# Returns text with ^ → ** converted (Ayumi only)
```

Path B applies `convert_ayumi_to_ngspice` для Ayumi-source models.
`convert_pwrs_to_ngspice` НЕ применяется. Используется для:
- `efactory tube show --id 12AX7` (display)
- Listing / metadata operations.

**Implication:** Path B вызовы получают partially-converted text для
Ayumi, raw text для остальных. Не SPICE simulation pipeline.

## Reference

- `src/adapters/outbound/spice_models/conversion.py` — converters.
- `src/adapters/outbound/spice_models/spice_library.py` — read pipeline,
  только Ayumi triggers converter at line 279-281.
- `data/models/tubes/custom/6N2P.lib` — exemplar of ngspice-syntax tube
  model (no patches needed).
- `data/models/tubes/koren/*.lib` — all 15 patched in T027 Phase C
  (ADR-T027c, 2026-06-02).
- `data/models/tubes/ayumi/*.inc` — still contain `PWRS()` + `^` for
  `.include` workflow (BACKLOG: patch when needed for direct simulation).
- KB topic `spice.tube-phono-riaa` — Phase C precedent + Koren patch
  rationale.

# Phase 6 — Agent live smoke test + 6Ж32П artefacts close-out

**Дата:** 2026-06-04
**Статус:** ✓ Agent end-to-end pipeline PASSED, host artefacts promoted
**Спека:** Live acceptance T031 KB-sync + Phase 5 templates через
runtime agent в `efactory:linux` контейнере. Vladimir-initiated test
scenario.

---

## 1. Test scenario

Vladimir as user → agent в efactory:linux: «разработай микрофонный
усилитель на 6Ж32П». Полная задача (5 шагов):

1. Найти datasheet 6Ж32П в сети.
2. Сделать SPICE модель штатными средствами efactory (без велосипедов).
3. Нарисовать схему преампа.
4. Промоделировать + verify характеристики.
5. Создать template для повторного использования.

Целевые характеристики: gain ~40 dB / BW 20-20k Hz / питание ~250 V /
low noise (6Ж32П == EF86, известная low-noise audio pentode).

Coverage acceptance:
- **L1+L2 KB-sync** (T134 discipline): сможет ли agent через KB
  routing самостоятельно дойти до правильных slash/CLI без подсказок?
- **Phase 5 templates discoverability:** разглядит ли agent
  `6zh38p-if-amp` как baseline для родственной 6Ж32П?
- **T031 pipeline end-to-end:** vision → JSON → fit → .lib → schematic
  adapt → sim → measure через одного агента в одном flow.

## 2. Agent's autonomous trajectory

Agent выполнил всю задачу autonomously (с минимальными user
clarification'ами по требованиям ТЗ — тип микрофона, balanced vs SE,
discretion).

**Steps observed (from agent's final report):**

1. **Routing.** Agent сам нашёл `6zh38p-if-amp` template через KB topic
   `spice.tube-rf-amp-6zh38p` (Phase 5 KB-sync entries). Корректно
   отверг `se-amp` (OPT 5k:8Ω для динамика — лишний шаг). Это **прямое
   подтверждение L1+L2 sync работает.**

2. **Datasheet hunt.** WebSearch → нашёл Svetlana EF86 datasheet 10/96
   (drtube.com/datasheets/ef86-sed1996.pdf). Корректная identification
   6Ж32П = EF86 (Soviet equivalent).

3. **SPICE fit (T031 pipeline).** Vision-extracted 53 IV-точки →
   `efactory tube fit-from-points 6ZH32P --type pentode ...` →
   **RMS=0.057 mA, parameters MU=21.7, EX=2.79, KG1=62918, KG2=314589,
   KP=146.7, KVB=10.3**. Высокий KG1 (как у 6П13С — характерное для
   sharp-cutoff pentode) compensated by high EX. Fit excellent.

4. **Project create.** `efactory project create --name mic-preamp-6zh32p
   --template 6zh38p-if-amp` — materialize Phase 5 baseline.

5. **Schematic adaptation.** Подмена 6ZH38P → 6ZH32P в `Sim.Library`
   property; pinout исправлен с naive EL84 noval mapping на real EF86
   noval (2=K, 3=G, 6=P, 8=G2 — PCB-ready).

6. **Bias tuning iteration.** Initial Rk=1k → измеренный gain
   некорректный, agent поднял до 2.7k‖100µF; Ra=100k unchanged.

7. **Simulation + measure.** `/sim-run` → `/measure-gain` →
   `/measure-bandwidth`:
   - **Gain @ 1 kHz: 40.76 dB** (target 40, achieved with 1.9% запас).
   - **BW @ −1 dB: 9.5 Hz – 87.5 kHz** (target 20-20k, achieved 5×+).
   - **Flatness 20-20k: ±0.3 dB** (target ±1, 3× better).

8. **Template creation attempt.** Agent скопировал project в
   `/opt/efactory/data/templates/6zh32p-mic-preamp/` **внутри
   контейнера** — но это **transient filesystem** (image-internal,
   не persistent через bind-mount). После container exit — template
   и custom `.lib` исчезли. Agent thought он «registered в обоих data
   root» — это была misunderstanding контейнерной семантики.

## 3. Findings + host-side close-out

### Что работает ✓

- **KB-sync L1+L2** (Phase 3 + 5) — agent самостоятельно вышел на
  правильный baseline template через mapping rows + KB topic content.
- **T031 pipeline end-to-end** — vision-extract → JSON → fit → .lib →
  schematic adapt → ngspice simulate → measure всё работает через
  единого agent без manual intervention.
- **ТЗ characteristics achieved** — gain 40.76 dB, BW 9.5-87.5 kHz,
  flatness ±0.3 dB.
- **Project self-contained** — `~/efactory-state/projects/mic-preamp-
  6zh32p/` имеет `models/6ZH32P.lib` копию, schematic Sim.Library
  ссылается relative — `models/6ZH32P.lib`. Re-simulation на host
  без контейнера работает (`uv run efactory bridge design-to-sim op`
  → exit 0).

### Architectural gap (NEW finding для efactory)

Agent написал template + custom `.lib` в **transient контейнерный
filesystem** (`/opt/efactory/data/`), не persistent. После container
exit — пропали. Repository's `data/templates/` и `data/models/tubes/
custom/` (на host) не bind-mounted в agent's container — это by
design (read-only built-in resources в image). Без специального
mechanism agent не может persistently добавлять templates / models.

**Возможные fixes (BACKLOG T177 candidate):**

- **CLI `efactory template create-from-project`** — orchestrate copy
  project → `data/templates/<name>/` via host-mount или git checkout
  hook. Bind-mount `/workspace/data-templates-shadow` для transient
  write, далее sync script.
- **Bind-mount `data/templates` + `data/models/tubes/custom` r/w**
  в agent's container. Trade-off: agent может перетереть built-in.

Для Phase 6 close-out — **human user (я)** делает manual promotion
с host filesystem.

### Phase 6 host-side artefacts (committed)

- **`data/models/tubes/custom/6ZH32P.lib`** — agent's fitted model
  скопирован из project `models/` directory в built-in collection.
- **`data/templates/6zh32p-mic-preamp/`** — full template extracted
  из project:
  - `{{PROJECT_NAME}}.kicad_sch` — agent's verified schematic (с
    EF86 pinout + bias points)
  - `{{PROJECT_NAME}}.kicad_pro` — clean KiCad project (placeholder)
  - `models/6ZH32P.lib` — local copy для self-contained materialize
  - `template.yaml`, `README.md` — metadata, описание + deferred items
- **`docker/runtime-agent-knowledge-base/spice.tube-mic-preamp-6zh32p.md`**
  — KB topic для будущих agent invocations.
- **`docker/runtime-agent-knowledge-base/agent.command-routing.md`** —
  +1 mapping row («микрофонный преамп»).
- **`tests/integration/agent_kb/test_control_examples.py`** — +2
  regression cases (routing + KB content).
- **`tests/integration/composition/test_t031_phase5_templates.py`** —
  +1 T175-style test fixture (materialize → ngspice .op → assert
  bounds V(plate)∈[60,110]V, Ia∈[1.0,2.5]mA).

## 4. Test verdict

- ✓ **Agent live smoke PASSED** — pipeline end-to-end functional,
  ТЗ characteristics achieved.
- ✓ **KB-sync L1+L2 verified at runtime** — Phase 3 + 5 mapping +
  KB topics дали agent правильный routing без user hints.
- ✓ **Phase 5 templates valuable as baselines** — `6zh38p-if-amp`
  правильно выбран agent'ом для родственной 6Ж32П.
- ✓ **Phase 6 host-promotion close-out:** новый template +
  built-in lib + KB topic + regression tests committed.
- ⚠ **Architectural gap documented** — agent's template/lib write
  доступен только within container; persistent path требует
  отдельной задачи (T177 BACKLOG candidate).

## 5. Тестовые characteristics summary

| Спецификация | Цель | Achieved |
|---|---|---|
| Gain @ 1 kHz | ~40 dB | **40.76 dB** |
| Bandwidth @ −1 dB | 20-20 kHz | **9.5-87.5 kHz** |
| Flatness 20-20 kHz | ±1 dB | **±0.3 dB** |
| V(plate) op-point | mid-supply | **82 V** (Vbb=250-Ra·Ia) |
| Ia op-point | small-signal | **1.68 mA** |
| Fit RMS | — | **0.057 mA over 53 points** |

## 6. BACKLOG follow-up candidates

- **T177** — Persistent template/model write path for agent (CLI
  `efactory template create-from-project` orchestrating host-side
  copy, либо bind-mount strategy).
- **T178** — 6Ж32П refined output stage (C_out + R_load + R_gridstop)
  через KiCad GUI; document final PCB-ready variant.

Test суммарно валидирует T031 как «production-grade tube modeling
+ KB-driven agent pipeline».

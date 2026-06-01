# Spec: Расширение каталога шаблонов проектов (T027)

**Статус:** Closed (все фазы A..E реализованы и merged 2026-06-02)
**Дата создания:** 2026-06-02
**Дата закрытия:** 2026-06-02 (PRs #102/103/104/106/107 — single-day sprint)
**Связанные документы:**
- `BACKLOG.md` — запись T027 от 2026-05-15 (Фаза 2 roadmap).
- `data/templates/{se-amp,nfb-se-amp,op-amp-inverting,bjt-ce-nfb}/` — уже
  материализованные шаблоны и `template.yaml`-конвенция.
- `scripts/regenerate-templates.py` — bake-pipeline builder → template.
- `src/adapters/inbound/cli/template_materializer.py` — runtime
  материализация шаблона в `<storage_root>/<project>/`.
- `src/adapters/inbound/cli/app.py` — `efactory project create
  --template T --name N` subcommand.
- `docker/runtime-agent-commands/project-create.md` — slash `/project-create`.
- DECISIONS.md — ADR 2026-05-19 (manifest как SSOT), ADR T134 (KB sync
  discipline).

---

## 1. Overview

T027 закрывает оставшуюся часть запроса от 2026-05-15: расширение
каталога project templates с одного (`se-amp`) до пяти типичных audio-
аудио-RЭА топологий — push-pull power amp, ламповый line preamp,
ламповый phono RIAA preamp, и active low-pass filter — плюс
расширение slash-команды `/project-create` template-аргументом и CLI
helper для listing'а доступных шаблонов. Цель — превратить «efactory
project create» из demo-only (SE-amp 6П14П) в полноценный starter
catalog, чтобы agent runtime'а efactory:linux умел подобрать готовый
скелет под user-intent без изобретения топологии с нуля.

## 2. User Stories / сценарии использования

- **Сценарий А (agent runtime в `efactory:linux`).** Vladimir запрашивает
  у agent'а: «сделай мне SE preamp на 6Н2П», agent через KB hit на
  `agent.command-routing` подбирает `/project-create my-preamp tube-line-preamp`,
  материализует проект, и сразу способен запустить `efactory measure gain`
  / `bandwidth` без manual builder-coding.
- **Сценарий B (dev efactory).** Vladimir или Гвидо локально: `uv run
  efactory project create --template tube-pp-amp --name pp-demo` →
  работающий `.kicad_sch` с балансом плеч, OPT, biasing — открывается
  в KiCad Simulator, ngspice сходится, calibration test зелёный.
- **Сценарий C (agent KB discovery).** Agent не помнит конкретное
  название шаблона — зовёт `efactory project list-templates`,
  получает registry (name + одно-строчное description), выбирает
  подходящий.
- **Сценарий D (smoke-acceptance).** Vladimir перед milestone'ом
  прогоняет Level 3 smoke на `efactory:linux` с scenario «agent создаёт
  каждый из 5 шаблонов, выполняет default-measurement, отчитывается
  результатом» — проверяет end-to-end из коробки.

## 3. Functional Requirements

- **ДОЛЖНА** материализовать 3 новых шаблона дополнительно к уже
  существующим (`se-amp`, `nfb-se-amp`, `op-amp-inverting`, `bjt-ce-nfb`):
  - `tube-pp-amp` — Tube push-pull power amp.
  - `tube-line-preamp` — Two-stage all-triode line preamp.
  - `tube-phono-riaa` — Tube phono RIAA preamp.
  - `active-lpf-sallen-key` — Active 2nd-order Sallen-Key low-pass filter.
  - **(Итого 4 новых шаблона — phono добавлен по запросу 2026-06-02.)**
- **ДОЛЖНА** каждая новая фикстура иметь:
  - builder-функцию `_build_<topology>` в
    `tests/integration/adapters/schematic_kicad/test_<topology>_facade.py`
    (по аналогии с T163 BJT CE NFB).
  - bake-hook в `scripts/regenerate-templates.py` → артефакты в
    `data/templates/<topology>/` (5 файлов: `README.md`, `template.yaml`,
    `models/`, `{{PROJECT_NAME}}.kicad_pro`, `{{PROJECT_NAME}}.kicad_sch`).
  - integration snapshot test `tests/integration/test_template_<topology>_snapshot.py`.
  - per-topology calibration test (см. Success Criteria §4).
  - KB sync Уровни 1+2 (mapping table entry в
    `agent.command-routing` + при необходимости свой topic в
    подходящем namespace; deterministic regression case в
    `tests/integration/agent_kb/test_control_examples.py`).
- **ДОЛЖНА** slash-команда `/project-create` принимать
  optional template-аргумент:
  `/project-create <NAME> [TEMPLATE]`, default — `se-amp` (back-compat
  с текущим hard-coded поведением).
- **ДОЛЖНА** появиться CLI-команда `efactory project list-templates`,
  возвращающая registry (name + summary из `template.yaml`).
- **МОЖЕТ** содержать дополнительные measurements в `README.md`
  каждого шаблона как «рекомендованный entry-point» (`efactory measure
  thd …` для PP / SE amps, `efactory measure phase-margin …` для NFB
  и Sallen-Key, и т.п.).
- **НЕ ДОЛЖНА** генерировать готовый PCB layout (`*.kicad_pcb`) —
  только schematic. PCB → отдельная задача (T029+ DRC fixture +
  T106 layout beautifier).
- **НЕ ДОЛЖНА** автоматизировать запуск measurements при materialize
  (что-то типа «pre-warm cache»). Шаблон = inert skeleton; первый
  measurement run — на usage-side.
- **НЕ ДОЛЖНА** требовать manual KiCad GUI interaction для acceptance —
  всё валидируется headless через `kicad-cli` + `ngspice` (как у
  текущих фикстур).

## 4. Success Criteria

Все 4 новых шаблона:
- `efactory project create --template <T> --name <N>` создаёт каталог
  `<storage_root>/<N>/` со всеми 5 артефактами; `efactory project
  show --name <N>` возвращает manifest без ошибок.
- `kicad-cli sch erc` на `<N>.kicad_sch` — 0 errors (warnings
  допустимы, но не больше 5 на проект, и каждый объяснён в `README.md`).
- ngspice OP analysis сходится; DC operating point — в expected
  active region для всех активных элементов (Vlamp ≠ 0, не saturation,
  не cutoff).
- Per-topology strict calibration test (см. ниже):

  | Шаблон                  | Method                              | Target                                        | Tolerance |
  |-------------------------|-------------------------------------|-----------------------------------------------|-----------|
  | `tube-pp-amp`           | `measure_phase_margin` @ canonical break (sec_a, C_fb) если есть NFB, иначе `measure_gain` mid-band | PM 45-90° или Av_mid ±15% к hand-calc | ±3° / ±15% |
  | `tube-line-preamp`      | `measure_gain` mid-band 1 kHz       | Av ≈ μ_eff(6Н2П first stage) ≈ 60-70 (≈ 36-37 dB) | ±15% |
  | `tube-phono-riaa`       | `measure_bandwidth` AC-sweep 20Hz-20kHz vs RIAA inverse curve | RIAA compliance ±1 dB в 20Hz-20kHz | ±1 dB |
  | `active-lpf-sallen-key` | `measure_bandwidth` AC-sweep around f_c | f_c ±10% к 1/(2π√(R1·R2·C1·C2)); Q ≈ 0.707 ±10% | ±10% |

- KB sync: `efactory:linux` agent через `FileSystemKbStore.search` на
  user query типа «create tube push-pull amp» возвращает hit
  `agent.command-routing` с command `/project-create <NAME> tube-pp-amp`.
- Pre-push 5/5 ✓ (ruff check, ruff format --check, mypy, pytest with
  coverage ≥ 80%, regenerate-templates clean diff).

## 5. Key Entities

- **`tube-pp-amp` topology:** концертино phase splitter на одной
  половине 6Н2П (high-µ для max swing/gain), пара 6П14П в push-pull
  выходе, OPT (`data/models/transformers/generic/`, 8 kΩ p-p : 8 Ω
  secondary), DC coupling между splitter cathode/plate и выходными
  grids через blocking capacitors, global cathode bias (shared cathode
  resistor + bypass) для каждой выходной лампы. **Нет global NFB**
  (purely open-loop для Phase A; NFB-вариант — follow-up, как
  `nfb-se-amp` относится к `se-amp`).
- **`tube-line-preamp` topology:** двухкаскадный all-triode на 6Н2П
  (обе половины двойного триода): 1-й каскад — common-cathode
  voltage amplifier (anode load Ra, cathode bias Rk + Ck bypass);
  2-й каскад — cathode follower (для низкого output Z, способного
  драйвить кабель / следующий power amp). Capacitor-coupled выход.
- **`tube-phono-riaa` topology:** двух- или трёх-каскадный preamp на
  12AX7 (`data/models/tubes/koren/12AX7.lib` — Koren parametrization
  предпочтительна, она же используется во всех Koren-based фикстурах)
  с **passive RIAA EQ network** между 1-м и 2-м каскадом: классическая
  R-C-R-C topology с standard time constants τ1=3180 µs (50 Hz
  pole), τ2=318 µs (500 Hz zero), τ3=75 µs (2122 Hz pole). Целевой
  gain @ 1 kHz ≈ 40 dB (для MM cartridge 5 mV → 500 mV line level).
- **`active-lpf-sallen-key` topology:** classic Sallen-Key voltage-
  controlled voltage-source (VCVS) с unity-gain buffer (op-amp
  TL072 из `data/models/opamps/generic/`), Butterworth Q=0.707 через
  equal R/equal C choice. Default cutoff f_c = 1 kHz (audio mid-band).
- **`template.yaml` schema** — без изменений (name, description, summary).
- **`registry of available templates`** — пока не вынесен в data-driven
  source-of-truth; для T027 либо derive из listing `data/templates/*/template.yaml`
  (data-driven, рекомендую), либо hard-code в Python (simpler но
  дрейф-prone — отвергаем).

## 6. Assumptions & Constraints

- Все existing SPICE-модели для нужных компонентов уже в репо:
  - `data/models/tubes/custom/6N2P.lib`, `6P14P.lib`, `6N1P.lib` ✓
  - `data/models/tubes/koren/12AX7.lib` ✓
  - `data/models/transformers/generic/` ✓ (generic OPT)
  - `data/models/opamps/generic/` ✓ (TL072 или similar)
- Builder-flow унаследован от T163 (`_build_<topology>` в test
  fixture file, bake-hook регистрируется в
  `scripts/regenerate-templates.py`, materialized template коммитится
  в `data/templates/`).
- KiCad schematic API (T100) поддерживает все нужные примитивы:
  triode / tetrode placement, transformer 4-pin symbol с polarity,
  multi-stage component graphs, capacitor / resistor / op-amp
  placement (подтверждено T153 + T163).
- 12AX7 ≡ ECC83 ≡ 6Н2П-EH («двойник» советского аналога) — но
  Koren-parametrized 12AX7 имеет более точную модель, чем custom
  6N2P (verified только OP point). Для phono выбираем 12AX7 ради
  точности AC sweep к RIAA compliance.
- WIP-limit BOARD.md → Doing = 1-2 задачи. T027 — единственная Doing
  на момент start; Phase A..E последовательны, не parallel.

## 7. Out of Scope

- **Speaker crossover networks** (2-way / 3-way LC) — требует discrete
  inductors, которых нет в библиотеке. Парковать в BACKLOG отдельной
  T-задачей.
- **MC cartridge head amplifier / step-up transformer (SUT)** для
  phono — `tube-phono-riaa` фокусируется только на MM input (~5 mV
  level). MC — отдельная фича.
- **Tube rectifier power supply (5U4G / 5Ц3С / etc.)** — все шаблоны
  предполагают ideal V_HT и V_heater (как и текущие фикстуры).
  Power-supply шаблоны (с C-L-C filter, voltage doubler, и т.п.) —
  отдельная T-задача.
- **`pcb_layout` фаза** для любого шаблона — только schematic. PCB
  через ERC/DRC (T029) и beautifier (T106).
- **NFB вариант PP-amp** — Phase A делает open-loop PP, NFB-вариант
  оставляем в BACKLOG как `T<NNN>-pp-amp-nfb` (по аналогии с
  `se-amp` → `nfb-se-amp`).
- **Active filters высших порядков** (4th-order cascaded, Bessel,
  Chebyshev) — Phase D даёт только Sallen-Key 2nd-order Butterworth.
  Расширение — отдельная задача.
- **Multi-board / multi-sheet schematics** — каждый шаблон fits в
  один root schematic sheet.
- **Manual KiCad GUI verification как acceptance gate** — verification
  только headless; Vladimir опционально открывает в GUI «для глаза»
  перед merge, но это не блокер.

---

## Plan (per-phase breakdown)

- **Phase A — `tube-pp-amp`.**
  - Spec finalize (Round 2 clarify ниже), copy `nfb-se-amp` builder
    как baseline, добавить concertina splitter + push-pull output
    pair + OPT.
  - Calibration test: open-loop voltage gain mid-band 1 kHz через
    `measure_gain`, target ≈ μ_6Н2П · g_m_6П14П · R_load (analytical
    hand-calc в `README.md`).
  - KB topic: `spice.tube-push-pull.md` (новый) — описание concertina
    + biasing pitfalls (DC balance плеч, idle current matching).
    KB `agent.command-routing` entry.
  - Snapshot test, bake-hook, materialized template.
  - **`/ultrareview` рекомендуется** (concertina/OPT math нетривиальны).

- **Phase B — `tube-line-preamp`.**
  - Двухкаскадная all-triode 6Н2П (CC + CF) — простейшая extension
    SE-amp пайплайна на double-triode.
  - Calibration test: mid-band gain @ 1 kHz через `measure_gain`,
    target Av ≈ μ·Ra/(Ra+ra) первого каскада × 1 (CF unity).
  - KB topic: `spice.tube-line-preamp.md` (новый). KB mapping entry.
  - **Self-review достаточно** (топология простая, два кадра).

- **Phase C — `tube-phono-riaa`.**
  - Двухкаскадный 12AX7 + passive RIAA RC network между каскадами.
  - Calibration test: AC sweep 20Hz-20kHz, сравнение с inverse RIAA
    curve (table standardize в `data/calibration/riaa-target-curve.csv`?
    или inline в test). Tolerance ±1 dB в audio band.
  - KB topic: `spice.tube-phono-riaa.md` (новый) — RIAA topology
    pitfalls (loading effects 2-го каскада на EQ network, capacitor
    tolerance impact).
  - **`/ultrareview` рекомендуется** (RIAA EQ network math и
    compliance — high error-surface; Vladimir эксперт по аудио,
    second opinion полезен).

- **Phase D — `active-lpf-sallen-key`.**
  - Op-amp Sallen-Key VCVS, Butterworth Q=0.707, f_c=1 kHz default.
  - Calibration test: `measure_bandwidth` AC sweep, измерение -3 dB
    point, Q estimate из peaking around f_c.
  - KB topic: `spice.active-filter-sallen-key.md` (новый). KB
    mapping entry.
  - **Self-review достаточно.**

- **Phase E — `/project-create` extension + CLI list-templates + closure.**
  - `/project-create.md` slash command принимает optional template.
  - `efactory project list-templates` CLI subcommand — data-driven
    из `data/templates/*/template.yaml`.
  - BACKLOG entry T027 acceptance обновляется под реальность
    («`efactory project create --template T --name N` ...» вместо
    «`/project create --template T NAME`»).
  - Final closing-правка BOARD: Doing → Done.

**Каждая Phase = один PR (укрупнённый: builder + calibration + KB +
snapshot + bake), squash-merged.** Прецедент: T153 (4 фазы), T100
(multiple phases). KB sync Level 3 smoke — bundled в Phase E или
отдельной session после merge всех 5 phases (как T164+T163 bundle
сделан в T165 предшественнике).

---

## Clarify (Round 2 — заполнено Гвидо, ждёт одобрения Vladimir)

Ниже — собственные открытые вопросы Гвидо по своим же ответам Round 1.
Каждый помечен **proposed answer** — это recommendation; Vladimir
может одобрить / коррекcтровать / отвергнуть.

### Open questions

**Q1 (Phase A, tube-pp-amp). OPT — какой именно из generic catalog?**
- Proposed answer: OPT 8 kΩ p-p : 8 Ω (primary плечо-к-плечу 8k,
  single secondary 8 Ω для 8-Ом dynamic), idealized — без leakage
  inductance / DC resistance для первого open-loop варианта (это
  будет уже T132 / future-NFB). Если в `data/models/transformers/
  generic/` пока есть только SE OPT (single primary 5 kΩ : 8 Ω
  unsplit) — Phase A добавляет PP variant `OPT_8kpp_8s.lib`.
- **Vladimir, одобрить?** Альтернативы: (a) 6.6 kΩ p-p : 4/8/16 Ω
  multi-tap (точнее к коммерческим 6П14П PP); (b) 10 kΩ p-p : 8 Ω
  (если ориентируемся на higher-Z 6П14П triode-mode PP).

**Q2 (Phase A, tube-pp-amp). Bias point — fixed bias или auto-bias?**
- Proposed answer: **Auto-bias** (cathode resistor + bypass cap)
  для каждой выходной лампы, по аналогии с `se-amp`. Проще, не
  требует negative HT supply, типичный choice для DIY tube PP.
  Target I_a quiescent ≈ 30-35 mA на лампу (близко к 6П14П UL/PP
  maximum dissipation 12 W → 35 mA @ 350 V).
- **Vladimir, одобрить?** Fixed bias дал бы немного выше power, но
  требует доп.PSU + adjust pot, что overengineering для template.

**Q3 (Phase A, tube-pp-amp). Splitter — concertina vs long-tail-pair vs
paraphase?**
- Proposed answer: **Concertina (split-load).** Простейший (одна
  лампа, два равных резистора Ra/Rk на одной 6Н2П triode), perfect
  AC balance, минимальный component count. Минус — limited output
  swing (~0.5×μ), но для драйва 6П14П в PP UL-mode хватит.
  Long-tail-pair — выше swing, но 2 lampы (или вторая половина 6Н2П),
  bias balance pot, проще в калибровке но больше components.
  Paraphase — устаревший вариант, не recommend.
- **Vladimir, одобрить concertina?** Если хочется long-tail-pair —
  это +1 stage и +2 components, scope Phase A немного расширяется.

**Q4 (Phase B, tube-line-preamp). Output coupling capacitor target value?**
- Proposed answer: **0.47 µF** (стандарт для line-level применения,
  даёт f_c LF ≈ 3.4 Hz при следующем stage Rin=100 kΩ, что вне
  audio band) + 100 kΩ grid leak на следующий stage (assumed load
  для AC sweep).
- **Vladimir, одобрить?** Альтернатива: 1.0 µF (subsonic margin
  ещё больше, но компонент крупнее).

**Q5 (Phase B, tube-line-preamp). Target gain — фиксированное число?**
- Proposed answer: **Av ≈ 30-40 (~30 dB)** mid-band 1 kHz, ±15%.
  Это natural gain CC stage на 6Н2П (μ=100, Ra=100k, Rk=2.2k+10µF)
  без NFB. Не фиксируем точное число — фиксируем tolerance к
  hand-calc analytic в README.
- **Vladimir, одобрить?**

**Q6 (Phase C, tube-phono-riaa). Лампа — 12AX7 (Koren) или 6Н2П
(custom)?**
- Proposed answer: **12AX7 (Koren parametrization).** Причины:
  (a) Koren модель точнее на AC sweep (custom 6N2P verified только
  OP point); (b) общепризнанная phono-преамп tube, обширная
  литература (Morgan Jones, Allen Wright); (c) RIAA compliance
  ±1 dB — high error-surface, нужна максимально точная model.
- **Vladimir, одобрить?** 6Н2П — советский аналог, но мы уже
  используем его для line preamp Phase B. Разные лампы для разных
  topology — OK?

**Q7 (Phase C, tube-phono-riaa). Passive vs active (feedback-type) RIAA EQ?**
- Proposed answer: **Passive RIAA** между 1-м и 2-м каскадом.
  Причины: (a) проще topology (R-C-R-C inter-stage, без NFB loop);
  (b) более forgiving к component tolerance — passive RIAA reacts
  к R/C drift как ±0.1 dB / 1% tolerance; (c) classic «pure-tube»
  approach. Active RIAA на feedback loop требует tube-based loop
  gain analysis (близко к T153 phase-margin pipeline), что
  расширяет scope Phase C.
- **Vladimir, одобрить passive?**

**Q8 (Phase C, tube-phono-riaa). RIAA compliance target — ±1 dB
или строже?**
- Proposed answer: **±1 dB в 20Hz-20kHz** (стандарт consumer-grade
  phono). High-end ±0.5 dB — нужны 1% tolerance components и
  более тонкая calibration; ±1 dB достаточно для template-level
  starter. Vladimir может tighten при materialize конкретного проекта.
- **Vladimir, одобрить ±1 dB?**

**Q9 (Phase D, active-lpf-sallen-key). Op-amp — TL072 или подругой?**
- Proposed answer: **TL072** из `data/models/opamps/generic/`
  (если есть) — стандарт low-cost JFET-input op-amp для audio
  Sallen-Key. Если в generic catalog пока только generic ideal
  op-amp — Phase D добавляет TL072 model first (одна `.lib`
  attribution Texas Instruments).
- **Vladimir, одобрить TL072?** Альтернатива: LM358 (BJT-input,
  worse audio noise но widely available); NE5532 (premium audio).

**Q10 (Phase D, active-lpf-sallen-key). Default cutoff f_c?**
- Proposed answer: **f_c = 1 kHz** (audio mid-band, neutral
  starter — user легко перенастроит). R=10 kΩ, C=15.9 nF
  (equal-R / equal-C Butterworth Q=0.707 → f_c = 1/(2π·R·C)).
- **Vladimir, одобрить f_c=1 kHz?** Альтернативы: 10 kHz
  (anti-aliasing для 44.1 kHz ADC), 200 Hz (subwoofer LP).

**Q11 (Phase E, slash command). Какое именно поведение default?**
- Proposed answer: `/project-create <NAME>` без template-аргумента
  → fallback на `se-amp` (back-compat). `/project-create <NAME>
  <TEMPLATE>` — material с указанным шаблоном. Документировать
  оба usage в `project-create.md` docstring.
- **Vladimir, одобрить?** Альтернатива: убрать default, требовать
  явный template — breaks back-compat для существующих agent
  sessions, не рекомендую.

**Q12 (Phase E, CLI list-templates). Output формат?**
- Proposed answer: **Human-readable table** (column name, column
  summary) на stdout, по аналогии с `efactory project list`.
  `--json` flag для machine-readable (по аналогии с другими CLI
  subcommands). Source-of-truth — directory listing
  `data/templates/*/template.yaml` (data-driven).
- **Vladimir, одобрить?**

**Q13 (KB sync). Уровень 3 smoke — bundle в Phase E PR или
отдельной session?**
- Proposed answer: **Отдельной session после merge всех 5 phases**,
  по образцу T164+T163 bundle → T165-смежная smoke session.
  В Phase E коммитится Level 1+2 (mapping + deterministic test),
  Level 3 (~30 мин real-agent на 5 scenarios + ngspice convergence
  на каждом) — отдельный TODO + session после `git checkout main &&
  git pull`.
- **Vladimir, одобрить?** Альтернатива: bundle в Phase E (тогда
  Phase E ~3-4 часа вместо ~1 часа).

### Resolved

**Все Q1-Q13 одобрены Vladimir 2026-06-02.** Уточнения по двум
вопросам обнаружены при verification моделей:

| Q   | Outcome                                                                                                                                                                      |
|-----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Q1  | **Уточнение:** `data/models/transformers/generic/OPT_PP_6K6_8.lib` уже существует (6.6 kΩ p-p : 8 Ω, Mullard 5-10 / DIY 6П14П PP стандарт). Phase A использует его, новый OPT не добавляется. Calibration hand-calc — на основе 6.6k p-p. |
| Q2  | Auto-bias (cathode R + bypass C) per выходную лампу; target I_a quiescent ≈ 30-35 mA. R_k подбирается под U_g_bias ≈ -7.3 V для 6П14П @ V_a=300 V.                            |
| Q3  | Concertina split-load splitter на одной триоде 6Н2П. Ra=Rk≈47 kΩ, gain per phase ≈ 27 (μ=100, ra=80k). Достаточно для драйва 6П14П от 50 mV input.                            |
| Q4  | Output coupling 0.47 µF + 100 kΩ assumed load (follow-stage grid leak).                                                                                                       |
| Q5  | Av mid-band ≈ 30-40 (~30 dB) ±15% к hand-calc analytical estimate в README.                                                                                                  |
| Q6  | 12AX7 (Koren parametrization) для phono. 6Н2П остаётся для line preamp Phase B (разные tubes для разных topologies — OK). **Empirical correction (Phase C, 2026-06-02):** rationale «Koren модель точнее на AC sweep» was based on incorrect assumption — `12AX7.lib` Koren и `6N2P.lib` custom используют **identical Koren parameters** (`MU=100 EX=1.4 KG1=1060 KP=600 KVB=300`). Single material difference: `12AX7.lib` had `PWRS()` (HSPICE syntax, broken на ngspice 44), `6N2P.lib` — `sgn(x)*pwr(abs(x),y)` (ngspice-compatible). Phase C patched **all 15 Koren models** (`12AX7`, `12AU7`, ..., `KT88`) to ngspice-compatible syntax. Choice 12AX7 over 6N2P retained на основе textbook convention (Morgan Jones / Allen Wright phono designs reference 12AX7/ECC83 explicitly). |
| Q7  | Passive RIAA inter-stage R-C-R-C (3180 / 318 / 75 µs стандартные time constants).                                                                                            |
| Q8  | RIAA compliance ±1 dB в 20Hz-20kHz (consumer-grade phono target).                                                                                                             |
| Q9  | **Подтверждение:** TL072 отсутствует (`data/models/opamps/generic/` содержит только GENERIC_OPAMP / GENERIC_OPAMP_2POLE). Phase D **bootstrap'ит** TL072 model first (одна .lib attribution Texas Instruments) — внутренний sub-step Phase D, не отдельная фаза. |
| Q10 | f_c = 1 kHz, R=10 kΩ, C=15.9 nF default. Equal-R / equal-C choice потребует доп. внимания к topology Sallen-Key (см. Analyze 🟡 W2).                                          |
| Q11 | `/project-create <NAME> [TEMPLATE]`, default TEMPLATE=`se-amp` (back-compat).                                                                                                |
| Q12 | Human-readable table (column name + summary из template.yaml) + `--json` flag; source-of-truth — directory listing `data/templates/*/template.yaml` (data-driven).            |
| Q13 | L3 smoke — отдельная session после merge всех 5 phases (TODO в `mcp__tools__add_todo` после Phase E merge). Phase E коммитит только L1+L2.                                  |

---

## Analyze (выполнен Гвидо 2026-06-02)

### 🔴 Critical

(нет)

### 🟡 Warning

- **W1 (Phase D, Sallen-Key Q-factor).** Classic equal-R/equal-C
  Sallen-Key с **unity-gain VCVS** даёт Q = 0.5 (overdamped),
  **не** Butterworth Q=0.707. Для Q=0.707 нужен **либо** unequal
  components (e.g., C1=2C, C2=C/2 с равными R), **либо**
  non-unity gain (K=1.586 для equal-R/equal-C Butterworth). Phase D
  должна **явно** выбрать один из двух подходов в spec'е builder'а
  (рекомендую — equal-R, C1=2·C2 для clarity: f_c = 1/(2π·R·√(C1·C2)),
  Q=0.5·√(C1/C2)=0.707 при C1=2·C2). README документирует выбор.
- **W2 (Phase A, OPT non-idealities).** `OPT_PP_6K6_8.lib` —
  generic idealized; реальный OPT имеет leakage inductance
  (HF roll-off), magnetizing inductance (LF roll-off), DC
  resistance (insertion loss). Phase A calibration target Av_mid
  ±15% подразумевает **mid-band only** (1 kHz). Bandwidth target
  (-3 dB points) — `МОЖЕТ` в README, но **НЕ** в strict
  calibration test (зависит от OPT model fidelity). T132
  (interleaved leakage) — отдельная задача, не Phase A scope.
- **W3 (Phase C, RIAA compliance tolerance).** ±1 dB target
  достижим при ideal-values component selection. Реальные
  компоненты (resistor ±5%, ceramic cap ±10%) дадут ±0.5-1 dB
  drift сами по себе. Calibration test использует
  **ideal nominal values** в SPICE netlist — НЕ tolerance-aware.
  Component sensitivity analysis — отдельная задача, не Phase C
  scope.

### 🟢 Note

- **N1.** KB topic naming convention: все новые topics — в
  `spice.*` namespace (`spice.tube-push-pull.md`,
  `spice.tube-line-preamp.md`, `spice.tube-phono-riaa.md`,
  `spice.active-filter-sallen-key.md`). Согласовано с existing
  conventions (`spice.feedback-break-point.md`, etc.).
- **N2.** Calibration test pattern: builders без NFB используют
  `test_measure_gain_calibration_<topology>.py` / `test_measure_
  bandwidth_calibration_<topology>.py` (Phase B/C/D). Builder с
  potential NFB (Phase A — open-loop, NFB-вариант отложен) —
  через `measure_gain`. Согласовано с T163 pattern.
- **N3.** `regenerate-templates.py` bake-hook конвенция:
  `_<topology>_BUILDER_PATH` const + `_load_<topology>_builder()`
  function + registration в main loop. Согласовано с existing
  `_SE_AMP_BUILDER_PATH` / `_NFB_SE_AMP_BUILDER_PATH` / etc.
- **N4.** Slash-команда `/project-create` принимает теперь два
  аргумента (NAME + optional TEMPLATE). Bash interpolation в
  `project-create.md` использует `$1` (NAME) и `${2:-se-amp}`
  (TEMPLATE с default). Standard bash idiom, не breaking change.
- **N5.** Phase E может также **deprecate** generic
  `/project-create-se` если он существует отдельно (не нашёл при
  разведке — significantly не существует). Не делать, если нет.

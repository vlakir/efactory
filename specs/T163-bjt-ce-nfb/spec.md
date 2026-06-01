# Spec: T163 BJT CE NFB fixture для full 4-method matrix

**Статус:** Analyzed
**Дата создания:** 2026-06-01
**Связанные документы:**
- BACKLOG.md → T163 entry
- DECISIONS.md → ADR-T153f (op-amp break convention),
  ADR-T153g (per-topology matrix; **этой задачей расширяется**),
  ADR-T153h (AC sanitizer)
- specs/T153-phase-margin/spec.md — предыстория multi-phase
- data/templates/op-amp-inverting/, data/templates/nfb-se-amp/ —
  structural reference для new fixture

---

## 1. Overview

efactory phase-margin pipeline поддерживает 4 метода measurement
(Middlebrook V, Middlebrook I, Tian, Rosenstark). После T153
calibration (C.1 op-amp inverting → 2/4 strict, C.3 NFB SE tube →
1/4 strict) per-topology matrix в ADR-T153g остаётся неполным:
BJT CE row помечен `?`. **T163 закрывает gap** — заводит fixture
`bjt-ce-nfb` (single-stage common-emitter с shunt-shunt feedback
R_F collector→base) и эмпирически валидирует 4-method matrix.

BJT CE — natural candidate для full 4-method coverage: base = high-Z
current input (Middlebrook I applicable), R_F passive interconnect
между active stages (Rosenstark two-port valid), bidirectional BJT
(Tian universal), V single trivially корректен.

## 2. Use cases

- **Test author / contributor.** «У меня есть BJT CE NFB circuit,
  на каком методе мерить phase margin?» → ADR-T153g matrix даёт
  per-topology рекомендацию + canonical break point из KB.
- **efactory developer.** «Phase-margin tool работает на op-amp и
  tube, но я хочу убедиться, что core methods не привязаны к
  конкретной active-device physics» → BJT calibration выступает
  третьей independent validation на отличной от op-amp/tube topology.
- **Spec-research user.** «Мне нужен empirical pattern сравнения 4
  методов на BJT NFB» → fixture + calibration test + ADR-T153g.

## 3. Functional Requirements

- **ДОЛЖНА** заводить новую fixture `data/templates/bjt-ce-nfb/`
  по pattern `nfb-se-amp` / `op-amp-inverting`: builder в
  `tests/integration/adapters/schematic_kicad/test_bjt_ce_nfb_facade.py`,
  bake hook в `scripts/regenerate-templates.py`, snapshot test,
  `{{PROJECT_NAME}}.kicad_sch` + `.kicad_pro` + `models/` + `template.yaml`
  + `README.md`.
- **ДОЛЖНА** добавить SPICE-model `data/models/bjt/onsemi/Q2N3904.lib`
  (новая категория `bjt/`, vendor subdir `onsemi/` по аналогии с
  `tubes/koren/`).
- **ДОЛЖНА** дать рабочий DC operating point (sanity check в
  builder/integration test) — V_CE_q ∈ [4 V, 8 V], I_C_q ∈ [0.5, 3] mA.
  Это гарантирует, что BJT работает в active region при canonical
  bias values.
- **ДОЛЖНА** добавить calibration test
  `tests/integration/application/measure_phase_margin/test_measure_phase_margin_calibration_bjt_ce.py`
  с 4 strict parametrized cases (V, I, Tian, Rosenstark) на canonical
  break point. Acceptance criteria определяются Q5 (см. §4).
- **ДОЛЖНА** обновить `DECISIONS.md` ADR-T153g — BJT CE row в
  per-topology matrix с empirical results + reasoning для degenerate
  cases (если найдены).
- **ДОЛЖНА** обновить KB topic
  `docker/runtime-agent-knowledge-base/topics/spice.feedback-break-point.md`:
  раздел «BJT CE shunt-shunt» с canonical break + per-method matrix
  + workflow example. KB Level 2 regression case в
  `tests/integration/agent_kb/test_control_examples.py`.
- **МОЖЕТ** включать Bode-relation cross-check (A(jω)/(1+T(jω))
  reconstruction) как secondary validation method — если convergence
  с Middlebrook V даёт чистую ground truth, это упрощает per-method
  comparison.
- **НЕ ДОЛЖНА** trogarь auto-detect heuristic (закрыто T164),
  AC sanitizer (закрыто T153h), facade.add_bjt (уже есть).
- **НЕ ДОЛЖНА** заводить two-stage CE-CE series-shunt fixture —
  отдельная задача потом, если потребуется validate series-shunt
  topology независимо.

## 4. Success Criteria

- ✅ Fixture `bjt-ce-nfb` materializeable через template manager;
  builder snapshot test зелёный; DC op-point в active region
  (criteria выше).
- ✅ 4-method calibration test проходит на canonical break point
  с следующими критериями:
  - **Primary**: Middlebrook V single-injection @ canonical break
    даёт PM ∈ ground-truth ±2°. Это becomes ground truth для остальных.
  - **Cross-validation желательна**: ≥1 из {I, Tian, Rosenstark}
    сходится к V's PM ±3° на canonical break. **Желательна, не
    обязательна** — если все три degenerate (как на tube C.3),
    task всё равно passing при условии полного documenting.
  - **Documented matrix обязателен независимо от outcome**: ADR-T153g
    BJT CE row содержит результат каждого method'а с physical
    reasoning для degenerate cases (например, «Rosenstark degenerate,
    потому что collector node не satisfies OC/SC two-port assumption
    из-за load coupling»). Это «honest claim» acceptance.
  - **Strong claim как stretch goal**: если все 4 strict сходятся
    (✓✓✓✓) — recorded в ADR как BJT CE full convergence; завершает
    matrix optimistic outcome. Если не сойдётся — все равно closure.
- ✅ ADR-T153g matrix обновлён с BJT row. Pattern записи
  совпадает с tube SE / op-amp inverting rows.
- ✅ KB topic + regression case.
- ✅ Pre-push 5/5 (ruff check, ruff format --check, mypy, pytest
  с coverage ≥80%, KB control regression case в pytest наборе).

## 5. Key Entities

- **Fixture `bjt-ce-nfb`** (Q-point validated в Phase A — см. ниже):
  - Q1: NPN 2N3904 (CE configuration).
  - R_B1: 100 kΩ (top divider, V_CC → base).
  - R_B2: 10 kΩ (bottom divider, base → GND).
  - R_C: 4.7 kΩ (collector load to V_CC).
  - R_E: 470 Ω + C_E bypass 47 µF.
  - R_F: 47 kΩ + C_F 1 µF (shunt-shunt AC feedback collector→base,
    DC-blocked — analog к nfb-se-amp `C_fb_block` pattern).
  - C_in: 1 µF, C_out: 10 µF (input/output AC coupling).
  - V_in: VSIN 1 mV ampl @ 1 kHz через R_S=50 Ω.
  - R_L: 10 kΩ (output load).
  - V_CC: 12 V.
  - **Q-point (analytical)**: V_B≈1.03V, V_E≈0.38V, I_C≈0.8-1.0 mA,
    V_C≈8.2V, V_CE≈7.8V → active region center.

  **Rationale для divider bias + C_F (отклонение от первоначального
  draft).** Phase A DC analysis показал: single R_B=100k от V_CC
  feeding base + R_F=47k параллельной feedback path → I_C driven
  to 5-10 mA → V_CE_sat. Self-bias via R_F alone тоже даёт saturation
  потому что β·R_C/R_F ≈ 15 >> 1 (high loop gain via DC feedback).
  **Standard fix** (Sedra-Smith Ch. 8 biasing) — voltage divider
  на base + AC-only feedback через DC-block C_F. Эта topology
  matches efactory's existing nfb-se-amp pattern (where C_fb_block
  10µ separates DC bias from feedback AC path).
- **SPICE model**: 2N3904 Gummel-Poon parameters (ON Semi PSpice
  public), `data/models/bjt/onsemi/Q2N3904.lib`.
- **Canonical break point** (hypothesis с fallback, revised после
  Q-point analysis):
  - **Primary (для V single)**: edge `(vout_node, C_F)` — analog к
    tube NFB `(sec_a, C_fb)` convention. Driver-Z (collector r_o ‖
    R_C) ≈ 4.5 kΩ; load-Z (R_F + r_π) ≈ 50 kΩ → ratio 11× —
    подходит для Middlebrook V single (low-Z driver).
  - **Primary (для I single)**: edge `(base_node, R_F)` — current-mode
    break на high-Z base input. Driver-Z (R_F + r_o reflected) high;
    load-Z (r_π) ~2.6 kΩ → подходит для Middlebrook I current-mode.
  - **Tian/Rosenstark**: оба candidate'а пробуются; passive R_F
    interconnect (или C_F edge) — natural two-port break.
  - **Phase B протестирует оба canonical break candidates** на каждом
    из 4 методов; canonical для ADR/KB recommendation — та edge,
    где ≥V strict сходится с лучшим cross-validation. Если обе
    degenerate на V single — recanvased spec (analyse-fail), задача
    останавливается на review.
- **Per-topology matrix row** (ADR-T153g): BJT CE shunt-shunt
  single-stage @ `(base, R_F)` → V/I/Tian/Rosenstark с empirical
  result для каждого.

## 6. Assumptions & Constraints

- Single-stage CE shunt-shunt feedback. Two-stage CE-CE series-shunt
  (Sedra-Smith Ch.10 voltage-voltage example) — out of scope.
- Linear small-signal analysis: V_in = 1 mV AC, операт. точка
  гарантирует linear region BJT. Никакого THD calibration (T131
  scope).
- 2N3904 model — ON Semi PSpice public (приемлемая лицензия для repo
  по аналогии с прочими `.lib` файлами уже лежащими в `data/models/`).
  Если parameters блокируются licensing — fallback на generic NPN
  (textbook Gummel-Poon с typical values).
- Phase-margin pipeline use case + CLI + KB infrastructure уже есть
  (T153). T163 — только fixture + calibration.
- Pre-push gate 5/5 без обходных манёвров (`# noqa` / `# type: ignore` /
  расширения `ignore` — только через явное обсуждение).

## 7. Out of Scope

- **Two-stage CE-CE series-shunt fixture**. Отдельная задача (если
  потребуется validate series-shunt independent topology).
- **MOSFET CE / FET-based NFB fixture**. Per-topology matrix может
  расшириться FET row отдельной задачей; T163 = только BJT.
- **T164 Level 3 smoke** (8 scenarios bundle с T163) — отдельный
  PR после T163 merge (TODO 0ea5f0ef уже зарегистрирован).
- **Расширение auto-detect heuristic** под BJT NFB. Закрыто T164.
  Если на BJT auto-detect не выберет canonical break — passed user
  explicitly (Vladimir сам подобрал break в test), без расширения
  heuristic.
- **Расширение AC sanitizer**. Закрыто T153h.
- **THD calibration** для BJT. Scope T131.
- **Bode-relation как самостоятельный method**. Может быть использован
  как secondary cross-check внутри Phase B, но не добавляется как
  5-й method в pipeline.

---

## Clarify

### Resolved (с ответами)

**Q1 (topology). Решено: single-stage CE shunt-shunt.**
- Reason: BACKLOG явно описывает «BJT common-emitter с emitter
  resistor + R_fb collector→base», что есть shunt-shunt single-stage.
- Reason: минимальный fixture (1 BJT + 5 пассивов + 3 caps) →
  быстрее calibration cycle, меньше debugging variables.
- Reason: single-stage shunt-shunt всё равно покрывает три критерия
  из BACKLOG для 4-method matrix (current-mode break на base, passive
  interconnect R_F, bidirectional active).
- Two-stage CE-CE series-shunt — отдельная задача, если потребуется
  validate series-shunt independent topology.

**Q2 (model + storage). Решено: 2N3904 / ON Semi PSpice / новая
категория `data/models/bjt/onsemi/`.**
- Reason: 2N3904 — де-факто стандарт textbook'ов (Sedra-Smith Ch.5,
  Razavi Ch.4), широко публикованные Gummel-Poon parameters.
- Reason: ON Semi публикует PSpice model files (приемлемая лицензия
  для встраивания в open-source проекты, как `.lib` файлы уже лежащие
  в `data/models/tubes/koren/`).
- Reason: новая категория `bjt/` по аналогии с `tubes/`, `diodes/`,
  `opamps/` — категоризация по device class. Vendor subdir `onsemi/`
  по аналогии с `tubes/koren/` (author/vendor naming).

**Q3 (component values). Revised после Q-point sanity analysis в
Phase A**: V_CC=12V, **R_B1=100k + R_B2=10k voltage divider** (не
single R_B), R_C=4.7k, R_E=470Ω + C_E=47µF, **R_F=47k + C_F=1µF
DC-block** (не bare R_F), C_in=1µF, C_out=10µF, R_S=50Ω, R_L=10kΩ.
Q-point: V_B≈1.03V, V_E≈0.38V, I_C≈1mA, V_CE≈7.8V (active).
- Reason: textbook-typical values для 1-2 mA Q-point на 2N3904.
- Reason: C_E bypass → high mid-band gain (g_m·R_C ≈ 100-400×) →
  чистый |T| >> 1 на mid-band → cleaner loop gain measurement.
- Reason: AC coupling C_in / C_out → frequency response с LF
  rolloff ~few Hz, HF rolloff из Miller + parasitics ~MHz; PM
  measurement в audio band будет mid-band linear.
- Sanity gate: V_CE_q ∈ [4, 8] V, I_C_q ∈ [0.5, 3] mA в integration
  test — если op-point не active region, fail integration test
  raises (catches model issues + bias errors при future revisions).

**Q4 (ground truth). Решено: Primary = Middlebrook V @ canonical
break, Secondary = Bode-relation A/(1+T) cross-check.**
- Reason: согласуется с C.3 closure после Phase D (AC sanitizer
  fix) — strictest single method = V single @ canonical, остальные
  ±3° относительно V.
- Reason: Bode-relation T = A_open/(1 - A_closed·β) — даёт
  independent estimate без physical break debate. На C.3 у tube
  выявил 3 artificial crossings (LF C_in / mid cancellation / HF
  Cps); на BJT шанс cleaner результата выше из-за более linear
  small-signal model.
- Analytical (handed-derived) — НЕ primary из-за упрощений (Miller
  ignored, Early ignored, simplified pole), используется только как
  rough sanity ±10°.

**Q5 (strictness). Решено: honest empirical claim — V strict primary,
≥1 cross-validate strict ±3°, остальные documented degenerate с
reasoning. Strong claim ✓✓✓✓ — stretch goal.**
- Reason: прошлый опыт T153 C.1/C.3 показывает, что strong claim
  ✓✓✓✓ часто разбивается о physics edge cases (op-amp 2/4, tube 1/4).
  Honest acceptance не блокирует closure: matrix получает empirical
  row с reasoning независимо от outcome.
- Reason: closure value не в максимизации галочек, а в reliable
  per-topology guidance — «BJT CE: используй V, опционально Tian
  для cross-check, не используй Rosenstark потому что [reason]» —
  это работающий output для user / agent.

**Q6 (decomposition). Решено пользователем: single PR.** Phase A
(fixture) + Phase B (calibration + ADR + KB) бандлятся одним PR
с одним commit'ом (squash) — как T153 C.1 / C.3.

**Q7 (scope discipline). Принято: НЕ трогаем** T162 (namespace),
T120 (AppImage cleanup), T124 (freecad-mcp), T108 (OpenCode), AC
sanitizer (T153h closed), auto-detect heuristic (T164 closed).
**Bundle отдельным PR после merge**: T164 Level 3 smoke (8
scenarios, TODO 0ea5f0ef).

---

## Analyze

### 🔴 Critical (фиксим до начала реализации)

- **C-1. ON Semi 2N3904 SPICE model licensing — проверить перед
  commit'ом.** Не все vendor model files имеют permissive redistribution.
  Если ON Semi PSpice `.lib` нельзя коммитить → fallback на canonical
  Gummel-Poon parameters из ngspice examples / Sedra-Smith Appendix
  (public domain). Если decision = vendor model — explicitly comment
  source + license в `.lib` header. Если decision = textbook — ссылка
  на source.
  **Mitigation в Phase A**: при добавлении `data/models/bjt/onsemi/
  Q2N3904.lib` первый шаг — find authoritative source (ON Semi
  PSpice ZIP, ngspice example, или textbook reference), читаем license,
  принимаем decision. Если ON Semi запрещает — переименовываем категорию
  `bjt/onsemi/` → `bjt/generic/` с canonical params.

- **C-2. DC op-point sanity check — где enforce'ится?** §3 говорит
  «sanity check в builder/integration test». Без конкретики drift
  при future revisions проедет молча.
  **Mitigation в Phase A**: интеграционный тест
  `test_bjt_ce_nfb_facade.py::test_op_point_active_region` — builder
  пишет netlist → `SpiceSimulator` adapter гонит op-point analysis →
  asserts: V_CE_q ∈ [4, 8] V, I_C_q ∈ [0.5, 3] mA, V_BE_q ∈ [0.55, 0.75] V.
  ngspice доступен локально (проверено в T153). Pre-push pytest сам
  поймает drift.

### 🟡 Warning (обсуждаем)

- **W-1. Multi-loop risk на BJT CE.** R_E без полного bypass + C_E
  как frequency-dependent bypass → теоретически local loop через R_E
  активен на LF (где |Z_CE| высокий), global loop через R_F dominates
  на mid-band. Auto-detect heuristic T164 designed для multi-loop tube —
  может выбрать local loop на BJT.
  **Mitigation**: тесты passing canonical break explicitly через API,
  НЕ через auto-detect. Auto-detect на BJT — out of scope T163.
  Если в KB topic рекомендуется auto-detect threshold — записать
  «BJT CE: auto-detect не валидирован T163, передавай canonical
  break explicitly».

- **W-2. Single-stage CE inverting, R_F shunt-shunt → signal sign.**
  Single CE inverts (collector выход 180° from base input). Feedback
  R_F идёт от inverted collector обратно на base — это **shunt
  negative feedback** при правильной polarity. Topology работает,
  но при анализе loop sign в loop-break injection: Middlebrook V
  injects V_test между driver и load → loop gain T = -V_received/V_injected,
  отрицательный sign возникает естественно. **Note**: убедиться,
  что pipeline возвращает |T| с правильным sign (overall negative
  для NFB). Уже отработано на op-amp/tube — должно сработать.

- **W-3. Acceptance §4 wording revised** (per resolve W-Q5):
  «Primary V strict обязателен; ≥1 cross-validate strict — желательно,
  не блокирующий; documented matrix — обязательно независимо от
  outcome». Это **разблокирует closure** на честном empirical
  ✓×××-results (т.е. честный «V only strict, остальные degenerate
  because X»).

### 🟢 Note (к сведению)

- **N-1. `Sim.Library` post-process pattern.** Builder embedд'ит
  абсолютные dev-paths (`_MODELS_DIR/bjt/onsemi/Q2N3904.lib`); bake
  hook должен replace на relative `models/Q2N3904.lib`. Standard
  pattern (см. `_bake_se_amp` lines 130-138). Учесть в Phase A.

- **N-2. C_in / C_out LF poles ~1-10 Hz.** PM at gain crossover в
  audio band kHz; LF poles не контаминируют measurement. OK.

- **N-3. NPN 2N3904 → facade.add_bjt(polarity='NPN', model_name='Q2N3904',
  ...).** KiCad symbol `Device:Q_NPN`, pin order C/B/E через
  `Sim.Pins='C=1 B=2 E=3'`. facade.add_bjt уже есть (facade.py:992),
  только нужен `spice_directive('.include models/Q2N3904.lib')` или
  embedded `.model` block.

- **N-4. KB topic `spice.feedback-break-point.md` — после T164 обновлён
  с tube section + threshold 0.7 workflow. T163 добавляет BJT section
  с canonical break recommendation + per-method matrix; не trogarь
  tube/op-amp sections.

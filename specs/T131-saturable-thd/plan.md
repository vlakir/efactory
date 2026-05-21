# Plan: T131 SPICE saturable transformer + THD

**Связан со spec:** `spec.md` (Status: Analyzed)
**Дата:** 2026-05-21
**Ветка:** `T131-saturable-thd`
**Структура коммитов:** 4 phase-commit'а → squash в один при merge
(правило «один PR — один коммит»).

---

## Архитектурный обзор

T131 живёт чисто в SPICE-path, не трогает FEM (T133) и не зависит
от него. Зависит от:

- **T129 Phase A** — `FrohlichBHCurve` (extend с новым методом
  `.h_b_pairs()` для ngspice).
- **T008 / T101** — `NgspiceSimulator`, `build_wrapper`, `AnalysisSpec`
  union (extend с `FourierAnalysis` branch).
- **T113 Phase 2** — `MagneticComponent` domain VO (reuse как input
  generator'а).

Hexagonal architecture: новый адаптер `spice_models/saturable_core.py`
(pure text-out generator), новый use case `analyze_distortion_
spectrum.py` (orchestrator), новый domain VO `ThdSweepSpec` +
`ThdSpectrum` (input/output use case). Existing ports
(`Simulator`, `MagneticAnalytics`) — без изменений.

```
domain/             ports/outbound/         adapters/outbound/
─────────           ───────────────         ─────────────────
ThdSweepSpec  ────► (no new port)           spice_models/
ThdSpectrum                                   └─ saturable_core.py (NEW)
                                            ngspice/
FrohlichBH ◄──────── Simulator (existing)     ├─ wrapper.py (EXTEND)
   .h_b_pairs()                                └─ four_parser.py (NEW)
                                            fem_solver_getdp/material.py
                                                    └─ + new method
application/
─────────
analyze_distortion_spectrum.py (NEW)
   ▲
   │ — собирает: MagneticComponent + FrohlichBHCurve → saturable subckt;
   │   netlist library substitution; per-cell SPICE+.four; aggregate
   │   ThdSpectrum.
   │
composition/                  (DI assembly, минимальная правка)
```

## Phase-commit summary

| Phase | Commit subject | Файлы (new / extend) | Тесты | Est |
|-------|----------------|----------------------|-------|-----|
| A | `T131 Phase A: saturable core subckt generator + FrohlichBHCurve.h_b_pairs()` | 2 new, 1 extend | 2 unit | ~3h |
| B | `T131 Phase B: FourierAnalysis branch + ngspice .four parser` | 2 new, 2 extend | 3 unit | ~3h |
| C | `T131 Phase C: ThdSweepSpec/ThdSpectrum domain + analyze_distortion_spectrum use case + netlist substitution` | 3 new, 1 extend | 4 unit + 1 integration | ~5h |
| D | `T131 Phase D: pilot fixture + acceptance test on SE-amp 6П14П` | 1 new fixture, 1 new acceptance | 1 acceptance | ~3h |

**Total:** ~14h работы; реально 2-3 рабочих сессии.

---

## Phase A — Saturable core subckt generator

### Цель

Pure text-out generator: вход `MagneticComponent` + `FrohlichBHCurve`,
выход — string ngspice `.subckt` с B-source PWL table для saturable
primary inductance.

### Файлы

**Новые:**
- `src/adapters/outbound/spice_models/saturable_core.py` —
  функция `generate_saturable_transformer_subckt(component:
  MagneticComponent, bh_curve: FrohlichBHCurve, subckt_name: str)
  -> str`.

**Extend:**
- `src/adapters/outbound/fem_solver_getdp/material.py` —
  новый метод `FrohlichBHCurve.h_b_pairs() -> tuple[tuple[float,
  float], ...]` (возвращает `((H0, B0), (H1, B1), ...)` для
  ngspice PWL table). Reuse existing `b_values`, `h_values`.

### Subckt структура

```
.SUBCKT <NAME> P1 P2 S1 S2
* Saturable transformer (T131 generator).
* Material: <material_name>, μ_init=<μ>, B_sat=<B>, turns_pri=<N1>,
* turns_sec=<N2>, Lp_linear=<Lp>H.
*
* Flux ψ_pri через B-source с table lookup:
*   v_internal = N1 · A_core · B(H_eff),  H_eff = N1·I_pri / l_path
* Linear coupling Lpri↔Lsec при Ls_lin=Lp/n², k=k_chosen.
*
G_flux 1 0 I(V_sense)  ; primary current sense
B_psi  2 0 V = N1 * A * tablookup(<H-B pairs>, V(1)*N1/lpath)
... (детали — Plan фиксирует API generator'а, не финальный subckt)
.ENDS <NAME>
```

**Уточнение subckt-architecture в Phase A implementation** —
несколько возможных способов саттурации в ngspice. Финальный subckt
будет либо:
- (i) **B-source flux model:** B-source задаёт ψ(I) через table; L_pri
  = dψ/dI implicitly nonlinear; V_pri = N1 · dψ/dt.
- (ii) **Variable-L через behavioural source:** Lp на каждом моменте
  пересчитан как μ_chord(B(t))·N²·A/l.

Решаем в Phase A — explicit (i) или declarative (ii). Sanity check
через unit test (smoke `ngspice -b` ничего не валит).

### Тесты (TDD red → green)

**Unit:**
- `tests/unit/adapters/outbound/spice_models/test_saturable_core.py`
  - `test_generate_returns_well_formed_subckt`: subckt starts с
    `.SUBCKT NAME P1 P2 S1 S2`, ends `.ENDS NAME`, содержит B-source
    с tabulated H-B pairs, содержит N1/N2 ratio.
  - `test_smoke_ngspice_parses_subckt`: пишет subckt + trivial test
    netlist (1V DC source на P1-P2), запускает `ngspice -b`, exit
    code 0.

- `tests/unit/adapters/outbound/fem_solver_getdp/test_material.py`
  (extend existing) — new test:
  - `test_h_b_pairs_monotonic_starts_from_origin`: первая пара (0,
    0), каждая пара монотонна по B и H, последняя пара B ≈ 0.99·B_sat.

### Acceptance Phase A

- `uv run ruff check . && uv run ruff format --check . && uv run
  mypy src && uv run pytest` — 0 errors.
- Unit tests green; smoke `ngspice -b` accepts generated subckt.
- Test coverage на новые файлы ≥ 80% (мелкий generator — ожидаем ~100%).

### Commit message Phase A

```
T131 Phase A: saturable core subckt generator + FrohlichBHCurve.h_b_pairs()

- Add generate_saturable_transformer_subckt() in spice_models/saturable_core.py:
  input MagneticComponent + FrohlichBHCurve → ngspice .subckt text.
- Add FrohlichBHCurve.h_b_pairs() method — exports (H, B) tuples for
  ngspice PWL table (companion to existing GetDP nu_of_b_table()).
- Unit tests: subckt well-formed; ngspice -b parses without error;
  h_b_pairs monotonic from origin to ~B_sat.

Phase A of 4 (see specs/T131-saturable-thd/plan.md).
```

---

## Phase B — FourierAnalysis branch + .four parser

### Цель

Расширить `AnalysisSpec` discriminated union на `FourierAnalysis`
branch и `build_wrapper` на эмиссию ngspice `.four` directive.
Parser ngspice log → structured Fourier output (per harmonic
amplitude + phase + THD).

### Файлы

**Новые:**
- `src/adapters/outbound/ngspice/four_parser.py` — function
  `parse_four_output(log_text: str) -> FourierResult` (regex-based;
  ngspice log format известен).

**Extend:**
- `src/domain/simulation.py` — new `FourierAnalysis` BaseModel
  + `FourierResult` BaseModel + extend `AnalysisSpec` union +
  extend `SimulationResult` (new optional branch `fourier_result`).
- `src/adapters/outbound/ngspice/wrapper.py` — extend
  `_format_directive` на `FourierAnalysis` branch.
- `src/adapters/outbound/ngspice/simulator.py` — extend `.run` для
  parse `.four` output из ngspice stdout/log (текущий `.run`
  читает `.raw` файл; `.four` output **в log**, не в `.raw`, потому
  что Fourier — analysis post-tran).

### Domain VO структура

```python
class FourierAnalysis(BaseModel):
    """ngspice `.four` analysis: pairs with TranAnalysis."""
    type: Literal['four'] = 'four'
    tran: TranAnalysis             # transient run on which to Fourier
    fundamental_hz: float          # > 0
    n_harmonics: int               # >= 2, <= 20
    signal: str                    # node name e.g. 'v(load)'

class HarmonicSample(BaseModel):
    """Один harmonic из .four output."""
    n: int                         # harmonic index (1=fund, 2, 3, ...)
    frequency_hz: float
    magnitude: float
    phase_deg: float
    normalized: float              # mag / mag(fund)

class FourierResult(BaseModel):
    """ngspice .four block parsed."""
    fundamental_hz: float
    thd_percent: float
    harmonics: tuple[HarmonicSample, ...]   # length == n_harmonics
```

`SimulationResult` теперь имеет **4 опциональных ветви** (op,
time_series, ac_sweep, fourier_result); validator расширяется на
«exactly one of 4».

### Тесты (TDD red → green)

**Unit:**
- `tests/unit/domain/test_simulation.py` (extend) —
  - `test_fourier_analysis_validation`: n_harmonics ≥ 2, fundamental_hz
    > 0, signal не пустой.
  - `test_simulation_result_exactly_one_of_four_branches`: existing
    validator расширен.

- `tests/unit/adapters/outbound/ngspice/test_four_parser.py` (new) —
  - `test_parse_known_four_log`: fixture ngspice log с `.four`
    блоком (canned text), parser возвращает корректные harmonics
    + THD.
  - `test_parse_rejects_malformed_log`: missing block → raises.

- `tests/unit/adapters/outbound/ngspice/test_wrapper.py` (extend) —
  - `test_format_directive_fourier`: input FourierAnalysis →
    output contains `.tran <ts> <tt>` + `.four <fund> <n_harm>
    <signal>`.

**Integration:**
- `tests/integration/adapters/outbound/ngspice/test_simulator_four.py`
  (new, gated `@needs_ngspice`) —
  - `test_run_fourier_on_pure_sine_returns_zero_thd`: synth netlist
    с одним sin-source 1V 1kHz на R-load → `.four` → THD < 1%
    (only numerical noise).
  - `test_run_fourier_on_clipped_sine_returns_non_zero_thd`: sin
    через diode clamp → THD > 10%.

### Acceptance Phase B

- Pre-push gate green.
- `FourierAnalysis` поддержан в `AnalysisSpec` discriminated union
  (Pydantic validation работает).
- ngspice integration tests pass на dev-машине / в efactory:linux.
- `SimulationResult` invariant сохранён (exactly one of branches).

### Commit message Phase B

```
T131 Phase B: FourierAnalysis branch + ngspice .four parser

- domain/simulation.py: add FourierAnalysis branch to AnalysisSpec
  union; add FourierResult, HarmonicSample VOs; extend SimulationResult
  validator (exactly-one-of-4).
- ngspice/wrapper.py: emit .tran + .four directives for FourierAnalysis.
- ngspice/four_parser.py: parse ngspice .four block from log.
- ngspice/simulator.py: when analysis is FourierAnalysis, parse log
  for .four output instead of .raw.
- Integration tests: pure sin → THD ≈ 0; clipped sin → THD > 10%.

Phase B of 4.
```

---

## Phase C — Domain VO + use case + netlist substitution

### Цель

Сборка: domain `ThdSweepSpec` (input) / `ThdSpectrum` (output) VO,
use case `analyze_distortion_spectrum`, netlist library substitution
helper.

### Файлы

**Новые:**
- `src/domain/thd.py` — `ThdSweepSpec`, `ThdSpectrum`,
  `ThdMeasurementPoint`.
- `src/application/analyze_distortion_spectrum.py` — use case.
- `src/adapters/outbound/ngspice/netlist_substitution.py` —
  helper для library substitution в netlist text.

**Extend:**
- `src/composition/` (если нужна DI factory для new use case) —
  минимальная правка, possibly just registration.

### Domain VO структура

```python
class ThdSweepSpec(BaseModel):
    """Input для analyze_distortion_spectrum."""
    component: MagneticComponent
    bh_curve: FrohlichBHCurve
    frequencies_hz: tuple[float, ...]      # length >= 1
    output_powers_w: tuple[float, ...]     # length >= 1
    load_ohm: float = 8.0                  # acceptance fixture default
    signal_node: str = 'v(load)'           # SPICE node для measure

class ThdMeasurementPoint(BaseModel):
    """Один cell спектра."""
    frequency_hz: float
    target_power_w: float
    measured_power_w: float                # actual после single-pass cal
    thd_percent: float
    dominant_harmonic_n: int               # 2 для SE class A
    harmonics: tuple[HarmonicSample, ...]  # reuse Phase B VO

class ThdSpectrum(BaseModel):
    """Output use case — full sweep result."""
    component_name: str
    points: tuple[ThdMeasurementPoint, ...]   # length = len(freqs) × len(powers)
    runtime_seconds: float
```

### Use case интерфейс

```python
async def analyze_distortion_spectrum(
    *,
    schematic_netlist_path: Path,
    spec: ThdSweepSpec,
    target_subckt_name: str,        # e.g. 'OPT_SE_5K_8'
    simulator: Simulator,
    workdir: Path,                  # для временных netlist'ов
) -> ThdSpectrum:
    """
    1. Generate saturable subckt из (component, bh_curve).
    2. Substitute target subckt в netlist (library substitution).
    3. Per (freq, power) — single-pass voltage calibration:
        a. .OP analysis → quiescent linear gain.
        b. V_grid_estimate = sqrt(2·P·R_load/gain²).
        c. .TRAN (10 periods @ fundamental, t_step=period/100) + .four.
        d. measured_power = V_load_rms²/R_load.
    4. Aggregate ThdSpectrum.
    """
```

### Netlist substitution

```python
def substitute_subckt_library(
    netlist_text: str,
    target_subckt_name: str,
    new_subckt_text: str,
) -> str:
    """
    Replace `.include <path/to/<target>.lib>` (или `.lib ...`)
    с inline subckt text.

    Идемпотентно (повторный вызов с тем же replacement = noop).
    Raises ValueError, если target subckt не найден в netlist.
    """
```

### Тесты (TDD red → green)

**Unit:**
- `tests/unit/domain/test_thd.py` —
  - `test_thd_sweep_spec_requires_nonempty_freqs_powers`.
  - `test_thd_spectrum_points_count_matches_matrix`.
  - `test_thd_measurement_point_dominant_harmonic_in_range`.

- `tests/unit/application/test_analyze_distortion_spectrum.py` —
  - `test_use_case_calls_simulator_per_matrix_cell` (fake
    `Simulator` returns canned `FourierResult`; assert N calls).
  - `test_use_case_aggregates_thd_spectrum`: fake returns known
    harmonics → assert THD%, dominant harmonic computed correctly.
  - `test_use_case_raises_on_simulator_failure`.

- `tests/unit/adapters/outbound/ngspice/test_netlist_substitution.py` —
  - `test_substitute_replaces_include_with_inline`.
  - `test_substitute_idempotent`.
  - `test_substitute_raises_when_target_not_found`.

**Integration:**
- `tests/integration/application/test_analyze_distortion_spectrum.py`
  (gated `@needs_ngspice`) —
  - `test_synthetic_minimal_amp_returns_well_formed_spectrum`:
    минимальная схема (V_in → R → linear OPT proxy → R_load),
    подаём saturable subckt, ожидаем ThdSpectrum со всеми cells
    заполненными.

### Acceptance Phase C

- Pre-push gate green.
- All unit tests pass; mock Simulator validated.
- Integration test passes (synth minimal amp) — не acceptance pilot
  ещё, тот в Phase D.
- Coverage ≥ 80% на новые файлы.

### Commit message Phase C

```
T131 Phase C: ThdSweepSpec/ThdSpectrum domain + analyze_distortion_spectrum + netlist substitution

- domain/thd.py: ThdSweepSpec, ThdSpectrum, ThdMeasurementPoint VOs.
- application/analyze_distortion_spectrum.py: use case orchestrator —
  single-pass voltage calibration + per-cell SPICE + .four + aggregate.
- ngspice/netlist_substitution.py: helper for library substitution.
- Tests: unit on domain validation; fake Simulator on use case;
  netlist substitution edge cases; integration on synth minimal amp.

Phase C of 4.
```

---

## Phase D — Pilot fixture + acceptance test

### Цель

Конкретный `MagneticComponent` для OPT_SE_5K_8 (A1 resolution),
acceptance pilot test на SE-amp 6П14П.

### Файлы

**Новые:**
- `tests/fixtures/magnetic/opt_se_5k_8_component.py` —
  factory function `opt_se_5k_8_magnetic_component() ->
  MagneticComponent` (Core E42/15 Nanoperm 8000, gap 0.3 mm,
  primary 1000 turns + secondary 40 turns ratio 25:1, bobbin
  E42/15).
- `tests/acceptance/` (new directory) + `__init__.py`.
- `tests/acceptance/test_saturable_thd_se_amp.py` — pilot
  acceptance test.

### Acceptance test структура

```python
@needs_kicad
@needs_ngspice
@pytest.mark.acceptance
async def test_se_amp_6p14p_saturable_thd_pilot(tmp_path: Path):
    # 1. Build se-amp schematic via existing facade
    #    (test_se_amp_facade flow, reused as factory).
    # 2. Export netlist via KicadCliSchematicExporter.
    # 3. component = opt_se_5k_8_magnetic_component().
    # 4. bh_curve = FrohlichBHCurve.from_pyom_material(
    #        mu_initial=8000, b_sat=1.2)
    # 5. spec = ThdSweepSpec(
    #        component=component,
    #        bh_curve=bh_curve,
    #        frequencies_hz=(50.0, 1000.0, 10000.0),
    #        output_powers_w=(0.25, 1.0, 3.0),
    #    )
    # 6. spectrum = await analyze_distortion_spectrum(
    #        schematic_netlist_path=netlist, spec=spec,
    #        target_subckt_name='OPT_SE_5K_8',
    #        simulator=NgspiceSimulator(app_mgr),
    #        workdir=tmp_path,
    #    )
    # 7. Primary acceptance gate:
    #    point_1khz_1w = find_closest(spectrum, freq=1000, power=1.0,
    #                                  power_tol=0.20)
    #    assert 1.0 <= point_1khz_1w.thd_percent <= 5.0
    #    assert point_1khz_1w.dominant_harmonic_n == 2
    # 8. Monotonic THD by power @ 1 kHz:
    #    thd_at_1khz = sorted by power
    #    assert thd_at_1khz strictly increasing
    # 9. Runtime budget: spectrum.runtime_seconds <= 120
    # 10. Diagnostic logging: print full spectrum table для review.
```

### Pre-check (A1 sanity)

Перед commit pilot — отдельный standalone unit test
`test_opt_se_5k_8_component_pyom_inductance`:
- PyOM `calculate_inductance` на новый `MagneticComponent`
  возвращает Lp близкое к 50 H (static lib magic number)
  с tolerance ±50% (Lp очень sensitive к gap; loose tolerance).
- Если Lp выйдет 5 H или 500 H — geometry/material выбран wrong.
- Если в [25, 75] H — OK, proceed с pilot.

### Acceptance Phase D

- Pre-push gate green.
- Acceptance pilot test passes (или: failure path по Clarify Q6
  ставится в action).
- Runtime ≤ 120 сек budget.
- Spectrum table готов для review Vladimir (pretty-print в test
  output).

### Commit message Phase D

```
T131 Phase D: pilot fixture + acceptance test on SE-amp 6П14П

- tests/fixtures/magnetic/opt_se_5k_8_component.py: PyOM-derived
  MagneticComponent for OPT_SE_5K_8 (E42/15 Nanoperm 8000, gap 0.3 mm,
  1000:40 turns ratio).
- tests/acceptance/test_saturable_thd_se_amp.py: acceptance pilot —
  SE-amp 6П14П with saturable OPT, 3×3 sweep, primary gate
  THD @ 1 kHz / 1 W ∈ [1%, 5%] with dominant 2nd harmonic.
- Sanity check: PyOM Lp on new MagneticComponent close to static lib
  50 H ±50% (loose, gap-sensitive).

Phase D of 4 — closes T131.
```

---

## Out of plan (явно НЕ делаем)

- **GUI Simulator acceptance** — Vladimir проверяет вручную после
  merge (T100 ритуал).
- **Hysteresis modeling** (B-H loop) — открыли T134 если pilot fail.
- **Material расширение** для GOSS M6 в `FrohlichBHCurve` —
  follow-up если Nanoperm 8000 proxy окажется недостаточным.
- **`.kicad_sch` modification** (schematic-level saturable) —
  follow-up T13X если возникнет user-need.
- **Closed-loop power calibration** — single-pass + ±20% tolerance
  достаточно для acceptance.
- **Other tube amps** (триод 6Н2П, push-pull) — generator universal,
  но validation в этой спеке только SE-amp 6П14П.
- **Sweep по material catalog** — отдельная задача (Phase 5 dorm).

---

## Quality gates per phase

Каждая фаза заканчивается прохождением:

```bash
uv run ruff check . && \
uv run ruff format --check . && \
uv run mypy src && \
uv run pytest && \
git add -A && git commit -m "T131 Phase X: ..."
```

Pre-push gate перед `git push -u origin T131-saturable-thd`
после всех 4 фаз — обязательно (правила repo).

## После Phase D

1. `git push -u origin T131-saturable-thd`.
2. `gh pr create` → получаем `#N`.
3. Перенести запись T131 в `BOARD.md` из Doing → Done с пометкой
   `[closed 2026-05-2X, PR #N]` (project rule: closing-правка
   делается **после** `gh pr create` отдельным commit'ом).
4. `git push` второй commit.
5. Self-review по checklist (scope / architecture / linters /
   docs / conventions / security).
6. **Опционально:** `/ultrareview <PR#>` — этот PR FEM/numerical-
   adjacent (Frohlich + Fourier math), но pure SPICE (не FEM). На
   T129 ultrareview нашёл flux linkage formula bug — для T131
   similar risk: B-H table correctness, calibration math. **Recommend
   `/ultrareview`** (использует quota, но обоснованно).
7. Squash merge.

## Зависимости и риски

**Зависимости:** T129 Phase A `FrohlichBHCurve` (есть, ready);
T113 Phase 2 `MagneticComponent` domain VO (есть, ready); T101 KiCad
schematic export (есть, ready).

**Риски:**

| Риск | Mitigation |
|------|------------|
| ngspice convergence failure на saturable B-source (numerical instability в saturation knee) | Plan: Frohlich curve smooth → expected OK; fallback — снизить `b_top` с 0.99 до 0.95 в FrohlichBHCurve. |
| PyOM `MagneticComponent` для OPT не сходится к 50 H — wrong geometry choice | Pre-check Phase D sanity test catches this; tune gap/turns before pilot. |
| `.four` directive precision на 50 Hz с 10 periods → 200 ms transient может быть slow | Acceptable: 50 Hz — diagnostic, не gate. Если совсем slow — снизить до 5 periods, accept reduced precision. |
| Static `OPT_SE_5K_8.lib` имеет Cps=200pF (inter-winding cap) — saturable subckt должен либо replicate, либо acceptance может расходиться | Plan: saturable subckt включает same Cps как **linear parameter**, не модель насыщения. |
| pytest acceptance test runs `kicad-cli` — slow на CI | Plan: `@pytest.mark.acceptance` mark, default skipped в `pytest`, opt-in через `pytest -m acceptance`. |

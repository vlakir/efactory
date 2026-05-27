# Spec: Параметрический sweep (`bridge_sweep`) с tabular output + ASCII plot

**Статус:** Analyzed
**Дата создания:** 2026-05-27
**Clarify прошёл:** 2026-05-27 (10 вопросов; 9 «по рекомендации» +
Q-H → a auto-detect log/linear)
**Analyze прошёл:** 2026-05-27 (14 issues: 2 Critical разрешены
in-spec, 6 Warning с predeclared resolutions, 6 Note —
реализационные guidance)
**Связанные документы:**
- `BACKLOG.md → ### Фаза 2 → T022`.
- `BACKLOG.md → T144` (absorbed 2026-05-27): sweep tabular numerical
  output + CSV/JSON gap.
- `application/bridge_sweep.py` — текущая реализация (T004b Phase 1,
  OP-only).
- `application/measure_{gain,bandwidth,thd}.py` — фундамент T023.
- `adapters/inbound/cli/plot_renderer.py` — фундамент T024.
- `domain/sim_results.py` — `SimResult` + `AnalysisType` enum.
- Top-level scope подтверждён в чате 2026-05-27:
  - **A** → c: `--metric op|gain|bandwidth|thd` с default `op`;
  - **B** → c: orthogonal `--analysis op|tran|ac|four` × `--metric`;
  - **D** → a: `--output text|csv|json` + `--output-file`;
  - **E** → a: 2-парам → multi-line plot, >2 параметров → plot disabled;
  - **F** → `/sweep` (slash-команда);
  - **G** → расширить существующий `bridge sweep` subcommand
    (backward-compat: OP default);
  - **H** → soft warn N>20, hard cap N>100 (`--max-combinations`);
  - **I** → KB sync Level 1+2 (T134 правило).

---

## 1. Overview

`efactory bridge sweep` — параметрический пробег SPICE-симуляции по
Cartesian product значений 1-2 параметров с **tabular numerical
output** (raw operating-points, либо измеренные метрики `gain` /
`bandwidth` / `thd` через T023) и **ASCII plot** (через T024) для
1-2 параметрических sweep'ов. Заменяет текущую T004b Phase 1 OP-only
реализацию (которая печатает только лейблы без чисел — T144),
сохраняя обратную совместимость для голого `--param REF=v1,v2`.

Цель — закрыть «самый частый use case в проектировании ламповых
каскадов»: sweep по катодному резистору / B+ / Rg с numerical
output из коробки. Plot — для визуального восприятия тренда (как
gain растёт с увеличением Rk и т.д.).

T022 — третий шаг analysis-first ordering Фазы 2:
- T023 (метрики) ✅ merged;
- T024 (plot) ✅ merged;
- **T022 (sweep) — текущая задача**;
- T021 (delta) — следующая, использует T022 как фундамент.

## 2. Сценарии использования

> Проект без явных «ролей» — efactory работает с агентом и Разработчиком
> через CLI / chat-обёртку.

- **Сценарий A (Agent / single-parameter raw OP sweep).** Агент
  проектирует SE amp и хочет понять, как меняется bias-точка катода
  при изменении `Rk`. Вызывает
  `efactory bridge sweep se-amp-demo --schematic se-amp-demo.kicad_sch
  --param Rk=470,560,680,820 --analysis op` → tabular:
  `Rk | V(plate) | V(K) | I(V1)` × 4 строки.

- **Сценарий B (Agent / single-parameter metric sweep).** Агент хочет
  понять зависимость gain от Rk. Вызывает
  `... --param Rk=470,560,680,820 --metric gain --freq 1000` →
  tabular: `Rk | gain_db | gain_linear` × 4 строки + (опционально)
  ASCII plot Rk vs gain_db.

- **Сценарий C (Agent / 2-parameter bandwidth sweep).** Агент хочет
  видеть как bandwidth зависит от `Cin` и `Rk`. Вызывает
  `... --param Cin=10n,100n,1u --param Rk=470,820 --metric bandwidth`
  → tabular матрица 3×2 + 2-линейный ASCII plot (одна линия на
  значение Rk, X = Cin).

- **Сценарий D (Agent / CSV export).** Агент хочет передать данные
  в дальнейшую обработку (например, для regression analysis).
  Вызывает `... --output csv --output-file sweep.csv` → CSV-файл,
  stdout молчит (или короткое summary).

- **Сценарий E (Agent / soft-warn over-budget).** Агент вызывает
  `--param R=1k,2k,3k,4k,5k --param C=100n,1u,10u,100u,1m` → 25
  combinations. Stdout: `Warning: 25 combinations × ~60s = ~25min.
  Continue? (use --max-combinations 100 to silence warning)` →
  по умолчанию **продолжает выполнение** (warning, не block).

- **Сценарий F (Agent / hard cap).** При N>100 без `--max-
  combinations` → exit 2 с сообщением о cap и предложением понизить
  granularity или явно указать override.

- **Сценарий G (T021 prerequisite, programmatic).** Use case
  `bridge_edit_and_resim` (T021) — частный случай sweep'а N=1
  параметра × 2 значения (before/after); reuse `bridge_sweep`
  internal-ом, не CLI-shell-out.

## 3. Functional Requirements

- **ДОЛЖНА** расширить `bridge sweep` CLI subcommand следующими
  флагами:
  - `--analysis <op|tran|ac>` (default `op`) — определяет
    физический SPICE-прогон per combination. **FOUR из списка
    исключён** (Q-B → c): он — внутренний механизм для
    `--metric thd`, наружу не торчит.
  - `--metric <op|gain|bandwidth|thd>` (default `op`) — определяет,
    как извлекаются числа в строку таблицы.
  - `--output <text|csv|json>` (default `text`).
  - `--output-file <path>` — записать output в файл (опционально);
    `text` тоже допустим (для логирования).
  - `--plot` (flag, default off) — при N ≤ соответствующего лимита
    показывать ASCII plot после таблицы.
  - `--plot-y <field>` — какую колонку использовать как Y (для
    metric — auto: `gain_db` / `bandwidth_hz` / `thd_percent`; для
    raw OP — обязательный явный signal name).
  - `--plot-x-scale <auto|linear|log>` (default `auto`) — Q-H → a +
    Analyze A8: log-space detection алгоритм.
  - `--output-signal <name>` (default `v(load)`, Analyze A6) —
    для metric mode pass-through в `measure_*`. Для `--metric op`
    игнорируется.
  - `--max-combinations <N>` (default 100) — override hard cap.
  - `--freq <Hz>` — обязательный для `--metric gain` и `--metric thd`.
  - `--f-low <Hz>`, `--f-high <Hz>` — для `--metric bandwidth`
    (default 1, 1e6).
  - `--mode <small|large>` — для `--metric gain` (default `small`).
  - `--v-in-peak <V>` — для `--metric gain --mode large` и
    `--metric thd`.
  - Существующие флаги (`--schematic`, `--param`, `--netlist-dir`,
    `--timeout`) — без изменений.

- **ДОЛЖНА** auto-mapping `--metric` → `--analysis`, если последний
  не указан явно (Analyze A1 — список **строго** валидных пар):
  - `--metric op` ⇔ `--analysis op` (единственная пара для `op`);
  - `--metric gain --mode small` ⇔ `--analysis ac`;
  - `--metric gain --mode large` ⇔ `--analysis tran`;
  - `--metric bandwidth` ⇔ `--analysis ac`;
  - `--metric thd` ⇔ `--analysis tran` (+ ngspice `fourier` internal).
  Любая другая комбинация при **явно** указанном `--analysis` →
  `typer.Exit(code=2)` с понятным сообщением:
  `incompatible combination: --metric=X --analysis=Y;
  expected --analysis=Z`.

- **ДОЛЖНА** при `--metric op` использовать
  `result.operating_points` напрямую (обратная совместимость T004b
  Phase 1). Если operating_points пуст — fail combination с
  понятным сообщением (см. §6 «T144 root-cause»).

- **ДОЛЖНА** при `--metric {gain,bandwidth,thd}` использовать
  существующие T023 use cases (`measure_gain` / `measure_bandwidth`
  / `measure_thd`) per combination. Результат VO выкладывается в
  ячейки таблицы.

- **ДОЛЖНА** генерировать tabular output по правилам:
  - **Колонки**: сначала параметры sweep'а (по порядку `--param`),
    потом колонки метрики (Analyze A5, фиксированный mapping):
    - **`gain`**: CSV `gain_db, gain_linear`; JSON добавляет
      `frequency_hz, mode, input_signal, output_signal, v_in_peak`.
    - **`bandwidth`**: CSV `f_low_hz, f_high_hz, bandwidth_hz`;
      JSON добавляет `midpoint_db, ref_db, midpoint_source,
      ref_freq_hz, input_signal, passband_signal`.
    - **`thd`**: CSV `thd_percent, dominant_harmonic_n,
      dominant_harmonic_percent`; JSON добавляет
      `fundamental_hz, v_in_peak, measured_power_w, signal,
      n_harmonics`.
    - **`op`**: dynamically — union всех ключей
      `result.operating_points` across combinations; missing →
      `None`.
  - **Текстовый формат**: aligned plain-text table (без library
    `tabulate` — используем стандартный str-форматтер). Текстовая
    таблица содержит то же подмножество колонок что CSV (для
    краткости); JSON — полный набор полей.
  - **CSV**: stdlib `csv.writer`, RFC 4180.
  - **JSON**: list[dict[col, value]], pretty-print (indent=2).

- **ДОЛЖНА** для plot:
  - **1-param sweep**: X = swept parameter (numeric SPICE notation
    parsed через существующий `parse_spice_number`); Y = chosen
    metric.
  - **2-param sweep**: multi-line plot, одна линия на значение
    второго параметра (label = `<param2>=<value>`). X — первый
    `--param` в порядке указания.
  - **X-axis scale**: **auto-detect** linear vs log (Q-H → a +
    Analyze A8). Алгоритм в **log-space** (robust к non-sorted):
    1. Парсим values через `parse_spice_number()`, фильтруем
       positive, сортируем ascending.
    2. При N≥3 после фильтра: `log10_values = [log10(v) for v in
       sorted_values]`, `diffs = [log10_values[i+1] -
       log10_values[i]]`.
    3. Если `stdev(diffs) / mean(diffs) < 0.10` И `mean(diffs)
       > 0.18` (≈ ratio 1.5) → geometric series → **log scale**.
    4. Иначе → **linear**.
    5. N<3 или не все positive → linear.
    Override через `--plot-x-scale linear|log` (escape hatch).
  - **>2 params**: `--plot` → warning + skip plot, таблица всё
    равно строится.
  - **Raw OP без явного `--plot-y`**: `--plot` → warning + skip.
  - **Non-numeric params** (например `--param model=KP-507,KP-509`):
    `parse_spice_number` fail → plot disabled с warning, таблица
    строится.

- **ДОЛЖНА** при N > soft warn limit (20) выводить warning в
  stderr с estimated runtime, не блокировать выполнение (Analyze
  A7 — упрощённый текст):
  `Warning: N combinations (estimated ~M min upper-bound runtime).
  Continuing.`
  где `M = ceil(N * timeout_seconds / 60)` (Analyze A13: upper-
  bound оценка, реальное время обычно 5-10× меньше). При N > hard
  cap (100, override через `--max-combinations <N>`) — exit 2
  без запуска с сообщением о cap.

- **ДОЛЖНА** иметь slash-команду `/sweep` (hyphenated flat per
  T014 A1 — но `sweep` — одно слово, без дефиса) в
  `docker/runtime-agent-commands/sweep.md`. Frontmatter:
  `description` + `argument-hint` + `allowed-tools: Bash`.

- **ДОЛЖНА** обновить KB topic `agent.command-routing` (T134
  Level 1): добавить строку для `/sweep`. **МОЖЕТ** завести
  отдельный KB topic если найдём pitfall в процессе implementation
  (например, «metric/analysis несовместимость» или «N²-blowup при
  2-парам»).

- **ДОЛЖНА** иметь deterministic regression test в
  `tests/integration/agent_kb/test_control_examples.py` (T134
  Level 2): `(query, expected_topic, expected_directive_keyword)`
  для `/sweep`.

- **НЕ ДОЛЖНА** писать `SimResult` через `SimResultsRepository`
  (Q-C → c): sweep — analytical artifact, не одиночная симуляция.
  Persistence — через `--output-file` explicit'ом.

- **НЕ ДОЛЖНА** делать diff measurement / before-after — это T021.

- **НЕ ДОЛЖНА** добавлять новые analysis backends (FEM, magnetic).

- **НЕ ДОЛЖНА** менять `application/edit_component_value` (Q-?).

- **НЕ ДОЛЖНА** делать parallel SPICE execution (per-combination
  последовательно; параллелизация — отдельная задача в BACKLOG,
  если возникнет потребность).

- **НЕ ДОЛЖНА** включать calibration loop для target-power (это
  T131 специализация).

## 4. Success Criteria

- Agent в `efactory:linux` TUI на `se-amp-demo` после T147 merge
  получает корректную tabular output для всех 4 metric types:
  - `--metric op --param Rk=470,820` → таблица с `V(plate)/V(K)/
    I(V1)` × 2 строки (после T147 OP сходится, см. §6).
  - `--metric gain --freq 1000 --param Rk=470,820` → таблица с
    `gain_db` × 2 строки.
  - `--metric bandwidth --param Rk=470,820` → таблица с
    `f_low_hz/f_high_hz/bandwidth_hz` × 2 строки.
  - `--metric thd --freq 1000 --v-in-peak 0.1 --param Rk=470,820`
    → таблица с `thd_percent` × 2 строки.

- 2-парам sweep `--param Cin=10n,100n --param Rk=470,820 --metric
  bandwidth --plot` → таблица 2×2 + 2-линейный ASCII plot.

- `--output csv --output-file sweep.csv` → корректный CSV-файл с
  header + rows.

- N > 20 → warning в stderr; N > 100 без override → exit 2.

- Все 5 pre-push gates зелёные (ruff / format / mypy / lint-imports
  3/3 KEPT / pytest); coverage ≥ 80% на новом коде.

- Acceptance тесты: ≥ 1 happy-path на каждый `--metric`, ≥ 1
  unhappy (metric/analysis incompat, N>cap без override, --plot
  с >2 params); e2e на real ngspice минимум 1 combination для
  каждого metric type.

- KB sync passed: `agent.command-routing` обновлён + regression
  test в `test_control_examples.py` зелёный.

## 5. Key Entities

- **`SweepRun`** (existing, in `application/bridge_sweep.py`) —
  расширяем **опциональным** полем `values: dict[str, float | str
  | None] | None = None` (Q-A → b + Analyze A4: backward-compat).
  - `result: SimulationResult | None` **остаётся** в VO (no
    breakage existing callers).
  - Для **`--metric op`** path: `result` filled (как раньше),
    `values` тоже filled — derived from `result.operating_points`
    (так renderer работает единообразно).
  - Для **metric-path** (`gain`/`bandwidth`/`thd`): `result=None`,
    `values` filled из соответствующего `Measurement` VO через
    A5 mapping.
  - `error: str | None` — без изменений (Q-D → a: failed
    combination → `values={col: None for col in metric_cols}` +
    `error='...'`).

- **`SweepConfig`** (новое, в `application/bridge_sweep.py`) —
  Pydantic frozen VO: `analysis: AnalysisType`, `metric: Literal
  ['op', 'gain', 'bandwidth', 'thd']`, плюс metric-specific поля
  (freq, mode, v_in_peak, f_low, f_high). Validators проверяют
  metric/analysis совместимость + required-поля per metric.

- **`SweepRow`** (новое, для table output) — Pydantic VO:
  `parameters: dict[str, str]`, `values: dict[str, float | str |
  None]` (None = combination failed). Сериализуется в text/CSV/JSON
  одинаково.

- **`SweepTableRenderer`** (новое, в `adapters/inbound/cli/`) —
  pure-function: `render_text/csv/json(rows: list[SweepRow]) ->
  str`. Testable без захвата stdout.

- **`SweepPlotRenderer`** (новое или extension `plot_renderer.py`)
  — pure-function: `render_sweep_plot(rows, x_param, y_field, *,
  group_by: str | None = None) -> str`. Multi-line plot для
  group_by != None.

## 6. Assumptions & Constraints

- **T147 закрыт (merged 2026-05-26).** OPT_SE_5K_8 floating-node
  баг fixed; теперь `.op` на `se-amp-demo` должен сходиться и
  возвращать непустой `operating_points`. **Проверить ручным
  smoke в Phase A**: `efactory bridge sweep se-amp-demo --schematic
  se-amp-demo.kicad_sch --param Rk=470 --analysis op` → если
  `operating_points` всё ещё пуст — fix root cause (vероятно в
  ngspice `.raw` parser или `.cir` generation) **в scope T022**.
  Это и есть прямой смысл T144.

- **Существующий `bridge_sweep`** имеет `for combo in itertools.
  product(*value_lists)` цикл с per-combination tempdir +
  `edit_component_value` + `export_spice_netlist` + `sim_run`.
  Расширение: на месте `sim_run` (когда `--metric != 'op'`) звать
  соответствующий `measure_*` use case (который сам делает sim под
  капотом). Для `--metric op` сохраняем текущий путь через `sim_run`.

- **Параметры sweep'а — string-typed** (SPICE notation `470`, `1k`,
  `10n`). Для plot X-axis парсятся через
  `parse_spice_number()` из `spice_units.py`. Если parsing fail
  (e.g., `--param model=KP-507,KP-509`) → plot disabled с warning,
  таблица строится.

- **T023 use cases** (`measure_gain` / `bandwidth` / `thd`) уже
  принимают netlist+exporter+simulator; reuse one-to-one. Без
  выноса в новый shared use case (Q-?).

- **`Simulator` port** (ngspice) — без изменений; уже умеет
  op/tran/ac/four.

- **`SchematicExporter` port** (kicad-cli) — без изменений; уже
  умеет export netlist'а.

- **Time budget**: per-combination ~30-60s на типичной фикстуре
  (SE amp); 100 combinations → ~50min в worst case (TRAN+THD).
  Soft warn 20 / hard cap 100 — баланс между «нужно очень много
  combinations для serious sweep» и «не хочу случайно запустить
  ночной прогон». Override через CLI.

- **Параллелизация — out of scope.** Per-combination
  последовательно. Если возникнет потребность — отдельная задача
  в BACKLOG.

- **Slash-команда `/sweep`**: cwd-instability проблема (T014 A2)
  → в frontmatter `argument-hint` явно требовать абсолютные пути
  для `--schematic`.

## 7. Out of Scope

- **T021 (`bridge_edit_and_resim` с auto-delta)** — следующая
  задача Фазы 2; T022 даёт фундамент (sweep over 2 values =
  before/after).
- **T025 (Sixel/Kitty schematic render)** — отдельная задача,
  ортогональна.
- **Parallel SPICE execution** — backlog при необходимости.
- **Sweep по non-component параметрам** (например, `.options` /
  `temp` / model parameters) — текущий design завязан на
  `edit_component_value(ref, value)` который меняет component
  values. Расширение — отдельная задача.
- **Adaptive sweep / golden-section search** — поиск оптимума по
  градиенту, не Cartesian product. Backlog.
- **FOUR `--analysis four` raw output без `--metric thd`** —
  resolved Q-B → c: FOUR убран из CLI options, доступен только
  как внутренний механизм `--metric thd`.

---

## Clarify (заполняется Claude)

### Open questions

- **Q-A: `SweepRun.metric_value` тип.** Расширить `SweepRun` полем
  `metric_value: GainMeasurement | BandwidthMeasurement |
  ThdMeasurement | None`? Или `dict[str, Any]`-payload, а сами VO
  собираются где-то выше (CLI-renderer)?
  - a) discriminated union (strict, type-safe);
  - b) `dict[str, Any]` (flexible, простой serialisation);
  - c) **отдельные подклассы `SweepRun`** (`OpSweepRun`,
    `GainSweepRun`, ...) — но 4× boilerplate.
  - **Рекомендация: b** — payload в CSV/JSON выглядит как ровный
    dict, не разваливается на discriminator; типизация на уровне
    `SweepConfig` (which metric was selected).

- **Q-B: `--analysis four` без `--metric thd` — нужен ли raw spectrum
  в таблице?** Колонки бы получались странные (n_harmonics × 2 как
  одну строку?). Похоже на дублирование `--metric thd`.
  - a) разрешить `--analysis four --metric op` → ошибка
    «incompatible»;
  - b) `--analysis four` *подразумевает* `--metric thd` (auto-set);
  - **c) убрать `four` из `--analysis` options**, оставить только
    `op/tran/ac` (FOUR — это внутренний механизм для `--metric thd`).
  - **Рекомендация: c** — простота превыше формальной полноты.

- **Q-C: `SimResultsRepository` persistence — per-combination или
  агрегированно?**
  - a) per-combination (N штук `.json` файлов в
    `.efactory/sim-results/`);
  - b) один агрегированный `sweep_<TIMESTAMP>.json` со всеми rows;
  - c) **не писать SimResult вообще** (sweep — analytical step,
    не sim-results-worthy).
  - **Рекомендация: c** — sim-results storage задумывался как
    реестр одиночных симуляций для контекста агента; sweep — это
    производный analytical artifact, его лучше хранить как
    `--output-file` явно.

- **Q-D: Behaviour при failed combination.**
  - a) **продолжить sweep, в строке таблицы — пометка `FAILED:
    <reason>` в колонке metric** (текущий behaviour T004b
    Phase 1);
  - b) abort sweep on first failure (fast fail);
  - c) `--continue-on-failure` flag (default `False` — fast fail).
  - **Рекомендация: a** — наш текущий behaviour полезен (видишь
    границу convergence при sweep по Rk), не ломать backward-compat.

- **Q-E: Plot — какой именно ASCII renderer?**
  - a) reuse `plotext` через `plot_renderer.render_time_series`
    (X/Y arrays) — overload signature под numeric X (sweep param);
  - b) добавить новую функцию `render_sweep_plot` в
    `plot_renderer.py` (специально под sweep, поддерживает
    `group_by`);
  - c) отдельный модуль `sweep_plot_renderer.py`.
  - **Рекомендация: b** — concerns раздельные, чтобы T024 функции
    остались про waveform/AC, не sweep.

- **Q-F: Stdout summary при `--output-file <path>`.**
  - a) полностью молчит (только exit-code 0);
  - b) **печатает 1 строку**: `Sweep complete: N rows → <path>`;
  - c) печатает полную таблицу + дополнительно пишет в файл.
  - **Рекомендация: b** — agent friendly (можно использовать в
    chain'е), но не silent.

- **Q-G: Soft warn — нужен ли user prompt подтверждения?**
  - a) interactive `Continue? [y/N]` (не работает в headless /
    agent режиме);
  - b) **только stderr warning, продолжаем выполнение** (agent
    видит warning, сам решает);
  - c) `--confirm` flag для прерывания на warn.
  - **Рекомендация: b** — гомогенно с CLI conventions efactory
    (нет interactive prompts).

- **Q-H: Plot — log/linear X-axis для component values?**
  - a) auto-detect (если values geometric series → log; иначе
    linear);
  - b) `--plot-x-scale linear|log` flag (default `linear`);
  - **c) только linear, без флага** (component values обычно мало
    спанируют — 470/680/820/1k, не 100/1k/10k/100k).
  - **Рекомендация: c** — простота, override через explicit user
    request если возникнет.

- **Q-I: KB pitfall topic — что фиксируем заранее в
  `agent.parametric-sweep` (или подобный)?**
  - a) **только `agent.command-routing` строка**, без отдельного
    topic'а (default «достаточно `--help`»);
  - b) полноценный pitfall-topic с N² blowup warning + metric/
    analysis совместимостью;
  - c) topic в `spice.*` namespace (sweep — SPICE-specific?).
  - **Рекомендация: a** — KB topics нужны только при non-obvious
    pitfall'ах; sweep сам по себе не имеет surprise'ов сверх
    `--help` / spec'а.

- **Q-J: Расширить ли `AnalysisType` enum** в `domain/sim_results.py`
  значением `sweep`?
  - a) да, новое значение `sweep` (для consistency);
  - **b) нет** — `SweepRun` не пишется в `SimResultsRepository` (Q-C
    → c); каждая внутри-sweep'а симуляция использует свой
    AnalysisType (op/ac/tran).
  - **Рекомендация: b** — следует из Q-C → c.

### Resolved (с ответами)

Vladimir (2026-05-27): Q-H → a, остальные — по рекомендации.

- **Q-A → b**: `dict[str, float | str | None]` payload (flat,
  легко ложится в CSV/JSON, не разваливается на discriminator).
  Типизация на уровне `SweepConfig` (which metric was selected).
  Вшито в Functional Requirements + Key Entities (`SweepRun.values`).
- **Q-B → c**: `--analysis` options = `op|tran|ac` (FOUR убран,
  он — internal механизм для `--metric thd`). Вшито в FR +
  «Совместимые пары».
- **Q-C → c**: sweep НЕ пишет `SimResult` в
  `SimResultsRepository`. Persistence — через `--output-file`
  явно. Вшито в FR (НЕ ДОЛЖНА писать SimResult).
- **Q-D → a**: failed combination не аборт sweep'а — в строке
  таблицы `metric_col=None` + `error='...'`. Backward-compat
  T004b Phase 1.
- **Q-E → b**: новая функция `render_sweep_plot` в
  `plot_renderer.py` с `group_by`-параметром (concerns раздельные:
  `render_ac_sweep`/`render_time_series` — для AC/TRAN waveform,
  `render_sweep_plot` — для parametric sweep).
- **Q-F → b**: при `--output-file` stdout печатает **1 строку
  `Sweep complete: N rows → <path>`** (agent-friendly, не silent).
- **Q-G → b**: soft warn N>20 → только stderr warning, продолжаем
  выполнение (нет interactive prompts в efactory CLI).
- **Q-H → a (Vladimir выбор)**: **auto-detect X-axis scale**.
  Алгоритм: при N≥3 численных values посчитать ratios между
  последовательными; если `stdev/mean < 0.10` И `mean > 1.5` →
  log; иначе linear. N<3 → linear по умолчанию. Override —
  `--plot-x-scale linear|log` escape hatch.
- **Q-I → a**: только `agent.command-routing` строка (без
  отдельного pitfall-topic'а — sweep не имеет surprise'ов сверх
  `--help`).
- **Q-J → b**: `AnalysisType` enum НЕ расширяется значением
  `sweep` (следует из Q-C → c).

---

## Analyze (заполняется Claude)

Проход 2026-05-27, 14 issues: **2 Critical** (фиксим до
implementation, оба разрешены in-spec), **6 Warning** (нужны
явные решения, варианты предложены), **6 Note** (реализационные
guidance).

### 🔴 Critical (фиксим до implementation)

- **A1: `--metric op` совместим **только** с `--analysis op`.** В
  spec'е написано «совместимые пары» с `(op, op)`, но эта пара
  не explicit'но помечена как **единственная** для `op`-metric.
  Иначе пользователь может задать `--metric op --analysis tran` и
  получить либо ошибку, либо неожиданную попытку извлечь
  operating_points из TRAN-результата (последний sample? mean?
  → ambiguous).
  **Resolution:** добавляю в FR явный список **строго**
  совместимых пар (vs «которые работают»):
  - `--metric op` ⇔ `--analysis op` (единственная пара);
  - `--metric gain --mode small` ⇔ `--analysis ac`;
  - `--metric gain --mode large` ⇔ `--analysis tran`;
  - `--metric bandwidth` ⇔ `--analysis ac`;
  - `--metric thd` ⇔ `--analysis tran`.
  Любая другая комбинация → `typer.Exit(code=2)` с понятным
  сообщением.

- **A2: Backward-incompat output format e2e теста.** Существующий
  `tests/e2e/walking_skeleton/test_bridge_sweep.py ::
  test_bridge_sweep_two_param_combinations` ассертит формат
  `Sweep complete: 4 combinations.` + `[R1=1k C1=1u]` строки —
  это **старый T004b Phase 1 формат**. Новый tabular выводится
  иначе (`R1 C1 V(plate) V(K) I(V1)` aligned table). Если просто
  переписать вывод — тест сломается.
  **Resolution:** **переписываем тест под новый tabular format**
  в Phase A (Phase C для CLI). Tabular лучше старого формата —
  держать оба не имеет смысла. Backward-compat сохраняем на
  уровне **CLI флагов** (старый вызов `bridge sweep <project>
  --schematic <path> --param REF=v1,v2` продолжает работать без
  новых флагов; default `--analysis op --metric op` даёт OP
  sweep), но **output format меняется**.

### 🟡 Warning (обсуждаем)

- **A3: T144 root-cause fix scope creep.** Если на Phase A smoke
  выяснится, что `operating_points` пуст не из-за OPT_SE_5K_8 (T147
  закрыт), а из-за adapter parser bug — fix может потребовать
  изменений в `adapters/outbound/ngspice/`. Risk: scope разрастается
  > 50 LOC.
  **Predeclared resolution:** если fix < 50 LOC и не меняет публичные
  port interfaces — **in scope T022, Phase A**. Если > 50 LOC ИЛИ
  меняет интерфейсы — **spin-off** new T-ID, T022 продолжается
  c явным skip-условием в e2e (e.g., `pytest.skip` для OP с
  объяснением).

- **A4: SweepRun extension — backward-compat для использования
  внутри.** Добавление `values: dict[str, float | str | None]` поля
  не должно ломать existing usage `SweepRun.parameters` /
  `SweepRun.result` (если есть call-sites вне CLI).
  **Predeclared resolution:** **дополнительное** опциональное поле
  `values: dict[str, float | str | None] | None = None` без
  удаления `result`. Для `--metric op` path: `result` заполнен
  (как раньше), `values` = {col: val} (новое представление,
  derived from result). Для metric-path: `result=None`, `values`
  filled. Renderer работает с `values` — единый путь.

- **A5: Конкретный список CSV/JSON колонок per metric.** Без
  фиксации — высокий risk inconsistency между Phase B и Phase C.
  **Predeclared resolution:** в Phase A добавляю в spec явный
  mapping VO → CSV columns:
  - **gain**: `gain_db, gain_linear` (CSV); JSON добавляет
    `frequency_hz, mode, input_signal, output_signal, v_in_peak`.
  - **bandwidth**: `f_low_hz, f_high_hz, bandwidth_hz` (CSV);
    JSON добавляет `midpoint_db, ref_db, midpoint_source,
    ref_freq_hz, input_signal, passband_signal`.
  - **thd**: `thd_percent, dominant_harmonic_n,
    dominant_harmonic_percent` (CSV); JSON добавляет
    `fundamental_hz, v_in_peak, measured_power_w, signal,
    n_harmonics`.
  - **op**: dynamically — все ключи `result.operating_points`
    (union across all combinations, missing → None).

- **A6: `--output-signal` pass-through для metric mode.** Текущие
  `measure_gain` / `measure_bandwidth` / `measure_thd` принимают
  `output_signal` (default `v(load)`). `sweep --metric gain` пока
  не имеет аналогичного флага → hard-coded `v(load)` для всех
  combinations, нет escape hatch для нестандартных нод.
  **Predeclared resolution:** добавляю `--output-signal <name>`
  CLI флаг (default `v(load)`) который пробрасывается в measure_*.
  Для `--metric op` игнорируется (operating_points возвращает
  все ноды сразу).

- **A7: Warning text при N>20 — misleading hint.** В Сценарии E
  spec'a написано: «`Continue? (use --max-combinations 100 to
  silence warning)`», но `--max-combinations 100` — это default,
  не silencer. Запутывает.
  **Predeclared resolution:** упрощаю текст до:
  `Warning: N combinations (estimated ~M min runtime). Continuing.`
  Без silencer-флагов (yagni); если когда-то понадобится — заведём
  отдельный `--quiet-warnings`.

- **A8: `--plot-x-scale auto` алгоритм — non-sorted edge case.**
  Если values заданы non-sorted (`--param R=10k,1k,5k`), сырые
  ratios получаются `[0.1, 5.0]` — mean=2.55, stdev=2.45,
  stdev/mean=0.96 → linear (неверно для geometric values).
  **Predeclared resolution:** перед detection **сортировать
  values по числовому значению**, ratios считать на отсортированной
  последовательности. Альтернативно — работать в log-space:
  `log10_values = sorted([log10(v) for v in values])`,
  `diffs = [log10_values[i+1] - log10_values[i]]`, если
  `stdev(diffs) / mean(diffs) < 0.10` И `mean(diffs) > 0.18` (≈
  ratio 1.5) → log; иначе linear. Это robust к порядку и точнее
  семантически. **Беру log-space вариант.**

### 🟢 Note (к сведению)

- **A9: AnalysisType enum уже содержит GAIN/BANDWIDTH/THD/FOUR.**
  Все нужные значения уже есть (T016 + T023). Q-J → b confirmed:
  не расширяем; внутри-sweep'а измерения используют существующие
  значения.

- **A10: ports — без новых.** T022 reuses existing
  `SchematicExporter` + `Simulator` + `NetlistEditor` (последний
  только для metric path, т.к. measure_* нужен ему). Новых outbound
  port'ов нет. SweepRun, SweepConfig, SweepRow — domain/application
  VOs, не порты.

- **A11: TDD outside-in.** Phase B (use case bridge_sweep
  generalised): сначала unit-тесты на `SweepConfig` validators
  (metric/analysis compat — A1), потом на `bridge_sweep` use case
  с fake-портами (parametrize over metric types), потом e2e на
  real ngspice (минимум 1 happy-path per metric + N>cap unhappy).

- **A12: stderr/stdout convention.** Warning → stderr. Tabular
  output → stdout (or `--output-file`). При `--output-file` —
  1-line summary в stdout (Q-F → b). При `--output csv` без
  `--output-file` — CSV в stdout (для pipe'инга в `column -t -s,`
  / `awk`).

- **A13: estimated runtime calculation.** Использую rough
  `~timeout_seconds × N` (upper bound) для warning text. Не пытаюсь
  быть умным — пользователь видит `~60min`, понимает порядок.

- **A14: измерение времени runtime в практике.** OP per
  combination ~1-2s, AC sweep ~3-5s, TRAN ~5-15s в зависимости
  от t_stop. N=20 → ~1-5 минут реально (vs ~20 минут upper bound).
  В A13 объяснено почему берём upper bound.

### Resolutions inline в spec

После Analyze пробежки правки FR применены: A1 (строгие валидные
пары), A4 (доп. поле `values`), A5 (CSV columns table), A6
(`--output-signal` флаг), A7 (упрощённый warn text), A8 (log-space
algorithm), A2 (e2e test rewrite в Phase A).

---

## Phase plan (Implementation — 4 фазы TDD outside-in)

### Phase A — Diagnostic smoke + e2e test rewrite + domain VO

1. **Manual smoke T144 root-cause** (Analyze A3): rebuild
   `efactory:linux` (включая T147 OPT_SE_5K_8 fix); внутри образа
   `efactory bridge sweep se-amp-demo --schematic
   se-amp-demo.kicad_sch --param Rk=820 --analysis op`. Если
   `operating_points` непуст → T144 root-cause = OPT_SE_5K_8
   (закрыт T147), continue. Если пуст → diagnose: ngspice
   `.raw` parser или `.cir` `.print` отсутствует. Fix < 50 LOC
   in scope; ≥ 50 LOC → spin-off T-ID (Analyze A3).
2. **`SweepConfig` Pydantic VO** (`application/sweep_config.py`)
   с `model_validator` на metric/analysis совместимость (A1).
   Required-fields per metric (freq for gain/thd, f-low/f-high
   for bandwidth, v-in-peak for gain-large/thd).
3. **`SweepRow`** TypedDict / Pydantic VO (`application/sweep_
   row.py`) с явным полем `values: dict[str, float | str | None]`.
4. **Unit tests Red→Green**: 8-12 кейсов SweepConfig validators
   (5 valid pairs + 5+ invalid combos exit 2).
5. **Переписать `test_bridge_sweep_two_param_combinations`** под
   новый tabular format (A2). До Phase B Red.
6. **CHANGELOG.md** stub под [Unreleased].

### Phase B — bridge_sweep use case generalised + measure_* integration

1. **Расширить `application/bridge_sweep.py`**:
   - Новая signature: `bridge_sweep(..., config: SweepConfig,
     netlist_editor: NetlistEditor)`.
   - Internal dispatch:
     - `config.metric == 'op'` → existing `sim_run` (как сейчас),
       extract `operating_points` → `values`.
     - `config.metric == 'gain'` → `measure_gain(...)` →
       GainMeasurement → A5 fields → `values`.
     - `bandwidth` → `measure_bandwidth` analogично.
     - `thd` → `measure_thd` analogично.
   - SweepRun extension: добавляется `values` опциональное поле.
2. **Unit tests с fake-портами** (TDD outside-in, Analyze A11):
   - Happy path per metric (4×).
   - Failed combination (sim/export error) → `error='...'` +
     `values={col: None}` (Q-D → a).
   - N>cap → ValueError (or sentinel value); CLI повышает в exit 2.
3. **Integration tests с real ngspice**: 1 happy-path per metric
   (4 total) на минимальной фикстуре (voltage divider или RC
   filter — без heavy SE amp dependencies).

### Phase C — CLI sub-Typer extension + renderers + plot

1. **CLI флаги** в `bridge_sweep_cli` (`adapters/inbound/cli/app.py`):
   все из FR (`--analysis`, `--metric`, `--output`, `--output-file`,
   `--plot`, `--plot-y`, `--plot-x-scale`, `--output-signal`,
   `--max-combinations`, `--freq`, `--f-low`, `--f-high`, `--mode`,
   `--v-in-peak`). `build_cli_app` пробрасывает существующий
   `netlist_editor`.
2. **Tabular renderer** (`adapters/inbound/cli/sweep_table_renderer.py`):
   pure-functions `render_text/csv/json(rows: list[SweepRow],
   metric: str) -> str`. 12+ unit tests (per format × per metric
   matrix + edge cases: empty rows, all-None values, missing OP
   keys).
3. **Plot renderer extension** (`adapters/inbound/cli/plot_
   renderer.py` — Q-E → b): новая функция `render_sweep_plot(
   rows, x_param, y_field, *, group_by: str | None = None, x_scale:
   Literal['auto', 'linear', 'log'] = 'auto') -> str`. Algorithm
   A8 в helper `_detect_x_scale`.
4. **E2e tests на real ngspice** (Analyze A11):
   - 1 happy-path per metric (refresh existing
     `test_bridge_sweep_two_param_combinations` + 3 новых).
   - `--output csv --output-file <path>` → CSV file + 1-line
     stdout summary (Q-F → b).
   - `--output json` → valid JSON в stdout.
   - `--plot` 1-param + 2-param multi-line.
   - N>20 soft warn в stderr; N>100 hard cap exit 2; `--max-
     combinations 200` override.
   - Incompatible `--metric op --analysis ac` → exit 2.

### Phase D — Slash-команда + KB sync (Levels 1+2) + docs

1. **`docker/runtime-agent-commands/sweep.md`** (frontmatter
   `description` + `argument-hint` про абсолютные пути +
   `allowed-tools: Bash`).
2. **`docker/runtime-agent-CLAUDE.md`** — секция «Параметрический
   sweep» с примерами (3-4 use case).
3. **KB sync Level 1** (T134 правило): обновить
   `docker/runtime-agent-knowledge-base/agent.command-routing.md`
   — добавить mapping строку: `| sweep parameters & plot |
   /sweep |`.
4. **KB sync Level 2**: добавить parametrized case в
   `tests/integration/agent_kb/test_control_examples.py` —
   `(query='как сделать parametric sweep по Rk',
   expected_topic='agent.command-routing',
   expected_directive_keyword='/sweep')`.
5. **Frontmatter validation tests** для `sweep.md` (2 теста как
   у других slash-команд).
6. **CHANGELOG.md** [Unreleased] verbose entry: domain VO, use
   case generalisation, CLI flags table, renderer, plot, slash,
   KB sync, T144 closure.
7. **BOARD.md** → Doing→Done в **этом же** task-PR (project rule).
8. **Self-review** по 7-чекпойнт списку (scope/архитектура/код/
   качество/документация/соглашения/безопасность).
9. **Pre-push gates 5 зелёные** (ruff/format/mypy/lint-imports
   3/3 KEPT/pytest); `gh pr create`; closing commit с
   `[closed YYYY-MM-DD, PR #N]`; squash-merge.

### Out-of-task spin-offs (BACKLOG entries to be created)

- **T?** Adaptive sweep / golden-section search для optimisation
  (если возникнет потребность).
- **T?** Parallel SPICE execution per combination (asyncio.gather).
- **T?** Sweep по не-component параметрам (`.options`, `temp`,
  model parameters).

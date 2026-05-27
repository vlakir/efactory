# Spec: Параметрический sweep (`bridge_sweep`) с tabular output + ASCII plot

**Статус:** Draft
**Дата создания:** 2026-05-27
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
  - `--analysis <op|tran|ac|four>` (default `op`) — определяет
    физический SPICE-прогон per combination.
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
  не указан явно:
  - `--metric op` → `op`;
  - `--metric gain --mode small` → `ac`;
  - `--metric gain --mode large` → `tran`;
  - `--metric bandwidth` → `ac`;
  - `--metric thd` → `tran` + ngspice `fourier`.
  При **явном** `--analysis` несовместимом с `--metric` — error с
  объяснением.

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
    потом колонки метрики.
  - **Текстовый формат**: aligned plain-text table (без library
    `tabulate` — используем стандартный str-форматтер).
  - **CSV**: stdlib `csv.writer`, RFC 4180.
  - **JSON**: list[dict[col, value]], pretty-print (indent=2).

- **ДОЛЖНА** для plot:
  - **1-param sweep**: X = swept parameter (numeric SPICE notation
    parsed через существующий `parse_spice_number`); Y = chosen
    metric. Линейный X-axis (НЕ log) — для sweep'ов значения
    обычно дискретные, log не оправдан.
  - **2-param sweep**: multi-line plot, одна линия на значение
    второго параметра (label = `<param2>=<value>`).
  - **>2 params**: `--plot` → warning + skip plot, таблица всё
    равно строится.
  - **Raw OP без явного `--plot-y`**: `--plot` → warning + skip.

- **ДОЛЖНА** при N > soft warn limit (20) выводить warning в
  stderr с estimated runtime, не блокировать выполнение. При
  N > hard cap (100, override через `--max-combinations <N>`)
  — exit 2 без запуска.

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

- **МОЖЕТ** опционально писать `SimResult` через
  `SimResultsRepository` (T016 pattern) если caller передал
  repository — **по одному `SimResult` на combination** (или один
  агрегированный «sweep» SimResult? — clarify).

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
  расширяем: добавляем поле `metric_value: GainMeasurement |
  BandwidthMeasurement | ThdMeasurement | None = None`
  (Pydantic strict union? или просто `dict[str, Any] | None` под
  «row payload»? — clarify).

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
  open question, видимо НЕ нужно (THD уже покрыт). Уточнить в
  Clarify.

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

- *(заполнится после Clarify-прохода Vladimir)*

---

## Analyze (заполняется Claude)

- *(заполнится после Clarify)*

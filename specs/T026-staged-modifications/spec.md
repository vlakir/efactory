# Spec: Staged-модификации `.kicad_sch` при открытом KiCad

**Статус:** Analyzed
**Дата создания:** 2026-06-03
**Связанные документы:**
- `DECISIONS.md` — ADR от 2026-05-18 (kicad-python 0.7.1 покрывает только PCB; Schematic API горизонт KiCad 11/12).
- `specs/T025-schematic-visualization/spec.md` — паттерн `schematic-render: <abs>` stdout-уведомлений; container path валиден host-side через bind-mount `/efactory/projects/<project>`.
- `docs/container-boundary.md` — образ/host контракт, на котором базируется path-translation.
- `BACKLOG.md` — исходная формулировка T026 (Фаза 2).
- T168 (PR #109) — defense-in-depth в `KicadSchematicWriter` adapter (universal application).
- T169 (PR #110) — env-sanitize pattern для subprocess-тестов (релевантно если apply задействует git subprocess).

---

## 1. Overview

Когда пользователь работает с `.kicad_sch` параллельно в KiCad GUI и в
чате efactory, операции efactory (`/sim-run`, `/project-create`,
будущие LLM-driven edits) могут перезаписать файл и потерять
несохранённое состояние GUI. T026 защищает workflow: при детекте
«KiCad держит файл открытым» (через lock-файл рядом) efactory пишет
staged-версию `<orig>.kicad_sch.staged` и уведомляет пользователя;
apply staged → активный — явным действием (CLI / slash). Когда KiCad
не детектируется — writer работает напрямую как сегодня (без
overhead).

## 2. User Stories

- Как разработчик, я хочу запускать `/sim-run` при открытом в KiCad
  GUI редактируемом файле, чтобы efactory не сломал моё несохранённое
  редактирование и не показал prompt «file changed on disk, reload?».
- Как разработчик, я хочу увидеть в чате уведомление «новая
  staged-версия схемы доступна по `<abs-path>`», чтобы знать, что
  efactory отложил запись.
- Как разработчик, я хочу применить staged-версию явной командой
  (`efactory schematic apply-staged <project>` или `/schematic-apply`),
  когда я закрыл KiCad GUI и готов принять изменения.
- Как разработчик, я хочу при следующем `/sim-run` / `efactory project
  show` увидеть warning о pending staged, если забыл его применить.
- Как разработчик, я хочу при apply-staged быть защищён от silent
  data loss: если я изменил `.kicad_sch` в KiCad GUI и сохранил
  отдельно, apply должен предупредить о divergence перед overwrite.

## 3. Functional Requirements

**ДОЛЖНА:**

- Детектировать состояние «KiCad держит `.kicad_sch` открытым» через
  lock-файл, который KiCad создаёт рядом с открытым файлом.
- **Phase 0 — empirical probe lock-файла как первый шаг
  implementation** (gate-условие). Если паттерн не обнаружится →
  остановиться, обсудить план B / re-scope, не двигаться дальше.
- При детекте — писать `<orig>.kicad_sch.staged` рядом + sidecar
  `<orig>.kicad_sch.staged.meta.json` с `parent_hash` (sha256 active
  content на момент write).
- При отсутствии детекта — writer пишет напрямую (current UX, без
  staged overhead).
- Применяться универсально в `KicadSchematicWriter` adapter — все
  usage paths (`/sim-run`, `/project-create`, T079 Phase 8 LLM edits,
  T106 beautifier) защищены автоматически.
- Печатать stdout уведомления (паттерн T025):
  - `schematic-staged: <abs-path-to-staged>` (machine-readable, для
    slash command auto-discovery).
  - Human-readable одна строка для CLI пользователей.
  - **Абсолютный container path** — валиден host-side через bind-mount
    `/efactory/projects/<project>` (тот же contract что T025).
- При повторной записи staged (staged уже существует) — latest wins,
  warning `schematic-staged-overwrite: previous <hash> dropped`. Sidecar
  meta.json обновляется свежим `parent_hash`.
- При identical content (staged ≡ active ≡ new) — no-op, `schematic-staged:`
  не печатается, meta.json не обновляется.
- Per-file detection и per-file staged — для multi-sheet hierarchical
  schematics writer пишет staged для каждого изменённого файла
  индивидуально.
- Предоставить команды apply staged → active:
  - CLI: `efactory schematic apply-staged <project> [--force]
    [--accept-overwrite]`.
  - Slash: `/schematic-apply [<project>]` — без аргумента apply'ит
    pending staged для current project context; с `<project>` — для
    указанного.
- Apply (per-file): atomic `os.replace(staged → active)` + удаление
  sidecar `.meta.json`. **Без auto-commit в git** (пусть user сам
  коммитит, как с `/sim-run`).
- Apply pre-check (для каждого staged) с **разделёнными флагами**
  (W1 решение (c)):
  - Если lock-файл всё ещё существует (KiCad открыт) → reject
    с подсказкой закрыть KiCad **или** `--force` (rutinный stale-lock
    recovery, low risk).
  - Если `current_active_hash ≠ parent_hash` (active изменился
    между staged-write и apply, **реальный data loss risk**) →
    reject с warning о divergence **или** `--accept-overwrite`
    (явное согласие потерять changes сделанные в KiCad GUI).
  - `--force` **не** обходит parent-hash check; нужен отдельный
    `--accept-overwrite`. Это намеренное разделение: rutinный
    lock-cleanup ≠ accepting data loss.
- Apply outcome: возвращает `applied_count`, `skipped_count`,
  `errors_per_file`. Partial success (multi-sheet, часть apply OK,
  часть skipped) — exit 1 с детализацией в stdout. Полный успех —
  exit 0.
- Apply при отсутствии pending staged: exit 0, stdout «no pending
  staged to apply».
- На entry-points (`/sim-run`, `efactory project show`, `efactory
  project list`) — детектить pending staged через `PendingStagedScanner`
  и выводить warning с подсказкой использовать apply-staged. **Не
  применять автоматом.** Warning idempotent — не блокирует операцию.
- Добавить `*.kicad_sch.staged` и `*.kicad_sch.staged.meta.json` в
  `.gitignore` шаблона проекта.
- KB sync (L1 mandatory):
  - `agent.command-routing` table +1 row: «применить отложенные
    изменения» / «apply staged schematic» / «accept pending changes»
    → `/schematic-apply`.
  - KB topic `schematic.staged-modifications` (новый namespace
    `schematic.*` — не конфликтует с существующими `spice.*`,
    `magnetics.*`, `fem.*`, `agent.*`). Coverage: paradigm (lock-file
    detect, staged sidecar, apply pre-checks, `--force` semantics).

**МОЖЕТ:**

- Cleanup команда `efactory schematic clear-staged <project>` —
  удаляет orphan staged + meta.json без apply (для recovery после
  manual edits). Out of MVP, follow-up.

**НЕ ДОЛЖНА:**

- Polling KiCad process death (background watcher) — over-engineering.
- Auto-apply на entry-point без явного действия пользователя.
- Версионировать staged суффиксами `.staged.N` — мусор, путаница.
- Лезть в host через docker socket / privileged mounts / `pgrep`
  host-процессов — efactory работает изолированно в `efactory:linux`
  container, host-side access out-of-scope.
- Модифицировать domain entities ради этой фичи — concern
  infrastructure, место в adapter / application use case (hexagonal).
- Защищать `.kicad_pcb`, `.kicad_pro` — задача про `.kicad_sch`,
  расширение в follow-up.
- Делать 3-way merge staged ↔ active ↔ new — staged всегда полностью
  замещает active при apply (overwrite semantics; parent_hash проверка
  только warning, не merge).
- Auto-commit apply в git — user-controlled.

## 4. Success Criteria

- **AC-0 (Phase 0 gate).** Empirical probe: открыть фикстурный проект
  в KiCad 10 GUI, `ls -la` рядом с `.kicad_sch` → найден detectable
  lock-файл с воспроизводимым именем-паттерном. Если **нет** — задача
  паузится, переоткрывается clarify-pass для plan B.
- **AC-1 (open-detect + staged write).** На фикстурном проекте
  открыть `.kicad_sch` в KiCad GUI, не сохранять, не закрывать. В
  отдельном terminal: trigger efactory operation. Verify: KiCad GUI
  **не** показывает prompt «file changed on disk, reload?», unsaved
  состояние сохраняется, рядом с `.kicad_sch` появились
  `.kicad_sch.staged` + `.kicad_sch.staged.meta.json`, stdout содержит
  `schematic-staged: <abs-path>`.
- **AC-2 (closed → direct).** Закрыть KiCad. Запустить `/sim-run` на
  том же проекте. Verify: `.kicad_sch.staged` **не** создан, `.kicad_sch`
  перезаписан напрямую (current UX preserved).
- **AC-3 (apply-staged happy path).** При наличии pending `.kicad_sch.staged`,
  закрытом KiCad и неизменном active (`current_hash == parent_hash`):
  `efactory schematic apply-staged <project>`. Verify: staged → active
  atomic rename, staged + meta.json удалены, exit 0, success в stdout.
- **AC-4 (entry-point warning).** При наличии pending staged запустить
  `efactory project show <project>`. Verify: stdout содержит warning
  про pending staged + подсказку apply-staged команду. `project show`
  exit 0 (warning не блокирует).
- **AC-5 (no-op idempotence).** При identical content
  (`staged ≡ active ≡ new`): запись no-op, stdout не печатает
  `schematic-staged:`. Subsequent `/sim-run` с тем же содержимым —
  идемпотентен.
- **AC-6 (overwrite warning).** При наличии staged + новая запись с
  different content: latest wins, stdout содержит
  `schematic-staged-overwrite: previous <hash> dropped`, sidecar
  meta.json обновлён.
- **AC-7 (parent-hash mismatch reject).** Active изменён извне между
  staged-write и apply (`current_hash ≠ parent_hash`). Verify:
  apply-staged без флагов **и** apply-staged `--force` (без
  `--accept-overwrite`) → reject + warning о divergence, exit 1.
  apply-staged `--accept-overwrite` → overwrite + warning в stdout,
  exit 0.
- **AC-8 (stale-lock reject).** Lock-файл существует (KiCad open).
  apply-staged без флагов → reject + подсказка закрыть KiCad, exit 1.
  apply-staged `--force` → bypass lock-check + warning, apply
  proceeds к parent-hash check (которая может тоже зарежить без
  `--accept-overwrite`).
- **AC-9 (multi-sheet partial).** Hierarchical проект с N=3 sheets,
  два изменены, один — нет. apply-staged: applied=2, skipped=0, exit 0.
- **AC-10 (apply with no pending).** При отсутствии staged: apply-staged
  → exit 0, stdout «no pending staged to apply».
- **Pre-push 4/4 ✓** (`ruff check`, `ruff format --check`, `mypy src/`,
  `pytest`); coverage не падает ниже текущего baseline (86.31% после
  T025).
- **L1 KB sync mandatory:** `agent.command-routing` +1 row, новый topic
  `schematic.staged-modifications`.
- **L2 regression mandatory:** parametrized cases в
  `tests/integration/agent_kb/test_control_examples.py` для KB routing
  «apply staged» → `/schematic-apply`. Adapter-level tests с
  моками lock detection (Path.exists / FS injection через abstract
  port).
- **L3 smoke (optional, manual).** Реальный KiCad GUI на host:
  open → trigger → verify no prompt → close → apply. Не automated.
  Manual в acceptance reporting.

## 5. Key Entities

- **`KicadLockDetector`** (infrastructure helper в
  `adapters/outbound/schematic_kicad/lock_detector.py`): stateless
  pure function `is_held_by_kicad(path: Path) -> bool`. Проверяет
  существование lock-файла `<path.parent>/~<path.name>.lck` (KiCad
  10 pattern, **Phase 0 verified 2026-06-03 на KiCad 10.0.3**).
  В MVP content lock не парсится — только existence check.
- **`StagedPath`** (helper в `adapters/outbound/schematic_kicad/
  staged_path.py`): pure-function `staged_path(original: Path) -> Path`
  → `<original>.staged`. `meta_path(staged: Path) -> Path` →
  `<staged>.meta.json`.
- **`StagedMetadata`** (DTO в том же module): JSON-сериализуемый
  `{ parent_hash: str (sha256 hex), staged_at: ISO8601 timestamp,
  staged_by: str (efactory version), trigger: str (operation name) }`.
  Хранится в sidecar `.meta.json`. Schema-validate'нется на чтение
  через pydantic.
- **`KicadSchematicWriter`** (existing adapter, T168 PR #109): метод
  `.write(path, content)` дополняется branch'ем:
  - if `KicadLockDetector.is_held_by_kicad(path)` → compute
    `parent_hash` из `path` (если active существует), write staged +
    meta.json, emit stdout уведомления.
  - else → direct write (current behaviour).
- **`PendingStagedScanner`** (infrastructure helper в
  `adapters/outbound/schematic_kicad/scanner.py`): `scan(project_root:
  Path) -> list[StagedEntry]`. `StagedEntry` =
  `{ active_path, staged_path, meta_path, parent_hash }`. Рекурсивный
  scan по subdirs (multi-sheet).
- **`ApplyStagedSchematicUseCase`** (application use case в
  `application/use_cases/apply_staged_schematic.py`): input —
  `project_id`, `force: bool`. Logic:
  1. Resolve project root via existing project repository.
  2. Scan pending staged.
  3. Для каждой entry pre-check (lock, parent_hash) с учётом force.
  4. Atomic `os.replace(staged → active)` + delete meta.
  5. Return `ApplyStagedOutcome(applied: int, skipped: list,
     errors: list)`.
- **CLI / slash:**
  - `efactory schematic apply-staged <project> [--force]` — Click
    sub-command в `cli/schematic.py` (новый или существующий module).
  - `/schematic-apply [<project>]` — slash file
    `commands/schematic-apply.md`.
- **KB:**
  - Row в `docker/runtime-agent-knowledge-base/agent.command-routing.md`.
  - Topic `docker/runtime-agent-knowledge-base/schematic.staged-modifications.md`.

## 6. Assumptions & Constraints

- efactory работает внутри `efactory:linux` Docker container. KiCad
  GUI крутится на host. Project folder доступен из container через
  bind-mount (`~/efactory-state/projects/<X>` на host =
  `/efactory/projects/<X>` в container per `docs/container-boundary.md`).
- Lock-файл, который KiCad создаёт при открытии `.kicad_sch`, лежит
  на shared volume → виден из container через bind-mount.
- KiCad 10 создаёт **detectable** lock-файл рядом с открытым файлом —
  **проверяется empirical в Phase 0** (AC-0 gate). Если предположение
  не выдерживает probe, задача переоткрывается.
- Один пользователь = один открытый KiCad GUI = один lock per file
  (no multi-user concurrency).
- Linux primary target (тот же scope что весь efactory).
  macOS / Windows lock-file детект — out of scope.
- Apply-staged никогда не делает auto-commit в git; пользователь сам
  коммитит результат через свой обычный workflow.
- stdout abs-paths из container валидны host-side для slash agent
  через bind-mount (T025 contract).
- Concurrent staged-writes одного и того же файла (race между двумя
  одновременными `/sim-run`) — out of MVP (single-user assumption).
  Write-to-tmp-then-rename pattern для atomicity внутри одного writer
  call всё равно используется.

## 7. Out of Scope

- **IPC reload через kicad-python.** Нет Schematic API до KiCad
  11/12 (~2027–2028); territory T079 Phase 8.
- **Polling KiCad process death** в background — over-engineering,
  race conditions.
- **Auto-apply** на entry-points — только warning, не actions.
- **Multi-user / concurrent edits с разных machines.**
- **macOS / Windows lock-file детект** — Linux only.
- **Защита `.kicad_pcb`, `.kicad_pro`** — задача про `.kicad_sch`.
- **3-way merge** staged ↔ active ↔ new — overwrite semantics.
- **LLM-driven conflict resolution** между staged и concurrently
  saved active — out of scope.
- **Auto-commit apply** — user-controlled.
- **Notification past stdout** (desktop notification, OS toast).
- **Cleanup команда** `clear-staged` — follow-up, не MVP.
- **Concurrent staged-write races** одного файла — single-user MVP.

---

## Clarify (заполняется Claude)

### Resolved (Round 1)

**Q1 — Lock-file pattern KiCad 10 → empirical probe PASSED.**
Phase 0 выполнен 2026-06-03 на KiCad 10.0.3 (host:
vlakir-IdeaPad-5-Pro-14ACN6, фикстура `~/efactory-projects/
se-amp-demo/se_amp.kicad_sch`).

**Точный паттерн:** при открытии файла `<basename>` KiCad создаёт
рядом lock-файл `~<basename>.lck`. Примеры:
- `se_amp.kicad_sch` → `~se_amp.kicad_sch.lck`
- `se_amp.kicad_pro` → `~se_amp.kicad_pro.lck` (KiCad открывает
  и `.kicad_pro` тоже, если он есть).

**Содержимое lock:** JSON одной строкой
`{"hostname":"<host>","username":"<user>"}` (62 bytes на тестовой
конфигурации). Полезно для будущей cross-machine validation
(out-of-MVP), но в MVP содержимое **не парсим** — только проверяем
existence.

**Cleanup поведение (важно для дизайна):**
- `SIGTERM`: KiCad убит, **lock-файл НЕ удаляется** → stale-lock.
- `SIGINT`: KiCad игнорирует.
- `SIGKILL`: то же что TERM — lock остаётся.
- Graceful exit через File→Close / GUI X-button (untested
  программно, но per KiCad общее поведение) — lock должен удалиться.

**Implication:** stale-lock после crash / kill — **норма, не
edge case**. `--force` flag для bypass'а — критически нужен и будет
использоваться часто, не как exception. Это reinforces Q2 (b)
решение и опровергает risk «user rarely needs --force».

AC-0 PASSED, можно двигать к Phase 1.

**Q2 — Stale-lock cleanup → (b) `--force` flag.** apply-staged
`--force` bypass'ит lock-check + warning в stdout «lock-file detected,
bypassing per --force». Прозрачно, явный user intent, без timeout-
эвристики.

**Q3 — Apply без auto-commit → (a).** `os.replace` staged → active +
delete meta. Без git activity. Aligned с current `/sim-run` UX.

**Q4 — Parent-hash check → (a) sidecar meta.json.** При write staged
храним `parent_hash` (sha256 active content). При apply сравниваем
`current_hash` против `parent_hash`. Mismatch → reject без `--force`.
Защита от silent data loss.

**Q5 — Slash UX → (a) + optional `<project>`.** `/schematic-apply` без
args применяет к current project context (через
`project.current_project_context()` или его эквивалент — TBD в Phase
1). С `<project>` — для указанного проекта.

**Q6 — L3 smoke → manual.** L1 KB + L2 regression mandatory. L3
manual в acceptance reporting, не automated.

**Q7 — stdout path → container abs.** Container internal path
(`/efactory/projects/<project>/.../foo.kicad_sch.staged`) валиден
host-side через bind-mount (T025 contract). Adapter печатает container
path, slash agent читает через bind-mount.

**Q8 — Multi-sheet → per-file.** Detection и staged per-file, scanner
рекурсивный. apply-staged итерирует по всем pending в проекте,
apply'ит каждый.

**Q9 — Где живёт detector/scanner → рядом с writer.**
`adapters/outbound/schematic_kicad/lock_detector.py`,
`staged_path.py`, `scanner.py`. KiCad-specific, не generic.

**Q10 — Apply staged → application use case.**
`application/use_cases/apply_staged_schematic.py`. Orchestrates ports.
Domain не вовлечён.

### Resolved (Round 2 — Analyze findings)

**W1 — `--force` semantic split → (c).** Два разных флага:
- `--force` → bypass только lock-check (rutinный stale-lock recovery,
  low data-loss risk).
- `--accept-overwrite` → bypass parent-hash check (явное согласие
  потерять изменения в KiCad GUI, real data loss).
- `--force` **не** охватывает `--accept-overwrite`. Чтобы apply при
  открытом KiCad и diverged active — нужно **оба** флага.
- Это разделяет rutinный recovery и осознанное принятие data loss
  semantically чисто.

---

## Analyze (заполняется Claude)

### 🔴 Critical (фиксим до начала реализации)

**C1 — AC-0 gate-условие требует pre-implementation deliverable.**
Phase 0 probe — это часть **первого** implementation step, но spec
формулирует его как «если не работает → пауза». Это означает что
Phase 0 не считается «implementation» в смысле squash-PR — это
discovery, отдельный от feature commit. Решение: Phase 0 — отдельный
короткий PR (или first commit на feature branch) с результатами probe
зафиксированными прямо в этом spec'е (Resolved Q1) **до** начала
Phase 1 writer/detector реализации. Без чистого Phase 0 результата —
не начинаем Phase 1.

**Действие:** Phase 0 — отдельная мини-фаза, deliverable = добавление
в spec точного lock-file pattern (Resolved Q1 уточняется), commit
`T026 Phase 0 probe`. Если probe negative — клярифай-pass и переоценка.

### 🟡 Warning (статус)

**W1 — RESOLVED (c).** См. Resolved Round 2 выше. `--force` для lock,
`--accept-overwrite` для parent-hash. Зашито в §3, §4 AC-7/AC-8.

**W2 — `current project context` для `/schematic-apply` без args.**
Spec ссылается на `project.current_project_context()` как на
существующий helper, но не подтверждено наличие такого. Если в efactory
текущая project context не существует как concept — `/schematic-apply`
без args может быть неоднозначен.

**Действие:** Phase 1 проверяет существование current-project helper.
Если нет — `/schematic-apply` требует `<project>` arg всегда (degrade
UX), либо мы заводим current-project context отдельной задачей
(out of T026 scope).

**W3 — Sidecar `.meta.json` cleanup race.** Apply pipeline: `os.replace
(staged → active)` затем `os.unlink(meta.json)`. Если процесс упал
между этими двумя операциями — orphan meta.json без staged. Recovery:
scanner ignore meta.json без corresponding staged. Это уже учтено в
дизайне scanner'а, но **явно записать в Phase 1 spec implementation
notes**.

**W4 — KicadSchematicWriter signature change.** Universal application
в adapter означает changed signature `.write()` или его обогащённое
поведение. Существующие call sites (T025, T027, etc.) не должны
ломаться. Если signature остаётся (`write(path, content)` → None) —
OK; если меняется (возвращает `WriteOutcome` с indication было ли
staged) — backward compatibility risk.

**Рекомендую:** signature не меняется. Indication о staged-режиме —
через stdout строки (machine-readable). Internal state (`is_staged:
bool`) — не часть public adapter API.

**W5 — `efactory project show` уже существует?** AC-4 предполагает
наличие команды `efactory project show`. Quick verify — есть ли она
в текущем CLI?

**Действие:** Phase 1 — `grep` подтверждает существование. Если нет —
заменить entry-point на актуальные команды.

### 🟢 Note (к сведению)

**N1 — KB namespace `schematic.*` — новый.** Не конфликтует с
existing `spice.*`, `magnetics.*`, `fem.*`, `agent.*`. Чистый старт.

**N2 — Apply atomic via `os.replace`.** `os.rename` non-atomic в
cross-filesystem случае; `os.replace` POSIX-atomic в same-fs. Project
folder = same fs assumption (bind-mount is bind, not copy). OK.

**N3 — Phase 0 probe artifact (DONE).** Verified on KiCad 10.0.3
(date: 2026-06-03, host: vlakir-IdeaPad-5-Pro-14ACN6, fixture:
`~/efactory-projects/se-amp-demo/se_amp.kicad_sch`). Pattern:
`<dir>/~<filename>.lck`. См. Resolved Q1 detail.

**N4 — Concurrent writes single-user.** Out of scope explicitly.
Edge-case: two parallel `/sim-run` operations. Single-user → не
поддерживаем, не валим тест.

**N5 — `.gitignore` шаблон обновление.** Шаблон в `templates/` или
hardcoded в код инициализации проекта? Phase 1 проверит и обновит в
нужном месте.

**N6 — sha256 over s-expr content.** `parent_hash` считается над
**raw bytes** `.kicad_sch` (не нормализованный s-expr). Это
дисциплинированно: любая diff в whitespace тоже флагается как divergence.
Желательно — user предупреждается что reformat в KiCad GUI триггернёт
parent-hash mismatch. Документируется в KB topic.

**N7 — Phase split.** Estimated phases:
- **Phase 0 (probe, ≤1 commit):** empirical lock-file pattern verify,
  update spec Resolved Q1.
- **Phase 1 (writer + detector + sidecar, ~1 day):** adapter changes,
  L2 tests с моками.
- **Phase 2 (use case + CLI + slash + KB, ~½ day):** apply-staged
  command, slash + KB row + topic.
- **Phase 3 (entry-point warnings, ~½ day):** integration в `project
  show`, `/sim-run`, etc.

Каждая фаза = отдельный commit на feature branch (squash в один PR
per project rule).

---

### Действия перед началом Implement

1. **W1 (force-split semantic) — Vladimir выбирает (a/b/c).**
2. **W2 (current project helper) — Phase 1 verify; если нет — degrade.**
3. **W5 (project show existence) — Phase 1 grep verify.**
4. **C1 — Phase 0 separate commit, gate-условие зафиксировано.**

После этих ответов — переносим T026 из BACKLOG → BOARD `Doing`, создаём
ветку `T026-staged-modifications`, начинаем Phase 0 probe.

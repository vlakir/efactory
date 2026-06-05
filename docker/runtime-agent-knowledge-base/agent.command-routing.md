---
topic: agent.command-routing
description: Mapping typical user-request → существующая slash-команда efactory
tags: [agent, slash-commands, routing, scope]
---
# Agent command routing — типичные user-сценарии

**Правило.** Когда user формулирует задачу — **сначала проверь
есть ли уже готовая slash-команда / `efactory` CLI** для неё, и
только если нет — пиши свой код. Защита от трёх типичных ловушек:
- (1) изобретение велосипеда (matplotlib-wrapper вместо `/plot-ac`),
- (2) сканирование собственных исходников efactory (`Grep` по
  `/opt/efactory/.venv/...` → теряется время),
- (3) повтор pitfall'а уже зафиксированного в KB (`/kb-search`
  перед сложной задачей).

## Mapping table

| User формулировка | Используй |
|---|---|
| «построй график АЧХ», «АЧХ», «частотка», «bode plot» | `/plot-ac` |
| «покажи waveform», «осциллограмма», «как выглядит signal» | `/plot-tran` |
| «какой gain», «коэффициент усиления», «K» | `/measure-gain --freq <Hz>` |
| «какая полоса», «bandwidth», «-3 dB полоса» | `/measure-bandwidth` |
| «THD», «искажения», «гармоники» | `/measure-thd --freq <Hz> --v-in-peak <V>` |
| «запас по фазе», «phase margin», «стабильность петли», «PM», «loop stability» | `/measure-phase-margin [--loop-break-node <n> --loop-break-element <ref>]` |
| «как зависит X от R/C», «параметрический sweep», «варьировать Rk», «таблица gain vs ...», «sweep по 1-2 компонентам» | `/sweep --metric <op|gain|bandwidth|thd> --param REF=v1,v2,...` |
| «если поменять X на Y, как изменится gain/bandwidth/thd/PM», «what-if», «как повлияет замена R5», «сравнение до/после», «delta после правки», «как изменится запас по фазе если» | `/edit-and-resim --set REF=VALUE [...] --measure <gain\|bandwidth\|thd\|phase-margin> [...] [--loop-break-node <n> --loop-break-element <ref>]` |
| «создай проект», «новый проект <NAME>» | `/project-create <NAME>` |
| «ламповый PP», «tube push-pull», «двухтактный усилитель», «PP на 6П14П / EL84» | `/project-create <NAME>` + материализуй template `tube-pp-amp` (см. KB `spice.tube-push-pull`); Phase E добавит `[TEMPLATE]` аргумент |
| «ламповый preamp», «line preamp», «6Н2П preamp», «ECC83 buffer», «tube buffer stage» | `/project-create <NAME>` + материализуй template `tube-line-preamp` (см. KB `spice.tube-line-preamp`); Phase E добавит `[TEMPLATE]` аргумент |
| «phono preamp», «RIAA preamp», «винил preamp», «MM cartridge amp», «12AX7 phono» | `/project-create <NAME>` + материализуй template `tube-phono-riaa` (см. KB `spice.tube-phono-riaa`); Phase E добавит `[TEMPLATE]` аргумент |
| «RF preamp 6Ж38П / 6BH6 / EF190», «IF amplifier sharp-cutoff pentode», «small-signal pentode preamp», «frame-grid pentode amp», «6Zh38P preamp» | (T031 Phase 5) `/project-create <NAME>` + материализуй template `6zh38p-if-amp` (см. KB `spice.tube-rf-amp-6zh38p`). Class A resistance-coupled, Vbb=150V, Rp=10k, default op-point Ia≈3.5 mA; Phase E добавит `[TEMPLATE]` аргумент |
| «SE amp на 6П13С», «output stage без OPT», «резистивная нагрузка пентод», «6P13S beam tetrode SE», «output stage no transformer», «smoke output amp без OPT» | (T031 Phase 5) `/project-create <NAME>` + материализуй template `6p13s-se-resistive` (см. KB `spice.tube-se-resistive-6p13s`). SE на резистивной нагрузке 5kΩ (A-W3 pattern), Vbb=250V, Rk=470Ω self-bias, default op-point Ia≈37 mA. **Не production audio** — для production OPT см. `se-amp` |
| «микрофонный преамп», «mic preamp tube», «6Ж32П / EF86 preamp», «low-noise pentode preamp», «ламповый микрофонный усилитель», «динамический микрофон + лампа», «studio mic preamp» | (T031 Phase 6) `/project-create <NAME>` + материализуй template `6zh32p-mic-preamp` (см. KB `spice.tube-mic-preamp-6zh32p`). Class A common-cathode на 6Ж32П (EF86 eq.), gain 40.76 dB, BW 9.5-87.5 kHz, Vbb=250V, Ra=100k, Rk=2.7k self-bias. EF86 noval pinout готов к PCB |
| «active filter», «Sallen-Key», «LPF», «low-pass filter», «op-amp filter», «Butterworth filter» | `/project-create <NAME>` + материализуй template `active-lpf-sallen-key` (см. KB `spice.active-filter-sallen-key`); Phase E добавит `[TEMPLATE]` аргумент |
| «запусти симуляцию», «.op / .tran / .ac», «прогони netlist» | `/sim-run` |
| «ERC проверка», «прогони ERC», «check schematic», «design check», «проверь схему на ошибки», «electric rules check», «erc errors», «нарушения схемы» | (T029) `/design-check [<schematic-path-или-project-dir>]` — standalone ERC через `kicad-cli sch erc` без вызова ngspice. Exit 0/1/2 = clean/errors/infrastructure-fail. Markdown отчёт `<project>/out/erc/<ts>/report.md`. См. KB `design.erc-quality-gate` (типы violations + fix-ы) |
| «проверь сетку схемы», «check grid», «off-grid endpoints», «компоненты не на grid», «grid alignment», «components off connection grid», «pins off connection grid», «проверь что схема on-grid», «grid-check» | (T187) `/grid-check [<schematic-path-или-project-dir>]` — read-only off-grid endpoint diagnostic (KiCad connection grid 1.27 mm). НЕ блокирует sim. Exit 0/1/2 = clean/has-off-grid/infra-fail. Markdown в `<project>/out/grid-check/<ts>/report.md`, endpoints sorted by \|Δ\| desc. Built-in templates ship'ятся on-grid (T187 snap-on-write); юзкейс — hand-edited / legacy schematics. См. KB `design.grid-check` |
| «покажи схему», «открой схему», «отрисуй проект», «как выглядит схема», «render schematic», «отобрази .kicad_sch» | (T025) `eog <schematic-render path> &` через Bash — Eye of GNOME откроется на host через X11. Auto-show отрабатывает в `/sim-run` / `/project-create` (см. `schematic-render: <abs>` строки в stdout); если пользователь просит повторно — `eog` на сохранённом пути. Не `xdg-open` (MIME db не настроен) |
| «покажи результат», «покажи график», «покажи в окне», «посмотреть симуляцию», «show sim result», «как выглядит результат» | (T025 dual-mode) для AC sweep — `/plot-ac`, для transient — `/plot-tran`. Обе slash-команды **уже** передают `--output /tmp/plot-*.png`; распарси `plot-render: <abs path>` строку и запусти `eog <abs path> &` для окна на host через X11. **НЕ пиши** ad-hoc matplotlib / Python скрипт — `bridge plot {ac,tran} --output` уже это делает. Текстовые measure-результаты (`/measure-gain` и т.п.) описывай словами |
| «покажи в графическом окне», «открой график», «графически» | то же что выше — `/plot-ac` / `/plot-tran` уже передают `--output` + дают `plot-render: <path>` строку + eog; повторно или explicit — `bridge plot {ac,tran} --output <abs.png>` + `eog <abs.png> &` (НЕ matplotlib ad-hoc) |
| «покажи всё», «открой проект», «дай посмотреть» (ambiguous) | уточни у пользователя что именно: схему, результат симуляции, plot, или текстовые measure-результаты. Не угадывай |
| «переключись на проект <NAME>» | `/project-use <NAME>` (display-only) |
| «покажи состояние проекта», «статус проекта», «что в проекте <NAME>», «show project status», «project info», «summary проекта <NAME>» | `efactory project show --name <NAME>` (T026: stdout также содержит warning `schematic-staged-pending: N file(s)` если есть отложенные `.kicad_sch.staged` — **обрати внимание и предложи `/schematic-apply`**). Не подменяй CLI ad-hoc обзором по `ls /workspace/<NAME>/` — потеряешь T026 warning'и и phase-статусы |
| «список проектов», «какие проекты есть», «list projects», «все мои проекты» | `efactory project list` (T026: per-project маркер `[N pending staged]` указывает где есть отложенные изменения схемы — не игнорируй) |
| «применить отложенные изменения», «apply staged schematic», «принять staged», «накатить staged kicad_sch», «accept pending changes» | (T026) `/schematic-apply <project>` или `efactory schematic apply-staged <project> [--force] [--accept-overwrite]`. `--force` bypass'ит stale-lock (KiCad crash → `~<name>.lck` остаётся, норма); **отдельный** `--accept-overwrite` для parent-hash mismatch (active изменён в GUI после staged-write — real data loss). См. KB `schematic.staged-modifications` |
| «добавь модель лампы», «нет такой лампы в библиотеке», «extract из datasheet», «vision datasheet PDF лампы», «6Ж38П / 6П13С / редкая советская лампа», «fit Koren parameters», «подбери параметры лампы», «add tube model from PDF» | (T031) `/tube-add-from-datasheet <part>` — vision-extract IV-точек анодных характеристик из datasheet PDF/PNG → fit Koren / modified-knee / modified-cutoff (T182 auto-default per tube_type) → `.lib` в user overlay (`$XDG_DATA_HOME/efactory/models/tubes/custom/`) + KB topic `tubes.<part>`. См. KB `tubes.curve-fitting` (pipeline + JSON schema) и `tubes.formula-variant-choice` (когда override default) |
| «у меня уже есть JSON с точками лампы», «fit из готовых measurements», «измерил лампу на стенде → SPICE модель», «tube IV points to .lib» | (T031/T182) `efactory tube fit-from-points <SPICE_ID> --type {triode\|pentode} --points <file.json> [--out DIR --include-vct --header-type tetrode --kg2-ratio FLOAT --force --formula-variant auto\|koren-canonical\|koren-modified-knee\|koren-modified-cutoff]` — pure compute. Default `--formula-variant auto` → pentode=modified-knee, triode=canonical. См. KB `tubes.formula-variant-choice` для override решений (power triode 300B → modified-cutoff, etc.); `tubes.curve-fitting` для JSON-схемы |
| «импортируй SPICE модель», «добавь модель BJT/MOSFET/JFET/op-amp/diode», «вставь 2N3904 из URL», «add IRF540 model», «import vendor SPICE», «модель из TI / Vishay / ON Semi / Microchip», «PSpice .lib import» | (T030) `/spice-import-url <URL>` — direct-URL HTTP download → classify (.SUBCKT / .MODEL TYPE → BJT/JFET/MOSFET/DIODE/OPAMP) → PWRS conversion → install в `<user_library_root>/<category>/<vendor>/<PART>.lib` с inline headers (vendor/source_url/sha256/imported_at/subcategory) → per-class ngspice OP smoke → KB topic `spice.<vendor>.<part>`. Exit 0/1/2 = ok/domain-fail/infra-fail. Auth-walled vendors (TI PSpice SSO .zip): user качает руками → `efactory spice import-file <path> --vendor=ti` (тот же pipeline). Flags: `--vendor`, `--force` (duplicate), `--skip-smoke`, `--dry-run`, `--category/--subcategory` (override эвристики). См. KB `spice.import-pipeline` (full pipeline + pitfalls + vendor mapping table) |
| «300B / 2A3 / power triode strong cutoff fit», «cutoff region не точно у триода», «модель глубокого cutoff power triode» | (T182) `efactory tube fit-from-points <NAME> --type triode --points <file.json> --formula-variant koren-modified-cutoff` — sigmoid-modified cutoff term для резче strong-cutoff edge. **НЕ комбинируй с `--include-vct`** (semantic overlap, use case rejects). См. KB `tubes.formula-variant-choice` §когда modified-cutoff |
| «сохрани этот проект как шаблон», «оформи как template», «promote project as template», «сделай чтобы потом ещё проекты из этого создавать», «save as reusable template» | (T177) `efactory template create-from-project <project_name> --name <template-name> [--summary "..."] [--description "..."] [--force]` — promote existing project в **persistent user overlay** (`$EFACTORY_USER_TEMPLATES_ROOT` или default `~/.local/share/efactory/templates/`). Изнутри `efactory:linux` агент-контейнера: bind-mounted в `/efactory/data/templates/` (persistent через `efactory-up`). Pre-T177 agent писал в transient `/opt/efactory/data/templates/` (теперь deprecated). См. KB `tubes.curve-fitting` секция «Persistent agent overlay» |
| «экспорт схемы для статьи», «publication-grade schematic», «SVG/PDF/PNG @ 300 DPI», «схема в LaTeX figure», «color и BW версии схемы», «render схемы для печати», «publication export schematic» | (T035 Phase 4.1) `/export-schematic-publication <PROJECT_SLUG> [--multi-sheet-mode per-sheet\|combined] [--lang ru\|en]` — publication-grade schematic: SVG (vector) + PDF (vector) + PNG @ 300 DPI × color + bw в `<project>/out/publications/<ts>/schematic/`. README.md на `--lang` со списком файлов. `combined` mode добавляет multi-page PDF. Auto-detect root `.kicad_sch` (по `<name>.kicad_sch` либо единственный). См. KB `design.export-publication` |
| «отчёт о симуляции для статьи», «sim report для публикации», «Markdown отчёт симуляции», «publication sim report», «отчёт с графиками TRAN/AC для draft статьи» | (T035 Phase 4.2 MVP) `/export-sim-report <PROJECT_SLUG> [--lang ru\|en]` — publication-grade Markdown sim-report. **⚠️ Текущий MVP ограничен metadata-секцией:** TRAN/AC/parametric plots ОТСУТСТВУЮТ (заблокировано T190 raw waveform persistence + T191 `--rerun` integration). До закрытия: для production-grade графиков workflow остаётся manual через `/sim-run` + screenshot `bridge plot`. После T190+T191 команда даст полный отчёт с PNG @ 300 DPI. См. KB `design.export-publication` |
| «как обойти X», «уже было / похоже на pitfall» | `/kb-search <query>` ПЕРЕД исследованием |
| «сохрани lesson», «потом не забыть» | `/kb-add <topic>` |

## Anti-patterns (NE делай)

- **Ad-hoc matplotlib script для визуализации.** Когда нужна
  графика waveform / АЧХ — у тебя уже есть `bridge plot {ac,tran}
  --output <abs.png>` (T025). Не пиши Python в `/tmp`, не вызывай
  `uv add matplotlib`. Если CLI surface действительно отсутствует
  для запрошенного вида output (не plot, не schematic) — **сообщи
  пользователю, что это feature gap** (зафиксируй в BACKLOG); не
  изобретай ad-hoc решение без явного его согласия.

- **`xdg-open`.** MIME database в `efactory:linux` не настроена,
  `xdg-open` уходит в браузерный fallback. Используй прямо `eog
  <png> &` (T025).

- **Сканирование собственных исходников efactory.** Если задача
  кажется не покрытой `efactory --help` — сначала `/kb-search`,
  потом спроси пользователя, **затем** уже Grep по `/opt/efactory`.

## Special cases

- **«посчитай leakage inductance OPT»** — не пиши свой Erickson,
  есть `application.analyze_interleaved_leakage` через
  `AnalyticalLeakage` adapter. См. KB `magnetics.pyom-leakage-broken`
  (Erickson — primary path, PyOM mesh broken).

- **«saturable transformer THD sweep»** — есть use case
  `application.analyze_distortion_spectrum` (T131). Не путать с
  `/measure-thd` (single point, без saturable injection).

- **«FEM cross-check магнитного сердечника»** — есть use case
  `application.mag_verify_field` (T113). Для E-core OPT сразу
  планируй 3D — см. KB `fem.2d-planar-zhang-gap`.

- **«what-if на схеме с несколькими метриками сразу»** — `/edit-and-
  resim --set R1=10k --set C3=470n --measure gain --measure thd`
  один проход вместо двух cycle'ов /measure + /edit. Strict baseline:
  если baseline-measure упало, edits НЕ применяются. Для one-shot
  (1-5 edits + 1-3 метрики). Для диапазона значений → `/sweep`
  (T022), не `/edit-and-resim`.

- **«как изменится phase margin после правки feedback резистора»** —
  `/edit-and-resim --set R_fb=47k --measure phase-margin
  --loop-break-node <node> --loop-break-element <ref>` (T153 B.7).
  Edge-pair либо explicit (обе опции), либо auto-detect (ни одной).
  Можно комбинировать с другими метриками одной командой:
  `--measure gain --measure phase-margin --freq 1k`. **Per-topology
  canonical breaks** (ADR-T153f + ADR-T153g, KB `spice.feedback-break-
  point`): op-amp inverting → `(vout, R_fb)` (low-Z driver); tube NFB
  SE → `(sec_a, C_fb)` (OPT secondary, auto-detect fails — explicit
  required); BJT CE → `(collector, R_C)` (preview, fixture TBD).
  Default `--injection-method middlebrook-voltage` корректно даёт
  T_loop на правильном break point; `tian` — universal на op-amp но
  degenerate на tube NFB.

- **«phase margin auto-detect отклонил edge / NoUnityGainCrossover»** —
  default `--injection-method middlebrook-voltage` даёт `T_v`, не
  `T_loop` (для op-amp |T_v| < 1 во всём диапазоне → no crossover, это
  ожидаемая calibration ситуация Phase B.4, не bug). Попробуй
  `--injection-method tian` (double V+I) или
  `--injection-method rosenstark-return-ratio` (open + short break).
  Если auto-detect отклонил edge с низкой confidence — задай пару
  `--loop-break-node <node> --loop-break-element <element_ref>`
  вручную (edge-pair однозначно идентифицирует один wire в graph).

- **«ngspice OOM / memory growth на TRAN»** — см. KB
  `spice.ngspice-version-upgrade` (контейнер использует 45.2 из
  source, apt 42 имел XSPICE TRAN memory leak). На свежесобранном
  образе проблемы быть не должно; если есть — пересобрать через
  `./scripts/efactory-build-dev`.

## Когда лезть в исходники efactory

Только если: (а) `/help` + `/kb-search` ничего не нашли, (б)
у `efactory --help` нет нужной subcommand, и (в) задача
существенная (не одноразовый probe). Иначе быстрее задать
вопрос user'у «не входит ли это в efactory infrastructure?»

**См.** `runtime-agent-CLAUDE.md` § «Custom slash-команды
efactory».

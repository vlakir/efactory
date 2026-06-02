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
| «active filter», «Sallen-Key», «LPF», «low-pass filter», «op-amp filter», «Butterworth filter» | `/project-create <NAME>` + материализуй template `active-lpf-sallen-key` (см. KB `spice.active-filter-sallen-key`); Phase E добавит `[TEMPLATE]` аргумент |
| «запусти симуляцию», «.op / .tran / .ac», «прогони netlist» | `/sim-run` |
| «покажи схему», «открой схему», «отрисуй проект», «как выглядит схема», «render schematic», «отобрази .kicad_sch» | (T025) `xdg-open <schematic-render path> &` через Bash — `eog` откроется на host через X11. Auto-show отрабатывает в `/sim-run` / `/project-create` (см. `schematic-render: <abs>` строки в stdout); если пользователь просит повторно — `xdg-open` на сохранённом пути |
| «покажи результат», «покажи график», «посмотреть симуляцию», «show sim result», «как выглядит результат» | для AC sweep — `/plot-ac`, для transient — `/plot-tran`. Если результат — plot PNG в stdout, открой через `xdg-open <path> &` (как для схемы). Текстовые measure-результаты (`/measure-gain` и т.п.) описывай словами |
| «покажи всё», «открой проект», «дай посмотреть» (ambiguous) | уточни у пользователя что именно: схему, результат симуляции, plot, или текстовые measure-результаты. Не угадывай |
| «переключись на проект <NAME>» | `/project-use <NAME>` (display-only) |
| «как обойти X», «уже было / похоже на pitfall» | `/kb-search <query>` ПЕРЕД исследованием |
| «сохрани lesson», «потом не забыть» | `/kb-add <topic>` |

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

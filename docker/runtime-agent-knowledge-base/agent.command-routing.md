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
| «как зависит X от R/C», «параметрический sweep», «варьировать Rk», «таблица gain vs ...», «sweep по 1-2 компонентам» | `/sweep --metric <op|gain|bandwidth|thd> --param REF=v1,v2,...` |
| «если поменять X на Y, как изменится gain/bandwidth/thd», «what-if», «как повлияет замена R5», «сравнение до/после», «delta после правки» | `/edit-and-resim --set REF=VALUE [...] --measure <gain\|bandwidth\|thd> [...]` |
| «создай проект», «новый проект <NAME>» | `/project-create <NAME>` |
| «запусти симуляцию», «.op / .tran / .ac», «прогони netlist» | `/sim-run` |
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

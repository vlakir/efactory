# T195 — FULL MANUAL: предложение переноса

База раунда: `ff11572f0308dcb7ddfe158a2222f2fe318647e1`.
`5afd093e388d5f508e9ef4d84093f7aaa4716792` — только comparison main,
не основание для rebase/merge. Исходная T036 исторически Done (PR #129),
но это не приёмка текущего source snapshot: код doctor и его тесты сохраняются.

## Фактический маршрут

Установлен dreamteam 2.0.0. Первый настоящий `dreamteam update --dry-run .`:
rc=1, stdout=0 строк, stderr=1 строка; проверенные категории диагностики
`unsupported`, `legacy`, `claude`. Вывод захвачен в RAM, raw не опубликован.
Повтор дал тот же результат. Это НЕ CLI migration success.

Штатный `dreamteam init <fresh ephemeral> --defaults --data project_name=efactory
--data language=ru --data package_manager=uv` завершился rc=0; render содержит
28 реальных файлов. Он нужен только для inventory/методики: business seeds
`src/main.py`, `tests/test_main.py` в efactory НЕ переносятся. Нет fake base,
`--force`, `--auto`, нового сервера или смены dependencies/CI.

## Source → active native map

| Source | Active target / решение |
|---|---|
| `CLAUDE.md` §§1–201 | `AGENTS.md`: существующие проектные planning/Git/review правила сохраняются; устаревшие имена клиента заменяются только в методике |
| `CLAUDE.md` §§203–308 | `AGENTS.md`: buildx/OOM и KB L1/L2/L3 сохранены; ссылка KB prompt должна вести к существующему `docker/runtime-agent-CLAUDE.md`, а не выдуманному AGENTS runtime |
| `.opencode/agents/{9 roles}.md` | Все девять сохраняются; tech-lead primary + question allow; остальные question deny; architect/reviewer deny-by-default, без edit/bash/exec, открыты только read/search и командная связь |
| `opencode.json` | Существующий schema/plugin 0.18.0/default tech-lead/instructions сохраняются; модели, providers, MCP не добавляются |
| `.opencode/team-roles.md` | Сохранить meaningful orchestration, убрать безусловный restart: active server 4096 не рестартовать, activation pending до безопасной границы новой сессии |
| `.opencode/ensemble.json` | Сохранить mergeOnCleanup=false и личный выбор моделей |
| `.copier-answers.yml` | После review: compatible native2.0.0; честная manual provenance в manifest+DECISIONS, исходная1.5.1 запись в byte-original archive; поля проекта/автора сохраняются, не defaults из ephemeral render |
| `CLAUDE.md` final | После независимого review+byte-original archive root legacy файл удалён полностью, включая временный development marker; unique knowledge active AGENTS; runtime CLAUDE untouched, CLI success не заявляется |
| tracked `.claude/**` | В точной базе отсутствуют (`git ls-tree` пуст). Не объявлять несуществующие inputs перенесёнными; untracked не копировать |
| runtime `docker/runtime-agent-*`, `scripts/*claude*` | Отдельный business runtime-контур, в этой migration-only задаче не деактивировать/не переименовывать; ссылки dev-методики сохраняют фактический runtime |
| root docs / CONCEPT | CONCEPT побайтово неизменен. README только development canonical refs + T195 note; BOARD только T195 Doing; DECISIONS только T195; BACKLOG и CHANGELOG без массовой замены истории |
| managed templates / hook / guard | Сохранить source custom templates и pre-push behavior; native guard перенесён как локальный инструмент, только комментарий о source cov80 уточнён. Не переносить generic gate change, Python3.14, coverage addopts или business placeholder seeds |
| `specs/design-brief-template.md` | Создан active native brief: все семь смысловых секций, результат/итерации, platform-appropriate prototype и acceptance; designer/team-roles ссылаются на него |

## Обязательные overrides

Python 3.13 scientific exception (ADR 2026-05-20), uv.lock и pyproject не менять.
Канонический gate — `.pre-commit-config.yaml`: ruff check ., ruff format --check .,
mypy src, lint-imports, pytest (исходный coverage>=80%). Не заменять generic
template четырьмя проверками. История disabled review bots и closing BOARD после
реального PR number сохраняется. CONCEPT принимается как существующее ТЗ v5.1,
не переделывается под шаблонные заголовки. Project memory — внутри репо.

## Review/control barrier

До review provenance и CLAUDE.md не менялись. Reviewer
`reviewer-t195-r1` фактически сообщил: read/glob/grep/team доступны,
edit/bash/exec отсутствуют. Это runtime observation, не только декларация YAML.
Architect-t195-control отдельно сообщил фактические read/search/team tools,
без edit/write/bash/exec/question; это observation, не destructive-denial probe.
Активная сессия writer остаётся devops;
новые конфиги не выдаются за уже загруженные текущим server 4096.

Acceptance T195: полный actual28+custom inventory, private byte-originals,
meaningful source→native map без потерь, independent review до final barrier,
повтор обычного plan с честным residual diff, baseline/post canonical gates,
source business/deps/CI/CONCEPT неизменны. Checkpoint не равен acceptance/Done.

Оба independent barrier пройдены reviewer-t195-r1 (сначала actual controls/map,
затем проверка отсутствия unique info в временном root marker) ДО окончательной
деактивации. Это не финальная приёмка. Byte-original проверку выполнил writer;
lead/reviewer не приписывается independent byte verification private archive.

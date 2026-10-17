# T195 — результат migration-only writer

## Что действительно сделано

FULL MANUAL на точной source базе `ff11572f0308dcb7ddfe158a2222f2fe318647e1`.
Main `5afd093e388d5f508e9ef4d84093f7aaa4716792` только сравнивался, не вливался
и не использовался для rebase. В comparison BOARD/BACKLOG/CHANGELOG max T194;
T195 выделен следующей задачей. T036 historical Done/PR129 не подменяет приёмку
текущего source snapshot; весь doctor business/test/runtime сохранён.

Initial CLI2.0.0 ordinary dryrun rc1 unsupported legacy; raw stdout/stderr только
RAM. Actual28 canonical inventory получен штатным fresh ephemeral render rc0.
`manifest.json` содержит все28 paths, custom/root inputs и42 path-specific
dispositions. В target не создавались generic src/main.py/tests/test_main.py.

Нативные controls9roles реализованы; question allow только primary tech-lead,
deny у8специалистов. Architect/reviewer denydefault + read/search/team allowlist.
Фактические R/O tools наблюдены отдельно reviewer-t195-r1 и
architect-t195-control (worktree:false), не объявлены проверкой только по YAML.
Новый primary native question live не вызывался ради smoke; activation нельзя
считать уже выполненной. Existing server4096 не рестартовал, новый не запускал.

Source unique knowledge в AGENTS сохранён: Python3.13 scientific exception,
review/closing, buildx/OOM, KB L1/L2/L3 и фактический runtime CLAUDE reference.
Добавлены native memory/CONCEPT/mutex правила, designer brief, локальный
pytest-guard (исходные CI/hooks/pytest defaults не менялись).

Два независимых review barrier соблюдены: actual native mapping/controls ДО
provenance, затем отсутствие unique info в root marker ДО окончательной
деактивации ROOT CLAUDE.md. Docker runtime CLAUDE не тронут.
Answers фиксирует compatible template2.0.0; manual provenance — manifest/ADR,
не ложный automated migration success. Redundant custom answer metadata
сохранена смыслом в manifest/ADR, а не оставлена под future CLI stripping.

## Source preservation и private originals

НОВЫЙ durable private artifact:
`/home/vlakir/.local/share/dreamteam/migration-20261016/efactory-T195-devops-r1-_pbzpz35`.
38 tracked byte-originals сохранены ДО изменения/deactivation, root/directories
0700, files0600. SHA256 совпадают с manifest. Проверку выполнил writer;
независимую byteverification лиду/reviewer не приписываю. Безопасный proof —
`archive-verification.json`. Untracked автоматически не копировал, raw secret/
settings/env/key/MCP values не читал/не публиковал. Tracked `.claude/` source0.

`git diff <base> -- src tests docker efactory-up Dockerfile Dockerfile.libs
pilot.Dockerfile hatch_build.py pyproject.toml uv.lock CONCEPT.md .github
.pre-commit-config.yaml hooks/pre-push specs/spec-template.md .gitignore` пуст.
Immutable CONCEPT побайтово сохранён. Общие root journals: только T195.

## Full ordinary plan/repeat, не fake noop

После final deactivation обычный `dreamteam update --dry-run .` дважды rc0,
stderr0; планы identical. Actual28: **26 unchanged, 2 ADD, 0 removed,
0 conflicts**, без методических MODIFY/loss. Residual ADD — только generic
`src/main.py` и `tests/test_main.py`, сознательно не материализованы в существующем
hexagonal приложении. Полного template noop нет, требованием человека он не
объявляется. FULL MANUAL не выдаётся за automated AC10. Raw CLI diff не сохранён;
полный whitelist per-path plan/repeat — `validation.json`.

## Gates: локальная диагностика и обязательная srv-приёмка

Own Python3.13.16 env, точные locked deps, editable project установлен с
`HATCH_BUILD_HOOKS_ENABLE=false`, чтобы bootstrap не ставил shared git hook.
Before-bootstrap shared-hook hash не захватил, обратного не утверждаю.
IDE build tool не смог проверить own проект (не открыт в IDE); unrelated calque
не трогал. Canonical source CLI gates выполнены напрямую из own env.

| Gate | Baseline | После migration |
|---|---|---|
| ruff check . | PASS | PASS |
| ruff format --check . | PASS209files | PASS209files |
| mypy src | PASS208sourcefiles | PASS208sourcefiles |
| lint-imports | PASS3contracts | PASS3contracts |
| full pytest, original cov80 | rc1,72fail/2516pass/10skip/1xfail | rc1, те же72 failed nodeids |

Coverage baseline/post **87.28%** (порог80 достигнут), но pytest FAIL остаётся
FAIL. Representative existing failure: kicad-cli exit3 «Не удалось загрузить
схему» в export/render pipelines. Полные exact failed-nodeid lists до/после
сравнены, identical; counts/coverage/rc/attribution — `validation.json`.
Диагностический -x/no-cov probe НЕ канонический gate; один первоначальный full
run tool timeout120s НЕ завершённый baseline. Канонические completed baseline
и post шли последовательно под `/tmp/efactory-pytest-1000.lock`, без maxfail/
skip/failure suppression. Business fixes/ослабление tests не выполнялись.

**Не push, не PR, не merge, не Done.** Первоначальный вывод writer о блокировке
любой remote publication только по локальным72fail был преждевременным:
глобальная более новая srv-policy прямо применяется к efactory и к этой старой
source базе без своего YAML. Обязательный путь — light локально, штатная
sandbox-доставка, full exact-final-SHA gates на srv ДО merge. Локальный72fail
— диагностика несовпавшей среды, а не разрешение bypass hooks/redpush или
замена штатной srv-приёмки. Supported dispatcher exact-checkout/gate override
подтверждён help; итоговый lead SHA, staging/cache/queue и запуск согласуются
после интеграции. См. `DIAGNOSIS.md` и `diagnosis.json`:71load-parse и1отдельный
empty-page PDF случай, не голословное «все72одинаковые». Никакого main CI/business
кода в source не переносилось. Локальный checkpoint — сохранение работы,
не финальная приёмка; T195 остаётся Doing.

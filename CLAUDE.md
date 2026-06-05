# Project rules for Claude

Этот файл — проектные правила для Claude (Claude Code). Глобальные
правила (`~/.claude/CLAUDE.md`) применяются всегда; здесь — только то,
что специфично для конкретного проекта.

## Что прочитать в начале сессии

1. `CONCEPT.md` (если есть) — изначальное видение проекта,
   immutable документ. Полезен как точка опоры через месяцы.
2. `README.md` — текущее описание / quick start / status проекта.
3. `DECISIONS.md` — архитектурные решения, которые уже приняты.
4. `BACKLOG.md` — что лежит в очереди.
5. При работе над крупной фичей — соответствующий `specs/T<NNN>-*/spec.md`.

## Ритуал составления `CONCEPT.md` (для нового проекта)

В начале нового проекта Claude помогает Разработчику составить
`CONCEPT.md` — immutable документ начального видения. Это ритуал
встречных вопросов, аналогичный `clarify` для спеки:

1. Разработчик пишет первый набросок (или формулирует идею).
2. Claude задаёт встречные вопросы по слепым зонам:
   - **Цель:** какую боль / задачу проект решает?
   - **Пользователь:** кто, в каком контексте?
   - **Ключевая функциональность:** MVP-минимум vs nice-to-have?
   - **Out of scope:** что СОЗНАТЕЛЬНО не делаем? (главный раздел
     для защиты от scope creep).
   - **Ограничения и догадки:** платформа, стек, нагрузка,
     ассумпции.
3. Ответы вшиваются в `CONCEPT.md`, проставляется дата создания.
4. **После фиксации `CONCEPT.md` не редактируется.** Текущее
   состояние ведётся в `README.md`. Если концепция кардинально
   меняется (rare, pivot) — добавляется `concepts/v2-...md`,
   `v3-...md` (ADR-pattern, но для концепций).

Заполнение `CONCEPT.md` — на этапе создания проекта через
`dreamteam init` (Claude задаёт встречные вопросы) или позже,
вручную.

## Описание проекта

Система сквозного проектирования РЭА с использованием ИИ

## Стек

<!-- Языки, фреймворки, ключевые библиотеки, целевая платформа. -->

**Базовый стек шаблона (для Python-проектов):**
- Python 3.13+ (`requires-python` в `pyproject.toml`). 3.14 рассматривался
  как первичная версия, но отвергнут 2026-05-20 (ADR в `DECISIONS.md`) —
  scientific Python ecosystem (femmt, pyopenmagnetics, scipy 1.12, ...)
  пока не догнал до 3.14: wheel'ов нет, sdist падает на upstream-багах.
  Возврат к 3.14 — после стабилизации scientific stack.
- Менеджер зависимостей и окружений: **`uv`** (выбран
  при `dreamteam init` через prompt `package_manager`; альтернативы:
  `uv` / `poetry` / `pdm` / `hatch` / `pip`).
- Линтер: `ruff` (правило `select = ["ALL"]` с фиксированным `ignore`).
- Тип-чекер: `mypy` с `mypy_path = "src"`.
- Тестовый стек: `pytest` + `pytest-cov` + `pytest-asyncio`. Coverage
  threshold ≥ 80% line coverage на `src/` (`--cov-fail-under=80`
  в `[tool.pytest.ini_options]`).
- **Корень исходников — `src/`** (всегда, во всех проектах).
- Тесты — в `tests/` в корне (в ruff `exclude`, но pytest их
  находит через `testpaths = ["tests"]`).

**Типичные команды (для выбранного `uv`):**
- `uv sync` — поставить зависимости (создаст `.venv` при первом запуске).
- `uv add <pkg>` / `uv add --dev <pkg>` — добавить runtime / dev зависимость.
- `uv run python ...` — запустить под `.venv` без активации.
- `uvx <tool>` — запустить CLI-инструмент без локальной установки.

Перед каждым `git push` обязательно **четыре** проверки с 0 ошибок:
1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run mypy <код>`
4. `uv run pytest` (включает coverage threshold ≥ 80%).

**Запускать одной цепочкой**, чтобы fail на любом шаге прерывал
commit:

```bash
uv run ruff check . && \
uv run ruff format --check . && \
uv run mypy <код> && \
uv run pytest && \
git add -A && git commit -m "..." && git push
```

**Catch-it-at-the-output:** если в выводе предыдущей команды
видишь `FAILED`, `Error`, `1 failed` или подобные маркеры —
**не двигайся дальше**, проверь причину. И не глуши exit-code:
`pytest | tail -5` возвращает exit-код `tail`, не `pytest` —
fail незаметно проскочит в `git commit`.

Никаких `# noqa` / `# type: ignore` / расширений `ignore`-секций
без явного обсуждения с Разработчиком. Подробно — в глобальном
`~/.claude/CLAUDE.md`, разделы «Линтеры» и «Тестирование».

## Git workflow

Базовые правила процесса (применяются в этом проекте всегда):

- **Задачи нумеруются.** Каждая запись в `BOARD.md` / `BACKLOG.md`
  имеет ID `T<NNN>`; ветка — `T<NNN>-<slug>`; PR — `T<NNN>: <title>`.
  Исключение — методические PR, меняющие сами правила (без `T`-ID).
- **Прямой push в `main` / `master` запрещён.** Любое изменение — через
  feature-ветку и PR/MR.
- **Один PR — один коммит.** На feature-ветке можно коммитить как
  удобно для работы, перед merge — squash.
- **Каждый PR проходит code review** перед merge. По умолчанию —
  Claude (self-review с чеклистом: scope / архитектура / код /
  линтеры / документация / соглашения / безопасность). Иногда —
  Разработчик.
- **Сторонние review-боты отключены** (CodeRabbit + Qodo Merge,
  решение 2026-05-21 в `DECISIONS.md`): `.coderabbit.yaml` +
  `.pr_agent.toml` в репо имеют `auto_review.enabled: false` /
  `handle_pr_actions = []`. Primary review path — self-review +
  `/ultrareview` on-demand для важных PR'ов.
- **`/ultrareview` — on-demand external review**, не mandatory.
  Free tier — **3 runs lifetime per account** (one-time allotment,
  без renewal); после исчерпания — **$5–20 per run** usage credits.
  При нашем PR-throughput (10-20/мес) mandatory означало бы $50-400/мес
  поверх Pro/Max подписки — экономически не оправдано.
  Используется выборочно на важных PR (cross-cutting refactor,
  security-sensitive, milestone-фазы). Для маленьких PR (методических,
  docs, single bug-fix) — self-review достаточно. Quota check —
  `/usage-credits` в Claude Code CLI перед запуском.
- **`/ultrareview` findings → PR comment manually.** Когда Vladimir
  запускает `/ultrareview <PR#>`, findings приходят в наш чат
  (JSON с severity/file/comment). Claude обрабатывает каждое (учесть
  / отбросить / отложить с обоснованием), фиксирует решения, и
  публикует summary в `gh pr comment <PR#>` для historical traceability
  на PR-странице (auto-post в GitHub нет, подтверждено агентом
  2026-05-21).

### Closing-правка `BOARD: Doing → Done` — отдельным commit'ом ПОСЛЕ `gh pr create`

Глобальное правило (закрытие задачи **в задачном PR**, без парного
chore-PR) сохраняется. Здесь — проектное уточнение порядка шагов на
ветке, чтобы в записи Done стоял реальный `[closed YYYY-MM-DD,
PR #N]`, а не placeholder `PR current`.

Алгоритм для task-PR (`T<NNN>-<slug>`):

1. Реализация задачи коммитится на ветке.
2. `git push -u origin T<NNN>-<slug>`.
3. `gh pr create` → получили `#N`.
4. В `BOARD.md` запись задачи переезжает из `## Doing` в `## Done`
   с пометкой `[closed YYYY-MM-DD, PR #N]`.
5. `git commit -m "chore(board): close T<NNN>"` + `git push`.
6. Self-review, squash-merge — оба commit'а в `main` схлопнутся в
   один (правило «один PR — один коммит»).

**Не применяется к:**

- Методическим PR без T-ID (`rules/<slug>`, `fixes/<slug>`) — у
  них нет BOARD-записи.
- Release-PR (`release: cut <ver>`) — они переносят задачи из
  `## Done` в `CHANGELOG.md`; closing-правка Done уже сделана в
  task-PR, которые в этот milestone вошли.

Принято в efactory после повторной (×6 в `[0.2.0]`) помарки
`PR current` → fix-up в следующем PR. См. ретро `[0.2.0]` в
`CHANGELOG.md` и задачу T093.

## Дисциплина планирования

Без Scrum-церемоний (sprints, story points, velocity, burndown).
Поддерживаем только полезные элементы:

- **Milestone-based versioning.** `[Unreleased]` в `CHANGELOG.md`
  накапливает изменения. Переход к новой версии `[N.M.0]` —
  когда **осмысленно завершено** (soft criterion): введены значимые
  изменения, ИЛИ завершён логически связанный цикл задач, ИЛИ
  накопилось «достаточно» для отдельной точки сохранения.
  Окончательно решает Разработчик; формальной метрики нет — она
  противоречит самому принципу «без Scrum-карго». Формат версий —
  Keep a Changelog (`## [N.M.0]`, без `v`-префикса).
- **Retrospective как ритуал** после закрытия milestone. Короткий
  разбор в формате трёх пунктов:
  - что зашло (work-as-expected, или приятный сюрприз),
  - что не зашло (boundle, slip-ы, лишний overhead),
  - правки методики (что менять в `~/.claude/CLAUDE.md` /
    проектном `CLAUDE.md` / шаблоне).
  Размещение: **секция `### Retrospective`** внутри записи
  соответствующей версии в `CHANGELOG.md`. Не отдельный файл —
  ретро тесно связан с milestone, удобно читать рядом.
- **Acceptance criteria** обязательны для задач крупнее однострочной
  правки — записываются прямо в `BOARD.md` / `BACKLOG.md` коротким
  блоком (`Acceptance: <что должно быть достигнуто, чтобы задача
  считалась закрытой>`) или в `specs/T<NNN>-*/spec.md` для крупных
  фич. Без явных acceptance criteria задача не считается зрелой
  для перехода `BACKLOG → BOARD → Doing`.
- **WIP-limit** в `BOARD.md → Doing`: максимум 1-2 задачи. Больше —
  теряется фокус (классическое kanban-правило).

Если у Разработчика настроен глобальный `~/.claude/CLAUDE.md` —
там лежит расширенная версия этих правил (разделы «Никогда не пушить
напрямую в main», «Один PR — один коммит», «Code review каждого PR»).
Краткой версии выше достаточно как самодостаточного источника.

## Проект-специфичные правила

### Сборка контейнера: `efactory-build-dev`, не `docker build` (T021, 2026-05-30)

Для **любой** пересборки `efactory:linux` на dev-машине Разработчика
**используем `./scripts/efactory-build-dev`** (T141 buildx wrapper с
persistent layer cache в `~/efactory-buildcache/`), а не generic
`docker build`.

**Почему это правило:**

- `docker build -t efactory:linux .` тянет каждый layer заново
  (~30 мин), даже если код не менялся.
- `./scripts/efactory-build-dev` с warm cache — секунды; с пустым cache
  один раз — те же ~30 мин, **но cache persistent**.
- T021 Phase D (2026-05-30) Гвидо сжёг ~30 минут вторым cold rebuild
  через `docker build` (cache не использовался), потому что был
  невнимателен. Правило закреплено чтобы не повторять.

**Когда использовать generic `docker build`:**

- Только при отсутствии `docker-buildx-plugin` на host'е (необычно).
- Документация для **конечных** пользователей в `README.md` (они
  скачивают efactory один раз и не имеют buildx).
- В CI пайплайнах (T115) если решено не подключать buildx.

**Что делать при OOM во время build / run:**

Дефолтный `--memory=8g` лимит docker run в `efactory-up` (T021) ловит
runaway memory у ngspice / FEM / PyOM advisor и убивает контейнер
вместо global OOM-killer'а на хосте. Сообщение в stderr подскажет
override: `EFACTORY_MEMORY_LIMIT=12g ./efactory-up ...`.

### Дисциплина sync с Agent Knowledge Base (T134, 2026-05-27)

KB runtime-агента (`docker/runtime-agent-knowledge-base/`) — primary
канал передачи знаний о возможностях efactory от dev-цикла к
production-агенту в `efactory:linux`. Если KB отстаёт от
имплементации — agent не знает о новых slash-командах / CLI
функционале, изобретает велосипед, сканирует свои собственные
исходники efactory. Поэтому при добавлении нового **user-facing
функционала** в efactory — обязательная **трёхуровневая дисциплина**:

**Уровень 1 — system prompt + KB sync (обязательно, секунды).**

- **Новая slash-команда** →
  - (a) Добавить bullet в **`docker/runtime-agent-CLAUDE.md`** —
    секция «Custom slash-команды efactory». Это system prompt
    baked'ится в `efactory:linux` образ и видна агенту с первой
    строки разговора; без этого agent в running-контейнере не знает
    о новом slash → разыщет через KB-routing если повезёт, иначе
    изобретёт велосипед (T187 Уровень 3 smoke 2026-06-05 поймал это
    для `/grid-check`).
  - (b) Обновить mapping table в KB topic `agent.command-routing`
    (одна строка `| user phrase | /slash |`) — для free-text
    discovery агентом через TOC / `/kb-search`.
  - (c) Если команда имеет неочевидную семантику (pitfall'ы,
    специфический workflow) — дополнительно завести свой KB topic.
- **Новая use case / adapter с non-obvious gotcha** (pitfall,
  workaround, дисциплина использования) → завести KB topic в
  подходящем namespace (`spice.*`, `magnetics.*`, `fem.*`,
  `agent.*`, `project.*` или новый осмысленный).
- **Тривиальный функционал** (CLI flag без surprise, helper-функция,
  bug-fix без lesson) — НЕ требует KB update; достаточно `--help` /
  docstring / commit-message.

**Уровень 2 — deterministic regression test (обязательно, секунды).**

Новая KB entry → добавить parametrized case в
`tests/integration/agent_kb/test_control_examples.py` — `(query,
expected_topic, expected_directive_keyword)`. Проверяется через
`FileSystemKbStore.search()` / `.get()`, без LLM-judge. Это **fast**
(<1s в pytest), без image rebuild — заменяет per-PR smoke в
большинстве случаев и страхует от silent regression на следующих
изменениях infrastructure.

**Уровень 3 — full smoke с реальным agent (recommended, ~25-30 мин).**

Делать **не на каждом PR**, а:

- При изменении KB infrastructure (`scripts/session_start_hook.py`
  hook output, `FileSystemKbStore` semantics, `agent.command-routing`
  table).
- Перед версионным release milestone (как milestone acceptance gate).
- При подозрении на regression в agent behaviour (например, agent
  начал хуже выбирать команды).

Стандартный smoke pattern — 5+ scenarios через `docker run efactory:
linux claude -p "..."` headless с bind-mount существующего auth
state. Acceptance — agent правильно использует KB hits, не
изобретает велосипеды, persistence через bind-mount работает между
сессиями.

**Стоимость pyramid:** Уровень 1 (секунды) → Уровень 2 (секунды) →
Уровень 3 (~30 мин). Каждый уровень даёт нарастающую уверенность
без излишних затрат на typical change. Уровень 1+2 — every PR с
user-facing функционалом; Уровень 3 — на milestone / infrastructure
change / sanity check.

**Запрещено:** merge user-facing функционала **без** Уровней 1+2 для
не-тривиального изменения. Это создаёт «KB debt» — agent отстаёт от
кода, и через несколько milestone'ов KB становится бесполезной.

Если функционал заведомо тривиальный (one-line CLI flag без
semantics) — явно проговаривать в PR description: «KB sync не
требуется, потому что …». Это явное решение, не silent skip.

## Что в этом проекте обычно идёт в BACKLOG.md, а не в текущую правку

<!-- Опционально: примеры типичных побочных находок для этого проекта,
     которые ты заметишь и захочешь починить «заодно», но не надо. -->


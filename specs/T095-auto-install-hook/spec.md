# Spec: T095 — Auto-install pre-commit hook через `uv sync`

**Статус:** Done
**Дата создания:** 2026-05-17
**Связанные документы:** `CHANGELOG.md → [0.2.0]` ретро (источник),
`DECISIONS.md` → ADR `2026-05-17 — Auto-install pre-push hook через
hatchling custom build hook`.

---

## 1. Overview

Сейчас после клонирования проекта разработчик должен помнить о
команде `uv run pre-commit install --hook-type pre-push` (введена в
T091). Если забыть — `git push` пройдёт без локального гейта, и
кривой код попадёт на платформу. Цель T095 — сделать установку
хука автоматической, по умолчанию, без отдельной команды.

## 2. Сценарии использования

- **Новый разработчик клонирует репо.** Делает `uv sync`. После этого
  pre-push хук работает на ближайшем `git push` — никакой ручной
  команды не нужно.
- **Сам Гвидо/Владимир после `git pull` с новой версией pre-commit
  config.** `uv sync` обновляет зависимости; хук перерегистрируется
  при необходимости.
- **CI-окружение.** `uv sync` НЕ должна пытаться установить хук, если
  `.git` отсутствует (artifact-CI checkouts, docker images без VCS).
  Не падать, не шуметь.
- **Отсутствие `.git`** (например, проект распакован из tarball) —
  silently skip установку, без error.

## 3. Functional Requirements

- ДОЛЖНА: после первого `uv sync` в свежем клоне `git push` запускает
  5-step gate автоматически без дополнительных команд.
- ДОЛЖНА: при отсутствии `.git/` молча пропускать установку (никакой
  ошибки, никакого `exit != 0`).
- ДОЛЖНА: при повторном `uv sync` (idempotent) не дублировать хук,
  не выдавать спама.
- ДОЛЖНА: на CI работать без побочных эффектов.
- НЕ ДОЛЖНА: ставить хуки никуда, кроме `.git/hooks/` внутри
  репозитория (никаких global git templates).
- НЕ ДОЛЖНА: затирать существующий `pre-push.legacy` (защита `main`,
  созданная T091).

## 4. Success Criteria

- **Smoke 1 (свежий клон):** удалить `.git/hooks/pre-push`, удалить
  `.venv/`, запустить `uv sync`. Затем `git push` (на тестовой
  ветке) — гейт срабатывает.
- **Smoke 2 (idempotency):** `uv sync` дважды подряд — без ошибок,
  хук не дублируется.
- **Smoke 3 (no-git):** распаковать tarball без `.git`, `uv sync` —
  exit 0, ноль шума.
- **README обновлён:** в Quick Start убран ручной шаг
  `uv run pre-commit install --hook-type pre-push` (или
  оставлен как fallback с пометкой «обычно не нужно»).
- **ADR в `DECISIONS.md`** записан с обоснованием выбранного
  механизма (hatchling custom build hook / скрипт-обёртка /
  альтернатива).

## 5. Key Entities

- **`hatch_build.py` / `scripts/hatch_build.py`** — custom build hook
  (если выбран механизм 1).
- **`[tool.hatch.build.hooks.custom]`** — регистрация в `pyproject.toml`.
- **`.git/hooks/pre-push`** — целевой файл, который ставит
  `pre-commit install --hook-type pre-push`.
- **`.git/hooks/pre-push.legacy`** — существующий хук защиты `main`,
  сохраняется в migration mode (см. T091).

## 6. Assumptions & Constraints

- Build-backend проекта — **hatchling** (см. `pyproject.toml [build-
  system]`). Editable install выполняется через hatchling.
- `uv sync` под капотом делает editable install (`pip install -e .`
  эквивалент). При первом запуске или после изменения `pyproject.toml`
  hatchling пересобирает editable wheel и (теоретически) дёргает
  custom build hooks.
- pre-commit framework уже в dev-deps (`pyproject.toml`, добавлен в
  T091). Команда `uv run pre-commit install --hook-type pre-push`
  работает.
- Целевые ОС — Linux/macOS/Windows; pre-commit framework
  кросс-платформенный.

## 7. Out of Scope

- **Propagation в template `dreamteam`** — отдельной T-задачей после
  обкатки в efactory.
- **Auto-install других git hooks** (commit-msg, post-commit и т.д.) —
  сейчас только pre-push.
- **Установка `pre-commit` в global git templates** — намеренно
  локально для проекта.
- **Альтернативные build-backends** (setuptools, pdm, etc.) — не
  поддерживаем; проект на hatchling.

---

## Smoke-эксперимент (предшествует выбору механизма)

**Гипотеза:** hatchling custom build hook активируется при `uv sync`
в editable mode.

**Шаги:**

1. Создать минимальный `hatch_build.py` в корне с `print` в `initialize`.
2. Зарегистрировать в `pyproject.toml`:
   `[tool.hatch.build.hooks.custom]`.
3. Принудительный reinstall: `uv sync --reinstall-package efactory`
   (или удаление `.venv` + `uv sync`).
4. Проверить, что print в stdout/stderr.

**Если гипотеза подтвердилась** — механизм 1 (hatchling hook):
заменить `print` на установку pre-commit hook с guard'ами.

**Если нет** — fallback на механизм 2 (скрипт-обёртка
`scripts/dev-setup.sh`), документация в README обновляется по этому
сценарию.

**Результат:** гипотеза подтвердилась.

- Smoke 1 (`uv sync --reinstall-package efactory`) — hook сработал,
  `version='editable'`, `target='wheel'`, marker в `/tmp/` записан.
- Smoke 2 (`uv sync` без `--reinstall`) — hook **не** сработал (uv
  кешировал editable wheel). Это даёт идемпотентность бесплатно.
- Smoke 3 (probe env): `.venv/bin/pre-commit` существует к моменту
  `initialize()`, `uv run --no-sync pre-commit --version` → SUCCESS.
  Build venv (где hatch запускается) разный с `.venv/` проекта —
  `--no-sync` редиректит на проектный venv, корректно.
- E2E: удалён `.git/hooks/pre-push`, выполнен
  `uv sync --reinstall-package efactory` → hook восстановлен,
  идентичен backup'у (стандартный pre-commit wrapper).

Выбран механизм 1. ADR — `DECISIONS.md`
(`2026-05-17 — Auto-install pre-push hook через hatchling custom
build hook`). Альтернативы 2 (скрипт) и 3 (entry-point-init)
оценены в ADR и отвергнуты.

---

## Clarify

Lite-спека, full clarify не делаем. Открытые вопросы решаются по
ходу smoke-эксперимента и обсуждаются точечно.

## Analyze

Lite-спека. Основные риски:

- 🟡 **Hatchling hook может не активироваться при `uv sync` без
  `--reinstall`** — `uv` кеширует editable build. Smoke это покажет.
- 🟡 **Guard на `.git/` нужен надёжный** — `pathlib.Path(".git").is_dir()`
  не работает, если `.git` — это файл с `gitdir:` (worktree, submodule).
  Использовать `git rev-parse --git-dir` через subprocess.
- 🟢 **Idempotency** — `pre-commit install` сама по себе идемпотентна
  (перезаписывает hook без ошибки), но мы хотим избежать лишнего
  шума на каждом `uv sync`. Возможно — проверять mtime файла.

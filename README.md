# efactory

Система сквозного проектирования РЭА с использованием ИИ

<!-- 1-3 предложения выше заполнились из ответов на `dreamteam init`.
     Расширь по необходимости. Архитектурные решения — в DECISIONS.md,
     история — в CHANGELOG.md. -->

## Быстрый старт

Менеджер зависимостей и окружения: **`uv`** (выбран при
`dreamteam init`).

```bash
uv sync                       # поставить зависимости
uv run python src/main.py     # запустить
```

## Зависимости

```bash
uv add <pkg>                  # runtime
uv add --dev <pkg>            # dev
```

## Проверки перед push

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy <путь к коду>
```

Все три должны проходить с 0 ошибок. Обходные манёвры (`# noqa`,
`# type: ignore`, расширение `ignore`-секции) — только по согласованию.

## Структура проекта

- `src/` — корень исходников.
- `CONCEPT.md` — изначальное видение проекта (immutable).
- `DECISIONS.md` — архитектурные решения с обоснованиями (ADR-Lite).
- `BOARD.md` — рабочая Kanban-доска (To Do / Doing / Done).
- `BACKLOG.md` — парковка идей и побочных находок.
- `CHANGELOG.md` — журнал заметных изменений.
- `specs/` — спецификации крупных фич.
- `CLAUDE.md` — проектные правила для Claude (Claude Code).

## Методика работы

Проект создан из шаблона
[vlakir/dreamteam](https://github.com/vlakir/dreamteam). Подробное
описание методики (scope discipline, ритуал spec/clarify/analyze для
крупных фич, pre-push контроль) — см. репозиторий шаблона.

<!-- Ниже добавляются проект-специфичные разделы: API, развёртывание,
     схемы БД, документация модулей, контакты и т.п. -->

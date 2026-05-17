# `domain/` — предметная область

Pydantic v2 модели предметной области с **поведением** (не анемичные),
value objects, доменные сервисы, доменные исключения.

## Сюда

- Pydantic-модели агрегатов (`Project`, `Component`, `Schematic`,
  `Board`, ...) с методами, реализующими бизнес-инварианты.
- Value objects — `model_config = ConfigDict(frozen=True)`.
- Доменные сервисы — функции/классы, выражающие бизнес-логику,
  которая не принадлежит ни одной модели.
- Доменные исключения (`InvalidNetTopologyError` и т.п.).

## НЕ сюда

- SQLAlchemy / ORM (persistence-модели живут в
  `adapters/outbound/persistence_sql/`).
- HTTP-клиенты, файловые операции, MCP-вызовы.
- Логирование, конфигурация, env vars.
- Импорты из `application/`, `ports/`, `adapters/`, `composition/`.

## Зависимости

Только `pydantic` и stdlib. Любая другая зависимость — сигнал, что
код не доменный.

## Структура

Плоская на старте: `domain/project.py`, `domain/<entity>.py`.
Разделение на bounded contexts (`electrical/`, `mechanical/`,
`magnetics/`) — отдельной задачей при накоплении ≥10 моделей.

См. ADR блоки в `DECISIONS.md` (hexagonal layout, Pydantic domain,
domain без bounded contexts на старте) и спеку `T085`.

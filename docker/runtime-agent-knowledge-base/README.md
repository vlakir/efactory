# Agent Knowledge Base — built-in seed (T134)

Эта директория содержит **built-in seed** entries для Agent Knowledge
Base efactory runtime-агента. Содержимое запекается в образ
`efactory:linux` через `Dockerfile` под `/efactory/knowledge-base/
built-in/`.

## Layout

Один topic = один markdown-файл `<namespaced-slug>.md`:

```yaml
---
topic: spice.saturable          # namespaced slug, должен match filename stem
description: One-liner для TOC  # ≤ 200 chars
tags: [spice, magnetics]        # optional, lowercase-kebab
---
# Markdown body

Полный контент: правило, обоснование, anti-pattern, anchor на
DECISIONS.md / spec'у если нужен.
```

## Naming convention

Namespaced slug `<namespace>.<name>`:

- `spice.*` — SPICE / ngspice pitfall'ы и patterns.
- `magnetics.*` — магнетика (PyOpenMagnetics, formula, geometry).
- `fem.*` — FEM (Elmer, GetDP, mesh).
- `agent.*` — agent behaviour rules (command routing, scope).
- `project.*` — project-wide conventions (KiCad symbol naming, etc).

## Не путать с

- `runtime-agent-commands/` — slash-команды (interactive entry
  points агента).
- `runtime-agent-settings.json` — SessionStart hook config.
- `runtime-agent-CLAUDE.md` — system prompt (статичная роль).

## Read me для нового entry

См. spec T134 §5 (KbEntry schema) + §3 FR. Pre-push gates:
- `efactory kb list` (validation через CLI).
- `tests/integration/agent_kb/` (control examples).

## Host-mutated entries

User-added (через `/kb-add` или `efactory kb add`) живут в
`$HOME/efactory-state/knowledge-base/` (bind-mount, не в репо).
Promotion в built-in seed — manual через PR (Vladimir + Гвидо
review).

## Migration roadmap

T134 core = 10 control examples (9 из T131/T132/T133 + 1 из
agent.command-routing). Full migration dev-process knowledge
(DECISIONS.md / CHANGELOG.md / Гвидо auto-memory / mem0) —
follow-up задача **T154** (см. BACKLOG).

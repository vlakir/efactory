# Phase 7 — Persistent user overlay для agent (T177)

**Дата:** 2026-06-04
**Статус:** ✓ Implemented + tested
**Спека:** Closing Phase 6 architectural gap. Agent's tube `.lib` и
templates теперь persistent через bind-mounted user overlay в
`efactory-up --agent` режиме.

---

## 1. Problem statement (Phase 6 finding)

Agent внутри `efactory:linux` контейнера cмог построить отличный
template для микрофонного преампа на 6Ж32П (gain 40.76 dB, BW 9.5-
87.5 kHz), но записал артефакты в **transient image filesystem**
(`/opt/efactory/data/templates/`, `/opt/efactory/data/models/tubes/
custom/`). После container exit — пропали.

Agent thought он «registered template в built-in collection» —
misunderstanding: built-in dirs **в image** (image content), не на
host. Bind-mount только `/workspace`, `/efactory/.claude`,
`/efactory/knowledge-base/host-mutated`.

Repository's `data/templates/` and `data/models/tubes/custom/` на
host (для built-in shipping) — read-only by design, не bind-mount'ятся
r/w в agent container (защита от accidental overwrite built-in).

## 2. Solution

Parallel pattern к existing user_library_root (T006 fix-up Q3):
добавили `user_templates_root` overlay + CLI command для promotion +
bind-mount strategy.

### 2a. Settings — `user_templates_root`

`src/composition/settings.py`:
- `_default_user_templates_root() → <data_dir>/templates` (XDG-стиль)
- Field `user_templates_root: Path` с default factory
- Env override: `EFACTORY_USER_TEMPLATES_ROOT=<path>`

### 2b. Template materializer — overlay-aware

`src/adapters/inbound/cli/template_materializer.py`:
- `list_templates(user_overlay_root)` merges built-in + overlay
- `describe_templates(user_overlay_root)` aggregates metadata
- `materialize_template(..., user_overlay_root=...)` resolves user → built-in
- User overlay побеждает at name conflict (consistent с user_library_root)

### 2c. New CLI: `efactory template create-from-project`

`src/application/create_template_from_project.py`:
- Use case `create_template_from_project(request) → result`
- Walks project dir, копирует с `<project>` → `{{PROJECT_NAME}}`
  placeholder rename
- Skip rules: `project.yaml`, `sim/`, `datasheets/`, `.efactory/`,
  `*.kicad_prl` (runtime artefacts).
- Generates stub `template.yaml` + `README.md` (с CLI `--summary` /
  `--description` overrides).
- Conflict check + `--force` semantic.

`src/adapters/inbound/cli/app.py`:
- `template_app` sub-Typer с `create-from-project` command
- Args: `<project_name>`, `--name <template>`, `--summary`,
  `--description`, `--force`
- Writes to `user_templates_root` (passed через DI from settings)

### 2d. efactory-up — bind-mount overlay в agent контейнер

`efactory-up` `--agent` mode:
- `mkdir -p $STATE_DIR/efactory/models $STATE_DIR/efactory/templates`
- `-v $STATE_DIR/efactory:/efactory/data:rw` (persistent overlay
  mount)
- `-e EFACTORY_USER_LIBRARY_ROOT=/efactory/data/models`
- `-e EFACTORY_USER_TEMPLATES_ROOT=/efactory/data/templates`

После changes:
- Agent's `efactory tube fit-from-points` (default `--out`) → host
  `~/efactory-state/efactory/models/tubes/custom/` (persistent ✓)
- Agent's `efactory template create-from-project` → host
  `~/efactory-state/efactory/templates/` (persistent ✓)
- User может потом cherry-pick promote'нутые artefacts в repo
  built-in (через `cp` или PR) — manual decision.

## 3. KB-sync (T134 L1+L2)

### Mapping table — +1 row

`agent.command-routing.md`:
> «сохрани этот проект как шаблон», «promote project as template»,
> «сделай чтобы потом ещё проекты из этого создавать», «save as
> reusable template» → `efactory template create-from-project
> <project> --name <template> [--summary] [--force]` — promote в
> persistent user overlay.

### KB topic update

`tubes.curve-fitting.md` секция «Persistent agent overlay (T177)»:
- Объясняет где persistent path (env + bind-mount).
- Документирует pre-T177 bug.
- User overlay побеждает built-in semantics.

### Regression tests

`test_control_examples.py` — +2 cases:
- Routing «сохрани проект как шаблон» → mapping table content.
- KB topic content «persistent agent overlay bind-mount».

## 4. Tests

`tests/unit/application/test_create_template_from_project.py` —
6 cases:
- Happy path: files copied + placeholders + metadata stubs.
- Excluded files NOT copied (project.yaml / sim/ / .kicad_prl).
- File count exact.
- Missing project → error.
- Missing schematic → error.
- Conflict без force → error.
- Force overwrites cleanly.

## 5. Architectural notes

### Overlay precedence

User overlay > built-in. Same pattern что и user_library_root.
Trade-off: agent может «убрать» built-in template из его view,
написав свой same-name. Built-in для других users (без overlay) —
без изменений.

### Bind-mount layout

```
host: ~/efactory-state/efactory/
        ├── models/
        │     └── tubes/custom/<NAME>.lib
        └── templates/
              └── <name>/
                    ├── {{PROJECT_NAME}}.kicad_sch
                    ├── {{PROJECT_NAME}}.kicad_pro
                    ├── models/<NAME>.lib
                    ├── template.yaml
                    └── README.md

container: /efactory/data/   (bind-mount)
            └── (зеркало host)
```

### Не bind-mounted (sufficient design)

`/opt/efactory/data/` (built-in shipping) остаётся read-only в
container — никакой агент не может accidentally перезаписать
built-in `se-amp` или `6zh38p-if-amp`.

`repo/data/` на host — НЕ bind-mounted в agent. Промоция overlay
artefact'ов в built-in (commit в репо) — manual human decision
после inspection. Это намеренно safe — agent не может silently
изменять built-in shipping content.

## 6. BACKLOG follow-up candidates (resolved scope minimization)

- **T179** — `efactory template inspect <name>` — show template
  metadata + diff vs built-in same-name (useful когда overlay
  perekry'l built-in).
- **T180** — Slash-команда `/template-promote-from-current-project`
  для agent — autodiscover'ит current project в `/workspace` и
  promote'нет.
- **T181** — `efactory template promote-to-built-in <name>` —
  optional helper для human user, который копирует overlay → repo's
  `data/templates/` с git add / commit hint (host-side only).

## 7. Verdict

T177 закрывает Phase 6 architectural gap минимальным переписыванием:
- 1 settings field
- 1 template_materializer signature extension
- 1 new use case (~200 LoC)
- 1 new CLI command
- 1 bind-mount + 2 env vars в efactory-up
- KB sync + 2 regression tests

Tests pass (1962 total, +6 T177 use case + 2 KB regression).
Pre-push 5/5 ✓.

Agent's мик-преамп story Phase 6 → Phase 7 теперь имеет working
end-to-end path: vision → fit → simulate → measure → **promote
template (persistent)** — без human host-side cleanup.

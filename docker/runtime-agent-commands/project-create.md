---
description: Создать новый efactory-проект из выбранного шаблона (default — se-amp).
argument-hint: <PROJECT_NAME> [TEMPLATE]
allowed-tools: Bash
---

Пользователь хочет создать новый efactory-проект. Аргументы переданы
через `$ARGUMENTS` (T027 Phase E: `<PROJECT_NAME> [TEMPLATE]`).

1. **Parse `$ARGUMENTS`:**
   - Если `$ARGUMENTS` пуст — напечатай
     `Usage: /project-create <PROJECT_NAME> [TEMPLATE]`, потом
     `efactory project list-templates`, остановись.
   - Иначе split `$ARGUMENTS` на whitespace: первое слово = `NAME`,
     второе слово (опционально) = `TEMPLATE`. Если `TEMPLATE` не
     указан — default `se-amp` (back-compat).

2. **Запусти:** `efactory project create --name <NAME> --template <TEMPLATE>`.

3. **Покажи stdout/stderr пользователю.**

4. **Если команда успешна** — короткое follow-up: «Проект создан в
   `/workspace/<NAME>/` (шаблон: `<TEMPLATE>`). Используй
   `/project-use <NAME>` для просмотра контекста или работай с
   `/workspace/<NAME>/*` через абсолютные пути.»

5. **T025 auto-show схемы.** Просканируй stdout на строки вида
   `schematic-render: <abs path to PNG>` (по одной на лист схемы
   созданного проекта). Для каждой выполни **обе** операции в этом
   порядке:
   - **`chafa <abs path>`** через Bash — печатает ANSI-block
     render в terminal, пользователь видит силуэт схемы прямо в
     чате. Размер chafa определяет по `$COLUMNS`/`$LINES` автоматом;
     если terminal очень широкий и render узковат — можно явно
     задать `--size=200x` (200 col wide, высота по aspect ratio).
   - **`Read <abs path>`** — multimodal LLM «видит» PNG, ты можешь
     описать топологию (схему, компоненты, связи) пользователю.

   При `Warning: schematic render failed: ...` в stderr — упомяни
   warning, но проект всё равно создан (fail-soft).

6. **Если упало (non-zero rc)** — покажи сообщение об ошибке. Если
   ошибка `Template '<name>' not found` — предложи
   `efactory project list-templates` для просмотра доступных шаблонов.

## Доступные шаблоны (T027 finished — 8 шаблонов)

- **`se-amp`** (default) — Single-ended 6П14П + OPT 5k:8Ω.
- **`nfb-se-amp`** — NFB SE 6Н1П+6П14П + global feedback.
- **`op-amp-inverting`** — Op-amp inverting (PM≈45° calibration ref).
- **`bjt-ce-nfb`** — BJT CE shunt-shunt NFB (2N3904).
- **`tube-pp-amp`** — Push-pull 6П14П PP + LTP 6Н2П splitter.
- **`tube-line-preamp`** — Tube line preamp 6Н2П CC+CF.
- **`tube-phono-riaa`** — Phono preamp 12AX7 + passive RIAA.
- **`active-lpf-sallen-key`** — Sallen-Key Butterworth LPF f_c=1kHz.

См. KB topics `spice.tube-push-pull`, `spice.tube-line-preamp`,
`spice.tube-phono-riaa`, `spice.active-filter-sallen-key` для design
discipline каждого шаблона.

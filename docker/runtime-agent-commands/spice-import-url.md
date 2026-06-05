---
description: Импорт SPICE-модели из публичного URL в пользовательскую библиотеку.
argument-hint: '<URL> [--vendor NAME] [--force] [--skip-smoke] [--dry-run]'
allowed-tools: Bash
---

Пользователь хочет добавить SPICE-модель компонента (BJT / JFET /
MOSFET / диод / op-amp) из публичного URL в `<user_library_root>` —
через `efactory spice import-url` (T030).

Args от пользователя: `$ARGUMENTS` (обязателен URL первым позиционным,
далее опциональные флаги).

1. **Извлеки URL.** Это первый позиционный аргумент (не начинается с
   `--`). Если URL отсутствует — напиши пользователю: «Передай URL
   модели первым аргументом: `/spice-import-url
   https://www.vishay.com/.../2n3904.lib`», остановись.

2. **Запусти:** `efactory spice import-url <URL> $ARGUMENTS_REST` —
   где `$ARGUMENTS_REST` это всё после URL (флаги `--vendor`,
   `--force`, `--skip-smoke`, `--dry-run`, `--json`, `--timeout`,
   `--max-bytes`, `--insecure`, `--category`, `--subcategory`).

3. **Покажи stdout полностью.** Pipeline отчитается:
   - `installed: <path> [smoke: passed|failed|skipped]`
   - `KB topic: <path>` (новый topic `spice.<vendor>.<part>` для
     последующего `/kb-search`).
   - В `--dry-run` режиме — план без записи на диск.

4. **Exit-code семантика:**
   - `0` → import успешен (или dry-run).
   - `1` → domain-level fail: download 4xx, classification ambiguous,
     duplicate без `--force`, smoke fail, encrypted/HTML content.
     **Что делать:** для duplicate — `--force` если хочешь
     перезаписать; для ambiguous — добавь `--category=<cat>
     --subcategory=<sub>` (см. список ниже).
   - `2` → infrastructure fail: network timeout, DNS, TLS reject,
     malformed URL scheme, disk error. Обычно re-try не помогает —
     fix окружение или используй `/spice-import-url <url> --insecure`
     (только для известных-доверенных vendor'ов).

5. **Когда `--vendor=<name>`:**
   - URL host автоматически детектится для `ti / vishay / onsemi /
     analog / microchip / infineon / st / nxp`. Если URL с другого
     host'а (например, academic site) — vendor = `unknown`.
   - Можно явно задать: `--vendor=diyaudio` (lowercase, letters/
     digits/underscore).

6. **Когда `--skip-smoke`:**
   - По умолчанию pipeline прогоняет ngspice OP analysis на per-class
     fixture'е (CE для BJT, CS для FET, forward для diode, unity
     buffer для op-amp). Smoke fail → install rollback.
   - `--skip-smoke` — пропустить, если модель заведомо нестандартная
     или ngspice недоступен.

7. **Когда `--category=<cat> --subcategory=<sub>`:**
   - Override автоматической классификации для edge-cases. Возможные
     значения category: `bjt / jfet / mosfet / diode / opamp / tube
     / transformer / load`. Subcategory: `npn|pnp / njf|pjf / nmos|
     pmos / signal|schottky|zener|rectifier|led / full_vendor /
     triode|pentode|...`.

8. **Auth-walled vendors (TI PSpice .zip за SSO).** Direct-URL
   downloader не умеет cookies / login. Workaround: пользователь
   скачивает руками, потом `efactory spice import-file <path>
   --vendor=ti` (та же pipeline).

См. KB topic `spice.import-pipeline` (детали flow, разрешённые
content-types, troubleshooting).

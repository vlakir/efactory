---
description: Применить pending staged-модификации `.kicad_sch` → active (T026).
argument-hint: '<project> [--force] [--accept-overwrite]'
allowed-tools: Bash
---

Пользователь хочет применить отложенные изменения schematic-файлов
(staged → active) для проекта. Это T026 staged-workflow: writer
не перезаписывает `.kicad_sch` пока KiCad GUI держит файл (lock-файл
`~<name>.lck` рядом), а кладёт изменения в `<orig>.kicad_sch.staged`
+ sidecar `.meta.json`. `/schematic-apply` применяет их.

Args от пользователя: `$ARGUMENTS` — обязательный `<project>` (имя
директории проекта), опциональные `--force` / `--accept-overwrite`.

1. **Извлеки `<project>`.** Это первый позиционный аргумент в
   `$ARGUMENTS`. Если его нет — спроси у пользователя: «Какой проект
   apply'им? (`/schematic-apply <project>`)».

2. **Запусти:** `efactory schematic apply-staged <project>
   [--force] [--accept-overwrite]` — флаги пробрасывай если
   пользователь их указал.

3. **Покажи stdout/stderr.** Особое внимание на строки:
   - `schematic-applied: <abs>` — успешный apply per file. Если ≥1
     — упомяни пользователю что active обновлён.
   - `schematic-apply-skipped: <abs> reason=lock ...` — KiCad GUI
     ещё держит файл. Подскажи: «закрой KiCad перед apply ИЛИ
     запусти с `--force` (lock-cleanup safe в большинстве случаев)».
   - `schematic-apply-skipped: <abs> reason=parent-hash-mismatch
     current=<hex16> expected=<hex16> ...` — active изменён извне
     (пользователь сохранил свою версию в KiCad GUI после
     staged-write). **Реальный data loss risk**. Подскажи:
     «active diverged от staged. Если согласен потерять KiCad-edit
     и принять staged — `--accept-overwrite`. Иначе сначала
     сохрани active вручную / зафиксируй diff и потом apply».
   - `schematic-apply-staged: no pending staged to apply` — нечего
     применять (exit 0). Скажи пользователю что pending не было.

4. **Exit code semantics:** 0 → всё применено или nothing to apply; 1
   → есть skipped entries. Не сваливай как «ошибка» если exit 1 —
   это часто «ждём действия пользователя» (закрыть KiCad / решить
   про overwrite).

5. **Не дублируй `--force` и `--accept-overwrite` semantic.**
   - `--force` → bypass stale-lock (rutinный recovery, low risk).
   - `--accept-overwrite` → bypass parent-hash check (real data
     loss, требует осознанного согласия).
   - `--force` **не** обходит parent-hash — для apply при divergence
     нужно `--accept-overwrite`. См. KB
     `schematic.staged-modifications`.

**См. также:** `/kb-search staged-modifications` для полного
workflow и pitfall'ов.

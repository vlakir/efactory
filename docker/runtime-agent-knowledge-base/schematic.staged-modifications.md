---
topic: schematic.staged-modifications
description: Staged `.kicad_sch` workflow когда KiCad GUI держит файл открытым (T026).
tags: [schematic, kicad, workflow, staged, apply]
---
# Staged-модификации `.kicad_sch` при открытом KiCad

efactory защищает несохранённое состояние KiCad GUI: если ты редактируешь
`.kicad_sch` в Eeschema, а пользователь параллельно триггерит efactory
operation (`/sim-run`, `/project-create`, future LLM-edits) — writer **не
перезаписывает** активный файл, а пишет рядом
`<orig>.kicad_sch.staged` + sidecar `.meta.json` с `parent_hash` (sha256
active content). Активный файл не трогается, KiCad GUI не показывает
prompt «file changed on disk, reload?», unsaved состояние сохраняется.

## Как пользователь увидит staged-write

В stdout efactory operation увидишь строки:

- `schematic-staged: <abs/path/to/foo.kicad_sch.staged>` — staged-файл
  записан рядом с активным.
- `schematic-staged-overwrite: previous <sha256> dropped` — если staged
  уже был, перезаписан (latest wins).

Если этих строк нет — write прошёл напрямую (lock-файл не
детектирован, KiCad был закрыт). Это **common case**, не аномалия.

## Применить staged → active

Когда пользователь готов принять отложенные изменения (закрыл KiCad
GUI **или явно осознанно**), запусти:

```
efactory schematic apply-staged <project> [--force] [--accept-overwrite]
```

или slash:

```
/schematic-apply <project>
```

(slash требует `<project>` arg всегда — current-project context в
efactory пока нет, см. spec T026 W2).

Apply per-file pre-checks:

1. **Lock check.** Если lock-файл (`<dir>/~<name>.lck`) всё ещё рядом —
   skip с `reason=lock`. Bypass: `--force`.
2. **Parent-hash check.** Если current active hash ≠ `parent_hash` из
   sidecar (active изменён в KiCad GUI и сохранён после staged-write) —
   skip с `reason=parent-hash-mismatch`. Bypass: `--accept-overwrite`.

**`--force` НЕ обходит parent-hash check** — это сознательное
разделение: lock false-positive (stale lock после crash) безопасно
отбросить; parent-hash mismatch означает **реальный data loss** в
KiCad GUI, требует осознанного подтверждения.

## KiCad 10 stale-lock — норма (не edge case)

Phase 0 probe 2026-06-03 (KiCad 10.0.3) показал: lock-файл
`<dir>/~<name>.lck` **НЕ удаляется** при `SIGTERM` / `SIGKILL` /
crash KiCad процесса. Удаляется только при graceful File→Close /
GUI X-button.

Поэтому `--force` в apply-staged ожидаемо используется часто — это
не «крайняя мера», а штатный recovery после crash. Не пугайся
warning'а «lock-file detected».

## Apply outcome formats

stdout строки:

- `schematic-applied: <abs/path/to/active>` — успешный apply per
  file.
- `schematic-apply-skipped: <abs> reason=lock ...` — заблокирован
  lock-check (stderr).
- `schematic-apply-skipped: <abs> reason=parent-hash-mismatch
  current=<hex16> expected=<hex16> ...` — divergence (stderr).
- `schematic-apply-staged: no pending staged to apply` — нет
  pending файлов (idempotent, exit 0).

Exit code: 0 если все pending applied или nothing to apply; 1 если
есть skipped entries.

## Anti-pattern (NE делай)

- **Не редактируй staged-файл вручную.** Это intermediate artifact,
  source of truth — active. Если нужно сохранить staged-изменения —
  сначала apply-staged, потом edit active.
- **Не коммить `.staged`/`.staged.meta.json` в git.** Они в
  `.gitignore` шаблона. Это per-machine state, не source.
- **Не запускай apply-staged когда KiCad GUI всё ещё открыт** без
  понимания. `--force` обходит lock-check, но KiCad может перезаписать
  active обратно на свою memory copy при следующем save → loss
  staged changes.

## См. также

- `BACKLOG.md` (Phase 8) → T079 IPC reload через `kicad-python`
  (нет Schematic API до KiCad 11/12 ~2027-2028).
- ADR-T026 в `DECISIONS.md` (если будет добавлен).
- Spec `specs/T026-staged-modifications/spec.md`.

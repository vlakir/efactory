---
topic: spice.import-pipeline
description: Pipeline импорта SPICE-моделей по URL (BJT/JFET/MOSFET/diode/op-amp) — T030
tags: [spice, import, url, bjt, jfet, mosfet, diode, opamp, vendor, t030]
---

# SPICE-model import pipeline (`/spice-import-url`)

## Когда смотреть в этот topic

- User говорит «добавь модель X», «импортируй SPICE для Y», «найди модель
  для 2N3904 / IRF540 / OPA1612 / 1N4148».
- В netlist'е unresolved part — нужно поставить vendor-модель из
  публичного URL.
- Нужно расширить пользовательскую библиотеку без вмешательства в
  built-in.

## Что делает pipeline

`/spice-import-url <URL>` (или CLI `efactory spice import-url <URL>`):

1. **Download.** stdlib `urllib` HTTP/HTTPS GET, без cookies/SSO,
   timeout 30s, max body 1 MiB, TLS verification on, cross-host
   redirect block (`vishay.com → www.vishay.com` ok, cross-domain —
   fail).
2. **Classify.** Regex-парсер `.SUBCKT` / `.MODEL` cards:
   - `.MODEL TYPE=NPN/PNP` → BJT/{npn|pnp}.
   - `.MODEL TYPE=NJF/PJF` → JFET/{njf|pjf}.
   - `.MODEL TYPE=NMOS/PMOS` → MOSFET/{nmos|pmos}.
   - `.MODEL TYPE=D` → DIODE/signal (override через `* subcategory:`).
   - `.SUBCKT` 5+ pin с `V+/V-/INP/INM/OUT` names → OPAMP/full_vendor.
   - `.SUBCKT` 3 pin → дискриминируется по internal `.MODEL` cards
     (Q-card → BJT, M-card → MOSFET).
   - Header `* category: <cat>` / `* subcategory: <sub>` — override.
3. **PWRS conversion.** `convert_pwrs_to_ngspice` (T168) idempotent
   на каждой card.
4. **Install.** `<user_library_root>/<category-plural>/<vendor>/
   <PART>.lib` с injected headers (`* vendor`, `* source_url`,
   `* sha256`, `* imported_at`, `* subcategory`).
5. **Smoke.** Per-class ngspice OP analysis (CE для BJT, CS для FET,
   forward для diode, unity buffer для op-amp). TUBE/TRANSFORMER/LOAD
   — skipped.
6. **KB topic.** `spice.<vendor>.<part>.md` auto-generated stub.

## Vendor extraction

Host-mapping table (URL → vendor):

| host | vendor |
|------|--------|
| `www.ti.com`, `ti.com` | `ti` |
| `www.vishay.com`, `vishay.com` | `vishay` |
| `www.onsemi.com`, `onsemi.com` | `onsemi` |
| `www.analog.com`, `analog.com` | `analog` |
| `ww1.microchip.com`, `www.microchip.com` | `microchip` |
| `www.infineon.com`, `infineon.com` | `infineon` |
| `www.st.com`, `st.com` | `st` |
| `www.nxp.com`, `nxp.com` | `nxp` |

Unknown host → vendor `unknown` (warning, не fail). Override: `--vendor=
<name>` (lowercase, letters/digits/underscore).

## Exit codes

- `0` — успех (или dry-run).
- `1` — domain fail: download 4xx, classification ambiguous (нужны
  `--category/--subcategory`), duplicate без `--force`, smoke failed,
  HTML/encrypted content.
- `2` — infrastructure fail: network timeout, DNS, TLS reject, invalid
  URL scheme.

## Pitfalls

- **Auth-walled vendors (TI PSpice .zip за SSO)** — pipeline их не
  скачивает. Workaround: скачай руками, потом `efactory spice import-
  file <path> --vendor=ti`.
- **Multi-`.SUBCKT` файлы** (TI dual op-amp `.lib` часто содержит 2-5
  SUBCKT'ов) — splits в отдельные `<PART>.lib` files (контракт
  `FilesystemSpiceModelLibrary`).
- **Encrypted LTspice blocks** (`*encrypted...*endencrypted`) —
  rejected как unsupported.
- **HTML вместо SPICE** (login portal page returned by 200 OK) —
  detected по `<html>` / `<form>` / `<input>` тегам, rejected.
- **Smoke fail rollback** — если ngspice не bias'ит модель (broken
  syntax / missing referenced `.MODEL`), install rollback'ится,
  staging directory чистится, KB topic не пишется.

## Когда использовать `--skip-smoke`

- Модель заведомо нестандартная (custom subckt с внешним wrapper'ом,
  который нужно сначала собрать).
- ngspice недоступен в окружении.
- Импорт legacy моделей tube / transformer (smoke не реализован для
  них, всё равно skipped автоматически).

## Связанные topics

- `agent.command-routing` — mapping user phrase → `/spice-import-url`.
- `spice.ngspice-syntax-compat` — PWRS conversion и HSPICE / ngspice
  differences.

## Acceptance проверки

`/spice-import-url file://$(realpath
tests/data/spice_import/vendor_samples/2n3904_bjt_npn.lib)`:

- exit 0.
- `<user_library_root>/bjt/unknown/Q2N3904.lib` создан с headers.
- KB topic `spice.unknown.q2n3904` indexable через `/kb-search`.
- ngspice OP smoke прошёл.

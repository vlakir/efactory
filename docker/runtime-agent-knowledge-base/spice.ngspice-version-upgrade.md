---
topic: spice.ngspice-version-upgrade
description: Контейнер efactory:linux использует ngspice 45.2 из source-build (не apt 42) — XSPICE TRAN memory leak fix
tags: [spice, ngspice, xspice, memory, container, t021]
---
# ngspice 45.2 в `efactory:linux` (не apt-version 42)

**TL;DR.** В `efactory:linux` стоят **две** копии ngspice: apt'овский 42
(для KiCad Simulator GUI / libngspice0 C++ linkage) и **из source — 45.2
в `/usr/local/bin/ngspice`** (для CLI pipeline через `bridge sim-run /
measure / edit-and-resim`). PATH ставит /usr/local перед /usr/bin, так
что любой subprocess из efactory кода зовёт 45.2.

## Зачем так сложно

Ubuntu 24.04 (`noble`) apt repo содержит **только ngspice 42**, у
которого баг: TRAN на XSPICE A-devices (saturable transformer
`OPT_SE_5K_8.lib` использует gyrator-cap — `spice.saturable-gyrator-cap`)
**растёт без bound в RAM**.

T021 (2026-05-30) — попытка Level 3 smoke `/edit-and-resim` на se-amp-
demo съела 8.8 GB RSS на ngspice 42 и убила hostsystem через global
OOM-killer. Тот же netlist на хосте (ngspice 45.2 из Ubuntu 25.04
universe) — 44 MB RSS, 0.32 sec.

Upstream 43-45.2 (2024-2025) содержит series fixes для XSPICE TRAN
memory accumulation. Минимально безопасная версия — **45.2**.

## Как это сделано в Dockerfile

Отдельный stage `ngspice-build` (`Dockerfile` line ~165):
- Source tarball: `https://codeload.github.com/imr/ngspice/tar.gz/refs/tags/ngspice-45.2`
  (sourceforge нестабилен через Cloudflare anti-bot).
- Configure flags: `--enable-xspice --enable-cider --with-readline=yes
  --enable-pss --enable-osdi --disable-debug`.
- Install в `/opt/ngspice/`; в `final` stage —
  `ln -sf /opt/ngspice/bin/ngspice /usr/local/bin/ngspice`.
- Apt'овский ngspice / libngspice0 НЕ удаляются — KiCad Simulator
  использует C++ linkage к libngspice 42.

Build dependencies (build-essential + autoconf/automake/libtool +
bison/flex/libreadline-dev) — apt cache mount
(`--mount=type=cache,target=/var/cache/apt`) — persistent между builds.

## Что делать, если опять OOM на TRAN

1. **Проверить, что используется 45.2** — `ngspice -v` в контейнере
   должен показать `ngspice-45.2`. Если 42 — образ старый, пересобрать
   через `./scripts/efactory-build-dev`.
2. **Schematic с saturable A-device + большой TRAN window** — снизить
   `t_stop` или сменить metric на AC (`--measure gain --mode small` /
   `--measure bandwidth`) — там нет TRAN buffer'а.
3. **`--measure thd` с large `v_in_peak`** (например ≥5V на input)
   → clipping + non-convergence → ngspice крутит solver, RAM растёт.
   Уменьшить `v_in_peak` или ограничить container'у через `docker run
   --memory=4g`.

## Когда апгрейдить дальше

Ngspice 46 уже релизнут (см. github tag `ngspice-46`). Когда понадобится
новая фича / fix — bump `NGSPICE_VERSION` в Dockerfile, rebuild,
verify.

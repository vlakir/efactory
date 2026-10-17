# T195 — продолжение diagnosis/policy от eee8473

Новый раунд начат actual devops-t195-r1 из exact clean checkpoint
`eee8473fdeba83a4c21380187585d37c92447ebd`. Это продолжение той же задачи;
source business/tests/deps/lock/CI не меняются. Исходные completed baseline/post
логи и их72nodeid lists сохранены; PATH/tool availability не маскировалась.

## Все72: категории и причинные границы

`diagnosis.json` сопоставляет каждый из72 failed nodeids ровно одному из72
traceback blocks; не extrapolation одного representative failure.

| Количество | Фактический симптом | Причина/граница вывода |
|---|---|---|
|71|load/parse schematic failure, обычно kicad-cli rc3|Host KiCad9.0.8 обнаруживается test availability checks, но source требует KiCad10 и writer emits schema20260306. Environment incompatibility strongly evidenced; target10 resolution всех71 ещё не выполнен и не гарантируется этим диагнозом.|
|1|publication rc2 «No sheets to plot»|Отдельная source fixture version20231120 с empty lib_symbols, не future-schema case. SVG в own probe rc0, PDF `--pages 1` rc2. Это воспроизводимая fixture/tool semantic несовместимость в host9; окончательное различение code vs target10 behavior требует target10 run.|

Executable НЕ missing: `/usr/bin/kicad-cli` version9.0.8,
ngspice45.2 и rsvg-convert присутствуют. dpkg metadata: kicad9.0.8,
kicad-symbols/kicad-footprints9.0.7, librsvg2-bin2.61.3. Tracebacks не указывают
missing executable/assets/config ни в одном из72; отсутствие указания не
подменяется exhaustive filesystem validation. Секретные settings/env не читались.

Source requirement: Dockerfile32–92 — Ubuntu24.04 + официальный PPA
`kicad/kicad-10.0-releases`; writer.py70 — `_KICAD_FILE_VERSION='20260306'`.
Test availability преимущественно `shutil.which`/наличие executable, а не major
version. Поэтому имеющийся host9 не является корректной source10 средой.

## Контролируемые own-env probes

Без изменения source/test или их фикстур: source `_build_rc_filter` из
tests/conftest.py21–48 вызван как есть в новой временной `.venv` директории;
сгенерированный schema20260306 файл существует, export netlist в host9 rc3.
Exact empty fixture из tests/e2e/walking_skeleton/test_publication_export.py68–78
повторена в отдельном own ephemeral probe: schema20231120, SVG rc0, per-page PDF
`--pages 1` rc2. Команда PDF совпадает с renderer.py174–194. Это diagnostic
probes, НЕ переделанные fixtures для green gate; full pytest не пропускался.
Hashes/rc/whitelist categories, без raw CLI content — `diagnosis.json`.
Словарь English/Russian diagnostic text в этих probes совпадений не дал:
это evidence только file/schema/hash/exit-code, НЕ самостоятельная текстовая
верификация parse/no-sheets. Семантическая классификация72 выше опирается на
original full pytest tracebacks, прочитанные writer; independent raw-trace
verification reviewer/лиду не приписывается.

Own editable efactory0.1.0 установлен; Python3.13.16, NumPy2.4.6, SciPy1.17.1,
PyOpenMagnetics1.3.10 из uv.lock. `uv sync --locked --active --check`: rc0,
would make no changes. Не было system/global updates, смены stack/version/lock,
установки второго host KiCad, PATH-hiding или бизнесфикса. Поэтому original72fail
identity остаётся исходным before/post доказательством; «after envfix» не
выдумывается, поскольку toolchain replacement не делался.

## Новая srv-policy и реально поддержанный exact-source путь

Read-only currentmain objects `5afd093e388d5f508e9ef4d84093f7aaa4716792`:
scripts/srv_gates.py + .forgejo/workflows/gates.yml + ci/forgejo/Dockerfile +
scripts/gates.sh. Глобальное правило efactory **light локально → sandbox → full
final exact SHA srv перед merge** действует и без workflow в старой source базе.
Первоначальный blanket remote-block вывод по72localfail исправлен, а не выдан
за окончательный policy verdict. Никакого redpush/hook bypass это не разрешает.

Штатный dispatcher CT121 `/usr/local/bin/srv-gates-run run --help` реально
выполнен read-only rc0: есть `--checkout` (включая.git), `--dockerfile`,
`--context`, `--prepare`, `--gates`, `--job`, `--out`. Это позволяет exact old
checkout без импорта main CI/business в source. Ordinary helper из main НЕ
запускался: он меняет remote и использует force/noverify. Нужна обычная unique
sandbox-ветка, если delivery применима, под управлением лида.

Canonical old-source gate-command override (без подмены на main mypy src tests):

```sh
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run lint-imports && uv run pytest
```

Current canonical gate image — Debiantrixie slim/Python3.13 с git/node/procps/
util-linux; в recipe НЕТ KiCad/ngspice/rsvg. Его штатные conditional skips —
факт existing CI environment, не искусственное weakening, но положительное
KiCad10 acceptance/coverage ими НЕ подтверждается. Источник Dockerfile и source
target stack не меняются ради формального green. Никакой appDocker build,
инфраструктурный install, новый сервер или full srv job этим writer не запущен.

Дальше: лид интегрирует итоговую metadata, фиксирует exact final lead SHA,
проверяет supported cache/image availability и общую очередь, согласует unique
staging/job и запускает штатный disposable gate run. Job flags source override
поддержаны; storage/cache/queue и final-SHA job evidence пока pending, не
притворный «srv уже green». Финальная приёмка/PR/Done не заявляются.

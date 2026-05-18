"""T102 one-shot: PSpice `PWRS(x,y)` → ngspice `sgn(x)*pwr(abs(x),y)`.

Применяет `convert_pwrs_to_ngspice` к каждому `*.lib` под
`data/models/tubes/custom/`. Идемпотентен: повторный запуск ничего не
меняет. Использование:

    uv run python scripts/patch_tubes_pwrs.py

Печатает по строке на каждый файл (changed / unchanged) и итог.
Exit code 0 в любом случае; cron / CI можно повесить без боязни flap.
"""

from __future__ import annotations

import sys
from pathlib import Path

from adapters.outbound.spice_models.conversion import convert_pwrs_to_ngspice

_TUBES_CUSTOM = Path('data/models/tubes/custom')


def main() -> int:
    if not _TUBES_CUSTOM.is_dir():
        sys.stderr.write(
            f'error: {_TUBES_CUSTOM} not found '
            f'(run from repo root)\n',
        )
        return 1
    changed = 0
    unchanged = 0
    for lib in sorted(_TUBES_CUSTOM.glob('*.lib')):
        before = lib.read_text(encoding='utf-8')
        after = convert_pwrs_to_ngspice(before)
        if before == after:
            unchanged += 1
            print(f'  unchanged: {lib.name}')
            continue
        lib.write_text(after, encoding='utf-8')
        changed += 1
        print(f'    patched: {lib.name}')
    print(f'\nDone: {changed} patched, {unchanged} already clean.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

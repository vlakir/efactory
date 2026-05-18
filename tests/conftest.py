"""Top-level pytest fixtures для efactory.

Содержит фикстуры, разделяемые между разными test-tier'ами (unit /
integration / e2e). По-фиксельному `pythonpath = ["src"]` уже даёт
`adapters.*` / `domain.*` / `composition.*` — ничего дополнительно
не подкладываем.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.outbound.schematic_kicad.facade import Schematic

if TYPE_CHECKING:
    from pathlib import Path


def _build_rc_filter(path: Path) -> Path:
    """RC-фильтр-эталон (T100 Phase 3): V1=1V DC → R=1k → C=1u → GND.

    Заменяет старую ручную фикстуру `tests/fixtures/rc_filter.kicad_sch`
    (149 строк s-expr), удалённую в T100 Phase 3. См. spec §4 — все
    ручные фикстуры переписаны через `efactory.schematic`. Координаты
    оставлены идентичными исходной фикстуре (для byte-уровня сличения
    в случае регресса).
    """
    sch = Schematic('rc_filter')
    v1 = sch.add_v_dc(reference='V1', value='1', at=(50.8, 62.23), rotation=180)
    r1 = sch.add_resistor(
        reference='R1', value='1k', at=(88.9, 55.88), rotation=90,
    )
    c1 = sch.add_capacitor(
        reference='C1', value='1u', at=(114.3, 55.88), rotation=90,
    )
    gnd_v = sch.add_ground(at=(50.8, 68.58))
    gnd_c = sch.add_ground(at=(118.11, 68.58))
    sch.connect(v1.pin_plus, r1.pin_a)
    sch.connect(r1.pin_b, c1.pin_a)
    sch.connect(c1.pin_b, gnd_c.pin)
    sch.connect(v1.pin_minus, gnd_v.pin)
    flg = sch.add_pwr_flag(at=(45.72, 68.58), rotation=180)
    sch.connect(flg.pin, v1.pin_minus)
    sch.label('in', at=(68.58, 55.88))
    sch.label('out', at=(101.6, 55.88))
    return sch.save(path)


@pytest.fixture
def rc_filter_schematic_path(tmp_path: Path) -> Path:
    """RC-фильтр `.kicad_sch`, сгенерированный фасадом T100 в `tmp_path`.

    Заменяет старую checked-in фикстуру `tests/fixtures/rc_filter.kicad_sch`.
    """
    return _build_rc_filter(tmp_path / 'rc_filter.kicad_sch')

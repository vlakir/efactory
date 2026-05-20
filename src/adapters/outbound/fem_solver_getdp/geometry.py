"""
E-core 2D-planar Gmsh .geo emitter (T113 Phase 2C).

Портирован из `scripts/pilot/mas_to_gmsh.py` (commit 273fbb6, debug-trail
из 5 итераций на Stage B+C). Эмитит front-view cross-section E-core OPT:
7 disjoint surfaces (core, primary window, secondary window, 3 air gaps,
air box) + outer boundary "infinity" для Dirichlet A_z=0.

Координаты: origin в центре E-core (front face), x right (width), y up
(height), глубина (z) свернута в 2D — depth fed обратно в Lp formula
(`L = 2 W_per_depth × depth / I²`).

Используется built-in Gmsh kernel (НЕ OpenCASCADE) — predictable tag
assignment, no boolean operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Constants — те же что в pilot mas_to_gmsh.py (за исключением имени класса).
AIR_BOX_PADDING = 3.0  # × max(core_w, core_h)
LC_CORE = 0.0015  # 1.5 mm в iron
LC_WINDING = 0.0015  # 1.5 mm в copper
LC_GAP = 0.00005  # 0.05 mm около gap (½× толщины 0.1 мм)
LC_AIR_FAR = 0.01  # 10 mm на outer boundary
# 10 μm inset на каждую сторону gap — предотвращает shared-vertex
# degeneracy mesh failures. Stage B+C debug urok.
GAP_INSET = 1e-5


@dataclass(frozen=True)
class ECoreDimensions:
    """
    2D-planar dimensions, обычно вычислены из PyOM `calculate_core_data`.

    Все размеры в метрах. Соответствует `processedDescription` PyOM MAS.
    """

    core_w: float  # full E-core width (front-view x)
    core_h: float  # full E-core height (front-view y)
    core_depth: float  # extrusion depth (z) — 3D scaling factor для Lp
    center_w: float  # центральная нога (column 0 width)
    center_h: float  # центральная нога height
    lateral_w: float  # боковая нога (column 1 width)
    lateral_x: float  # |x| центра боковой ноги
    window_w: float  # окно обмотки width
    window_h: float  # окно обмотки height
    gap_len: float  # длина air gap (одна общая для всех 3 ножек)

    @classmethod
    def from_pyom_core(cls, processed_core: dict[str, Any]) -> ECoreDimensions:
        """Извлечь dims из PyOM `processedDescription` core-dict."""
        pd = processed_core['processedDescription']
        fd = processed_core['functionalDescription']
        center = pd['columns'][0]
        lateral = pd['columns'][1]
        window = pd['windingWindows'][0]
        gap_len = fd['gapping'][0]['length']
        return cls(
            core_w=float(pd['width']),
            core_h=float(pd['height']),
            core_depth=float(pd['depth']),
            center_w=float(center['width']),
            center_h=float(center['height']),
            lateral_w=float(lateral['width']),
            lateral_x=abs(float(lateral['coordinates'][0])),
            window_w=float(window['width']),
            window_h=float(window['height']),
            gap_len=float(gap_len),
        )


class _GeoBuilder:
    """Minimal Gmsh built-in-kernel emitter — rectangle by rectangle."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._next_point = 1
        self._next_line = 1
        self._next_loop = 1
        self._next_surface = 1

    def add_rect(
        self,
        x: float,
        y: float,
        dx: float,
        dy: float,
        lc: float,
    ) -> int:
        """Добавить прямоугольник, вернуть curve-loop tag."""
        p0 = self._next_point
        self._next_point += 4
        l0 = self._next_line
        self._next_line += 4
        loop = self._next_loop
        self._next_loop += 1

        self.lines.append(
            f'Point({p0}) = {{ {x:.7g}, {y:.7g}, 0, {lc:.7g} }};\n'
            f'Point({p0 + 1}) = {{ {x + dx:.7g}, {y:.7g}, 0, {lc:.7g} }};\n'
            f'Point({p0 + 2}) = {{ {x + dx:.7g}, {y + dy:.7g}, 0, {lc:.7g} }};\n'
            f'Point({p0 + 3}) = {{ {x:.7g}, {y + dy:.7g}, 0, {lc:.7g} }};\n'
            f'Line({l0}) = {{ {p0}, {p0 + 1} }};\n'
            f'Line({l0 + 1}) = {{ {p0 + 1}, {p0 + 2} }};\n'
            f'Line({l0 + 2}) = {{ {p0 + 2}, {p0 + 3} }};\n'
            f'Line({l0 + 3}) = {{ {p0 + 3}, {p0} }};\n'
            f'Curve Loop({loop}) = {{ {l0}, {l0 + 1}, {l0 + 2}, {l0 + 3} }};\n',
        )
        return loop

    def add_surface(
        self,
        outer_loop: int,
        holes: list[int] | None = None,
    ) -> int:
        tag = self._next_surface
        self._next_surface += 1
        loops = [outer_loop, *(holes or [])]
        loop_list = ', '.join(str(t) for t in loops)
        self.lines.append(f'Plane Surface({tag}) = {{ {loop_list} }};\n')
        return tag

    def emit(self) -> str:
        return ''.join(self.lines)


def emit_e_core_geo(dims: ECoreDimensions) -> str:
    """
    Build .geo string для 2D-planar E-core front-view.

    Возвращает 7 Physical Surfaces (core/primary/secondary/3 gaps/air) +
    1 Physical Curve "infinity" — точно тот же layout что в pilot
    `tests/fixtures/magnetic/opt-6p14p-se/geometry.geo` (Stage B+C
    baseline).
    """
    cw = dims.core_w
    ch = dims.core_h
    half_cw = cw / 2.0
    half_ch = ch / 2.0
    cent_w = dims.center_w
    half_cent_w = cent_w / 2.0
    win_w = dims.window_w
    win_h = dims.window_h
    half_win_h = win_h / 2.0
    lat_x = dims.lateral_x
    lat_w = dims.lateral_w
    half_lat_w = lat_w / 2.0
    gap = dims.gap_len
    half_gap = gap / 2.0
    air_extent = max(cw, ch) * AIR_BOX_PADDING / 2.0

    win_left_x = -(half_cent_w + win_w)
    win_right_x = +half_cent_w

    g = _GeoBuilder()
    core_loop = g.add_rect(-half_cw, -half_ch, cw, ch, LC_CORE)
    win_left_loop = g.add_rect(win_left_x, -half_win_h, win_w, win_h, LC_WINDING)
    win_right_loop = g.add_rect(win_right_x, -half_win_h, win_w, win_h, LC_WINDING)
    cent_inset_w = cent_w - 2 * GAP_INSET
    gap_center_loop = g.add_rect(
        -half_cent_w + GAP_INSET,
        -half_gap,
        cent_inset_w,
        gap,
        LC_GAP,
    )
    lat_inset_w = lat_w - 2 * GAP_INSET
    gap_left_loop = g.add_rect(
        -lat_x - half_lat_w + GAP_INSET,
        -half_gap,
        lat_inset_w,
        gap,
        LC_GAP,
    )
    gap_right_loop = g.add_rect(
        lat_x - half_lat_w + GAP_INSET,
        -half_gap,
        lat_inset_w,
        gap,
        LC_GAP,
    )
    air_loop = g.add_rect(
        -air_extent,
        -air_extent,
        2 * air_extent,
        2 * air_extent,
        LC_AIR_FAR,
    )

    s_core = g.add_surface(
        core_loop,
        holes=[
            win_left_loop,
            win_right_loop,
            gap_center_loop,
            gap_left_loop,
            gap_right_loop,
        ],
    )
    s_primary = g.add_surface(win_left_loop)
    s_secondary = g.add_surface(win_right_loop)
    s_gap_center = g.add_surface(gap_center_loop)
    s_gap_left = g.add_surface(gap_left_loop)
    s_gap_right = g.add_surface(gap_right_loop)
    s_air = g.add_surface(air_loop, holes=[core_loop])

    # Air box — 7-й rect → его линии начинаются с 1 + 4*6 = 25
    air_rect_line_base = 1 + 4 * 6
    air_boundary_lines = [
        air_rect_line_base,
        air_rect_line_base + 1,
        air_rect_line_base + 2,
        air_rect_line_base + 3,
    ]

    out = [
        '// E-core 2D-planar front view — emitted by efactory',
        '// adapters.outbound.fem_solver_getdp.geometry.emit_e_core_geo',
        f'// core depth (3D scaling factor for Lp): {dims.core_depth:.5g} m',
        '',
        g.emit().rstrip(),
        '',
        '// Physical groups',
        f'Physical Surface("core") = {{ {s_core} }};',
        f'Physical Surface("primary") = {{ {s_primary} }};',
        f'Physical Surface("secondary") = {{ {s_secondary} }};',
        f'Physical Surface("gap_center") = {{ {s_gap_center} }};',
        f'Physical Surface("gap_left") = {{ {s_gap_left} }};',
        f'Physical Surface("gap_right") = {{ {s_gap_right} }};',
        f'Physical Surface("air") = {{ {s_air} }};',
        '',
        '// Outer boundary — Dirichlet A_z = 0',
        'Physical Curve("infinity") = { '
        + ', '.join(str(line) for line in air_boundary_lines)
        + ' };',
        '',
        'Mesh.ElementOrder = 2;',
        'Mesh.Algorithm = 6;  // Frontal-Delaunay',
    ]
    return '\n'.join(out) + '\n'

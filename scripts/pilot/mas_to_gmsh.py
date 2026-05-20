"""Generate Gmsh 2D-planar .geo from PyOM MAS geometry.json.

Front-view cross-section E-core OPT (extruded in depth direction by `depth`
when solved as 2D-planar — Elmer/GetDP scale flux per unit depth and multiply
by core depth to get total inductance).

Coordinate system: origin at E-core center (front face). x right (width),
y up (height), depth axis (z) collapsed in 2D.

Geometry tiling (6 disjoint surfaces filling the air box):
  1. core         — iron (outer E rectangle ∖ {2 windows ∪ 3 gap strips})
  2. primary      — left winding window (fills it for pilot)
  3. secondary    — right winding window
  4. gap_center   — thin air slot in center leg at y=0
  5. gap_left     — thin air slot in left lateral leg at y=0
  6. gap_right    — thin air slot in right lateral leg at y=0
  7. air          — air box ∖ outer E rectangle (only space outside core)

Outer air-box boundary tagged as "infinity" — Dirichlet A=0 for FEM.

Built-in geo kernel (NOT OpenCASCADE): predictable tag assignment, no
boolean operations. More verbose but no surprises after solver upgrades.

Usage:
  python scripts/pilot/mas_to_gmsh.py
  # reads tests/fixtures/magnetic/opt-6p14p-se/geometry.json
  # writes tests/fixtures/magnetic/opt-6p14p-se/geometry.geo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / 'tests' / 'fixtures' / 'magnetic' / 'opt-6p14p-se'

AIR_BOX_PADDING = 3.0  # × max(core_w, core_h)

LC_CORE = 0.0015      # 1.5 mm in iron
LC_WINDING = 0.0015   # 1.5 mm in copper
LC_GAP = 0.00005      # 0.05 mm near gap (½× толщины 0.1 мм — 2-3 элемента
                      # across gap для разрешения концентрации поля).
                      # GAP_INSET = 10 μm защищает от collinear-edge mesh fail.
LC_AIR_FAR = 0.01     # 10 mm at outer boundary

# Gap inset (m): shrink every column-gap rectangle by this much on each
# side. Prevents shared-vertex degeneracy with adjacent windows (centre leg)
# and the core outer face (lateral legs). 10 μm ≪ column widths (6–12 mm)
# → ~0.2-0.3% reluctance error per gap, well inside pilot tolerance.
GAP_INSET = 1e-5


def _load_geometry() -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / 'geometry.json').read_text())


def _extract_dims(mas: dict[str, Any]) -> dict[str, float]:
    """Pull 2D-planar dimensions from the processed core."""
    pd = mas['magnetic']['core']['processedDescription']
    fd = mas['magnetic']['core']['functionalDescription']
    center = pd['columns'][0]
    lateral = pd['columns'][1]
    window = pd['windingWindows'][0]
    gap_len = fd['gapping'][0]['length']
    return {
        'core_w': float(pd['width']),
        'core_h': float(pd['height']),
        'core_depth': float(pd['depth']),
        'center_w': float(center['width']),
        'center_h': float(center['height']),
        'lateral_w': float(lateral['width']),
        'lateral_x': abs(float(lateral['coordinates'][0])),
        'window_w': float(window['width']),
        'window_h': float(window['height']),
        'gap_len': float(gap_len),
    }


class _GeoBuilder:
    """Minimal Gmsh built-in-kernel emitter.

    Tracks point/line/loop tags, emits rectangles as 4 points + 4 lines +
    1 curve loop. Returns the curve-loop tag.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._next_point = 1
        self._next_line = 1
        self._next_loop = 1
        self._next_surface = 1

    def add_rect(
        self, x: float, y: float, dx: float, dy: float, lc: float,
    ) -> int:
        """Add a rectangle and return its curve-loop tag."""
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

    def add_surface(self, outer_loop: int, holes: list[int] | None = None) -> int:
        """Add a Plane Surface (outer loop, optional holes). Return tag."""
        tag = self._next_surface
        self._next_surface += 1
        loops = [outer_loop, *(holes or [])]
        loop_list = ', '.join(str(t) for t in loops)
        self.lines.append(f'Plane Surface({tag}) = {{ {loop_list} }};\n')
        return tag

    def emit(self) -> str:
        return ''.join(self.lines)


def emit_geo(dims: dict[str, float]) -> str:
    cw = dims['core_w']
    ch = dims['core_h']
    half_cw = cw / 2.0
    half_ch = ch / 2.0
    cent_w = dims['center_w']
    half_cent_w = cent_w / 2.0
    win_w = dims['window_w']
    win_h = dims['window_h']
    half_win_h = win_h / 2.0
    lat_x = dims['lateral_x']
    lat_w = dims['lateral_w']
    half_lat_w = lat_w / 2.0
    gap = dims['gap_len']
    half_gap = gap / 2.0
    air_extent = max(cw, ch) * AIR_BOX_PADDING / 2.0

    win_left_x = -(half_cent_w + win_w)  # left edge of left window
    win_right_x = +half_cent_w           # left edge of right window

    g = _GeoBuilder()
    # 1. Outer E-core rectangle
    core_loop = g.add_rect(-half_cw, -half_ch, cw, ch, LC_CORE)
    # 2. Left winding window
    win_left_loop = g.add_rect(win_left_x, -half_win_h, win_w, win_h, LC_WINDING)
    # 3. Right winding window
    win_right_loop = g.add_rect(win_right_x, -half_win_h, win_w, win_h, LC_WINDING)
    # 4. Center-leg gap (inset on each side — see GAP_INSET)
    cent_inset_w = cent_w - 2 * GAP_INSET
    gap_center_loop = g.add_rect(
        -half_cent_w + GAP_INSET, -half_gap, cent_inset_w, gap, LC_GAP,
    )
    # 5. Left lateral-leg gap
    lat_inset_w = lat_w - 2 * GAP_INSET
    gap_left_loop = g.add_rect(
        -lat_x - half_lat_w + GAP_INSET, -half_gap, lat_inset_w, gap, LC_GAP,
    )
    # 6. Right lateral-leg gap
    gap_right_loop = g.add_rect(
        lat_x - half_lat_w + GAP_INSET, -half_gap, lat_inset_w, gap, LC_GAP,
    )
    # 7. Air box outer
    air_loop = g.add_rect(
        -air_extent, -air_extent, 2 * air_extent, 2 * air_extent, LC_AIR_FAR,
    )

    # Iron surface = core outer ∖ (windows ∪ gaps)
    s_core = g.add_surface(
        core_loop,
        holes=[win_left_loop, win_right_loop,
               gap_center_loop, gap_left_loop, gap_right_loop],
    )
    # Winding & gap surfaces (each is just its own loop, no holes)
    s_primary = g.add_surface(win_left_loop)
    s_secondary = g.add_surface(win_right_loop)
    s_gap_center = g.add_surface(gap_center_loop)
    s_gap_left = g.add_surface(gap_left_loop)
    s_gap_right = g.add_surface(gap_right_loop)
    # Air surface = air box ∖ core outer
    s_air = g.add_surface(air_loop, holes=[core_loop])

    # Air-box outer boundary lines (lines 25..28 — air box was the 7th rect)
    # Each rectangle uses 4 sequential lines: rect_i lines = 1+4*(i-1) .. 4+4*(i-1)
    air_rect_line_base = 1 + 4 * 6  # 25
    air_boundary_lines = [
        air_rect_line_base, air_rect_line_base + 1,
        air_rect_line_base + 2, air_rect_line_base + 3,
    ]

    out = [
        '// E-core OPT 6П14П SE pilot — 2D-planar front view',
        '// Generated by scripts/pilot/mas_to_gmsh.py — DO NOT EDIT BY HAND',
        f'// core depth (3D scaling factor): {dims["core_depth"]:.5g} m',
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


def main() -> int:
    mas = _load_geometry()
    dims = _extract_dims(mas)
    geo_text = emit_geo(dims)
    out_path = FIXTURE_DIR / 'geometry.geo'
    out_path.write_text(geo_text)
    print(f'wrote {out_path} ({len(geo_text)} bytes)')
    print(
        f'  core: {dims["core_w"] * 1000:.2f}×{dims["core_h"] * 1000:.2f} mm '
        f'(depth {dims["core_depth"] * 1000:.2f} mm)',
    )
    print(f'  center leg: {dims["center_w"] * 1000:.2f}×{dims["center_h"] * 1000:.2f} mm')
    print(f'  window: {dims["window_w"] * 1000:.2f}×{dims["window_h"] * 1000:.2f} mm')
    print(f'  gap: {dims["gap_len"] * 1000:.3f} mm (×3 — center + 2 laterals)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

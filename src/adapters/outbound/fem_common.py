"""
Shared helpers для FEM-adapter family: PyOM data extraction + geometric VOs.

Used by `fem_solver_getdp` и `fem_solver_elmer` (added в T133). До T133
эти helpers жили в `fem_solver_getdp/{geometry,adapter}.py`; при добавлении
второго FEM backend extracted сюда, чтобы избежать adapter→adapter import
и DRY-нарушения.

Содержит:
- `ECoreDimensions` — pure-geometric VO для 2D-planar E-core dimensions.
  Factory `from_pyom_core` извлекает из PyOM `calculate_core_data` output.
- `emit_e_core_geo` — Gmsh `.geo` emitter для 2D-planar E-core front view
  (7 Physical Surfaces + outer boundary "infinity"). Shared между GetDP
  (Dirichlet outer) и Elmer (Infinity BC outer) adapter'ами; различие
  в BC задаётся в solver-specific `.sif` / `.pro` template, а не в .geo.
- `read_initial_permeability` / `read_saturation_flux_density` /
  `extract_frohlich_params` — извлечь Frohlich material params из PyOM
  `get_core_materials()`.
- `_GeoBuilder`, LC_* / GAP_INSET / AIR_BOX_PADDING — Gmsh kernel
  helpers и mesh-density константы.
- `_first_entry` — internal helper для PyOM list/dict-fields normalization.

Hex-architecture note: модуль НЕ часть domain (PyOM-aware factory'и
attached), но shared между adapter'ами одного семейства (FEM). Adapter→
adapter direct import избегаем; общие helpers — нормально.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Gmsh mesh-density константы (T113 Phase 2C debug-trail из 5 итераций
# на Stage B+C; портированы из pilot mas_to_gmsh.py).
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

    .geo BC-agnostic: outer boundary помечена "infinity" как Physical
    Curve; solver-specific BC type (Dirichlet A=0 у GetDP T113, Infinity
    BC у Elmer T133) задаётся в `.sif` / `.pro` template.
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
        '// adapters.outbound.fem_common.emit_e_core_geo',
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
        '// Outer boundary "infinity" — BC type (Dirichlet / Infinity BC)',
        '// задаётся в solver-specific .sif / .pro template.',
        'Physical Curve("infinity") = { '
        + ', '.join(str(line) for line in air_boundary_lines)
        + ' };',
        '',
        'Mesh.ElementOrder = 2;',
        'Mesh.Algorithm = 6;  // Frontal-Delaunay',
    ]
    return '\n'.join(out) + '\n'


def emit_e_core_geo_3d(
    dims: ECoreDimensions,
    *,
    air_extent_factor_xy: float = 3.0,
    air_extent_factor_z: float = 2.0,
    with_gaps: bool = True,
) -> str:
    """
    Build .geo string для 3D E-core OPT (T133 Phase 3b/3d).

    Использует OpenCASCADE kernel для clean boolean operations. Topology
    — 4 Physical Volumes (core, primary, secondary, air) или 7 если
    `with_gaps=True` (+ gap_center, gap_left, gap_right). 1 Physical
    Surface "outer" (для Infinity BC или Dirichlet в .sif). Z-axis =
    core depth direction (out of front-view plane).

    Pipeline (with_gaps=True, Phase 3d):
    1. Box(1) = iron core outer block (full size).
    2. Box(2-3) = winding windows (through-holes from front to back faces).
    3. Box(4-6) = 3 gaps (center + 2 lateral, horizontal slits через core
       legs). PyOM lateral coords для OPT 6П14П SE extend за core
       boundary — Phase 3d использует **clamping** к `[-half_cw + GAP_INSET,
       half_cw - GAP_INSET]` чтобы gap boxes strictly inside core.
       Acceptance impact: clamped lateral gap = slightly narrower чем
       actual lateral leg (~7.5 mm vs 9.0 mm physical), но reluctance
       difference < 20% — well within 25% acceptance to ZHANG.
    4. Box(7) = outer air box (encloses everything).
    5. BooleanDifference: iron = Box(1) ∖ {Box(2-6)}, keeping cutouts.
    6. BooleanDifference: air = Box(7) ∖ {iron + all 5 cutouts}.
    7. Physical Volume tags для Body assignment в .sif.
    8. Outer surfaces — 6 thin-slab `Surface In BoundingBox` queries.

    Pipeline (with_gaps=False, Phase 3b smoke):
    Same но без Box(4-6) gaps; 4 Physical Volumes total.

    Args:
        dims: E-core geometry (same VO как 2D emit_e_core_geo).
        air_extent_factor_xy: outer box extent in xy direction
            (factor × max(core_w, core_h)). Default 3 — same as 2D
            `AIR_BOX_PADDING`.
        air_extent_factor_z: outer box z-padding before/after core depth
            (factor × core_depth). Default 2 — sufficient для magnetic
            decay в air above/below core.
        with_gaps: include 3 gaps (Phase 3d default True для acceptance);
            False — Phase 3b ungapped smoke.

    Notes:
        Mesh density tuned для 3D (tetrahedra grow faster than triangles):
        LC_CORE .. LC_AIR_FAR×3. Gaps refine mesh locally (LC_GAP=50μm).

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
    lat_w = dims.lateral_w
    lat_w / 2.0
    gap = dims.gap_len
    half_gap = gap / 2.0
    depth = dims.core_depth

    air_x = max(cw, ch) * air_extent_factor_xy / 2.0
    air_z_pad = depth * air_extent_factor_z

    win_left_x = -(half_cent_w + win_w)
    win_right_x = +half_cent_w

    # Gap x-bounds computed из core geometry (PyOM `lateral_x` interpretation
    # ambiguous для OPT 6П14П SE: lateral_x + half_lat_w = 22.6 mm > core
    # half-width 21.1 mm → gap boxes outside core). Geometrically lateral
    # legs occupy core boundary до winding window:
    #   - Left lateral: x ∈ [-half_cw, win_left_x]
    #   - Right lateral: x ∈ [win_right_x + win_w, half_cw]
    # Это согласовано с layout: |center| + 2|window| + 2|lateral| = core_w.
    # Lateral leg width = (core_w - center_w - 2·window_w) / 2.
    #
    # 3D OCC sliver tolerance: gap edges должны быть ≥ LC_GAP (50 μm)
    # от core boundary AND winding window edges, иначе mesh failed
    # с "overlapping facets" error на center gap left edge ↔ primary
    # window right edge (1 μm sliver). Inset = LC_GAP solves.
    gap_3d_inset = LC_GAP  # 50 μm — mesh-able sliver thickness

    # Center-leg gap — fully inside center leg [-half_cent_w, +half_cent_w]
    cent_gap_xmin = -half_cent_w + gap_3d_inset
    cent_gap_xmax = half_cent_w - gap_3d_inset
    cent_gap_w = cent_gap_xmax - cent_gap_xmin

    # Left lateral leg geometrically: x ∈ [-half_cw, win_left_x]
    lat_left_gap_xmin = -half_cw + gap_3d_inset
    lat_left_gap_xmax = win_left_x - gap_3d_inset
    lat_left_gap_w = lat_left_gap_xmax - lat_left_gap_xmin

    # Right lateral leg geometrically: x ∈ [win_right_x + win_w, +half_cw]
    lat_right_gap_xmin = win_right_x + win_w + gap_3d_inset
    lat_right_gap_xmax = half_cw - gap_3d_inset
    lat_right_gap_w = lat_right_gap_xmax - lat_right_gap_xmin

    # Slab thickness для outer-face queries — order LC_AIR_FAR (10 mm).
    slab = LC_AIR_FAR

    # Outer-face slab thickness — should encompass mesh element size at boundary.
    eps_xy = slab / 2.0
    eps_z = slab / 2.0
    z_min = -air_z_pad
    z_max = depth + air_z_pad

    air_x_2 = 2 * air_x
    z_span = z_max - z_min

    if with_gaps:
        # 7 Physical Volumes path: iron + 2 windings + 3 gaps + air.
        # Box tags: 1=core, 2=primary, 3=secondary, 4=gap_center,
        # 5=gap_left, 6=gap_right, 7=outer air.
        gap_boxes = f"""\
// Tag 4: center-leg gap (clamped to core)
Box(4) = {{ {cent_gap_xmin:.7g}, {-half_gap:.7g}, 0,
           {cent_gap_w:.7g}, {gap:.7g}, {depth:.7g} }};
// Tag 5: left lateral-leg gap (clamped to core)
Box(5) = {{ {lat_left_gap_xmin:.7g}, {-half_gap:.7g}, 0,
           {lat_left_gap_w:.7g}, {gap:.7g}, {depth:.7g} }};
// Tag 6: right lateral-leg gap (clamped to core)
Box(6) = {{ {lat_right_gap_xmin:.7g}, {-half_gap:.7g}, 0,
           {lat_right_gap_w:.7g}, {gap:.7g}, {depth:.7g} }};

// Tag 7: outer air box (encloses everything)
Box(7) = {{ {-air_x:.7g}, {-air_x:.7g}, {z_min:.7g},
           {air_x_2:.7g}, {air_x_2:.7g}, {z_span:.7g} }};

// === Boolean operations (sequential — robust для multi-cutouts) ===
iron1[] = BooleanDifference{{Volume{{1}}; Delete;}}{{Volume{{2}};}};
iron2[] = BooleanDifference{{Volume{{iron1[0]}}; Delete;}}{{Volume{{3}};}};
iron3[] = BooleanDifference{{Volume{{iron2[0]}}; Delete;}}{{Volume{{4}};}};
iron4[] = BooleanDifference{{Volume{{iron3[0]}}; Delete;}}{{Volume{{5}};}};
iron_with_holes[] = BooleanDifference{{Volume{{iron4[0]}}; Delete;}}{{Volume{{6}};}};
air_volume[] = BooleanDifference{{Volume{{7}}; Delete;}}
                                {{Volume{{iron_with_holes[0], 2, 3, 4, 5, 6}};}};

// === Physical Volume tags ===
Physical Volume("core", 1) = {{iron_with_holes[0]}};
Physical Volume("primary", 2) = {{2}};
Physical Volume("secondary", 3) = {{3}};
Physical Volume("gap_center", 4) = {{4}};
Physical Volume("gap_left", 5) = {{5}};
Physical Volume("gap_right", 6) = {{6}};
Physical Volume("air", 7) = {{air_volume[0]}};
"""
        n_phys_vols = 7
    else:
        # 4 Physical Volumes path (Phase 3b smoke): no gaps.
        gap_boxes = f"""\
// Tag 4: outer air box (encloses everything)
Box(4) = {{ {-air_x:.7g}, {-air_x:.7g}, {z_min:.7g},
           {air_x_2:.7g}, {air_x_2:.7g}, {z_span:.7g} }};

// === Boolean operations (no gaps) ===
iron_with_holes[] = BooleanDifference{{Volume{{1}}; Delete;}}{{Volume{{2, 3}};}};
air_volume[] = BooleanDifference{{Volume{{4}}; Delete;}}
                                {{Volume{{iron_with_holes[0], 2, 3}};}};

// === Physical Volume tags ===
Physical Volume("core", 1) = {{iron_with_holes[0]}};
Physical Volume("primary", 2) = {{2}};
Physical Volume("secondary", 3) = {{3}};
Physical Volume("air", 4) = {{air_volume[0]}};
"""
        n_phys_vols = 4

    return f"""// 3D E-core OPT — emit_e_core_geo_3d (with_gaps={with_gaps})
// Core depth (z-axis extent): {depth:.5g} m
// Outer air box: ±{air_x:.5g} m xy, [{z_min:.5g}, {z_max:.5g}] m z
//
// {n_phys_vols} Physical Volumes + 1 Physical Surface 100=outer.
SetFactory("OpenCASCADE");

Geometry.Tolerance = 1e-6;
Geometry.ToleranceBoolean = 1e-6;

Mesh.MeshSizeMin = {LC_GAP:.7g};
Mesh.MeshSizeMax = {LC_AIR_FAR * 3:.7g};
Mesh.Algorithm3D = 1;  // Delaunay
Mesh.ElementOrder = 1;  // Whitney AV edge basis — lowest order tetrahedra

// === Box primitives (OCC: x0, y0, z0, dx, dy, dz) ===
// Tag 1: iron core outer block (will be cut by windings + gaps)
Box(1) = {{ {-half_cw:.7g}, {-half_ch:.7g}, 0,
           {cw:.7g}, {ch:.7g}, {depth:.7g} }};

// Tag 2: primary winding window (left)
Box(2) = {{ {win_left_x:.7g}, {-half_win_h:.7g}, 0,
           {win_w:.7g}, {win_h:.7g}, {depth:.7g} }};
// Tag 3: secondary winding window (right)
Box(3) = {{ {win_right_x:.7g}, {-half_win_h:.7g}, 0,
           {win_w:.7g}, {win_h:.7g}, {depth:.7g} }};

{gap_boxes}

// === Outer boundary surfaces — 6 thin-slab queries ===
// `Surface In BoundingBox{{xmin, ymin, zmin, xmax, ymax, zmax}}` — gmsh
// OCC-aware конструкция, возвращает surface tags fully внутри box.
// Каждый slab охватывает одну outer face (с margin slab/2 в нормаль).
face_bottom() = Surface In BoundingBox{{
    {-air_x - 1:.7g}, {-air_x - 1:.7g}, {z_min - 1:.7g},
    {air_x + 1:.7g}, {air_x + 1:.7g}, {z_min + eps_z:.7g}
}};
face_top() = Surface In BoundingBox{{
    {-air_x - 1:.7g}, {-air_x - 1:.7g}, {z_max - eps_z:.7g},
    {air_x + 1:.7g}, {air_x + 1:.7g}, {z_max + 1:.7g}
}};
face_xmin() = Surface In BoundingBox{{
    {-air_x - 1:.7g}, {-air_x - 1:.7g}, {z_min - 1:.7g},
    {-air_x + eps_xy:.7g}, {air_x + 1:.7g}, {z_max + 1:.7g}
}};
face_xmax() = Surface In BoundingBox{{
    {air_x - eps_xy:.7g}, {-air_x - 1:.7g}, {z_min - 1:.7g},
    {air_x + 1:.7g}, {air_x + 1:.7g}, {z_max + 1:.7g}
}};
face_ymin() = Surface In BoundingBox{{
    {-air_x - 1:.7g}, {-air_x - 1:.7g}, {z_min - 1:.7g},
    {air_x + 1:.7g}, {-air_x + eps_xy:.7g}, {z_max + 1:.7g}
}};
face_ymax() = Surface In BoundingBox{{
    {-air_x - 1:.7g}, {air_x - eps_xy:.7g}, {z_min - 1:.7g},
    {air_x + 1:.7g}, {air_x + 1:.7g}, {z_max + 1:.7g}
}};

Physical Surface("outer", 100) = {{
    face_bottom(), face_top(),
    face_xmin(), face_xmax(),
    face_ymin(), face_ymax()
}};
"""


def _first_entry(
    raw: object,
    field_path: str,
    material_name: str,
) -> dict[str, Any]:
    """
    Извлечь первое (или единственное) entry из PyOM list/dict-поля.

    LookupError — поле пусто или отсутствует.
    TypeError    — поле есть, но shape не list/dict (malformed material data).
    """
    if isinstance(raw, list):
        if not raw:
            msg = f'material {material_name!r}: {field_path} список пуст'
            raise LookupError(msg)
        return raw[0]
    if isinstance(raw, dict):
        return raw
    if raw is None:
        msg = f'material {material_name!r}: {field_path} отсутствует'
        raise LookupError(msg)
    msg = (
        f'material {material_name!r}: {field_path} имеет неожиданный shape '
        f'({type(raw).__name__}); ожидался list или dict'
    )
    raise TypeError(msg)


def read_initial_permeability(mat: dict[str, Any], material_name: str) -> float:
    """Pull `permeability.initial[0].value` (or scalar dict fallback)."""
    perm = mat.get('permeability') or {}
    entry = _first_entry(perm.get('initial'), 'permeability.initial', material_name)
    value = entry.get('value')
    if value is None:
        msg = f'material {material_name!r}: permeability.initial[0].value is null'
        raise LookupError(msg)
    return float(value)


def read_saturation_flux_density(mat: dict[str, Any], material_name: str) -> float:
    """Pull `saturation[0].magneticFluxDensity` (or scalar dict fallback)."""
    entry = _first_entry(mat.get('saturation'), 'saturation', material_name)
    b_sat = entry.get('magneticFluxDensity')
    if b_sat is None:
        msg = f'material {material_name!r}: saturation[0].magneticFluxDensity is null'
        raise LookupError(msg)
    return float(b_sat)


def extract_frohlich_params(
    pyom_module: Any,  # noqa: ANN401  - dynamic .so module
    material_name: str,
) -> tuple[float, float]:
    """
    Read (mu_initial, B_sat) из PyOM `get_core_materials()` для material name.

    PyOM 1.3.10 MAS schema:
    - `material.permeability.initial` — list (frequency-dependent), берём [0]
      (low-frequency / 25°C convention).
    - `material.saturation` — list (temperature-dependent), берём [0].

    Raises:
        LookupError: material не найден, либо required поля пусты/отсутствуют.

    """
    for mat in pyom_module.get_core_materials():
        if mat.get('name') == material_name:
            return (
                read_initial_permeability(mat, material_name),
                read_saturation_flux_density(mat, material_name),
            )
    msg = f'material {material_name!r} не найден в PyOM catalog (get_core_materials)'
    raise LookupError(msg)

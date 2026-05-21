// T133 Phase 0 probe — минимальная 2-region геометрия для проверки
// синтаксиса H-B Curve и Infinity BC в Elmer 26.2 MagnetoDynamics2D.
//
// Геометрия:
//   - Внешний квадрат 2×2 (Air).
//   - Внутренний квадрат 0.5×0.5 (Iron, nonlinear material).
//   - Outer boundary = Physical Curve "Outer" → тестируем Infinity BC.
//
// Сетка крупная (lc=0.1) — нам нужна только parsability, не precision.

lc_air = 0.1;
lc_iron = 0.05;

// Outer (Air) box
Point(1) = {-1.0, -1.0, 0, lc_air};
Point(2) = { 1.0, -1.0, 0, lc_air};
Point(3) = { 1.0,  1.0, 0, lc_air};
Point(4) = {-1.0,  1.0, 0, lc_air};

Line(1) = {1, 2};
Line(2) = {2, 3};
Line(3) = {3, 4};
Line(4) = {4, 1};

// Inner (Iron) box
Point(5) = {-0.25, -0.25, 0, lc_iron};
Point(6) = { 0.25, -0.25, 0, lc_iron};
Point(7) = { 0.25,  0.25, 0, lc_iron};
Point(8) = {-0.25,  0.25, 0, lc_iron};

Line(5) = {5, 6};
Line(6) = {6, 7};
Line(7) = {7, 8};
Line(8) = {8, 5};

Curve Loop(1) = {1, 2, 3, 4};       // outer
Curve Loop(2) = {5, 6, 7, 8};       // iron (hole в air)

Plane Surface(1) = {2};              // Iron
Plane Surface(2) = {1, 2};           // Air (с дыркой под Iron)

// Physical tags — ElmerGrid mapping:
//   Surface tag 1 → Body 1 (Iron)
//   Surface tag 2 → Body 2 (Air)
//   Curve tag 3   → Boundary 1 (Outer)
Physical Surface("Iron", 1) = {1};
Physical Surface("Air", 2) = {2};
Physical Curve("Outer", 3) = {1, 2, 3, 4};

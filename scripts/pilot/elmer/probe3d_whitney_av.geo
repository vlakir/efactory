// T133 Phase 3a probe — минимальная 3D геометрия для проверки Elmer
// MagnetoDynamics Whitney AV solver. Iron cuboid 100×100×50 mm в Air box
// 400×400×300 mm (z down/up shells).
//
// Тестирует: gmsh `Extrude` 3D генерация → ElmerGrid 14 2 -autoclean
// → Whitney AV solver + tree gauge + MUMPS direct linear (5.26 s CPU
// на 9641 nodes / 45981 tetrahedra; converged NRM=4.2e-9).

lc_iron = 0.005;
lc_air = 0.02;

// Iron cuboid 100 × 100 × 50 mm
Point(1) = {-0.05, -0.05, 0, lc_iron};
Point(2) = { 0.05, -0.05, 0, lc_iron};
Point(3) = { 0.05,  0.05, 0, lc_iron};
Point(4) = {-0.05,  0.05, 0, lc_iron};
Line(1) = {1, 2};
Line(2) = {2, 3};
Line(3) = {3, 4};
Line(4) = {4, 1};
Curve Loop(1) = {1, 2, 3, 4};
Plane Surface(1) = {1};
iron_extrude[] = Extrude {0, 0, 0.05} { Surface{1}; };
// iron_extrude[0] = top surface, [1] = volume tag

// Air outer box 400 × 400 × 300 mm
Point(100) = {-0.2, -0.2, -0.1, lc_air};
Point(101) = { 0.2, -0.2, -0.1, lc_air};
Point(102) = { 0.2,  0.2, -0.1, lc_air};
Point(103) = {-0.2,  0.2, -0.1, lc_air};
Line(101) = {100, 101};
Line(102) = {101, 102};
Line(103) = {102, 103};
Line(104) = {103, 100};
Curve Loop(100) = {101, 102, 103, 104};
Plane Surface(100) = {100};
air_extrude[] = Extrude {0, 0, 0.3} { Surface{100}; };

// Air volume = outer box ∖ iron block (Volume() с двумя shells = hole)
v_air = newv;
Volume(v_air) = {air_extrude[1], iron_extrude[1]};

Physical Volume("iron", 1) = {iron_extrude[1]};
Physical Volume("air", 2) = {v_air};
// Outer boundary surfaces (для Dirichlet или Infinity BC в .sif)
Physical Surface("outer", 3) = {
  air_extrude[0],  // top
  air_extrude[2],  // side 1
  air_extrude[3],  // side 2
  air_extrude[4],  // side 3
  air_extrude[5],  // side 4
  100              // bottom (original surface 100)
};

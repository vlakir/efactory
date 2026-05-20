// T113 Phase 1 pilot — GetDP 2D-planar magnetostatic for OPT 6П14П SE
//
// Computes primary self-inductance L_p via energy method:
//   L_p = 2 W / I_ref²
// where W is total magnetic field energy in the 3D-equivalent volume
// (W = W_per_depth × core_depth) при I_ref = 1 A через 2500-витковый
// primary.
//
// Physical groups read from geometry.msh (auto-generated from geometry.geo
// by scripts/pilot/mas_to_gmsh.py; PG tags 1-7 = surfaces, 8 = infinity
// curve).
//
// Material: Nanoperm 8000, μ_r = 8000 (initial — linear approximation для
// pilot; nonlinear B-H curve — Phase 2 integration follow-up если pilot
// показывает достаточную close к analytical).

Group {
  Core      = Region[1];
  Primary   = Region[2];
  Secondary = Region[3];
  GapC      = Region[4];
  GapL      = Region[5];
  GapR      = Region[6];
  Air       = Region[7];
  Infinity  = Region[8];

  Iron     = Region[{Core}];
  NonIron  = Region[{Primary, Secondary, GapC, GapL, GapR, Air}];
  Domain   = Region[{Iron, NonIron}];
  Coil     = Region[{Primary}];
}

Function {
  mu0      = 4*Pi*1e-7;       // [H/m]
  mur_iron = 8000;            // Nanoperm 8000 μ_initial

  nu[Iron]     = 1.0 / (mu0 * mur_iron);
  nu[NonIron]  = 1.0 / mu0;

  // Primary winding (2500 витков, 1 A reference) wraps around центральную
  // ножку: ВВЕРХ через LEFT window, ВНИЗ через RIGHT window. В 2D-planar
  // это +Jz в Primary и -Jz в Secondary (Secondary PG здесь reinterpreted
  // как возвратная сторона primary; реальный secondary winding не
  // энергизован для self-inductance расчёта).
  //
  // Без знакового расщепления тока — это одиночный прямой провод,
  // а не coil, и Lp получается завышенной в ~2.8× (эмпирически).
  //
  // js[] возвращает Vector[0,0,Jz]: BF_PerpendicularEdge делает {a}
  // z-направленным, поэтому source тоже должен быть z-вектором.
  N_primary    = 2500;
  I_ref        = 1.0;
  area_window  = 9.075e-3 * 30.3e-3;
  J_density    = N_primary * I_ref / area_window;

  js[Primary]   = Vector[0, 0,  J_density];
  js[Secondary] = Vector[0, 0, -J_density];
}

Constraint {
  { Name MVP_2D;
    Case {
      { Region Infinity; Value 0.; }
    }
  }
}

FunctionSpace {
  { Name Hcurl_a_2D; Type Form1P;
    BasisFunction {
      { Name sn; NameOfCoef an;
        Function BF_PerpendicularEdge;
        Support Domain; Entity NodesOf[All]; }
    }
    Constraint {
      { NameOfCoef an; EntityType NodesOf; NameOfConstraint MVP_2D; }
    }
  }
}

Jacobian {
  { Name Vol; Case { { Region All; Jacobian Vol; } } }
}

Integration {
  { Name I1;
    Case {
      { Type Gauss;
        Case {
          { GeoElement Triangle;  NumberOfPoints  3; }
          { GeoElement Triangle2; NumberOfPoints  6; }
          { GeoElement Line;      NumberOfPoints  1; }
          { GeoElement Line2;     NumberOfPoints  3; }
        }
      }
    }
  }
}

Formulation {
  { Name Magnetostatics_2D; Type FemEquation;
    Quantity {
      { Name a; Type Local; NameOfSpace Hcurl_a_2D; }
    }
    Equation {
      Galerkin { [ nu[] * Dof{d a}, {d a} ];
                 In Domain; Jacobian Vol; Integration I1; }
      Galerkin { [ -js[], {a} ];
                 In Primary;   Jacobian Vol; Integration I1; }
      Galerkin { [ -js[], {a} ];
                 In Secondary; Jacobian Vol; Integration I1; }
    }
  }
}

Resolution {
  { Name Mag2D;
    System {
      { Name A; NameOfFormulation Magnetostatics_2D; }
    }
    Operation {
      Generate[A]; Solve[A]; SaveSolution[A];
      PostOperation[Mag2D];
    }
  }
}

PostProcessing {
  { Name Mag2D; NameOfFormulation Magnetostatics_2D;
    Quantity {
      { Name a; Value { Local { [ {a} ];   In Domain; Jacobian Vol; } } }
      { Name b; Value { Local { [ {d a} ]; In Domain; Jacobian Vol; } } }
      // Magnetic energy per unit depth (J/m): ∫ ½ ν |B|² dS
      { Name energy_per_depth;
        Value {
          Integral { [ 0.5 * nu[] * {d a} * {d a} ];
                     In Domain; Jacobian Vol; Integration I1; }
        }
      }
    }
  }
}

PostOperation {
  { Name Mag2D; NameOfPostProcessing Mag2D;
    Operation {
      // Field outputs for inspection (Gmsh .pos format)
      Print[ a, OnElementsOf Domain, File "a.pos" ];
      Print[ b, OnElementsOf Domain, File "b.pos" ];
      // Scalar energy → Table format (single numeric value, легко парсить)
      Print[ energy_per_depth[Domain], OnGlobal, Format Table,
             File "energy_per_depth.txt" ];
    }
  }
}

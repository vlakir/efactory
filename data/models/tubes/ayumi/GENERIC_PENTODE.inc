* Generic Ayumi-style pentode (T006 example, not physically accurate).
*
* Demonstrates Ayumi formula style with `^` exponent — adapter
* converts to ngspice `**` on read (T006 Resolved #4).
* tube_type: pentode
* Pins: P (plate), G2 (screen), G (grid), K (cathode)
*
* Replace with vendor-fitted parameters before using in a real design.
.SUBCKT GENERIC_PENTODE P G2 G K
* Plate current — Ayumi-style with `^` exponent, converted on read.
Bp P K I=0.05m * (V(G2,K)/200 + V(G,K))^1.5
* Screen current — small fraction of plate.
Bs G2 K I=0.01m * (V(G2,K)/200 + V(G,K))^1.5
* Inter-electrode capacitances (typical EL34 ballpark).
Cgk G K 15p
Cg2k G2 K 8p
Cpk P K 6p
.ENDS GENERIC_PENTODE

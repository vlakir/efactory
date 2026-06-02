* 6922 / EH 6922 / E88CC special — brand variant of 6DJ8/ECC88 dual triode.
*
* Functionally identical к 6DJ8 — selected for low noise / matching /
* extended ratings (EH 6922 specifically Electro-Harmonix premium select).
* SPICE parameters from Ayumi 6DJ8 dataset (same family).
*
* ngspice-syntax из коробки (T166 2026-06-02): степень через `**`,
* signed power — `sgn(x)*pwr(abs(x), y)`. Не требует converter passes
* для `.include` workflow.
*
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode) — single section.
.SUBCKT 6922 P G K
* MU=33 EX=1.43 KG1=270 KP=145 KVB=300 (Ayumi 6DJ8 dataset)
E1 7 0 VALUE={V(P,K)/145*LN(1+EXP(145*(1/33+V(G,K)/SQRT(300+V(P,K)**2))))}
G1 P K VALUE={(sgn(V(7))*pwr(abs(V(7)),1.43)+sgn(V(7))*pwr(abs(V(7)),1.43))/270}
C1 G K 3.3p
C2 G P 1.4p
C3 P K 0.18p
RGI G K 1MEG
.ENDS 6922

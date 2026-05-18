* 211 (VT-4-C) — transmitting triode (~12 W SE, RF / hi-end audio).
*
* Ayumi-style triode formula. Низкая внутренняя гф, требует Va ~1000V.
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode, thoriated-tungsten filament).
.SUBCKT 211 P G K
* MU=12 EX=1.4 KG1=4500 KP=80 KVB=300
E1 7 0 VALUE={V(P,K)/80*LN(1+EXP(80*(1/12+V(G,K)/SQRT(300+V(P,K)^2))))}
G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/4500}
C1 G K 6p
C2 G P 14.5p
C3 P K 4.5p
RGI G K 1MEG
.ENDS 211

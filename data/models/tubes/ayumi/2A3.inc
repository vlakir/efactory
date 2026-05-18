* 2A3 — directly-heated power triode (~3.5 W SE, классика 1930-х).
*
* Ayumi-style triode formula (`^` оператор → конвертируется в `**`).
* Параметры из Ayumi published dataset.
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode, filament center-tap).
.SUBCKT 2A3 P G K
* MU=4.2 EX=1.4 KG1=1500 KP=80 KVB=300
E1 7 0 VALUE={V(P,K)/80*LN(1+EXP(80*(1/4.2+V(G,K)/SQRT(300+V(P,K)^2))))}
G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/1500}
C1 G K 7.5p
C2 G P 16.5p
C3 P K 5.5p
RGI G K 1MEG
.ENDS 2A3

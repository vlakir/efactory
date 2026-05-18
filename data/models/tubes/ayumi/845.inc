* 845 — directly-heated transmitting triode (~20 W SE, high-voltage 1kV+).
*
* Ayumi-style triode formula. Требует Va ~1000-1250V; hi-end DHT amps.
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode, thoriated-tungsten filament).
.SUBCKT 845 P G K
* MU=5.3 EX=1.4 KG1=2500 KP=80 KVB=300
E1 7 0 VALUE={V(P,K)/80*LN(1+EXP(80*(1/5.3+V(G,K)/SQRT(300+V(P,K)^2))))}
G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/2500}
C1 G K 6p
C2 G P 14p
C3 P K 3p
RGI G K 1MEG
.ENDS 845

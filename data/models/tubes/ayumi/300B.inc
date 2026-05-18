* 300B — directly-heated power triode (~8 W SE, легендарный hi-end).
*
* Ayumi-style triode formula (использует `^` оператор — на чтении
* конвертируется в ngspice `**` адаптером T006).
* Approximate parameters from published 300B curves; production
* fitting через T031.
*
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode).
.SUBCKT 300B P G K
* MU=3.85 EX=1.4 KG1=1500 KP=80 KVB=300
E1 7 0 VALUE={V(P,K)/80*LN(1+EXP(80*(1/3.85+V(G,K)/SQRT(300+V(P,K)^2))))}
G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/1500}
C1 G K 8.5p
C2 G P 14p
C3 P K 4.3p
RGI G K 1MEG
.ENDS 300B

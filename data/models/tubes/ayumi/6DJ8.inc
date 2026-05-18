* 6DJ8 / ECC88 / E88CC — high-gm dual triode (RF, audiophile preamp).
*
* Ayumi-style triode formula с `^` оператором (конвертируется на чтении
* в `**`). Параметры — typical sample из Ayumi published dataset.
*
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode) — single section.
.SUBCKT 6DJ8 P G K
* MU=33 EX=1.43 KG1=270 KP=145 KVB=300
E1 7 0 VALUE={V(P,K)/145*LN(1+EXP(145*(1/33+V(G,K)/SQRT(300+V(P,K)^2))))}
G1 P K VALUE={(PWRS(V(7),1.43)+PWRS(V(7),1.43))/270}
C1 G K 3.3p
C2 G P 1.4p
C3 P K 0.18p
RGI G K 1MEG
.ENDS 6DJ8

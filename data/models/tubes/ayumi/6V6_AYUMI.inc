* 6V6 — alternative Ayumi-style fit (beam tetrode, ~12 W).
*
* Параллельная Koren-моделью реализация для сравнения fit'ов.
* Ayumi подход с `^` оператором.
* tube_type: pentode
* Pins: P (plate), G2 (screen), G (grid 1), K (cathode).
.SUBCKT 6V6_AYUMI P G2 G K
* MU=10.85 EX=1.31 KG1=1672 KG2=4200 KP=58 KVB=14
E1 7 0 VALUE={V(G2,K)/58*LN(1+EXP(58*(1/10.85+V(G,K)/V(G2,K))))}
G1 P K VALUE={(PWRS(V(7),1.31)+PWRS(V(7),1.31))/1672 * ATAN(V(P,K)^1/14)}
G2 G2 K VALUE={(PWRS(V(7),1.31)+PWRS(V(7),1.31))/4200}
C1 G K 9p
C2 G P 0.7p
C3 P K 7.5p
RGI G K 1MEG
.ENDS 6V6_AYUMI

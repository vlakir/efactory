* GENERIC_PENTODE — Ayumi-style pentode formatting reference.
*
* Файл-пример формата для пользователей; не реальная лампа.
* Использует `^` оператор (Ayumi-syntax) — на чтении заменяется
* на `**` (ngspice-syntax) адаптером `tube_models`.
*
* Для реальных pentode/tetrode см. koren/EL34.lib, 6L6.lib, etc.
*
* tube_type: pentode
* Pins: P (plate), G2 (screen), G (grid 1), K (cathode).
.SUBCKT GENERIC_PENTODE P G2 G K
* MU=10 EX=1.35 KG1=700 KG2=4500 KP=60 KVB=20
E1 7 0 VALUE={V(G2,K)/60*LN(1+EXP(60*(1/10+V(G,K)/V(G2,K))))}
G1 P K VALUE={(PWRS(V(7),1.35)+PWRS(V(7),1.35))/700 * ATAN(V(P,K)^1/20)}
G2 G2 K VALUE={(PWRS(V(7),1.35)+PWRS(V(7),1.35))/4500}
C1 G K 12p
C2 G P 1p
C3 P K 8p
RGI G K 1MEG
.ENDS GENERIC_PENTODE

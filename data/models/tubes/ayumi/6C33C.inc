* 6C33C-B — Russian high-gm low-rp power triode (~30 W SE, OTL amps).
*
* Ayumi-style triode. Изначально для регуляторов в советской военной
* аппаратуре; стала культовой для OTL hi-fi (Atma-Sphere и др.).
*
* ngspice-syntax из коробки (T167 2026-06-02): степень через `**`,
* signed power — `sgn(x)*pwr(abs(x), y)`. Не требует converter passes
* для `.include` workflow.
*
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode).
.SUBCKT 6C33C P G K
* MU=2.6 EX=1.45 KG1=350 KP=60 KVB=300
E1 7 0 VALUE={V(P,K)/60*LN(1+EXP(60*(1/2.6+V(G,K)/SQRT(300+V(P,K)**2))))}
G1 P K VALUE={(sgn(V(7))*pwr(abs(V(7)),1.45)+sgn(V(7))*pwr(abs(V(7)),1.45))/350}
C1 G K 30p
C2 G P 26p
C3 P K 14p
RGI G K 1MEG
.ENDS 6C33C

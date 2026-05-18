* 6080 / 6AS7G — low-mu dual power triode (audio regulators, OTL drivers).
*
* Ayumi-style triode formula. Low rp (~280 Ω); популярна в OTL и
* линейных регуляторах БП.
* tube_type: triode
* Pins: P (plate), G (grid), K (cathode) — single section.
.SUBCKT 6080 P G K
* MU=2.0 EX=1.45 KG1=1500 KP=80 KVB=300
E1 7 0 VALUE={V(P,K)/80*LN(1+EXP(80*(1/2.0+V(G,K)/SQRT(300+V(P,K)^2))))}
G1 P K VALUE={(PWRS(V(7),1.45)+PWRS(V(7),1.45))/1500}
C1 G K 6p
C2 G P 8p
C3 P K 2.2p
RGI G K 1MEG
.ENDS 6080

# T70/T77 — L'instrument rendu : l'étalon money, le biais de sa passe 1, la carte d'erreur

**Date** : 2026-09-02. **Fiches** : T70 (P1, l'arbitre externe escaladé), T77 (P8, la carte
d'erreur par classe). **Registre** : `docs/corpus/t70/money-10000/registre-money.jsonl`,
10 000 décisions, contexte money, corpus figé de sha256
`be7e73bf2980e89adc50175f35590ad9ac1bbae873e6d9bc16950e240a4b34ca`.

## Ce que ce document rend

L'instrument de T70 est **complet** : les 10 000 décisions disputées du corpus money sont
arbitrées, aucune ne manque. Trois chiffres en sortent, et un seul est un verdict de force —
aucun.

| Ce qui est mesuré | Valeur | IC 95 % (bootstrap 10 000) |
|---|---|---|
| Perte d'équité de l'incumbent 2-ply, par décision disputée | **0,00313** | [0,00298 ; 0,00327] |
| Pénalité de la passe 1 sur ses propres verdicts réaudités | 0,00320 | [0,00256 ; 0,00400] |
| Contribution de cette pénalité au registre entier | ~0,00149 | produit de deux mesures |

**Coût d'un point de comparaison** : 1 898 s de mur sur 30 processus, soit **15,82 h·cœur**. La
fiche demandait « des heures, pas des jours » pour que T71 soit engageable. C'est tenu.

## L'étalon — l'incumbent sur son propre registre

10 000 décisions notées, **zéro hors registre**. 434 décisions (4,34 %) où le coup joué n'était
que borné parce que dominé ; 193 (1,93 %) restées ouvertes.

| Classe | n | Perte par décision |
|---|---|---|
| backgame | 433 | 0,00603 |
| prime_vs_prime | 456 | 0,00403 |
| contact | 5 004 | 0,00320 |
| blitz | 1 251 | 0,00297 |
| crashed | 428 | 0,00293 |
| bearoff_contact | 582 | 0,00274 |
| race_contact | 669 | 0,00271 |
| holding | 1 177 | 0,00245 |

**500 × ce chiffre (1,563) n'est pas un PR.** Le corpus ne contient que les décisions disputées,
environ 10 % du total, et les décisions écartées ne portent pas une perte nulle : les deux
moteurs y jouent le même coup, pas forcément le meilleur. Le PR du projet reste celui de T3E
(`bench/pr.py`), 0,273 au 2-ply.

## Le biais de la passe 1

497 décisions tranchées en passe 1 (gnubg 3-ply) ont été réaudité en passe 2. **219, soit 44,1 %,
désignent un autre coup après escalade.** La pénalité d'équité correspondante est 0,00320 par
décision auditée. 4 664 décisions du registre (46,6 %) ont été tranchées en passe 1, d'où une
contribution d'environ 0,00149 par décision au registre entier.

Répartition des passes : 4 664 en passe 1, 2 721 en passe 2, 2 615 en passe 3.

**Ce chiffre mesure l'écart de la passe 1 à la passe 2, jamais à la vérité.** Si le rollout
tronqué était lui-même biaisé, cet écart le manquerait entièrement — c'est
`bench/arbiter_bias_t70.py`, contre les tables exactes, qui répond à cette autre question
(`docs/mesures/t70-non-biais-300.json`). Les deux contrôles sont requis, et les deux ont tourné.

## T77 — la carte d'erreur : aucun découpage

Seuil DS-12, écrit avant la mesure : une classe justifie une tête dédiée si son erreur dépasse
**2,0×** la moyenne **et** qu'elle pèse plus de **5 %** des décisions réelles.

| Classe | Erreur / moyenne | Poids réel | Déclenche |
|---|---|---|---|
| backgame | 1,93× | 2,43 % | non |
| prime_vs_prime | 1,29× | 4,10 % | non |
| contact | 1,02× | 54,81 % | non |
| blitz | 0,95× | 11,99 % | non |
| crashed | 0,94× | 3,56 % | non |
| bearoff_contact | 0,88× | 5,65 % | non |
| race_contact | 0,87× | 6,30 % | non |
| holding | 0,78× | 11,16 % | non |

**Aucune classe ne franchit les deux seuils.** Le backgame est bien deux fois plus coûteux que la
moyenne, mais il ne pèse que 2,4 % des décisions réelles ; les classes lourdes sont toutes proches
de la moyenne. DS-12 conclut : **aucun découpage**. L'aiguillage dur par classe est mesuré neutre
sur ce corpus, et l'on ne spécialise pas par principe. T77 se referme sur ce verdict.

## Ce qui a rendu ces chiffres possibles, et qui a failli les fausser

L'arbitrage du reliquat a tourné sur deux machines. Un désaccord de build de gnubg entre elles a
été corrigé à la racine le 2026-09-01 : melbaa exécutait un instantané git ultérieur (build
20260827), mochy le tarball de release épinglé (build 20250313, sha256 `6f7d969b…c445979`).
melbaa a été recompilée depuis le même tarball. C'est la source, pas le CPU, qui expliquait
l'écart de ±0,005 PR observé en T3E.

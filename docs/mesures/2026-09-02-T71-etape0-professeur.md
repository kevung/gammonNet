# T71 étape 0 — le professeur bat l'élève, et l'étape 1 a sa prémisse

**Date** : 2026-09-02. **Fiche** : T71 (P2, distiller notre 2-ply). **Banc** :
`bench/etape0_t71.py`. **Registre** : `docs/corpus/t70/money-10000/registre-money.jsonl`,
10 000 décisions disputées, contexte money.

## La règle d'or de DS-14, et pourquoi cette mesure vient en premier

Le piège n°1 documenté de la distillation est le **plafond du professeur** : un élève converge
vers la force de son maître, quelle que soit la quantité de données qu'on lui donne. Avant de
dépenser des heures à étiqueter un million de positions, il faut donc vérifier que le maître
vaut mieux que l'élève. Le seuil est écrit dans la fiche avant la mesure : **z > 3 sur au moins
10 000 décisions appariées**.

## Le résultat

| | |
|---|---|
| Décisions appariées | **10 000 / 10 000** |
| Non appariables | 0 (0,00 %) |
| Avance du professeur 2-ply sur l'élève 0-ply | **+0,00213 par décision** |
| IC 95 % (bootstrap 10 000) | [+0,00194 ; +0,00233] |
| z | **21,55** (seuil de la fiche : 3) |
| Coût | 15,98 h·cœur, 30 processus |

**Verdict : professeur confirmé.** L'étape 1 de T71 a sa prémisse.

## Par classe de position

| Classe | n | Avance | IC 95 % |
|---|---|---|---|
| blitz | 1 251 | +0,00274 | [+0,00220 ; +0,00330] |
| backgame | 433 | +0,00258 | [+0,00141 ; +0,00378] |
| contact | 5 004 | +0,00228 | [+0,00199 ; +0,00256] |
| race_contact | 669 | +0,00214 | [+0,00152 ; +0,00278] |
| prime_vs_prime | 456 | +0,00196 | [+0,00091 ; +0,00302] |
| holding | 1 177 | +0,00192 | [+0,00145 ; +0,00243] |
| bearoff_contact | 582 | +0,00067 | [+0,00008 ; +0,00125] |
| crashed | 428 | +0,00048 | [−0,00026 ; +0,00120] |

Deux classes n'ont presque rien à apprendre de la recherche : `bearoff_contact`, où la table
exacte tranche déjà, et `crashed`, dont l'intervalle contient zéro. Partout ailleurs la recherche
ajoute une information que le réseau seul n'a pas.

## Ce que ce z n'est pas

**Ce n'est pas une mesure de force absolue.** Le corpus est conditionné sur le désaccord 2-ply
avec gnubg : il ne contient que des décisions où deux moteurs divergent, donc des positions où
l'évaluation statique est déjà en difficulté. L'avance mesurée y est plus grande que sur une
partie ordinaire. Ce que le chiffre établit est exactement ce que la règle d'or demande — que le
professeur ne soit pas plafonné au niveau de l'élève — et rien de plus.

Le critère de succès de l'étape 1 est ailleurs, et il est écrit dans la fiche : l'intervalle
2-ply par décision contre l'arbitre, aujourd'hui [−0,00005 ; +0,00019] (T36), doit **se déplacer
au-dessus de zéro**. Le 0-ply montera trivialement et ne prouvera rien.

## L'écart avec l'étalon, lu ensemble

L'étalon T70 du même jour donne 0,00313 de perte par décision pour l'incumbent 2-ply
(`2026-09-02-T70-etalon-money.md`). L'avance du 2-ply sur le 0-ply vaut 0,00213. Les deux se
lisent ensemble : sur ce corpus, la recherche récupère environ 40 % de ce qui sépare le réseau
statique de l'arbitre, et il reste 0,00313 que ni le réseau ni la recherche à deux plis ne
voient. C'est cette part-là que l'étape 1 vise.

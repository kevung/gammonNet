# 2026-10-15 — T72 : la distillation 0-ply plafonne, quel que soit le volume

**Nature** : des **mesures**. Élèves entraînés le 2026-10-13 par `tools/distill_volume_t72.py`
sur les étiquettes 0-ply du professeur `cubeless_prob5_512_512_256_256` (corpus
`build_distill_corpus`, graine 20261013, validation 400 000 lignes). Chaque élève est noté sur
le registre T70 money (10 000 décisions disputées), 2-ply `(0,1,5)`, `prune_32` à `k=12`,
20 processus sur melbaa. IC 95 % par bootstrap (10 000 tirages), **non appariés** entre
lignes. JSON bruts et résumés d'entraînement : `t72-distillation/`.

Deux formes d'élève : **prof** (la forme du professeur, 560 384 MACs) et **cible**
(256-128-64, 91 456 MACs — la taille visée pour la vitesse).

## La courbe volume → perte en décision

| Lignes d'entraînement | prof : perte T70 | cible : perte T70 | prof : écart de validation | cible : écart de validation |
|---|---|---|---|---|
| 0,8 M | 0,00901 [0,00849 ; 0,00955] | 0,01031 [0,00973 ; 0,01093] | 0,00635 | 0,00855 |
| 3,2 M | 0,00839 [0,00784 ; 0,00895] | 0,00968 [0,00910 ; 0,01030] | 0,00414 | 0,00685 |
| 12,8 M | 0,00828 [0,00771 ; 0,00884] | 0,00942 [0,00887 ; 0,00999] | 0,00363 | 0,00590 |
| 51,2 M | 0,00831 [0,00775 ; 0,00889] | 0,01009 [0,00946 ; 0,01074] | 0,00343 | 0,00574 |
| 51,2 M, cosinus 1 000 époques | 0,00797 [0,00741 ; 0,00857] | 0,00886 [0,00828 ; 0,00945] | 0,00205 | 0,00438 |
| **professeur** | **0,00266** [0,00253 ; 0,00279] | | | |

(« écart de validation » = `holdout_mean_abs`, écart moyen absolu aux sorties du professeur.)

## Ce que ça dit

- **Le volume fait baisser l'écart de validation, pas la perte en décision.** De 0,8 M à
  51,2 M lignes, l'écart de l'élève prof est divisé par 1,9 ; sa perte T70 ne bouge plus
  au-delà de 3,2 M (intervalles confondus).
- **Le calendrier cosinus long aide un peu**, surtout l'élève cible (0,01009 → 0,00886, IC
  presque disjoints mais non appariés : à confirmer par une comparaison appariée avant d'en
  faire un acquis).
- **Le fait central** : l'élève **de la forme même du professeur** reste à ~3 fois sa perte
  (0,00797 contre 0,00266), alors que son écart de validation n'est plus que de 0,002. La
  capacité n'est donc pas ce qui manque ; c'est l'objectif. Un écart moyen absolu de 0,002
  sur les probabilités suffit à inverser des coups frères dont les équités sont proches —
  et c'est exactement ce que T70 compte.

## Ce que ça ne dit pas

- Rien sur la force en partie : T70 est une perte par décision disputée, pas un PR (voir la
  note de `bench/measure_t70.py`).
- Rien sur un objectif de **classement** entre coups frères : c'est l'hypothèse suivante, non
  testée — le corpus de distillation ne porte pas d'indice de décision, il faudrait l'ajouter
  au générateur. Ce travail n'est pas engagé : c'est une piste de recherche à ouvrir, pas une
  suite à dérouler.

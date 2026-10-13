# Filtres de coups à 3 et 4 plis, racine étagée (issue #31)

**Date** : 2026-10-11 · **Machine** : poste de bureau, 16 fils, Linux 7.2.9-arch1-1 ·
**Branche** : `feat/racine-etagee` · **Instrument** : `bench/deep_root.py` · **Corpus** :
`docs/mesures/deep-root-test-sgf.jsonl` (274 décisions de coup non forcées de `test.sgf`, un
match réel en 7 points, au score réel) · **Résultats** : `docs/mesures/deep-root-3ply.jsonl`,
`docs/mesures/deep-root-4ply.jsonl` · **Spec** : `docs/specs/filtre-de-coups-spec.md` §6, §8

> **Machine chargée — les évaluations sont le coût, pas les secondes.** D'autres chantiers
> occupaient la machine (charge 13 à 39 sur 16 fils) pendant toutes les passes. Une même
> décision a coûté 66 s puis 107 s pour le même nombre d'évaluations. Les évaluations du grand
> réseau ne dépendent pas de la charge ; les secondes sont données pour l'ordre de grandeur.

## La question

1. Le vecteur de filtres à 3 et 4 plis : une seule réplique `(1, 0, 0)` à chaque nœud intérieur
   (déjà retenu côté blunderDB) contre l'ancien « 5 coups ».
2. La racine : choisir les candidats payés à `k` plis sur le classement 0-ply (`filter[k] =
   (1, 2, 0,04)`, la racine de `normal`), ou d'abord sur un classement à 2 plis (racine
   étagée, spec §8).

## Les formes

Toutes élaguées à `k = 12`, cubeless, au score réel ; intérieur `(1, 0, 0)` sauf `old`.

| nom | intérieur | étage | racine |
|---|---|---|---|
| `old` (3 plis) | profondeur 2 : `(1, 2, 0,04)` | — | `(5, 0, 0)` |
| `direct` (avant) | `(1, 0, 0)` | — | `(1, 2, 0,04)` |
| `staged_canonical` | `(1, 0, 0)` | 2 plis, `(1, 2, 0,04)` | `(0, 2, 0,04)` |
| `staged_wide` (**retenue**) | `(1, 0, 0)` | 2 plis, `(0, 8, 0,16)` | `(0, 2, 0,04)` |
| `ref_inner1` / `ref` | `(1, 0, 0)` | — | `(0, 8, 0,16)` |
| `ref_unpruned` | comme `staged_wide`, sans élagage | | |

**Perte** d'une forme : `REF(meilleur) − REF(coup choisi)`, `REF` étant la valeur `k` plis du
coup sous la référence (contrôle : la référence relit son propre choix à 0 près, 0,000e+00 sur
toutes les décisions). Nous contre nous : la référence dit ce qu'une racine plus large aurait
choisi, pas la force.

## 3 plis — 40 décisions (une sur 7 du match)

`python bench/deep_root.py measure --ply 3 --workers 14 --every 7 --only old direct
staged_canonical staged_wide ref_inner1 ref_unpruned`

| forme | évals moy. | vs `direct` | perte vs `ref_inner1` | ≠ réf. |
|---|---|---|---|---|
| `old` | 853 914 | ×4,8 | 0,000003 | 1 |
| `direct` | 179 277 | — | 0 | 0 |
| `staged_canonical` | 138 044 | −23 % | 0 | 0 |
| `staged_wide` | 151 696 | −15 % | 0 | 0 |
| `ref_inner1` | 476 748 | ×2,7 | (réf.) | — |

Les trois formes à intérieur `(1, 0, 0)` choisissent **le même coup sur les 40 décisions**,
celui de la racine large. Temps, un seul processus, ordre alterné, mêmes 40 décisions :
`direct` 9,85 s, `staged_wide` 8,32 s par décision (−16 %).

## 4 plis — 14 décisions (une sur 20 du match)

`python bench/deep_root.py measure --ply 4 --workers 14 --every 20`

| forme | évals moy. | vs `direct` | perte vs `ref` | IC 95 % | ≠ réf. |
|---|---|---|---|---|---|
| `direct` | 4 163 227 | — | 0,000013 | [0 ; 0,000040] | 1 |
| `staged_canonical` | 2 981 419 | −28 % | 0,000013 | [0 ; 0,000040] | 1 |
| `staged_wide` | 2 993 865 | −28 % | **0** | [0 ; 0] | **0** |
| `ref` | 11 907 258 | ×2,9 | (réf.) | | — |

`staged_wide` choisit le coup de la racine large sur les 14 décisions ; `direct` et
`staged_canonical` le manquent une fois (perte 0,00019). Le gain d'évaluations est nul sur les
décisions où l'étage ne coupe pas (5 sur 14, ±1 %) et de 29 à 48 % sur les 9 autres. Temps, un
seul processus, 4 décisions, ordre alterné : 149,5 s contre 151,7 s — sous la charge du moment,
ces secondes ne suivent pas les évaluations (l'ouverture 51 : 5,9 M contre 4,0 M évaluations,
194 s contre 270 s) et ne concluent rien ; les évaluations font foi.

## Le coût de l'élagage aux niveaux `ply3` / `ply4`

La forme retenue contre elle-même non élaguée (`ref_unpruned`), même protocole :

| niveau | décisions | perte moy. | IC 95 % (bootstrap) | ≠ |
|---|---|---|---|---|
| `ply3` | 40 | 0,000043 | [0 ; 0,000125] | 2 |
| `ply4` | 14 | 0,000478 | [0 ; 0,001435] | 1 |

À 4 plis, une seule décision porte toute la perte (0,0067) : l'intervalle est large parce que
l'échantillon est petit, pas parce que l'élagage coûte davantage en moyenne. Ces nombres sont
les champs `prune_equity_loss` des deux niveaux (`src/gn_search.c`).

## Décision

Publié en niveaux natifs `ply3` et `ply4` : intérieur `(1, 0, 0)`, étage à 2 plis `(0, 8,
0,16)`, racine `(0, 2, 0,04)`, `k = 12`. Entre les deux étages, `staged_canonical` coûte
quelques évaluations de moins à 3 plis mais manque une décision à 4 plis que l'étage large
trouve ; la variante large est retenue, comme la mesure du portage Go de blunderDB (perte
divisée par deux, 0,00009 contre 0,00020) l'indiquait déjà. 0 à 2 plis : inchangés au bit
(`tests/test_search_filter.py`, `tests/test_search_root_stage.py`).

Échantillons petits (40 et 14 décisions d'un seul match) : ordres de grandeur d'un réglage de
recherche, pas une mesure de force (CLAUDE.md, règle 2).

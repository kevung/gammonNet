# Le filtre de coups en triplet, réglé sur le registre T70 money

**Date** : 2026-10-04 · **Machine** : poste de bureau, 16 fils, Linux 7.2.7-arch1-1, gcc 16.2.1 ·
**Branche** : `feat/movefilter-seuil` · **Instruments** : `bench/measure_t70.py --dump`
(perte et coût par décision), `bench/paired_dumps_t70.py` (appariement de deux dumps, Δ et IC
95 % bootstrap, verdict de non-infériorité) · **Registre** :
`docs/corpus/t70/money-10000/registre-money.jsonl`, partitionné sans recouvrement en un
**pilote** de 1 000 décisions et une **confirmation** de 9 000 · **Résultats** :
`docs/mesures/t70-filtre-*.json` · **Spec** : `docs/specs/filtre-de-coups-spec.md`

> **Machine chargée — comparer les secondes cumulées, pas le temps de mur.** D'autres chantiers
> tournaient sur la même machine pendant les trois passes de confirmation, lancées l'une après
> l'autre et non entrelacées. Les secondes de recherche ci-dessous sont des sommes par décision
> sur 14 processus ; elles portent la charge du moment où chaque passe a tourné. Preuve que
> la charge pèse : t=0,02 fait **moins** d'évaluations que t=0,04 et coûte **plus** de secondes.
> Les **évaluations** sont le coût qui ne dépend pas de la charge. Le rapport de vitesse à vide
> reste à mesurer par `bench/time_filter_t70.py`, qui joue les deux réglages sur chaque décision
> dans le même processus, l'ordre alterné ; ce banc n'a pas été lancé pour cette fiche.

## La question

Le défaut `normal` approfondissait à la racine un compte fixe de 3 candidats (`(0,1,3)`, 2-ply,
élagage `k = 12`). Le filtre en triplet (accepte, extra, seuil) approfondit le meilleur, puis
jusqu'à `extra` autres tant que leur équité superficielle reste à moins de `seuil` du meilleur.
La question : un triplet `(accepte 1, extra 2, seuil t)` à la racine joue-t-il aussi bien que
`(0,1,3)`, et pour quel coût ?

**Règle de décision** : non-infériorité si la borne **haute** de l'IC 95 % de
Δ = perte(candidat) − perte(défaut) est **≤ 0,001** par décision (marge du registre T70),
**et** un gain de coût net.

## Pilote (1 000 décisions, 992 notées)

| Réglage à la racine | Perte / décision [IC 95 %] | Évaluations | Secondes cumulées |
|---|---|---|---|
| `(0,1,3)` — défaut d'alors | 0,00321 [0,00271 ; 0,00375] | 12 873 396 | 2 480 |
| 1 + 2 à 0,08 | 0,00321 [0,00271 ; 0,00375] | 12 445 791 | 2 024 |
| 1 + 2 à 0,04 | 0,00321 [0,00272 ; 0,00375] | 11 695 560 | 1 711 |
| 1 + 2 à 0,02 | 0,00346 [0,00295 ; 0,00403] | 10 333 118 | 1 387 |

0,04 et 0,02 sont passés en confirmation ; 0,08 non — il ne gagnait que ×1,03 en évaluations au
pilote.

## Confirmation (9 000 décisions, 8 913 appariées)

| Réglage à la racine | Perte / décision [IC 95 %] | Évaluations | Évaluations d'élagage | Secondes cumulées |
|---|---|---|---|---|
| `(0,1,3)` | 0,00355 [0,00339 ; 0,00372] | 117 091 975 | 332 242 513 | 24 764 |
| 1 + 2 à 0,04 | 0,00362 [0,00346 ; 0,00379] | 106 387 892 | 307 815 927 | 16 094 |
| 1 + 2 à 0,02 | 0,00388 [0,00370 ; 0,00406] | 93 604 150 | 274 926 124 | 19 022 |

Appariées décision par décision contre `(0,1,3)` :

| Candidat | Δ / décision [IC 95 %] | z | Coup changé | Non-infériorité (≤ 0,001) | Évaluations | Secondes cumulées |
|---|---|---|---|---|---|---|
| **t = 0,04** | **+0,00007** [+0,00002 ; +0,00012] | 2,69 | 100 décisions | **oui** | ×1,10 en moins | ×1,54 en moins |
| t = 0,02 | +0,00033 [+0,00023 ; +0,00043] | 6,58 | 493 décisions | oui | ×1,25 en moins | ×1,30 en moins |

Les deux passent la marge. Δ est significativement positif dans les deux cas : le triplet perd
un peu d'équité, mesurablement, mais très en dessous de la marge.

## Décision

**t = 0,04 devient le défaut du niveau `normal`** : `filter = (0, 1, 1)`, `filter_extra =
(0, 0, 2)`, `filter_threshold = (0, 0, 0.04)`, élagage `k = 12` inchangé. Il perd environ **cinq
fois moins** d'équité que t = 0,02 (+0,00007 contre +0,00033) pour un coût en évaluations
moindre que `(0,1,3)`. t = 0,02 serait plus rapide en évaluations (×1,25), pour cinq fois plus
d'équité perdue.

## Ce que la mesure ne couvre pas

- **Money seulement.** Au score, la recherche classe en équité de match (`2·MWC − 1`), une
  échelle que le seuil ne remet pas à l'échelle : 0,04 y est une bande différente, non mesurée.
- **Élagué à `k = 12` seulement.** `thorough` (sans élagage) garde le compte `(0,1,3)`.
- **Natif seulement.** Les temps navigateur de T91 ont été pris avec `(0,1,3)` et ne sont pas
  rejoués ; aucun gain de vitesse n'est affirmé pour le navigateur.
- **La perte d'élagage publiée** (`prune_equity_loss` = +0,00023, T3A) a été mesurée au filtre
  `(0,1,3)` ; elle n'est pas remesurée avec le triplet.

## Effet sur les sorties figées

- Le filtre par compte (`extra = 0`) rend toujours, au bit près, les équités d'or produites
  avant le triplet (`tests/test_search_filter.py::test_count_filter_reproduces_the_pre_triplet_gold`,
  qui fixe désormais ses formes `(0,1,3)` en clair au lieu de les lire dans les niveaux).
- Le niveau `normal` avec son triplet, sur les dix mêmes positions : même meilleur coup et même
  équité du meilleur partout ; sur trois positions (`GQsQ42HXuQ8AAA` 2-2, `JmfwCSDC5+AFCA` 4-4,
  `sGfhCQI5HuEAMg` 2-1), les 2e et/ou 3e candidats sortent de la bande de 0,04, ne sont plus
  approfondis et gardent leur équité superficielle. Ces sorties sont figées à part
  (`test_normal_level_reproduces_its_triplet_gold`).

# T3E — le PR : 1,088 → 0,499 → 0,273, et la référence publiée reproduite aux trois profondeurs

**Date** : 2026-08-27 · **Machine** : la machine de calcul, répliqué sur `melbaa` · **Branche** :
`t3e-performance-rating`

> **La question.** La condition de sortie de la phase 3 est libellée en PR depuis le début —
> **1,06 → 0,50 → 0,22**, les chiffres publiés par l'auteur du modèle — et la métrique n'avait
> **jamais tourné**. `PLAN.md` en fait un test bloquant, pour une raison qui n'est pas cosmétique :
> *« Un PR qui ne bouge pas quand on ajoute un ply signale une recherche fausse. C'est le test le
> plus révélateur de toute la chaîne. »*
>
> **La réponse.** Il descend, et il descend **sur les trois valeurs de référence**, chacune tombant
> dans son intervalle de confiance.

## Le résultat

600 décisions de contact, graine 20260827, arbitre **gnubg 3-ply** sur tous les coups légaux.

| configuration | PR | IC 95 % | accord | référence |
|---|---|---|---|---|
| 0-ply | **1,088** | [0,802 ; 1,412] | 83,3 % | 1,06 ✅ |
| 1-ply | **0,499** | [0,330 ; 0,705] | 88,7 % | 0,50 ✅ |
| 2-ply `(0,1,3)`, élagage `k=12` | 0,375 | [0,264 ; 0,499] | 89,5 % | — |
| **2-ply `(0,1,3)`, sans élagage** | **0,273** | [0,190 ; 0,364] | 90,2 % | 0,22 ✅ |

**Le 1-ply à 0,499 contre 0,50 publié est le fait le plus fort de cette fiche** : deux chaînes
indépendantes, deux arbitres différents, le même chiffre au millième. C'est la meilleure
validation de la recherche que ce dépôt ait produite.

## La prédiction qui a été vérifiée

Le premier passage n'avait mesuré que le 2-ply **élagué** : 0,375, soit 0,155 au-dessus de la
référence — **hors intervalle**. Plutôt que d'invoquer le filtre ou le corpus, une hypothèse
chiffrée a été posée : l'élagage `k=12` a une perte mesurée de **+0,00023 d'équité par décision**
(`docs/mesures/2026-08-27-T3D-elagage-par-defaut.md`), soit **0,115 de PR** exactement — les trois
quarts de l'écart.

Mesuré : la différence entre les deux configurations de 2-ply vaut **0,102**.

**La prédiction tombe à 11 % près, sur une quantité obtenue par une voie entièrement
différente** — un banc de décisions appariées d'un côté, un PR contre un arbitre externe de
l'autre. Ce n'est pas une coïncidence commode : c'est le même phénomène vu deux fois.

## La réplication, et ce qu'elle a révélé sur la métrique elle-même

La mesure a été refaite sur `melbaa`, **avec un autre build de gnubg** : même version nominale
(1.08.003), mêmes poids (`gnubg.wd`, `14184acc9c60ef67`, 408 016 octets), mais build du 20260827
contre 20250313.

| ply | machine de calcul | `melbaa` | écart |
|---|---|---|---|
| 0 | 1,088 | 1,088 | 0,000 |
| 1 | 0,499 | 0,498 | 0,001 |
| 2 (`k=12`) | 0,375 | 0,373 | 0,002 |

**Le corpus est identique au bit près** sur les deux machines (`sha256 80bbbb337cf738830fa59384`),
et notre réseau y rend la même valeur au bit près. Ce qui diffère est **l'arbitre**.

**Cette différence a été détectée avant d'être subie, puis bornée.** Cinq décisions sondées des
deux côtés : écart absolu moyen 2,9e-5, maximum 1,4e-4, **de signe aléatoire** (12 positifs,
18 négatifs) — donc s'annulant sur 600 décisions. L'effet prédit sur le PR était de ±0,0006 si
aléatoire, ±0,0051 au pire ; les écarts observés valent 0,001 et 0,002.

**Ce que cela dit de la métrique** : un PR mesuré contre gnubg n'est reproductible qu'à
**~±0,005 près d'un build à l'autre**, à version nominale et poids identiques. C'est une limite de
la métrique, pas de la chaîne — et elle est trente fois plus petite que l'intervalle de confiance
du PR lui-même.

## Ce que la mesure ne dit pas

- **Le corpus est uniquement de contact.** Une référence de PR se mesure d'ordinaire sur un
  mélange réaliste, courses comprises. Le contact étant la partie difficile, ce PR est
  probablement **pessimiste** — mais ce n'est pas mesuré, et l'écart n'est pas chiffré.
- **L'arbitre de l'auteur n'est pas connu.** La comparaison à 1,06 / 0,50 / 0,22 suppose une
  méthode voisine ; l'accord aux trois profondeurs est un argument fort qu'elle l'est, pas une
  preuve.
- **Le PR n'est pas une force en ppg** et ne s'y convertit pas. C'est un taux d'erreur par
  décision. La force, c'est T35 qui la donne.

## Le prix du calcul, et ce qui l'a fait baisser

La première version arbitrait **séquentiellement** : une seule session gnubg, 68 minutes pour
600 décisions, sur une machine de 32 fils — alors que la documentation du script annonçait déjà
`--workers 26`. L'arbitrage est pourtant trivialement parallélisable : chaque décision est une
question indépendante.

| | |
|---|---|
| séquentiel | 68 min |
| **24 ouvriers** | **6 min** |

S'y ajoute un **cache d'arbitre** : il ne dépend que du corpus et de sa profondeur, jamais de la
configuration jugée. Le mettre en cache est la différence entre vérifier une hypothèse et
l'admettre — c'est lui qui a rendu la question « et sans élagage ? » posable.

## Reproduire

```bash
python bench/pr.py --decisions 600 --plies 0,1,2,2@0 --arbiter-ply 3 --workers 24
```

`2@0` désigne un 2-ply sans élagage : plusieurs configurations dans le même passage, donc un seul
arbitrage. Sortie : [`t3e-pr.json`](t3e-pr.json).

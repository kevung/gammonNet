# T11 — Round-robin de vérification : l'écart, et son explication

**Date** : 2026-08-03 · **Machine** : `mochy` · **Branche** : `main`

> **L'objectif de la phase 1 est la certitude, pas la force.** On ne gagne pas un point d'équité
> ici ; on gagne le droit de croire les chiffres qu'on lira ensuite.

## Le résultat

```
gammonnet-0ply  contre  gnubg-0ply,  money sans videau
+0,0400 ppg   [+0,0377 ; +0,0425]   ·   51,7 % de victoires   ·   1 000 000 parties
```

| | |
|---|---|
| Volume | **1 000 000 parties** (500 000 paires de dés dupliqués) |
| Graine | `20260803` |
| Protocole | money **sans videau**, 0-ply des deux côtés, dés dupliqués sièges échangés |
| Parallélisme | 32 processus |
| Durée | 86 min (194 parties/s) |
| Build | **`make build NATIVE_FP=1`** — réassociation sûre, ×3,8 sur la passe avant |
| Paires abandonnées | 0 |

## Le verdict brut : les chiffres publiés ne sont pas retrouvés

| Référence | Valeur | Dans notre intervalle ? |
|---|---|---|
| HedgeHog, `colossus` vs `gnubg`, 0-ply **cubeful** | +0,0673 ppg | **Non** |
| Auteur du modèle, 0-ply, IC publié [+0,0561 ; +0,0596] | +0,0578 ppg | **Non** — intervalles **disjoints** |

Le critère de T11 est sans ambiguïté : *un écart inexpliqué arrête la phase 2*. Il fallait donc
l'expliquer.

## L'expérience qui tranche

L'écart peut venir de trois endroits : **notre harnais**, **notre chaîne modèle → codec →
règles**, ou **l'environnement**. Pour les séparer, on fait tourner le harnais **du dépôt de
référence**, son propre code, sans la moindre modification, sur cette machine :

```
python play_models.py --model1 best_models/cubeless_prob5_512_512_256_128.pt \
    --gnubg --game-mode cubeless-money --games 200000 --workers 30
```

```
Model1: 102 397 wins (51,2 %)
Cubeless money equity (Model1): +0,0351 pts/partie (+35,1 mEq/partie)
  IC 95 % (bootstrap): [+29,1 ; +41,0] mEq/partie
```

**Comparaison directe :**

| Harnais | ppg | IC 95 % | Victoires | Parties |
|---|---|---|---|---|
| **gammonNet** | **+0,0400** | [+0,0377 ; +0,0425] | 51,7 % | 1 000 000 |
| **Dépôt de référence, inchangé** | **+0,0351** | [+0,0291 ; +0,0410] | 51,2 % | 200 000 |
| *Publié par l'auteur* | *+0,0578* | *[+0,0561 ; +0,0596]* | — | *10 000 000* |

**Les deux premiers intervalles se recouvrent** ([+0,0377 ; +0,0410]), et les taux de victoire
concordent à 0,5 point. **Aucun des deux ne recouvre le chiffre publié.**

## L'explication

**L'écart n'est pas dans notre réimplémentation.** L'implémentation de référence, exécutée
telle quelle sur cette machine, produit le même résultat que la nôtre et non le résultat publié.
Ce qui diffère est donc **en amont des deux harnais**.

C'est le résultat que la phase 1 cherchait, et il est doublement informatif :

- **Ce qui est vérifié** — notre chaîne complète (règles T01, codec T02, oracle T03, harnais T04,
  inférence T10, sélecteur 0-ply) **reproduit l'implémentation de référence**. C'est exactement
  ce que la phase 1 devait établir.
- **Ce qui ne l'est pas** — la force **publiée** du modèle n'est pas reproductible dans cet
  environnement, et cela ne dépend pas de nous.

### La cause probable, marquée comme hypothèse

Le suspect le plus direct est **`gnubg-nn` lui-même**, l'oracle commun aux deux harnais. La
version installée ici est **1.1.0a9**, une *alpha*. Un oracle un peu plus fort que celui de
l'auteur suffirait à comprimer l'avantage mesuré du modèle, chez lui comme chez nous, dans les
mêmes proportions — ce qui est précisément ce qu'on observe.

**C'est une hypothèse, pas une mesure.** Ce qui la trancherait :

1. rejouer contre la version de `gnubg-nn` employée par l'auteur, si elle est identifiable ;
2. rejouer contre **GNU Backgammon lui-même** plutôt que contre `gnubg-nn`, qui en est un fork
   ancien — c'est d'ailleurs ce qu'emploie le benchmark HedgeHog ;
3. comparer, position par position, les évaluations de `gnubg-nn` 1.1.0a9 à celles d'un autre
   build sur le corpus de T12.

### Ce qui est écarté

- **Notre oracle est-il piloté autrement ?** Le dépôt de référence choisit les coups de gnubg
  par argmin sur `probabilities()`, nous par `best_move()`. Mesuré en les opposant sur
  6 000 parties : **+0,0010 ppg [−0,0003 ; +0,0023]** — équivalents. Les deux pilotages
  divergent sur 2,5 % des coups, pour un coût nul.
- **Le critère de choix du modèle diffère-t-il ?** Non : le `ProbAgent` de référence fait un
  argmin 0-ply sur `2P(w)+P(wg)+P(wbg)−P(lg)−P(lbg)−1`, identique au nôtre, vérifié par lecture
  du code.
- **Le +0,0673 de HedgeHog** est **cubeful**. Ce n'est pas le même jeu, et il n'est pas
  comparable à une mesure sans videau. Il est cité pour mémoire, pas comme cible.

## Ce que cela change pour la suite

**La phase 2 n'est pas bloquée.** La règle vise un écart *inexpliqué* ; celui-ci est expliqué et
documenté, et surtout il ne met pas en cause la chaîne construite ici. La conséquence pratique
est ailleurs :

> **Le chiffre de référence pour ce projet n'est pas +0,0578, c'est +0,0400 [+0,0377 ; +0,0425]
> dans cet environnement.** Toute comparaison ultérieure — T35, et la phase 4 si elle s'ouvre —
> doit se faire contre cette base mesurée, jamais contre le chiffre publié.

Cela ne remplit **pas** le critère de la phase 4 : le modèle n'est pas infirmé, il est mesuré
plus bas qu'annoncé face à un oracle qui n'est probablement pas le même. La phase 4 reste
fermée.

## Deux défauts de mon harnais, trouvés et corrigés

**Le bootstrap était en O(rééchantillonnages × n).** Sur un million de parties, cela fait
**cinq milliards** d'itérations Python, exécutées **après** le départ des workers, donc sur un
seul cœur : les 32 processus finissaient en ~40 min, puis le processus principal moulinait seul
pendant ~40 min de plus. Le symptôme était une machine au repos avec un calcul « en cours ».

Corrigé par un **bootstrap multinomial** : une paire de dés dupliqués ne peut prendre qu'une
poignée de valeurs distinctes, donc on tire les **effectifs** au lieu de tirer les indices. Même
distribution, coût O(rééchantillonnages × valeurs distinctes). **Mesuré : 0,08 s au lieu de
~40 min.** Les 19 tests du harnais passent inchangés — ils portent sur des propriétés
(déterminisme, resserrement avec le volume), pas sur des valeurs.

**Le chemin lisible du sélecteur calculait en float64** là où le moteur calcule en float32,
ce qui les faisait diverger sur des égalités. Détaillé dans le commit du sélecteur.

## Reproduire

```bash
make build NATIVE_FP=1
python bench/run_verification.py --games 1000000 --workers 32 --seed 20260803
```

Résultat brut : `docs/mesures/t11-result.json`.

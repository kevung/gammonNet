# T92 — le pont vers le moteur tiers, et ce qu'une décision coûte

*2026-09-07 · mochy (AMD Ryzen Threadripper PRO 3955WX, 16 cœurs / 32 fils) ·
`bgsage` 1.7.20260829, roue `manylinux` cp312 · dépôt à `37c65e2`*

> **Cette fiche ne mesure aucune force.** Elle répond à deux questions qui doivent l'être avant
> qu'un chiffre de force veuille dire quelque chose : *la position que nous croyons envoyer
> est-elle celle qu'il reçoit ?* et *combien coûte une décision ?*

---

## 1. Ce que la licence permet, revérifié le 2026-09-07

| Fait | Vérifié |
|---|---|
| Licence du code **et des poids et de la base de fin de partie** | MPL-2.0, explicitement : *« everything in the repository, including the trained model weights in `models/` and the bearoff database in `data/` … you are free to use them in a commercial product »* |
| Distribution | `pip install bgsage`, roue `manylinux_2_27_x86_64` de 8,9 Mio, Python 3.10 à 3.14, seule dépendance `numpy` |
| Processeur seul | oui — CUDA est employé s'il existe, jamais requis |

**Ce que nous en faisons, et rien d'autre** : nous l'**exécutons**. Exécuter n'est pas
distribuer ; le copyleft de fichier de MPL-2.0 porte sur les fichiers modifiés que l'on
distribue. Aucun de ses fichiers n'entre dans un artefact d'ici, rien de son code n'est copié,
et il n'est pas employé comme professeur d'entraînement (`PLAN.md`, règle de la phase 9).

---

## 2. Le pont, vérifié sur 200 000 positions

La sentinelle habituelle du projet — le compte de pips — ne suffisait pas ici : elle ne voit
pas une erreur de **génération de coups**. Le contrôle porte donc sur l'identité des ensembles
de positions atteignables, sur des positions tirées de parties jouées au hasard, barre et
sorties comprises.

```
python bench/probe_sage_bridge.py --positions 200000 --workers 26
```

| | |
|---|---|
| Positions examinées | **200 000** |
| dont avec un pion sur la barre | 82 700 (41,4 %) |
| dont avec au moins un pion sorti | 30 864 (15,4 %) |
| dont **BLACK** au trait | 99 993 (50,0 %) |
| Aller-retour de conversion en échec | **0** |
| Ensembles de coups légaux différents | **4** (0,002 %) |

Relevé brut : [`t92-pont.json`](t92-pont.json).

### Les quatre divergences, et qui a raison

Les quatre sont de la même forme : **un coup de plus chez eux**, toujours en fin de partie
(un seul pion restant, quatorze sortis), toujours un coup **à un seul dé** alors que les deux
sont jouables par une combinaison. La règle est explicite : on doit jouer les deux dés quand
il existe une façon légale de le faire.

L'arbitrage n'est pas notre parole contre la leur — **GNU Backgammon a été consulté sur les
quatre**, et il tranche avec nous :

| dés | gammonNet | GNU Backgammon | eux | clé de position |
|---|---|---|---|---|
| 2-1 | 1 | 1 | 2 | `PLCOAEEACBACAAAAAAAA` |
| 3-1 | 1 | 1 | 2 | `MPNDAABGCAACAAAAAAAA` |
| 1-3 | 1 | 1 | 2 | `LLICEBOBCAACAAAAAAAA` |
| 3-1 | 1 | 1 | 2 | `OPKEAIGACEACAAAAAAAA` |

**Le coup en trop n'est pas anodin sur ces positions** : dans le premier cas, la ligne légale
frappe un blot et gagne un backgammon là où la ligne illégale gagne un gammon — un point
d'équité d'écart. Mais le taux est de **4 sur 200 000**, et il n'est mesuré que sur une
distribution de jeu **au hasard**, qui atteint bien plus de fins de partie qu'une partie
sérieuse. Ce n'est pas une note sur la force du moteur ; c'est une contrainte de protocole,
traitée au §4.

### Une seconde différence, de convention celle-là

Quand aucun coup n'est légal (un joueur qui reste à la barre), nous rendons une liste vide ; il
rend le **plateau inchangé** comme unique « coup » — malgré son propre docstring, qui annonce
une liste vide. Les deux disent la même chose. La différence est normalisée en un seul endroit
(`bench/probe_sage_bridge.py`, `SageEngine.choose`) plutôt que devinée à chaque appel : un
moteur qui « jouerait » le plateau inchangé perdrait un tour sans que rien ne le signale.

---

## 3. Les étiquettes de niveau sont décalées d'un cran

**C'est le piège d'entrée de toute comparaison avec ce moteur.** Il numérote ses niveaux depuis
l'évaluation statique, à la manière d'eXtreme Gammon. Vérifié dans sa propre source
(`bgsage/gnubg.py`, `GnuBgAnalyzer.__init__`) :

```python
# Display label uses our XG convention (1-ply = raw NN)
self.eval_level_str = f"{self.n_plies + 1}-ply"
```

| son étiquette | profondeur réelle — la nôtre, et celle de GNU Backgammon |
|---|---|
| `1ply` | **0-ply** |
| `2ply` | **1-ply** |
| `3ply` | **2-ply** ← le niveau publié de ce dépôt |
| `4ply` | **3-ply** |
| `truncated1/2/3` | ce ne sont pas des profondeurs : des rollouts tronqués |

Conséquence immédiate, et elle vaut d'être dite : **le « PR 0,21 » qu'ils publient est un
niveau de rollout tronqué**, pas une profondeur. Le comparer à notre PR 2-ply de 0,273 (T3E)
comparerait deux instruments différents, sur deux corpus différents, avec deux arbitres
différents. `PLAN.md` phase 9 en fait sa première ligne.

Ce décalage est écrit à **un seul endroit** du dépôt (`SageEngine.REAL_PLY`, repris par
`PAIRS` dans `tools/build_corpus_t93.py`), et le nom que l'instrument porte dans une matrice
est toujours la profondeur **réelle** : `sage-2ply` est son `3ply`.

---

## 4. Ce qu'une décision coûte

Machine **au repos** — charge 0,13 au démarrage, le banc refuse de rendre un temps au-dessus de
2,0 (règle 3, et la mémoire du projet : sous charge, un temps est faux d'un facteur variable
sans en avoir l'air). 40 décisions de contact tirées de parties jouées, 21,65 coups légaux en
moyenne, **un seul fil de chaque côté**.

```
python bench/cost_per_decision_sage.py --positions 40 \
    --levels-ours instant,ply1,normal,thorough \
    --levels-theirs 1ply,2ply,3ply,4ply,truncated1
```

| profondeur réelle | nous | eux | rapport |
|---|---|---|---|
| **0-ply** | **1,42 ms** (`instant`) | **3,53 ms** (`1ply`) | nous ×2,5 plus rapides |
| **1-ply** | 519 ms (non filtré) | 22,1 ms (`2ply`) | *voir la réserve ci-dessous* |
| **2-ply** | **412 ms** (`normal` : filtre `(0,1,3)`, élagage `k=12`) | **327 ms** (`3ply`) | eux ×1,26 plus rapides |
| 2-ply sans élagage | 1 728 ms (`thorough`) | — | |
| **3-ply** | — | 5 900 ms (`4ply`) | |
| rollout tronqué | — | 1 170 ms (`truncated1`) | |

Moyennes ; les médianes sont dans [`t92-cout-decision.json`](t92-cout-decision.json) et leur
écart est instructif — leur `3ply` a une médiane de 154 ms pour une moyenne de 327, distribution
bien plus dispersée que la nôtre (434 / 412). Ils dépensent peu sur les décisions faciles.

> **La ligne 1-ply ne compare pas le même travail, et n'est pas présentée comme si.** Notre
> 1-ply est **non filtré** par construction (`bench/pr.py` : avec `filter[1] = 1`, la passe
> profonde ne rescore qu'un candidat et le coup reste celui du 0-ply, ce qu'un pilote a montré
> en rendant 0,946 aux deux profondeurs). Le leur filtre. Le rapport ×23,5 mesure donc surtout
> l'absence de filtre chez nous. La ligne est conservée parce que c'est la configuration dont
> T3E publie le PR, et la réserve est écrite plutôt que le chiffre retiré.

### Ce que le 2-ply dit, et ne dit pas

À la profondeur qui compte — celle que l'artefact sert — **les deux moteurs coûtent le même
ordre de grandeur, avec un avantage de ×1,26 pour eux**. C'est un fait de vitesse, pas de
qualité : rien ici ne dit lequel joue mieux. Deux réserves nommées : leur `3ply` porte son
propre filtre de coups, dont le réglage nous est inconnu, et ce banc mesure un seul fil, quand
le module WebAssembly, lui, en distribue huit.

---

## 5. Le budget que cette fiche dégage

C'est l'objet de la fiche : dimensionner T93 et T94 sur un chiffre mesuré plutôt que sur une
intuition.

| point de comparaison | coût unitaire | 10 000 décisions |
|---|---|---|
| une décision comparée à **0-ply** | 4,95 ms | 50 s·cœur — **négligeable** |
| une décision comparée à **2-ply** | 739 ms | 2,05 h·cœur |
| l'**arbitrage escaladé** de T70 | — | 15,8 h·cœur (mesuré en T70) |

Donc, avec 26 processus :

- **T93 est une affaire d'heures**, pas de jours : un corpus de 8 000 décisions à 0-ply et un de
  6 000 à 2-ply, arbitrages compris, tiennent dans une demi-journée de machine. La fiche T70
  demandait « des heures et non des jours » de son instrument ; celui-ci hérite de la propriété.
- **T94 se scinde en deux.** Un tête-à-tête à **0-ply** coûte ~0,27 s par partie : 100 000
  parties tiennent en 7,5 h·cœur, soit une vingtaine de minutes. Un tête-à-tête à **2-ply**
  coûte ~40 s par partie : 100 000 parties demandent ~1 100 h·cœur, soit **environ deux jours
  sur mochy seule**, ou un peu plus d'un jour en ajoutant melbaa.

**Ces trois dernières lignes sont des extrapolations, pas des mesures** (règle 3). Elles valent
comme ordre de grandeur d'un budget, et le temps réellement consommé sera publié avec le
résultat.

---

## 6. Ce que cette fiche laisse ouvert

- **La configuration de leur filtre de coups** au niveau `3ply` n'est pas connue ; nous
  comparons deux moteurs à leur réglage servi, ce qui est le bon choix, mais ce n'est pas un
  contrôle à une seule variable.
- **Le videau n'est pas touché.** Leur `cube_action` existe et expose tout ce qu'il faut
  (money, Jacoby, beaver, score de match) ; rien n'en est encore mesuré ici.
- **Le rapport de vitesse est celui d'un seul fil sur une seule machine.** Il ne se transpose ni
  au navigateur ni à un téléphone, et la phase 8 a montré combien cette transposition est
  infidèle.

# T97 — une table d'équité de match calculée par ce moteur

*2026-09-17 au 2026-09-18 · smith (2× EPYC 9254, 35 processus), mochy (28), melbaa (24) ·
jeu et videau à profondeur 0 · réseau `cubeless_prob5_512_512_256_128`*

> **Ce que la fiche établit.** Une table d'équité de match de 25 points, Crawford et
> après-Crawford compris, **entièrement dérivée du moteur de ce dépôt** : aucune table tierce en
> entrée, aucune valeur initiale, aucune constante réglée à la main. Ses identités tiennent, son
> harnais est symétrique, et elle n'est **pas distinguable en force** de Kazaross-XG2 sur
> 120 000 matchs de 25 points.
>
> **Ce qu'elle n'établit pas.** Qu'elle soit *meilleure*. L'intervalle de force contient zéro.
> Le seul argument qui reste pour la préférer n'est pas la force, c'est l'**indépendance** — et
> cela doit être dit comme tel.

---

## 1. Le calcul, et pourquoi il n'a pas de point fixe

Une partie se termine toujours par des points marqués : l'un des deux `away` **décroît
strictement**. Une cellule ne dépend donc que de cellules dont la somme `a + b` est plus petite,
déjà calculées quand on y arrive. La table se remplit par programmation dynamique sur `a + b`
croissant. **Aucune valeur initiale n'est injectée** — l'objection « votre table de départ était
la leur » ne se pose pas.

Trois familles, dans cet ordre : `POST[n]` (après-Crawford), `PRE[a][1]` (la partie de Crawford,
sans videau — c'est une règle, pas une connaissance), puis `PRE[a][b]` par `a + b` croissant.

**La prémisse est vérifiée, pas crue.** `--check-dependencies` recalcule des cellules avec les
cases non encore calculées remplies de 0, puis de 1. Les deux passes rendent **exactement** le
même nombre : aucune case non calculée n'est lue. Si elles différaient, toute la suite serait
fausse.

## 2. Le volume, mesuré avant d'être choisi

| | |
|---|---|
| campagnes | 3, graines **disjointes** (20260922, 20260923, 20260924) |
| cellules | 350 (25 après-Crawford, 325 pré-Crawford) |
| parties par cellule | 20 000 pour `a + b ≤ 10`, 4 000 au-delà |
| **total** | **5 832 000 parties** |
| débit | 464–580 parties/s (smith, 35), 246 (mochy, 28), 126 (melbaa, 24) |
| parties bloquées | **0** |

`tools/merge_met.py` **refuse** deux campagnes à la même graine : les moyenner diviserait
l'erreur-type affichée par racine de deux sans rien apporter.

Table : [`t97-table-reunie.met`](t97-table-reunie.met) · relevé :
[`t97-table-reunie.json`](t97-table-reunie.json).

## 3. Les contrôles internes

| Contrôle | Attendu | Mesuré |
|---|---|---|
| dépendances jamais lues avant calcul | identique | **identique** |
| `MET(1,1)` | 0,5 | **0,50240 ± 0,00234** (1,0 σ) |
| diagonale `MET(a,a)`, 25 cellules | 0,5 | **+0,000564 ± 0,000330** (1,7 σ) |
| monotonies en `a`, en `b`, après-Crawford | 0 violation | **0 sur 350 cellules** |

La diagonale est le contrôle de **biais de siège** : un moteur qui jouerait mieux d'un côté du
damier se verrait là. Il ne s'y voit pas.

> **Le contrôle d'identités a dû être corrigé en route.** Il comparait les écarts à une tolérance
> **fixe** de 0,002. Une table mesurée ne vérifie aucune identité exactement : elle la vérifie à
> son erreur-type près. Une tolérance en dur signale les cellules les **mieux** mesurées — l'exact
> inverse de ce qu'on veut — et laisse passer les autres. `MET(1,1)` était « violée » à ce régime ;
> elle est à 1,0 σ de 0,5.

## 4. Le *free drop* apparaît, il n'est écrit nulle part

| après-Crawford, poursuivant à | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| **calculé ici** | 0,502 | 0,488 | 0,318 | 0,309 | 0,188 | 0,178 |
| Kazaross-XG2 | 0,500 | 0,488 | 0,323 | 0,310 | 0,190 | 0,181 |

Le décrochement par paires — deux valeurs proches, puis une chute — est la signature du *free
drop* : à un nombre pair de points restants, le meneur peut refuser un double sans rien risquer.
**Aucune ligne du code ne le mentionne.** C'était le critère d'acceptation de la fiche, et il est
tenu.

## 5. L'incertitude, deux fois fausse avant d'être juste

C'est la partie de la fiche qui a demandé le plus de travail, et elle n'a rien à voir avec les
valeurs de la table.

**Premier défaut, trouvé par la passe miroir.** La passe miroir mesure la moitié basse de la table
et déduit la haute — l'inverse de la passe directe. C'est la **seule** façon de vérifier
l'antisymétrie : une passe unique la retrouve par construction, puisqu'elle la pose. Confrontées,
les deux passes donnaient un z moyen de **+0,83** et **3,3 %** de cellules au-delà de 3 σ là où
0,3 % étaient attendus. La cause : la valeur d'une cellule est une moyenne de valeurs d'**autres**
cellules, qui portent leur propre erreur, et l'erreur-type ne comptait que les parties de la
cellule courante — le dernier étage du calcul, jamais ce dont il hérite.

Un second contrôle l'a confirmé **indépendamment de toute question d'orientation** : les cellules
d'après-Crawford sont mesurées dans la **même** orientation par les deux passes, qui ne diffèrent
alors que par la graine, et elles s'écartaient déjà de −0,69 σ. *Deux campagnes indépendantes ne
peuvent pas faire ça si leurs barres d'erreur sont justes.*

**Second défaut, trouvé par les trois campagnes.** Après correction, le χ² réduit entre campagnes
vaut **1,312 ± 0,053** sur 700 degrés de liberté : il reste 14,5 % manquants. La cause est
identifiée — la propagation somme les variances des dépendances comme si elles étaient
indépendantes, alors que deux dépendances partagent les leurs, et la covariance positive négligée
manque au total. Plutôt que de traîner une matrice de covariance à travers cinquante étages, **on
mesure ce qui manque** : la dispersion entre campagnes indépendantes *est* l'incertitude. Facteur
d'échelle **×1,145**, appliqué, imprimé, et versionné dans le relevé.

**Les valeurs de la table n'ont jamais bougé dans toute cette histoire.** Seule leur précision
annoncée l'a fait — et avec elle le nombre de cellules que la comparaison signale.

## 6. Contre Kazaross-XG2 : un plateau, pas des accidents

Seuil **versionné avant les données** (`bench/compare_met.py`, commité pendant que la première
campagne tournait) : une cellule est signalée si l'écart dépasse **à la fois** 3 σ et 0,005.

| | |
|---|---|
| écart absolu médian | **0,00125** sur 350 cellules |
| écart absolu maximal | 0,00612 |
| cellules signalées | **7** |

Les sept sont dans la même région, et ce ne sont pas sept accidents : la carte des écarts (en
dix-millièmes de MWC) montre **un plateau cohérent**, entièrement positif.

```
        b=19   b=20   b=21   b=22   b=23   b=24   b=25
a=12   +13.6  +31.8  +34.7  +41.0  +36.0  +40.0  +22.6
a=13   +19.1  +24.8  +47.7  +44.4  +39.0  +30.8  +29.3
a=14   +31.6  +38.9  +58.5  +29.7  +55.9  +33.3  +50.1
a=15   +37.2  +37.6  +43.1  +33.6  +46.2  +44.2  +48.9
a=16   +38.3  +19.1  +61.2  +30.2  +59.9  +52.2  +55.0
a=17    -1.4  +10.7  +32.4  +30.6  +34.0  +29.2  +37.6
a=18   +23.2   +1.9  +31.9  +36.6  +45.1  +37.5  +41.6
```

**Notre table donne de +0,003 à +0,006 de plus au meneur, dans les matchs longs.** Les trois
campagnes s'accordent entre elles là-dessus — sur `pre[16][23]` : 0,73588 · 0,73741 · 0,73718,
contre 0,73084 chez Kazaross.

Le miroir du plateau est en après-Crawford, où notre poursuivant reçoit **moins** que chez eux
(−0,0014 à −0,0025 pour `n ≥ 5`). Les deux vont ensemble : le meneur vaut plus parce qu'atteindre
l'après-Crawford en tête vaut plus.

## 7. Trois explications candidates, deux écartées par la mesure

### 7.1 Une asymétrie du harnais ? **Non** — bornée à 0,0004

Trente cellules mesurées dans les **deux** orientations, 60 000 parties chacune, **depuis la même
table de dépendances** — le seul protocole qui sépare une asymétrie du harnais d'une différence
entre deux tables.

| | |
|---|---|
| écart moyen directe − miroir | **+0,000194 ± 0,000101** (1,9 σ) |
| écart médian | +0,000084 |
| cellules au-delà de 3 σ | **0 sur 30** |

Six fois plus petit que le +0,00121 observé entre les deux campagnes complètes — qui était donc
bien de la propagation accumulée, chaque campagne construisant ses cellules basses dans sa propre
orientation, et non un biais du moteur.

**Ce test est conservateur, et il faut le dire** : les deux passes partagent la même table de
dépendances, donc l'erreur héritée est un terme **commun** qui s'annule dans la différence alors
qu'il est compté deux fois dans σ. D'où un écart-type des z de 0,58 au lieu de 1. La borne vraie
est donc meilleure que celle annoncée.
Relevés : [`t97-orientation-directe.json`](t97-orientation-directe.json),
[`t97-orientation-miroir.json`](t97-orientation-miroir.json).

### 7.2 La profondeur du videau ? **Non** — le plateau tient

Les six cellules du plateau et **quatre témoins** où nous sommes d'accord avec Kazaross,
recalculées avec un videau **1-ply** au lieu de 0, depuis la table réunie.

| | écart à Kazaross, videau 0-ply | videau 1-ply |
|---|---|---|
| plateau (6 cellules) | **+0,00520** | **+0,00478** |
| témoins (4 cellules) | −0,00029 | −0,00021 |

Les témoins disent que la profondeur ne déplace pas **tout** ; le plateau dit qu'elle ne le
déplace pas **lui**. Relevé : [`t97-arbitrage-videau-1ply.json`](t97-arbitrage-videau-1ply.json).

**Réserve nommée** : seules les décisions de la cellule courante passent à 1-ply ; ses
dépendances restent celles de la table 0-ply. Ce test mesure la sensibilité du videau *de cette
cellule*, pas celle de toute la récursion.

### 7.3 Ce qui reste, et qui n'est pas tranché

Deux explications survivent, et la fiche ne choisit pas entre elles :

- **Leur table.** `gn_met_table.h` dit sa provenance : rollouts XG jusqu'à 9 points, rollouts
  gnubg jusqu'à 15, puis *« extended to 25 points by projecting take points »*. **Le plateau est
  exactement dans la région extrapolée.** C'est le fait le plus suggestif de la fiche — et il
  reste une coïncidence de localisation, pas une démonstration.
- **La profondeur du jeu de pions.** L'arbitrage ci-dessus a fait varier le videau, jamais les
  pions : `ply = 0` dans les deux colonnes. Une campagne à `ply = 1` tourne (smith, 2026-10-05)
  et complétera cette fiche.

## 8. La force : indistinguable, et c'est le résultat

`bench/met_strength.py` fait jouer **le même moteur contre lui-même**, à dés dupliqués, les deux
joueurs ne différant que par le fichier de table qu'ils consultent. Le choix des **25 points**
n'est pas cosmétique : les deux tables ne diffèrent que là où le match est long, et une campagne
en 7 points mesurerait surtout du bruit.

| | volume | résultat |
|---|---|---|
| Kazaross-XG2 contre notre table, matchs en 25 points | 60 000 paires — **120 000 matchs**, 1 827 686 parties | **−0,00393 match par paire** [−0,00877 ; +0,00105] |

**Zéro est dans l'intervalle.** Le point d'estimation est en faveur de notre table (1,6 σ), ce qui
ne suffit pas et ne sera pas présenté autrement.

Ce que ce chiffre établit tout de même : **le choix entre ces deux tables coûte au plus
0,009 match par paire**, et probablement rien. Personne ne publie cette borne.

Et le contrôle qui rend le résultat lisible plutôt qu'ambigu : un zéro exact est indiscernable
d'un mécanisme qui ne prendrait pas. Contre une table **plate à 0,5**, qui détruit toute logique
de videau, Kazaross gagne **+0,783 match par paire**. Le mécanisme atteint bien les ouvriers.
Relevé : [`t97-force-25pts.json`](t97-force-25pts.json).

## 9. Ce que la fiche autorise, et ce qu'elle n'autorise pas

**Elle n'autorise pas** à remplacer la table de l'artefact *au nom de la force* : l'intervalle
contient zéro.

**Elle autorise** à publier la table comme **mesure**, et à l'offrir comme table de rechange —
pour une raison qui n'est pas la force et qui doit être nommée : l'artefact distribué cesserait
d'embarquer une œuvre tierce. Kazaross-XG2 est licite et attribuée, mais c'est le seul endroit où
l'artefact dit « faites-nous confiance » plutôt que « voici le calcul », et elle est arbitrée par
des moteurs que nous ne contrôlons pas, dont l'un est commercial. Une table calculée ici est
reproductible par quiconque relance `tools/compute_met.py`.

**C'est une décision de propriétaire de projet, pas une conclusion de mesure.** La mesure dit
seulement qu'elle ne coûte rien.

## 10. Reproduire

```
# une campagne (≈ 1,2 h sur 35 processus)
python tools/compute_met.py --games 20000 --games-far 4000 --near 10 \
    --ply 0 --cube-ply 0 --workers 35 --seed <graine> \
    --check-dependencies 12 --out campagne.json --table-out campagne.met

# la réunion, qui refuse deux graines identiques et mesure le facteur d'échelle
python tools/merge_met.py c1.json c2.json c3.json \
    --out t97-reunie.json --table-out t97-reunie.met

# la confrontation, au seuil versionné avant les données
python bench/compare_met.py --computed t97-reunie.json

# la force, et son contrôle (remplacer t97-reunie.met par une table plate)
python bench/met_strength.py --table-b t97-reunie.met \
    --pairs 60000 --length 25 --workers 28
```

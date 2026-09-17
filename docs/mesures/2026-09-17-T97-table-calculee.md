# T97 — une table d'équité de match calculée par ce moteur : premier passage

*2026-09-17 · smith (2× EPYC 9254, 35 processus), mochy (28), melbaa (24) ·
jeu et videau à profondeur 0 · réseau `cubeless_prob5_512_512_256_128`*

> **État : premier passage rendu, table non publiée.** Les contrôles internes passent tous ; la
> confrontation entre la passe directe et la passe miroir a trouvé un défaut **dans l'estimateur
> d'incertitude**, corrigé, et trois campagnes refaites tournent derrière. Cette fiche consigne
> ce qui est établi, ce qui ne l'est pas, et pourquoi la table n'est pas encore un résultat.

---

## Ce que le calcul est

Une partie se termine toujours par des points marqués : l'un des deux `away` **décroît
strictement**. Une cellule ne dépend donc que de cellules dont la somme `a + b` est plus petite,
déjà calculées quand on y arrive. **Il n'y a pas de point fixe à chercher, et aucune valeur
initiale n'est injectée** — l'objection « votre table de départ était la leur » ne se pose pas.

Trois familles, dans cet ordre : `POST[n]` (après-Crawford), `PRE[a][1]` (la partie de Crawford,
sans videau — c'est une règle), puis `PRE[a][b]` par `a + b` croissant.

**La prémisse est vérifiée, pas crue.** `--check-dependencies` recalcule des cellules avec les
cases non encore calculées remplies de 0, puis de 1. Les deux passes rendent **exactement** le
même nombre sur les douze cellules contrôlées : aucune case non calculée n'est lue.

## Le volume, mesuré avant d'être choisi

| | |
|---|---|
| cellules | 350 (25 après-Crawford, 325 pré-Crawford) |
| parties par cellule | 20 000 pour `a + b ≤ 10`, 4 000 au-delà |
| total | **2 024 000 parties** par campagne |
| débit | **464 parties/s** sur smith (35 processus), 246 sur mochy (28), 126 sur melbaa (24) |
| durée | 4 363 s sur smith |
| parties bloquées | **0** |

## Les contrôles internes, tous passés

| Contrôle | Attendu | Mesuré |
|---|---|---|
| `MET(a,a) = 0,5` sur les 25 cellules diagonales | 0 | **+0,000172 ± 0,000429** (0,40 σ) |
| monotonie en `a`, en `b`, après-Crawford | 0 violation | **0 sur 350 cellules** |
| dépendances jamais lues avant d'être calculées | identique | **identique** |

**La diagonale est le contrôle de biais de siège**, et il passe : le harnais est symétrique à
±0,0004. Un moteur qui jouerait mieux d'un côté du damier que de l'autre se verrait là.

## Le *free drop* apparaît, il n'est écrit nulle part

| après-Crawford, poursuivant à | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| **calculé ici** | 0,506 | 0,488 | 0,317 | 0,309 | 0,188 | 0,178 |
| Kazaross-XG2 | 0,500 | 0,488 | 0,323 | 0,310 | 0,190 | 0,181 |

Le décrochement par paires — deux valeurs proches, puis une chute — est la signature du *free
drop* : à un nombre pair de points restants, le meneur peut refuser un double sans rien risquer.
**Aucune ligne du code ne le mentionne.** C'était le critère d'acceptation de la fiche.

## Contre Kazaross-XG2

Seuil **versionné avant les données** (`bench/compare_met.py`, commité pendant que la campagne
tournait) : une cellule est signalée si l'écart dépasse **à la fois** 3 σ et 0,005.

| | |
|---|---|
| écart absolu médian | **0,00186** sur 350 cellules |
| écart absolu maximal | 0,00696 |
| cellules signalées | 19, **toutes de même signe** |

L'écart est **structuré**, pas bruité :

| | écart moyen signé |
|---|---|
| pré-Crawford, `b ≤ 15` | +0,0007 |
| pré-Crawford, `b ∈ [16, 20]` | +0,0019 |
| pré-Crawford, `b ∈ [21, 25]` | +0,0027 |
| après-Crawford, `n ≥ 5` | −0,0014 à −0,0025 |

Notre table donne un peu plus au meneur en pré-Crawford et un peu moins au poursuivant en
après-Crawford — les deux vont ensemble —, et l'écart **grandit avec la longueur du match**.

**Deux lectures, et rien ne les départage encore.**

1. **Leur table.** `gn_met_table.h` dit sa provenance : rollouts XG jusqu'à 9 points, rollouts
   gnubg jusqu'à 15, puis *« extended to 25 points by projecting take points »*. **Dix-sept des
   dix-neuf cellules signalées ont `b ≥ 20`** — la région où leur table cesse d'être un rollout.
2. **Notre profondeur.** La table a été calculée avec un jeu et un videau à profondeur 0. Une
   table est celle des joueurs qui l'ont produite.

La fiche exige de les **arbitrer, pas de les expliquer** : recalculer ces cellules à une
profondeur de videau supérieure dira laquelle tient. `--from-table` / `--cells` le permettent
sans rejouer la table.

---

## Le défaut que la passe miroir a trouvé, et qui suspend le résultat

La passe miroir mesure la moitié basse de la table et déduit la haute — l'inverse de la passe
directe. C'est la **seule** façon de vérifier l'antisymétrie : une passe unique la retrouve par
construction, puisqu'elle la pose.

Confrontées (2 024 000 et 1 944 000 parties, graines disjointes) :

| | attendu | mesuré |
|---|---|---|
| écart moyen direct − miroir | 0 | **+0,00121** |
| z moyen | 0 | **+0,83** |
| cellules au-delà de 3 σ | 0,3 % | **3,3 %** |

Et un second contrôle, qui tranche **indépendamment de toute question d'orientation** : les
cellules d'après-Crawford sont mesurées dans la **même** orientation par les deux passes, qui ne
diffèrent alors que par la graine. Elles s'écartent de **−0,69 σ** en moyenne. *Deux campagnes
indépendantes ne peuvent pas faire ça si leurs barres d'erreur sont justes.*

**Le défaut est dans l'estimateur d'incertitude, et il est structurel.** La valeur d'une cellule
est une moyenne de valeurs d'**autres** cellules, qui portent leur propre erreur. L'erreur-type ne
comptait que les parties de la cellule courante — le dernier étage du calcul, jamais ce dont il
hérite. Elle compte désormais les deux : chaque cellule consultée pèse la fraction des parties qui
y tombent, et apporte son erreur au carré.

**Ce que cela change, et ce que cela ne change pas.** Les **valeurs** de la table ne bougent pas :
elles ne dépendent pas de l'estimateur d'erreur. Ce qui bouge est leur précision annoncée, donc la
lecture des 19 cellules signalées : le seuil absolu de 0,005 tient, le critère à 3 σ était trop
généreux.

**Ce qui reste ouvert** : une fois les barres corrigées, un résidu d'asymétrie subsiste
probablement. Il se tranchera en mesurant les deux orientations d'une **même** cellule depuis la
**même** table de dépendances — le seul protocole qui sépare une asymétrie du harnais d'une
différence entre deux tables.

## La force, et le contrôle qui rend son absence lisible

`bench/met_strength.py` fait jouer le même moteur contre lui-même à dés dupliqués, les deux
joueurs ne différant que par leur fichier de table. Premier chiffre, 40 paires en 7 points :
**zéro exact** — les deux tables jouent le même jeu à ce volume.

Un zéro exact est indiscernable d'un mécanisme qui ne prendrait pas. D'où le contrôle : contre une
table plate à 0,5, qui détruit toute logique de videau, Kazaross gagne **+0,783 match par paire**.
Le mécanisme atteint bien les ouvriers ; c'est le choix entre ces deux tables-ci qui ne se voit
pas à ce volume.

## Ce qui tourne

Trois campagnes à graines disjointes (20260922 smith, 20260923 melbaa, 20260924 mochy) derrière
l'estimateur corrigé. Elles se moyenneront par `tools/merge_met.py`, qui **refuse** deux
campagnes à la même graine et imprime le χ² réduit entre elles — le contrôle qu'une campagne
unique ne peut pas s'offrir.

## Ce que la fiche ne prétend pas

- La table **n'est pas publiée** et ne remplace rien : ni dans l'artefact, ni dans les mesures.
- Sa **force** n'est pas établie. Une table plus proche d'une autre table n'est pas une table
  meilleure, et le seul énoncé qui autoriserait la bascule est un affrontement à volume.
- La **profondeur** qui l'a produite est 0. Sa sensibilité à la profondeur n'est pas mesurée.

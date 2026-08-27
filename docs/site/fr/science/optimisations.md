# Les optimisations, et les quatre projections que la mesure a démenties

## Le point de départ

Un moteur qui joue bien mais met deux secondes par décision n'est pas utilisable dans un
navigateur. Le travail d'optimisation avait donc un but précis, et une contrainte : **aller plus
vite sans dégrader l'analyse**. Cela exclut tout ce qui échange de la qualité contre du temps.

Ne restent que les gains **exacts** — le résultat ne bouge pas d'un bit — ou **mesurés gratuits** :
il bouge moins que le bruit, chiffré.

## Ce qui a été gagné

| | Avant | Après | |
|---|---|---|---|
| Décision 2-ply `(0,1,3)` | 2,0075 s | **0,306 s** | **×6,6** |
| Décision 3-ply | 60 à 96 s | **10,60 s** | ×5,7 à ×9 |
| Artefact (poids) | 2,1 Mio | **1,06 Mio** | ×1,99 |

Tous les gains de vitesse sont **exacts** : le corpus de non-régression et l'égalité bit à bit avec
le chemin scalaire tiennent à chaque étape.

## 1. L'inférence par lot

Le réseau est interrogé par **lots** : les poids sont lus une fois pour trente-deux positions au
lieu d'une fois par position. Mesuré ×8,5 en natif, ×2,21 dans un navigateur.

**Bit-identique au chemin unitaire** — pas seulement proche. Le noyau réordonne *quelle* position
une ligne de poids multiplie ensuite, jamais l'ordre de la somme d'une position donnée.

## 2. Le réseau d'élagage, et le plafond qu'il a d'abord rencontré

Un réseau 196 → 32 → 5, distillé du grand, trie les coups pour que le grand n'en note que `k`.
Mesuré 92,5× moins cher par évaluation, et il met le meilleur coup du grand dans son top-5 dans
94,2 % des décisions de contact.

**La projection annonçait ×4,3. La mesure a donné ×1,36.**

```{admonition} La cause, et elle est instructive
:class: important

Le noyau calcule **32 voies quoi qu'il arrive**. L'élagage retirait 82 % des évaluations mais
seulement **26 % du travail** : chaque nœud faisait toujours son appel, avec cinq positions au lieu
de vingt. **Un appel à cinq positions coûte exactement ce que coûte un appel à trente-deux.**

Remplissage mesuré : **14,5 %** des voies portaient une position utile.
```

## 3. Remplir les lots — le gain qui a débloqué le reste

En réunissant les survivants des **vingt-et-un jets** d'un nœud dans les mêmes lots, le remplissage
passe de 14,5 % à **80,5 %**, et les voies calculées de 831 136 à 150 112.

| | Sans élagage | `k=12` | `k=3` |
|---|---|---|---|
| s/décision | 2,0075 | **0,5588** | **0,2396** |
| gain | — | ×3,6 | ×8,4 |

Et le gain **se transporte dans le navigateur** : ×3,65 mesuré sur Firefox, contre ×3,9 en natif.
C'était la question ouverte, le lot n'y rendant que ×2,21.

## 4. La sparsité des entrées

Le vecteur de 196 caractéristiques n'a que **26 entrées non nulles** en moyenne, et **38,3** pour
l'union d'une fratrie de 32 — les frères ne diffèrent que d'un coup.

**C'est exact, pas approché** : en IEEE 754, `acc + w × 0,0` vaut `acc` sans arrondi. Sauter ces
termes ne déplace pas un bit.

Mesuré : **×1,15** sur une décision à toute profondeur, ×1,23 sur le petit réseau seul.

## Les quatre projections démenties

C'est la section la plus utile de cette page : **quatre fois, un raisonnement sur le nombre
d'opérations a prédit le mauvais résultat.**

| Projection | Mesure |
|---|---|
| « L'élagage doit rendre ×4,3 » | **×1,36** — le noyau calcule 32 voies quoi qu'il arrive |
| « Grouper les passes pour garder le petit réseau en cache » | **2,2 % plus lent** |
| « Fusionner aussi les lots du petit réseau » | **0,7 à 0,9 %** — dans le bruit, branche abandonnée |
| « Sauter 80 % de la première couche » | **plus lent** en indirect ; il a fallu **compacter** les colonnes |

La quatrième mérite d'être détaillée : sauter les entrées nulles en indexant `w_row[nonzero[idx]]`
faisait **cinq fois moins de multiplications** et allait **plus lentement**. Il a fallu rassembler
les colonnes vivantes et les poids correspondants dans des tampons **contigus** pour que la boucle
chaude reste un flux. **Le motif d'accès bat le compte d'opérations.**

```{admonition} La leçon, écrite dans le code
:class: warning

Toute projection de vitesse se vérifie par une mesure avant d'être écrite. Le code porte, à côté de
chaque optimisation, la version naïve qui a échoué — pour que personne ne la réessaie.
```

## Ce qui est fermé, avec son chiffre

| Idée | Verdict mesuré |
|---|---|
| Régler la largeur de lot | 1,3 % au mieux ; et le compilateur ne vectorise la boucle chaude qu'à 32 |
| Fusionner les lots du petit réseau | 0,7 %, abandonné |
| Grouper les passes pour le cache | 2,2 % **plus lent** |
| L'encodage | 0,00037 ms — 0,6 % d'une évaluation |
| Le travail non-réseau de la recherche | ≤ 3,5 % d'une décision |
| Dés quasi-aléatoires | variance ÷1,00 à 1 296 essais, ÷1,03 à 144 |
| La profondeur comme levier de **force** | +0,00022 d'équité par ply — dans le bruit |

## La contraction FMA, débusquée par une vérification

En vérifiant qu'un réarrangement de boucle ne changeait rien, les équités bougeaient de ~3e-9.
Écartés par la mesure : la composition des lots, la mémoire non initialisée (valgrind), le
non-déterminisme.

Restait la **contraction** : le compilateur fusionne `a×b + c` en un FMA — **un** arrondi au lieu de
deux — et il le fait **selon la forme du code autour**. À entrées et ordre de sommation identiques,
réarranger une boucle déplaçait le résultat.

`-ffp-contract=off` sur le fichier de recherche, et lui seul. Coût mesuré : **1 %**.

```{admonition} Pourquoi c'était important
:class: note

Ce projet fait reposer beaucoup sur l'exactitude bit à bit — l'empreinte qui verrouille un journal
de campagne, la reprise d'une campagne interrompue, le corpus de non-régression. La laisser dépendre
de la forme du code, c'est la perdre au premier refactor, **sans un signe**.
```

## Ce qui reste ouvert

- **Les filtres à seuil d'équité**, comme GNU Backgammon (« garder 8 coups à moins de 0,16 » au
  lieu d'un nombre fixe) : adaptatif, donc plus rapide sur les positions évidentes *et* plus fin
  sur les serrées.
- **Une table de transposition** sur les nœuds de recherche — dont le taux de répétition doit être
  **mesuré** avant qu'une ligne soit écrite.
- **L'élagage des nœuds de hasard** (star1/star2) : exact, mais difficile et au bénéfice inconnu.

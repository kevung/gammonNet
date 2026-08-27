# Le taux d'erreur : le PR

## Ce que le PR est

Le **Performance Rating** est le taux d'erreur d'un joueur, jugé par un analyseur plus fort :

$$ PR = 500 \times (\text{équité moyenne perdue par décision}) $$

Le facteur 500 est une convention d'affichage : il met un joueur de club vers 10 et un moteur vers
0,5.

**L'arbitre doit être plus fort que le sujet.** Un joueur ne peut pas juger ses propres erreurs :
il choisirait toujours ce qu'il croit le meilleur, et son PR serait zéro par construction. Le banc
**refuse** de tourner si l'arbitre n'est pas strictement au-dessus de tout ce qu'il juge.

## Le résultat

600 décisions de contact, graine 20260827, arbitre **GNU Backgammon 3-ply** sur tous les coups
légaux.

| Configuration | PR | IC 95 % | Accord | Référence publiée |
|---|---|---|---|---|
| 0-ply | **1,088** | [0,802 ; 1,412] | 83,3 % | 1,06 |
| 1-ply | **0,499** | [0,330 ; 0,705] | 88,7 % | 0,50 |
| 2-ply, sans élagage | **0,273** | [0,190 ; 0,364] | 90,2 % | 0,22 |
| 2-ply, élagage `k=12` | 0,375 | [0,264 ; 0,499] | 89,5 % | — |

**Les trois valeurs de référence tombent dans leur intervalle.**

Le PR descend à chaque ply — c'est le contrôle que le plan du projet désigne comme le plus
révélateur de toute la chaîne : *« un PR qui ne bouge pas quand on ajoute un ply signale une
recherche fausse »*.

Le **1-ply à 0,499 contre 0,50 publié** est le fait le plus fort de cette page : deux chaînes
indépendantes, deux arbitres différents, le même chiffre au millième.

## L'appariement, et pourquoi il n'introduit pas d'artefact

GNU Backgammon n'est pas invité à **choisir** un coup dans sa notation : il est invité à
**évaluer nos positions résultantes**. Les deux camps classent donc exactement le même ensemble, et
un désaccord est un vrai désaccord d'évaluation, pas une erreur de lecture d'une notation.

C'est la règle que tout ce dépôt suit : *une seconde façon, non vérifiée, de lire un coup est une
source d'erreur silencieuse*.

## Le contrôle bloquant a servi — contre moi

Le premier passage a rendu **0,946 au 0-ply et 0,946 au 1-ply**, au chiffre près. Le contrôle a
fait exactement ce pour quoi il existe.

Ce n'était pas la recherche : à `filter[1] = 1`, la passe profonde du 1-ply ne rescore **qu'un seul
candidat** — celui que la passe superficielle a déjà mis en tête — donc le coup choisi reste
exactement celui du 0-ply. Un filtre mal posé, pas un moteur faux.

## La prédiction vérifiée

Le 2-ply **élagué** donne 0,375, soit 0,155 au-dessus de la référence — hors intervalle. Plutôt
que d'invoquer le filtre ou le corpus, une hypothèse chiffrée a été posée :

> L'élagage `k=12` a une perte mesurée de **+0,00023 d'équité par décision**, soit **0,115 de PR**
> exactement. Il expliquerait les trois quarts de l'écart.

Mesuré : la différence entre les deux configurations de 2-ply vaut **0,102**.

La prédiction tombe **à 11 % près**, sur une quantité obtenue par une voie entièrement différente —
un banc de décisions appariées d'un côté, un PR contre un arbitre externe de l'autre.

## La reproductibilité de la métrique elle-même

La mesure a été refaite sur une seconde machine, avec un **autre build de GNU Backgammon** : même
version nominale, mêmes poids, build antérieur de plus d'un an.

| ply | machine A | machine B | écart |
|---|---|---|---|
| 0 | 1,088 | 1,088 | 0,000 |
| 1 | 0,499 | 0,498 | 0,001 |
| 2 (`k=12`) | 0,375 | 0,373 | 0,002 |
| 2 (sans élagage) | 0,273 | 0,270 | 0,003 |

Le corpus est identique au bit près sur les deux machines, et notre réseau y rend la même valeur.
**Ce qui diffère est l'arbitre.**

La différence a été détectée puis **bornée avant d'être subie** : cinq décisions sondées des deux
côtés, écart absolu moyen 2,9e-5, **de signe aléatoire** — donc s'annulant sur 600 décisions.
Effet prédit ±0,0006 ; écarts observés 0,001 à 0,003.

```{admonition} Ce que cela dit de la métrique
:class: important

Un PR mesuré contre GNU Backgammon n'est reproductible qu'à **~±0,005 près d'un build à l'autre**,
à version nominale et poids identiques. C'est une limite de la métrique, pas de la chaîne — et elle
est trente fois plus petite que l'intervalle de confiance du PR lui-même.
```

## Les deux réserves

- **Le corpus est uniquement de contact.** Une référence de PR se mesure d'ordinaire sur un mélange
  réaliste, courses comprises. Le contact étant la partie difficile, ce PR est **probablement
  pessimiste** — mais ce n'est pas mesuré, et l'écart n'est pas chiffré.
- **L'arbitre de l'auteur des chiffres de référence n'est pas connu.** L'accord aux trois
  profondeurs est un argument fort que la méthode est voisine, pas une preuve.

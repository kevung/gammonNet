# L'analyse d'un vrai match, décision par décision

## Ce que ce banc apporte que la force ne dit pas

La campagne de force rend un scalaire sur 50 000 paires : **de combien**. Elle ne dit pas **où** les
deux moteurs diffèrent, ni si leurs désaccords portent sur des décisions qui comptent. C'est
pourtant la première chose qu'un utilisateur verra.

## Le protocole

Un match réel de 7 points joué par des humains en tournoi. Analyse 2-ply, filtre `(0,1,3)`, élagage
`k=12`, **au score et au videau réels de chaque décision**.

**La lecture du fichier est portée par GNU Backgammon** : ce dépôt ne sait lire ni `.mat` ni `.sgf`
— c'est une frontière volontaire. Il ne consomme que des identifiants de position, un score et un
videau.

## Le résultat

**139 décisions, accord sur le meilleur coup : 120/139 — 86,3 %.**

Ce que chaque arbitre dit du coût des 19 désaccords :

| | Arbitre **gnubg** (EMG) | Arbitre **nous** (2·MWC−1) |
|---|---|---|
| médiane | **+0,0048** | +0,0009 |
| moyenne | +0,0062 | +0,0021 |
| quartiles | +0,0022 / +0,0101 | — |
| **maximum** | **+0,0195** | +0,0142 |
| sous 0,01 | 13/19 | — |
| **au-dessus de 0,05** | **0/19** | 0 |

## Ce que cela établit

**C'est le profil d'un moteur équivalent.** Un moteur plus faible se trahirait par une **queue** —
quelques désaccords à 0,05 ou 0,10, sur des positions qui décident d'une partie. Cette queue
n'existe pas : le pire désaccord du match entier vaut 0,0195, et GNU Backgammon lui-même ne classe
une décision comme comptant qu'au-delà de ~0,05.

Les deux moteurs divergent **là où plusieurs coups se valent**, pas là où une partie se décide.

## Ce que cela n'établit pas

```{admonition} Ce n'est pas une mesure de force
:class: warning

139 décisions n'en portent pas. C'est un **diagnostic** : il dit la nature des désaccords, pas leur
poids sur une saison de jeu.
```

**Les deux colonnes ne se comparent pas en magnitude.** Les échelles diffèrent — EMG contre
`2·MWC−1`, affines l'une de l'autre à pente positive. Ce qui est robuste est que **les deux
concluent « petit »**, et chacune se favorise par construction.

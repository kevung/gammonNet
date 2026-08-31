# T3C — un vrai match, décision par décision : où les deux moteurs divergent, et ce que ça coûte

**Date** : 2026-08-27 · **Machine** : la machine de calcul · **Branche** : `t3c-analyse-de-match`

> **La question.** T35 rend un scalaire sur 50 000 paires : *de combien*. Il ne dit pas **où** les
> deux moteurs diffèrent, ni si leurs désaccords portent sur des décisions qui comptent. C'est
> pourtant la première chose qu'un utilisateur verra.
>
> **La réponse.** Sur un match réel de 7 points, **139 décisions, 19 désaccords (13,7 %)** — et
> **aucun ne coûte plus de 0,0195 d'équité**. Les deux moteurs divergent là où plusieurs coups se
> valent, jamais là où une partie se décide.

## Le protocole

Match `test.sgf` — HSBT Paris 2023, 7 points, joué par des humains. Analyse 2-ply, filtre
`(0,1,3)`, élagage `k=12`, au score et au videau réels de chaque décision.

**La lecture du fichier est portée par gnubg.** `CLAUDE.md` place l'import de matchs hors de ce
dépôt ; rien ici ne sait lire un `.mat` ni un `.sgf`. Nous ne consommons que des identifiants de
position, un score et un videau.

**L'appariement des coups est par construction.** gnubg n'est pas invité à choisir dans sa
notation : il est invité à **évaluer nos positions résultantes**. Les deux camps classent donc
exactement le même ensemble, et un désaccord est un vrai désaccord d'évaluation — pas un artefact
de lecture. C'est la règle que `best_play` et `ranked_plays` suivent déjà : *une seconde façon, non
vérifiée, de lire un coup* est une source d'erreur silencieuse.

## Le résultat

**Accord sur le meilleur coup : 120/139 — 86,3 %.**

Ce que chaque arbitre dit du coût des 19 désaccords :

| | arbitre **gnubg** (EMG) | arbitre **nous** (2·MWC−1) |
|---|---|---|
| médiane | **+0,0048** | +0,0009 |
| moyenne | +0,0062 | +0,0021 |
| quartiles | +0,0022 / +0,0101 | — |
| **maximum** | **+0,0195** | +0,0142 |
| sous 0,01 | 13/19 | — |
| **au-dessus de 0,05** | **0/19** | 0 |

*(La colonne « nous » porte sur 17 des 19 : l'élagage tronque notre liste de candidats, et le coup
de gnubg n'y figure pas toujours. La colonne gnubg est complète — il évalue tous nos coups légaux.)*

## Ce que cela établit, et ce que cela n'établit pas

**Le profil est celui d'un moteur équivalent.** Un moteur plus faible se trahirait par une
**queue** — quelques désaccords à 0,05 ou 0,10, sur des positions qui décident d'une partie. Cette
queue n'existe pas : le pire désaccord du match entier vaut 0,0195, et gnubg lui-même ne classe une
décision comme comptant qu'au-delà de ~0,05.

**Les deux colonnes ne se comparent pas en magnitude.** Les échelles diffèrent — EMG contre
`2·MWC−1`, affines l'une de l'autre à pente positive (sonde T35 du 2026-08-09). Ce qui est robuste
est que **les deux concluent « petit »**, et chacune se favorise par construction : gnubg juge avec
son réseau, nous avec le nôtre. Aucune n'est publiée seule — la règle de T39.

**Ce n'est pas une mesure de force.** 139 décisions n'en portent pas ; la règle 2 de `CLAUDE.md`
s'applique. C'est un **diagnostic** : il dit la nature des désaccords, pas leur poids sur une
saison de jeu. Le poids, c'est T35 qui le donne.

## Trois pièges payés en chemin, tous dans le code

1. **gnubg n'imprime pas de retour à la ligne après son invite.** Tout `readline` bloque pour
   toujours ; il faut lire caractère par caractère avec `select`.
2. **`next roll` n'émet pas toujours une seule invite.** Compter une invite par commande décale
   toutes les réponses d'un cran, **en silence** — le parsing lit alors le plateau d'une autre
   décision. La parade retenue est une purge différenciée : longue après les deux commandes de
   navigation, qui font calculer gnubg, courte après les commandes d'état, qui répondent sans rien
   calculer.
3. **La position résultante a rendu la main**, donc l'état de match qui la décrit est celui de
   l'**adversaire**. Une première version passait l'état non retourné : elle aurait fait optimiser
   le mauvais joueur en rendant des nombres parfaitement plausibles.

## Ce que ce banc ouvre

C'est le **substrat du PR** : analyser un match décision par décision contre un arbitre est
exactement le calcul du PR, qui n'a jamais tourné et qui porte la condition de sortie de la
phase 3 (1,06 → 0,50 → 0,22).

## Reproduire

```bash
python bench/analyse_match.py --match test.sgf --ply 2 --prune-k 12 --max-decisions 400
```

Sortie : [`t3c-analyse-match.json`](t3c-analyse-match.json) — pour chaque décision, les candidats,
les classements, les équités et les cinq probabilités des deux camps.

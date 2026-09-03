# 2026-09-03 — Ce que coûte la taille, et ce que coûte la distillation elle-même

**Fiches** : préparation de T72 (P3, réduire le réseau), et lecture qui éclaire T71.
**Instrument** : `bench/measure_t70.py` sur le registre money de T70, 10 000 décisions disputées,
2-ply, `prune_k = 12`. **Étalon** : l'incumbent 2-ply, **0,00313** [0,00298 ; 0,00327].

## Le résultat qui n'était pas cherché

Six architectures ont été distillées du réseau actuel, sur le même corpus, à la même graine,
une seule chose changeant d'une ligne à l'autre — la taille. La dernière ligne du tableau est le
témoin : **la même architecture que l'original**.

| Architecture | MACs | × réf | Perte par décision | IC 95 % |
|---|---|---|---|---|
| **l'original** | 526 976 | 1,000 | **0,00313** | [0,00298 ; 0,00327] |
| 512-512-256-128 **redistillé** | 526 976 | 1,000 | **0,00990** | [0,00930 ; 0,01053] |
| 320-160-80 | 127 120 | 0,241 | 0,01071 | [0,01013 ; 0,01133] |
| 256-128-64 | 91 456 | 0,174 | 0,01068 | [0,01007 ; 0,01131] |
| 192-96-48 | 60 912 | 0,116 | 0,01147 | [0,01083 ; 0,01215] |
| 96-48-24 | 24 696 | 0,047 | 0,01119 | [0,01062 ; 0,01179] |
| 128-64-32 | 35 488 | 0,067 | 0,01192 | [0,01126 ; 0,01261] |

**À taille identique, la distillation perd un facteur 3,2.** 0,00313 devient 0,00990 sans qu'un
seul paramètre ait été retiré. Le réseau redistillé a exactement la forme de son maître, il a
appris sur 800 000 positions étiquetées par ce maître, et il joue trois fois plus mal.

**Réduire la taille, en comparaison, ne coûte presque rien.** De 527 000 à 25 000 MACs — un
facteur 21 — la perte passe de 0,00990 à 0,01119, soit **+13 %**. Les intervalles de 320-160-80,
256-128-64, 192-96-48 et 96-48-24 se recouvrent tous : sur ce corpus, ces quatre tailles sont
indiscernables entre elles.

## Ce que cela change pour T72

T72 vise 60 000 à 100 000 MACs à qualité indiscernable. Le résultat ci-dessus dit que **la
contrainte de taille n'est pas le problème** : elle est atteignable, et même largement dépassable.
Le problème est ailleurs, dans la méthode qui produit l'élève.

Il dit aussi ce que T72 devra mesurer pour ne pas se tromper de conclusion : son résultat sera à
comparer au **redistillé de même taille**, jamais à l'original. Sans ce témoin, une perte de 0,010
aurait été attribuée à la réduction alors qu'elle vient à 87 % de la distillation.

## Ce que cela change pour T71

Le candidat B1 de T71, entraîné sur 366 978 positions étiquetées **par notre 2-ply**, rend
**0,00537**. Le redistillé de même architecture, entraîné sur 800 000 positions étiquetées par le
**0-ply** du même réseau, rend 0,00990.

**Les étiquettes 2-ply valent donc mieux que les 0-ply d'un facteur 1,8**, à architecture égale et
sur moins de données. C'est la prémisse de T71 confirmée par un chemin qu'elle n'avait pas prévu :
la recherche met dans l'étiquette une information que le réseau statique n'a pas.

Mais les deux restent au-dessus de l'étalon 0,00313, et le témoin dit pourquoi : **ce n'est pas le
volume d'étiquettes qui manque, c'est que la distillation supervisée ne reproduit pas ce réseau.**
L'original n'a pas été appris ainsi — il vient d'un entraînement par différences temporelles sur
un volume de parties auto-jouées sans commune mesure avec 800 000 positions.

## Ce que ce document ne conclut pas

Il ne dit pas que la distillation est sans valeur : elle produit, à 25 000 MACs, un réseau qui
perd 0,0112 par décision **disputée**, sur un corpus qui ne contient que les ~10 % de décisions où
deux moteurs divergent. Ce n'est pas un PR, et la traduction en force de jeu demanderait une
mesure qui n'a pas été faite.

Il ne dit pas non plus que le volume ne compte pas — la courbe volume → force de T71, en cours de
mesure sur 1,5 million d'étiquettes, répondra à cette question-là et à elle seule.

## Reproduire

```
python tools/distill_smaller.py --sweep
for net in models/t72prep_*.bin; do
  python bench/measure_t70.py \
    --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model "$net" --ply 2 --prune-model models/prune_32.bin --prune-k 12 \
    --workers 30 --out "docs/mesures/$(basename "$net" .bin)-t70.json"
done
```

Les six entraînements prennent environ trois minutes chacun sur une RTX 4090 ; les six mesures,
environ deux minutes chacune sur 30 processus.

# T96 — le correctif amont du générateur de coups, mesuré avant d'être adopté

*2026-09-17 · mochy (32 fils), 26 processus · `tools/scan_movegen.py`*

> **Ce que cette fiche corrige, c'est une priorité que j'avais annoncée à tort.** Le dépôt amont
> a publié le 2026-08-12 (`5c9aa87`) un correctif de générateur de coups — *« a false forced-pass
> where a shorter play shadowed the maximal play, incidence at most 1/3700 »* — dans
> `c_engine/bg_engine.c`, **fichier que notre `Makefile` compile dans `libgammonnet.so` et dans
> le module WebAssembly**. Lu seul, ce constat désigne un défaut de correction dans un artefact
> distribué. Mesuré, il ne se manifeste pas.

---

## Ce qui a été mesuré, et comment

Deux passes, sur des positions **atteintes par jeu réel** plutôt que sur un corpus figé : la
question porte sur une incidence rare, et les 204 positions de T01 ne font que 4 284 couples
(position, jet).

### Passe 1 — contre GNU Backgammon, le générateur indépendant

Le même croisement que T01 : pour chaque couple, l'**ensemble des positions atteintes** de notre
côté contre celui de `gnubg_nn.moves`.

| | |
|---|---|
| positions visitées | 520 000 |
| couples (position, jet) | 10 920 000 |
| coups engendrés | 242 366 821 |
| **désaccords** | **0** |
| listes contenant deux fois la même position atteinte | 0 |

### Passe 2 — notre moteur avant contre après

Une empreinte SHA-256 qui couvre **les sous-coups eux-mêmes**, pas seulement les positions
atteintes : le défaut amont porte sur le nombre de dés du coup enregistré, et une comparaison qui
ne regarderait que les positions ne le verrait pas par construction.

La marche aléatoire qui produit les positions choisit son successeur **après tri sur la position
atteinte**, jamais dans l'ordre rendu par le générateur — sans cela, deux ordres de génération
différents feraient diverger les empreintes pour une raison qui n'est pas une divergence de
règles.

| | `b2750df` (le nôtre) | `7184e2f` (corrigé) |
|---|---|---|
| coups engendrés | 242 791 638 | 242 791 638 |
| listes mêlant deux longueurs de coup | 0 | 0 |
| **graines dont l'empreinte diffère** | **0 / 26** | |

---

## Le verdict

**Le correctif ne déplace rien sur notre chemin.** Les vingt-six empreintes sont identiques, et
la comparaison à gnubg ne trouve aucun désaccord sur 10,9 millions de couples.

L'incidence annoncée en amont est une **borne** — vraisemblablement tirée du débordement de leur
table de hachage, que le correctif traite en même temps — et non une fréquence observée. Si le
défaut se déclenchait une fois sur 42 000 couples, les vingt-six empreintes auraient divergé
vingt-six fois.

**Conséquence pour l'artefact publié : aucune.** Il n'y a rien à corriger, rien à republier, et
la ligne « urgence » que cette fiche devait porter n'a pas lieu d'être.

**Conséquence pour l'épingle :** monter à `7184e2f` reste souhaitable — le build est propre, la
suite passe (1 836 tests), et c'est la seule façon d'obtenir les nouveaux poids —, mais c'est un
changement de confort. Il porte en revanche une contrainte qui n'était pas visible :

> **`7184e2f` ne contient plus `cubeless_prob5_512_512_256_128.pt`.** Les trois seuls échecs de
> la suite sous la nouvelle épingle sont `test_environment.py`, qui vérifie que le `.pt` du
> réseau de record est présent. L'épingle et les poids **ne peuvent donc pas bouger l'un sans
> l'autre** : ou bien on reste à `b2750df`, ou bien on adopte les poids de T96. Un dépôt épinglé
> à `7184e2f` et servant les anciens poids aurait une provenance qu'il ne sait plus produire.

---

## Ce que ça coûte de le refaire

5 min 30 sur 26 processus pour les deux passes, soit ~2,4 h·cœur. `tools/scan_movegen.py` prend
`--positions`, `--seed`, `--no-gnubg` (les contrôles internes et l'empreinte seuls) et `--out`.

```
seq 0 25 | xargs -P 26 -I{} python tools/scan_movegen.py \
    --positions 20000 --seed $((20260917 + {})) --out build/scan/s{}.json
```

## La réserve

Une incidence nulle sur 10,9 millions de couples **n'est pas une preuve d'absence** : elle borne
l'incidence à moins de ~3/10⁷ par couple avec 95 % de confiance. Elle dit que le défaut ne
concerne pas la pratique de ce dépôt, pas qu'il n'existe pas.

# Vérifier l'artefact vous-même

L'archive contient de quoi contrôler qu'elle fait ce qu'elle annonce, **sans nous croire**.

## La parité avec le moteur de référence

```sh
node verify/parity.mjs
```

Il compare le module WebAssembly au moteur natif sur un repère de **2 000 positions**, et
**refuse** au-delà de 1e-6.

Attendu :

```
✅ scalaire   max|Δ| = 0.000e+0
✅ SIMD       max|Δ| = 6.407e-7
```

Le build scalaire est **exact**. Le build SIMD réassocie les sommes, d'où l'écart de 6,4e-7 —
borné, documenté, et sans effet sur le coup choisi.

## Les sommes de contrôle

```sh
sha256sum -c SHA256SUMS
```

Et le `sha256` des poids doit correspondre à celui inscrit dans `verify/*.provenance.json` — le
même depuis le premier jour du projet.

## Les mesures brutes

`evidence/` contient les données derrière chaque chiffre des notes de version :

| Fichier | Ce qu'il porte |
|---|---|
| `t3e-pr.json` | le taux d'erreur aux trois profondeurs, avec ses intervalles |
| `t3c-analyse-match.json` | les 139 décisions d'un vrai match, les deux moteurs |
| `t21b-navigateur-*.json` | le coût d'une décision et le parallélisme, dans un navigateur |
| `t3a-prune-search.json` | ce que l'élagage coûte et rapporte, par `k` |

Rien n'y est agrégé : ce sont les sorties des bancs, telles qu'ils les ont écrites.

## Les invariants de l'API

```sh
node verify/api_invariants.mjs
```

La parité dit que le module **calcule** comme le moteur natif. Ceci dit qu'il **répond ce qu'il
promet** : que la liste des coups candidats est ordonnée par équité, que son premier élément est
bien le coup que rend `bestPlay`, que chaque candidat porte cinq probabilités exploitables, que
celles-ci décrivent **le même joueur que l'équité posée à côté d'elles**, et que, filtre de coups
éteint, les N meilleurs coups ne dépendent pas de N.

Le contrôle de référentiel est le plus récent, et il a fallu deux erreurs de lecture chez le même
consommateur pour l'écrire. Il ne peut pas se faire par une vérification d'imbrication : une
distribution retournée reste parfaitement imbriquée. Ce qui mord, c'est l'identité — l'équité
cubeless money **est** une fonction des cinq probabilités, donc à 0-ply, recalculer l'une depuis
les autres doit reproduire l'autre, au signe près. Sous une inversion, la reconstruction sort avec
le signe opposé, et aucune tolérance ne cache ça. S'y ajoute le coup qui **finit** la partie : ses
probabilités valaient zéro, ce qui, retourné, disait « gain certain, aucun gammon » sur une sortie
qui gagne un gammon.

Ce dernier point n'est pas décoratif. `rankPlays` dimensionnait son tampon de candidats sur le
nombre de coups demandé, et la recherche tronque à la taille de son tampon **avant d'évaluer quoi
que ce soit**, dans l'ordre de génération : demander 3 coups en faisait classer 3 arbitraires. Sur
l'ouverture 3-1, le deuxième coup rendu valait −0,1262 là où la liste complète trouve −0,0029. Rien
ne clochait : probabilités plausibles, équités plausibles, ordre décroissant. Il a fallu comparer
deux appels pour le voir.

Avec le filtre **actif**, les N meilleurs dépendent légitimement de N — un filtre à N cherche en
profondeur les N coups les plus prometteurs d'une passe superficielle, et le vrai N-ième peut se
trouver en dehors. GNU Backgammon a le même comportement.

# Spec — le format de poids `BGN6` (float16 de transport)

**Statut** : en vigueur depuis T50 (v1.0.1). **Code** : écriture `tools/pack_fp16.py` (`pack`),
lecture `src/gn_infer_reference.c` (`load_fp16`, `from_half`). **Tests** : `tests/test_fp16.py`.
**Repère de parité** : `build/reference16.bin` (`make wasm-parity`), servi dans l'artefact sous
`verify/reference16.bin`. **Mesure** : `docs/mesures/2026-10-22-float16-reseau-servi.md`.

Ce document s'adresse à **toute réimplémentation du lecteur** dans un autre langage. Il dit ce
que contient le fichier, comment le relire sans réinterpréter l'arithmétique, comment prouver
qu'on l'a relu juste, et ce que le format coûte par rapport au float32.

## 1. Ce que le format est, et ce qu'il n'est pas

`BGN6` **transporte**, il ne calcule pas. Les poids y sont stockés en IEEE 754 binary16 ; le
lecteur les reconvertit en binary32 **au chargement**, et le réseau calcule ensuite exactement
comme avec un `.bin` float32 — même noyau, même ordre de sommation, même vitesse. Le gain est
la taille du fichier (×1,99), rien d'autre.

Un réseau chargé depuis un `.bin16` **n'est pas** le réseau float32 : ses poids ont été
arrondis. Il rend d'autres sorties (§5) et se vérifie contre **son propre** repère (§4), jamais
contre celui du float32. Il garde en revanche son nom (`CLAUDE.md`, nomenclature : une
conversion de format ne fait pas un réseau nouveau) ; seul le suffixe `.bin16` le distingue.

## 2. La disposition du fichier

Tout est **petit-boutiste**, sans remplissage ni alignement.

| Champ | Type | Valeur pour `strehl-prob5-512-512-256-256` |
|---|---|---|
| magic | 4 octets ASCII | `BGN6` (le float32 porte `BGNN` : aucun lecteur ne peut confondre les deux) |
| `num_hidden` | int32 | 4 (1 ≤ `num_hidden` ≤ 8) |
| `input_size` | int32 | 196 |
| `activation` | int32 | 0 = ReLU (1 sigmoïde, 2 tanh, 3 leaky ReLU, 4 hard sigmoïde) |
| `output_mode` | int32 | 2 = prob5, cinq sorties sigmoïdes (0 probabilité, 1 équité linéaire : une sortie) |
| `hidden_sizes` | int32 × `num_hidden` | 512, 512, 256, 256 |
| couches | voir ci-dessous | `num_hidden + 1` couches, de l'entrée vers la sortie |

La couche `L` a `rows = layer_out[L]` lignes et `cols = layer_in[L]` colonnes, avec
`layer_in[0] = input_size`, `layer_in[L] = hidden_sizes[L-1]`, `layer_out[L] = hidden_sizes[L]`
pour les couches cachées, et `layer_out[num_hidden] = 5` en prob5 (1 sinon). Pour chaque couche,
dans l'ordre :

| Bloc | Type | Taille |
|---|---|---|
| poids | binary16 × `rows · cols` | **ligne par ligne** : le poids de la sortie `i` et de l'entrée `j` est à l'indice `i · cols + j` |
| biais | **binary32** × `rows` | — |

Les biais restent en float32 : 1 541 valeurs sur 561 925 (0,27 % du fichier), et l'endroit où
une erreur se propagerait le plus. Le fichier s'arrête exactement après le dernier biais. Un
fichier trop court **et** un fichier trop long sont refusés par le lecteur C (`tests/test_fp16.py`,
`test_a_truncated_artifact_is_refused_not_guessed` et
`test_an_overlong_artifact_is_refused_not_trimmed`) : un octet après le dernier biais est une
forme incomprise, pas une marge. Une réimplémentation refuse de même. (Jusqu'à v1.8.1 incluse, le
lecteur C s'arrêtait au dernier biais attendu sans regarder la suite.)

Pour le réseau servi : 1 126 968 octets, contre 2 247 736 pour le `.bin`.

## 3. La conversion — deux règles, et un piège

**À l'écriture** (`pack_fp16.py`) : chaque poids binary32 est arrondi en binary16 **au plus
proche, ex æquo au pair** (`numpy.astype("<f2")`, l'arrondi IEEE par défaut). Le plus grand
poids du réseau servi vaut 16,73 en valeur absolue : aucun ne déborde vers l'infini, et un
fichier qui contiendrait un infini ou un NaN n'a pas été produit par cet outil.

**À la lecture** : chaque binary16 est converti en binary32 **exactement**. La conversion est
exacte dans ce sens — tout binary16 fini est représentable en binary32 — et n'a donc qu'un seul
résultat correct ; il n'y a rien à arrondir ni à choisir. Toute conversion correcte — une
instruction matérielle, une bibliothèque, la routine `from_half` recopiée — donne les mêmes
bits, à une condition :

> **Le piège : les sous-normaux.** Le réseau servi contient **631 poids sous-normaux** en
> binary16 (valeur absolue sous 2⁻¹⁴ ≈ 6,1×10⁻⁵, non nulle), et 30 poids arrondis à zéro. Un
> lecteur qui les ramène à zéro (*flush-to-zero*, mode « dénormaux = 0 » d'un SIMD, conversion
> maison qui ignore l'exposant nul) produit **un autre réseau**, et échoue au repère §4. Les
> sous-normaux binary16 deviennent des **normaux** binary32 : il faut les renormaliser
> (`from_half`, branche `exponent == 0`).

Le zéro négatif se conserve (bit de signe), ce qui ne change aucune sortie mais permet de
comparer les poids relus bit à bit.

## 4. La preuve de parité

Un lecteur de `BGN6` est juste s'il rend, sur le repère `reference16.bin`, les sorties
que le moteur natif de ce dépôt y a écrites.

**Le repère** (`tools/dump_reference.py --model …bin16 --out build/reference16.bin`) a la même
forme que `reference.bin` :

```
int32     magic 'GNRF'
int32     nombre de positions (2 000)
int32     nombre de caractéristiques (196)
int32     nombre de sorties (5)
float32[] caractéristiques, 2 000 × 196, positions bout à bout
float32[] sorties,          2 000 × 5, calculées par le natif depuis le .bin16
```

Les caractéristiques sont **les mêmes** que celles de `reference.bin` ; seules les sorties
diffèrent. Une réimplémentation se vérifie donc sur ses deux chargeurs avec les mêmes entrées.

**Le critère** est celui de T20 : `max|Δ| < 1e-6` sur les 10 000 sorties. **Mesuré** le
2026-10-22 (`node wasm/parity.mjs`) : `max|Δ| = 0` pour le module WebAssembly scalaire et SIMD,
sur les deux formats. Un écart de l'ordre de 1e-4 désigne presque toujours un lecteur qui
compare au mauvais repère (le float32) ; un écart sur quelques sorties seulement désigne
presque toujours les sous-normaux (§3).

**Ce que le repère ne couvre pas** : le réseau d'élagage `strehl-prune-32`, emballé au même
format, n'a pas de repère propre ; sa parité se prouve par celle de la recherche qui l'utilise.

## 5. Ce que le format coûte

Mesuré le 2026-10-22 sur `strehl-prob5-512-512-256-256`, les deux réseaux (grand et élagage) en
`.bin16` (`docs/mesures/2026-10-22-float16-reseau-servi.md`) :

| Grandeur | Valeur | Instrument |
|---|---|---|
| **perte en jeu, réglage `normal` servi** (Δ apparié float16 − float32) | **−0,0000049** [−0,000016 ; +0,000006] par décision disputée | registre arbitré de T70, 9 786 décisions money, 2-ply, `k = 12` |
| coup différent, même instrument | 32 décisions sur 9 786 (0,33 %) | idem |
| coup différent à 0-ply | 0,042 % [0,036 ; 0,050] | 350 469 décisions, marche aléatoire |
| perte par décision à 0-ply | 1,7×10⁻⁸ | idem, jugée par le float32 |
| écart d'équité money par position, moyen / p99,9 / maximal | 1,27×10⁻⁴ / 7,0×10⁻⁴ / 8,6×10⁻³ | 9 617 222 positions résultantes |
| écart maximal sur une des cinq sorties | 8,1×10⁻³ | idem |
| vitesse | inchangée par construction : même calcul en float32, mêmes comptes d'évaluations | — |
| taille | ×1,99 plus petit (1 126 968 octets contre 2 247 736) | — |

Pour situer : l'int8 entraîné pour la quantification coûte +0,00060 sur le même registre
(`2026-09-02-T73-int8-arbitre-t70.md`), et le changement de poids de T98 a rapporté −0,00067.
Le float16 est **indiscernable de zéro** à cette échelle.

## 6. Ce qui est garanti, et ce qui ne l'est pas

**Garanti, par le repère** : un lecteur qui passe §4 rend, à 1e-6 près, ce que le moteur natif
de ce dépôt rend sur le `.bin16`. C'est une propriété du lecteur, vérifiable par quiconque ;
c'est la seule garantie que ce format offre.

**Mesuré, pas garanti** : l'écart entre le `.bin16` et le `.bin`. Aucune borne a priori ne le
tient — l'erreur d'arrondi d'un poids est bornée (2⁻¹¹ en relatif), mais sa propagation à
travers cinq couches dépend de la position. Ce qu'on peut écrire, c'est ce qui a été observé :

> **Sur 9,6 millions de positions, l'équité money d'une position évaluée depuis le `.bin16`
> s'écarte de celle du `.bin` de 1,3×10⁻⁴ en moyenne, de moins de 7×10⁻⁴ dans 99,9 % des cas, et
> de 8,6×10⁻³ au plus.** En jeu, au réglage servi, la perte est indiscernable de zéro
> (§5).

Une analyse stockée sous le `.bin` et recalculée sous le `.bin16` **change donc de valeur** — de
l'ordre de 10⁻⁴, rarement plus — et peut, dans environ 0,3 % des décisions disputées, désigner
un autre meilleur coup, d'équité quasi égale. Un appelant qui compare des analyses entre elles
doit traiter le passage d'un format à l'autre comme un changement de moteur, pas comme un
changement de transport.

**Hors mesure** : le contexte match et le videau en float16 ; les réseaux autres que
`strehl-prob5-512-512-256-256` et `strehl-prune-32`. Un nouveau réseau emballé en `BGN6` refait
§5 avant d'hériter de ces chiffres.

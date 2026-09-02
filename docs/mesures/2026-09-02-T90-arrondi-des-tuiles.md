# T90 — L'arrondi des tuiles : un garde-fou, zéro gain, et c'est normal

**Date** : 2026-09-02 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3, 8 cœurs
physiques / 16 fils, AVX2), Linux 7.1.9-arch1-2 · **Chaîne** : gcc 16.2.1 ·
**Branche** : `feat/t84-noyau-largeur`

> **Cette fiche ne mesure pas une vitesse.** Elle pose un garde-fou **avant** que T84 déplace
> ce qu'il garde. Le seul chiffre qu'elle produit est un coût, et il est nul.

## Le piège, et pourquoi il n'a pas été vu

Le portage Go a écrit, pour arrondir une dimension au multiple inférieur d'une tuile :

```go
rounded := outDim & ^(tile - 1)
```

C'est **correct seulement pour une puissance de deux**. Le masque garantit
`rounded <= outDim`, mais **pas** que `rounded` soit un multiple de la tuile — et c'est la
seconde propriété que la boucle `for j := 0; j < rounded; j += tile` utilise.

À tuile 6, largeur 195 :

| | |
|---|---|
| `195 & ^(6-1)` | **194** |
| 194 est-il un multiple de 6 ? | **non** (194 = 6×32 + 2) |
| dernier `j` visité | 192 |
| éléments lus | 0..197, soit **198** d'une ligne de **195** |

Trois flottants au-delà de la ligne. Les tests ne l'ont pas vu parce que **la tuile valait 4
quand ils ont été écrits**, et qu'à toute puissance de deux le masque et l'arrondi correct
coïncident exactement — ce que `tests/tile_asan.c` vérifie sur toutes les puissances de deux
jusqu'à 64 et toutes les largeurs jusqu'à 260.

`GN_EVAL_BATCH` vaut 32 ici et aucun masque de ce genre n'existe dans le C : **le code actuel
est sauf**. C'est précisément pourquoi la fiche est un garde-fou et non un correctif.

## Ce qui est livré

**`src/gn_tile.h`**, et rien d'autre à retenir :

- `gn_round_down_multiple(n, tile)` — `n - n % tile`, avec pour postcondition explicite
  *le résultat est ≤ n **et** un multiple exact de la tuile*. C'est la seconde moitié que le
  masque viole. Une tuile nulle ou négative rend 0 plutôt que de diviser par zéro : le noyau
  tombe alors entièrement dans sa queue scalaire, ce qui est lent — un mode de défaillance
  qui se voit, contrairement à une lecture hors matrice.
- `GN_STATIC_ASSERT_POWER_OF_TWO(n)` et `GN_STATIC_ASSERT_MULTIPLE_OF(n, tile)` — pour
  **énoncer l'hypothèse au compilateur** là où elle est faite, et non au lecteur.

**Ce que l'arrondi sûr coûte, lu dans l'assembleur généré** (`gcc -O3`, pas déduit) :

| écriture | instructions émises |
|---|---|
| `n & ~(8-1)` | `andl $-8` |
| `gn_round_down_multiple(n, 8)` | `andl $-8` + `testl`/`cmovle` (la garde n ≤ 0) |
| `gn_round_down_multiple(n, 6)` | `imulq`/`shrq`/`leal` (multiplication-décalage) |

**À tuile puissance de deux, c'est la même instruction**, plus deux pour la garde — payées
**une fois par appel de noyau**, pas une fois par élément. Le coût est donc nul à l'échelle
où il se mesurerait ; aucun banc n'a bougé (`bench-gemm`, `test_gemm_int8.py` : 105 tests,
bit à bit contre le scalaire).

## Où l'hypothèse est désormais énoncée

- `src/gn_gemm_int8.c` — la tuile de voies des trois chemins vectoriels (SIMD128, SSE2/AVX2)
  s'appelle maintenant `GN_INT8_LANES = 8` au lieu d'être un `8` littéral dans trois
  conditions de boucle, elle porte `GN_STATIC_ASSERT_POWER_OF_TWO`, et la borne de la boucle
  passe par `gn_round_down_multiple`. Sémantiquement identique à `n + 8 <= batch` ; ce qui
  change est que la tuile est nommée et que l'arrondi ne peut plus être réécrit en masque.
- `src/gn_int8_model.c` — `GN_INT8_CHUNK` doit tenir dans l'accumulateur de ligne de
  `gn_gemm_int8_relu` (256 entrées). C'était une phrase de commentaire et un refus **à
  l'exécution** ; c'est maintenant une assertion de compilation. Élargir la constante casse
  le build au lieu de faire échouer chaque évaluation à l'exécution.

## Le test, et pourquoi il a deux volets

`tests/tile_asan.c`, compilé à part sous `-fsanitize=address,undefined` (`make test-tile`,
et repris par `tests/test_tile.py` dans `make test`).

Un débordement de trois flottants au bout d'une ligne ne se voit pas sans redzone : sur un
tableau statique il y a simplement de la place. La ligne est donc allouée sur le tas **à la
taille exacte**.

| volet | ce qu'il exécute | attendu |
|---|---|---|
| positif | postcondition sur 34 tuiles × 261 largeurs ; masque ≡ arrondi sur toute puissance de deux ; noyau tuilé à **tuile 6** sur la ligne exacte | sort 0 |
| **négatif** (`--trap`) | la forme **masquée**, sur cette même ligne exacte | **meurt** en `heap-buffer-overflow` |

Le volet négatif n'est pas décoratif : sans lui, un build où ASan ne serait pas actif
laisserait le volet positif passer sans rien prouver. Vérifié :

```
==2087878==ERROR: AddressSanitizer: heap-buffer-overflow
READ of size 4 at 0x7d4d275e038c thread T0
    #0 tiled_sum tests/tile_asan.c:60
0x7d4d275e038c is located 0 bytes after 780-byte region
```

## Ce qui n'est PAS livré, et par qui

Le second volet de la fiche — **exposer les formes canoniques (`prune_k = 12`, filtre
`(0,1,3)`, profondeur 2) par l'API**, avec leur mesure de qualité attachée — touche
`wasm/gammonnet.mjs`, sur lequel T86 travaille en parallèle. Il est **laissé de côté ici**
pour ne pas entrer en collision, et reste à faire.

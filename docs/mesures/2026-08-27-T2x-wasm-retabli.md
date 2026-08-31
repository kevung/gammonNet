# 2026-08-27 — La cible WebAssembly rétablie, et un repère qui a bougé

## Ce qui a été fait

Emscripten avait disparu de la machine. Il est réinstallé **en 6.0.5**, la version
exacte que citent T20 et T21 (`docs/mesures/2026-08-03-T20-wasm.md`), par `emsdk` dans
`~/emsdk` — sans `sudo`, sans rien toucher hors de ce répertoire.

```bash
source ~/emsdk/emsdk_env.sh    # emcc 6.0.5, requis avant tout `make wasm`
```

Une différence subsiste, et elle est de nature : le relevé du 2026-08-03 dit
**`6.0.5-git`**, forme d'un paquet système construit depuis git ; ce qui est installé
aujourd'hui est la release 6.0.5 d'emsdk (commit `dbd755b5`). Même numéro de version en
amont, chaîne binaire pas nécessairement identique. **Ce n'est donc pas la version qui
prouve quoi que ce soit, c'est le repère ci-dessous.**

## La régression trouvée en vérifiant

La cible WebAssembly ne se construisait plus, et pas à cause d'Emscripten :

```
wasm-ld: error: gn_search.o: undefined symbol: gn_bearoff_probs
wasm-ld: error: gn_search.o: undefined symbol: gn_evalcache_lookup
wasm-ld: error: gn_search.o: undefined symbol: gn_cube_value
```

`WASM_SOURCES` avait dérivé derrière `SOURCES`. `gn_search.c` est le **même fichier** des
deux côtés, et la phase 3 lui a donné trois dépendances — table de fin de partie, cache
d'évaluation, videau — ajoutées au natif et jamais à la cible navigateur, qui n'avait plus
été construite depuis le 2026-08-03. Corrigé en alignant la liste.

`gn_bearoff.c` entre dans le module **sans sa table** : `gn_bearoff_shared()` rend NULL
tant que rien ne l'a chargée, et la recherche retombe sur le réseau. Servir la table à un
navigateur est une décision d'artefact — sa taille est en jeu — qui appartient à T50.

## Le repère, mesuré

`make wasm-parity`, 2000 positions × 5 sorties, tolérance 1e-6 de T20 :

| build | max\|Δ\| natif ↔ Wasm | T20, le 2026-08-03 |
|---|---|---|
| scalaire | **0,000e+00** — au bit près | 4,77e-07 (annoncé pour la parité) |
| SIMD | **6,407e-07** | — |

Taille : 54 954 octets (scalaire), 63 046 octets (SIMD).

## Ce que ce tableau ne dit pas

**Le repère de T20 n'est pas retrouvé, il est déplacé**, et l'écart n'est pas expliqué.
Les deux valeurs passent la tolérance de 1e-6, ce qui rend le module utilisable ; cela ne
rend pas les deux mesures comparables. Trois causes au moins sont possibles, et rien ici
ne permet de trancher entre elles :

1. la chaîne de compilation n'est pas la même construction (`6.0.5-git` contre release) ;
2. la liste de sources a changé — trois modules de plus entrent dans le lien ;
3. **le côté natif a changé** depuis le 3 août : T3A a retravaillé le regroupement et les
   lots de l'inférence, et le repère est produit par le natif d'aujourd'hui.

La troisième est la plus vraisemblable — le scalaire est passé de « 4,77e-07 » à
exactement zéro, ce qui ressemble à un ordre de sommation devenu identique des deux
côtés — mais **vraisemblable n'est pas mesuré**. Trancher demande de reconstruire le natif
du 3 août et de refaire les deux lectures ; l'expérience n'a pas été faite.

## Ce qui reste bloqué pour T73

Le micro-banc GEMM int8 **sur les sept plateformes** demande des appareils physiques et
des navigateurs réels, pas cette machine. La réinstallation d'Emscripten lève le blocage
de la compilation, pas celui-là.

Node : `v18.20.8` sur cette machine, contre `26.5.1` en T21. Sans effet attendu sur une
comparaison numérique — la sémantique flottante de WebAssembly est spécifiée — mais à
savoir avant toute lecture de **débit** sous Node.

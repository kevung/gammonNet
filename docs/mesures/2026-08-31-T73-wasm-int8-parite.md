# 2026-08-31 — Le chemin int8 câblé dans WebAssembly, et sa parité native↔Wasm au bit près

## Ce qui manquait

`src/gn_gemm_int8.c` était compilé dans la bibliothèque native depuis le début
de T73 (le micro-banc `bench_gemm_int8.c` l'exerçait déjà, seuil DS-09
franchi : ×2,13 au lot du moteur) mais **absent de `WASM_SOURCES`** — jamais
compilé pour la cible navigateur, donc jamais mesuré là où le critère
d'acceptation de T73 le demande : *« Le bit-à-bit natif↔Wasm tient sur le
chemin déterministe ; l'écart du repère reste identique après
quantification. »*

## Ce qui a été fait

- `src/gn_gemm_int8.c` ajouté à `WASM_SOURCES` (`Makefile`).
- `wasm/gn_wasm.c` : deux exports minces, `gnw_gemm_int8_relu` et
  `gnw_gemm_int8_raw`, passe-plat vers le noyau — comme tous les autres
  exports de ce fichier. Aucun réseau quantifié n'est câblé à l'inférence :
  ceci expose le NOYAU seul, pour la vérification de parité.
- `tools/dump_reference_int8.c` : fige un repère natif sur les cinq formes
  réelles du réseau embarqué (196→512→512→256→128→5), au lot du moteur (32),
  décalage 7 — même générateur déterministe (xorshift) et mêmes graines que
  `bench/bench_gemm_int8.c`, pour que les deux fichiers restent lisibles
  côte à côte. Les deux fonctions (`_relu` et `_raw`) sont exercées sur les
  cinq formes, pas seulement celle où chacune sert réellement dans le
  réseau — une couverture plus large, gratuite ici (pas de rollout, cinq
  petits GEMM).
- `wasm/parity_int8.mjs` : comparaison **au bit près**, pas à une tolérance —
  contrairement à `parity.mjs` (float32, seuil 1e-6). C'est la nature même de
  la garantie que `gn_gemm_int8.h` revendique : l'addition int32 est
  associative, donc un seul bit de désaccord invaliderait la revendication
  d'inconditionnalité du fichier.
- `make wasm-parity-int8` : la cible qui enchaîne les trois.

## Le résultat

```
repère : 5 couches, lot 32, décalage 7 — comparaison au bit près, pas à une tolérance
✅ scalaire   relu: 0 désaccord(s) (pire écart 0)   raw: 0 désaccord(s) (pire écart 0)
✅ SIMD       relu: 0 désaccord(s) (pire écart 0)   raw: 0 désaccord(s) (pire écart 0)
```

Repère natif produit par le noyau **SSE2** (dispatché sur cette machine).
**Zéro désaccord**, sur les deux fonctions, sur les cinq formes, sur les deux
builds Wasm (scalaire et SIMD128 `i32x4.dot_i16x8_s`) — la revendication du
fichier tient à l'épreuve, pas seulement sur le papier.

Le chemin float32 n'a pas régressé : `make wasm-parity` rend toujours
0,000e+0 (scalaire) et 6,407e-7 (SIMD), identique au repère du 2026-08-27.

## Taille de l'artefact

`build/wasm/gammonnet.wasm` : 84 950 octets (scalaire) ; `gammonnet-simd.wasm` :
93 825 octets (SIMD) — le noyau int8 inclus, avec le reste de T78 (bearoff
distillé) et T81 (tête de videau) déjà présents depuis leur fusion sur
`main`. Loin sous les 300 Kio de l'acceptation de T73 ; un delta isolé
attribuable au seul `gn_gemm_int8.c` n'a pas été mesuré séparément (l'essai a
échoué : retirer le fichier des sources sans retirer ses exports casse le
lien — pas refait, le chiffre n'est pas requis par le critère).

## Ce que ceci ne couvre pas

**Aucun réseau n'est réellement quantifié et évalué en int8 dans le module
navigateur.** Ce qui est prouvé ici est que le NOYAU, isolé, calcule la même
chose des deux côtés — pas qu'une inférence de bout en bout en int8 existe.
Câbler un réseau QAT exporté vers ce chemin (poids int8, échelles par couche,
`gnw_evaluate_batch` équivalent en int8) reste une fiche à part, plus grande,
et c'est elle qui bloque une comparaison réellement à niveau du QAT contre la
quantification post-entraînement (voir
`docs/mesures/2026-08-31-T73-qat-echelle-diagnostic.md`).

Le test décisif de l'anomalie du lot (build natif dégradé SSE2, gain de lot
comparé à un build FMA/VNNI) et le micro-banc sur les sept plateformes
physiques restent hors de portée de cette machine.

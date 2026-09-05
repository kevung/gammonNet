# T91 — Le noyau écrit à la main devient l'artefact WebAssembly, et `-fassociative-math` en sort

**Date** : 2026-09-03 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3,
8 cœurs physiques / 16 fils, AVX2), 14,4 Gio, Linux 7.1.9-arch1-2 · **Chaîne** :
gcc 16.2.1, emcc 6.0.9-git, node 26.8.1, Chromium 152.0.7977.64, Firefox 154.0.1 ·
**Branche** : `perf/wasm-noyau-intrinseques` · **Instruments** :
`node bench/browser_kernel.mjs`, `make bench-width-wasm-fp`, `make wasm-parity`,
`node wasm/harness.mjs --mode bench`

> **Charge de la machine.** Un autre chantier tournait sur la même machine. Toutes les
> mesures navigateur retenues ont été prises entre **2,0 et 3,1** de charge moyenne à une
> minute, relevée avant et après chaque balayage. Les valeurs absolues en portent la trace ;
> les **rapports** sont ce sur quoi ce document conclut, et ils reproduisent ceux de T84 à
> deux points près là où les deux se recouvrent (Firefox `autofp` largeur 32 : 1,1547 s ici,
> 1,1461 s en T84 ; `intrin` largeur 32 : 0,6963 s ici, 0,6897 s en T84).

## La question, et ce que T84 avait laissé ouvert

T84 a livré `src/gn_kernel_f32.h` en **opt-in** et n'a pas changé le défaut, délibérément :
en natif les intrinsèques demandent `-march=native`, donc un binaire qui ne démarre plus sur
une machine sans AVX2, donc une répartition à l'exécution — un autre chantier. Mais elle a
noté que **la cible WebAssembly n'a pas cette contrainte** : `gammonnet-simd.wasm` assume
déjà SIMD128. Elle a conclu par « le chantier le plus rentable que cette fiche laisse
derrière elle », bloqué sur T86 qui modifiait `wasm/`. T86 est fusionnée.

Trois choses à trancher, et la troisième n'était pas dans l'énoncé :

1. le noyau écrit à la main comme **défaut** de la cible WebAssembly ;
2. la **largeur** de lot de cette cible, que T84 avait close pour le natif seul ;
3. `-fassociative-math`, que T84 mesurait à **−2,8×** sur le chemin par lot alors que T21
   l'avait adopté pour **+3,9×** sur la passe avant.

## Ce qui est livré

| | avant | après |
|---|---|---|
| noyau | auto-vectorisé | **`GN_KERNEL_INTRINSICS`** (simd128, 2 lignes × 4 vecteurs) |
| largeur (`GN_EVAL_BATCH`) | 32 | **16** |
| arithmétique | `-fassociative-math` … | **rien** (+ `-ffp-contract=off`) |
| `gnw_evaluate_batch` | boucle sur `gn_evaluate_features` | **`gn_evaluate_features_batch`** |

Le **natif reste tel quel** : `KERNEL_INTRINSICS` y demeure un opt-in, `GN_EVAL_BATCH` y
reste 32, et `NATIVE_FP` un opt-in. Le binaire livré cible le x86-64 de base ; activer les
intrinsèques sans répartition à l'exécution produirait un binaire qui ne démarre plus sur une
machine sans AVX2. C'est T50, pas un jeu de drapeaux, et T84 le disait déjà.

## Le bit à bit, AVANT tout chronométrage

`bench/bench_kernel.c` compare `gn_evaluate_batch` à `gn_evaluate`, position par position,
avant de mesurer quoi que ce soit. Sur les quatre variantes chronométrées ci-dessous, dans
les deux navigateurs :

| variante | max\|Δ\| |
|---|---|
| `autofp` (l'artefact d'avant), largeur 16 | 2,086e-07 |
| `autofp` (l'artefact d'avant), largeur 32 | 1,788e-07 |
| **`intrin` (l'artefact d'après), largeur 16** | **0,000e+00** |
| **`intrin` (l'artefact d'après), largeur 32** | **0,000e+00** |

**Et le drapeau qui changeait des bits, c'est `-fassociative-math`, pas les intrinsèques.**
C'est le point que T84 n'avait pas isolé : dans `autofp`, ce qui bouge n'est pas le noyau —
c'est la **référence**. `gn_evaluate` passe par `nn_forward_prob5` (`nn_eval.c`), dont la
réassociation vectorise la somme ; le noyau par lot, lui, parallélise sur `n` et laisse
l'ordre de sommation intact. Les deux chemins du **même artefact** ne répondaient donc pas la
même chose à 2e-07 près.

## Le gain, dans un vrai navigateur

`node bench/browser_kernel.mjs`, profil neuf, serveur statique, aucun protocole
d'automatisation. Médiane de 3 passes, 3 décisions 2-ply `(0,1,3)` `k=12` par passe.
Fichiers : `docs/mesures/t91-navigateur-chromium.json`, `…-firefox.json`.

### Chromium 152

| largeur | noyau | éval/s | s/décision | gain |
|---|---|---|---|---|
| **32** | **`autofp` — l'artefact d'avant** | **9 315** | **1,4980** | 1,00× |
| 16 | `autofp` | 12 038 | 1,2027 | 1,25× |
| 32 | `intrin` | 42 905 | 0,3823 | 3,92× |
| **16** | **`intrin` — l'artefact d'après** | **48 762** | **0,3343** | **4,48×** |

### Firefox 154

| largeur | noyau | éval/s | s/décision | gain |
|---|---|---|---|---|
| **32** | **`autofp` — l'artefact d'avant** | **10 309** | **1,1547** | 1,00× |
| 16 | `autofp` | 8 214 | 1,3287 | 0,87× |
| 32 | `intrin` | 21 186 | 0,6963 | 1,66× |
| **16** | **`intrin` — l'artefact d'après** | **17 861** | **0,6860** | **1,68×** |

**Seuil d'abandon de la fiche : ×1,5.** Chromium rend **×4,48**, Firefox **×1,68**. Les deux
passent, et il fallait bien les deux : le même fichier vaut un facteur 2,7 d'écart entre les
deux moteurs, exactement ce que T84 avait montré et qui interdit de conclure sur un seul.

## Le verdict de largeur, pour la cible WebAssembly seule

À noyau écrit à la main, passer de la largeur 32 à 16 :

| | Chromium | Firefox | natif (T84) |
|---|---|---|---|
| s/décision, largeur 32 | 0,3823 | 0,6963 | 0,2423 |
| s/décision, largeur 16 | **0,3343** | **0,6860** | 0,2257 |
| écart | **−12,6 %** | −1,5 % | −6,9 % |

**La largeur 16 est retenue pour la cible WebAssembly**, et pour une raison qui se lit dans
le noyau lui-même : SIMD128 n'a que **quatre** voies. À largeur 32, `GN_KERNEL_VECS` vaut 8,
la tuile dégénère en **1 ligne × 8 vecteurs** et il ne reste qu'une chaîne d'accumulation par
ligne de sortie. À largeur 16 elle vaut **2 lignes × 4 vecteurs** : deux chaînes
indépendantes, plus la colonne lue une fois pour deux lignes — c'est-à-dire tout l'objet du
noyau. Le banc l'imprime : `noyau simd128 intrinsèques, 2 lignes x 4 vecteurs de 4`.

Chromium gagne 12,6 %, Firefox 1,5 %, et **aucun des deux ne perd**. Le natif, où huit voies
AVX2 donnent déjà 4 lignes × 1 vecteur à largeur 32, garde sa largeur 32 : la question y
reste close comme T84 l'a close.

**Le REGROUPEMENT des 21 lancers n'est pas touché et n'a jamais été en cause.** Un lot de 16
se remplit à **96,5 %** — mesuré par `make bench-width-fill` en T84 — *parce qu'il est
groupé* ; dégroupé, il retomberait vers les 84,3 % que le portage Go obtient. Le verdict de
T84 (« le regroupement est CONSERVÉ ») tient intégralement ; c'est la largeur, et elle seule,
qui se règle par cible.

## `-fassociative-math` : ce qu'il achetait, et ce qu'il coûtait

T21 l'a adopté en août 2026 pour une raison exacte et toujours vraie : `forward_raw` de
`nn_eval.c` accumule dans **une seule variable**, donc le compilateur n'a le droit ni de
dérouler ni de vectoriser cette boucle tant qu'on ne l'autorise pas à réassocier. Depuis T35,
une **décision** ne passe plus par là : elle passe par le noyau par lot de
`gn_infer_reference.c`, où la réassociation ne libère rien et gêne l'auto-vectorisation.
D'où le paradoxe que T84 a mesuré : le drapeau qui aidait hier nuisait aujourd'hui.

**Mais il restait un chemin qui le réclamait.** `gnw_evaluate_batch` — le point d'entrée qu'on
appelle avec des centaines de vecteurs de caractéristiques en une traversée — **bouclait sur le
chemin scalaire**, une position à la fois. Retirer le drapeau sans rien
faire d'autre l'effondrait :

| `gnw_evaluate_batch`, Chromium, 2 000 vecteurs | build SIMD | build scalaire |
|---|---|---|
| artefact d'avant (`-fassociative-math`, boucle scalaire) | 8 776 éval/s | 2 366 éval/s |
| drapeau retiré, boucle scalaire conservée | **2 354 éval/s** | — |
| **drapeau retiré, `gn_evaluate_features_batch`** | **41 580 éval/s** | **7 984 éval/s** |

Le remède n'est donc pas un arbitrage entre les deux chiffres de T21 et T84 : c'est de faire
entrer ce point d'entrée par la même porte que la recherche. `gn_evaluate_features_batch`
(nouveau, `src/gn_infer_reference.c`) partage `forward_feature_rows` avec
`gn_evaluate_batch`, si bien que les deux portes ne peuvent pas dériver vers deux ordres de
sommation différents. Les tronçons qui ne remplissent pas `GN_EVAL_BATCH` voies passent par
la porte scalaire plutôt que de payer un lot presque vide — ce qui n'est permis que **parce
que** les deux sont bit à bit.

Résultat : **×4,74 sur le chemin d'`analyze()`** en plus du ×4,48 sur celui des décisions, et
plus rien ne réclame `-fassociative-math` dans cet artefact. Il reste défini et
documenté ; `make wasm WASM_EXTRA="$(FP_RELAXED)"` le rend, et `make bench-width-wasm-fp`
construit les variantes qui le mesurent.

## La parité — elle s'améliore, et elle tombe à zéro

`make wasm-parity`, 2 000 positions × 5 sorties, repère produit par le natif :

| | scalaire | SIMD |
|---|---|---|
| repère du dépôt, avant ce chantier | 0,000e+00 | **6,407e-07** |
| reconstruit ici, drapeaux d'avant (contrôle) | 0,000e+00 | **6,407e-07** |
| **après** | **0,000e+00** | **0,000e+00** |

Le contrôle importe : il dit que la valeur d'avant est bien reproduite sur cette machine, donc
que le zéro d'après est un changement et non une différence d'environnement.

**Le sens du changement est celui qu'on attendait, et il va au bout.** L'artefact
WebAssembly est désormais **bit à bit avec le moteur natif**, ce que le dépôt n'avait plus
depuis T21. La tolérance de 1e-6 de T20 n'est plus consommée du tout.

`make wasm-parity-int8` reste au bit près sur les deux builds (chemin int8, inchangé).

## La suite

- `make wasm-api` : `api_invariants`, `worker_invariants`, `pool_invariants` — verts.
- `make wasm-codec` : 2 050 positions du corpus T12, égalité **exacte**, sur les deux builds.
- `make wasm-parity-int8` : au bit près, sur les deux builds.
- `pytest tests/` : **1 795 passés, 45 ignorés**, aucun échec (dont les 9 du corpus de
  non-régression T12, `tests/test_regression.py`, sorties figées au bit près).
- `make test-tile` : le garde-fou de T90, sous ASan, aux deux volets.

## Taille de l'artefact

| | avant | après |
|---|---|---|
| `gammonnet.wasm` (scalaire) | 97 734 o | **97 157 o** (−0,6 %) |
| `gammonnet-simd.wasm` | 109 240 o | **100 992 o** (−7,6 %) |

Le build SIMD **rétrécit** de 8 Ko : l'auto-vectorisation sous `-fassociative-math` déroulait
la boucle chaude, le noyau écrit à la main ne la déroule pas. Qui épingle une somme de
contrôle doit la reprendre ; les deux fichiers changent.

## Reproduire

```bash
make wasm                                        # les nouveaux défauts
make wasm-parity                                 # 0,000e+00 sur les deux builds
node wasm/harness.mjs --browser chromium --mode bench --build simd --reps 7

make bench-width-wasm-fp                         # les 5 variantes, largeurs 16 et 32
node bench/browser_kernel.mjs --browser chromium --widths 16,32 \
     --kernels autofp,intrin --reps 3 --decisions 3
node bench/browser_kernel.mjs --browser firefox  --widths 16,32 \
     --kernels autofp,intrin --reps 3 --decisions 3

make wasm WASM_KERNEL= WASM_BATCH= \
     WASM_EXTRA="-fassociative-math -fno-signed-zeros -fno-trapping-math -fno-math-errno"
                                                 # l'artefact d'avant, pour comparer
```

## Ce que cette version impose à qui épingle l'artefact

1. **Une montée d'épingle.** Les deux `.wasm` changent de taille et de somme de contrôle ;
   qui les épingle reprend les deux.
2. **Rien à changer dans le code appelant.** L'API, les exports et le protocole de worker
   sont identiques ; le chemin par lot et `rankPlays` deviennent simplement plus rapides.
3. **Les réponses peuvent bouger dans la dernière décimale — dans le bon sens.** Le module
   est maintenant bit à bit avec le natif là où il s'en écartait de 6,4e-07. Tout repère figé
   qui aurait été produit par l'ancien module est à régénérer.
4. **Les mesures d'ordonnancement de T87 sont à relire, pas à refaire.** Une décision passe de
   ~1,4 s à ~0,33 s dans Chromium : les 2,5 % d'oisiveté du pool portent sur un mural quatre
   fois plus court, donc la conclusion (« l'ordonnancement est sous le seuil par
   construction ») se renforce. En revanche le coût de `postMessage` d'`analyze()`, lui, n'a
   pas bougé alors que le calcul a été divisé par 4,7 : **la frontière de la règle « le nombre
   de tâches paie quand une tâche coûte cher à CALCULER et rien à TRANSMETTRE » s'est déplacée
   contre le découpage**, et le défaut `tasksPerWorker = 1` est plus justifié qu'avant.

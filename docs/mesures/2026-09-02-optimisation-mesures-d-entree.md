# Les mesures d'entrée de la campagne d'optimisation — et deux pièges de banc

**Date** : 2026-09-02 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3,
**8 cœurs physiques / 16 fils**, AVX2), 14,4 Gio, Linux 7.1.9-arch1-2 · **Chaîne** : gcc
16.2.1, emcc 6.0.9-git, Python 3.13.15, torch 2.13.0+cpu ·
**Branche** : `perf/plan-optimisation-navigateur`

> **Pourquoi ce relevé.** Le registre d'optimisation date du 2026-08-26 et ses chiffres
> viennent de deux autres machines. `docs/etudes/2026-09-02-retours-du-portage-go.md` déplace
> quatre de ses conclusions, mais avec des mesures prises en Go. La règle 3 de `CLAUDE.md`
> interdit de transposer l'une ou l'autre sans mesurer. Voici les chiffres d'ici, aujourd'hui.
>
> Le plan qu'ils servent est `docs/etudes/2026-09-02-optimiser-pour-le-navigateur.md`
> (fiches T84–T90).

## Conditions — la machine n'était PAS au repos, et il faut le dire

Un autre chantier faisait tourner `tools/serve.py` (60–70 % d'un cœur) pendant une partie de
la séance, et un navigateur était ouvert. La charge moyenne a varié entre **0,45 et 3,12**.

**Le plancher de bruit, mesuré et non supposé** :

| | |
|---|---|
| six exécutions consécutives du **même** binaire, `k=12` | 0,3846 → 0,4177 s/décision — **±8 %** |
| la **même** configuration, à trois moments de la séance | 0,3610 / 0,4115 / 0,4604 s — **±22 %** |

**Conséquence, à appliquer à tout ce qui suit** : les **rapports mesurés dos à dos** (A/B dans
la même minute) sont bons ; les **valeurs absolues** portent ±20 %. Aucune conclusion de ce
document ne repose sur un écart inférieur à 10 % entre deux relevés non consécutifs.

---

## 0. Deux pièges de banc, trouvés en prenant ces mesures

**`make bench-batch` n'existait pas.** `bench/bench_batch.c` est dans l'arbre depuis le
2026-08-03 ; aucune règle du `Makefile` ne le construisait. Il se compilait donc à la main,
au hasard des drapeaux. La règle est ajoutée par ce relevé, à `-O3`, et le commentaire qui
l'accompagne dit ce que ce banc ne mesure pas.

**Et il ne mesure pas le noyau livré.** Deux différences, toutes deux dans le sens qui
sous-estime :

| | `bench/bench_batch.c` | `src/gn_infer_reference.c` (livré) |
|---|---|---|
| largeur du lot | **variable d'exécution** | constante de compilation `GN_EVAL_BATCH` |
| sparsité de la couche 1 | absente | présente |
| drapeaux | ceux de la ligne de compilation du banc | `BATCH_CFLAGS`, c'est-à-dire `-O3` |

Le troisième point à lui seul vaut **48 %** :

| lot | `-O2` éval/s | `-O3` éval/s |
|---|---|---|
| 1 | 734,9 | 1 042,5 |
| 2 | 1 429,2 | 1 845,2 |
| 4 | 2 834,1 | 4 695,6 |
| 8 | 5 633,0 | 9 129,1 |
| 16 | 10 862,4 | 17 213,3 |
| **32** | **19 297,5** | **28 648,4** |

Bit à bit contre le chemin scalaire à **toutes** les largeurs (`max|Δ| = 0,000e+00`). Une
troisième exécution, plus tard dans la séance, a lu 25 301,9 éval/s à 32 : ±13 %, cohérent
avec le plancher de bruit ci-dessus.

**Ce que la colonne `-O3` dit quand même** : le gain de lot **ne sature pas à 32** (×27,5
pour 32 voies). Ce que ce banc **ne peut pas** dire, c'est ce que vaudrait une largeur 8
*compilée en constante* — sa largeur est une variable, donc sa courbe n'est pas celle du
noyau. Le piège est le même que celui du portage Go, dans l'autre sens.

---

## 1. Le chemin scalaire, et ce que la réassociation vaut vraiment

`make bench-infer`, 2 000 positions du repère, médiane de 11 :

| build | éval/s | ms/éval |
|---|---|---|
| défaut | **3 168,2** | 0,3156 |
| `NATIVE_FP=1` | **13 408,5** | 0,0746 |

**×4,23**, et T21 publiait 3 218 / 13 143 sur une autre machine : ce poste se reproduit à 2 %
près. Le commentaire du `Makefile` est confirmé sans réserve.

**Mais il ne se transporte PAS à une décision.** Même build, même séance :

| | défaut | `NATIVE_FP=1` |
|---|---|---|
| 2-ply sans élagage | 1,2087 | 1,2188 |
| 2-ply `k=12` | 0,3610 | 0,3388 |
| 2-ply `k=3` | 0,1542 | 0,1507 |

**0 à 6 %, dans le bruit.** La réassociation achète ×4,23 sur un chemin que la recherche
n'emprunte plus : depuis le branchement du noyau groupé (T35), une décision passe par
`gn_evaluate_batch`, déjà vectorisé sur la dimension du lot **sans** réassociation. Le
sous-ensemble de drapeaux reste utile au build WebAssembly, qui l'utilise ; il n'est pas un
levier natif.

## 2. L'encodage

`make bench-encoding`, 20 000 positions de vraie partie, meilleur de 5 :

| | ms |
|---|---|
| `gn_encode` seul | 0,00030 |
| grand : caractéristiques → sorties | 0,30814 |
| grand : position → sorties (recherche) | 0,31241 — encodage **1,4 %** |
| petit : caractéristiques → sorties | 0,00327 |
| petit : position → sorties (recherche) | 0,00352 — encodage **7,2 %** |

## 3. Une décision, et le remplissage des lots

`make bench-decision`, 20 décisions, 2-ply filtre `(0,1,3)`, build par défaut :

| | s/décision | éval. grand | éval. petit |
|---|---|---|---|
| sans élagage | 1,2087 | 33 799 | — |
| `k=12` | 0,3610 | 12 080 | 31 138 |
| `k=8` | 0,3077 | 8 643 | 32 468 |
| `k=5` | 0,2267 | 6 055 | 32 180 |
| `k=3` | 0,1542 | 3 884 | 40 107 |

`-DGN_BATCH_FILL_STATS`, mêmes 20 décisions :

| | grand : appels / remplissage / voies calculées | petit : appels / remplissage / voies calculées |
|---|---|---|
| sans élagage | 35 201 / **60,8 %** / 1 126 432 | — |
| `k=12` | 8 147 / **93,6 %** / 260 704 | 26 605 / **74,4 %** / 851 360 |
| `k=3` | 2 663 / 91,7 % / 85 216 | 38 279 / **65,8 %** / 1 224 928 |

**Deux faits, et ils réorientent le débat sur la largeur de lot.**

1. **Le regroupement des 21 lancers fait son travail** : le grand réseau remplit **93,6 %**
   de ses voies à `k=12`. Le portage Go mesure 84,3 % à largeur 8 *sans* regrouper — donc
   moins bien. La largeur 32 **avec** regroupement bat la largeur 8 **sans**, sur ce critère.
2. **Le petit réseau consomme la majorité des voies calculées** : 851 360 contre 260 704 à
   `k=12` — **76,6 %** ; 1 224 928 contre 85 216 à `k=3` — **93,5 %**. Et c'est lui dont le
   remplissage est mauvais (74,4 %, 65,8 %). Le registre a déjà mesuré que fusionner ses lots
   ne rend que 0,7–0,9 % : ce n'est pas le remplissage qui compte pour lui, c'est que chaque
   voie y est bon marché (25 Kio de poids contre 2,0 Mio).

## 4. La sparsité de la couche 1 — en C, elle paie ; le constat 2 du portage Go est un artefact de Go

Elle est **déjà livrée** (`gn_infer_reference.c:360-406`, commit `bb904c5`, 2026-08-26) mais
n'avait pas de mesure A/B publiée. A/B dos à dos, même build, `nonzero` remplacé par `NULL` :

| | avec sparsité | sans | gain |
|---|---|---|---|
| `k=12` | 0,4589 / 0,4601 / 0,4604 | 0,5326 / 0,5317 / 0,5320 | **×1,161** |
| `k=3` | 0,2014 / 0,2017 / 0,2033 | 0,2336 / 0,2367 / 0,2334 | **×1,160** |

**16 %, reproductible à 0,3 % près.** Le portage Go mesure **6 %** pour la même transformation
et l'impute au coût de sa compaction (~3,3 cycles par flottant déplacé). L'hypothèse qu'il
formule — *« en C, avec un memcpy par colonne, ce coût est probablement plus faible »* — est
**confirmée** : c'est bien un artefact du langage.

**Ce qui reste non mesuré** : la part qui revient au **petit** réseau, où le registre attend
78 % parce que sa couche 1 pèse 97,5 % de ses MACs. Le chiffre de 16 % ci-dessus est celui des
deux réseaux ensemble.

## 5. Le videau au score coûte 2 µs par nœud — et la recherche en fait un par nœud

Nouvel instrument : `bench/bench_cube.c`, 2 000 distributions **réelles** (le repère évalué par
le réseau), médiane de 11 passes, efficacités mesurées par état de possession.

| cas | `gn_cube_decide` ns | `gn_cube_value` ns |
|---|---|---|
| money, centré | 22,0 | **14,0** |
| money, possédé | 22,0 | 13,9 |
| money, adverse | 21,9 | 14,4 |
| 2-away/2-away, centré | 342,0 | 246,0 |
| **5-away/5-away, centré** | **2 569,8** | **2 028,7** |
| 5-away/5-away, possédé | 2 600,4 | 2 008,1 |

`gn_cube_value` — et non `gn_cube_decide` — est ce que la recherche appelle, **une fois par
nœud évalué** (`gn_search.c:289`, atteint depuis `leaf_value` ligne 309 et depuis
`shallow_fill` ligne 511).

**Ce que cela pèse.** À `k=12`, une décision évalue 12 080 + 31 138 = **43 218 nœuds**. Au
score :

```
43 218 × 2 029 ns ≈ 88 ms
```

contre une décision cubeless mesurée à 0,36–0,46 s : **de l'ordre de 20 à 25 % d'une décision
au score**. En money, le même calcul donne 0,6 ms — **rien**.

Le portage Go mesure 2 106 ns pour la même opération : l'ordre de grandeur se transporte, et
sa décomposition (`level_solve` 83 %, consultations de la table 11 %) porte sur la structure
de `gn_cube.c`, donc elle vaut ici.

> **Réserve honnête.** Les 88 ms sont un **produit de deux mesures**, pas un chronométrage.
> `bench_decision` ne sait pas activer `use_cube`, et le nombre de nœuds qui portent réellement
> une valuation de videau n'a pas été compté. Le chiffre est à confirmer par un banc `use_cube`
> avant qu'une fiche s'appuie dessus.

## 6. Trois postes que le portage Go a livrés et qui ne valent rien ici — mesuré

**Les tampons alloués par appel.** Compteur posé sur `malloc` dans `gn_search.c` seul
(`-Dmalloc=…`) :

| | paires malloc/free par décision | octets par décision |
|---|---|---|
| sans élagage | 1 477 | 130,6 Mio |
| `k=12` | **1 678** | **132,6 Mio** |
| `k=3` | 1 733 | 135,5 Mio |

Le profil semble accablant. Il ne l'est pas : rejoué seul (mêmes tailles, 90 Kio et 147 Kio
alternés, premier contact des pages compris), il coûte **0,027 ms** — soit **0,007 %** d'une
décision. glibc recycle un bloc chaud ; il n'y a pas de ramasse-miettes à nourrir. Le poste est
réel en Go et **vide en C**.

**Le tri.** 2 087 `qsort` par décision à `k=12`, 43 926 éléments au total, 21 en moyenne par
tri, sur des `GnCandidate` de **72 octets** avec comparateur indirect. Rejoué seul :

| | ms par décision |
|---|---|
| `qsort` + comparateur indirect | 0,80 – 0,90 |
| clés extraites + tri par insertion | 0,16 – 0,18 |

**0,65 ms de gain, soit 0,16 % d'une décision.** Sous le plancher de bruit.

> **Mais il y a autre chose, et ce n'est pas de la vitesse.** `compare_candidates`
> (`gn_search.c:366`) ne compare **que l'équité**, et `qsort` n'est pas stable. L'ordre de deux
> candidats de même équité dépend donc de l'implémentation de `qsort` — celle de la glibc en
> natif, celle de la libc d'Emscripten en WebAssembly. Le harnais de parité compare des
> **équités** à 1e-6 : une permutation d'ex æquo lui est **invisible**, et elle change le coup
> annoncé. Voir T88.

**La revalidation à l'encodage.** `gn_encode` appelle `gn_position_is_valid` à chaque appel,
y compris sur des positions que la recherche vient de produire et qui sont légales par
construction :

| | ns/appel |
|---|---|
| `gn_position_is_valid` | 44,4 |
| `gn_encode` (validation comprise) | 91,5 |

**La validation est 48,5 % de l'encodage.** À `k=12`, 43 218 encodages ⇒ ~1,9 ms par décision,
**0,5 %**. Mesurable, pas rentable seul.

**Et un quatrième, sans objet** : la déduplication des coups. Le moteur vendoré déduplique déjà
**par position résultante** (`gn_rules_reference.c:220`). Rien à reprendre.

## 7. Le parallélisme est borné par les cœurs physiques — confirmé en C

`bench_decision` `k=12`, 10 décisions par processus, N processus indépendants lancés ensemble :

| processus | déc/s agrégées | accélération |
|---|---|---|
| 1 | 1,799 | ×1,00 |
| 2 | 3,637 | ×2,02 |
| 4 | 5,757 | ×3,20 |
| **8** | **7,616** | **×4,23** |
| 12 | 8,920 | ×4,96 |
| 16 | 9,035 | ×5,02 |

**×4,23 sur 8 cœurs physiques**, et le multithreading simultané n'ajoute que **19 %** en
doublant les processus. Le portage Go mesure ×3,98 sur la même machine, en Go : le constat 5 de
son étude se transporte tel quel. La cause qu'il nomme — les mêmes ~2 Mio de poids traversant
un L3 partagé sur une puce mobile 15-28 W — est cohérente avec le décrochage dès 4 processus.

**Conséquence pour un pool de Web Workers** : le nombre utile de workers est borné par les
cœurs **physiques** et par la bande passante, pas par `navigator.hardwareConcurrency`, que
`wasm/workers.html` et `wasm/decision.html` sont les seuls à lire aujourd'hui. À contre-mesurer
sur une machine de bureau à plus de cœurs — T21b avait obtenu ×6,2 à 8 workers sur une machine
à 28 cœurs, ce qui ne contredit rien.

## 8. La largeur de lot — un balayage NON concluant, et il faut le dire

`GN_EVAL_BATCH` recompilé, une seule exécution par largeur, `k=12`, machine en dérive :

| largeur | s/décision |
|---|---|
| 4 | 0,9899 |
| 8 | 0,5898 |
| 16 | **0,4074** |
| 24 | 0,4425 |
| 32 | 0,4381 |
| 48 | 0,4527 |

16 sort devant 32 de 7 %. **Ce n'est pas une conclusion** : la même configuration a lu entre
0,3610 et 0,4604 s dans la séance, un seul relevé par largeur, et T3A avait mesuré l'inverse
(16 nettement pire) — mais sans élagage, ce qui change la distribution des tailles de fratrie.
À refaire au repos, plusieurs relevés, avec `-fopt-info-vec` relu à chaque largeur. Voir T84.

Ce que le balayage confirme sans ambiguïté : **l'effondrement à 4 et 8** (×2,3 et ×1,4) est
bien la falaise de vectorisation de `gcc` que T3A avait nommée, pas une propriété du matériel.

## 9. L'artefact distribué, en octets

| pièce | octets |
|---|---|
| `gammonnet.wasm` (scalaire) | 84 004 |
| `gammonnet-simd.wasm` | **92 483** |
| `gammonnet.mjs` / `gammonnet-simd.mjs` | 64 899 / 64 909 |
| grand réseau float16 (`.bin16`) | **1 059 640** |
| réseau d'élagage float16 | 13 036 |

**Sans `SharedArrayBuffer`, chaque worker recharge sa propre copie des 1,07 Mo de poids**
(`wasm/worker.mjs` le dit et l'assume). Huit workers ⇒ ~8,6 Mo de poids résidents, sur une
machine dont la mesure du §7 dit que huit fils ne rendent que ×4,2.

---

## Reproduire

```bash
# le socle
ln -s <dépôt>/vendor vendor && cp <dépôt>/models/*.bin models/
make build && make env

make bench-infer                       # §1, défaut
make clean && make bench-infer NATIVE_FP=1
make bench-encoding                    # §2
make bench-batch                       # §0 — règle ajoutée par ce relevé
make bench-decision                    # §3 — puis à la main avec prune et k
build/bench_decision models/cubeless_prob5_512_512_256_128.bin 20 models/prune_32.bin 12

# §3, remplissage
make clean && make build CFLAGS="-O2 -std=c11 -Wall -Wextra -fPIC -DGN_BATCH_FILL_STATS"

make bench-cube                        # §5 — l'instrument et sa règle sont neufs

# §7, le parallélisme
for N in 1 2 4 8 12 16; do ... done      # N copies concurrentes, temps mural
```

Le compteur de `malloc` du §6 se pose sans toucher au source :
`cc … -Dmalloc=gn_bench_malloc -Dfree=gn_bench_free -c src/gn_search.c`.

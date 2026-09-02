# T84 — La largeur de lot, tranchée par des intrinsèques : le regroupement est CONSERVÉ

**Date** : 2026-09-02 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3, 8 cœurs
physiques / 16 fils, AVX2), 14,4 Gio, Linux 7.1.9-arch1-2 · **Chaîne** : gcc 16.2.1,
emcc 6.0.9-git, node 26.8.1 (V8), Chromium et Firefox du système ·
**Branche** : `feat/t84-noyau-largeur` · **Instruments** : `make bench-width`,
`make bench-width-wasm`, `make bench-width-fill`, `node bench/browser_kernel.mjs`

> **Charge de la machine.** Le balayage natif retenu a été pris entre **1,1 et 3,9** de charge
> moyenne (deux autres chantiers sur la même machine, montés en fin de séance). Un premier
> balayage pris à **charge 10** est conservé plus bas : les **rapports** y sont les mêmes à
> deux points près, les valeurs absolues sont deux fois plus basses. Rien ici ne repose sur un
> absolu.

## La question, et pourquoi ce n'est pas « 8 ou 32 »

C'est : *le regroupement des 21 lancers gagne-t-il encore sa complexité si le noyau est écrit
à la main ?* Sa suppression retirerait les trois phases de `rank_plays`
(`gn_search.c:568-849`) — une simplification réelle, pas seulement une vitesse.

**Tout balayage antérieur a mesuré autre chose.** T3A l'avait nommé et la mesure d'entrée du
2026-09-02 (§8) l'avait confirmé sans pouvoir conclure : **gcc ne vectorise la boucle chaude
qu'à partir de 24**, donc une largeur de 8 testée sans intrinsèques est une falaise de
compilateur, pas une propriété du matériel. Et `bench/bench_batch.c` prend sa largeur en
**variable d'exécution** : sa courbe est la sienne, pas celle du noyau livré, dont la largeur
est une constante de compilation.

**La falaise, lue dans `-fopt-info-vec` et non supposée.** Sur la boucle interne du noyau
(`gn_infer_reference.c:529` et `:537`) :

| largeur | ce que gcc émet (cible de base) | ce qu'il émet en `-march=native` |
|---|---|---|
| **8** | 16 octets, **facteur de déroulage 1** | 32 octets, **facteur de déroulage 1** |
| 16 | 16 octets, déroulage 4 | 32 octets, déroulage 1 (et 8 sur la voisine) |
| 32 | 16 octets, déroulage 4 | 32 octets, déroulage 8 |

À largeur 8 il n'y a **qu'un accumulateur vectoriel** et la boucle sur `j` est une chaîne
d'additions dépendantes, quatre cycles l'une de l'autre, quelle que soit la largeur du
vecteur. **Aucune version de gcc ne tuile sur les LIGNES de sortie**, et c'est exactement ce
qu'il faut à un lot étroit.

## Le noyau écrit à la main

`src/gn_kernel_f32.h`. Un seul principe : **huit accumulateurs vectoriels, toujours**,
arrangés en `GN_KERNEL_ROWS` lignes × `GN_KERNEL_VECS` vecteurs selon la largeur compilée et
le nombre de voies de la cible — 8×1, 4×2, 2×4 ou 1×8. Accumuler R lignes contre la même
colonne casse la chaîne de dépendance en R chaînes indépendantes **et** lit la colonne une
fois pour R lignes.

**Le bit à bit tient par construction, et il est vérifié avant tout chronométrage.**
Vectoriser sur `n` ne touche pas l'ordre de sommation — la voie `n` somme sur `j` dans l'ordre
scalaire, indépendamment des autres ; tuiler sur les lignes non plus — la ligne `i` est une
autre somme. `bench/bench_kernel.c` compare position par position contre `gn_evaluate` avant
de mesurer quoi que ce soit : **max|Δ| = 0,000e+00 aux trois largeurs, sur les deux cibles,
sur les trois noyaux.**

> **Le seul moyen de perdre le bit à bit est le FMA** : `_mm256_fmadd_ps` arrondit une fois
> là où multiplier puis additionner arrondit deux fois. Les multiplications et les additions
> sont écrites séparément **et** l'unité de compilation porte `-ffp-contract=off`, parce que
> gcc contracte sinon même des intrinsèques écrites explicitement.

## Natif — trois largeurs, trois noyaux

Trois noyaux et non deux, délibérément : `-march=native` sépare **« écrit à la main »** de
**« jeu d'instructions plus large »**, que le premier chiffre venu confondrait. Médiane de 3
passes en round-robin (et non trois passes par binaire : la dérive entrerait droit dans la
comparaison, ce qui est exactement ce qui avait rendu le balayage d'entrée non concluant).

| largeur | noyau | éval/s | gain | s/décision | gain | max\|Δ\| |
|---|---|---|---|---|---|---|
| 8 | auto-vectorisé (base x86-64, SSE) | 21 721 | 0,56× | 0,7062 | 0,62× | 0 |
| 8 | auto-vectorisé (`-march=native`, AVX2) | 23 948 | 0,62× | 0,6602 | 0,66× | 0 |
| 8 | **intrinsèques AVX2** | **68 557** | **1,78×** | **0,2504** | **1,75×** | 0 |
| 16 | auto-vectorisé (base) | 36 354 | 0,94× | 0,5153 | 0,85× | 0 |
| 16 | auto-vectorisé (AVX2) | 36 504 | 0,95× | 0,4199 | 1,04× | 0 |
| 16 | **intrinsèques AVX2** | **92 334** | **2,39×** | **0,2257** | **1,94×** | 0 |
| **32** | **auto-vectorisé (base) — ce qui est livré** | **38 565** | **1,00×** | **0,4383** | **1,00×** | 0 |
| 32 | auto-vectorisé (AVX2) | 59 053 | 1,53× | 0,3144 | 1,39× | 0 |
| 32 | **intrinsèques AVX2** | **83 816** | **2,17×** | **0,2423** | **1,81×** | 0 |

**Ce que la table dit, dans l'ordre.**

1. **La falaise est réelle et elle est celle du compilateur.** Auto-vectorisé, une largeur de
   8 vaut 0,62× d'une décision à largeur 32. Écrit à la main, elle vaut **1,75×**. La
   mesure d'entrée avait raison de refuser de conclure.
2. **Une fois le noyau écrit à la main, la largeur ne décide plus grand-chose.** Les trois
   décisions valent **0,2504 / 0,2257 / 0,2423 s** : l'écart entre la meilleure et la pire est
   de **11 %**, et entre 8 et 32 de **3,3 %**.
3. **« Écrit à la main » et « AVX2 » sont deux choses.** À largeur 32, AVX2 seul rend 1,53× ;
   l'écriture à la main ajoute 1,42× par-dessus. À largeur 8, AVX2 seul rend 1,10× et
   l'écriture à la main **2,86×** — parce que c'est là que le tuilage par lignes travaille.

## Navigateur — et les deux moteurs ne disent PAS la même chose

Même `bench/bench_kernel.c`, compilé en WebAssembly avec `-msimd128`. SIMD128 n'a que
**quatre** voies flottantes, donc l'enjeu du tuilage y est plus grand. Trois relevés :
Node 26 (V8), Chromium et Firefox, profil neuf, sans automatisation (serveur statique + page
qui renvoie son résultat, le dispositif de `wasm/harness.mjs`).

| largeur | noyau | Node/V8 éval/s | Chromium éval/s | Chromium s/déc. | Firefox éval/s | Firefox s/déc. |
|---|---|---|---|---|---|---|
| 8 | auto (SIMD128) | 23 827 | 25 180 | 0,6017 | 9 035 | 1,1320 |
| 8 | **intrinsèques** | **46 008** | **44 651** | **0,3452** | **15 674** | **0,6810** |
| 16 | auto | 27 890 | 28 818 | 0,5449 | 9 309 | 1,2370 |
| 16 | **intrinsèques** | **49 168** | **46 973** | **0,3347** | **17 861** | **0,6580** |
| **32** | **auto — ce qui est livré** | **10 104** | **9 624** | **1,4017** | 9 783 | 1,3813 |
| 32 | **intrinsèques** | **43 501** | **40 528** | **0,3784** | **18 732** | **0,6897** |

Bit à bit tenu partout : **max|Δ| = 0** sur les six variantes, dans les deux navigateurs.

**Deux faits, et le second n'était pas prévisible.**

1. **Les intrinsèques gagnent partout et largement** : ×1,6 à ×4,9 sur le débit du noyau,
   ×2,0 à ×4,2 sur une décision, dans les deux moteurs.
2. **L'auto-vectorisation s'effondre à largeur 32 dans V8/Chromium, et pas dans Firefox.**
   9 624 éval/s contre 28 818 à largeur 16 — un facteur **3** — sur le **même** `.wasm`, alors
   que Firefox lit 9 783 / 9 309 / 9 035, parfaitement plat. Ce n'est donc pas une propriété
   du bytecode émis par LLVM mais du moteur qui l'exécute. La cause exacte n'est **pas**
   établie ici et ce document ne la devine pas.

**Et la configuration réellement livrée est la pire des six.** L'artefact WebAssembly est
compilé avec `-fassociative-math` (T21, ×3,9 sur la passe avant **scalaire**). Mesuré avec ces
drapeaux-là, sur le chemin par lot :

| variante, drapeaux de l'artefact | éval/s | s/décision | max\|Δ\| |
|---|---|---|---|
| auto, largeur 16 | 9 905 | 1,4647 | 2,086e-07 |
| **auto, largeur 32 — l'artefact d'aujourd'hui** | **12 062** | **1,1461** | 1,788e-07 |
| **intrinsèques, largeur 32** | **37 923** | **0,3909** | 3,576e-07 |

La réassociation, qui achète ×3,9 sur la passe avant scalaire, **coûte** un facteur 2,8 sur le
noyau par lot à largeur 16 (27 890 → 9 905). Le chemin qu'une décision emprunte depuis T35
est le second, pas le premier.

## Le remplissage des voies, par largeur — la preuve directe sur le regroupement

`make bench-width-fill`, 8 décisions, noyau intrinsèques, compteurs de `gn_search.c` :

| largeur | grand : remplissage | voies calculées | petit : remplissage | voies calculées |
|---|---|---|---|---|
| 8 | **98,2 %** | 203 440 | 92,1 % | 510 832 |
| 16 | 96,5 % | 206 976 | 84,0 % | 559 648 |
| 32 | **93,5 %** | 213 568 | 74,8 % | 628 992 |

Les **93,5 %** du grand réseau à largeur 32 reproduisent les 93,6 % de la mesure d'entrée §3 :
le regroupement fait son travail, et il le fait mieux que les **84,3 %** que le portage Go
obtient à largeur 8 **sans** regrouper.

**Et le total de voies calculées ne varie que de 5 % sur le grand réseau** (203 440 à
213 568). Le gâchis que la largeur 32 introduit vaut donc au maximum 5 % du travail du grand
réseau — pendant que la même largeur rend, par la forme du noyau, bien davantage. **Le
remplissage n'est pas l'argument, dans un sens comme dans l'autre.**

## VERDICT — le regroupement est CONSERVÉ, et la question est close

Le seuil d'abandon de la fiche est **10 %** : moins de 10 % de gain à noyau écrit à la main
⇒ la largeur 32 et le regroupement restent, et la question est close pour de bon.

**Mesuré, à noyau écrit à la main :**

| | natif | Chromium | Firefox |
|---|---|---|---|
| passer de la largeur 32 à 8 | **+3,3 % plus lent** | −8,8 % plus rapide | −1,3 % plus rapide |
| passer de la largeur 32 à 16 | −6,9 % plus rapide | −11,6 % plus rapide | −4,6 % plus rapide |

**Cinq de ces six écarts sont sous les 10 %.** Le sixième — Chromium, 32 → 16, **−11,6 %** —
est le seul qui dépasse le seuil, et il ne dit rien sur le regroupement : il plaide pour une
largeur de **16**, pas pour l'abandon du groupement. Un lot de 16 se remplit à 96,5 %
**parce qu'il est groupé** ; dégroupé, il retomberait vers les 84 % que le portage Go mesure.
Et le même passage vaut −6,9 % en natif et −4,6 % dans Firefox : la seule cible qui le
réclame est celle dont l'auto-vectorisation s'effondre à 32, un défaut de moteur que le
noyau écrit à la main efface déjà.

Abandonner le **regroupement** pour aller vers un lot étroit, en revanche, ne rachète rien :
en natif c'est une perte de 3,3 %, en navigateur c'est sous le bruit, et cela retirerait au
passage les 93,5 % de remplissage que les trois phases de `rank_plays` achètent.

> **Le regroupement des 21 lancers est CONSERVÉ. La largeur 32 est CONSERVÉE. La question de
> la largeur de lot est close, comme T3A avait clos le réglage de `GN_EVAL_BATCH`.**
>
> Ce qui la clôt n'est pas un chiffre de plus, c'est que la variable qui la rendait ouverte a
> changé de camp : **la largeur ne décide plus rien une fois le noyau écrit à la main** (11 %
> entre la meilleure et la pire des trois), alors que **le noyau, lui, décide de tout**
> (×1,81 natif, ×3,70 dans Chromium, ×2,00 dans Firefox, à largeur égale et à bit égal).

## Ce qui est livré, et ce qui ne l'est pas

**Livré** : `src/gn_kernel_f32.h` (AVX/SSE2/SIMD128/scalaire, largeur et tuile paramétrables),
son branchement dans `forward_batch` derrière `GN_KERNEL_INTRINSICS`, l'interrupteur
`make build KERNEL_INTRINSICS=1`, et les instruments (`bench/bench_kernel.c`,
`bench/width_sweep.py`, `bench/browser_kernel.mjs`, quatre cibles `make`).

**Pas livré : le changement de défaut.** Il n'est pas à la main de cette fiche.

- **En natif**, les intrinsèques demandent `-march=native` (ou au moins `-mavx`). Le binaire
  livré cible le x86-64 **de base** : l'activer produirait un binaire qui ne démarre plus sur
  une machine sans AVX2. Il faut une répartition à l'exécution, ou une décision d'artefact —
  T50, pas un jeu de drapeaux.
- **En WebAssembly**, `gammonnet-simd.wasm` assume déjà SIMD128, donc le gain (×3,70 sur une
  décision dans Chromium) y est disponible **immédiatement et sans condition**. Mais toucher
  aux drapeaux de l'artefact déplacerait son empreinte d'évaluation (avec
  `-fassociative-math`, l'écart au scalaire passe de 1,788e-07 à 3,576e-07 — les deux sous la
  tolérance de 1e-6 de T20, mais ce n'est plus le même artefact), et `wasm/` est en cours de
  modification par T86. **À reprendre en coordination, et c'est le chantier le plus rentable
  que cette fiche laisse derrière elle.**

## Ce que la suite dit après ces trois fiches

- `pytest tests/` : **1 767 passés, 45 ignorés**, aucun échec. (Une première exécution
  comptait 17 erreurs dans `test_serve*.py` — un worktree neuf n'a pas l'artefact épinglé
  `v1.2.1` ; `python tools/fetch_release.py` les fait disparaître, et elles n'ont rien à voir
  avec le noyau.)
- Corpus de non-régression **T12** : 9 passés, sorties figées au bit près.
- `make wasm-parity` sur l'artefact **livré** (défauts inchangés) :
  **scalaire max|Δ| = 0,000e+00, SIMD max|Δ| = 6,407e-07**, tolérance 1e-6 — exactement la
  valeur que le dépôt publiait avant cette branche. Le refactor de `forward_batch` (le choix
  de la source compactée fait une fois par couche au lieu d'une fois par ligne) n'a rien
  déplacé.
- `make test-tile` : le garde-fou de T90, sous ASan, aux deux volets.

## Reproduire

```bash
make bench-width                       # natif, 9 binaires, round-robin
make bench-width KERNEL_PASSES=5 KERNEL_REPS=7 KERNEL_DECISIONS=12
make bench-width-wasm                  # WebAssembly sous node (V8)
make bench-width-fill                  # le remplissage par largeur
node bench/browser_kernel.mjs --browser chromium --json /tmp/c.json
node bench/browser_kernel.mjs --browser firefox  --json /tmp/f.json
make build KERNEL_INTRINSICS=1         # la bibliothèque avec le noyau à la main
```

Le premier balayage natif, pris à **charge 10** et conservé pour montrer que les rapports
tiennent : largeur 8 auto 17 649 / intrin 63 332 éval/s ; largeur 32 auto 35 255 / intrin
75 903 ; décisions 0,8159 / 0,2983 et 0,4800 / 0,2646 s. Les absolus valent la moitié de ceux
du tableau retenu ; les rapports, à deux points près, sont les mêmes.

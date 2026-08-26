# DS-04 — Encodage creux, accumulation incrémentale, quantification — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-04-nnue-creux-quantification.md`, version injectée du 2026-08-27

> **Ce que ce retour décide** : si le poste « arithmétique » (×2 à ×4) et le poste « taille de
> réseau » (×4 à ×16) peuvent être pris ensemble par un changement d'architecture d'inférence.
> **Ce qu'il conclut** : le ×10 est atteignable mais composé, jamais par une seule technique —
> distillation vers ~60–100k MACs (×2,5–5, qualité quasi intacte si le maître est
> sur-paramétré), quantification int8/int16 **en QAT obligatoire** (la PTQ s'effondre sur petit
> réseau) avec noyau GEMM par lots sur produit scalaire fusionné (VNNI / SDOT / relaxed-SIMD,
> ×2–3 mesurés et non ×4), plus SVD/élagage pour franchir le facteur 10 ; **NNUE incrémental
> écarté** (entrées denses, évaluation par lots, aucun précédent publié sur un jeu à dés) ; le
> bit-à-bit natif↔Wasm **se renforce** en arithmétique entière, à condition de figer ordre de
> sommation, saturation et arrondi, et de contraindre les poids à 7 bits si relaxed_dot est
> utilisé. Licences : XNNPACK BSD-3 / ruy Apache-2.0 / ggml MIT utilisables ; Stockfish NNUE
> GPL-3 inutilisable.
> **Ce qu'il ne tranche pas** : aucun chiffre publié « Wasm relaxed-SIMD int8 = X % du natif
> int8 » sur le même matériel (à mesurer chez nous — c'est l'objet de DS-09) ; l'arbitrage
> batched vs incremental sur jeu à dés reste une hypothèse argumentée ; le ~10 ms de gnubg au
> 2-ply n'a pas de source primaire publiée.

---
# gammonNet — Évaluer un petit réseau de valeur 10× plus vite (CPU + WebAssembly), sans perte de qualité

## TL;DR
- **Le facteur 10 est atteignable, mais pas par une seule technique** : il faut composer (a) une réduction du réseau vers ~60–100k MACs par la distillation/l'élagage, qui rend le compte de MACs comparable à celui de gnubg, et (b) la quantification int8/int16 avec un noyau GEMM par lots exploitant les instructions de produit scalaire (VNNI / dotprod / wasm relaxed-SIMD). Chaque brique isolée donne ~2–3× ; leur produit dépasse 10×. [HYPOTHÈSE / THÉORIQUE]
- **NNUE n'est pas la bonne voie ici** : son gain vient de l'accumulation incrémentale sur entrées binaires creuses le long d'un chemin make/unmake, ce qui ne correspond ni à vos caractéristiques denses ni à votre évaluation par lots. Personne, à ma connaissance, n'a publié d'application de l'accumulation incrémentale NNUE à un jeu à dés. [DÉCLARÉ]
- **Pièges de licence signalés** : le code NNUE de Stockfish est GPL-3.0-or-later (inutilisable dans votre module Wasm distribué). Utilisez XNNPACK (BSD-3-Clause), ruy/gemmlowp/oneDNN (Apache-2.0), libxsmm (BSD-3-Clause) ou ggml (MIT) — tous compatibles avec une distribution permissive. [MESURE/DÉCLARÉ]

## Key Findings

1. **Votre noyau n'est pas lent, il calcule trop.** Votre réseau fait ~527 000 MACs/évaluation contre ~32 640 pour gnubg (~16×) et seulement ~2 550 aux nœuds internes de gnubg via son réseau d'élagage. [DÉCLARÉ, fourni par l'utilisateur ; confirmé pour gnubg : 250 entrées → 128 cachées → 5 sorties = 32 640 poids, mailing-list bug-gnubg 2002-09]. Le levier premier est donc **arithmétique** (moins de MACs), le levier second est **le débit par MAC** (quantification + SIMD).

2. **La quantification int8 donne en pratique 1,5–3×, pas 4×.** Les bancs publiés convergent : le blog PyTorch « INT8 Quantization for x86 CPU in PyTorch » rapporte 2,97× en géomoyenne sur 69 modèles (AWS r7iz.metal-16xl, Intel Xeon Gold 6455B, 4e génération Xeon Scalable), FBGEMM 1,43× ; sur mobile ARM, le gain int8 mesuré est de 0,8–3,0× (souvent bien en deçà du 4× théorique NEON). Pour un petit MLP, on vise réalistiquement 2–3×. [MESURE]

3. **La qualité est préservée si l'on fait du QAT.** Sur petits réseaux, la PTQ int8 perd typiquement ~1–1,5 point (85 % → 83,5 %), le QAT récupère presque tout (84,8 %). Pour un réseau de segmentation « tiny » (TinyIceNet), le QAT 8 bits égale voire dépasse le FP32. Recommandation : QAT, per-channel. [MESURE]

4. **NNUE existe hors des échecs (shogi, xiangqi, Gomoku) mais jamais, à ma connaissance, sur un jeu à dés.** Rapfi/Mixnet (Gomoku, 2025) est l'exemple le plus proche de votre cas et démontre exactement votre stratégie : distillation d'un CNN vers un petit réseau, quantification int16/int8, mise à jour incrémentale, +4× par SIMD AVX2. [MESURE]

5. **La reproductibilité au bit près est plus facile en entier qu'en flottant** — l'arithmétique int8→int32 est exacte et associative — à condition de figer l'ordre de sommation, la stratégie de saturation et l'arrondi, et d'éviter l'instruction `i16x8.relaxed_dot_i8x16_i7x16_s` en Wasm, qui est explicitement non déterministe. [THÉORIQUE/DÉCLARÉ]

## Details

### 1. La quantification (sous-question 1)

**Ce qu'on perd en précision.**
- [MESURE] Sur petit réseau, un banc de quantification typique donne : FP16 baseline 85 % → **INT8 PTQ 83,5 %** (–1,5 pt) → **INT8 QAT 84,8 %** (–0,2 pt). Le QAT est sur la frontière de Pareto ; la PTQ int8 en est légèrement dominée. (https://apxml.com/courses/practical-llm-quantization/chapter-6-evaluating-deploying-quantized-llms/accuracy-performance-tradeoffs, consulté 26/08/2026)
- [MESURE] TinyIceNet (segmentation, petit réseau) : FP32 = 75,168 % F1 ; **PTQ 8 bits s'effondre** (les poids 7–9 bits donnent 13–43 %), il faut ≥12 bits pour stabiliser autour de 70–71 % ; **QAT 8 bits = 75,216 %**, égalant/dépassant le FP32 grâce à l'effet régularisant. (https://arxiv.org/pdf/2603.03075, consulté 26/08/2026) — enseignement : **sur petit réseau, la PTQ int8 peut être dangereuse ; le QAT est le choix sûr.**
- [MESURE] Enquête générale : QAT atteint 4–12× de compression et 2–10× de débit « en maintenant la précision à 3 % du modèle pleine précision » ; en dessous de 4 bits la dégradation devient non linéaire. (https://arxiv.org/pdf/2505.08793, consulté 26/08/2026)
- [DÉCLARÉ] Levier pratique : la quantification **par canal** (per-channel) des poids est « le premier bouton à tourner » en cas de falaise de qualité. (https://medium.com/@jickpatel611/7-ml-quantization-wins-int8-fp8-without-quality-freefall-19d569b734ad, consulté 26/08/2026)

**Int16 vs int8.** L'int16 quasi n'entraîne aucune perte (utilisé par NNUE pour l'accumulateur précisément parce que l'int8 déborderait avant le ClippedReLU). Compromis recommandé : **entrées/première couche en int8 avec accumulation int32 ; accumulateur/valeurs sensibles en int16**.

**Gain de débit réel (et non théorique).**
- [THÉORIQUE] int8 = 4× de voies SIMD vs float32 → borne 4×.
- [MESURE] PyTorch backend x86 : **2,97× géomoyenne** sur 69 modèles (Xeon Gold 6455B, 4e gén.), FBGEMM 1,43×. (https://www.intel.com/content/www/us/en/developer/articles/technical/int8-quantization-for-x86-cpu-in-pytorch.html, consulté 26/08/2026)
- [MESURE] Mobile ARM : int8 = **0,8–3,0×** selon modèle/matériel, « bien moins que les 4× théoriques du NEON », parfois plus lent que le FP32 (squeezenet/vgg16 sur un SoC M11). (https://arxiv.org/pdf/2202.06512, consulté 26/08/2026)
- [MESURE] Dynamic quantization CPU : « typiquement 1,5–2× ». (https://medium.com/@ibrahimfadhili/shrinking-ai-models-by-75-a-practical-guide-to-pytorch-int8-quantization-f8a24836bc28, consulté 26/08/2026)
- [MESURE] Pour très petites dimensions, l'int8 peut **ralentir** : LLM.int8() montre que les modèles de dimension ≤ 2560 sont ralentis par le surcoût quantif/déquantif. C'est directement pertinent : **votre réseau est petit, le surcoût de (dé)quantification par couche peut manger le gain** si les couches sont minuscules. (https://arxiv.org/pdf/2208.07339, consulté 26/08/2026)

**Conclusion sous-question 1 :** viser **2–3× mesurés** par la seule quantification, avec QAT per-channel, int8 sur les grosses couches et int16 là où la dynamique l'exige.

### 2. Les noyaux et les bibliothèques (sous-question 2)

**Débits.** Un GEMM int8 bien tuilé atteint 77–83 % de l'utilisation crête sur accélérateur ; sur CPU la réalité pour de petites matrices est limitée par (a) le surcoût de packing/quantification et (b) le fait que M (taille de lot) est petit. Votre lot de 32 aide : c'est assez pour amortir le packing des poids (statiques, pré-empaquetés une fois) et remplir les registres.

**Instruction clé.** Le produit scalaire int8 fusionné :
- x86 : **VPDPBUSD** (AVX-512 VNNI / AVX-VNNI) ;
- ARM : **SDOT/UDOT** (dotprod) ;
- WebAssembly : **`i32x4.relaxed_dot_i8x16_i7x16_add_s`** (relaxed-SIMD), qui se compile en VPDPBUSD sur x86-AVX-VNNI et en SDOT sur ARM64. [DÉCLARÉ, https://github.com/WebAssembly/relaxed-simd/blob/main/proposals/relaxed-simd/Overview.md, consulté 26/08/2026]

**Bibliothèques et LICENCES (contrainte bloquante).**

| Bibliothèque | Licence (SPDX) | Wasm ? | Remarque |
|---|---|---|---|
| **XNNPACK** (google) | **BSD-3-Clause** | Oui (backend Wasm SIMD de TF.js) | Dépendances toutes permissives (cpuinfo/pthreadpool BSD-2, FP16/FXdiv MIT). Le meilleur candidat. |
| **ruy** (google) | **Apache-2.0** | partiel | Successeur de gemmlowp ; int8 très général. |
| **gemmlowp** (google) | **Apache-2.0** | limité | Superseded par ruy. |
| **oneDNN** (uxl) | **Apache-2.0** | non ciblé Wasm | x86/ARM serveur ; lourd pour un petit MLP. |
| **libxsmm** | **BSD-3-Clause** | non | GEMM JIT petites tailles, x86. |
| **ggml** (ggml-org) | **MIT** | oui | Générique, tensors quantifiés. |
| **Eigen** | **MPL-2.0** (copyleft faible au fichier) | oui | Acceptable mais obligations MPL. |
| **Stockfish NNUE** | **GPL-3.0-or-later** | — | ⚠️ **INUTILISABLE** dans un artefact distribué non-GPL. |

[MESURE, licences vérifiées via fichiers LICENSE des dépôts (XNNPACK LICENSE, ruy/gemmlowp BUILD, oneDNN LICENSE, libxsmm SPDX en-têtes, ggml/llama.cpp LICENSE, Stockfish Copying.txt), consulté 26/08/2026]
⚠️ **Piège majeur signalé** : reprendre le code NNUE de Stockfish (ou tout dérivé GPL) contaminerait votre module Wasm distribué. Apache-2.0/BSD/MIT sont sûrs, avec leurs obligations (notice ; pour Apache-2.0, marquage des fichiers modifiés). Eigen est en MPL-2.0 (copyleft faible « au fichier ») : acceptable, mais impose de publier les modifications des fichiers Eigen touchés.

**Wasm SIMD vs natif — performances mesurées.**
- [MESURE] SPEC CPU : Wasm est **45 % (Firefox) à 55 % (Chrome) plus lent** que le natif en moyenne, pics 2,08×/2,5×. (https://www.usenix.org/conference/atc19/presentation/jangda, consulté 26/08/2026)
- [MESURE] PolyBench : slowdown Wasm ≈ **1,3×** vs natif (x86 et ARM). (https://arxiv.org/pdf/2206.12888, consulté 26/08/2026)
- [MESURE] Microbenchmark SIMD/hachage : Wasm **4× plus lent** que natif à gros volumes, en partie car Wasm SIMD est limité à 128 bits contre 256 bits pour AVX2. (https://nickb.dev/blog/the-webassembly-value-proposition-is-write-once-not-performance/, consulté 26/08/2026) — **point crucial : le Wasm plafonne à 128 bits ; AVX2/AVX-512 natif fait 256/512 bits, d'où un écart structurel.**
- [MESURE] XNNPACK Wasm SIMD int8 : **~20×** vs les kernels TFLite quantifiés par défaut (V8, 3 systèmes x86-64 + 2 ARM64) — ⚠️ gain vs baseline lente, **pas** vs natif. (https://blog.tensorflow.org/2021/09/faster-quantized-inference-with-xnnpack.html, consulté 26/08/2026)
- [MESURE] Relaxed-SIMD (dot-product int8) dans llama.cpp : sur M2 MacBook Air, Chrome v144, 4 fils, gain vs Wasm SIMD standard = **~1,01–1,05× pour du pur int8 (Q8_0)** mais **1,75–2,18× pour les K-quants** — ⚠️ PR non mergée, gain vs Wasm-SIMD (pas natif). (https://github.com/ggml-org/llama.cpp/pull/19590, consulté 26/08/2026)

**Conclusion sous-question 2 :** utilisez **XNNPACK** (BSD) comme socle, ou un noyau maison basé sur les intrinsèques `relaxed_dot`. Attendez-vous à ce que le Wasm soit ~1,3–2× plus lent que le natif à cause du plafond 128 bits, mais le gain relatif int8 vs float32 (2–3×) se transporte.

### 3. Les autres voies vers le facteur 10 (sous-question 3)

- **Distillation.** [MESURE] Sur régression de pose, un étudiant à **7 % des paramètres** du maître reste très proche, et un étudiant à ~20–34 % dépasse parfois le maître (sur-paramétrisation). La dégradation ne s'aggrave nettement qu'au-delà de ~93 % de réduction. (https://arxiv.org/pdf/1908.00858, consulté 26/08/2026) C'est votre meilleur levier : distiller votre réseau 512→512→256→128 vers un réseau ~2–4× plus étroit, entraîné à imiter les 5 sorties du gros réseau.
- **Factorisation de rang faible (SVD tronquée).** [MESURE] Sur couches entièrement connectées : jusqu'à **13× de compression de la 1re FC pour –0,84 pt top-1** (Denton et al.) ; Tai et al. : 5× compression et **1,8× de débit pour < 0,5 pt** top-5. Le coût passe de O(mk) à O(mt+tk). (https://arxiv.org/pdf/1901.06955, consulté 26/08/2026) Pertinent pour vos grosses couches 512×512.
- **Élagage structuré.** Retire des neurones entiers (colonnes/lignes) → gains directs en GEMM dense. À combiner avec la distillation.
- **float16/bfloat16.** [MESURE] bf16 conserve la plage du fp32 (8 bits d'exposant) et, sur CNN MNIST/CIFAR, **égale la précision fp32**. Mais : les CPU sans `avx512_bf16` l'émulent avec **forte dégradation** ; le fp16 charge 2× plus vite (bande passante) mais le calcul CPU fp16 n'est pas universel. Sur mobile/Wasm, **le fp16 n'apporte pas le gain de débit de l'int8**. (https://ovino.readthedocs.io/en/latest/IE_DG/Bfloat16Inference/ ; https://arxiv.org/pdf/2006.07700, consulté 26/08/2026)
- **Courbes précision/MACs pour petits réseaux de jeux.** [MESURE] Rapfi/Mixnet (Gomoku) est la référence : « computation orders of magnitude less to reach a similar accuracy of much larger neural networks such as Resnet », #1 sur 520 agents Botzone, champion GomoCup 2024 (54 concurrents battus), dépassant Katagomo (le plus fort agent Gomoku open-source basé sur l'algorithme d'AlphaZero). (https://arxiv.org/pdf/2503.13178, consulté 26/08/2026)

**Tableau des voies vers le facteur 10**

| Voie | Facteur attendu | Perte de qualité | Effort | Licence des briques | Compatible WebAssembly ? | Compatible bit-à-bit ? |
|---|---|---|---|---|---|---|
| Quantification int8/int16 (QAT) | 2–3× [MESURE] | ~0–0,3 pt avec QAT [MESURE] | Moyen | XNNPACK BSD / ruy Apache | Oui (relaxed-SIMD) | Oui si ordre/saturation figés ; **non** si `relaxed_dot` utilisé sans poids i7 |
| Distillation vers réseau plus étroit | 2–4× [MESURE/HYPOTHÈSE] | quasi nulle si maître sur-paramétré [MESURE] | Moyen | code d'entraînement (le vôtre) | Oui | Oui (nouveau réseau, arithmétique figée) |
| Factorisation rang faible (SVD) | 1,5–2× débit [MESURE] | < 0,5–0,85 pt [MESURE] | Faible | le vôtre | Oui | Oui |
| Élagage structuré | 1,5–3× [HYPOTHÈSE] | faible si réentraîné | Moyen | le vôtre | Oui | Oui |
| Noyau GEMM par lots + VNNI/dotprod | 2–4× vs scalaire [MESURE] | nulle | Élevé | XNNPACK BSD / maison | Oui (128 bits, plafond) | Oui (int) / **non** si relaxed_dot |
| float16/bfloat16 | 1–2× (surtout mémoire) [MESURE] | quasi nulle [MESURE] | Faible | le vôtre | Partiel | **Non** (flottant, ordres de sommation) |
| Accumulation incrémentale NNUE | faible ici [HYPOTHÈSE] | — | Élevé | non-GPL requis | Oui | Difficile |

**Comment atteindre 10× :** distillation (×~2,5) × quantification+noyau (×~3) ≈ **7–8×** de façon robuste, + factorisation/élagage pour franchir 10×. **Ne comptez pas sur une seule voie.**

### 4. La reproductibilité au bit près (sous-question 4)

- [THÉORIQUE] **L'entier aide** : le produit int8×int8→int32 est exact, sans arrondi ; la somme d'entiers est associative tant qu'il n'y a pas de débordement. Vous éliminez les problèmes FMA/flottant qui vous ont forcé à désactiver la contraction.
- [DÉCLARÉ] **Nouveaux écarts à contrôler :** (a) **ordre de sommation** — non problématique en int exact tant qu'aucune saturation intermédiaire n'a lieu ; (b) **saturation** — le point de saturation dépend de l'ordre, il faut donc soit garantir l'absence de débordement (accumulateur int32 large), soit figer l'ordre ; (c) **arrondi** de la remise à l'échelle (division par le facteur d'échelle) — fixez une règle unique (par ex. arrondi arithmétique demi-vers-le-haut) et implémentez-la identiquement ; (d) **signé vs non signé** — VPDPBUSD est u8×s8, SDOT est s8×s8 : les ISA diffèrent sur l'interprétation, donc **choisissez une convention unique et adaptez l'empaquetage par plateforme** pour un résultat identique.
- [DÉCLARÉ] **WebAssembly déterministe** : le Wasm « standard » (SIMD 128) est déterministe. Mais **relaxed-SIMD est explicitement non déterministe** : pour `i16x8.relaxed_dot_i8x16_i7x16_s`, « When the second operand of the product has the high bit set in a lane, that lane's result is implementation defined », et la somme adjacente peut être saturée ou non selon l'implémentation. (https://github.com/WebAssembly/relaxed-simd/blob/main/proposals/relaxed-simd/Overview.md, consulté 26/08/2026)
  - **Conséquence directe** : si vous voulez le bit-à-bit natif↔Wasm, soit (i) contraignez vos poids à 7 bits (i7) pour que le bit de poids fort ne soit jamais mis, ce qui rend le résultat défini, soit (ii) **n'utilisez pas relaxed_dot** et restez sur SIMD standard (`i32x4.dot_i16x8_s` + extensions), au prix d'un peu de débit.

### 5. NNUE, précisément (sous-question 5)

**Architecture réelle (Stockfish/HalfKP historique).** [DÉCLARÉ, https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md + https://www.chessprogramming.org/Stockfish_NNUE, consulté 26/08/2026]
- Feature transformer : entrées binaires creuses HalfKP (~41 024 entrées possibles, mais **0–30 actives** par position pour HalfKP), accumulateur = 2×256 int16 (une moitié par perspective).
- Transform : forme un vecteur de 512 int8 (moitié côté au trait, moitié adverse).
- Couches suivantes : 512→32 (ou 2×256→32), 32→32, 32→1, en int8 avec **accumulation int32**, activation **ClippedReLU** (écrêtage 0..127).
- Facteurs d'échelle : poids ×64, activations en int8 (0..127), sortie divisée par FV_SCALE=16. Variantes ultérieures : HalfKA, HalfKAv2, HalfKAv2_hm (miroir horizontal), buckets de couches (8 « layer stacks » sélectionnés selon le nombre de pièces).
- Accumulateur int16 (pas int8) « car les valeurs dépasseraient la plage int8 avant le ClippedReLU ».

**Fraction de MACs économisée par l'accumulation incrémentale.** [DÉCLARÉ/THÉORIQUE]
- L'économie est **concentrée sur le feature transformer** (la plus grosse couche : 256 sorties × dizaines de milliers d'entrées). Aux échecs, un coup typique ne change que **2–4 features actives** (pièce quittant/arrivant), donc au lieu de recalculer la somme de toutes les lignes actives, on **ajoute/retranche 2–4 lignes de 256**. Les couches suivantes (petites) sont recalculées entièrement à chaque nœud.
- Condition de rentabilité : l'incrémental cesse d'être rentable quand **trop de features changent** — typiquement un **coup de roi en HalfKP force un rafraîchissement complet** de l'accumulateur, car toutes les features sont indexées par la case du roi.
- Ordre de grandeur : le feature transformer représente l'essentiel des poids ; l'incrémental le rend quasi gratuit sur les coups « normaux », d'où le gain global majeur de NNUE. [HYPOTHÈSE quantitative : la majorité des MACs du transformer sont évitées sur les coups sans déplacement de roi]

**Changement de trait.** Double accumulateur (perspective « côté au trait » et « adverse ») ; à chaque coup on échange les moitiés et on met à jour les deux.

### 6. NNUE hors des échecs (sous-question 6)

- [DÉCLARÉ] **Shogi** : origine (Yu Nasu, 2018, YaneuraOu), « apparemment de force AlphaZero ». (https://chessprogramming.org/NNUE ; https://arxiv.org/pdf/2209.01506, consulté 26/08/2026)
- [DÉCLARÉ] **Échecs** (Stockfish 12, 2020), **échecs chinois / xiangqi**, variantes via Fairy-Stockfish.
- [MESURE] **Gomoku** : Rapfi/Mixnet (2025) — pas du NNUE au sens strict, mais **exactement les mêmes principes** (codebook distillé, mise à jour incrémentale, quantification int16/int8) appliqués à un jeu **déterministe** à information parfaite. (https://arxiv.org/pdf/2503.13178, consulté 26/08/2026)
- **Jeu à hasard (dés/cartes/poker) : je n'ai trouvé AUCUNE publication appliquant l'accumulation incrémentale de type NNUE à un jeu à dés.** Voir « Ce que je n'ai pas trouvé ».

### 7. Le cas particulier de l'expectiminimax (sous-question 7)

**Structure en étoile vs chemin.** Votre nœud développe 21 jets × ~20 filles ≈ 420 positions par nœud 1-ply, toutes proches de la parente. Deux effets opposés :
- **En faveur de l'incrémental** : structure en étoile = beaucoup de filles proches d'une même parente ; on pourrait précalculer l'accumulateur de la parente puis n'appliquer que le delta de chaque coup. C'est précisément ce que Rapfi exploite (mais en profondeur, α-β). [HYPOTHÈSE]
- **Contre l'incrémental** : (a) vos caractéristiques sont **denses et globales** (tirs touchant un blot, pips attendus, containment via tables) — un seul déplacement de pion peut changer **beaucoup** de ces grandeurs (le nombre de tirs touchant change dès qu'un blot bouge), donc le « delta » n'est pas petit comme aux échecs ; (b) **l'évaluation par lots de 32 positions indépendantes se calcule très efficacement en GEMM dense** avec un bon noyau, et un GEMM dense de 32 colonnes sature bien mieux le SIMD qu'une cascade de mises à jour incrémentales de petits vecteurs. [HYPOTHÈSE argumentée]
- **Arbitrage batched vs incremental** : je n'ai pas trouvé de travail publié chiffrant précisément cet arbitrage pour un jeu à dés. Le point de bascule dépend du nombre de features qui changent par coup ; au backgammon, avec des caractéristiques denses recalculées en O(24) ou O(36), **le lot dense me paraît gagnant**. [HYPOTHÈSE]

**Élagage en expectiminimax.** [MESURE/DÉCLARÉ] Star1/Star2 de Ballard (« The *-Minimax Search Procedure for Trees Containing Chance Nodes », *Artificial Intelligence* 21(3):327-350, 1983), « redécouverts » par Hauk, Buro & Schaeffer (*Computers and Games* 2004) : « with effective move ordering and probing the Star2 algorithm considerably outperforms Expectimax », permettant des recherches full-width de profondeur 5 (au lieu de 3) en tournoi. Leur conclusion notable : « good checker play in backgammon does not require deep searches ». (https://dl.acm.org/doi/10.1007/11674399_4, consulté 26/08/2026) — **implication stratégique : investir dans une évaluation statique rapide et précise (0/1-ply) peut valoir mieux que d'aller plus profond.**

**Réseaux d'élagage de gnubg.** [DÉCLARÉ] gnubg utilise un jeu de petits réseaux d'élagage ; d'après l'analyse de Jim Segrave citée dans le manuel V0.16 : « Jim Segrave has just done an analysis of this and found that less than 1% of all moves come out different with the pruning nets activated. In most of these positions the move would not have made any difference to the game at all. » (https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html, consulté 26/08/2026) C'est l'idée de votre ~2 550 MACs aux nœuds internes : **un mini-réseau d'élagage** pour trier les candidats avant l'évaluation complète.

**Lignée d'architectures.** TD-Gammon : 198 entrées (encodage de Tesauro, 4 unités/point/couleur = 96×2, + barre + sortis + trait), **1 couche cachée** de 40 unités (v0.0, 1991), 80 (v1.0/2.0/2.1/3.0), 160 (v3.1, 1998), 4 sorties (White/Black normal win + gammon win). (https://en.wikipedia.org/wiki/TD-Gammon, consulté 26/08/2026). gnubg : 250→128→5 = 32 640 poids, réseaux séparés par phase (contact, course, crashed). BGBlitz/Snowie : même lignée feed-forward. **Aucun n'utilise 512→512→256→128 comme vous** — votre réseau est ~16× plus gros que l'état de l'art éprouvé, ce qui confirme que la réduction est votre levier premier.

## Recommendations

**Architecture d'inférence que je recommanderais.**

*Étape 0 — Réduire d'abord le réseau (le plus gros gain).*
- Distiller 512→512→256→128→5 vers **256→128→64→5** (ou plus étroit si la qualité tient), entraîné à imiter les 5 sorties du réseau actuel (perte MSE sur logits + éventuellement sur l'équité). Cible : passer de ~527k à **~60–100k MACs** (≈5–8×). Valider sur votre base de benchmark (comme les ~100 000 positions de contrôle de gnubg).
- Appliquer une **SVD tronquée** sur les couches restantes les plus larges (rang t tel que mt+tk ≪ mk) pour grappiller 1,5–2× de plus si la qualité le permet.

*Étape 1 — Quantifier en QAT.*
- **Entrées et poids en int8, per-channel**, accumulation **int32**.
- **Accumulateur/première couche large en int16** si la dynamique de vos caractéristiques denses l'exige (elles ne sont pas bornées 0..1 comme des features binaires).
- Activation **ClippedReLU** (écrêtage 0..127) pour rester en int8 entre couches, comme NNUE.
- Facteurs d'échelle en puissances de 2 → la remise à l'échelle devient un décalage (shift), exact et portable.

*Étape 2 — Noyau GEMM par lots.*
- Disposition mémoire : **poids pré-empaquetés hors ligne** en tuiles adaptées à VNNI/dotprod (blocs K de 4 int8 contigus pour VPDPBUSD/SDOT). Activations en **column-major par lot de 32** (M=32) pour maximiser la réutilisation des poids.
- Boucle : pour chaque tuile de sortie, charger 4 int8 de K, diffuser sur les 32 colonnes, accumuler en int32 via `VPDPBUSD` (x86), `SDOT` (ARM), `i32x4.dot_i16x8_s`/relaxed (Wasm).
- **Deux chemins Wasm** : (i) *déterministe* = SIMD 128 standard, pour le bit-à-bit ; (ii) *rapide* = relaxed-SIMD avec poids contraints à 7 bits (i7) pour rester défini et donc reproductible.
- Socle logiciel : **XNNPACK (BSD-3-Clause)** si vous acceptez sa surface, sinon **noyau maison** (~quelques centaines de lignes) avec intrinsèques, ce qui donne le contrôle total sur l'ordre de sommation (indispensable au bit-à-bit).

*Étape 3 — Recherche.*
- Ajouter un **mini-réseau d'élagage** (~10–20 neurones cachés, façon gnubg) aux nœuds internes pour ne faire l'évaluation complète que sur les candidats retenus.
- Implémenter **Star2** (avec ordonnancement des coups) plutôt que l'expectiminimax plein.

**Bornes / seuils qui changeraient la décision :**
- Si la distillation coûte > 1 pt d'équité (ou > ~2 % d'erreur sur votre base de contrôle), réduisez moins agressivement et compensez par le noyau.
- Si le lot de 32 en GEMM dense atteint déjà le facteur 10 après quantification, **n'implémentez pas l'incrémental** (complexité inutile, risque bit-à-bit).
- Si le Wasm reste > 2× plus lent que le natif après optimisation, envisagez d'activer les threads Wasm (SharedArrayBuffer) et de paralléliser sur les 21 jets.

## Caveats — Ce que je n'ai pas trouvé

- **Personne, à ma connaissance, n'a publié d'application de l'accumulation incrémentale de type NNUE à un jeu à dés** (backgammon, jeux de dés, poker). NNUE est documenté pour shogi, échecs, xiangqi ; les principes ont été portés au Gomoku (Rapfi, jeu déterministe). Votre projet serait donc, sur ce point, en terrain neuf — ce qui est une information utile en soi. [DÉCLARÉ]
- **Pas de banc d'essai publié chiffrant l'arbitrage « batched vs incremental » pour un jeu à dés** avec caractéristiques denses. Mon analyse penche vers le lot dense, mais c'est une [HYPOTHÈSE] argumentée, non une mesure.
- **Aucune source directe donnant le ratio « Wasm relaxed-SIMD int8 = X % du natif int8 » sur le même matériel.** Les chiffres existants sont des gains relatifs (vs baseline lente ou vs Wasm-SIMD standard). Il faudra le mesurer sur votre cible.
- **Le temps de décision 2-ply de gnubg (~10 ms) n'a pas de source primaire directe.** Le manuel gnubg donne des débits d'évaluation anciens (~28 000 évals/s sur CPU de 2005 ≈ 36 µs/évaluation) et la règle « chaque ply ≈ ×20 » ; votre chiffre de 10 ms est plausible sur CPU moderne mais je ne l'ai pas confirmé par une source publiée. À noter aussi : gnubg utilise des réseaux en **virgule flottante**, pas int8/NNUE — la référence int8 pertinente reste Stockfish NNUE. [DÉCLARÉ, fourni par l'utilisateur]
- **Pas de courbe précision-vs-MACs publiée spécifiquement pour des réseaux de valeur de backgammon** ; la référence transférable la plus proche est Rapfi (Gomoku).
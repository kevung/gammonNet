# DS-09 — WebAssembly et WebGPU — retour

**Date de la recherche** : 2026-08-26 · **Outil** : Claude, recherche approfondie
**Prompt** : `docs/recherche/DS-09-webassembly-et-webgpu.md`, version injectée du 2026-08-27

> **Ce que ce retour décide** : si le facteur de vitesse gagné en natif se transporte dans le
> navigateur — seul endroit où le produit vit — et jusqu'où le 3-ply devient concevable sur
> l'appareil.
> **Ce qu'il conclut** : le socle est un **noyau int8 maison en SIMD128 déterministe**
> (`i32x4.dot_i16x8_s` — universel, Safari iOS 16.4+ compris, bit-à-bit préservé) ; le
> relaxed-dot 7 bits n'est qu'une **accélération opt-in** Chrome/Firefox/Android — absent de
> Safari stable en août 2026 (arrivé en Technology Preview 250 seulement) et non déterministe,
> donc hors du repère bit-à-bit ; **WebGPU est écarté** pour l'évaluateur (dispatch-bound :
> 24–36 µs par lancement, gain < 2× sous 512×512, non bit-exact par spécification WGSL) ; les
> bibliothèques génériques sont battues par le noyau maison sur un réseau si petit (repli
> licence-sûr unique : ONNX Runtime Web, MIT). Projections depuis notre banc : ~9 400 éval/s
> mesurés → **~60 000–120 000 éval/s** après distillation + int8 (hypothèses, micro-banc à
> faire). Nos 3,3 ouvriers effectifs sont expliqués (`hardwareConcurrency` plafonné à 4 sur
> iOS + throttling thermique qui retire les grands cœurs vers ~49–50 °C) ; l'anomalie
> ×2,21/×8,5 du lot reçoit une explication dominante — pas de VNNI/FMA en Wasm déterministe,
> plafond 128 bits — et un **test décisif** : un build natif dégradé SSE2 sans FMA/VNNI.
> Artefact : int8 + Brotli → sous ~300 Kio transférés, hors chemin critique.
> **Ce qu'il ne tranche pas** : aucun banc publié int8 vs f32 en SIMD128 pour de petites GEMM
> (notre banc serait la première source) — tous les débits projetés sont des hypothèses à
> confirmer par le micro-banc ; la présence de `packed_4x8_integer_dot_product` et des
> subgroups sur Safari iOS 26 n'est pas confirmée ; la latence de dispatch WebGPU sur iPhone
> n'a jamais été mesurée ; les éval/s récents de gnubg et des moteurs de go en navigateur sont
> introuvables.

---
# gammonNet — Débit d'inférence atteignable dans le navigateur pour un petit réseau dense (rapport technique)

## TL;DR
- **Le chemin réaliste et portable est un noyau int8 SIMD128 écrit à la main, pas WebGPU ni une bibliothèque tierce.** Sur votre propre banc, le réseau actuel (527 000 MACs, f32, SIMD128) tient déjà ~9 400 évaluations/s ; un réseau distillé à ~80 000 MACs devrait porter cela à ~60 000–90 000 éval/s [HYPOTHÈSE], la quantification int8 ajoutant un gain modéré dans le sous-ensemble *déterministe* de SIMD128 (`i32x4.dot_i16x8_s`).
- **Le produit scalaire int8 en 7 bits de relaxed-SIMD (`i32x4.relaxed_dot_i8x16_i7x16_add_s`) est le seul mécanisme qui rapproche du VNNI/SDOT natif, mais il n'existe PAS sur Safari (macOS ni iOS) en stable en août 2026** — il vient seulement d'arriver dans Safari Technology Preview 250 (13 août 2026). C'est donc un chemin *optionnel* pour Chrome/Firefox/Android, pas un socle. Et il est explicitement non déterministe : il casse votre garantie bit-à-bit.
- **WebGPU est disponible sur iOS 26 mais ne convient pas à cette charge** : à des lots de 32–quelques centaines de positions avec dépendance séquentielle entre niveaux, le coût d'aller-retour de lancement (~24–36 µs par dispatch mesuré, et 15–25 ms bout-en-bout pour un petit modèle sur M2) annule le gain. Restez sur le CPU/WASM ; réservez WebGPU aux rollouts massifs si un jour ils migrent au navigateur.

## Key Findings

1. **SIMD128 est universel, y compris iOS.** Safari 16.4 (27 mars 2023) a complété le tableau ; Chrome 91+, Firefox 89+, Edge 91+. C'est votre socle garanti sur les sept plateformes. [DOCUMENTÉ]
2. **Relaxed-SIMD n'est PAS un socle.** Chrome 114+, Firefox 120+ (drapeau retiré en Firefox 145), mais Safari/iOS « Not supported » jusqu'à 26.6/TP selon caniuse (données juillet 2026). Concevez le noyau int8 pour fonctionner *sans* lui, avec relaxed-dot en accélération opt-in détectée à l'exécution. [DOCUMENTÉ]
3. **L'écart int8 vs f32 mesuré en WASM pour de petites GEMM est modeste, pas spectaculaire** — parce que le sous-ensemble déterministe de SIMD128 n'a pas d'équivalent de VPDPBUSD (int8 4-voies). Le gros gain int8 mesuré (5,6× NEON SDOT, 2× théorique AVX512-VNNI) est un chiffre *natif*, pas WASM.
4. **Le threading impose COOP/COEP**, ce qui casse Stripe Checkout, Google Sign-In et les iframes tierces sans CORP/CORS. Sur mobile le parallélisme réel est faible : iOS Safari plafonne `navigator.hardwareConcurrency` à 4, et la limitation thermique retire les cœurs « grands » sous charge soutenue — ce qui explique vos 3,3 ouvriers effectifs.
5. **WebGPU/WGSL n'est pas déterministe** (tolérances en ULP, FMA optionnelle) et **relaxed-SIMD non plus** (non-déterminisme local explicitement spécifié). Seuls SIMD128 pur et le chemin int16-dot déterministe préservent votre égalité bit-à-bit natif↔WASM.
6. **Licences : ONNX Runtime Web (MIT) et TensorFlow.js (Apache-2.0) sont distribuables ; gnubg est GPL** — comme Stockfish, exploitable pour ses mesures, pas pour son code.
7. **Budget d'artefact : ~2 Mio f32 est au-dessus du raisonnable ; la quantification int8 divise le poids par ~4** (~500 Kio) et se place sous les repères usuels (170 Kio critiques compressés).

---

## Details

### 1. SIMD dans WebAssembly

**SIMD128 (largeur fixe, déterministe).** Disponibilité :
- Chrome 91+ (2021), Firefox 89+ (2021), Edge 91+, **Safari 16.4 (27 mars 2023)** — première version où *tous* les navigateurs majeurs supportent le SIMD 128 bits fixe. [DOCUMENTÉ — Uno Platform, https://platform.uno/blog/safari-16-4-support-for-webassembly-fixed-width-simd-how-to-use-it-with-c/, consulté 26/08/2026]
- iOS : Safari iOS 16.4+ (même moteur WebKit). [DOCUMENTÉ]
- Le v128 + 236 instructions sont mappés vers SSE sur x86 et NEON sur ARM. [DOCUMENTÉ — testmuai/LambdaTest, https://www.testmuai.com/learning-hub/wasm-simd-browser-support/]

L'instruction clé pour un noyau int déterministe est **`i32x4.dot_i16x8_s`** : produit scalaire de deux vecteurs i16x8, multiplication lane-à-lane puis addition des paires adjacentes → i32x4. Sur ARM elle se compile en `smull ; smull2 ; addv`. [DOCUMENTÉ — MDN, https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/SIMD/arithmetic/dot_i16x8_s, consulté 26/08/2026 ; PR WebAssembly/simd#127, https://github.com/WebAssembly/simd/pull/127]. **Point capital pour vous : c'est du int16×int16 (2-voies), pas du int8 4-voies.** Pour du int8 vous élargissez en i16 puis appliquez ce dot ; le sous-ensemble déterministe de SIMD128 n'offre PAS de VPDPBUSD/SDOT int8 4-voies. C'est la raison structurelle pour laquelle le gain int8 restera modéré tant que vous exigez le déterminisme.

**Relaxed-SIMD (non déterministe).** Instructions concernées pour vous : **`i16x8.dot_i8x16_i7x16_s`** et **`i32x4.dot_i8x16_i7x16_add_s`**. Elles exposent le produit scalaire int8 4-voies avec accumulation, comme VPDPBUSD/AVX-VNNI (x86) et SDOT (ARM). La contrainte 7 bits sur le second opérande résout l'incompatibilité x86 (signé×non-signé) vs ARM (signé×signé ou non-signé×non-signé) : si le second vecteur a au plus 7 bits significatifs, signé et non signé coïncident, et le résultat est défini. [DOCUMENTÉ — WebAssembly/relaxed-simd issue #52, https://github.com/WebAssembly/relaxed-simd/issues/52, consulté 26/08/2026]

Déploiement (août 2026) :
- Chrome 114+ / Edge 114+, Firefox 120+ (derrière drapeau jusqu'à Firefox 145 où il est activé par défaut), Opera 100+, Samsung Internet 23+. [DOCUMENTÉ — caniuse, https://caniuse.com/wf-wasm-simd-relaxed, données juillet 2026]
- **Safari desktop et Safari iOS : « Not supported » jusqu'à 26.5, 26.6 et même TP** dans la table caniuse. [DOCUMENTÉ — caniuse, consulté 26/08/2026]
- Il vient d'être **ajouté à Safari Technology Preview 250 (13 août 2026)** — « Added support for relaxed SIMD instructions. (317549@main) ». [DOCUMENTÉ — WebKit, https://webkit.org/blog/18191/release-notes-for-safari-technology-preview-250/, publié 13/08/2026]. STP n'est pas une version stable ; aucun iPhone grand public ne l'exécute au 26/08/2026. Historique : « still behind a flag in Safari » fin 2025, tandis que Firefox l'avait déjà dé-flaggé. [DOCUMENTÉ — Uno Platform, https://platform.uno/blog/the-state-of-webassembly-2025-2026/]

**Écart int8 vs f32 mesuré :**
- Natif ARM NEON : noyau int8 SDOT à **4,70 ns** contre **26,5 ns** en f32 pour une comparaison de vecteurs 768-D → **5,6×** [MESURE — arXiv 2601.15311 « Aeon », https://arxiv.org/pdf/2601.15311]. *Natif, pas WASM.*
- Natif x86 (FBGEMM) : l'accumulation int8→int16 atteint un pic théorique **2× le pic FP32** (153,6 GOPS sur Broadwell) ; mais avec accumulation int32, « the theoretical compute peak for INT8 is not better than FP32 even though each element size is 4× smaller » car 4 instructions (vpmaddubsw, vpmaddwd, vpaddd) sont nécessaires par FMA int8 sans VNNI. [MESURE/DOCUMENTÉ — arXiv 2101.05615]
- **Je n'ai pas trouvé de banc publié isolant int8 vs f32 pour une GEMM 512×512 *en WebAssembly SIMD128*** avec matériel + version cités (voir « Ce que je n'ai pas trouvé »).

Conséquence pour gammonNet : le gain int8 « facile » vient surtout de la **bande passante** (poids 4× plus petits, meilleure occupation du cache/registres) et non d'un débit arithmétique 4× ; en SIMD128 déterministe, tablez sur **~1,3–2×** vs f32 pour vos petites GEMM [HYPOTHÈSE], et un supplément vers 2–3× seulement si relaxed-dot est disponible (donc jamais sur iOS) [HYPOTHÈSE].

### 2. Les fils (threads)

**COOP/COEP.** `SharedArrayBuffer` et les fils WASM exigent l'isolation d'origine croisée : `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp`. [DOCUMENTÉ — web.dev, https://web.dev/articles/coop-coep, consulté 26/08/2026]. Conséquences concrètes :
- COOP `same-origin` fait perdre `window.opener` aux pop-ups d'autres origines : **casse Google Sign-In, Stripe Checkout, YouTube** et les flux OAuth/paiement en pop-up. [DOCUMENTÉ — uper.pl, https://uper.pl/en/blog/coop-coep-corp-cross-origin-isolation/, 2026]
- COEP `require-corp` bloque toute ressource tierce (CDN, iframes, analytics, pubs) qui n'envoie pas CORP/CORS. Le mode **`credentialless`** réduit la casse en chargeant sans cookies plutôt qu'en exigeant CORP. [DOCUMENTÉ — web.dev]
- Note : Safari a longtemps été le plus strict sur les variantes de COEP acceptées ; lichess/stockfish.wasm exigent explicitement ces en-têtes et détectent leur absence. [DOCUMENTÉ — lichess-org/stockfish.wasm, https://github.com/lichess-org/stockfish.wasm]

**Parallélisme réel sur mobile.**
- `navigator.hardwareConcurrency` : selon un rapport terrain (issue mdn/browser-compat-data #30063, ouverte par Knagis le 17 juillet 2026), « actual testing show that every iphone from 11 to 17 always return 4 … The value of this property is always 4, to prevent device fingerprinting » ; caniuse/W3cubDocs affirme au contraire « WebKit browsers clamp the maximum value returned to 2 on iOS devices and 8 on all others » — **donnée contradictoire, mais le test terrain donne 4 sur iOS**. [DOCUMENTÉ — https://github.com/mdn/browser-compat-data/issues/30063 ; https://docs.w3cub.com/browser_support_tables/hardwareconcurrency.html]. Firefox plafonne à 16. [DOCUMENTÉ — Bugzilla 1728741]
- **Limitation thermique et big.LITTLE** : sous charge soutenue, le gouverneur thermique réduit la fréquence puis migre les tâches des grands cœurs vers les petits, voire éteint le cluster grand. Sur Nexus 6P, les grands cœurs passent hors-ligne et migrent vers les petits après une montée modérée de température, autour de 50 °C. [MESURE — arXiv 2005.12326]. Un test terrain montre qu'une fois le grand cluster throttlé à 0,63 GHz, il « n'est plus utilisé pour aucune tâche » et le seuil observé est 49 °C. [MESURE — XDA, https://xdaforums.com/t/thermal-throttling-temp-performance-test.3388559/]. Travaux récents : l'ordonnancement « energy-aware » fait tourner les CPU à des fréquences sous-optimales pendant l'inférence. [DOCUMENTÉ — arXiv 2603.23640]
- **Vos 3,3 ouvriers effectifs** sont cohérents avec ceci : sur un octa-cœur big.LITTLE, seuls les grands cœurs sont vraiment utiles pour une GEMM, les petits contribuent partiellement, et le throttling en retire sous charge. C'est une borne physique, pas un défaut de votre ordonnanceur. [HYPOTHÈSE]

### 3. WebGPU

**Disponibilité :** Chrome/Edge 113+ (2023), Firefox 141+ (Windows) / 145+ (macOS), et **Safari 26 sur macOS Tahoe 26, iOS 26, iPadOS 26, visionOS 26** — WebGPU est activé par défaut. [DOCUMENTÉ — web.dev, https://web.dev/blog/webgpu-supported-major-browsers ; testmuai, https://www.testmuai.com/learning-hub/webgpu-browser-support/]. Donc oui, disponible sur iPhone, mais seulement iOS 26+.

**Le coût d'aller-retour tue la charge.** Mesures publiées :
- Latence de lancement WebGPU : **24–36 µs par dispatch**, contre 7,4 µs pour CUDA. [MESURE — arXiv 2604.02344, https://arxiv.org/html/2604.02344v1, « Our measurements (WebGPU 24–36 µs, CUDA 7.4 µs) are consistent »]
- Petit modèle d'embedding, une inférence : **WASM 8–12 ms vs WebGPU 15–25 ms sur MacBook Air M2** — « The GPU dispatch overhead… exceeds the computation itself. » [MESURE — SitePoint, https://www.sitepoint.com/webgpu-vs-webasm-transformers-js/]
- GEMM : en dessous de 256×256 « the net difference fell within measurement noise » ; à 512×512 le gain WebGPU est « less than 2× » ; WebGPU ne domine (3–8×) qu'à partir de 2048×2048. [MESURE — SitePoint, https://www.sitepoint.com/webgpu-vs-webgl-inference-benchmarks/]

Votre charge (lots de 32–quelques centaines × ~80 000 MACs, avec dépendance séquentielle entre plies) est exactement le régime « dispatch-bound » où WebGPU perd. Chaque niveau de recherche impose un aller-retour ; on ne peut pas fusionner à travers la dépendance. **Recommandation : ne pas utiliser WebGPU pour l'évaluateur.** [HYPOTHÈSE étayée par les mesures ci-dessus]

**Entiers/dot product en WGSL.** L'extension **`packed_4x8_integer_dot_product`** (built-ins `dot4U8Packed`, `dot4I8Packed`, + `pack4xI8`/`unpack4xI8`) existe depuis Chrome 123 ; à signaler par `requires packed_4x8_integer_dot_product;` car non portable. [DOCUMENTÉ — Chrome for Developers, https://developer.chrome.com/blog/new-in-webgpu-123, consulté 26/08/2026]. Gain mesuré : int8 vs f16 **1,6–2,8×**, et avec `dot4U8Packed` **1,7–2,9×** sur divers GPU grand public. [MESURE — Chrome I/O 2024, https://developer.chrome.com/blog/io24-webassembly-webgpu-2]. Les **subgroups** (Chrome 134) donnent 2,3–2,9× supplémentaires sur des matrice-vecteur chez Google Meet. [MESURE — Chrome for Developers, https://developer.chrome.com/blog/new-in-webgpu-134]. Mais ces extensions sont côté Chromium ; leur présence sur Safari iOS n'est pas garantie, et elles ne changent pas le verdict dispatch-bound.

### 4. Ce que font les autres

- **Stockfish WASM (NNUE, lichess).** ~**60 knœuds/s** en WASM NNUE avec `-msimd128` (sse/ssse3/sse41), « Not known where performance is lost. » [MESURE — niklasf, PR #21 stockfish.wasm, https://github.com/lichess-org/stockfish.wasm/pull/21 ; valeur non re-confirmée par une source primaire chiffrée récente]. Sur mobile, selon UBOS, « the browser-based analysis board on Lichess reports close to 1 MN/s on a Redmi Note 14 Pro, while a locally-run Stockfish binary via Python only shows about 600 kN/s » — mais le WASM met plus longtemps à atteindre la même profondeur, et la cause citée est double : « Lichess caps threads (often 2-4 on mobile) » et le mode Multi-PV qui gonfle le N/s affiché. [MESURE/DOCUMENTÉ — UBOS, https://ubos.tech/news/lichess-vs-stockfish-why-online-analysis-shows-higher-speed-but-slower-depth/]. **Licence : GPL-3 → code inutilisable pour vous, mesures utiles.** stockfish.wasm exige COOP/COEP.
- **GNU Backgammon (gnubg).** Portage web réel : `hwatheod/gnubg-web`, source gnubg 1.05.000 compilé en WASM, GUI JavaScript, poids `gnubg.wd` packagés. [DOCUMENTÉ — https://github.com/hwatheod/gnubg-web]. Le manuel documente les « pruning neural networks » qui filtrent les coups candidats (< 1 % de décisions changées) — analogue à votre filtre serré 2-ply. [DOCUMENTÉ — https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html]. **Licence : GPL → code exclu.** gnubg publie des tables CPU × éval/s (Analyse→Vitesse d'évaluation) mais je n'ai pas récupéré les valeurs chiffrées récentes (voir « Ce que je n'ai pas trouvé »).
- **KataGo/Leela/lc0 web** : je n'ai pas trouvé de banc navigateur chiffré fiable et daté pour ces moteurs de go dans le temps imparti (voir « Ce que je n'ai pas trouvé »).

### 5. Bibliothèques d'inférence pour le navigateur

| Bibliothèque | Licence | Distribuable ? | Pertinence pour 80 k MACs |
|---|---|---|---|
| **ONNX Runtime Web** | **MIT** (le format ONNX lui-même : Apache-2.0) | ✅ Oui | Moteur ORT compilé en WASM via Emscripten ; surcoût par appel + graphe générique probablement rédhibitoire face à un noyau maison sur un si petit réseau |
| **TensorFlow.js (backend WASM)** | **Apache-2.0** | ✅ Oui | S'appuie sur **XNNPACK** (BSD) ; gain annoncé par Google : « our Wasm backend has become up to 10X faster », décomposé en « SIMD brings a 1.7-4.5X performance improvement to plain Wasm, and multithreading brings another 1.8-2.9X speedup on top of that » [MESURE — TensorFlow Blog, Ann Yuan & Marat Dukhan, 2 sept. 2020, https://blog.tensorflow.org/2020/09/supercharging-tensorflowjs-webassembly.html] ; mais orienté modèles « models repo », surcoût JS/kernel |
| **XNNPACK** (sous-jacent) | **BSD-3** | ✅ Oui | Noyaux flottants très optimisés ; réutilisable |
| **WebNN API** | (API navigateur) | n/a | **Chrome/Edge seulement, en preview, CR janvier 2026 ; « should not currently be used in a production environment »** ; pas de Safari/Firefox → hors jeu pour vous [DOCUMENTÉ — Microsoft Learn, https://learn.microsoft.com/en-us/windows/ai/directml/webnn-overview] |
| **gnubg / Stockfish** | **GPL** | ❌ Non | Copyleft fort — exclu |

Surcoût par appel : les papiers WebGPU montrent que pour de petits modèles le surcoût d'orchestration domine (WASM 8–12 ms là où le calcul pur est bien moindre). Pour 80 000 MACs par éval et des lots de 32, **un noyau écrit à la main (comme vous le faites déjà) battra une bibliothèque générique** dont le coût par appel et la couche de graphe ne s'amortissent pas. [HYPOTHÈSE étayée]. Verdict : gardez votre noyau maison ; ONNX Runtime Web (MIT) est le seul repli acceptable côté licence si vous vouliez un jour externaliser.

### 6. Le déterminisme

**Ce qui met en danger votre égalité bit-à-bit :**
- **SIMD128 pur : sûr.** Chaque instruction produit un résultat déterministe, portable, identique sur tout CPU. « WASM SIMD locks every instruction to a deterministic, portable result across CPUs. » [DOCUMENTÉ — testmuai]. `i32x4.dot_i16x8_s` est donc votre allié : entièrement défini.
- **Relaxed-SIMD : explicitement non déterministe.** « This proposal introduces non-deterministic instructions - given the same inputs, two calls to the same instruction can return different results. » [DOCUMENTÉ — Overview.md, https://github.com/WebAssembly/relaxed-simd/blob/main/proposals/relaxed-simd/Overview.md]. Trois familles : (a) entiers interprétés différemment (swizzle, dot 4-voies) ; (b) flottants hors-domaine/NaN (min/max, float→int) ; (c) précision/ordre (FMA, réciproques). Pour le dot int8, le non-déterminisme réside dans le choix signé/non-signé quand le bit de poids fort du second opérande est à 1 — **d'où votre contrainte 7 bits** : en bornant les poids à 7 bits, `IMPLEMENTATION_DEFINED_ONE_OF(signé, non-signé)` n'est jamais atteint et le résultat redevient défini. [DOCUMENTÉ — pseudo-code `i16x8_dot_i8x16_i7x16_s`, même source]. Le non-déterminisme est « limité au résultat d'une instruction et cohérent entre exécutions » sur une même machine, mais **peut différer entre implémentations/CPU**. [DOCUMENTÉ — WebAssembly/design issue #1401]. Vous avez déjà désactivé la contraction FMA côté natif ; relaxed-SIMD réintroduirait précisément ce type de divergence.
  - **Conclusion : si vous adoptez relaxed-dot, faites-le derrière un drapeau, avec les poids strictement bornés à 7 bits, et n'incluez JAMAIS ce chemin dans votre repère bit-à-bit.** Le chemin de référence reste SIMD128 déterministe.
- **WebGPU/WGSL : non bit-exact.** La spec WGSL (W3C, Candidate Recommendation Draft du 25 août 2026) définit la précision des built-ins flottants par des **tolérances en ULP**, pas des résultats exacts (§15.7 « Floating Point Evaluation », §15.7.4 « Floating Point Accuracy »). Certaines fonctions ont une erreur non bornée près des cas limites (ex. `atan2` : « The error in the result is unbounded: When abs(x) is very small … At the origin (x,y) = (0,0) … »). La §15.7.5 « Reassociation and Fusion » autorise l'implémentation à fusionner ou non un `a*b+c` (FMA vs mul+add séparés) — donc pas de garantie bit-à-bit. La spec prévient : « different implementations may exhibit the different behaviors … a portability hazard. » [DOCUMENTÉ — W3C WGSL, https://www.w3.org/TR/WGSL/, §1.1 et §15.7, consulté 26/08/2026]. **WebGPU est structurellement incompatible avec votre garde anti-régression bit-à-bit.**

### 7. La taille de l'artefact

- **Budget raisonnable 2026.** Repère web.dev : « try to deliver under 170 KB of critical-path resources (compressed/minified). This guarantees your website will be fast even on inexpensive devices and slow 3G » ; budgets JS souvent fixés à 200 Kio compressés. [DOCUMENTÉ — web.dev, https://web.dev/articles/your-first-performance-budget ; https://web.dev/articles/codelab-setting-performance-budgets-with-webpack]. La ligne de base « performance inequality » 2024 (P75 mobile/réseau) vise un premier chargement < 5 s. [DOCUMENTÉ — Infrequently Noted 2024, https://infrequently.org/2024/01/performance-inequality-gap-2024/]. Vos ~2 Mio de poids f32 sont donc au-dessus du raisonnable pour du chemin critique — à charger en différé, pas au premier rendu.
- **Ce que gagne la quantification.** int8 = **~4× plus petit** que f32 → ~500 Kio, puis compressible. Brotli bat gzip : « Brotli has improved the compression ratio by 20% from that of gzip in the given experiment » (37 553 o gzip → 32 645 o Brotli sur 99 900 caractères). [MESURE — arXiv 2409.15046]. Après int8 + Brotli, un réseau distillé descend plausiblement sous ~150–300 Kio transférés [HYPOTHÈSE].
- **Techniques de chargement.**
  - **Compilation en flux** : `WebAssembly.instantiateStreaming(fetch(...))` compile pendant le téléchargement. [DOCUMENTÉ — MDN, exemples SIMD]
  - **`Content-Encoding: br`** (Brotli) servi par le serveur pour le .wasm et les poids ; zstd émergent.
  - **Chargement différé des poids** hors du bundle critique ; **Cache API / Service Worker** pour ne télécharger qu'une fois (vos poids sont statiques par version).
  - Poids **pré-empaquetés en tuiles int8** hors ligne (ce que vous prévoyez) : téléchargement direct sans transformation au chargement.

---

## Tableau de disponibilité (mécanisme × navigateur)

| Mécanisme | Chrome desktop | Firefox | Safari macOS | Chrome Android | **Safari iOS** | Réserves |
|---|---|---|---|---|---|---|
| **WASM SIMD128** | 91+ ✅ | 89+ ✅ | 16.4+ ✅ | 91+ ✅ | **16.4+ ✅** | Déterministe ; socle sûr. int8 = int16-dot 2-voies seulement |
| **Relaxed-SIMD (dot int8 7 bits)** | 114+ ✅ | 120+ (défaut dès 145) ✅ | ❌ (STP 250 seulement, 13/08/2026) | 114+ ✅ | **❌ Non supporté (≤26.6/TP)** | Non déterministe ; opt-in uniquement |
| **Fils WASM / SharedArrayBuffer** | ✅ (COOP/COEP) | 79+ ✅ | 14.1+ ✅ | ✅ | ✅ (COOP/COEP, WebKit strict) | Casse tiers ; `hwConcurrency`=4 sur iOS |
| **WebGPU (compute)** | 113+ ✅ | 141+/145+ ✅ | 26+ ✅ | 113+ (Android 12+, GPU récents) | **26+ ✅** | Dispatch-bound pour cette charge ; non bit-exact |
| **WGSL packed int8 dot** | 123+ ✅ | polyfill | à vérifier | 123+ ✅ | non garanti | Extension optionnelle non portable |
| **WebNN** | preview (drapeau) | ❌ | ❌ | preview | ❌ | Pas prod ; hors jeu |

Dates de consultation : 26/08/2026 pour toutes les lignes. Sources : caniuse, MDN, web.dev, WebKit blog, Chrome for Developers (voir Details).

## Tableau de débit attendu (charge gammonNet)

**Hypothèse de calcul explicite** : votre banc actuel donne ~9 400 éval/s à 527 000 MACs (1-ply : 7 475 éval / 797 ms ; 2-ply : 12 951 éval / 1 394 ms ; 0-ply : 16 / 1,7 ms), soit ~**5 GMAC/s effectifs** en f32 SIMD128 par ouvrier-agrégat mesuré. On suppose le débit MAC/s constant à ISA égale, et on applique les facteurs de réduction de MACs et de gain int8.

| Configuration | MACs/éval | Facteur vs actuel | Débit estimé (éval/s) | Étiquette |
|---|---|---|---|---|
| **Actuel : 527 k, f32, SIMD128** | 527 000 | 1,0× | **~9 400** | [MESURE — votre banc] |
| Distillé 80 k, f32, SIMD128 | 80 000 | ~6,6× (MACs) | **~60 000** | [HYPOTHÈSE] |
| Distillé 80 k, int8 SIMD128 déterministe (`i32x4.dot_i16x8_s`) | 80 000 | ~6,6× × ~1,3–2× | **~80 000–120 000** | [HYPOTHÈSE] |
| Distillé 80 k, int8 + relaxed-dot 7 bits (Chrome/FF/Android) | 80 000 | ~6,6× × ~2–3× | **~120 000–180 000** | [HYPOTHÈSE — indispo iOS] |
| **Safari iOS (plafond réaliste)** | 80 000 | déterministe seul, hwConcurrency=4, throttling | **~60 000–100 000** puis dégradé sous charge | [HYPOTHÈSE] |

Interprétation : le distillé seul (÷~6,6 MACs) est votre plus gros levier ; l'int8 déterministe ajoute un facteur modéré (surtout bande passante) ; le relaxed-dot ferait le reste mais **jamais sur iOS**, donc ne le mettez pas sur le chemin critique du produit.

## Pourquoi le gain du lot est ×2,21 en WASM contre ×8,5 en natif

Toutes des [HYPOTHÈSE], classées par force d'explication :
1. **Absence de VNNI/FMA exploitable en WASM déterministe.** Le natif x86 batché sature VPDPBUSD (int8 4-voies) et FMA sur 256/512 bits : le lot amortit le chargement des poids ET nourrit des unités très larges, d'où un gain massif. En SIMD128 déterministe vous n'avez que 128 bits et `i32x4.dot_i16x8_s` (2-voies int16), sans FMA (que vous avez de toute façon désactivée pour le déterminisme). Le lot amortit moins car l'unité arithmétique par élément est intrinsèquement plus lente et plus étroite. **C'est l'explication dominante.**
2. **Jeu d'instructions plafonné à 128 bits.** AVX2 = 256 bits, AVX-512 = 512 bits : à effectif de lot égal, le natif traite 2×–4× plus d'éléments par instruction, et le batching, en allongeant les vecteurs contigus, exploite mieux ces largeurs. SIMD128 plafonne le bénéfice.
3. **Qualité de vectorisation LLVM→SIMD128.** L'auto-vectorisation vers wasm est moins agressive/mature que vers AVX2 ; les motifs de réduction (dot) se compilent en séquences plus longues (ex. `smull ; smull2 ; addv`). Le gain de batching dépend de la capacité du compilateur à garder les accumulateurs en registres sur toute la tuile — moins bien réalisé en WASM.
4. **Pression de registres.** Le moteur mappe les v128 sur 16 registres XMM/NEON physiques ; un noyau batché à large tuile déborde plus vite en WASM (spill), ce qui rogne le gain que le natif obtient avec plus de registres (32 en AVX-512, ZMM).
5. **Barrières de sécurité mémoire WASM.** Chaque accès mémoire linéaire peut porter une vérification de borne ; le batching regroupe les accès mais le surcoût relatif de ces barrières reste plus élevé qu'en natif, plafonnant l'accélération.
6. **Régime déjà compute-bound par élément en WASM.** Corollaire de (1)–(2) : comme chaque évaluation unitaire est déjà lente en WASM, la part de coût fixe (appel, mise en cache) que le batching amortit est proportionnellement plus faible → gain de lot plus petit. En natif, l'éval unitaire est si rapide que les coûts fixes dominent, et les amortir donne ×8,5.

**Ce que je ferais mesurer pour trancher** : comparer, sur la *même* machine x86, un build natif SANS VNNI ni FMA (juste SSE2/128 bits) vs votre WASM. Si le gain de lot natif chute alors vers ~2–3×, l'hypothèse (1)+(2) est confirmée : c'est bien la largeur d'ISA et VNNI qui font le ×8,5, pas un défaut de votre code WASM.

## Ce que je ferais mesurer en premier sur nos sept plateformes

Le banc existe déjà (Chromium, Firefox, 2 Android, 2 iPhone). À y ajouter, par ordre de priorité :

1. **Micro-banc GEMM int8 vs f32 en SIMD128**, tuiles réelles du réseau distillé (ex. 512×512→256, 256→128, lots 32/64/256), en isolant : (a) `i32x4.dot_i16x8_s` déterministe, (b) chemin f32x4 actuel, (c) relaxed-dot là où dispo. Reportez éval/s ET MAC/s par plateforme+version. **C'est le chiffre manquant nulle part sur le web** (voir section suivante) — vous seriez la source.
2. **Le même build natif dégradé à 128 bits (SSE2, sans FMA/VNNI)** pour valider l'explication du ×2,21 vs ×8,5 (test décisif ci-dessus).
3. **Courbe de throttling thermique** : éval/s en fonction du temps sur 5–10 min de rollout continu sur les 2 iPhone et 2 Android, avec journalisation du nombre d'ouvriers réellement actifs — pour quantifier la chute (vos 3,3 ouvriers) et décider d'un plafond de fils volontaire.
4. **Coût réel d'un dispatch WebGPU** sur iPhone (iOS 26) et Android : mesurez un aller-retour compute minimal pour confirmer le régime dispatch-bound sur *vos* appareils avant d'écarter définitivement WebGPU.
5. **Poids transférés après int8 + Brotli**, et temps de première évaluation (compilation en flux + chargement différé) sur réseau P75 mobile.
6. **Test bit-à-bit natif↔WASM sur le chemin int8 déterministe** : reproduisez votre écart actuel (4,77e-07) et vérifiez qu'il reste identique après quantification ; marquez explicitement le chemin relaxed-dot comme HORS garantie.

## Ce que je n'ai pas trouvé

- **Aucun banc publié isolant int8 vs f32 pour une GEMM de petite taille (≤512×512) spécifiquement en WebAssembly SIMD128, avec matériel + version de navigateur cités.** Les chiffres int8 5,6× / 2× existent en natif (NEON SDOT, AVX-VNNI) mais pas en WASM. C'est précisément la mesure que votre banc devrait produire.
- **Valeurs éval/s chiffrées et datées de gnubg** (la page « Analyse→Vitesse d'évaluation » liste des CPU mais je n'ai pas récupéré de tableau récent exploitable). Le ~60 knœuds/s de Stockfish WASM NNUE (PR #21) n'a pu être re-confirmé par une source primaire chiffrée récente.
- **Bancs navigateur chiffrés pour KataGo / Leela Zero / lc0 en WASM ou WebGPU** (nodes/s, éval/s) avec matériel + version.
- **Statut précis de `packed_4x8_integer_dot_product` et des subgroups sur Safari iOS 26** (présence côté WebKit non confirmée).
- **Confirmation primaire WebKit** du non-support de relaxed-SIMD en Safari stable au-delà de la table caniuse (la seule primaire trouvée est l'ajout en STP 250 le 13/08/2026) ; caniuse liste encore « TP: Not supported », discordance de fraîcheur à surveiller.
- **Chiffre de latence de dispatch WebGPU mesuré sur un iPhone précis** (les 24–36 µs viennent de GPU desktop/CUDA-comparés ; le 15–25 ms bout-en-bout vient d'un M2, pas d'un iPhone).

## Recommandations

**Étape 1 — Socle (maintenant).** Implémentez le noyau int8 **en SIMD128 déterministe** (`i32x4.dot_i16x8_s`, accumulation i32, i16 là où la dynamique l'exige, ClippedReLU 0..127, échelles en puissances de 2). C'est le seul chemin qui (a) marche sur les sept plateformes dont iOS, (b) préserve votre égalité bit-à-bit. Cible : porter les ~9 400 éval/s actuels vers 60 000–120 000 éval/s via distillation + int8. **Seuil de décision** : si le micro-banc (mesure #1) montre un gain int8 déterministe < 1,3× vs f32, réévaluez si la complexité int8 vaut le coup côté iOS.

**Étape 2 — Accélération opt-in (Chrome/Firefox/Android).** Ajoutez le chemin **relaxed-dot 7 bits** derrière une détection d'exécution, poids bornés à 7 bits, **hors du repère bit-à-bit**. Gain attendu 2–3× là où dispo. **Seuil** : n'activez en production que si le micro-banc confirme > 1,5× vs le chemin déterministe sur ces navigateurs.

**Étape 3 — Threads, prudemment.** Servez COOP/COEP avec **COEP `credentialless`** pour limiter la casse tierce ; auditez d'abord vos dépendances (paiement, auth, analytics, CDN) en mode `report-only`. Plafonnez volontairement les fils à ~grands-cœurs+1 sur mobile (mesure #3) plutôt que de suivre `hardwareConcurrency`. **Seuil** : si la courbe thermique montre un effondrement au-delà de N ouvriers, fixez N comme plafond.

**Étape 4 — WebGPU : ne pas faire, sauf rollouts.** Écartez WebGPU pour l'évaluateur interactif (dispatch-bound). Ne le reconsidérez que si vous portez un jour les rollouts massifs au navigateur avec des lots de plusieurs milliers de positions indépendantes (régime où le dispatch s'amortit) — et alors sans garantie bit-à-bit.

**Étape 5 — Artefact.** int8 + Brotli + compilation en flux + Cache API ; poids hors chemin critique. Cible < 300 Kio transférés.

**Bibliothèques** : gardez votre noyau maison. Repli licence-safe unique = ONNX Runtime Web (MIT). Excluez tout GPL/AGPL (gnubg, Stockfish) du code distribué.

## Caveats

- Tous les débits éval/s projetés sont des **[HYPOTHÈSE]** extrapolées de VOTRE banc (9 400 éval/s à 527 k MACs) ; les facteurs int8/lot doivent être confirmés par la mesure #1.
- La disponibilité relaxed-SIMD sur Safari évolue vite (STP 250 le 13/08/2026) : re-vérifiez avant tout engagement produit ; ne pariez pas sur iOS stable avant plusieurs cycles.
- Le plafond `hardwareConcurrency`=4 sur iOS et la contradiction caniuse (2 vs 4 vs 8) : traitez 4 comme valeur terrain, mais mesurez le parallélisme *utile* réel.
- Les chiffres int8 5,6× / 2× sont **natifs**, non transposables tels quels en WASM SIMD128 128 bits.
- Les mesures WebGPU de latence proviennent de GPU desktop/M2, pas d'iPhone : confirmez sur vos appareils (mesure #4).
- Les blogs secondaires (alldevtoolshub, groundy) affirmant « Relaxed SIMD ships in Safari 18.4+ » sont **contredits par caniuse et par le blog WebKit** (arrivée en STP 250 seulement) ; ne vous y fiez pas.
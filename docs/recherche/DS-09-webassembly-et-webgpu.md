# DS-09 — WebAssembly et WebGPU : ce que le client peut réellement calculer

**Vague** 2 · **Dépend de** DS-04 · **Alimente** DS-14
**Ce qu'elle décide** : si le facteur de vitesse gagné en natif se transporte dans le navigateur —
seul endroit où le produit vit — et jusqu'où le 3-ply devient concevable sur l'appareil.

---

## À injecter avant de lancer — ne pas coller cette section

**Injections faites le 2026-08-27**, depuis le retour DS-04. **Le prompt est prêt à lancer tel
quel.**

| Marqueur | Rempli depuis |
|---|---|
| `ARCHITECTURE` | DS-04, Recommendations : réseau distillé ~60–100k MACs, QAT int8 per-channel, accumulation int32, ClippedReLU, échelles en puissances de 2 |
| `NOYAUX` | DS-04, sous-question 2 : GEMM int8 par lots de 32 sur produit scalaire fusionné ; deux chemins Wasm (SIMD128 déterministe / relaxed-SIMD à poids 7 bits) ; pas d'accumulation incrémentale NNUE |

---

═══════════════════ DÉBUT DU PROMPT — copier à partir d'ici ═══════════════════

Tu m'aides sur **gammonNet**, un évaluateur de positions de backgammon compilé en **WebAssembly**
pour tourner dans le navigateur de l'utilisateur, y compris sur téléphone, et en natif pour les
rollouts. Le produit vit dans le navigateur : le natif ne sert qu'à mesurer et à entraîner.

**Ce que nous avons déjà mesuré**, sur sept plateformes (Chromium, Firefox, deux Android, deux
iPhone) :

| | valeur mesurée |
|---|---|
| Pénalité WebAssembly contre natif | **×1,18 à ×1,29** |
| Décision 0-ply (16 évaluations) | 1,7 ms |
| Décision 1-ply (7 475 évaluations) | 797 ms |
| Décision 2-ply, filtre serré (12 951 évaluations) | 1 394 ms |
| Match de 7 points | ~2 min sur 3,3 ouvriers mesurés |
| Écart au repère natif, sur les sept plateformes | `4,77e-07` — identique partout |

Le gain du calcul par lots, mesuré, est de **×2,21 dans le navigateur** contre ×8,5 en natif :
l'équilibre y est différent, et c'est un fait que je ne sais pas expliquer.

**Le réseau, et ce qui va changer.** Aujourd'hui : 196 entrées denses en `float32`, 512 → 512 →
256 → 128 → 5, ~527 000 MACs par évaluation, noyau par lots de 32. Une étude d'architecture
d'inférence recommande de passer à : **un réseau distillé 2–4× plus étroit (cible 60 000–100 000
MACs), quantifié par entraînement conscient de la quantification (QAT) — poids et activations
int8 per-channel, accumulation int32, accumulateur int16 là où la dynamique des entrées denses
l'exige, activation ClippedReLU (écrêtage 0..127), facteurs d'échelle en puissances de 2 (la
remise à l'échelle devient un simple décalage), poids pré-empaquetés hors ligne en tuiles
adaptées au produit scalaire** — avec des noyaux de la forme : **GEMM int8 par lots de 32 sur
produit scalaire fusionné (VPDPBUSD / AVX-VNNI en natif x86, SDOT sur ARM) ; en WebAssembly,
deux chemins — SIMD128 standard (`i32x4.dot_i16x8_s`, déterministe, pour le bit-à-bit) et
relaxed-SIMD (`i32x4.relaxed_dot_i8x16_i7x16_add_s`, avec poids contraints à 7 bits pour que le
résultat reste défini). Pas d'accumulation incrémentale de type NNUE : l'étude l'a écartée pour
nos entrées denses évaluées par lots.**

## La question

**Quel débit d'inférence est réellement atteignable dans un navigateur pour un réseau de cette
taille, avec quels mécanismes, et lesquels sont disponibles sur les navigateurs qui comptent — y
compris Safari sur iPhone ?**

## Les sous-questions

1. **SIMD dans WebAssembly.** `SIMD128` : disponibilité réelle par navigateur et par version, y
   compris Safari iOS. **Relaxed SIMD** : où en est le déploiement en 2026, quelles instructions
   sont concernées, et en particulier les produits scalaires entiers (`i8x16` / `i16x8` à
   accumulation) qui décident du sort d'un noyau `int8` ? Quel écart de débit est **mesuré** entre
   `f32` et `int8` en WebAssembly pour des produits matriciels de petite taille ?
2. **Les fils.** `SharedArrayBuffer` et les fils WebAssembly demandent les en-têtes d'isolation
   d'origine croisée (COOP/COEP). Quelles en sont les conséquences pratiques pour un site — quelles
   ressources tierces deviennent inutilisables ? Quel parallélisme réel obtient-on sur téléphone,
   sachant que nous mesurons **3,3 ouvriers effectifs** là où l'appareil en annonce davantage ?
   Y a-t-il des chiffres publiés sur la limitation thermique et l'ordonnancement des cœurs
   hétérogènes (grands/petits) sur mobile ?
3. **WebGPU.** Pour une charge comme la nôtre — des lots de 32 à quelques centaines de positions,
   ~500 000 MACs chacune, avec **une dépendance séquentielle entre les niveaux de la recherche** —
   le coût d'un aller-retour de lancement de calcul annule-t-il le gain ? Quels sont les ordres de
   grandeur mesurés de la latence de lancement et du débit atteignable ? WebGPU est-il disponible
   sur Safari iOS en 2026, et sous quelles conditions ? Existe-t-il des retours d'expérience
   publiés sur de **petits** réseaux en WebGPU, par opposition aux grands modèles ?
4. **Ce que font les autres.** Comment les moteurs de jeu compilés pour le navigateur atteignent
   leur débit — Stockfish en WebAssembly, les moteurs de backgammon qui tournent sur le client,
   les moteurs de go. Quels chiffres publient-ils, et quelles techniques citent-ils ? (Attention :
   le code de Stockfish est sous GPL-3 et nous est inutilisable ; ses **mesures**, elles,
   m'intéressent.)
5. **Les bibliothèques d'inférence pour le navigateur** : ONNX Runtime Web, TensorFlow.js
   (backends WASM et WebGPU), et autres. Pour un réseau de 500 000 MACs, leur surcoût par appel
   est-il rédhibitoire par rapport à un noyau écrit à la main ? Y a-t-il des mesures ? Quelles
   licences ?
6. **Le déterminisme.** Nous tenons à ce que le natif et le WebAssembly rendent le même résultat
   **au bit près** — c'est notre garde contre les régressions silencieuses, et nous avons déjà dû
   désactiver la contraction FMA pour l'obtenir. Qu'est-ce qui, dans SIMD128, relaxed SIMD et
   WebGPU, met cette propriété en danger ? Le relaxed SIMD est-il, comme son nom le suggère,
   explicitement non déterministe entre implémentations — et si oui, sur quelles opérations
   précisément ?
7. **La taille de l'artefact.** Notre réseau pèse ~2 Mio en `float32`. Quel est le budget de
   téléchargement raisonnable pour une application web en 2026, et que gagne la quantification sur
   ce poste ? Quelles techniques de chargement progressif sont employées ?

## Contraintes

- **Chiffre, avec le matériel et la version du navigateur.** Un « le SIMD accélère nettement » ne
  m'aide pas. Un « ×3,1 sur un produit 512×512 en int8, Chrome 1xx, Apple M2 » m'aide.
- Toute bibliothèque signalée arrive **avec sa licence**. Nous distribuons l'artefact : le
  copyleft fort est exclu.
- **Safari sur iPhone est une contrainte de premier ordre**, pas une note de bas de page : c'est
  la plateforme la plus limitée que nous devons servir, et nous y mesurons déjà.

## Format du rendu

Un rapport en **français** où :

- Chaque affirmation porte une étiquette : `[MESURE]` (banc publié, matériel et version cités),
  `[DOCUMENTÉ]` (spécification ou tableau de compatibilité), `[HYPOTHÈSE]`.
- Chaque source porte son lien et sa date de consultation.
- **Un tableau de disponibilité** : mécanisme × (Chrome desktop, Firefox, Safari macOS, Chrome
  Android, Safari iOS), avec la version à partir de laquelle c'est disponible et les réserves.
- **Un tableau de débit attendu** pour notre charge, avec l'hypothèse de calcul explicitée.
- Une section **« Ce que je ferais mesurer en premier sur nos sept plateformes »** — nous avons
  déjà le banc, dis-moi quoi y ajouter.
- Une section **« Ce que je n'ai pas trouvé »**.

═══════════════════ FIN DU PROMPT — copier jusqu'ici ═══════════════════

---

## Note interne — ne pas coller

**L'enjeu produit, en une ligne.** Le 2-ply passe aujourd'hui dans le navigateur à ~1,4 s par
décision, avec un filtre agressif. Si DS-04 et DS-09 rendent ensemble un facteur 10, le 2-ply
large devient interactif et le **3-ply sur l'appareil** cesse d'être absurde — ce qui déplacerait
la frontière que `BRIEF.md` §6 pose comme structurante depuis le début du projet.

**L'anomalie à faire expliquer.** Le lot rend ×8,5 en natif et ×2,21 dans le navigateur. Personne
n'a expliqué cet écart dans le dépôt. Si ce retour l'explique — cache, largeur de vecteur,
absence d'AVX2, coût des appels — c'est un gain immédiat, indépendamment du reste.

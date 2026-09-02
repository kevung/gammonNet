# 2026-08-31 — La QAT jugée sur le jeu : la première mesure vraiment comparable

## Le résultat

Corpus de 300 positions (le même protocole que la mesure du 2026-08-04 :
`tools/measure_quantization.py`, `SEED=20260803`), 5 034 décisions non
forcées, arbitrées par le réseau flottant de référence.

| chemin | équité perdue / décision | taux de désaccord | exécuté réellement ? |
|---|---|---|---|
| float16 | **0,000106** | 0,015 % | oui |
| **QAT int8** (ce document) | **0,003114** | 19,1 % | **oui — la première fois** |
| int8, quantification post-entraînement | 0,011234 | 4,92 % | **non** — simulée en float32 |

**La QAT bat la quantification post-entraînement d'un facteur ~3,6**, sur la
métrique qui compte (`PLAN.md`/T31 : le taux de désaccord et l'équité perdue
quand il y a désaccord — pas l'écart de sortie brut, qui ment). Elle reste
loin derrière float16 — attendu, int8 dispose de 8 fois moins de niveaux par
activation.

## Pourquoi ce nombre n'existait pas avant aujourd'hui

Le chiffre que `train_qat_int8.py` imprimait depuis le début de T73 (l'écart
d'équité moyen contre le professeur, sur des positions isolées, sans aucun
classement de coup) n'a **jamais** été comparable au 0,011234 publié le
2026-08-04 — celui-ci EST déjà la bonne métrique (taux de désaccord × équité
perdue), mesurée sur un protocole et un corpus différents. Le script
lui-même le disait (« Ce chiffre NE dit PAS la force ») tout en l'imprimant
juste à côté des repères, ce qui invitait la comparaison qu'il venait de
récuser.

Produire le nombre comparable a demandé, dans l'ordre :

1. **Câbler `gn_gemm_int8.c` dans WebAssembly** et prouver sa parité
   native↔Wasm au bit près (`docs/mesures/2026-08-31-T73-wasm-int8-parite.md`)
   — sans quoi rien ne prouvait que le noyau calculait ce qu'il prétendait.
2. **Corriger la calibration d'échelle** (une par couche, pas une seule
   contaminée par elle-même —
   `docs/mesures/2026-08-31-T73-qat-echelle-diagnostic.md`).
3. **Un décalage PAR CANAL dans le noyau C** (`gn_gemm_int8_relu_pc`) : la
   QAT quantifie les poids par canal, un décalage unique par couche aurait
   jeté exactement la précision que l'entraînement avait appris à garder.
4. **Quantifier l'ENTRÉE pendant l'entraînement**, pas seulement les
   activations entre couches cachées — le noyau déployé n'a aucune entrée
   flottante.
5. **`floor`, pas `round`** dans la simulation d'activation — le noyau
   requantifie par un décalage arithmétique pur (un plancher, délibérément
   sans terme d'arrondi pour rester déterministe), et la QAT simulait un
   arrondi au plus proche. C'était le désaccord dominant : écart moyen
   entraînement/déploiement 0,017 → 0,0021 après ce seul correctif.
6. **Exporter réellement** (`tools/export_qat_int8.py`, format `BGQ8`) et
   **exécuter réellement** (`python/gammonnet/infer_int8.py`, le vrai noyau
   C via `ctypes`, pas une réimplémentation NumPy qui pourrait diverger).
7. **Mesurer avec le même protocole** que la référence
   (`tools/measure_qat_decision_loss.py`), pas une position isolée.

Chacune de ces étapes, sautée, aurait laissé un nombre plausible mais faux —
exactement le mode de défaillance que `CLAUDE.md` règle 2 nomme.

## Ce que ceci ne couvre pas

- **Ni le débit ni la taille d'un modèle int8 réellement déployé n'ont été
  mesurés** — ce document établit la QUALITÉ d'une inférence int8 réelle,
  pas sa vitesse en usage. Le micro-banc GEMM (`bench_gemm_int8.c`) mesure le
  noyau seul, pas ce pipeline d'export.
- **`Int8Network` n'est pas câblée dans `gn_search.c`** : aucune recherche
  expectiminimax ne peut encore choisir un coup avec ce chemin. C'est un
  harnais de mesure, pas un moteur de jeu.
- Le corpus (300 positions, comme la référence du 2026-08-04) reste modeste ;
  un intervalle de confiance n'a pas été calculé ici — à faire avant toute
  décision de déploiement.

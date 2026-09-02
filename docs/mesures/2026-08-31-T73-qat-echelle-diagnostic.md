# 2026-08-31 — QAT : l'échelle d'activation unique se calibrait sur son propre écrêtage

## Le signal de départ

`tools/train_qat_int8.py` rendait un écart d'équité moyen (professeur contre élève,
sur les positions retenues du corpus de distillation) de **0,018984** — nettement
au-dessus des repères imprimés sur la même ligne (0,011234 pour la quantification
post-entraînement, 0,000106 pour float16, mesure du 2026-08-04).

## Le bug trouvé

`calibrate_activation_scale` (une seule échelle, pour tout le tronc) mesurait le
maximum d'activation couche par couche en **rejouant la propagation avant** —
mais chaque `ClippedReLU` du tronc porte encore, à ce moment-là, l'échelle par
défaut du constructeur (1/64, plafond ≈ 2,0), puisque l'appelant ne la remplace
qu'APRÈS calibration. La couche 2 est donc mesurée sur une sortie de couche 1
déjà écrêtée à un plafond arbitraire, et ainsi de suite : l'échelle unique qui en
sort sous-estime systématiquement toute couche plus profonde que celle qui a fixé
le maximum apparent.

Diagnostic (`/tmp/.../diag_qat.py`, réseau embarqué réel, 4096 positions du corpus
de distillation) : la dernière couche cachée (128 neurones) atteint réellement
**52,75** avant quantification ; l'échelle unique alors choisie (2⁻³ = 0,125) ne
couvre que 127 × 0,125 ≈ **15,9** — un facteur **~3,3 de saturation**, dans la
couche la plus proche de la sortie.

## Le correctif

`calibrate_activation_scales` (pluriel) : une échelle **par couche**, calibrée
**séquentiellement** — chaque couche est mesurée sur la sortie RÉELLEMENT vue
par la suivante (écrêtage et arrondi appliqués avant de mesurer la couche
d'après), pas sur un plafond par défaut arbitraire. `python/gammonnet/qat.py`,
`tools/train_qat_int8.py`, `tests/test_qat.py` (nouveau test de non-régression :
une couche aux poids artificiellement élargis doit recevoir une échelle plus
grossière que la précédente, pas la même).

## L'effet mesuré, et sa limite

Ré-entraînement identique par ailleurs (même corpus, même graine, 40 époques,
0,5 min) : écart d'équité moyen **0,018984 → 0,015791** — une amélioration réelle
d'environ 17 %, avec l'échelle de la dernière couche passée de 2⁻³ à 2⁰.

**Ce nombre ne se compare toujours pas à 0,011234 / 0,000106.** Ces deux repères
sont une **perte d'équité par décision** (candidats classés, coup choisi comparé
au meilleur SELON le modèle de référence, `tools/measure_quantization.py`, corpus
de 400 positions / 6831 décisions). Le nombre de `train_qat_int8.py` est un écart
de **régression brute** sur des positions isolées (aucun classement de coups),
d'un corpus et d'une méthode différents — le script le dit lui-même (« Ce chiffre
NE dit PAS la force ») tout en l'imprimant à côté des deux repères, ce qui invite
la comparaison qu'il vient de récuser.

**Obtenir un nombre réellement comparable est bloqué** : `measure_quantization.py`
charge les modèles au format `.bin` du moteur d'inférence C (`Network.load`), et
le chemin d'export du réseau QAT vers ce format — le câblage int8 dans
`gn_infer`/WebAssembly — n'est pas encore construit (même chantier que le point 4
de T73 signalé le 2026-08-31, non commencé).

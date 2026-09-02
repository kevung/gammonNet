# T86 — ce que la surface WebAssembly a coûté, point d'entrée par point d'entrée

**Date** 2026-09-02 · **Machine** poste de bureau (Arch, gcc 15, Emscripten
`/usr/lib/emscripten`, Node v26.8.1, Chromium système) · **Branche**
`feat/t86-surface-wasm`.

Cette fiche ne gagne aucune microseconde ; elle déplace une frontière. Ce qui
se mesure ici est donc un **coût** — les octets ajoutés au `.wasm` — et une
**absence d'effet** — la parité, qui doit rester exactement ce qu'elle était.

## Le repère, et pourquoi il n'est pas celui de PLAN.md

`PLAN.md` cite **92 483 o** en SIMD. Ce chiffre date du 2026-09-02 00:14 et la
cible `wasm` **ne liait plus** depuis : `gn_infer_reference.c` avait pris une
dépendance sur `gn_int8_model.c` (format BGQ8) ajoutée à `SOURCES` mais pas à
`WASM_SOURCES`, et la dernière construction WebAssembly datait d'avant. Le
correctif de lien (premier commit de la branche) porte le module à
**100 262 o** sans qu'aucun point d'entrée de T86 n'y soit pour rien.

Les deux repères sont donc donnés partout : celui de la fiche, et celui à
partir duquel T86 ajoute réellement.

## Le tableau

Mesures SIMD, `-O3`, réassociation flottante, les mêmes drapeaux que
l'artefact publié. Chaque ligne est une **construction complète**, le code du
point d'entrée retiré de `gn_wasm.c` et pas seulement absent de
`EXPORTED_FUNCTIONS` — `EMSCRIPTEN_KEEPALIVE` garde une fonction vivante même
non exportée, et mesurer par la liste d'exports n'aurait rien mesuré du tout
(constaté : quatre listes d'exports différentes, quatre fichiers de la même
taille à l'octet près).

| Étape | `.wasm` SIMD | Δ | Δ cumulé / 100 262 |
|---|---:|---:|---:|
| repère `PLAN.md` (avant le correctif de lien) | 92 483 o | — | — |
| **base T86** (correctif de lien, aucun ajout) | 100 262 o | +7 779 | — |
| étape 1 — le worker relaie la recherche | 100 262 o | **0** | 0,00 % |
| étape 2a — Position ID (encode + décode) | 101 162 o | +900 | +0,90 % |
| étape 2b — XGID (encode + décode) | 107 109 o | +5 947 | +6,83 % |
| étape 2c — compte de pips | 108 628 o | +1 519 | +8,34 % |
| étape 3 — la notation de coup | 109 834 o | +1 206 | **+9,55 %** |

Scalaire, pour mémoire : 89 497 → 98 273 o (+9,81 %).

**Seuil de la fiche : +25 %.** Il n'est pas approché — +9,55 % sur la base
réelle, +18,76 % même en comptant le correctif de lien qui n'appartient pas à
T86.

### Ce que le tableau apprend

- **L'étape 1 ne coûte rien du tout**, et c'est le fait central de la fiche :
  les trois points d'entrée de la recherche étaient **déjà** exportés. Le
  manque était un protocole de worker, c'est-à-dire du JavaScript. Le
  consommateur a réécrit un ordonnanceur, un codec et une notation pour
  contourner un fichier de 80 lignes.
- **Le Position ID est presque gratuit** (+900 o) parce que
  `gn_position_id` / `gn_position_from_id` étaient déjà liés : la recherche
  les appelle à chaque décision. On n'ajoutait que l'enveloppe.
- **Le XGID coûte six fois plus** (+5 947 o, 61 % du total de T86) parce que
  sa paire était éliminée à l'édition de liens, faute d'appelant. C'est le
  seul poste qu'on pourrait retirer si le budget venait à mordre : gammonGo
  écrit ne pas en avoir besoin (son plateau est déjà structuré), et blunderDB
  passe par cgo, pas par ce module. Il est gardé parce que la marge le permet
  et qu'un codec amputé de la moitié de ses formats invite à réécrire l'autre
  moitié — ce que cette fiche corrige précisément.
- **La notation coûte 1 206 o**, soit 1,2 % du module, pour supprimer une
  écriture entière chez un consommateur.

## L'exactitude : rien n'a bougé

| Contrôle | Résultat |
|---|---|
| `wasm-parity` scalaire | max\|Δ\| = **0,000e+0** (2 000 positions × 5 sorties) |
| `wasm-parity` SIMD | max\|Δ\| = **6,407e-7** (seuil T20 : 1e-6) — inchangé |
| `wasm-parity-int8` | 0 désaccord, **au bit près**, sur les deux builds |
| `wasm-api` | 19 invariants, verts |
| `wasm-codec` (nouveau) | 2 050 positions, **égalité exacte**, deux builds |
| `wasm/worker_invariants.mjs` (nouveau) | 13 invariants, verts |
| `pytest tests/` | vert |

Le 6,407e-7 du SIMD est celui d'avant la branche : c'est le prix de la
réassociation flottante, documenté depuis T20, et T86 ne le déplace pas d'un
chiffre.

## Le codec, contre le C et non contre ce qu'il remplace

`make wasm-codec` fige le repère par le **natif** (`tools/dump_codec_reference.py`,
qui contrôle l'aller-retour côté C avant d'écrire quoi que ce soit), puis
compare à l'**égalité exacte** — un identifiant est une chaîne, il n'y a pas de
tolérance à lui accorder.

    corpus T12, 2 050 positions
      dont 400 avec un pion sur la barre, 402 avec des pions sortis,
           1 042 au trait de Noir
    scalaire : encode 0 · décode 0 · xgid 0 · xgid⁻¹ 0 · pips 0
    SIMD     : encode 0 · décode 0 · xgid 0 · xgid⁻¹ 0 · pips 0

**L'écart avec l'écriture TypeScript de gammonGo : 0 position sur 2 050**
(`wasm/codec_vs_gammongo.mjs`, transcription de leur algorithme). Leur codec
déduit était juste ; il n'en reste pas moins qu'il était validé contre ce
module et non contre une référence indépendante. La substitution ne change pas
un seul identifiant.

## La décision de bout en bout, dans un vrai navigateur

Chromium, `wasm/decision.html`, build SIMD, `k = 12`, depuis un Position ID,
**dans un worker, sans une ligne de recherche en JavaScript** :

    2-ply filtre 3/1, élagage k=12
      1 774,9 ms · 15 142 évaluations · sGfwATDgc/ABMA · équité 0,16689869
      coup retenu : « 6/5 8/5 »
      accord natif : même coup, même compte d'évaluations, Δéquité 3,1e-7

Le même calcul sur le thread principal de la même page : 1 687,7 ms (médiane
de trois). Le worker coûte donc ~5 % — la sérialisation d'un message et un
`postMessage` — et ce qu'il rapporte est que la page ne gèle pas.

La notation est celle de `GnPlay.moves`, la liste ordonnée que la recherche a
réellement retenue, et non une reconstruction par différence de plateaux : un
`resultId` seul est ambigu, deux appariements peuvent laisser le même
plateau.

## L'annulation : ce qui est possible, mesuré

    en vol abandonnée   = FAUX   (attendu)
    en file abandonnée  = VRAI
    worker encore chaud = VRAI

Le premier est une **limite de plateforme, constatée et non supposée** : un
appel WASM synchrone n'est pas interruptible depuis JavaScript. Le worker est
mono-thread, donc tant que `_gnw_best_play` s'exécute, `self.onmessage` ne
tourne pas et le message `stop` n'arrive pas. Un drapeau coopératif dans le C
n'y changerait rien — personne ne pourrait le lever. Les deux échappatoires
connues sont écartées, et pour des raisons de fiche :

- **`SharedArrayBuffer`** exige COOP/COEP, que l'hébergeur statique ne donne
  pas — c'est déjà la raison pour laquelle chaque worker recharge ses 1,06 Mo
  de poids ;
- **Asyncify** instrumente tout le module et le fait grossir, ce que le seuil
  de +25 % de cette fiche refuse.

Ce qui est livré à la place vaut ce que `terminate()` coûtait : le worker
**survit** à l'annulation. Un geste dépassé chez le consommateur recharge
aujourd'hui 1,06 Mo de poids (`progressive-eval.ts` : *« Creates a NEW worker
each call »*) ; avec la file et les générations, il ne recharge rien. Et
`progressive: true` ramène l'attente perçue d'une décision superflue de
~2,7 s à ~6 ms, en postant le 0-ply avant d'engager le 2-ply.

## Reproduire

```bash
make wasm            # les deux builds, tailles affichées
make wasm-parity     # réseau, natif ↔ Wasm
make wasm-parity-int8
make wasm-api        # invariants du module ET du protocole de worker
make wasm-codec      # le codec contre le C, égalité exacte
node wasm/codec_vs_gammongo.mjs
node wasm/harness.mjs --browser chromium --mode decision --build simd \
     --page /wasm/decision.html --timeout 1200000
```

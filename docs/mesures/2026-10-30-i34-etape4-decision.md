# 2026-10-30 — Le 768×768 au bout du protocole de #34, et la décision

*Issue #34, étape 4, et la question posée en plus : peut-on le servir aussi vite que le réseau
actuel sans perdre sa force ? Suite de
[`2026-10-27-i34-prob5-elargis-registre.md`](2026-10-27-i34-prob5-elargis-registre.md) (étapes 0
et 2) et de [`2026-10-27-i34-etape3-cout.md`](2026-10-27-i34-etape3-cout.md) (étape 3).*

> **EN COURS DE RÉDACTION.** Les sections marquées « campagne en cours » attendent leurs
> journaux. Les seuils du tête-à-tête cubeful (§1.3) sont écrits ici **avant** toute lecture du
> signe, comme en T98.

---

## 1. Est-il vraiment plus fort ?

### 1.1 Le tête-à-tête 0-ply sans arbitre (étape 1) — *campagne en cours*

`bench/run_round_robin.py --engines gammonnet-0ply,prob5-768x768-0ply --pairs 500000 --seed
20261030`, dés dupliqués, sièges échangés, un million de parties par sens, bootstrap sur les
paires. Le chiffre de l'amont est +9,7 mEq/partie [+8,9 ; +10,6] sur 10 M parties.

### 1.2 Le registre arbitré de T70, sous recherche — rappel des étapes 2 et 3

| comparaison (10 000 décisions money, 2-ply) | Δ apparié [IC 95 %] |
|---|---|
| 768×768 − réseau actuel, sans élagage | **−0,00035** [−0,00044 ; −0,00025] |
| 768×768 − réseau actuel, niveau `normal` servi | **−0,00033** [−0,00044 ; −0,00023] |
| 768×768 `normal` − réseau actuel `normal` `k = 24` (×1,5 de coût) | −0,00017 [−0,00028 ; −0,00005] |
| 768×768 `normal` − réseau actuel `(0,1,3)` `k = 0` (×4,5) | −0,00005 [−0,00017 ; +0,00007] |

Le 768×768 rejoué aujourd'hui au niveau `normal` retrouve **au chiffre près** sa ligne de
l'étape 3 : 0,0025564 [0,00243 ; 0,00268], 249 décisions hors registre, 119 197 460
évaluations.

### 1.3 Le tête-à-tête cubeful au niveau servi — *campagne en cours*

768×768 contre le réseau actuel, **la politique `normal` des deux côtés** (`bench/run_t35.py
--theirs self --ours-policy normal`, qui donne désormais au second joueur la même politique,
seuls les poids diffèrent), `prune_32` des deux côtés, videau 2-ply, dés dupliqués, IC par
bootstrap sur les paires (`bench/report_t35.py`).

**Seuils, écrits avant lecture** (ceux de T98, pour la même question de non-régression) :

- **match** 7 points, scores tirés comme T35, graine 20261030, 35 000 paires : borne basse de la
  MWC du 768×768 **≥ 49,5 %** ;
- **money**, deux journaux indépendants (graines 20261031 et 20261032), 200 000 et 150 000 paires
  visées, lus en commun : borne basse **≥ −0,010 ppg**.

Un intervalle entièrement positif serait en plus un gain **en jeu**, sous recherche, videau et
score compris. Ce n'est pas le critère : le critère est la non-régression.

---

## 2. L'étape 4 du protocole

### 2.1 L'élagueur — **`prune_32` est gardé**, comme en T98

Redistillé du 768×768 par la recette de T98 (`tools/build_prune_corpus.py --count 800000`, puis
`tools/train_prune.py`, trois graines), puis noté sur le registre de T70 au niveau `normal`, le
768×768 comme grand réseau des deux côtés :

| élagage, sur le 768×768 | perte par décision | Δ apparié contre `prune_32` | hors registre |
|---|---|---|---|
| `prune_32` | 0,00256 [0,00243 ; 0,00268] | — | 249 |
| redistillé, graine 1 | 0,00263 | +0,00009 [+0,00001 ; +0,00018] | 277 |
| redistillé, graine 2 | 0,00261 | +0,00006 [−0,00002 ; +0,00015] | 246 |
| redistillé, graine 3 | 0,00260 | +0,00004 [−0,00004 ; +0,00013] | 262 |

**Trois graines sur trois du mauvais côté**, et le même ordre de grandeur qu'en T98. Les
réseaux redistillés et leur provenance sont archivés hors du dépôt ; aucun nouvel artefact,
aucun nouveau nom.

### 2.2 Le float16 — **mesure**

`tools/pack_fp16.py` : 1 069 312 poids en float16, 2 309 biais laissés en float32, 4 286 524 →
2 147 900 octets.

**En jeu, au réglage servi** (registre de T70, `normal`, le 768×768 ET `prune_32` en `.bin16`,
apparié au float32) : **Δ = +0,0000068** [−0,0000008 ; +0,0000176], 23 coups changés sur 9 750.
Indiscernable de zéro, comme sur le réseau actuel (−0,0000049 [−0,000016 ; +0,000006]).

**Position par position** (`bench/measure_fp16.py`, 20 000 positions, graine 20260803, chaque
position résultante de chaque jet) :

| | 768×768 | réseau actuel (fiche float16) |
|---|---|---|
| écart d'équité moyen, positions | 2,69×10⁻⁴ | 1,20×10⁻⁴ |
| maximal, positions | 4,07×10⁻³ | 1,29×10⁻³ |
| maximal, positions résultantes (9 617 222) | 2,02×10⁻² | 8,64×10⁻³ |
| coup différent à 0-ply | **0,058 %** [0,050 ; 0,066] | 0,042 % [0,036 ; 0,050] |
| perte par décision | 2,6×10⁻⁸ | 1,7×10⁻⁸ |

L'arrondi déplace deux fois plus l'équité d'un réseau deux fois plus large, et reste sans
effet mesurable en jeu. `tests/test_fp16.py` borne l'écart maximal sur son petit corpus à 10⁻³ ;
le 768×768 y fait 1,15×10⁻³. La branche d'adoption devra élargir cette borne, sur la foi de la
mesure ci-dessus et non pour faire passer un test.

### 2.3 La parité WebAssembly et les golds — **mesure**

- `make wasm-parity` avec le 768×768 : **max|Δ| = 0** sur les 2 000 positions de référence,
  builds scalaire et SIMD, contre le natif par défaut.
- Sur la branche d'adoption (§5) : `make wasm-parity` (float32 et float16), `make wasm-policy`
  et `make wasm-policy-threads` (1 495 décisions, 0 écart d'action, max|Δ| = 0), `make wasm-api`
  (77 invariants) et `make wasm-codec` passent.

---

## 3. Peut-on le servir aussi vite que le réseau actuel ? — **oui, et le réseau actuel aussi va plus vite**

### 3.1 Le profil : ce que coûte un réseau ×1,9

Le 768×768 fait 1 069 312 multiplications-additions par position contre 560 384 : **×1,908**.
L'étape 3 a chronométré **×1,90**. Le coût suit le compte d'opérations au pour cent près : aucun
effet de cache ni de tuilage propre à la largeur 768 n'est à récupérer. Pour aller plus vite, il
faut faire **moins d'opérations**, pas les faire mieux.

### 3.2 Ce que le réseau calcule pour rien — **mesure**

Les couches cachées sont des ReLU, et la plupart de leurs unités sortent à zéro. Mesuré sur
192 000 positions candidates (corpus d'élagage du 768×768), part des entrées d'une couche qui
ne valent pas zéro, par position et sur un lot de positions voisines :

| couche (768×768) | par position | lot de 16 | lot de 40 |
|---|---|---|---|
| 196 → 768 (entrées) | 14,2 % | 22,4 % | 26,6 % |
| 768 → 768 | 25,7 % | 43,4 % | 51,8 % |
| 768 → 256 | 15,7 % | 30,2 % | 37,8 % |
| 256 → 256 | 21,0 % | 37,3 % | 46,3 % |
| 256 → 256 | 14,0 % | 23,5 % | 29,0 % |
| **opérations utiles, tout le réseau** | 21,2 % | **36,4 %** | 43,9 % |

Le réseau actuel a le même profil (35,0 % par lot de 16). Le noyau ne sautait jusqu'ici que les
entrées nulles de la première couche ; il calculait les 1,07 million d'autres
multiplications-additions même quand elles valaient `w × 0`.

### 3.3 Deux changements de noyau, exacts au bit près

1. **Les unités nulles sortent de la somme suivante** (`src/gn_infer_reference.c`). Après chaque
   ReLU, les colonnes nulles dans toutes les voies vivantes sont compactées en place, et la
   couche suivante ne somme que les autres.
2. **Les poids sont lus en place** (`src/gn_kernel_f32.h`, noyau écrit à la main, donc
   WebAssembly et natif `KERNEL_INTRINSICS=1`). Une copie transposée par tuile, construite au
   chargement, range côte à côte les poids d'une colonne : le noyau n'a plus à les rassembler à
   chaque lot.

**Pourquoi c'est exact.** Une activation de ReLU vaut `+0.0f` ou un nombre positif. Un terme
retiré vaut donc `w × +0`, un zéro signé, et ajouter un zéro signé ne change aucun accumulateur
non nul ; il ne peut que changer le signe d'un accumulateur nul, et la ReLU suivante comme la
sigmoïde l'effacent. L'ordre des termes restants est inchangé. **Vérifié, pas seulement
argumenté** : empreinte des classements de `bench_decision` identique sur les deux réseaux et
tous les builds, `tests/test_batch.py`, `tests/test_kernel.py` et `tests/test_infer.py` verts,
`make wasm-parity` à max|Δ| = 0, et les campagnes de tête-à-tête ont été reprises en cours
de route sur le nouveau noyau sans que leur en-tête (empreinte d'évaluation comprise)
ne change.

### 3.4 Le natif — **mesure**

`build/bench_decision <réseau> 20 models/prune_32.bin 12 --level=normal`, un fil, smith au
repos (campagnes suspendues), trois passes alternées, dispersion sous 0,5 %. Médianes :

| build | réseau actuel | 768×768 | 768×768 / réseau actuel **d'aujourd'hui** |
|---|---|---|---|
| **par défaut, livré aujourd'hui** | **0,349 s** | 0,662 s | ×1,90 |
| par défaut + unités nulles sautées | 0,182 s | 0,336 s | **×0,96** |
| `KERNEL_INTRINSICS=1`, x86-64 de base (SSE2) + poids en place | 0,138 s | 0,250 s | ×0,72 |
| `KERNEL_INTRINSICS=1`, AVX (`-march=native`), ancien noyau | 0,148 s | 0,259 s | — |
| `KERNEL_INTRINSICS=1`, AVX + poids en place | 0,093 s | 0,151 s | ×0,43 |

### 3.5 Le navigateur — **mesure** (ordinateur seulement)

`bench/browser_kernel.mjs --widths 16 --reps 3 --decisions 3`, décision 2-ply `(0,1,3)` `k = 12`
(le protocole de l'étape 3), smith au repos, Chromium 131 et Firefox 140 ESR, trois passes
alternées ; max|Δ| = 0 contre le chemin scalaire à chaque passe. Médianes :

| navigateur | noyau | réseau actuel | 768×768 |
|---|---|---|---|
| Chromium 131 | **livré aujourd'hui** | **0,330 s** | 0,607 s |
| Chromium 131 | unités nulles sautées | 0,230 s | 0,430 s |
| Chromium 131 | + poids en place | 0,206 s | **0,368 s** (×1,11 d'aujourd'hui) |
| Firefox 140 | **livré aujourd'hui** | **0,688 s** | 1,302 s |
| Firefox 140 | unités nulles sautées | 0,384 s | 0,752 s |
| Firefox 140 | + poids en place | 0,205 s | **0,366 s** (×0,53 d'aujourd'hui) |

**Lecture.** Sur le nouveau noyau, le 768×768 coûte dans Chromium **11 % de plus** que le réseau
actuel sur le noyau d'aujourd'hui, et dans Firefox **deux fois moins**. Le rapport entre les deux
réseaux reste, lui, d'environ ×1,8 à noyau égal : l'optimisation profite aux deux.

**Le mobile n'est toujours pas mesuré**, faute d'appareil. Le rapport ×1,8 entre réseaux à noyau
égal est une hypothèse raisonnable pour un téléphone ; le gain du noyau, lui, dépend du moteur
SIMD du navigateur (×1,6 dans Chromium, ×3,4 dans Firefox) et ne se transporte pas.

### 3.6 Les autres pistes, et pourquoi elles s'arrêtent là

- **Distiller le 768×768 dans la forme actuelle — mesuré, sans effet.** *Expérience de mesure
  courte, hors phase 4 : rien de ce qu'elle produit n'est livré.* Le réseau actuel, affiné sur
  8 M positions étiquetées par le 768×768 (`tools/finetune_wide_i34.py`, 6 époques, MSE
  held-out vers le 768×768 de 3,6×10⁻⁵ à 1,6×10⁻⁵), rend au registre de T70 (`normal`)
  0,00292 [0,00278 ; 0,00305] : **Δ = +0,00004** [−0,00005 ; +0,00012] contre le réseau actuel,
  et +0,00036 [+0,00026 ; +0,00047] contre le 768×768. Il se rapproche des sorties du maître sans
  rien prendre de sa force : c'est le plafond de T72, retrouvé par un autre chemin.
- **Élagage plus serré propre au 768×768 — non poursuivi.** Il n'existe pas d'élagueur meilleur
  que `prune_32` (§2.1), et l'étape 3 a mesuré que le gain de `k = 12` à `k = 24` ne vaut que
  0,00015 pour +52 % de budget : le serrer sur le 768×768 rachèterait de la vitesse en payant de
  la force, ce que le noyau donne gratuitement.
- **Recherche mixte (grand réseau aux nœuds qui comptent) — non essayée.** Elle demande deux
  réseaux dans `gn_search` et une mesure à temps égal entière ; le noyau rend le 768×768 aussi
  rapide que le réseau d'aujourd'hui sans rien en retirer, ce qui ôte son objet à cette piste.
- **Parcimonie des poids, int8 — écartés.** Élaguer des poids est un réentraînement (phase 4) ;
  l'int8 reste refusé (T73). Le float16 réduit le transport, pas le calcul (§2.2).

---

## 4. L'épingle et le générateur de coups — mesurés à part

Les poids du 768×768 vivent au commit amont `18b0a80`, les sources compilées à l'épingle
`7184e2f`. **Monter l'épingle ne change rien à ce que le moteur calcule** :

- `tools/scan_movegen.py`, 26 graines × 20 000 positions : **0 désaccord** avec GNU Backgammon
  sur 10 920 000 couples (position, jet), 242 791 638 coups des deux côtés, **0 empreinte sur 26
  qui diffère** entre `7184e2f` et `18b0a80`, aucune liste mêlant deux longueurs de coup ;
- `make build` contre `18b0a80` : empreintes des classements identiques sur les deux réseaux,
  `test_infer`, `test_batch`, `test_kernel`, `test_codec`, `test_search`, `test_policy`
  verts.

**Mais l'épingle ne monte pas avec ce réseau.** À `18b0a80`, `export_weights.py` écrit un autre
format (`BGNV`, version 2, avec le nom de l'encodeur) : chaque `.bin` change d'octets, et avec
lui le format float16 (`BGN6`, dérivé de `BGNN`), les tests d'en-tête et les SHA-256 publiés.
C'est un chantier de format, pas de poids. La branche d'adoption lit donc les poids au commit
`18b0a80` (md5 vérifié) et les exporte par l'`export_weights.py` de l'épingle — le `.bin`
obtenu a exactement le SHA-256 mesuré ici (`d78a54cf…`).

---

## 5. La branche d'adoption — prête, **non fusionnée**

`adoption/i34-768` : nom `strehl-prob5-768-768-256-256-256`, provenance (`weights_commit`),
`THIRD-PARTY.md` et notices (« Copyright (c) 2026 Alex Strehl » pour les poids, l'exception
GPL-3 de l'amont nommée), chemins par défaut, en-tête de test, corpus T12 (mêmes 2 050
positions, 2 037 sorties bougent), corpus de politique régénéré, golds du filtre réenregistrés.

---

## 6. La recommandation — *à compléter avec §1.1 et §1.3*

---

## Reproduire

```
# §1.1
python bench/run_round_robin.py --engines gammonnet-0ply,prob5-768x768-0ply \
    --pairs 500000 --workers 24 --seed 20261030 --out i34-tete-a-tete-0ply.json
# §1.3
python bench/run_t35.py --mode match --match-length 7 --theirs self --ours-policy normal \
    --ours-model models/cubeless_prob5_768_768_256_256_256.bin \
    --theirs-model models/cubeless_prob5_512_512_256_256.bin \
    --seed 20261030 --pairs 35000 --workers 35 --journal i34-h2h-match.jsonl
python bench/run_t35.py --mode money … --seed 20261031 --pairs 200000 --journal i34-h2h-money-a.jsonl
python bench/run_t35.py --mode money … --seed 20261032 --pairs 150000 --journal i34-h2h-money-b.jsonl
# §2.1
python tools/build_prune_corpus.py --count 800000 --workers 16 \
    --model models/cubeless_prob5_768_768_256_256_256.bin --seed 20261030 --out prune_corpus_768.npz
python tools/train_prune.py --corpus prune_corpus_768.npz --seed 2026103{1,2,3} --split-seed 20261030 \
    --teacher models/cubeless_prob5_768_768_256_256_256.bin --out prune_32_768_s{1,2,3}.bin
python bench/measure_t70.py --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model models/cubeless_prob5_768_768_256_256_256.bin --ply 2 --filter 0,1,1 \
    --filter-extra 0,0,2 --filter-threshold 0,0,0.04 --prune-model <élagueur> --prune-k 12 \
    --workers 16 --out … --dump …
python bench/paired_dumps_t70.py <prune_32>.dump.jsonl <redistillé>.dump.jsonl
# §2.2
python tools/pack_fp16.py models/cubeless_prob5_768_768_256_256_256.bin <…>.bin16
python bench/measure_fp16.py --fp32 models/cubeless_prob5_768_768_256_256_256.bin \
    --fp16 <…>.bin16 --positions 20000 --workers 12
# §3.6
python tools/build_prune_corpus.py --count 8000000 --workers 16 \
    --model models/cubeless_prob5_768_768_256_256_256.bin --seed 20261101 --out wide_corpus_8m.npz
python tools/finetune_wide_i34.py --corpus wide_corpus_8m.npz --out i34-ft-512.pt --epochs 6 --lr 1e-4
python tools/export_model.py --model $PWD/i34-ft-512.pt --out i34-ft-512.bin
# §4
seq 0 25 | xargs -P 12 -I{} python tools/scan_movegen.py --positions 20000 \
    --seed $((20260917 + {})) --out s{}.json
```

## Relevés

`i34-e4-*.json` dans ce répertoire : registre (`768-*-normal`, `paire-*`), float16
(`fp16-positions`, `768-fp16-normal`, `paire-fp16`), distillation (`ft512-normal`,
`paire-ft512-*`), natif (`natif`), navigateur (`navigateur`), générateur (`generateur-18b0a80`).
Dumps, élagueurs redistillés, élève affiné et `.bin16` : archivés hors du dépôt
(`gammonNet-attic/t34/etape4/`).

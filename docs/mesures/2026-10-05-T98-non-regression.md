# T98 — Changer de poids sans régression

*2026-10-05, tête-à-tête dépouillé le 2026-10-15 · mochy (Threadripper PRO 3955WX, 16/32) et melbaa (Xeon E5-2683 v3, 14/28) ·
candidat `cubeless_prob5_512_512_256_256` (sha256 `a84ff7b4…cfdd3`), incumbent
`cubeless_prob5_512_512_256_128`*

> **La question, et elle seule.** T96 a établi que le candidat est plus fort en évaluation
> statique. Cette fiche vérifie que rien de ce qui est **servi** ne régresse en changeant de
> poids : la recherche au niveau `normal`, le navigateur, le réseau d'élagage, le videau, le
> match.

---

## 1. Les pions sous recherche, au niveau `normal` servi — **mesure**

`normal` tel qu'il est défini aujourd'hui : triplet `(0,1,1)+(0,0,2)` à 0,04, `k=12`,
`prune_32` des deux côtés. Registre arbitré de T70, **10 000 décisions money**, dumps appariés
(`bench/paired_dumps_t70.py`).

| | perte par décision disputée | hors registre |
|---|---|---|
| 128 + `prune_32` (servi aujourd'hui) | 0,00358 [0,00342 ; 0,00374] | 0,95 % |
| **256 + `prune_32`** | **0,00287** [0,00274 ; 0,00301] | 2,14 % |
| 256 sans élagage | 0,00269 [0,00255 ; 0,00282] | 1,45 % |

**Apparié, 256 − 128 : −0,00067** [−0,00079 ; −0,00055] par décision, z = −10,6, sur 9 774
décisions. Le candidat perd 19 % de moins, au réglage servi. Pas de régression.

Le contrôle : 0,00358 recoupe le 0,00362 du rapport du 2026-10-04 (même niveau, sous-registre
de 9 000 décisions).

Le taux hors registre du candidat (2,14 %) est écarté et non compté zéro. Pour effacer l'écart, il
faudrait que ces décisions coûtent en moyenne ~0,03 chacune, dix fois la perte moyenne : la
même lecture que T96.

## 2. Le réseau d'élagage — **gardé**

`prune_32` est distillé de l'ancien réseau. T96 soupçonnait qu'il avantage l'incumbent. Il a
été redistillé du candidat avec la même recette (`tools/build_prune_corpus.py --count 800000
--workers 32`, puis `tools/train_prune.py`), sur trois graines, puis noté sur le même grand
réseau 256 :

| élagage, sur le 256 | Δ apparié contre `prune_32` | coût contre sans élagage |
|---|---|---|
| `prune_32` (ancien enseignant) | — | +0,00018 [+0,00012 ; +0,00025] |
| redistillé, graine 1 | +0,00008 [−0,00000 ; +0,00017] | +0,00026 [+0,00017 ; +0,00034] |
| redistillé, graine 2 | +0,00006 [−0,00002 ; +0,00014] | +0,00024 [+0,00017 ; +0,00032] |
| redistillé, graine 3 | +0,00012 [+0,00004 ; +0,00020] | +0,00031 [+0,00022 ; +0,00040] |

**Trois graines sur trois sont du mauvais côté.** Le biais que T96 nommait ne se voit pas :
l'ancien réseau d'élagage trie aussi bien les coups du nouveau grand réseau, et même un peu
mieux. **`prune_32` est gardé** : ni nouvel artefact, ni nouveau nom. Le coût de l'élagage sur le
candidat (+0,00018) reste dans l'ordre de celui que T3D publiait (+0,00023).

## 3. Le navigateur — **mesure**

Décision 2-ply `k=12`, noyau `intrin` de largeur 16, médiane de 3×3, passes **alternées**
128/256/128/256 dans la même séance. Seul le ratio est publié : mochy était chargée (7/32).

| navigateur, machine | 128 | 256 | écart |
|---|---|---|---|
| Firefox 156, mochy | 0,6685 s | 0,7230 s | **+8,2 %** |
| Chromium 152, melbaa | 0,7387 s | 0,7909 s | **+7,1 %** |
| Firefox 156, melbaa | 1,2600 s | 1,3554 s | **+7,6 %** |

Même ordre que le natif (+9,0 %, T96) : le noyau écrit à la main ne fige aucune taille de
couche, et le dernier étage de 256 n'y paie rien de plus. **`make wasm-parity` donne
max|Δ| = 0 sur les deux réseaux**, builds scalaire et SIMD, contre le natif par défaut.
Relevé : [`t98-navigateur.json`](t98-navigateur.json).

## 4. Le videau — **mesure partielle, et un instrument qui a bougé**

**Les efficacités ne peuvent pas bouger.** (0,566 / 0,688 / 0,687) sont ajustées par
`bench/fit_efficiency.py` sur la table bilatérale exacte, sans le réseau. Elles ne sont pas
réajustées.

**La comparaison de T34 contre gnubg 0-ply**, rejouée sur **les mêmes 30 000 décisions**
(positions de contact tirées par l'ancien réseau, `--corpus-model`), décision par décision :

| | accord avec gnubg |
|---|---|
| 128 | 0,9229 |
| 256 | 0,9196 |

−0,34 point. Sur les décisions discordantes, gnubg est d'accord avec le 128 seul 523 fois et
avec le 256 seul 422 fois (McNemar z = −3,3). **L'écart est réel, et il ne dit pas lequel a
raison** : gnubg 0-ply n'est pas un arbitre. C'est le tête-à-tête (§5), qui joue le videau, qui
dira s'il coûte quelque chose.

**Un défaut d'instrument, hors sujet ici mais trouvé en route.** Le contrôle ne reproduit pas le
chiffre publié par T34 (0,8134). Le script intact de `main` donne aussi 0,9229. Le banc a changé
depuis le 2026-08-07 (pilotage de gnubg, conventions de videau), pas le réseau. Le chiffre de
T34 n'est plus reproductible tel quel.

## 5. Le tête-à-tête cubeful — **mesure : pas de régression, en match comme en money**

256 contre 128, même `prune_32` `k=12` des deux côtés, 2-ply `(0,1,3)`, videau 2-ply, dés
dupliqués (`bench/run_t35.py --theirs self --theirs-model`). Seuils et volumes écrits dans
`PLAN.md` (T98) **avant** toute lecture du signe :

- **match** (7 points, scores tirés comme T35) : borne basse de la MWC ≥ 49,5 % ; 35 000 paires ;
- **money** : borne basse ≥ −0,010 ppg ; 201 000 paires sur deux journaux indépendants.

IC 95 % par bootstrap sur les paires (`bench/report_t35.py`), jamais sur les parties.

| | volume | 256 contre 128 | seuil | verdict |
|---|---|---|---|---|
| **match** 7 points, mochy, graine 20261005 | 35 000 paires (70 000 matchs) | MWC **50,05 %** [49,81 ; 50,29] | ≥ 49,5 % | **tenu** |
| money, melbaa, graine 20261005 | 120 000 paires | +0,0021 ppg [−0,0062 ; +0,0103] | — | — |
| money, mochy, graine 20261006 | 81 000 paires | +0,0108 ppg [+0,0004 ; +0,0212] | — | — |
| **money en commun** | **201 000 paires** (402 000 parties) | **+0,0056 ppg** [−0,0010 ; +0,0121] | ≥ −0,010 | **tenu** |

**Lecture.** Les deux bornes basses sont au-dessus de leur marge — de 0,31 point en match, de
0,009 ppg en money : **le changement de poids ne fait rien régresser de ce qui est joué**,
videau et score compris. **Aucun gain n'est résolu** pour autant : les deux intervalles
contiennent zéro, et c'est la question posée — la non-régression, pas la force. Le −0,34 point
d'accord avec gnubg sur le videau (§4) ne coûte donc rien de mesurable au jeu.

**Les deux moitiés money sont compatibles** : écart +0,0087 ppg, erreur-type ~0,0068, z ≈ 1,3.
Mises en commun parce qu'elles ne partagent aucun dé : chaque paire tire les siens de
`blake2b(graine | clé | index)`, et sur les 81 000 index communs 545 lignes seulement (0,7 %)
sont identiques entre les deux journaux, toutes des paires nulles et courtes — une rencontre
fortuite, pas des parties jouées deux fois. `report_t35.py` refuse une graine répétée.

**Ce que le volume n'a pas tenu, et pourquoi la conclusion n'en dépend pas.** Le volume money
visait une demi-largeur ≤ 0,005 ppg sur l'écart-type du pilote (1,144 par paire). L'écart-type
réalisé est **1,486** — +30 %, la queue lourde du videau (un écart par paire atteint 64 ppg, un
videau à 64) que 1 000 paires n'avaient pas encore vue. La demi-largeur obtenue est **0,0066**.
Le critère, lui, est la borne basse, et elle est à −0,0010 pour une marge de −0,010. Le match a
tenu son plan (0,474 prévu, 0,460 réalisé, demi-largeur 0,24 point pour 0,25 visé).

**Deux builds.** Les empreintes numériques (256 / 128) diffèrent entre machines : mochy
`c9c11f1c` / `3f5f3c8a`, build par défaut ; melbaa `fa8bb9d4` / `6f4dc735`, build `NATIVE_FP=1`
(les empreintes que la fiche d'adoption de T97 attribue à ce build). Chaque journal est
homogène, et une confrontation jouée sous deux builds est deux échantillons de la même quantité
— l'accord des deux moitiés le confirme. Aucune partie abandonnée à la limite de
tours. Journaux versionnés compressés :
[`t98-h2h-match.jsonl.gz`](t98-h2h-match.jsonl.gz),
[`t98-h2h-money-melbaa.jsonl.gz`](t98-h2h-money-melbaa.jsonl.gz),
[`t98-h2h-money-mochy.jsonl.gz`](t98-h2h-money-mochy.jsonl.gz).

**Rapport avec l'adoption déjà faite.** v1.6.0 a basculé le réseau sur la non-régression de T97
(`2026-10-05-T97-adoption-256.md`) : 2 000 paires de chaque réseau contre gnubg 2-ply, écart
candidat − référence +0,83 point de MWC [−0,70 ; +2,33]. Cette fiche la confirme à **17 fois**
(match) et **100 fois** (money) ce volume, en confrontation directe : la bascule tient, rien n'est à défaire.

## Reproduire

```
python bench/measure_t70.py --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --model models/cubeless_prob5_512_512_256_256.bin --ply 2 \
    --filter 0,1,1 --filter-extra 0,0,2 --filter-threshold 0,0,0.04 \
    --prune-model models/prune_32.bin --prune-k 12 --workers 30 \
    --out t70-256.json --dump t70-256.dump.jsonl
python bench/paired_dumps_t70.py t70-128.dump.jsonl t70-256.dump.jsonl

make build && make wasm          # natif PAR DÉFAUT : la parité bit à bit est contre lui
python tools/dump_reference.py --model models/cubeless_prob5_512_512_256_256.bin
GN_MODEL_BIN=models/cubeless_prob5_512_512_256_256.bin node wasm/parity.mjs
node bench/browser_kernel.mjs --browser firefox --widths 16 --kernels intrin --reps 3 \
    --decisions 3 --models cubeless_prob5_512_512_256_128.bin,cubeless_prob5_512_512_256_256.bin,\
cubeless_prob5_512_512_256_128.bin,cubeless_prob5_512_512_256_256.bin

python bench/compare_cube.py --model models/cubeless_prob5_512_512_256_256.bin \
    --dump t34-256.dump.jsonl --out t34-256.json

python bench/run_t35.py --mode match --theirs self \
    --ours-model models/cubeless_prob5_512_512_256_256.bin \
    --theirs-model models/cubeless_prob5_512_512_256_128.bin \
    --ours-ply 2 --ours-filter 0,1,3 --ours-prune-k 12 --seed 20261005 \
    --pairs 35000 --workers 30 --journal h2h-match.jsonl
python bench/run_t35.py --mode money ... --seed 20261005 --pairs 120000 --journal h2h-money-melbaa.jsonl
python bench/run_t35.py --mode money ... --seed 20261006 --pairs 81000 --journal h2h-money-mochy.jsonl

# dépouillement : la money se lit en commun
gunzip -k docs/mesures/t98-h2h-*.jsonl.gz
python bench/report_t35.py --journal docs/mesures/t98-h2h-match.jsonl
python bench/report_t35.py --journal docs/mesures/t98-h2h-money-melbaa.jsonl \
    --journal docs/mesures/t98-h2h-money-mochy.jsonl
```

Les journaux ont été joués avant le rebase sur v1.6.0, quand le réseau par défaut était encore le
128 : le nom de notre joueur portait alors `@cubeless_prob5_512_512_256_256`, et les dés d'une
paire dérivent des noms. Pour rejouer une paire **au bit près** avec le code d'aujourd'hui, ajouter
`--dice-key-from <journal>` (contrôlé sur trois paires money de mochy : identiques).

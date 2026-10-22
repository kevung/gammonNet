# 2026-10-22 — Ce que le float16 coûte sur le réseau servi

**Question** (issue #32) : que coûtent, en écart d'équité et en choix de coup, les poids de
`strehl-prob5-512-512-256-256` stockés en float16 (`BGN6`, `.bin16`) et reconvertis en float32
au chargement ? **Machine** : mochy, **chargée** (deux mesures concurrentes, charge jusqu'à 61
sur 32 fils) — seuls des fractions, des écarts et des comptes sont rapportés ici, aucune durée.
**Branche** : `t32-fp16`.

Le verdict du 2026-08-04 (`2026-08-04-quantification.md`) portait sur **l'ancien réseau**
(512-512-256-128), à 400 positions et à 0-ply seulement. Il n'avait pas été refait depuis le
changement de poids (T96–T98).

## Le résultat

> **Au réglage servi, le float16 ne coûte rien de mesurable** : Δ apparié
> **−0,0000049** [−0,000016 ; +0,000006] d'équité par décision disputée, sur 9 786 décisions
> arbitrées par rollouts. L'int8 entraîné pour la quantification coûtait **+0,00060** sur le
> même instrument : la borne haute du float16 est cent fois en dessous, et son intervalle
> contient zéro.

| | float32 (`.bin`) | float16 (`.bin16`) |
|---|---|---|
| perte par décision disputée, 2-ply `normal` | 0,00287 [0,00274 ; 0,00301] | 0,00287 [0,00273 ; 0,00300] |
| décisions notées / hors registre | 9 786 / 214 | 9 788 / 212 |
| **Δ apparié (float16 − float32)** | — | **−0,0000049** [−0,000016 ; +0,000006], z = −0,92 |
| décisions où le coup change | — | **32 sur 9 786 (0,33 %)** |
| évaluations du grand réseau / du réseau d'élagage | 118 618 386 / 343 026 504 | ×1,000 / ×1,000 |

Le float32 retrouve exactement le 0,00287 de T98 (`2026-10-05-T98-non-regression.md`, 256 +
`prune_32`) : l'instrument n'a pas bougé.

## Les deux mesures

### 1. La perte en jeu, au réglage servi

`bench/measure_t70.py` sur le registre arbitré de T70 (`docs/corpus/t70/money-10000`, 10 000
décisions money, équités de référence par rollouts), au niveau `normal` tel qu'il est servi :
2-ply, filtre `(0,1,1)` / `(0,0,2)` / `(0,0,0,04)`, élagage `k = 12`. Le côté float16 charge
**les deux** réseaux de la v1.8.0 en `.bin16` — le grand et celui d'élagage —, c'est-à-dire
exactement ce qu'un lecteur du format chargerait. Les deux dumps sont appariés décision par
décision (`bench/paired_dumps_t70.py`, bootstrap 10 000).

Les 214 décisions hors registre ne sont **pas** comptées zéro : elles sont écartées des deux
côtés de l'appariement et rapportées. Elles sont propres au réseau, pas au format (212 contre
214).

### 2. L'écart d'évaluation, position par position

`bench/measure_fp16.py`, corpus de marche aléatoire du projet (graine `20260803`, la même que
le repère de parité), 20 000 positions, à 0-ply. Pour chaque position, et pour **chaque position
résultante** d'un coup légal sur les 21 lancers — celles que la recherche évalue réellement :

| | n | écart d'équité moyen | médian | p99 | p99,9 | **maximal** | écart max sur les 5 sorties |
|---|---|---|---|---|---|---|---|
| positions du corpus | 20 000 | 1,20×10⁻⁴ | 0,96×10⁻⁴ | 4,9×10⁻⁴ | 6,7×10⁻⁴ | **1,29×10⁻³** | 5,7×10⁻⁴ |
| positions résultantes | 9 617 222 | 1,27×10⁻⁴ | 1,00×10⁻⁴ | 5,0×10⁻⁴ | 7,0×10⁻⁴ | **8,64×10⁻³** | 8,1×10⁻³ |

Et le choix du coup, à 0-ply :

| décisions (≥ 2 coups) | coup différent | taux [IC 95 % Wilson] | perte si différent, moyenne / max | **perte par décision** |
|---|---|---|---|---|
| 350 469 | 148 | **0,042 %** [0,036 ; 0,050] | 4,1×10⁻⁵ / 3,0×10⁻⁴ | **1,7×10⁻⁸** |

La perte est jugée par le float32, qui sert ici de vérité.

## Ce que cela confirme, et ce qui a bougé

**L'écart d'évaluation n'est pas la métrique qui coûte.** Le float16 déplace l'équité d'environ
10⁻⁴ en moyenne — autant que sur l'ancien réseau (1,06×10⁻⁴) —, mais il le fait presque
uniformément sur les coups frères : 0,04 % des choix changent à 0-ply, et quand ils changent,
c'est entre deux coups distants de 4×10⁻⁵ en moyenne.

**Le taux de désaccord à 0-ply est plus haut que celui d'août** (0,042 % contre 0,015 %), mais
celui d'août reposait sur **un** désaccord en 6 831 décisions : son intervalle contient le
chiffre d'aujourd'hui. Ce n'est pas une différence établie entre les deux réseaux.

**Le maximum est loin de la queue.** 8,6×10⁻³ d'équité sur une position résultante, quand le
p99,9 est à 7×10⁻⁴ : une poignée de positions — que ce document n'a pas isolées — encaisse un
écart dix fois supérieur au reste. Il ne se voit pas dans le jeu (la perte maximale observée
quand un coup change est 3×10⁻⁴), mais il interdit d'écrire une borne « garantie » plus serrée
que ce maximum (`docs/specs/format-bgn6-spec.md`, §6).

## Ce que ceci ne dit pas

- **Rien sur la vitesse.** Le format transporte : le calcul est le même noyau, sur des float32,
  et les comptes d'évaluations sont identiques (×1,000). Les durées des deux passes T70 ont été
  prises sous charge et ne sont pas rapportées.
- **Rien au-delà du money.** Le contexte match et le videau n'ont pas été mesurés en float16.
  Rien ne suggère qu'ils divergent — l'écart d'évaluation est le même —, mais ce n'est pas une
  mesure.
- **Le corpus de marche aléatoire n'est pas une distribution de parties réelles.** Le maximum
  d'écart est celui de ce corpus ; le registre de T70, lui, est fait de vraies décisions.

## Le coût

Deux passes T70 de 10 000 décisions en parallèle (16 processus chacune), et 20 000 positions
sur 30 processus, sur une même machine saturée, entre 10 h 01 et 10 h 25.

## Reproduire

```
make build && make wasm-parity            # écrit aussi models/…bin16 et build/reference16.bin
python bench/measure_t70.py --registry docs/corpus/t70/money-10000/registre-money.jsonl \
    --ply 2 --filter 0,1,1 --filter-extra 0,0,2 --filter-threshold 0,0,0.04 --prune-k 12 \
    --model models/cubeless_prob5_512_512_256_256.bin --prune-model models/prune_32.bin \
    --workers 16 --label fp32-normal --out fp16-t70-fp32.json --dump fp32.dump.jsonl
python bench/measure_t70.py … --model <réseau>.bin16 --prune-model <élagage>.bin16 \
    --label fp16-normal --out fp16-t70-fp16.json --dump fp16.dump.jsonl
python bench/paired_dumps_t70.py fp32.dump.jsonl fp16.dump.jsonl --out fp16-t70-paire.json
python bench/measure_fp16.py --fp32 models/cubeless_prob5_512_512_256_256.bin \
    --fp16 models/cubeless_prob5_512_512_256_256.bin16 --positions 20000 --workers 30 \
    --out fp16-positions.json
```

Données : `fp16-t70-fp32.json`, `fp16-t70-fp16.json`, `fp16-t70-paire.json`,
`fp16-positions.json`.

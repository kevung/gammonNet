# 2026-10-27 — Les prob5 élargis de l'amont, sous recherche, sur le registre de T70

*Issue #34, étapes 0 et 2 du protocole. smith (2× EPYC 9254), 35 processus, rien d'autre ne
tournait. `alexstrehl/backgammon-ai-engine` à `18b0a80`, licence MIT relue (titulaire
« Alex Strehl »). **L'épingle reste `7184e2f`** : les poids sont lus dans le commit, pas
installés.*

> **Sous recherche 2-ply, le 768×768 est meilleur que le réseau de record, et l'écart ne
> s'explique pas par le registre** : perte par décision **0,00209** [0,00199 ; 0,00221] contre
> **0,00245** [0,00233 ; 0,00257], intervalles disjoints. Appariement décision par décision :
> **Δ = −0,00035** [−0,00044 ; −0,00025], z = −7,0, soit **−14 %**. Le 768-512 gagne aussi, deux
> fois moins (Δ = −0,00022 [−0,00030 ; −0,00014]). Le verdict tient avec l'élagage `k = 12`.
> **Le critère d'arrêt de l'étape 2 n'est pas atteint : le chantier passe à l'étape 3, le coût
> chronométré.** Ce n'est **pas** une décision d'adoption.

---

## Étape 0 — import et parité

| | incumbent | candidat A | candidat B |
|---|---|---|---|
| fichier amont | `cubeless_prob5_512_512_256_256.pt` | `best_models/cubeless_prob5_768_512_256_256_256.pt` | `best_models/experimental/cubeless_prob5_768_768_256_256_256.pt` |
| architecture | [512, 512, 256, 256] | [768, 512, 256, 256, 256] | [768, 768, 256, 256, 256] |
| paramètres (amont) | 561 925 | 809 221 | 1 071 621 |
| md5 amont | `ac95a983` | `bd1a7931`, **vérifié** | `b3fad4eb`, **vérifié** |
| `.bin` exporté (sha256) | `a84ff7b4…` | `41d2208a…` | `d78a54cf…` |

Export par l'`export_weights.py` de l'épingle, sans modification : le format suit
(`NN_MAX_LAYERS = 8`). `tests/test_infer.py` avec `GN_MODEL_PT` / `GN_MODEL_BIN`, **critère et
corpus de T10** : **14 tests passés** pour chacun. Le seul échec est
`test_the_header_says_what_we_expect`, qui fige l'architecture du réseau de record ; c'est son
rôle, comme en T96.

## Étape 2 — le registre arbitré de T70

`bench/measure_t70.py`, registre `docs/corpus/t70/money-10000` (10 000 décisions money,
équités de référence par rollouts), 2-ply, filtre par défaut du banc (le réglage de T96). Les
trois réseaux sont notés **sur la même machine, le même jour, au même réglage**.

**L'instrument d'abord** : l'incumbent rejoué aujourd'hui retrouve **au chiffre près** sa ligne
de T96 — 0,00245 [0,00233 ; 0,00257], 136 décisions hors registre à `k = 0` ; 0,00266, 215 hors
registre à `k = 12`.

| réglage | réseau | perte par décision disputée [IC 95 %] | hors registre |
|---|---|---|---|
| **sans élagage** | incumbent | 0,00245 [0,00233 ; 0,00257] | 136 (1,36 %) |
| **sans élagage** | 768-512 | 0,00222 [0,00210 ; 0,00234] | 153 (1,53 %) |
| **sans élagage** | **768×768** | **0,00209** [0,00199 ; 0,00221] | 171 (1,71 %) |
| `k = 12` | incumbent | 0,00266 [0,00253 ; 0,00279] | 215 (2,15 %) |
| `k = 12` | 768-512 | 0,00248 [0,00236 ; 0,00261] | 227 (2,27 %) |
| `k = 12` | **768×768** | **0,00237** [0,00225 ; 0,00249] | 243 (2,43 %) |

### L'appariement — ce qui conclut

`bench/paired_dumps_t70.py`, Δ = perte(candidat) − perte(incumbent), bootstrap sur les
positions. Une décision hors registre d'un côté est écartée **des deux** et comptée à part.

| réglage | candidat | **Δ apparié** [IC 95 %] | z | appariées | coup différent | écartées |
|---|---|---|---|---|---|---|
| `k = 0` | **768×768** | **−0,00035** [−0,00044 ; −0,00025] | −6,99 | 9 772 | 1 924 | 228 |
| `k = 0` | 768-512 | −0,00022 [−0,00030 ; −0,00014] | −4,94 | 9 794 | 1 685 | 206 |
| `k = 12` | 768×768 | −0,00029 [−0,00039 ; −0,00020] | −5,92 | 9 714 | 1 746 | 286 |
| `k = 12` | 768-512 | −0,00016 [−0,00024 ; −0,00007] | −3,67 | 9 726 | 1 496 | 274 |

Les quatre intervalles sont entièrement négatifs. Le classement est le même aux deux réglages :
768×768, puis 768-512, puis l'incumbent.

### Ce qui flatte les candidats, et de combien

Le registre a été construit sur les coups d'un réseau de la famille de l'incumbent. Les
candidats ont donc plus de décisions hors registre (171 et 153 contre 136), écartées et non
comptées zéro. Pour que les 228 décisions écartées de l'appariement 768×768 effacent l'écart, il
faudrait qu'elles coûtent en moyenne **environ 0,015 d'équité chacune**. C'est six fois la perte
moyenne d'une décision disputée, et trois fois celle de la pire classe (backgame : 0,0047 à
0,0050). **L'écart ne s'explique pas par l'exclusion**, mais la marge est moins confortable
qu'en T96 (0,050).

**Le biais d'élagage joue contre les candidats** : `prune_32` est distillé d'un ancien grand
réseau. C'est pour cela que le verdict est porté par la ligne `k = 0`.

### Par classe de position (`k = 0`)

| classe | incumbent | 768-512 | 768×768 |
|---|---|---|---|
| contact | 0,00251 | 0,00227 | **0,00210** |
| blitz | 0,00224 | 0,00193 | **0,00182** |
| holding | 0,00184 | 0,00180 | **0,00166** |
| race_contact | 0,00212 | 0,00208 | **0,00192** |
| bearoff_contact | 0,00221 | 0,00209 | 0,00209 |
| prime_vs_prime | 0,00329 | 0,00300 | **0,00293** |
| crashed | 0,00223 | **0,00172** | 0,00183 |
| backgame | 0,00502 | **0,00446** | 0,00466 |

Le 768×768 ne perd sur aucune classe. Ce sont des moyennes par classe, sans intervalles ; elles
donnent la forme du gain, pas sa preuve.

## Ce que cette fiche ne dit pas

- **Le coût.** Le banc rapporte des secondes de recherche cumulées : ×1,95 pour le 768×768 et
  ×1,42 pour le 768-512 (`k = 0`). C'est cohérent avec les ×1,8–1,9 et ×1,4 annoncés en amont,
  mais **ce n'est pas une mesure de coût** : la machine portait 35 processus. Le coût natif au
  repos, puis celui du navigateur (ordinateur et mobile), sont l'objet de l'étape 3.
- **La force en jeu.** Un registre mesure la qualité des décisions de pions en money ; ni le
  videau, ni le match, ni un tête-à-tête.
- **L'équivalence à temps égal.** Un réseau ×1,9 doit battre ce qu'on obtiendrait en dépensant
  ce temps en recherche avec le réseau actuel. C'est la question que l'étape 3 doit trancher, et
  c'est elle qui décidera.

## Relevés

- **Notes et appariements** : `i34-{incumbent,c768x512,c768x768}-k{0,12}-t70.json` et
  `i34-paire-*-t70.json`, dans ce répertoire.
- **Dumps décision par décision** (2 Mo chacun) : archivés hors du dépôt
  (`gammonNet-attic/t34/`).
- **Poids** : non versionnés. On les régénère par
  `git -C vendor/backgammon-ai-engine show 18b0a80:<fichier>`, puis l'`export_weights.py` de
  l'épingle.

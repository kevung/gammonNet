# 2026-10-13 — Où passe le temps d'une décision, niveau par niveau

**Nature** : des **mesures**, mochy au repos (charge ~3,5 sur 32 fils, rien d'autre de ce dépôt
ne tournait), un seul processus, réseau servi `cubeless_prob5_512_512_256_256`, élagueur
`prune_32`, money cubeless. Banc : `build/bench_decision ... --level=<nom>` (option ajoutée par
ce travail, même construction de configuration que `gn_policy.c`).

## Les trois niveaux natifs

| Niveau | Décisions | s/décision | Grand réseau / décision | Petit réseau / décision | µs par éval. du grand |
|---|---|---|---|---|---|
| `normal` (2-ply) | 20, médiane de 3 passes | **0,347** [min 0,345 ; max 0,349] | 8 633 | 20 697 | 40 |
| `ply3` | 20, médiane de 3 passes | **6,52** [6,52 ; 6,55] | 135 593 | 277 578 | 48 |
| `ply4` | **3**, une passe | **127,9** | 3 254 403 | 8 028 333 | 39 |

Le chiffre du 4-ply porte sur trois positions : il dit l'ordre de grandeur, pas une moyenne.

## Ce qui borne la décision

Callgrind, niveau `normal`, 4 décisions (marche enregistrée comprise) : **`gn_evaluate_batch`
porte 92,95 % des instructions**, `forward_raw` 2,94 %, la génération de coups 2,06 %,
`memset` 0,86 %, l'encodage 0,28 %. Ce sont des instructions, pas des secondes ; mais le temps
par évaluation du grand réseau est le même à 10 % près aux trois profondeurs, ce qui dit la même
chose par une autre voie : **le temps d'une décision est le nombre d'évaluations du grand réseau
fois ~40 µs.**

Le constat de `2026-08-26-T3A-branchement.md` (« les évaluations du grand réseau ne bornent plus
la décision ») date d'avant les optimisations de T3A et ne tient plus.

## Ce que le code dit, sans mesure

- **Aucun parallélisme** dans `src/` : une décision, quelle que soit sa profondeur, tient sur un
  cœur.
- `tools/serve.py` sérialise **toutes** les requêtes derrière `_ENGINE_LOCK` (#20, justifié :
  l'état global corrompait 85 % des réponses concurrentes). Le service entier tient donc aussi
  sur un cœur.
- L'état global à rendre propre à chaque fil est court : les tampons de lot de
  `gn_infer_reference.c`, les compteurs de `gn_search.c`, la table des jets (initialisée une
  fois), le cache partagé `gn_evalcache_shared` et le compteur de `gn_bearoff.c`.

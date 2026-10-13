# Le filtre de coups en triplet (accepte, extra, seuil)

**Statut** : en vigueur. **Code** : `src/gn_search.h` (`GnSearchConfig`, `GnSearchLevel`,
`gn_search_set_filter`, `gn_search_set_root_stage`), `src/gn_search.c` (`filter_survivors`,
`prune_keep`, `rank_root`). **Liaison
Python** : `python/gammonnet/search.py` (`SearchConfig.filter`, `.filter_extra`,
`.filter_threshold`). **Mesure** : `docs/mesures/2026-10-04-filtre-triplet-t70.md`.

## 1. Ce que le filtre décide

À chaque nœud de profondeur `d ≥ 1`, la recherche classe les coups légaux par une passe
superficielle (0-ply, ou réseau d'élagage puis grand réseau), du meilleur au moins bon. Le
filtre décide combien de ces candidats sont **approfondis**, c'est-à-dire re-notés par la
récursion à la profondeur `d`. Les autres gardent leur équité superficielle et leur rang.

## 2. Le triplet

Pour chaque profondeur `d ∈ [0, GN_MAX_PLY]` :

| Champ C | Champ Python | Nom | Sens |
|---|---|---|---|
| `filter[d]` | `filter[d]` | accepte | les `accepte` premiers sont toujours approfondis |
| `filter_extra[d]` | `filter_extra[d]` | extra | jusqu'à `extra` de plus, dans l'ordre du classement… |
| `filter_threshold[d]` | `filter_threshold[d]` | seuil | …tant que leur équité superficielle est ≥ celle du meilleur moins `seuil` |

Soit `n` le nombre de candidats classés et `e₀ ≥ e₁ ≥ …` leurs équités superficielles :

```
si accepte = 0 et extra = 0 :  approfondis = n                (aucun filtrage)
sinon :
    k ← min(accepte, n)
    tant que k < min(accepte + extra, n) et e_k ≥ e₀ − seuil :  k ← k + 1
    approfondis = k
```

La marche **s'arrête** au premier candidat hors de la bande : le classement étant trié, aucun
suivant n'y est. Avec `accepte = 0` et `extra > 0`, le meilleur est toujours approfondi (il est
dans sa propre bande). Un compte négatif se lit comme zéro.

Le seuil est dans l'échelle sur laquelle le classement trie à ce nœud : équité money cubeless,
équité de match sous `use_match`, cubeful sous `use_cube`. Il n'est jamais remis à l'échelle.

## 3. Compatibilité : le compte d'avant est le cas `extra = 0`

Avec `extra = 0`, la boucle ne s'exécute pas et `seuil` n'est jamais lu : `approfondis =
min(accepte, n)`, ou `n` si `accepte = 0` — exactement le filtre par compte qui précédait le
triplet. Une configuration remise à zéro (`gn_search_config`, `_CSearchConfig()`) est donc
inchangée **au bit près**. Deux preuves le tiennent :

- `tests/test_search_filter.py::test_extra_zero_never_reads_the_threshold` — seuils 0, 0,05 et
  1e9 avec `extra = 0` rendent le classement identique ;
- `tests/test_search_filter.py::test_count_filter_reproduces_the_pre_triplet_gold` — des
  équités figées en hexadécimal, produites par le code d'avant le triplet aux formes par compte
  `(0,1,3)` élaguée à `k = 12` et non élaguée ; les formes y sont écrites en clair, pour qu'un
  réglage de niveau ne puisse pas déplacer la cible de cet or.

## 4. L'élagage ne passe pas sous le filtre

`prune_k` est relevé à `accepte + extra` (le plus que le filtre puisse approfondir) quand il
est plus petit : élaguer sous le filtre chercherait moins de candidats que demandé, sans signe.

## 5. Refus

`gn_search_set_filter(config, d, accepte, extra, seuil)` rend `-1` et ne touche à rien pour une
profondeur hors `[0, GN_MAX_PLY]`, un compte négatif, ou un seuil négatif ou non fini. Un
triplet qui ne peut pas être ce que l'appelant voulait est refusé, jamais rabattu.

## 6. Les niveaux canoniques

`GnSearchLevel` porte le triplet complet ; `data/search_levels.json` l'exporte sous `filter`,
`filter_extra` et `filter_threshold`, aux indices `0..ply`. Un réglage de niveau ne change que
sur une mesure de non-infériorité (registre T70, marge Δ ≤ 0,001 par décision) **et** un gain
de vitesse net ; la fiche de mesure dit lequel a été retenu.

| Niveau | `filter` | `filter_extra` | `filter_threshold` | `prune_k` |
|---|---|---|---|---|
| `instant` | `(0)` | `(0)` | `(0)` | 0 |
| `normal` | `(0, 1, 1)` | `(0, 0, 2)` | `(0, 0, 0.04)` | 12 |
| `thorough` | `(0, 1, 3)` | `(0, 0, 0)` | `(0, 0, 0)` | 0 |
| `ply3` | `(0, 1, 1, 0)` | `(0, 0, 0, 2)` | `(0, 0, 0, 0.04)` | 12 |
| `ply4` | `(0, 1, 1, 1, 0)` | `(0, 0, 0, 0, 2)` | `(0, 0, 0, 0, 0.04)` | 12 |

`ply3` et `ply4` portent en plus une racine étagée (§8) : `root_stage_ply = 2`, triplet
d'étage `(0, 8, 0.16)`. Natifs seulement : la forme WebAssembly (§7) ne sait pas porter
l'étage, et `gnw_search_level` les refuse plutôt que de décrire une autre recherche.

`normal` : à la racine, le meilleur plus jusqu'à 2 autres à moins de 0,04 — contre `(0,1,3)`,
Δ = +0,00007 [+0,00002 ; +0,00012] par décision sur 8 913 décisions money appariées, ×1,10
d'évaluations en moins. Mesuré en money et élagué à `k = 12` seulement : `thorough` garde le
compte, et le seuil n'est pas mesuré au score.

## 7. Les cibles WebAssembly

`gnw_best_play`, `gnw_rank_plays` et `gnw_cube_decide` prennent, après `filter_top` (l'accepte
de la racine) et `filter_inner`, `filter_extra` et `filter_threshold` de la racine ;
`Evaluator` les expose en `filterExtra` et `filterThreshold`, `Evaluator.level()` les porte, et
`gnw_search_level` les rend pour que `wasm/api_invariants.mjs` tienne la copie JavaScript à la
table C. Laissés à 0, rien n'est écrit : la recherche est le filtre par compte. Un triplet
incohérent est refusé (`bestPlay` rend `null`, les autres lèvent).

## 8. La racine étagée (3 et 4 plis)

Une décision de coup à `k` plis approfondit à `k` plis, directement depuis le classement
superficiel, les survivants de `filter[k]`. À 3 et 4 plis chaque candidat approfondi coûte un
sous-arbre entier : les choisir sur un classement 0-ply paie des coups qu'un regard à 2 plis
écarte déjà. L'étage insère ce regard (l'idée de la recherche de GNU Backgammon, réimplémentée
sans son code) :

```
classement superficiel (élagage, puis grand réseau)
→ triplet d'étage (root_stage_filter, _extra, _threshold)
→ ses survivants notés à root_stage_ply plis, triés entre eux
→ filter[k] sur CE classement
→ ses survivants notés à k plis, triés entre eux
```

Chaque candidat garde l'équité de la passe la plus profonde qu'il a atteinte, comme la passe
profonde sans étage laisse la queue 0-ply derrière son préfixe : le classement rendu est les
survivants à `k` plis, puis les autres survivants de l'étage à `root_stage_ply` plis, puis le
reste à 0 pli. La notation de l'étage est celle d'une décision à `root_stage_ply` plis : ses
nœuds intérieurs lisent `filter[1..root_stage_ply − 1]`. L'élagage de la racine garde au moins
`accepte + extra` de l'étage (§4).

**Portée.** Seule la racine d'une décision de coup (`gn_search_plays`, `gn_best_play`, la
politique) est étagée ; les nœuds intérieurs et l'équité avant le jet (`gn_search_equity`,
`gn_search_probs`, donc les décisions de videau) ne lisent jamais ces champs.

**Activation.** L'étage n'agit que si `1 ≤ root_stage_ply < ply`. `root_stage_ply = 0` (ce que
rend `gn_search_config`) et un étage qui n'est pas strictement moins profond que la décision
laissent la recherche sans étage **au bit près** (`tests/test_search_root_stage.py`).

**Refus.** `gn_search_set_root_stage(config, ply, accepte, extra, seuil)` rend `-1` et ne
touche à rien pour un `ply` hors `[0, GN_MAX_PLY − 1]`, un compte négatif, ou un seuil négatif
ou non fini ; `ply = 0` éteint l'étage et remet ses quatre champs à zéro. Côté Python,
`SearchConfig.root_stage_ply` / `.root_stage_filter` passent par cette fonction et lèvent
`ValueError` sur un refus.

**La forme publiée** (niveaux `ply3`, `ply4`, §6) : une seule réplique à chaque nœud intérieur
`(1, 0, 0)`, l'étage à 2 plis au triplet large `(0, 8, 0.16)`, puis `(0, 2, 0.04)` à la
racine, élagué à `k = 12`. Mesure : `docs/mesures/2026-10-11-filtres-3-4-plis.md`.


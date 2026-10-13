# Spec — la recherche sur plusieurs fils, au bit près

**Statut** : implémentée en C (`src/gn_parallel.{h,c}`, `src/gn_search.c`, commits `6051023` et
`c2d681d`), natif et WebAssembly multi-fils. **Ce document s'adresse à toute réimplémentation de
la recherche** dans un autre langage : il dit ce qu'il faut paralléliser, ce qu'il ne faut pas
toucher, et comment prouver qu'on n'a rien changé.

## 1. La propriété, avant la vitesse

> **Un nombre de fils ne change rien à ce que la recherche rend** : ni le classement, ni une
> équité, ni une probabilité, ni le compte d'évaluations (cache éteint).

Elle tient parce que :

1. **le réseau est bit à bit par position**, quel que soit le lot où elle voyage
   (`tests/test_batch.py`) — une position évaluée sur un autre fil, dans un autre lot, rend les
   mêmes bits ;
2. **toute somme se fait dans l'ordre fixe des jets** (`r = 0 … 20`), après que tous les
   sous-arbres ont rendu leur valeur — jamais « au fil de l'arrivée » ;
3. **chaque tâche n'écrit que sa propre case** (la valeur du jet `r`, l'équité du candidat `i`) ;
4. **le cache ne rend que ce que le réseau aurait rendu** : il change le compte d'évaluations,
   jamais une valeur.

Une réimplémentation qui somme dans l'ordre d'achèvement des tâches (un `atomic add` de flottants,
un canal lu au fil de l'eau) **perd la propriété** : l'addition flottante n'est pas associative.
C'est le piège principal.

## 2. Ce qui se parallélise — quatre boucles, une seule forme

Les sous-arbres d'une boucle sont **indépendants** ; on les répartit, on attend, puis on combine
**séquentiellement dans l'ordre**.

| Boucle (`gn_search.c`) | Tâches | Seuil | Combinaison |
|---|---|---|---|
| Nœud de hasard **groupé** (élagage actif), après les deux passes peu profondes groupées : valuation, tri et passe profonde de chaque jet | 21 (un par jet) | `depth ≥ 2` | `Σ_r poids[r] · best[r]` dans l'ordre de `r` |
| Nœud de hasard **non groupé** (sans élagage) : classement complet de chaque jet | 21 | `depth ≥ 2` | idem |
| **Passe profonde** d'un classement (`rank_plays_deepen`) et **étage de racine** (`rank_root`) : l'équité `-V(résultat, depth)` de chaque candidat retenu | n candidats | `depth ≥ 2` et `n > 1` | chaque tâche écrit `out[i].equity` ; le **tri** se fait après, sur le fil appelant |
| **Backups de distribution** (`position_probs`, `probs_by_roll`) : la distribution du meilleur coup de chaque jet | 21 | profondeur des réponses + 1 ≥ 2 | `Σ_r poids[r] · mine[r][k]` dans l'ordre de `r`, en `double` |

**Ce qui ne se parallélise pas** : la passe peu profonde **groupée** des 21 jets (le petit réseau
puis le grand, une seule fois pour tous les survivants). Elle reste séquentielle sur le fil du
nœud : c'est elle qui remplit les lots, et la découper viderait les lots (T3A, remplissage
14,5 % → 80,5 %). Les nœuds de profondeur 1 ne sont pas découpés non plus — vingt et une passes
d'une douzaine d'évaluations : le découpage coûte plus qu'il ne rend (seuil de départ, non encore
optimisé par la mesure).

Les boucles s'emboîtent : un candidat de la racine (tâche) ouvre un nœud de hasard (21 tâches),
dont chaque jet peut ouvrir une passe profonde, etc. Le pool doit donc accepter des **tâches qui
ouvrent des tâches** sans interblocage.

## 3. Le pool — ce que fait celui du C

`gn_parallel_for(n, fn, ctx)` : appelle `fn(ctx, i)` pour chaque `i` de `[0, n)`, rend la main
quand tous ont rendu. Le fil appelant **exécute lui-même** les tâches de son groupe, puis, s'il en
reste en cours ailleurs, **aide** aux tâches en attente des autres groupes au lieu de dormir —
c'est ce qui rend l'emboîtement sans interblocage. Les aides prennent dans le **plus ancien**
groupe ouvert (le plus haut dans l'arbre, donc les plus grosses tâches). Un seul verrou suffit :
une tâche dure au moins la milliseconde.

En Go, la transposition naturelle : un `sync.WaitGroup` par boucle et un sémaphore global de
`GOMAXPROCS` jetons, la tâche s'exécutant **sur le goroutine appelant** quand aucun jeton n'est
libre (sinon un arbre profond épuise les jetons et s'interbloque). Les valeurs vont dans un
tableau indexé par `r` ou `i`, sommé après `Wait()` dans l'ordre.

## 4. L'état qui doit devenir propre à chaque fil

Tout tampon écrit pendant une évaluation ou une génération de coups. En C, il y en avait **sept**,
dont un trouvé seulement par l'empreinte du banc (§5) :

- les tampons du noyau par lots (entrées transposées, deux couches en alternance) ;
- **le tampon de compaction des colonnes d'entrée** — un `static` local, invisible à une
  recherche des variables globales ; il déplaçait 31 évaluations sur 68 260 et changeait des
  coups ;
- les tampons du chemin scalaire, **qui appartenaient au modèle** (deux fils évaluant le même
  réseau les partageaient) ;
- les tampons du chemin int8 ;
- les listes de coups de la génération et du classement ;
- les compteurs d'évaluations (rapatriés au fil qui ouvre la section, cf. `GnCounts`).

Partagés et protégés : le **cache** (un verrou par tranche de seaux — une lecture concurrente
d'une écriture pourrait voir une clé exacte et des probabilités à moitié réécrites) et ses
compteurs (atomiques).

## 5. Comment prouver qu'on n'a rien changé

1. **Une empreinte de tous les classements** (résultat de chaque coup et son équité, au bit, dans
   l'ordre rendu) sur un jeu fixe de décisions réelles, à 1 fil puis à N fils : **égale**. C'est
   `build/bench_decision --threads=n` (« empreinte des classements »). Le compte d'évaluations
   doit être égal aussi, cache éteint.
2. Couvrir chaque chemin : niveau élagué (`normal`), sans élagage (`thorough`), racine étagée
   (`ply3`), distributions, match avec videau, cache allumé (`tests/test_parallel_search.py`).
3. Contre le moteur de référence : la parité de politique (`wasm/policy_parity.mjs --all`) passe à
   `max|Δ| = 0` sur 1 411 décisions avec le module multi-fils à 4 fils.

## 6. Ce que ça rend — mesures

Natif, mochy au repos, réseau 256, mêmes décisions (`docs/mesures/2026-10-13-profil-decision-niveaux.md`) :

| Niveau | 1 fil | 16 fils | 32 fils |
|---|---|---|---|
| `normal` (2-ply) | 0,346 s | 0,037 s (×9,4) | 0,030 s (×11,5) |
| `ply3` | 6,16 s | 0,47 s (×13) | 0,36 s (×17) |
| `ply4` | 127,9 s | 9,08 s (×14) | 7,34 s (×17) |

Ces facteurs sont ceux de **ce** noyau C sur **cette** machine. Une autre implémentation, un
autre ordonnanceur ou un autre processeur se mesurent — ils ne se déduisent pas de ce tableau
(`CLAUDE.md`, règle 3).

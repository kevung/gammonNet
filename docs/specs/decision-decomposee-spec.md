# Spec — une décision découpée en tâches, au bit près

**Statut** : implémentée en C (`src/gn_plan.{h,c}`, les briques de `src/gn_search.{h,c}`, et
`gn_policy_decide_split` dans `src/gn_policy.{h,c}`). Elle est exposée par le module WebAssembly
(`Evaluator.planDecision`, `runTask`, `advance`, `combineDecision`, `EvaluatorPool.decideSplit`)
et par Python (`python/gammonnet/plan.py`). Issue #36.

**Le besoin, dit comme une capacité.** Une décision isolée, comme un coup ou un videau, doit pouvoir
se répartir entre plusieurs **instances mono-fil qui ne partagent aucune mémoire**. C'est le cas,
par exemple, d'un pool de Web Workers qui s'échangent des messages. Le module multi-fils couvre
déjà la mémoire partagée (`recherche-parallele-spec.md`). Il exige une page isolée (en-têtes
COOP/COEP), et un runtime peut ne pas pouvoir l'offrir.

## 1. La garantie

> **Recombinée, une décision découpée rend ce que la même décision rend en un bloc, au bit près**
> — quel que soit l'ordre d'exécution des tâches, et quelle que soit l'instance qui exécute
> chacune.

| Décision | Ce qui est égal au bit |
|---|---|
| `"move"` (`bestPlay`) | `equity`, `resultId`, `notation` ; en natif, le classement entier (`gn_search_plays`) |
| `"cube"` (`cubeDecision`) | `action`, `equityNoDouble`, `equityDouble`, `takePoint`, `probs` |
| `"policy"` (`policy`) | `action`, `resignValue`, `searched`, `equityA`, `equityB`, le coup et le plateau résultant |
| `"position"` (`evaluatePositionAtPly`) | `equity` et `probs` |

**Ce qui n'est pas promis** : le **compte d'évaluations**. Le bloc envoie au réseau, en un seul
lot, les survivants des 21 jets d'un nœud. Une tâche n'envoie que ceux de son jet. Et le cache
d'évaluation est propre à chaque instance. Le total est rendu (`evaluations`), et il a été égal au
bloc sur tous les relevés faits cache éteint (§6). Il n'est pas promis pour autant.

## 2. Pourquoi la garantie tient : par construction, pas par imitation

La recherche en un bloc et la recherche découpée passent par **les mêmes fonctions** :

1. **La racine d'un coup s'écrit en vagues** (`gn_search_root_begin` / `gn_search_root_next`). Une
   vague approfondit un préfixe du classement à une profondeur donnée. Une racine non étagée a une
   seule vague, ou aucune à 0-ply. Une racine étagée (`ply3`, `ply4`) en a deux. `gn_search_plays`
   lui-même parcourt ces vagues (`rank_root`). Les coupes du filtre, les tris et l'ordre des vagues
   sont donc le même code, quel que soit celui qui note les candidats.
2. **Une tâche est un jet d'un nœud de hasard** : la case `r` qu'écrit la boucle du nœud. C'est
   `best[r]` de la récursion d'équité, ou `mine[r]` du backup de distribution. Elle est calculée par
   les fonctions que le nœud appelle pour cette case (`roll_equity`, `grouped_roll_slot`,
   `roll_probs`), et non par une copie de celles-ci.
3. **La recombinaison est la somme du nœud lui-même**, dans l'ordre fixe des jets `r = 0 … 20` :
   `chance_sum` pour l'équité, `chance_probs` pour la distribution (somme en `double`, un seul
   arrondi en `float`). Le négatif d'un candidat est celui de `deepen_one`.
4. **La politique s'exécute deux fois avec les mêmes lignes** (`gn_policy_decide_split`). Une
   décision ne demande qu'une recherche au plus : le meilleur coup, ou la distribution avant le
   jet. Au premier appel, la politique enregistre la recherche dont elle a besoin et s'arrête. Une
   fois cette recherche menée en tâches, elle est rejouée avec la réponse. Les raccourcis (un seul
   coup légal, une perte certaine, un videau que le joueur ne peut pas tourner) concluent dès le
   premier appel, sans aucune tâche.

**Le seul pas qui n'est pas littéralement partagé** est la passe peu profonde d'un nœud groupé
(élagage actif). Le bloc envoie ensemble au grand réseau les survivants des 21 jets, une tâche
n'envoie que ceux de son jet. L'égalité repose ici sur la propriété sur laquelle le groupement
lui-même repose déjà : `gn_evaluate_batch` rend les mêmes bits pour une position, quels que soient
ses voisins de lot (`gn_infer.h`, `tests/test_batch.py`). Les contrôles de parité (§6) la
vérifient.

## 3. Le déroulement

```
planDecision(kind, positionId, turn, d1, d2, options) → { done, plan, stage }   // planificateur
runTask(tâche)                                        → résultat                // n'importe quelle instance
advance(plan, résultats)                              → { done, plan, stage }   // n'importe quelle instance
combineDecision(plan)                                 → la décision             // n'importe quelle instance
```

- **`planDecision`** fait ce qui est bon marché et doit être classé d'abord : la passe de la petite
  puis du grand réseau à la racine, le raccourci d'une politique, une évaluation à 0-ply. Puis il
  émet la première vague. À 0-ply, et pour tout raccourci, le plan est conclu sans aucune tâche.
- **`advance`** prend **exactement un résultat par tâche** de la vague courante, dans n'importe
  quel ordre. Il refuse un résultat manquant, un doublon, un résultat d'une autre vague ou d'un
  autre plan (clé de vague), ou un plan déjà conclu.
- **Aucun état n'est gardé** dans une instance entre deux appels : le plan entre et ressort en
  octets. Le planificateur, l'exécutant, celui qui fait avancer et celui qui conclut peuvent être
  quatre instances différentes.

## 4. Ce que porte une tâche

Une tâche fait **256 octets**, avec un encodage explicite en petit-boutiste, versionné
(`GN_PLAN_VERSION = 1`) :

| Champ | Rôle |
|---|---|
| magique `GNDT`, version | refuser un format inconnu |
| empreintes : réseau, élagueur, table de fin de partie | FNV-1a 64 bits sur leurs octets ; 0 = absent |
| clé de vague | lier le résultat à sa vague et à son plan |
| indice | la case que le résultat remplit |
| configuration de la décision | profondeur, filtres en triplet, étage de racine, `k` d'élagage, état de match, possession et efficacité du videau pour les feuilles cubeful |
| la tâche | genre, position du nœud, profondeur, score et possession vus du joueur au trait, jet `r` |

Il y a trois genres de tâche :

- `GN_TASK_ROLL_EQUITY` : `best[r]` de `V(pos, depth)` ;
- `GN_TASK_ROLL_PROBS` : `mine[r]` du backup de distribution ;
- `GN_TASK_NODE_EQUITY` : `V(pos, depth)` entier, pour une vague trop peu profonde pour valoir
  21 tâches (profondeur 1, sous le seuil `PARALLEL_MIN_DEPTH` que les fils utilisent pour la même
  boucle).

**Le refus.** Une instance dont les empreintes diffèrent de celles de la tâche **refuse** de
l'exécuter (`-2`) : autre réseau, autre élagueur, ou autre table. Une réponse calculée avec
d'autres poids serait plausible, et se recombinerait sans bruit en une décision qu'aucune instance
n'a prise. Le cache n'entre pas dans l'empreinte, puisqu'il ne change aucun résultat. La table
d'équité de match non plus : le module WebAssembly n'a que la table compilée. En natif, une table
remplacée (`gn_met`) doit être la même sur toutes les instances, et c'est à l'appelant de le
garantir.

Un **résultat** revient sous la forme `{ index, key: [basse, haute], value, probs[5], evaluations }`.
Tous ces nombres sont exacts en double : la clé de vague est coupée en deux moitiés de 32 bits, et
les probabilités sont des `float`.

## 5. Combien de tâches

Ce sont des **comptes, pas des temps**, relevés par `wasm/decision_parity.mjs` sur le corpus de la
politique (1 411 décisions) et sur les 2 050 positions de T12. Les chiffres sont dans le
commentaire de l'issue #36 et dans le relevé du contrôle.

| Décision | Tâches |
|---|---|
| `instant`, et tout raccourci | 0 : conclu à la planification |
| coup `normal` (triplet `(0,1,1)+(0,0,2)` à 0,04, `k=12`) | 21 par candidat retenu, de 1 à 3 candidats : 21, 42 ou 63 |
| coup `thorough` (`(0,1,3)`, sans élagage) | jusqu'à 63 |
| videau, politique avant le jet, à ply ≥ 1 | 21 |
| position avant le jet (`"position"`) | 42 : 21 pour l'équité, 21 pour la distribution |
| coup à 1-ply | une tâche par candidat (le nœud entier) |
| racine étagée (`ply3`, natif) | deux vagues |

## 6. Comment prouver qu'on n'a rien changé

1. **`tests/test_plan.py`** (natif) : coups à 1-ply, `normal`, `thorough`, racine étagée `ply3`,
   match avec feuilles cubeful ; la valeur avant le jet ; le videau ; la politique aux trois
   niveaux ; avec la table exacte bilatérale. Les tâches sont exécutées depuis leurs octets, dans
   un ordre mélangé. On compare les bits (`struct.pack`), sans aucune tolérance. Les refus sont
   vérifiés aussi : autre empreinte, élagueur absent, résultat manquant, doublon, vague d'un autre
   plan, plan conclu.
2. **`wasm/decision_parity.mjs`** (module WebAssembly) : le corpus de la politique à ses niveaux
   (politique, coup, videau, position avant le jet, cubeless et cubeful), puis
   `--corpus t12`. Les tâches tournent sur une **autre instance** que le planificateur, dans un
   ordre mélangé, et chaque plan, tâche et résultat passe par `structuredClone`. On compare avec
   `Object.is` sur chaque nombre. Toute différence fait échouer le contrôle.
3. **`wasm/worker_invariants.mjs`** : la décision découpée traverse le protocole de worker
   (quatre messages sans état). **`wasm/pool_invariants.mjs`** : `decideSplit` distribue chaque
   tâche une fois, et chaque vague arrive entière à `advance`.
4. Le bloc lui-même n'a pas bougé : la racine réécrite en vagues passe les tests de recherche
   existants (`tests/test_search*.py`, `test_parallel_search.py`, `test_policy.py`), dont la
   non-régression T12.

## 7. Ce qui n'est pas mesuré

- **Aucun temps.** Le gain de répartir une décision sur N workers dépend du coût d'une tâche
  (de l'ordre de la vingtième partie d'une décision 2-ply), de celui d'un `postMessage` et du
  clonage, de l'oisiveté en fin de vague, et du planificateur qui reste séquentiel. Rien de tout
  cela n'est chronométré ici (`CLAUDE.md`, règle 3). La forme `tasksPerMessage` du pool est un
  défaut de départ.
- **Le module multi-fils** exécute une tâche comme le module mono-fil, au bit près, puisque c'est
  le même code. Mélanger les deux dans un même pool n'a pas été exercé.

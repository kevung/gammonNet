# T87 — l'oisiveté d'un pool, relevée avant d'être corrigée : le remède ne passe pas le seuil dans le navigateur, et le passe en Python

**Date** 2026-09-02 · **Machine** poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3,
**8 cœurs physiques / 16 fils**), 14,4 Gio, Linux 7.1.9 · **Navigateur** Chromium
système, headless, profil neuf, build SIMD · **Branche** `feat/t87-ordonnancement`

> **Ce que la fiche demandait** : instrumenter l'oisiveté du pool dans un
> navigateur sur un match complet, avant de la corriger ; mesurer le nombre
> utile de workers sur au moins deux machines de classes différentes ; et ne
> rien livrer dont le gain reste sous **5 % du temps mural d'un match**.
>
> **Ce que la mesure répond, en quatre points.**
>
> 1. L'oisiveté du chemin qui coûte — celui des décisions — vaut **2,5 à 2,6 %**
>    sans qu'on touche à rien, parce qu'il présente déjà 139 tâches pour 8
>    workers. Le maximum qu'un ordonnancement PARFAIT y gagnerait est **2,6 %**,
>    et le tri autorisé par la fiche **1,2 %**. Le poste est **sous le seuil
>    d'abandon par construction, pas par malchance** : il n'est pas livré.
> 2. Sur l'autre chemin, celui des lots, multiplier les tâches fait bien tomber
>    l'oisiveté de 17,6 % à 7,2 % — **et allonge le travail de 50 %**, parce
>    qu'une tâche y coûte 250 Ko à transmettre. D'où la règle dans sa forme
>    utile : *le nombre de tâches paie quand une tâche coûte cher à calculer et
>    rien à transmettre.*
> 3. **En Python, où cette condition est remplie, la même règle rend +6,1 %**,
>    reproductible sur trois exécutions. C'est la seule des deux applications
>    qui franchit le seuil, et c'est celle-là qui est livrée.
> 4. Le nombre utile de workers est **`min(fils annoncés, 8)`**, mesuré sur
>    quatre configurations ; passer de 8 à 16 achète 3,7 à 6,2 % de temps mural
>    pour **deux fois** plus de mémoire et de secondes-worker. Une seule machine
>    m'était accessible pour le chemin des décisions, et le §5 le dit sans le
>    maquiller.

## Conditions — la machine n'était pas au repos, et il faut le dire

Deux autres chantiers (T84/T85) tournaient sur la même machine pendant toute la
séance. La charge moyenne a varié entre **1,8 et 7,6** hors nos propres workers.

**Le plancher de bruit, constaté et non supposé.** Le même travail — 139
décisions à 8 workers, code identique, empreinte de résultat identique — a
mis **70,5 s** à 21 h 44 et **48,6 s** à 21 h 48 : **±45 %** sur le temps
absolu, à quatre minutes d'intervalle.

**Conséquence appliquée partout dans ce document** : aucun chiffre absolu n'est
comparé à un autre chiffre absolu pris à un autre moment. Les granularités sont
mises en concurrence **dans la même passe**, et l'oisiveté — qui est un
**rapport** — est ce qui se transporte. Elle vaut 2,62 % dans le relevé lent et
2,48 % dans le relevé rapide : le rapport tient, le temps non.

---

## 0. L'instrument, et pourquoi il relève DEUX occupations

`ScheduleReport` (`wasm/pool.mjs`) relève, pour chaque tâche, son worker et ses
deux dates. Il en tire deux occupations :

| | ce qu'elle compte |
|---|---|
| `busyMs` | vue du **pool** : de l'envoi du message à la réponse — sérialisation et deux traversées de `postMessage` comprises |
| `computeMs` | vue du **worker** : le temps réellement passé dans le WASM, que le worker rapporte lui-même |

Les confondre ferait passer une latence de messagerie pour du travail et
**sous-estimerait l'oisiveté**. L'écart entre les deux est publié comme tel — et
il se révélera être le fait central de la section 2.

Le corpus est un **match complet** : les 139 décisions de coup de `test.sgf`
(HSBT Paris 2023, 7 points, joué par des humains), au score et au videau réels
de chaque décision, réduites à ce qu'une décision demande
(`docs/corpus/t87-match-7pts.json`, dérivé du relevé T3C). Configuration :
niveau « normal » — 2-ply, filtre `(0,1,3)`, élagage `k = 12`, recherche
cubeless au score.

**L'empreinte des réponses est relevée à chaque passage** — la concaténation
des coups retenus et de leurs identifiants. Elle vaut `5b43a926` sur tous les
relevés de ce document, et le total d'évaluations vaut **1 851 884** partout :
aucun des réglages essayés ne déplace un seul coup annoncé.

---

## 1. L'oisiveté relevée : 2,6 % là où ça coûte, 17,6 % là où ça ne coûte pas

Un seul passage, 8 workers, les deux chemins du pool l'un après l'autre :

| chemin | tâches | mural | oisiveté (pool) | oisiveté (worker) | tâche min / méd / max |
|---|---:|---:|---:|---:|---|
| **`decide`** — 139 décisions | 139 | 70 490 ms | **2,62 %** | 2,66 % | 1 335 / 3 784 / 8 474 ms |
| **`analyze`** — 2 000 positions | 8 | 213 ms | **23,87 %** | 29,18 % | 88 / 160 / 211 ms |

**La règle de la fiche est vérifiée, dans une seule passe et sur un seul
pool.** La seule différence entre les deux lignes est le **nombre de tâches** :
`decide` en présente 139 pour 8 workers, `analyze` exactement 8. Le premier
absorbe l'aléa, le second ne peut pas — celui qui a fini n'a rien à prendre.

**Et le découpage d'`analyze` est PARFAIT.** 2 000 positions sur 8 workers font
huit tâches de 250, et chaque position coûte la même passe avant. Le
déséquilibre relevé (88 ms contre 211 ms pour un travail identique) ne vient
donc pas du découpage : il vient de l'**ordonnanceur du système**. Un
navigateur ne possède pas la machine.

---

## 2. Le correctif fait ce qu'on lui demande, et il coûte plus qu'il ne rapporte

Six granularités, **8 workers, sept passes entrelacées dans la même minute**,
médiane retenue. *(La ligne « 1 » lit 17,6 % d'oisiveté là où le relevé de la
section 1 lisait 23,9 % : ce sont deux moments différents d'une machine qui
dérive. C'est ce tableau-ci qui fait foi, puisque ses six lignes ont été prises
dans la même minute ; celui de la section 1 n'a d'autre rôle que d'opposer les
deux chemins l'un à l'autre.)*

| tâches/worker | tâches | mural médian | oisiveté (pool) | oisiveté (worker) | tâche min/max |
|---:|---:|---:|---:|---:|---|
| **1** *(défaut)* | 8 | **70,3 ms** | 17,60 % | 22,21 % | 51 / 63 ms |
| 2 | 16 | 75,4 ms | 17,19 % | 28,42 % | 25 / 37 ms |
| 4 | 32 | 82,0 ms | 11,22 % | 33,31 % | 14 / 21 ms |
| 8 | 63 | 106,3 ms | **7,16 %** | 54,63 % | 5 / 19 ms |
| 16 | 63 | 104,5 ms | 8,15 % | 54,22 % | 7 / 15 ms |
| 32 | 63 | 109,9 ms | 8,66 % | 53,14 % | 8 / 15 ms |

Écart au repère natif : `6,4e-7` à toutes les lignes — inchangé, c'est le prix
connu de la réassociation flottante.

**L'oisiveté tombe de 17,6 % à 7,2 %. Le travail met 50 % de temps en plus.**

La colonne qui explique est la quatrième : l'oisiveté **vue du worker** monte de
22 % à 55 % pendant que celle vue du pool descend. Autrement dit, le pool tient
ses workers occupés — mais de plus en plus à **attendre des messages** plutôt
qu'à calculer. Sur ce chemin une tâche coûte cher à *transmettre* : 250
positions de caractéristiques font 250 Ko clonés par `postMessage`, et c'est le
**fil principal**, seul et non parallèle, qui paie chaque clonage. Multiplier
les tâches déplace le goulot du pool vers lui.

> ### La règle, dans la forme qui sert
>
> **Le nombre de tâches paie quand une tâche coûte cher à CALCULER et rien à
> TRANSMETTRE.**
>
> `decide()` est ce cas — 1,8 s de recherche pour un message de soixante
> octets — et son oisiveté vaut 2,5 % sans qu'on ait rien à faire.
> `analyze()` est le cas inverse, et y multiplier les tâches est une perte
> mesurée de 50 %.
>
> La formulation d'origine — « le nombre de tâches, pas le tri » — reste
> vraie ; elle est simplement incomplète, et l'incomplétude coûte 50 % quand
> on l'applique au mauvais chemin.

**Le défaut reste donc une tâche par worker**, et le réglage `tasksPerWorker`
est exposé, documenté avec cette courbe, pour qui mesurerait autre chose sur son
appareil. Un défaut à 4 aurait été une conviction contredite par le relevé de sa
propre fiche.

---

## 3. Le tri : ce qu'il pourrait rapporter, borné par le haut

La fiche autorise un tri à condition que sa clé soit le **nombre
d'évaluations** — déterministe et portable — et jamais un temps mesuré. Le
relevé porte les trois grandeurs pour les 139 décisions : le nombre
d'évaluations rendu par la recherche, le nombre de coups légaux, et le temps
réellement mis.

| | min | médiane | max |
|---|---:|---:|---:|
| temps d'une décision | 1 335 ms | 3 784 ms | 8 474 ms |
| évaluations | 5 379 | 13 868 | 16 593 |
| coups légaux | 2 | 18 | 153 |
| **ms par évaluation** | 0,173 | 0,295 | **0,524** |

**Corrélations** : temps ↔ évaluations **0,511** ; temps ↔ coups légaux
**0,228** ; évaluations ↔ coups légaux 0,259.

La clé que la fiche autorise n'explique donc que la moitié de la variance : le
coût d'une évaluation varie lui-même d'un facteur **trois** selon la position
(remplissage des lots, cache, contention). Mais le point décisif n'est pas là.

**La simulation, coûts réels rejoués sur 8 workers** (ordonnancement glouton,
la borne basse étant la somme des coûts divisée par le nombre de workers) :

| ordre | temps de fin | gain contre l'ordre du match |
|---|---:|---:|
| borne basse théorique (somme ÷ 8) | 68 615 ms | — |
| **ordre du match** (ce que le pool fait) | 70 466 ms | — |
| tri décroissant par **nombre d'évaluations** | 69 631 ms | **1,18 %** |
| tri décroissant par **coups légaux** | 69 442 ms | 1,45 % |
| tri décroissant par **temps réel** *(oracle impossible)* | 69 559 ms | 1,29 % |

> **Aucun ordonnancement, même omniscient, ne peut gagner plus de 2,63 %** —
> c'est l'écart entre l'ordre actuel et la borne basse. Le tri autorisé par la
> fiche en récupère **1,2 %**.
>
> Le seuil d'abandon est de 5 % du temps mural d'un match. **Le tri n'est pas
> livré, et il ne l'est pas parce qu'il ne peut pas l'être** : la marge
> n'existe pas.

L'oracle fait *moins bien* que le tri par coups légaux, ce qui n'est pas une
erreur : le glouton n'est pas optimal, et à ce niveau de marge les trois ordres
sont indiscernables du bruit.


---

## 4. Le nombre utile de workers — et il n'est pas celui que le navigateur annonce

### 4.1 Le chemin des décisions, sur un match complet

Balayage complet, 139 décisions à chaque ligne, **une seule passe par point**,
pendant que la charge de fond montait de 3 à 20 :

| workers | mural | accélération | oisiveté | **secondes-worker dépensées** |
|---:|---:|---:|---:|---:|
| 1 | 211,6 s | ×1,00 | 0,00 % | 211,6 |
| 2 | 125,1 s | ×1,69 | 0,67 % | 248,4 |
| 4 | 87,3 s | ×2,43 | 1,53 % | 343,6 |
| 6 | 58,9 s | ×3,59 | 2,60 % | 344,3 |
| **8** | **50,4 s** | **×4,20** | 3,18 % | 390,4 |
| 12 | 63,4 s | ×3,34 | 2,63 % | 740,9 |
| 16 | 47,3 s | ×4,47 | 3,35 % | 731,1 |

Le point à 12 est manifestement pollué (il est plus lent que 8 *et* que 16).
Les trois points du plateau ont donc été **rejoués sur une machine plus calme**,
dans une seule passe, avec 8 et 16 répétés :

| workers | mural | oisiveté | secondes-worker |
|---:|---:|---:|---:|
| 6 | 48,7 s | 2,16 % | 285,8 |
| 8 | 41,7 s | 3,01 % | 323,6 |
| 12 | 43,0 s | 2,67 % | 501,7 |
| 16 | 41,5 s | 3,33 % | 641,9 |
| 8 *(bis)* | 44,6 s | 2,76 % | 346,7 |
| 16 *(bis)* | 41,6 s | 3,15 % | 644,2 |

**Empreinte `5b43a926` et 1 851 884 évaluations à TOUTES les lignes des deux
tableaux.** Le travail est rigoureusement le même ; seul le nombre de workers
change.

> ### Ce que la dernière colonne dit, et qui ne se voyait pas
>
> **Le même travail coûte 211,6 secondes-worker à un worker, 390 à huit et 731
> à seize.** Chaque worker ajouté ralentit tous les autres : à seize, une
> évaluation coûte **3,5 fois** ce qu'elle coûte seule. C'est la contention de
> bande passante que T23 avait diagnostiquée sans pouvoir la chiffrer — chaque
> worker relit sa propre copie des poids, faute de `SharedArrayBuffer`.
>
> **Passer de 8 à 16 workers achète 6,2 % de temps mural au premier balayage
> et 3,7 % au second, pour deux fois plus de mémoire (24 → 48 Mo) et deux fois
> plus de secondes-worker.** Le C
> mesurait 19 % pour le même doublement (mesures d'entrée, §7) ; le navigateur
> en rend trois fois moins.

### 4.2 Le chemin des lots — le même protocole que T23 et T21b, une troisième machine

`wasm/workers.html`, 2 000 positions, corpus et page identiques à ceux des deux
relevés publiés :

| workers | éval/s | accélération | pire tâche du fil principal |
|---:|---:|---:|---:|
| 1 | 8 285 | ×1,00 | 0,2 ms |
| 2 | 15 244 | ×1,84 | 0,2 ms |
| 4 | 24 213 | ×2,92 | 0,1 ms |
| **8** | **29 412** | **×3,55** | 4,3 ms |
| 16 | 27 137 | ×3,28 | **21,7 ms** |

**Seize workers sont plus lents que huit sur ce chemin**, et ils font passer la
pire tâche du fil principal de 4,3 à 21,7 ms — l'interface commence à s'en
ressentir.

Les trois machines, même page, même corpus, même protocole :

| machine | fils | ×2 | ×4 | ×8 | ×16 |
|---|---:|---:|---:|---:|---:|
| poste de bureau, Chromium 150 (T23, 2026-08-04) | 16 | 1,92 | 3,11 | **3,82** | — |
| `melbaa`, Firefox 154 (T21b, 2026-08-27) | 28 | 1,74 | 3,10 | **6,20** | — |
| ce poste, Chromium (T87, 2026-09-02) | 16 | 1,84 | 2,92 | **3,55** | 3,28 |

Les deux postes à 16 fils plafonnent autour de ×3,6–3,8 ; la machine à 28 fils
atteint ×6,2 **au même nombre de workers**. Le nombre de workers utile n'est pas
proportionnel aux fils annoncés — c'est le **débit** qui l'est, jusqu'à un
plafond que huit workers atteignent partout.

### 4.3 Un navigateur bridé à quatre fils

Le même chemin de décisions, Chromium sous `taskset -c 0-3` (deux cœurs
physiques et leurs jumeaux), sur un tiers de match (45 décisions) :

| workers | mural | accélération | oisiveté |
|---:|---:|---:|---:|
| 1 | 62,9 s | ×1,00 | 0,00 % |
| 2 | 39,1 s | ×1,61 | 1,37 % |
| 4 | 32,7 s | ×1,92 | 2,50 % |
| **6** | **29,4 s** | **×2,14** | 2,68 % |
| 8 | 31,3 s | ×2,01 | 4,12 % |

`navigator.hardwareConcurrency` y annonce **4** — Chromium honore le masque
d'affinité. Suivre ce chiffre donnerait ×1,92 pour un maximum à ×2,14 : sur une
petite machine il est à peu près juste, sur la grande il est **deux fois trop
grand**. C'est exactement pourquoi il ne peut pas être *la* réponse.

### 4.4 La règle qui en sort, et son statut

`EvaluatorPool.suggestedSize()` rend **`min(fils annoncés, 8)`**, plafonné par
un budget mémoire optionnel. Ce plafond de 8 est celui que **les quatre relevés
disponibles** désignent :

- ×3,55 ici à 8 workers sur le chemin des lots, et **moins** à 16 ;
- ×3,82 à 8 sur un autre poste à 16 fils (T23) ;
- ×6,2 à 8 sur une machine à 28 fils (T21b) ;
- maximum entre 4 et 6 sur un navigateur bridé à 4 fils.

Aucun relevé ne montre de gain franc au-delà de huit, et deux montrent une
perte. La règle **n'est pas une mesure de l'appareil de l'utilisateur** et le dit
dans sa propre documentation : la plateforme ne publie pas son nombre de cœurs
physiques, et `hardwareConcurrency` est plafonné à 4 sur iOS quel que soit le
téléphone. `ScheduleReport` est livré précisément pour que chaque consommateur
tranche sur sa machine plutôt que de nous croire.

---

## 5. Ce qui manque, dit franchement

**Je n'ai eu qu'une machine.** Le critère de la fiche demande deux machines de
classes différentes ; pour le **chemin des décisions** — celui qui compte, celui
que T86 vient d'ouvrir — je n'ai qu'un poste 8 cœurs / 16 fils. Ce qui le
complète ici n'en tient pas lieu :

- le **bridage à quatre fils** (§4.3) est le même silicium sous un masque
  d'affinité : il change le nombre de fils, pas la classe de machine — ni le
  cache, ni la bande passante, ni l'hétérogénéité des cœurs ;
- les **deux autres machines** (§4.2) sont réelles et de classes différentes,
  mais leurs relevés portent sur le chemin des **lots** et datent d'avant T86 ;
- **aucun appareil mobile** n'a été mesuré. C'est le manque le plus gênant,
  parce que c'est là que le nombre de workers importe le plus : `iOS` annonce 4
  quel que soit le téléphone, les cœurs y sont hétérogènes, et un ordonnanceur
  mobile peut reléguer des workers sur les cœurs économes. T23 le nommait déjà
  comme non mesuré ; il l'est toujours.

Le plafond de 8 est donc une **règle prudente tirée de quatre relevés**, pas une
loi. Elle est écrite comme telle dans le code, et l'instrument qui permettrait
de la réfuter est livré avec.

---

## 6. Le même remède, ailleurs : il paie en Python

`python/gammonnet/arena.py` découpait, lui aussi, en exactement `workers`
tâches. La règle mesurée en §2 prédit qu'il est dans le **bon** cas : une tâche
y est une liste d'indices en entrée et quelques flottants en sortie, pour des
parties entières de calcul.

2 500 paires, 8 processus, `first-play` contre `random`, passes entrelacées :

| tâches/processus | tâches | médiane de 5 passes | gain |
|---:|---:|---:|---:|
| 1 *(l'ancien défaut)* | 8 | 11,371 s | — |
| 2 | 16 | 11,408 s | −0,32 % |
| 4 | 32 | 10,763 s | +5,34 % |
| 8 | 64 | 10,796 s | +5,05 % |
| **16** | **128** | **10,676 s** | **+6,11 %** |

Deux confirmations, chacune dans sa propre exécution entrelacée : **+6,23 %** à
5 000 paires (3 passes) et **+6,10 %** à 2 500 paires sur 9 passes (12,059 s
contre 11,323 s). Les granularités 4 et 8, elles, ne se reproduisent pas — +5,3 %
puis +2,4 % — ce qui suffit à préférer 16.

Trois exécutions indépendantes lisent donc **+6,11 %, +6,23 % et +6,10 %** pour
16 tâches par processus. **C'est au-dessus du seuil de 5 %, et c'est la seule des
deux applications de la règle qui le franchit** : le défaut d'`arena.py` passe
donc à 16, et `tests/test_arena.py` vérifie que le résultat — la mesure de force
elle-même — n'en bouge pas d'un chiffre.

> **Le même remède conceptuel vaut +6 % dans un cas et −50 % dans l'autre.** Le
> discriminant n'est ni le langage ni l'algorithme : c'est **ce qu'il en coûte
> de confier une tâche**. C'est cela que l'ADR-0003 doit retenir.
---

## 7. Ce que les consommateurs reprennent

**La règle, dans sa forme mesurée** — « le nombre de tâches paie quand une
tâche coûte cher à calculer et rien à transmettre ; et si un tri doit exister,
sa clé est le nombre d'évaluations » — **avec la borne qui la rend
actionnable** : sur le chemin des décisions, aucun ordonnancement ne peut
gagner plus de 2,6 %.

**gammonGo** écrit aujourd'hui son propre ordonnanceur dans
`frontend/gammongo/src/lib/gammonnet/` :

| ce qu'il peut retirer | lignes | pourquoi |
|---|---:|---|
| `eval-worker.ts` | 50 | son en-tête dit lui-même pourquoi il existe : *« pool.mjs's own worker.mjs does NOT expose them (it only relays raw `evaluateBatch` chunks) »*. T86 a fermé ce manque, T87 mesure le pool qui le remplace. |
| `spawn-ply2-worker.ts` | 11 | le lanceur du précédent. |
| la boucle de distribution de `match-analysis.ts` — `poolSize`, `workers[]`, `inFlight`, `nextIndex`, `runNext`, `finishIfDone`, `cancel` | ~80 | c'est **exactement** `pool.decide()` : une décision par tâche, distribution gloutonne, annulation. Mesurée ici à 2,5 % d'oisiveté sur un match complet — il n'y a rien à y gagner en la réécrivant, et rien à y perdre en l'abandonnant. |
| son ticket de suivi sur `DEFAULT_POOL_SIZE` | — | le fichier dit *« un compromis assumé, PAS une mesure … 4 est un choix délibérément conservateur en attendant cette mesure — ticket de suivi »*. La mesure est ci-dessus, et `EvaluatorPool.suggestedSize()` la porte. |

**~140 lignes de production**, en plus des ~570 que T86 lui avait déjà
libérées, et les tests qui couvrent cette boucle avec.

Ce qu'il **garde** est ce qui lui appartient vraiment : le magasin de reprise
(`MatchAnalysisStore`), le comptage `recomputed` que son critère d'acceptation
nomme, et la conversion `EvalOutcome → PositionAnalysis`. Le pool ne connaît
pas ses appelants ; la persistance et la reprise sont « ailleurs », et elles
restent là-bas.

**blunderDB** ne consomme pas ce pool (il passe par cgo) et n'a rien à
reprendre ici, sinon la règle : son analyse de match en Go découpe elle aussi,
et la borne de 2,6 % vaut pour elle si son nombre de tâches dépasse déjà son
nombre de fils.

---

## 8. Ce qui est livré, et ce qui ne l'est pas

| | |
|---|---|
| **Livré** — `ScheduleReport` | l'oisiveté d'un travail, relevée des deux côtés, pour que chaque consommateur tranche sur SON appareil au lieu de nous croire |
| **Livré** — `tasksPerWorker` | le réglage, avec sa courbe mesurée, défaut inchangé (1) |
| **Livré** — `EvaluatorPool.suggestedSize()` / `memoryCostMB()` | l'API cesse de laisser croire que `hardwareConcurrency` est la réponse |
| **Livré** — `wasm/pool_invariants.mjs` | les invariants de distribution, avec des workers dont le test choisit le temps de réponse |
| **Livré** — `arena.play_pair(chunks_per_worker=…)`, défaut **16** | +6,1 % mesuré, reproductible trois fois : la seule application de la règle qui franchit le seuil |
| **Livré** — `bench/bench_arena_grain.py` | le banc qui l'a mesuré, avec son contrôle que le résultat ne bouge pas |
| **NON livré** — le tri par nombre d'évaluations | 1,2 % contre un seuil à 5 %, et un plafond théorique à 2,6 % |
| **NON livré** — plus d'une tâche par worker sur `analyze` | −10 points d'oisiveté, **+50 % de temps mural** |

**Le poste « ordonnancement » de T87 est abandonné DANS LE NAVIGATEUR, et la
mesure qui l'abandonne est ci-dessus** ; il est livré en Python, où la même
règle rend 6 %. Ce n'est pas un échec de mise en œuvre : le chemin qui coûte
présentait déjà 139 tâches pour 8 workers, et la fiche l'avait prévu sans le
savoir en écrivant que le remède est le nombre de tâches. Il était déjà pris.

---

## Reproduire

```bash
python tools/fetch_release.py     # l'artefact float16 épinglé
make wasm && make wasm-api        # dont les invariants de l'ordonnanceur

# L'oisiveté des deux chemins, 8 workers, match complet
node wasm/harness.mjs --browser chromium --page /wasm/ordonnancement.html \
     --build simd --mode idle --workers 8 --timeout 850000

# La granularité, passes entrelacées
node wasm/harness.mjs --browser chromium --page /wasm/ordonnancement.html \
     --build simd --mode sweep-analyze --workers 8 \
     --tasksPerWorker 1,2,4,8,16,32 --reps 7 --timeout 850000

# Le nombre de workers, chemin des décisions
node wasm/harness.mjs --browser chromium --page /wasm/ordonnancement.html \
     --build simd --mode sweep-decide --workers 1,2,4,6,8,12,16 \
     --timeout 2900000
```

Le balayage du plateau (`--workers 6,8,12,16,8,16`), le navigateur bridé
(`PATH` pointant sur un `chromium` qui appelle `taskset -c 0-3`, avec
`--limit 45`) et le banc Python :

```bash
python bench/bench_arena_grain.py 2500 8 5
```

Les relevés bruts : [`t87-oisivete-avant.json`](t87-oisivete-avant.json),
[`t87-oisivete-apres.json`](t87-oisivete-apres.json),
[`t87-granularite.json`](t87-granularite.json),
[`t87-workers-decision.json`](t87-workers-decision.json),
[`t87-workers-plateau.json`](t87-workers-plateau.json),
[`t87-workers-4-fils.json`](t87-workers-4-fils.json),
[`t87-workers-lots.json`](t87-workers-lots.json).

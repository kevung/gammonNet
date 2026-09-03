---
status: accepted
date: 2026-09-02
portée: gammonNet et ses artefacts (natif, `gammonnet serve`, WebAssembly) ; lie ses consommateurs blunderDB et gammonGo
---

# Les optimisations communes vivent ici, et le critère de rangement se mesure

gammonNet a aujourd'hui **deux implémentations** de la même Configuration : le C de ce dépôt,
et le portage Go de blunderDB, prouvé conforme au bit près (`verify/reference.bin`,
max|Δ| = 5,960e-08). Il a **trois** cibles d'exécution : le natif, le service
`gammonnet serve`, et le module WebAssembly que gammonGo livre au navigateur.

Le 2026-09-02, blunderDB a mené une campagne d'optimisation sur son portage : une décision
2-ply `(0,1,3)` `k=12` y est passée de **5,5 s à 0,277 s**, sans qu'aucune équité ne bouge
d'un bit. La question s'est posée immédiatement : qu'est-ce qui, de ce travail, doit
redescendre ici, et qu'est-ce qui n'a de sens que dans un langage ?

**Décision : toute optimisation dont le gain survit à un changement de langage est
conceptuelle, et se décide, se mesure et s'écrit d'abord ici. Les consommateurs suivent.**

## Le critère, et pourquoi il est opératoire

*Une optimisation est **conceptuelle** si son gain survit à un changement de langage.*
Sinon elle est **d'implémentation**, et personne ne peut la factoriser.

Ce critère n'est pas une intuition : il se mesure, et la mesure a déjà tranché les six
postes du chantier Go. Chacun a été chronométré ici, en C, sur le même matériel
(`docs/mesures/2026-09-02-optimisation-mesures-d-entree.md`) :

| Poste livré dans le portage Go | Gain en Go | Gain mesuré **en C** | Verdict |
|---|---|---|---|
| Tri typé stable au lieu d'un tri réflexif | 7 432 → 83 allocations/décision | **0,16 %** | implémentation |
| Tampons possédés plutôt qu'alloués par appel | −15 % à 0-ply | **0,007 %** | implémentation |
| Encodage sans revalider une position légale | ×2,05 sur l'encodage | **0,5 %** | implémentation |
| Déduplication par table de hachage | doubles ×3,2 | déjà fait par le moteur vendoré | sans objet |
| Alternance des niveaux au lieu d'une copie | ×5,4 à ×10,6 | sans objet (autre structure) | sans objet |
| Sparsité de la couche 1 | **~6 %**, et −9 % hors fratrie | **×1,161** | implémentation |
| **Valuer le videau par lot sur les candidats** | non tenté | poste à **20-25 %** au score | **conceptuelle** |
| **Ordonnancer par nombre de tâches, non par tri** | oisiveté 15 % → 3-5 % | **0 % au navigateur, +6,1 % en Python** | **conceptuelle**, avec une condition |

Le résultat est net et il aurait été impossible à deviner : **cinq des six postes du
chantier Go ne valent rien ici**. Ce sont des artefacts du langage — un tri réflexif, un
ramasse-miettes, une copie de tranche. Les deux qui redescendent sont précisément ceux qui
touchent la **forme de l'algorithme**, pas son écriture.

La sparsité de la couche 1 mérite d'être lue deux fois : elle rend 6 % en Go et 16 % en C,
parce que la compaction coûte ~3,3 cycles par flottant en Go. Le portage avait posé
l'hypothèse ; la mesure la confirme. C'est le cas d'école du critère — même idée, gain qui
ne survit pas au changement de langage, donc chaque implémentation décide pour elle.

**L'ordonnancement est un second cas d'école, et il tranche dans l'autre sens : c'est la
RÈGLE qui voyage, pas le gain.** T87 l'a mesuré dans un navigateur, sur un match complet
(`docs/mesures/2026-09-02-T87-ordonnancement.md`). La règle du portage Go est exacte —
l'oisiveté d'un pool est celle de son nombre de tâches, et le tri n'y peut presque rien —
mais le chemin qui coûte 2,7 s par décision présente **déjà** 139 tâches pour 8 workers, et
son oisiveté vaut **2,5 à 2,6 %**. Un ordonnancement omniscient y gagnerait 2,6 %, le tri
autorisé par la fiche 1,2 % : le poste est sous le seuil d'abandon **par construction**.

Et la règle a une frontière que le portage Go ne pouvait pas voir, parce que ses tâches ne
traversent pas de `postMessage` : **le nombre de tâches paie quand une tâche coûte cher à
CALCULER et rien à TRANSMETTRE.** Sur le chemin des lots de caractéristiques, où chaque
tâche fait voyager 250 Ko clonés par le fil principal, multiplier les tâches fait tomber
l'oisiveté de 17,6 % à 7,2 % **et allonge le travail de 50 %**.

**La preuve que c'est bien la condition, et non le langage, qui décide** : le même remède,
appliqué au `ProcessPoolExecutor` de `python/gammonnet/arena.py` — où une tâche est une
liste d'entiers en entrée et quelques flottants en sortie, pour des parties entières de
calcul — rend **+6,1 %**, lu trois fois (+6,11, +6,23, +6,10). Le même changement
conceptuel vaut donc **+6 % dans un runtime et −50 % dans un autre**, et le discriminant
n'est ni le langage ni l'algorithme : c'est **ce qu'il en coûte de confier une tâche**.

Ce que cela ajoute au critère de rangement : une optimisation conceptuelle voyage avec sa
**condition d'application**, ou elle ne voyage pas. Importée sans elle, elle est une
régression qui se croit une optimisation — et une régression que les tests laissent passer,
puisqu'elle ne déplace aucun résultat.

## Ce que cela oblige

1. **Une optimisation conceptuelle s'écrit ici d'abord**, avec sa mesure et sa preuve
   d'exactitude, puis les consommateurs la reprennent. blunderDB s'impose déjà cette règle
   pour son `cube.go` (« *the file is a port, so any change here lands in gammonNet's
   `gn_cube.c` and its spec §2 first* ») ; cette décision l'étend à toute optimisation
   conceptuelle, et à gammonGo.
2. **Une fiche dit laquelle des deux couches elle touche**, et pour la couche conceptuelle,
   **ce que chaque consommateur devra reprendre** — le portage Go, le module WebAssembly, le
   service. Une fiche qui améliore le C sans le dire laisse les implémentations diverger,
   ce qui est exactement ce que cette décision empêche.
3. **Une optimisation d'implémentation reste chez celui qui la porte**, sans remords et sans
   remontée. L'assembleur AVX2 de blunderDB n'a rien à faire ici ; les intrinsèques SIMD128
   du navigateur n'ont rien à faire là-bas.
4. **Les mesures, elles, remontent toujours** — y compris celles qui réfutent. Trois
   prémisses de ce dépôt sont tombées ce jour-là : précalculer les `metAfter` du videau vaut
   1 % et non ce qu'on espérait (`level_solve` pèse 83 % du poste, et chaque bissection est
   une division sur le chemin critique plus un branchement imprévisible) ; « les doubles
   sont les lancers coûteux » est faux (1 800 coups contre 168, mais l'élagage n'en garde
   que `k` et la position laissée est plus contrainte — écart réel **1,54×**) ; et un banc
   qui évalue huit positions **quelconques** mesure autre chose que ce que la recherche
   fait, dont l'union des entrées actives est deux fois plus étroite sur une fratrie.

## La condition que cette décision révèle

Elle ne tient pas toute seule. **L'artefact WebAssembly sous-exporte**, et gammonGo réécrit
donc du moteur en TypeScript : son propre ordonnanceur de workers, le codec Position ID
gnubg (deviné puis validé empiriquement à 5,85e-9), la notation de coup par différence de
plateaux, et la sémantique du videau rétro-conçue depuis un défaut.

La cause n'est pas ce qu'on croit. `_gnw_rank_plays`, `_gnw_best_play` et
`_gnw_cube_decide` **sont** exportés ; c'est `wasm/worker.mjs` qui ne relaie que
`init`/`evaluate`/`stop`. Le codec, lui, n'est enveloppé nulle part dans `gn_wasm.c`, et
**la notation de coup n'existe pas en C du tout** — il n'y a rien à exporter, il y a quelque
chose à écrire.

Tant que ce manque dure, « les optimisations communes vivent ici » est un vœu : le
navigateur continue d'exécuter du TypeScript écrit à côté du moteur, et tout ordonnancement
optimisé ici reste mort. C'est pourquoi **T86 passe devant T85 alors qu'elle ne gagne pas une
microseconde** : elle est la condition des autres.

## Deux défauts que ce cadrage a fait apparaître

Ils sont consignés ici parce qu'ils sont exactement le genre de chose qu'une frontière floue
laisse vivre.

- **`wasm/gammonnet.mjs` pose `efficiency = 0.566` en défaut** de `rankPlays` et de
  `cubeDecision`, dont le défaut d'`owner` est `GN_CUBE_CENTRED`. Or 0,566 est l'efficacité
  du videau **possédé** ; la centrée vaut 0,688 (T34). Le C n'a aucun défaut et le Python
  indexe le triplet par `owner` : c'est le wrapper seul qui invente une valeur. **Le remède
  n'est pas 0,566 → 0,688, c'est pas de défaut du tout, ou un défaut indexé par `owner`.**
- **Le classement des coups n'est pas déterministe entre plateformes.**
  `compare_candidates` ne compare que l'équité et `qsort` n'est pas stable : l'ordre des
  ex æquo dépend de la libc — glibc en natif, Emscripten en WebAssembly, une troisième en
  Go. Le harnais de parité compare des équités à 1e-6, **donc la permutation lui est
  invisible** — et elle change le coup annoncé. C'est le contre-exemple parfait à l'idée
  qu'une tolérance numérique suffit à prouver deux implémentations d'accord.

> **Les deux sont corrigés le 2026-09-02** — mesure :
> `docs/mesures/2026-09-02-T88-census-ex-aequo.md`.
>
> Le second n'était pas théorique, et il n'était pas non plus partout : le `qsort` de la
> glibc est stable en pratique, celui d'Emscripten ne l'est pas. **Le classement divergeait
> donc dans l'artefact servi au navigateur, et nulle part ailleurs** — 89 des 433 décisions
> à meilleur coup ex æquo du corpus T12 y annonçaient un autre coup que le natif, à équité
> égale au bit près. La règle de départage retenue est celle du portage Go (à équité égale,
> l'ordre d'arrivée est conservé), précisément parce que l'objet de cette décision est
> l'accord et non la seule détermination.
>
> Ce que cet épisode ajoute à la décision ci-dessus : **un défaut d'exactitude peut vivre
> sous le seuil que les tests regardent ET n'apparaître que sur une cible**. Le harnais qui
> l'aurait vu n'est pas un harnais plus tolérant, c'est un harnais qui compare des ORDRES et
> pas seulement des nombres.

## Ce que cela coûte

Écrire d'abord ici est plus lent pour qui a le correctif sous la main dans son langage. C'est
le prix assumé : la seule alternative est deux implémentations qui divergent en silence, et
le défaut de déterminisme ci-dessus montre qu'elles peuvent diverger **sous le seuil que les
tests regardent**.

Cette décision ne dit rien de *qui* écrit. Elle dit où la chose est décidée, mesurée et
consignée, et dans quel ordre les trois consommateurs la reçoivent.

## Le premier poste conceptuel a été livré, et il tient

> **T85, le 2026-09-02** — `docs/mesures/2026-09-02-T85-videau-par-lot.md`, forme consignée en
> `docs/specs/t34-videau-spec.md` §7.1.
>
> Le tableau ci-dessus rangeait « valuer le videau par lot sur les candidats » comme le seul
> poste **conceptuel** que le portage Go n'avait pas tenté, à 20-25 % au score. La mesure le
> confirme et le livre : au score, le videau passe de **103,6 ms à 42,7 ms** par décision
> (×2,43 par valuation), sa part de **19,35 % à 9,05 %**, soit **11,4 % sur la décision
> entière** ; **en money, rien**, comme prévu. Le résultat est bit à bit — 12 600 classements
> du corpus T12 rejoués sans une ligne de `diff`.
>
> Deux choses que cet épisode ajoute à la décision.
>
> **Le critère a bien tenu.** Le gain est de la latence de division recouverte par des voies
> indépendantes : il ne doit rien à C, et il se transportera tel quel en Go et dans le
> navigateur. C'est la définition même de « conceptuelle », et c'est la première fois qu'elle
> est vérifiée après coup plutôt que prédite.
>
> **Mais la mesure d'entrée qui avait rangé ce poste était un produit, pas un chronométrage**,
> et elle le disait. Le compléter a demandé de construire un instrument entrelacé — sans quoi
> le même poste se lit 10,6 %, 26 % ou 20,5 % selon la façon de soustraire, sur une machine
> partagée, le même après-midi. **Une fiche dont le seuil d'abandon est de 5 % doit donc dire
> non seulement ce qu'elle mesure, mais avec quel instrument** : un rapport dos à dos entre
> deux processus ne suffit pas quand le voisin fait tourner autre chose.

# Optimiser pour le navigateur — le plan, et ce que ses mesures d'entrée disent déjà

**Date** : 2026-09-02 · **Mesures d'entrée** :
[`docs/mesures/2026-09-02-optimisation-mesures-d-entree.md`](../mesures/2026-09-02-optimisation-mesures-d-entree.md)
· **Fiches ouvertes** : T84 – T90 · **Branche** : `perf/plan-optimisation-navigateur`

> **La question.** Une décision 2-ply `(0,1,3)` `k=12` coûte **~2 689 ms** dans Firefox sur un
> worker (T21b) et **0,36 s** en natif sur la machine de bureau. Le portage Go de blunderDB fait
> la même décision en **0,277 s** après sa campagne du 2026-09-02. C'est l'utilisateur de
> gammonGo qui paie l'écart, et c'est là que le levier est le moins exploité.
>
> Ce document instruit ce chantier. **Il n'implémente rien** : la règle 3 de `CLAUDE.md` interdit
> d'écrire du code d'optimisation avant que les mesures d'entrée existent, et elles n'existaient
> pas sur cette machine avant aujourd'hui.

## La décision d'architecture qui commande le plan

> **Les optimisations communes vivent dans gammonNet et dans ses artefacts.**

Elle sépare deux couches, et chaque fiche doit dire laquelle elle touche :

| Couche | Ce que c'est | Où elle se décide |
|---|---|---|
| **Conceptuelle** | La forme de l'algorithme : valuer le videau par lot, regrouper ou non les 21 lancers, ordonnancer par nombre de tâches, exploiter la sparsité et sur quel lot | **Ici.** Les consommateurs reprennent |
| **Implémentation** | L'assembleur AVX2 pour Go, les intrinsèques SIMD128 pour WebAssembly, ce que `gcc` veut bien vectoriser | Irréductiblement par langage et par cible. Personne ne la factorise |

Le précédent existe : blunderDB s'impose déjà, dans son `CLAUDE.md`, que tout changement à son
`cube.go` *« lands in gammonNet's gn_cube.c and its spec §2 first »*. La décision d'aujourd'hui
étend cette règle d'un fichier à **toute optimisation conceptuelle**.

**Corollaire opératoire** : une fiche qui améliore le C sans dire comment le portage Go, le
module WebAssembly et `gammonnet serve` la reprennent laisse les implémentations diverger. Chaque
fiche ci-dessous porte donc une ligne « ce que les consommateurs reprennent ».

## Et la cause racine que les mesures n'atteignent pas

**L'artefact WebAssembly sous-exporte, et gammonGo réécrit du moteur en TypeScript pour
compenser.** Un relevé des recouvrements entre les trois dépôts l'a établi, avec les commentaires
de gammonGo qui l'assument :

1. **`wasm/pool.mjs` n'est pas utilisé.** gammonGo écrit deux ordonnanceurs à lui, parce que
   `wasm/worker.mjs` *« only relays raw evaluateBatch chunks »*. Vérifié ici : son protocole est
   `init` / `evaluate` / `stop`, rien d'autre. **Les points d'entrée de la recherche sont pourtant
   exportés du module** — `_gnw_best_play`, `_gnw_rank_plays`, `_gnw_cube_decide` sont dans
   `EXPORTED_FUNCTIONS` — mais le worker ne les relaie pas. Ce qui manque n'est donc pas un
   export : c'est **un worker qui expose la recherche**.
2. **Le codec Position ID est réécrit en TypeScript**, deviné puis validé empiriquement à
   5,85e-9. Vérifié ici : le C a `gn_position_id`, `gn_position_from_id`, `gn_position_from_xgid`,
   `gn_xgid` ; **aucun des quatre n'est enveloppé dans `wasm/gn_wasm.c`**, donc aucun n'est
   exportable. Deux lignes de glu et une d'export l'effaceraient.
3. **La notation de coup est réécrite en TypeScript par différence de plateaux.** Vérifié ici, et
   c'est pire que rapporté : **le C n'a pas de générateur de texte de coup non plus**. Il n'y a
   rien à exporter ; il y a quelque chose à écrire.
4. **La sémantique du videau a été rétro-conçue** côté client.
5. **Un défaut confirmé.** `wasm/gammonnet.mjs` expose `efficiency = 0.566` en défaut de
   `rankPlays` **et** de `cubeDecision`, dont le défaut d'`owner` est `0` = `GN_CUBE_CENTRED`.
   Or 0,566 est l'efficacité **possédée** ; celle du videau **centré** est 0,688
   (`docs/mesures/2026-08-07-T34-ajustement.md`, et les trois valeurs mesurées sont
   0,688 / 0,566 / 0,687). Le C n'a aucun défaut — il exige le paramètre ; le Python indexe le
   triplet mesuré par l'état de possession. **Le seul défaut du dépôt est le mauvais, et il est
   dans l'artefact distribué.** Correction proposée en T86, à valider avant écriture.
6. **Les formes canoniques sont recopiées quatre fois** (`prune_k = 12`, filtre `(0,1,3)`,
   profondeur 2) : `wasm/gammonnet.mjs` preset `normal`, le portage Go, `client.ts`,
   `advanced-settings.ts`. gammonGo ajoute un `PRUNE_K_FAST = 3` sans mesure amont — alors que
   T3A en a une : `k=3` perd +0,00389 d'équité par décision [+0,00232 ; +0,00585], contre
   +0,00023 pour `k=12`.

**Sans T86, tout l'ordonnancement optimisé ici reste mort** : le navigateur continuera d'exécuter
du TypeScript écrit à côté du moteur. C'est pourquoi T86 est en tête de l'ordre recommandé alors
qu'elle ne fait gagner aucune microseconde.

---

## Ce que les mesures d'entrée ont déjà tranché

### Trois portes se referment

**La réassociation flottante n'est pas un levier natif.** `NATIVE_FP=1` achète ×4,23 sur le
chemin scalaire et **0 à 6 % sur une décision** : depuis T35 la recherche passe par le noyau
groupé, déjà vectorisé sans réassociation. Le drapeau reste utile au build WebAssembly, qui
l'emploie. Ne pas rouvrir « et si on l'activait par défaut ».

**La sparsité de la couche 1 est déjà livrée, et elle paie en C.** ×1,161 à `k=12`, ×1,160 à
`k=3`, A/B dos à dos reproductible à 0,3 % près. Le portage Go mesure 6 % pour la même
transformation et impute l'écart au coût de sa compaction ; l'hypothèse qu'il formule est
**confirmée**. Il n'y a rien à reprendre du portage sur ce poste, et son constat 2 ne s'applique
pas ici. Reste ouvert : la part du **petit** réseau, jamais mesurée séparément (T89).

**Le remplissage des lots n'est pas le problème du grand réseau.** 93,6 % à `k=12` avec le
regroupement des 21 lancers — mieux que les 84,3 % que le portage Go obtient à largeur 8 **sans**
regrouper. La question posée par son constat 1 (« le regroupement gagne-t-il encore sa complexité
à 8 voies ? ») ne se tranche donc pas par le remplissage : elle se tranche par le **débit crête à
noyau écrit à la main**, ce qui est exactement T84.

### Un poste s'ouvre, et c'est le plus gros

**Le videau au score coûte ~2 029 ns par nœud, et la recherche en fait un par nœud.** En money :
14 ns. Deux ordres de grandeur d'écart, et à `k=12` une décision évalue 43 218 nœuds :

```
43 218 × 2 029 ns ≈ 88 ms,  soit ~20-25 % d'une décision AU SCORE
```

C'est le constat 3 du portage Go, chiffré ici : *« ce qui marcherait, et qui n'a pas été tenté :
valuer le videau par lot sur les candidats »*. Les 60 bissections de chaque candidat sont
indépendantes, donc vectorisables sur la dimension des candidats — même figure que le noyau
réseau, mêmes garanties si chaque voie garde sa séquence. **C'est T85.**

Et ce qui est **fermé** l'est aussi : précalculer les consultations de la table d'équité de match
vaut 11 % d'un poste dont `level_solve` pèse 83 %. Le portage l'a écrit, mesuré à 1 %, et annulé.
Ne pas le refaire.

### Trois postes du portage Go n'ont pas d'objet ici — mesuré, pas supposé

Le chantier Go a livré six postes hors réseau. Verdict pour chacun :

| poste Go | équivalent en C | mesuré ici | verdict |
|---|---|---|---|
| tri typé stable au lieu d'un tri réflexif | 4 `qsort` avec comparateur indirect sur des `GnCandidate` de 72 o ; 2 087 tris et 43 926 éléments par décision | `qsort` 0,80–0,90 ms, clés extraites + insertion 0,16–0,18 ms | **0,16 % — artefact de langage.** Mais la **stabilité** est un vrai sujet : voir T88 |
| tampons possédés par le chercheur | `malloc` par appel dans `rank_plays_prune` et cinq autres sites ; **1 678 paires et 132,6 Mio par décision** | le même profil rejoué seul : **0,027 ms** | **0,007 % — vide en C.** glibc recycle un bloc chaud ; il n'y a pas de ramasse-miettes à nourrir |
| encodage sans revalidation | `gn_encode` appelle `gn_position_is_valid` à chaque appel | validation 44,4 ns sur 91,5 ns d'encodage — **48,5 %** ; ~1,9 ms par décision | **0,5 % — mesurable, pas rentable seul.** À prendre en passant si T84 touche l'encodage, jamais pour lui-même |
| déduplication par table de hachage | le moteur vendoré déduplique déjà **par position résultante** (`gn_rules_reference.c:220`) | — | **Sans objet.** Déjà fait |
| alternance des niveaux au lieu d'une copie | `forward_batch` alterne déjà `g_batch_a` / `g_batch_b` ; la recherche copie des `GnPosition` de **29 octets** | — | **Sans objet.** La copie qui coûtait en Go est ici un objet de 29 octets |
| index de notation | **le C n'a pas de générateur de texte de coup** | — | **Idée à reprendre, mais à l'envers** : ce n'est pas une optimisation, c'est une fonction manquante que gammonGo a dû réécrire. Voir T86 |

**La leçon générale, et elle mérite d'être écrite** : quatre des six postes du chantier Go sont
des **artefacts du langage** — pression sur le ramasse-miettes, réflexion, copies de valeur. Ils
ne redescendent pas. Ce qui redescend est ce qui touche la **forme de l'algorithme** : le videau
par lot (T85), l'ordonnancement par nombre de tâches (T87), et un fait de mesure — « les doubles
sont les lancers coûteux » est faux, l'écart réel est 1,54× en évaluations.

### Un défaut de déterminisme, trouvé en mesurant le tri

`compare_candidates` (`gn_search.c:366`) ne compare **que l'équité**, et `qsort` n'est pas stable.
L'ordre de deux candidats de même équité dépend donc de l'implémentation de `qsort` : celle de la
glibc en natif, celle de la libc d'Emscripten en WebAssembly, une troisième dans le portage Go.
Le harnais de parité compare des **équités** à 1e-6 : une permutation d'ex æquo lui est
**invisible**, et elle change le coup annoncé. **C'est T88**, et ce n'est pas une fiche de
vitesse.

---

## Les fiches, et l'ordre recommandé

L'ordre tient compte des trois cibles. **Une optimisation qui ne sert que le natif vaut moins
qu'une qui sert aussi le navigateur**, puisque c'est là qu'une décision coûte 2,7 s.

| # | Fiche | Couche | Cibles servies | Gain attendu | Seuil d'abandon |
|---|---|---|---|---|---|
| 1 | **T86** — la surface de l'artefact WebAssembly | conceptuelle + artefact | navigateur | **zéro microseconde**, et sans elle rien d'autre n'atteint le navigateur | si le `.wasm` dépasse +25 % (115 Kio), livrer par étapes et publier ce que chaque point d'entrée coûte |
| 2 | **T85** — valuer le videau par lot sur les candidats | **conceptuelle** | natif, navigateur, serve | 15–20 % d'une décision **au score** ; rien en money | < 5 % sur une décision au score ⇒ annulé, comme le portage Go a annulé le sien |
| 3 | **T88** — le déterminisme du classement | **conceptuelle** (exactitude) | les trois | zéro vitesse ; ferme un mode de divergence silencieuse entre cibles | aucun : si la mesure montre que les ex æquo n'existent pas en pratique, la fiche se ferme sur ce chiffre, publié |
| 4 | **T84** — la largeur de lot, tranchée par des intrinsèques | conceptuelle **et** implémentation | natif, navigateur | inconnu ; SIMD128 n'a que **4** voies flottantes, donc l'enjeu y est plus grand qu'en AVX2 | < 10 % à noyau écrit à la main ⇒ la largeur 32 et le regroupement restent, et la question est close pour de bon |
| 5 | **T87** — l'ordonnancement par nombre de tâches | **conceptuelle** | navigateur, serve, arena | oisiveté de ~15 % à 3-5 % (mesuré en Go) ; le nombre utile de workers borné par les cœurs physiques | < 5 % de temps mural sur un match complet ⇒ non livré |
| 6 | **T89** — la sparsité sur le petit réseau | conceptuelle | les trois | le registre attend 78 % sur un réseau qui consomme **76,6 à 93,5 %** des voies calculées | < 5 % sur une décision ⇒ le chiffre de 78 % est retiré du registre |
| 7 | **T90** — l'arrondi des tuiles et les formes canoniques | implémentation + artefact | les trois | zéro ; c'est un garde-fou et une source unique de vérité | aucun |
| — | **T73** (déjà ouverte) — QAT int8 + noyau SIMD128 | implémentation, par cible | navigateur surtout | le levier de fond ; DS-09 fixe son seuil à 1,3× | inchangé |

### Pourquoi cet ordre, et pas l'ordre des gains

**T86 d'abord parce qu'elle est la condition des autres.** Elle ne gagne rien. Mais tant que le
navigateur exécute la recherche en TypeScript à côté du moteur, T85 et T87 améliorent un code que
le navigateur n'appelle pas. C'est la seule fiche du lot dont l'absence rend les autres inutiles
sur la cible qui souffre le plus.

**T85 ensuite parce que c'est le seul gros poste ouvert, et qu'il est mesuré.** ~88 ms sur une
décision au score, un chemin d'exactitude identique à celui du noyau réseau (chaque voie garde sa
séquence de bissection), et il sert les trois cibles à la fois. C'est aussi le poste dont le
portage Go dit explicitement qu'il n'a pas été tenté.

**T88 en troisième parce qu'un défaut de déterminisme se paie plus tard et plus cher.** Il est
gratuit à corriger aujourd'hui et coûteux le jour où deux cibles annoncent deux coups différents
sur une position d'ex æquo, sans qu'aucun harnais ne le signale.

**T84 seulement en quatrième**, malgré son importance apparente, parce qu'elle demande d'écrire
des intrinsèques dans deux jeux d'instructions avant de savoir ce qu'elle rapporte — c'est la
fiche la plus chère du lot par unité d'information, et T73 réécrit ce noyau de toute façon. Son
seul résultat certain est un **résultat négatif utile** : fermer la question de la largeur.

**T87 en cinquième** parce que son gain est réel mais borné : le portage mesure ~5 % pour un tri
correct et 10-12 points d'oisiveté récupérés par l'aplatissement de la frontière. Elle dépend en
outre de T86 pour exister dans le navigateur.

**T89 et T90 en dernier** : la première est une mesure avant d'être un chantier ; la seconde est
une dette d'hygiène qui devient urgente le jour où T73 déplace les tuiles, pas avant.

---

## La discipline — elle est la moitié du résultat

Reprise du chantier blunderDB, et elle n'est pas négociable ici non plus.

**Un poste par commit, avec son chiffre dans le message.** Pas de commit « diverses
optimisations » : on ne sait plus ensuite lequel a payé, ni lequel a coûté.

**Un poste sans gain mesurable n'est pas livré.** Sur blunderDB, le plus gros poste de la liste —
le videau — a été écrit, mesuré à 1 %, puis **annulé**, et c'est le meilleur résultat du chantier.
Chaque fiche ci-dessus porte son seuil d'abandon *avant* que le code existe, précisément pour que
l'annulation soit une issue prévue et non un aveu.

**Rien ne doit déplacer une sortie.** Le corpus de non-régression T12 et
`dist/…/verify/reference.bin` (tolérance 1e-6) sont les juges, et le contrôle **bit à bit** là où
il est atteignable — `bench_batch` le tient aujourd'hui à `max|Δ| = 0,000e+00` sur toutes les
largeurs, `tests/test_batch.py` l'exige, et T88 ajoute que l'égalité des équités ne suffit pas :
l'**ordre** des ex æquo en fait partie.

**Et un piège nommé d'avance.** Le portage Go a écrit `outDim & ^(tile-1)` pour arrondir au
multiple inférieur — correct seulement pour une puissance de deux ; à tuile 6, la boucle lisait
des poids **hors matrice**, et les tests ne l'ont pas vu parce que la tuile valait 4 quand ils ont
été écrits. `GN_EVAL_BATCH` vaut 32 ici, donc le code actuel est sauf. **T73 et T84 déplacent ces
tuiles**, et T90 pose le garde avant qu'ils le fassent.

---

## Faut-il un ADR, et où ? — recommandation

**Oui, un seul, et dans gammonNet : `docs/adr/0003`.**

Les raisons, dans l'ordre où elles pèsent :

1. **Ce qui est décidé est une frontière, pas une technique.** « L'optimisation conceptuelle
   appartient à gammonNet ; l'implémentation appartient à chaque cible » est exactement le genre
   d'énoncé qu'un ADR existe pour figer : il se défait très cher une fois que trois dépôts ont
   divergé, et il ne se déduit d'aucun fichier.
2. **gammonNet est l'amont, donc le lieu où la règle est vérifiable.** blunderDB et gammonGo sont
   des consommateurs ; une règle écrite chez un consommateur ne lie pas les deux autres. Écrite
   ici, elle est citable par les deux — et le précédent du `cube.go` de blunderDB montre que
   c'est comme cela que la chose fonctionne déjà, en plus petit.
3. **Un ADR par dépôt serait le début de la divergence qu'il prétend empêcher.** Trois textes à
   maintenir en accord, c'est deux de trop.

**Ce que blunderDB et gammonGo font à la place** : une ligne d'invariant dans leur `CLAUDE.md`
qui **pointe** l'ADR d'ici — la généralisation de celle qui existe déjà chez blunderDB pour
`cube.go`. Une ligne, pas un document.

**Ce que l'ADR doit contenir, et qui n'est pas évident** : le critère qui range une optimisation
d'un côté ou de l'autre. La proposition, tirée des six postes examinés plus haut : *une
optimisation est conceptuelle si son gain survit à un changement de langage.* Le tri typé et les
tampons possédés ne survivent pas — mesurés à 0,16 % et 0,007 % en C. Le videau par lot,
l'ordonnancement par nombre de tâches et la sparsité survivent. Le critère est opératoire parce
qu'il se **mesure** : on porte, on mesure, et le chiffre range la fiche.

**Je ne l'ai pas écrit** — la consigne était de recommander, pas de décider.

---

## Ce que je n'ai pas pu mesurer

- **Le navigateur.** Aucun relevé Firefox/Chromium n'a été refait : T21b date du 2026-08-27 et
  vient d'une autre machine (`melbaa`, 28 cœurs). Toutes les projections navigateur de ce
  document reposent sur lui. **La première mesure de T86 doit être un T21b rejoué ici**, sans
  quoi les gains navigateur restent des transpositions.
- **Le profil interne d'une décision.** Ni `perf` ni `valgrind` ne sont installés sur cette
  machine, et le repli par équations sur trois configurations donne un coefficient négatif pour
  le petit réseau — le modèle linéaire ne tient pas. « Où passe le temps dans une décision » reste
  donc **non mesuré** ; c'est la mesure d'entrée manquante la plus gênante, et T85 comme T89
  devront la produire par instrumentation directe.
- **Le videau dans la recherche.** Les ~88 ms du §5 sont un **produit de deux mesures** — coût par
  nœud et nombre de nœuds — pas un chronométrage. `bench_decision` ne sait pas activer
  `use_cube`. T85 commence par là.
- **La largeur de lot.** Le balayage recompilé donne 16 devant 32 de 7 %, sur un seul relevé par
  largeur et une machine qui dérivait de 20 % dans la séance. **Non concluant**, et l'inverse de
  ce que T3A avait mesuré sans élagage. À refaire au repos.
- **La sparsité par réseau.** Le ×1,16 mesuré est celui des deux réseaux ensemble.
- **Le mobile.** Toujours pas d'appareil ; T21 avait chiffré ×2,12 à ×2,83.

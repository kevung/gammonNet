# Ce que le portage Go a mesuré, et ce que cela change ici

Un portage Go indépendant de gammonNet existe. Le 2 septembre 2026, ce
portage a reçu son noyau d'inférence groupé et une campagne d'optimisation de tout ce qui
l'entoure. Une décision 2-ply `(0,1,3)` `k=12` y est passée de **5,5 s à 0,277 s** en série.

Le code n'a rien à remonter ici : le noyau groupé existe déjà en C, le regroupement dans
la recherche aussi, et tout ce qui a été écrit là-bas est ou bien spécifique à Go, ou bien
déjà présent. **Ce sont les mesures qui remontent**, parce que quatre d'entre elles
contredisent ou déplacent ce que `2026-08-26-optimisations-avant-navigateur.md` affirme.

## Comment lire ces chiffres

Chaque constat porte son marqueur, comme la règle 3 de `CLAUDE.md` l'exige.

- **[MESURE Go]** — chronométré dans le portage Go, sur AMD Ryzen 7 PRO 6850U (Zen 3,
  8 cœurs physiques / 16 fils, AVX2), Go 1.25.13. Le nombre est réel ; sa **transposition
  au C est une hypothèse**, explicitement signalée à chaque fois.
- **[MESURE transposable]** — porte sur une propriété du *modèle* ou de la *recherche*
  (nombre d'évaluations, remplissage d'un lot, répartition du coût entre lancers), pas sur
  la vitesse d'un langage. Ces chiffres valent ici tels quels.
- **[HYPOTHÈSE]** — ce que j'en déduis, et qui reste à mesurer ici.

Le portage est bit-à-bit conforme (parité `verify/reference.bin` à **5,960e-08**,
inchangée après tout ce travail), donc les grandeurs *structurelles* qu'il rapporte —
combien d'évaluations, quels candidats, quel remplissage — sont celles de gammonNet, pas
celles d'un cousin.

---

## 1. La largeur de lot 32 pourrait être ce qui rend le regroupement nécessaire

**[MESURE transposable]** À largeur **8**, une décision 2-ply `(0,1,3)` `k=12` remplit
**84,3 %** des voies **sans aucun regroupement des vingt-et-un lancers**. Mesuré deux
fois : d'abord en simulant le lot avant qu'il n'existe (les candidats qu'une passe de
remplissage doit évaluer, arrondis au multiple de 8), puis en le décrivant une fois le
noyau branché. Les deux disent 84,3 %, à la décimale.

Ce chiffre est structurel : il ne dépend que du nombre de candidats qu'une passe de
remplissage a en main après retrait des positions terminales et des succès de cache — soit
`k=12` au plus dans la passe grand réseau. Douze candidats dans des tranches de 8 laissent
peu de vide ; dans des tranches de 32, ils en laissent beaucoup.

Or `T3A-regroupement.md` mesure ici, à largeur 32 : **14,5 %** de remplissage sans
regroupement, **80,5 %** avec. Le regroupement des 21 lancers a donc été construit pour
compenser une largeur, et il découpe `rank_plays` en trois phases pour cela
(`rank_plays_prune` / `_finish` / `_deepen`, `gn_search.c:568-849`).

**[HYPOTHÈSE, et c'est la question à trancher]** Si le débit crête est le même à 8 et à 32
voies, une largeur de 8 rendrait le regroupement inutile et permettrait de supprimer cette
machinerie. Deux éléments plaident pour, un contre :

- **Pour.** Sur Zen 3/4, `VMULPS` s'exécute sur FP0/FP1 et `VADDPS` sur des pipes
  **disjointes** FP2/FP3, débit réciproque 0,50 chacune. Le facteur limitant est le nombre
  de ports, pas la largeur du lot : 8 voies avec assez d'accumulateurs indépendants
  saturent autant que 32. Le portage Go, à largeur 8, obtient **17 µs par position** sur
  une fratrie de huit coups — à comparer aux 41 µs mesurés ici à largeur 32, sur une autre
  machine, donc sans conclusion directe.
- **Contre, et c'est sérieux.** `T3A-largeur-de-lot.md` mesure que **gcc ne vectorise la
  boucle chaude qu'à 32** (`-fopt-info-vec`), avec une falaise ×3,75 à 16. Ce n'est pas
  une propriété du matériel mais du compilateur, et le portage Go contourne le problème en
  écrivant l'assembleur à la main. **En C, tester la largeur 8 sans écrire d'intrinsèques
  reviendrait à tomber de la falaise** — la ligne « régler `GN_EVAL_BATCH` : 1,3 % au
  mieux » du registre reste donc juste *à noyau constant*.

La question n'est pas « 8 ou 32 » mais « le regroupement des 21 lancers gagne-t-il encore
sa complexité si le noyau était écrit en intrinsèques à 8 voies ». Elle n'est pas tranchée,
et elle mérite de l'être avant T73, qui réécrit ce noyau de toute façon.

## 2. La sparsité de la couche 1 rapporte moins que le registre ne l'annonce

Le registre la classe **priorité 1**, avec « ~15 % sur le grand réseau, ~78 % sur le
petit » (section 1). Le portage Go l'a implémentée — union des indices non nuls sur le lot,
compaction des poids dans un tampon contigu, exactement la forme d'ici
(`gn_infer_reference.c:342-360`).

**[MESURE Go]** Elle rapporte **~6 %** sur le lot que la recherche assemble réellement, et
elle **coûte 9 %** sur huit plateaux sans rapport.

L'écart avec les 15 % attendus tient à deux choses, et une seule est propre à Go :

- **Propre à Go.** La compaction coûte ~3,3 cycles par flottant déplacé et mange presque
  tout le gain arithmétique. En C, avec un `memcpy` par colonne, ce coût est probablement
  plus faible — **[HYPOTHÈSE]**, à mesurer ici.
- **Transposable.** L'union dépend de ce qu'on met dans le lot. Sur une **fratrie** — les
  coups d'un même lancer depuis une même position, ce que la recherche assemble — l'union
  vaut ~32 entrées actives sur 196. Sur huit plateaux **sans rapport**, elle monte à ~64,
  et le gain devient une perte. Le registre cite 38,3/196 pour une fratrie « ≤ 32
  positions » ; à huit, c'est ~32/196, donc légèrement mieux — et pourtant le gain net est
  faible.

**Conséquence méthodologique, elle transposable :** un banc qui évalue huit positions
**quelconques** sous-estime la sparsité d'un facteur deux et mesure autre chose que ce que
la recherche fait. Le portage a dû ajouter un banc « fratrie » distinct pour obtenir un
chiffre honnête. `bench/bench_batch.c` mérite la même distinction.

Rien ici n'invalide la priorité 1 du registre — le gain de 78 % sur le **petit** réseau,
dont la couche 1 pèse 97,5 %, n'a pas été mesuré côté Go, et c'est là que la sparsité
devrait le plus rendre. Mais l'estimation « ~15 % sur le grand réseau » est à revoir.

## 3. Précalculer les `metAfter` du videau ne vaut rien — et on sait maintenant pourquoi

Le portage a écrit puis **annulé** l'optimisation que son ADR-0011 annonçait : précalcul et
déduplication des consultations de la table d'équités de match, `probsExclusive` calculé
une fois au lieu de deux, courbe résolue hors de la boucle, copie de 150 octets supprimée,
bissections `tp`/`cp` entrelacées.

**[MESURE Go, mais la cause est transposable]** A/B dans le même processus, minimum de huit
relevés : **2 106 contre 2 126 ns, soit 1 %**, sous le plancher de bruit de la machine
(±15 %).

La décomposition, elle, porte sur la structure de `gn_cube.c` et vaut ici :

| | part de `build_levels` |
|---|---|
| consultations de la table d'équités | **11 %** |
| `level_solve` | **83 %** |

Chaque itération de bissection est **une division sur le chemin critique plus un
branchement imprévisible** (la comparaison qui choisit le demi-intervalle). Environ
60 cycles irréductibles par itération, 60 itérations, et ni le nombre d'itérations ni la
forme des segments ne peuvent bouger : le corpus de non-régression les fige.

**Ce qui marcherait**, et qui n'a pas été tenté : **valuer le videau par lot sur les
candidats**, exactement comme le réseau l'est. Les 60 bissections de chaque candidat sont
indépendantes, donc vectorisables sur la dimension des candidats — même figure que le
noyau, mêmes garanties d'exactitude si chaque voie garde sa propre séquence. Le poste vaut
~3,9 % d'une décision au score **avant** le noyau groupé, donc bien davantage après.

À ne pas rouvrir en revanche : « précalculer les consultations de la table ». C'est 11 %
d'un poste, et la mesure dit que cela ne se voit pas.

## 4. « Les doubles sont les lancers coûteux » est faux

**[MESURE transposable]** C'est l'intuition évidente, et elle est fausse. Les doubles
génèrent **1 800 coups contre 168** pour un lancer ordinaire, parce qu'ils placent jusqu'à
quatre demi-coups au lieu de deux. Mais :

- l'élagage n'en garde que `k` ;
- la position qu'ils laissent est **plus contrainte**, donc les réponses à approfondir sont
  moins nombreuses.

Résultat : **les doubles sont parmi les lancers les moins chers**, et l'écart total entre
lancers n'est que de **1,54×** en nombre d'évaluations.

Conséquence pour tout ordonnancement — le pool de Web Workers de `wasm/pool.mjs`, le
`ProcessPoolExecutor` de `python/gammonnet/arena.py` : trier les tâches par « doubles
d'abord » n'apporte rien, et peut nuire. Le portage a mesuré qu'un tri par coût décroissant
correct ne vaut que **~5 %** ; ce qui a payé, c'est **le nombre de tâches** — aplatir la
frontière pour présenter 63 tâches en une seule barrière au lieu de 21 tâches par barrière
a fait tomber l'oisiveté de ~15 % à 3-5 %.

Si un ordonnancement doit trier ici, la clé est le **nombre d'évaluations** (déterministe
et portable), jamais un temps mesuré ni un proxy sur le type de lancer.

## 5. Deux constats de contexte

**Le plafond n'est pas le code, c'est la mémoire. [MESURE Go, transposable en nature]**
Deux mesures indépendantes convergent : des décisions 2-ply *totalement indépendantes*
lancées en parallèle rendent **×3,98 sur 8 cœurs physiques**, et un lot de positions
analysées en parallèle rend **×4,08**. Le facteur est identique à 1-ply et à 2-ply alors
que le coût par position diffère d'un facteur 40, ce qui disculpe la synchronisation. La
cause : chaque fil fait passer les **mêmes 2,1 Mo de poids** dans un L3 partagé, sur une
puce mobile 15-28 W. Le multithreading simultané n'apporte rien au-delà des cœurs
physiques.

Cela vaut pour le parallélisme par processus d'ici comme pour le pool de Web Workers : le
nombre de workers utile est borné par les cœurs **physiques** et par la bande passante, pas
par `navigator.hardwareConcurrency`. À contre-mesurer sur une machine de bureau avant d'en
faire une règle.

**Un piège d'arrondi, si la largeur de lot cesse d'être une puissance de deux.** Le portage
a écrit `outDim & ^(tile-1)` pour arrondir au multiple inférieur. Cela n'est correct que
pour une puissance de deux ; à `tile = 6`, la boucle lisait une tuile de poids **hors
matrice**. Les tests ne l'ont pas vu parce que la tuile valait 4 au moment où ils ont été
écrits. `GN_EVAL_BATCH` vaut 32 ici, donc le code actuel est sauf — mais T73 déplace ces
tuiles.

---

## Ce que je n'ai pas mesuré, et qui reste ouvert ici

- La sparsité sur le **petit** réseau, là où le registre attend 78 %. Le portage la traite
  par le même chemin que le grand, sans mesure séparée.
- Le coût de la compaction **en C**, qui décide si le constat 2 vaut ici ou seulement en Go.
- La largeur 8 en C avec des intrinsèques, qui décide du constat 1.
- Les fiches T72 (distillation), T73 (int8) et T74 (élagage interne) restent entières :
  rien de ce travail ne les touche, puisque tout y était bit-à-bit conservateur.

Un point du registre est en revanche **confirmé par ailleurs** : une recherche
bibliographique menée de ce côté-là conclut que les **tables de transposition sur les
nœuds internes** et **Star1/Star2** entrent en conflit direct avec l'inférence par lots —
leurs dépendances séquentielles annulent le gain qui fait toute la vitesse d'un évaluateur
dense. La section 3 du registre les classe déjà « valeur inconnue, ne pas construire avant
ce chiffre » ; il y a maintenant une raison de penser que ce chiffre sera mauvais.

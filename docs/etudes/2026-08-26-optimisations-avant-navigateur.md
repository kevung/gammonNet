# Ce qui reste à gagner sans rien perdre en qualité

**Date** : 2026-08-26 · **Registre** : idées candidates, chacune avec sa mesure d'entrée

> **La contrainte.** Aller plus vite **sans dégrader l'analyse**. Cela exclut d'emblée tout ce qui
> échange de la qualité contre du temps — un `k` d'élagage plus serré, un filtre plus court, un
> réseau plus petit. Ne restent que les gains **exacts** (le résultat ne bouge pas d'un bit) ou
> **mesurés gratuits** (il bouge moins que le bruit, chiffré).
>
> Ce document n'implémente rien. Il classe les candidats par ce qu'ils valent **d'après une mesure
> d'entrée**, pas d'après une intuition, et dit pour chacun ce qu'il faudrait mesurer ensuite.

## Où va le temps aujourd'hui

Mesuré, mono-fil, machine calme, après le regroupement des lots :

| profondeur | s/décision | évaluations grand | évaluations petit |
|---|---|---|---|
| 2-ply `(0,1,3)`, `k=5` | 0,35 | 5 874 | 30 802 |
| 3-ply `(0,1,1,5)`, `k=5` | 12,2 | 227 574 | 1 146 566 |
| 4-ply `(0,1,1,1,5)`, `k=5` | **256,9** | 4 685 329 | **22 206 442** |
| 4-ply `(0,1,1,1,3)`, `k=3` | 100,1 | 1 742 039 | 14 038 324 |

**Le fait qui commande le classement** : plus on descend, plus c'est le **petit** réseau qui
domine — 5,2× le grand au 2-ply, 5,0× au 3-ply, **4,7× au 4-ply**. Toute optimisation du petit
réseau vaut donc quatre à cinq fois ce que vaut la même optimisation du grand.

## 1. La sparsité des entrées — exacte, mesurée, et la plus grosse

**L'idée.** Le vecteur de 196 caractéristiques est presque vide. Mesuré sur 4 000 positions de
vraie partie : **26,0 entrées non nulles sur 196 — 13,3 %**. La première couche multiplie donc
87 % de ses poids par zéro.

**Pourquoi c'est exact et pas une approximation.** En IEEE 754, `acc + w × 0.0` vaut `acc`
exactement, sans arrondi — tant qu'aucun `w` n'est infini ou NaN, ce que le format `.bin` exclut.
Sauter ces termes ne déplace pas un bit. Ce n'est pas de la quantification.

**Ce que ça vaut, mesuré à l'entrée.** Le noyau par lot est transposé (une caractéristique, trente-
deux voies), donc ce qui compte n'est pas la sparsité d'une position mais l'**union** sur la
fratrie évaluée ensemble. Mesurée sur 353 fratries réelles :

| | non nuls |
|---|---|
| une position seule | 27,7 / 196 |
| **union d'une fratrie (≤ 32 positions)** | **38,3 / 196 — 19,5 %** |

Les frères ne diffèrent que d'un coup : leurs entrées non nulles se recouvrent presque. **80,5 %
de la première couche est sautable, par lot.**

**Ce que ça rend, par réseau** — projection à partir des tailles de couches, ~~à mesurer~~
**mesurée le 2026-09-02, T89** :

| | première couche / total | gain **projeté** | gain **mesuré** (isolation, fratrie) |
|---|---|---|---|
| grand réseau (196→512→512→256→128→5) | 100 352 / 526 976 = 19,0 % | ~15 % | **×1,15** — confirmé |
| **petit réseau (196→32→5)** | 6 272 / 6 432 = **97,5 %** | ~~**~78 %**~~ | **×1,39 — le 78 % est RETIRÉ** |

~~Et comme le petit réseau fait quatre à cinq fois plus d'évaluations que le grand à toute
profondeur, c'est **le** candidat.~~

> **CORRIGÉ le 2026-09-02 — `docs/mesures/2026-09-02-T89-sparsite-par-reseau.md`.**
>
> Les deux affirmations barrées ci-dessus sont fausses, et de la même façon : elles supposent
> que le temps suit le nombre de multiplications. Mesuré, réseau par réseau, en A/B apparié
> par décision :
>
> - la sparsité rend **+39 %** au petit réseau en isolation, pas 78 % ; le reste de son
>   passage avant (transposition de 32×196, relevé des colonnes vivantes, sortie, sigmoïdes)
>   ne rétrécit pas avec l'union, et ses 25 Kio de poids tiennent en L1 ;
> - sur une **décision**, le petit réseau apporte **+2 %** et le grand **+10 %** — parce que
>   le petit, c'est 77 % des voies calculées mais **5 %** du temps : sa voie est bon marché.
>   Une optimisation du petit réseau ne vaut donc pas quatre à cinq fois celle du grand, elle
>   en vaut le **cinquième**.
>
> Le poste est **déjà livré** (`gn_infer_reference.c`, 2026-08-26) et **déjà rentabilisé** à
> +13 % sur une décision. Il n'y a pas de chantier « sparsité du petit réseau » à ouvrir.

**Et une distinction que ce registre ne faisait pas** : l'union dépend du **type de lot**.
Sur une **fratrie** elle vaut 40,5 / 196 (les 38,3 ci-dessus, confirmés) ; sur des positions
**quelconques** — ce que `bench/bench_batch.c` évalue — elle monte à **124,0 / 196** et le
gain tombe à ×1,04 sur les deux réseaux. Il ne devient jamais une **perte** ici, contrairement
au portage Go (−9 %), parce que la compaction est un `memcpy` par colonne et non ~3,3 cycles
par flottant.

**Ce qu'il faudrait mesurer ensuite** : le coût de la construction de la liste des indices non
nuls (elle se fait pendant la transposition, qui parcourt déjà les 196 caractéristiques). Les
projections ci-dessus supposaient que le temps suit le nombre de multiplications, ce que ce
dépôt a maintenant vu être faux **trois** fois.

## 2. Les filtres à seuil d'équité, comme gnubg — adaptatifs, pas dégradants

**L'idée, et elle vient de gnubg qui la publie** (`show rollout`) : il ne garde pas un nombre fixe
de coups, il garde *« les 8 meilleurs à moins de 0,16 d'équité »*. Nous gardons `filter[d] = 3`,
toujours trois, que la décision soit serrée ou évidente.

**Pourquoi c'est un gain sans perte.** Sur une position où le meilleur coup domine de 0,3
d'équité, un seuil garde **un** candidat là où nous en cherchons trois en profondeur — deux tiers
du travail profond économisés, et le même coup joué. Sur une position serrée, le seuil en garde
huit là où nous n'en gardons que trois : **on gagne en qualité là où ça compte**, et on paie
seulement là.

**Ce qu'il faudrait mesurer** : la distribution des écarts d'équité au sommet du classement
superficiel. Si les décisions serrées sont rares, le gain moyen est grand.

## 3. Une table de transposition sur les nœuds de recherche — exacte, valeur inconnue

**L'idée.** Le cache d'évaluation stocke des **feuilles** (les cinq probabilités d'une position).
Rien ne stocke `V(pos, profondeur)`. Deux chemins qui atteignent la même position à la même
profondeur la recalculent entièrement.

**Pourquoi c'est exact** : c'est la même valeur, par définition, à condition d'inclure dans la clé
tout ce dont `V` dépend — position, profondeur, état de match, propriétaire du videau. Une clé
incomplète serait un bug silencieux du genre le plus coûteux.

**Ce qu'il faudrait mesurer AVANT d'écrire quoi que ce soit** : le taux de répétition réel. Au
backgammon les transpositions sont rares à faible profondeur — des dés différents mènent à des
positions différentes. Une instrumentation d'une demi-journée (compter les `(position,
profondeur)` répétés pendant une décision) dit si l'idée vaut la peine. **Ne pas la construire
avant ce chiffre.**

## 4. L'élagage des nœuds de hasard (star1/star2) — exact, coûteux à écrire

**L'idée.** Un nœud de hasard fait la moyenne de 21 jets. Si l'on connaît des bornes sur la valeur
d'un coup, on peut prouver qu'un jet ne peut plus changer le maximum, et arrêter de l'explorer —
c'est l'alpha-bêta transposé aux nœuds de chance (Ballard, 1983 ; idée publiée).

**Exact** si les bornes sont saines. **Difficile à écrire correctement**, et le bénéfice dépend de
la largeur des bornes, que rien ici ne connaît. À garder pour après la sparsité, qui est plus
simple et mieux chiffrée.

## 5. float16 — pas exact, mais mesuré gratuit

Déjà mesuré (`docs/mesures/2026-08-04-quantification.md`) : ×1,99 sur la taille, **0,015 % des
décisions déplacées**, ~1e-9 d'équité — *« 1/100 000 du bruit »*. Ce n'est pas bit-exact, donc
hors de la contrainte stricte, mais c'est le seul gain de **bande passante** disponible, et la
bande passante est ce qui plafonne la machine (T35 : le débit agrégé sature à 11 ouvriers, pas
par manque de cœurs).

**Conséquence à ne pas escamoter** : il déplace les sorties du réseau, donc l'empreinte
d'évaluation qui verrouille les journaux T35. C'est un choix de format d'artefact, pas un réglage.

## Ce qui est fermé, et qu'il ne faut pas rouvrir

| idée | verdict, mesuré |
|---|---|
| régler `GN_EVAL_BATCH` | 1,3 % au mieux ; et gcc ne vectorise la boucle chaude qu'à 32 |
| **la largeur de lot, et le regroupement des 21 lancers** | **close pour de bon le 2026-09-02 (T84)** : à noyau écrit à la main, les largeurs 8, 16 et 32 tiennent en **11 %** ; passer de 32 à 8 coûte 3,3 % en natif et ne rend rien au navigateur. Le regroupement et la largeur 32 sont **conservés**. Ce qui décide n'est pas la largeur mais **le noyau** — ×1,81 natif, ×3,70 dans Chromium, à bit égal |
| fusionner les lots du **petit** réseau | 0,7–0,9 %, dans le bruit — branche abandonnée |
| regrouper les passes pour garder le petit réseau en cache | **2,2 % plus lent** |
| l'encodage | 0,00037 ms, 0,6 % d'une évaluation |
| le travail non-réseau de la recherche | ≤ 3,5 % d'une décision |
| dés quasi-aléatoires | variance ÷1,00 à 1 296 essais, ÷1,03 à 144 |
| la profondeur comme levier de **force** | +0,00022 d'équité par ply, dans le bruit (T36) |

## L'ordre que la mesure impose

1. ~~**La sparsité des entrées.** Exacte, chiffrée à l'entrée, et elle frappe le réseau qui
   domine.~~ **LIVRÉE le 2026-08-26, mesurée le 2026-09-02 (T89) : +13 % sur une décision,
   dont +10 % pour le grand réseau et +2 % pour le petit.** Elle ne « frappe pas le réseau qui
   domine » : le petit réseau domine les VOIES, pas le TEMPS. Rien à rouvrir.
2. **Les filtres à seuil.** Gain adaptatif, et il rapproche notre configuration de celle de gnubg,
   ce qui rend les comparaisons plus honnêtes.
3. **Mesurer** le taux de transposition avant d'envisager la table.
4. **float16**, comme format d'artefact navigateur, si tu l'acceptes.
5. star1/star2, en dernier : le plus dur pour le bénéfice le moins connu.

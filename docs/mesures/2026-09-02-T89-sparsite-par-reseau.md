# T89 — La sparsité, mesurée par réseau : le 78 % du registre est retiré

**Date** : 2026-09-02 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3, 8 cœurs
physiques / 16 fils, AVX2), 14,4 Gio, Linux 7.1.9-arch1-2 · **Chaîne** : gcc 16.2.1 ·
**Branche** : `feat/t84-noyau-largeur` · **Instrument** : `make bench-sparsity` (neuf)

> **Conditions, et elles sont mauvaises.** Deux autres chantiers tournaient sur la même
> machine. La charge moyenne a varié de **3,2 à 12,1** pendant la séance, et le débit absolu
> avec elle — le grand réseau a été lu entre **12 470 et 44 127 éval/s** pour exactement le
> même binaire, soit un facteur 3,5. **Aucune valeur absolue de ce document n'est
> exploitable.** Tous les chiffres retenus sont des **rapports mesurés dos à dos**, et le
> protocole ci-dessous existe précisément pour que ces rapports survivent à cette charge —
> ce qu'ils ont fait : le même rapport lu à charge 3,2 et à charge 12,1 diffère de 0,3 point.

## Ce que cette fiche sépare, et que personne n'avait séparé

La sparsité de la couche 1 est **livrée depuis le 2026-08-26** et vaut **×1,161**, mesuré A/B
dos à dos le 2026-09-02. Ce chiffre est celui des **deux réseaux ensemble**.

Le registre du 2026-08-26 (§1) projette, à partir du nombre de multiplications :

| | première couche / total | gain **projeté** |
|---|---|---|
| grand (196→512→512→256→128→5) | 19,0 % | ~15 % |
| **petit (196→32→5)** | **97,5 %** | **~78 %** |

Il le dit lui-même : *« les projections ci-dessus supposent que le temps suit le nombre de
multiplications, ce que ce dépôt a déjà vu être faux deux fois »*. Il l'a vu une troisième.

## Le protocole, et pourquoi il a fallu le refaire une fois

Le nouvel instrument (`bench/bench_sparsity.c`) éteint la compaction **réseau par réseau**,
via un drapeau porté par le `GnNetwork` sous `-DGN_BATCH_SPARSITY_SWITCH` — **compilé hors de
la bibliothèque livrée**, exactement comme `GN_BATCH_FILL_STATS` : la sparsité n'est pas une
option d'exécution, c'est le noyau. Le drapeau doit vivre sur le réseau et non dans un global
parce que `gn_search.c` tient les deux réseaux et les passe à `gn_evaluate_batch` sans dire
lequel est lequel.

**Première écriture, jetée.** La décomposition a d'abord été construite en chronométrant
quatre blocs indépendants (aucune / grand seul / petit seul / les deux) et en prenant les
rapports des médianes. Trois exécutions de cette forme ont donné, pour la **même** quantité,
**+2,1 %, +3,0 % et +8,2 %** — c'est-à-dire la dérive de la machine, pas le poste. Une
rotation de l'ordre des réglages ne suffisait pas.

**Ce qui marche : l'appariement par décision.** Chaque décision est chronométrée sous les
**deux** réglages coup sur coup, sur le même plateau et le même lancer, dans l'ordre
**A B B A** (le palindrome annule tout avantage de position). La statistique est la
**médiane des rapports par décision**, et non le rapport de deux médianes. Ce qui reste de
dérive est celle de quelques centaines de millisecondes.

## A. Le gain par réseau, en isolation

`gn_evaluate_batch`, lots pleins de 32 positions, A/B alterné dans la même passe, médiane de
7 à 9. Cinq exécutions, charge de 3,2 à 12,1 :

| réseau | type de lot | gain |
|---|---|---|
| grand | **fratrie** | ×1,129 / 1,137 / 1,153 / 1,158 / 1,160 → **×1,15** |
| grand | quelconques | ×1,027 / 1,030 / 1,030 / 1,053 → **×1,04** |
| **petit** | **fratrie** | ×1,371 / 1,372 / 1,385 / 1,391 / 1,393 → **×1,39** |
| petit | quelconques | ×1,023 / 1,035 / 1,036 / 1,042 / 1,085 → **×1,04** |

**Le registre est confirmé sur le grand réseau et faux d'un facteur deux sur le petit :**
~15 % projeté / **+15 % mesuré** d'un côté, **~78 % projeté / +39 % mesuré** de l'autre.

La cause est celle que le registre redoutait. Le passage avant du petit réseau à 32 voies
n'est pas fait que de multiplications : la transposition des 32×196 caractéristiques, le
relevé des colonnes vivantes, la couche de sortie et les cinq sigmoïdes ne rétrécissent pas
avec l'union. L'encodage seul pèse déjà **7,2 %** du chemin « position → sorties » du petit
réseau (mesure d'entrée §2), contre 1,4 % pour le grand. Ses 25 Kio de poids tiennent en L1 :
il n'y a pas de bande passante à économiser, seulement des multiplications, et elles ne sont
pas tout.

## B. La largeur de l'union — la distinction fratrie / quelconques, portée ici

Le noyau est transposé (une caractéristique, trente-deux voies) : ce qui compte n'est pas la
sparsité d'une position mais l'**union** sur le lot.

| type de lot | union moyenne | maximum |
|---|---|---|
| **fratrie** (les coups légaux d'un plateau et d'un lancer — ce que la recherche donne) | **40,5 / 196** | 44 |
| **quelconques** (des plateaux pris à sept plis d'écart — ce que `bench_batch.c` mesure) | **124,0 / 196** | 154 |

Les 40,5 confirment les **38,3** que le registre avait mesurés sur 353 fratries réelles.

**L'écart entre les deux types est le fait principal de cette section** : ×3,1 sur la largeur
de l'union, et le gain qui tombe de ×1,15/×1,39 à ×1,04. `bench/bench_batch.c` évalue des
positions quelconques, donc **il mesure autre chose que ce que la recherche fait** — la
distinction que le portage Go avait dû ajouter est reproduite ici et vaut de même.

**Une nuance, et elle va dans l'autre sens que le portage Go.** Sur des plateaux sans rapport,
le portage Go mesure une **perte de 9 %** ; ici le gain se réduit à ×1,04 mais **ne devient
jamais une perte**, même à union 124/196. C'est le même artefact de langage que la mesure
d'entrée §4 avait déjà identifié : la compaction coûte ~3,3 cycles par flottant en Go, et un
`memcpy` par colonne en C. Le mode de défaillance du portage Go n'existe pas ici.

## C. Ce que chaque réseau apporte à une **décision**

2-ply filtre `(0,1,3)`, `k=12`, A/B apparié, ordre A B B A, médiane des rapports par
décision. Cinq exécutions, charge de 3,2 à 12,1 (le s/décision absolu a varié de 0,48 à 1,61
entre elles ; les rapports, non) :

| | ex. 1 | ex. 2 | ex. 3 | ex. 4 | ex. 5 | retenu |
|---|---|---|---|---|---|---|
| ce que le **grand** apporte seul | +9,9 % | +10,5 % | +11,8 % | +14,7 % | +9,5 % | **+10 %** |
| ce que le **petit** apporte seul | +2,6 % | +2,4 % | +1,9 % | +1,4 % | +3,0 % | **+2 %** |
| les deux ensemble | +13,5 % | +12,3 % | +11,8 % | +14,4 % | +12,2 % | **+13 %** |
| **ce que le petit ajoute au grand** | +1,8 % | +2,5 % | +1,1 % | +4,4 % | +1,8 % | **+2 %** |

Les « deux ensemble » à **+13 %** recoupent le **×1,161** publié le 2026-09-02 : le poste est
le même, mesuré autrement.

**Le paradoxe apparent, et sa résolution.** Le petit réseau consomme **76,6 %** des voies
calculées à `k=12` (mesure d'entrée §3), et la sparsité lui rend **39 %** en isolation. Il
apporte pourtant **2 %** à une décision. Les deux sont vrais parce que sa voie est **bon
marché** : à `k=12`, 31 138 évaluations du petit à ~1,8 M éval/s font **17 ms**, contre
12 080 évaluations du grand à ~40 k éval/s, soit **300 ms**. Le petit réseau, c'est **5 %**
du temps d'une décision pour 77 % des voies. 39 % de 5 %, c'est 2 %.

C'est exactement la troisième fois que ce dépôt voit la prémisse « le temps suit le nombre
d'opérations » tomber. Le registre l'écrivait aussi à l'envers : *« toute optimisation du
petit réseau vaut quatre à cinq fois ce que vaut la même optimisation du grand »*, parce
qu'il fait quatre à cinq fois plus d'évaluations. **C'est faux dans les deux sens** : elle en
vaut le cinquième.

## Verdict

**Seuil d'abandon de T89 : moins de 5 % de gain supplémentaire sur une décision.** Mesuré
entre **+1,1 % et +4,4 %**, retenu **+2 %**, jamais au-dessus du seuil sur cinq exécutions.

> **Le chiffre de 78 % est RETIRÉ du registre du 2026-08-26.** La sparsité rend **+39 %** au
> petit réseau en isolation, pas 78 %, et **+2 %** à une décision. Le poste est **déjà livré
> et déjà rentabilisé** ; il n'y a pas de chantier « sparsité du petit réseau » à ouvrir, et
> la fiche se ferme sur ce constat.

Ce qui reste vrai et se publie :

- **par réseau** : ×1,15 sur le grand, ×1,39 sur le petit, en isolation sur des fratries ;
- **par type de lot** : ×1,15/×1,39 sur fratrie, ×1,04/×1,04 sur des positions quelconques,
  l'union passant de 40,5 à 124,0 entrées sur 196 ;
- **sur une décision** : +10 % pour le grand, +2 % pour le petit, +13 % ensemble ;
- la projection par nombre de MACs a surestimé le petit réseau **d'un facteur deux** et
  touché juste sur le grand.

## Reproduire

```bash
make bench-sparsity                        # 7 relevés, 12 décisions
make bench-sparsity REPS=9 DECISIONS=16    # plus long, moins bruité
```

Le binaire est compilé à part avec `-DGN_BATCH_SPARSITY_SWITCH` ; la bibliothèque livrée par
`make build` ne contient ni le drapeau, ni les compteurs, ni le branchement.

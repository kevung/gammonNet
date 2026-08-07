# T38 — Ce que la table exacte comble, et un arbitre sans variance

**Date** : 2026-08-06 · **Machine** : la machine de calcul · **Branche** : `t38-bearoff`

> T33 annonçait ce chiffre et ne l'avait pas produit : *« Mesurer l'écart réseau seul contre table
> exacte. C'est la valeur de cette tâche, et elle n'est pas encore connue. »* Il est connu.

## Le résultat

**8 000 décisions de bearoff sans contact**, chacune notée **exactement** par la table bilatérale
`gnubg-TS-06-11`. Aucune estimation, aucun rollout, aucune variance : la table donne l'équité de
tout coup légal, donc le meilleur coup et ce que le coup joué a coûté.

| moteur | accord avec le jeu parfait | perte moyenne / décision | si désaccord | pire |
|---|---|---|---|---|
| gammonNet 0-ply | 94,5 % | **0,00028** | 0,00501 | 0,0474 |
| gammonNet 1-ply | 95,3 % | **0,00020** | 0,00434 | 0,0919 |
| gammonNet 2-ply *(garde 1-5)* | 97,9 % | **0,00004** | 0,00182 | 0,0212 |
| GNU Backgammon 0-ply | 99,8 % | 0,00000 | 0,00043 | 0,0023 |
| GNU Backgammon 1-ply | 99,8 % | 0,00000 | 0,00041 | 0,0023 |
| GNU Backgammon 2-ply | **100,0 %** | **0,00000** | 0,00038 | 0,0009 |

## Ce que ce tableau compare réellement — et ce n'est pas ce qu'on croit

**Ce n'est pas réseau contre réseau.** GNU Backgammon embarque sa propre base de fin de partie et
la consulte ; sa quasi-perfection ici ne mesure pas la qualité de ses réseaux, elle mesure qu'il a
une table et que nous n'en avons pas branchée.

C'est donc exactement la quantité que T38 devait produire : **le trou qu'une table comblerait**,
soit **0,00028 point d'équité par décision de bearoff au 0-ply**.

Deux lectures s'ajoutent, et la seconde est la plus intéressante :

- **La recherche comble déjà l'essentiel du trou.** De 0-ply à 2-ply, la perte tombe de 0,00028 à
  0,00004 — un facteur sept. Le réseau seul est déjà bon en fin de partie ; c'est la queue de
  distribution qui coûte, et la profondeur la rattrape en grande partie.
- **Mais la queue reste.** Le pire cas de notre 1-ply vaut **0,0919** d'équité sur une seule
  décision, quand celui de gnubg plafonne à 0,0023. Une moyenne de 0,0002 cache des décisions où
  l'on se trompe de près d'un dixième de point. C'est précisément ce qu'une table exacte supprime,
  et ce qu'aucune profondeur de recherche ne garantit.

## Le domaine, et pourquoi il borne la conclusion

Ces chiffres portent sur le **bearoff sans contact** : au plus onze pions par camp, tous dans les
six premiers points, personne sur la barre. `BRIEF.md` §9 avertit qu'un corpus riche en fins de
partie flatte un moteur qui a des tables et punit celui qui n'en a pas — c'est exactement ce que ce
tableau montre, et ce serait le lire à l'envers que d'en tirer une force globale.

**Ce qui reste à faire pour clore T38** : brancher la table sur l'évaluateur, avec le repli
explicite sur le réseau hors domaine. Le lecteur et le prédicat d'appartenance existent et sont
testés ; le branchement dans `gn_search` ne l'est pas.

## L'autre livrable, qui dépasse T38

**Dans le domaine de la table, la difficulté centrale du projet disparaît.**

Partout ailleurs, affirmer qu'un moteur joue mieux qu'un autre demande un arbitre — des rollouts,
avec leur variance et la réserve qu'un rollout conduit par notre réseau nous favorise. Ici, rien de
tel : on lit le meilleur coup, on lit ce que le coup joué valait, la différence est exacte.

**Et le rendement de l'instrument est sans commune mesure avec celui d'un round-robin.** La
première lecture exploitable a coûté **quelques secondes** sur 400 décisions. Le round-robin de T36
demandait vingt-quatre heures pour douze mille parties, et aurait rendu ±0,017 — probablement « on
ne peut pas conclure ». Une partie ne rend **qu'un** point de donnée ; elle contient cinquante-cinq
décisions, et chacune d'elles est ici mesurée sans bruit.

C'est ce qui a fait changer l'instrument de T36. Voir `PLAN.md`.

## Comment le format a été établi

Sans lire une ligne du code de GNU Backgammon, et la provenance en sort meilleure. Le détail est
dans `python/gammonnet/bearoff.py` et au registre de [`docs/etudes/`](../etudes/) ; en résumé :

1. **L'arithmétique du fichier donne la structure** — `1 225 323 048` octets moins 40 d'en-tête font
   *exactement* `12 376 × 12 376 × 8`.
2. **L'en-tête est en clair** : `gnubg-TS-06-11-1`.
3. **`bearoffdump`**, outil documenté livré avec gnubg, sert d'oracle : il rend « Position 8 / 992 »
   pour l'index 100 000, et `8 × 12376 + 992 = 100000`.
4. **L'échelle a été ajustée** contre lui — `équité = brut/65535 × 2 − 1`, les quatre colonnes
   concordent.
5. **L'indexation a été validée exhaustivement** : la formule rend l'indice de gnubg sur les
   **12 376** positions, sans une exception. `C(6+11, 6) = 12 376` — le compte dit lui-même qu'il
   s'agit d'un rang combinatoire.

## Ce que cette tâche a coûté en fausses routes

Trois, toutes dues à des choses affirmées plutôt que mesurées, et toutes rattrapées par une mesure :

- **Un `id(play)` comme clé** sur une liste régénérée. A levé immédiatement — la bonne façon
  d'échouer.
- **La progression retirée en parallélisant.** Il a fallu deviner l'avancement d'un calcul d'une
  heure pour s'apercevoir qu'elle manquait. Remise.
- **Un 2-ply lancé sans filtre.** Un calcul dimensionné pour trente-cinq minutes en aurait pris
  dix heures ; il a tourné soixante-huit minutes avant d'être coupé. Le filtre est désormais
  explicite dans le code, avec la raison.

## Reproduire

```bash
python bench/exact_gap.py --decisions 8000 --plies 0,1,2 --workers 26 --with-gnubg
```

Sortie : [`t38-exact-gap.json`](t38-exact-gap.json). Durée mesurée : **5 min** sur 26 processus.
Prérequis : la base `gnubg_ts6x11.bd`, voir [`docs/prerequis.md`](../prerequis.md).

## Le branchement, et ce qu'il rapporte — 2026-08-07

Ce que la section précédente annonçait comme reste à faire est fait : `gn_search.c`
(`leaf_value`, la passe superficielle de `rank_plays`) et `gn_choose.c`
(`gn_best_play_0ply`) consultent désormais la table bilatérale — via un pointeur de
module réglé une fois par `gn_bearoff_set_shared` (`src/gn_bearoff.h`/`.c`) — avant
d'interroger le réseau sur une feuille. Par défaut le pointeur est `NULL` et rien ne
change : aucune régression n'a été refigée pour ce travail. Deux compteurs distincts
existent maintenant, `gn_bearoff_shared_hits()` et `gn_search_evaluations()`, et
`src/gn_search.c` prend soin de ne jamais compter une réponse de table comme une
évaluation réseau.

### La mesure : le trou se ferme

Même protocole que la section précédente — **8 000 décisions de bearoff**, notées
exactement par la table — mais avec `--with-table`, qui branche la table sur nos
moteurs (jamais sur GNU Backgammon, qui a déjà la sienne) avant la première
évaluation de chaque processus.

| moteur | perte moyenne **sans** table | perte moyenne **avec** table |
|---|---|---|
| gammonNet 0-ply | 0,00028 | **0,00000** |
| gammonNet 1-ply | 0,00020 | **0,00000** |
| gammonNet 2-ply *(garde 1-5)* | 0,00004 | **0,00000** |

**100,0 % d'accord avec le jeu parfait aux trois profondeurs, perte moyenne, perte en
cas de désaccord et pire cas tous exactement à 0,0** — colonnes complètes dans
[`t38-exact-gap-table.json`](t38-exact-gap-table.json). Ce n'est pas une amélioration
partielle : dans le domaine de la table, gammonNet joue désormais aussi bien que la
table elle-même le permet, au ply près, exactement comme GNU Backgammon dans la
mesure de référence — parce qu'il fait la même chose qu'elle, consulter une table
plutôt qu'estimer.

La mesure elle-même a pris **6 secondes** sur 26 processus, contre 5 minutes sans
table : une réponse de table est une lecture mémoire, une évaluation réseau est une
propagation avant à travers quatre couches.

### Le taux de hits

Sur 300 décisions de bearoff tirées dans le même domaine (`random_bearoff`), à
chaque profondeur, toutes les feuilles rencontrées sont tombées dans le domaine de
la table :

| profondeur | feuilles | hits de table | évaluations réseau | taux de hits |
|---|---|---|---|---|
| 0-ply | 1 320 | 1 320 | 0 | 100,00 % |
| 1-ply | 166 593 | 166 593 | 0 | 100,00 % |
| 2-ply *(garde 1-5)* | 1 644 308 | 1 644 308 | 0 | 100,00 % |

Ce n'est pas une coïncidence à expliquer : le domaine sans contact est fermé par
construction sous les coups légaux — un pion n'y fait que descendre vers la sortie,
jamais sortir des six premiers points ni faire remonter le nombre de pions d'un
camp — donc toute feuille atteinte depuis une position du domaine y reste, à une
exception près, la position terminale, qui n'est de toute façon ni évaluée ni
recherchée en table (elle est calculée, voir `gn_terminal_equity`). Un taux de hits
inférieur à 100 % sur ce protocole aurait signalé un bug d'appartenance plutôt
qu'un phénomène à interpréter — ce qu'il n'a pas fait.

### Ce que cette mesure ne dit pas

Le domaine reste celui de la section précédente : bearoff sans contact, au plus onze
pions par camp, tous dans les six premiers points. La table ne referme aucun trou en
contact — elle n'y répond jamais, `gn_bearoff_contains` la refuse — et un taux de
hits de 100 % ici ne dit rien du taux de hits sur une partie complète, où la plupart
des décisions se jouent hors de ce domaine. C'est une mesure, pas une hypothèse :
`docs/mesures/t38-exact-gap-table.json` en est la sortie brute.

**La table reste un actif natif, jamais un artefact de navigateur.** Le fichier fait
1,2 Gio ; il est ouvert par `mmap`, jamais chargé, et jamais compilé en WebAssembly.
`gn_bearoff_set_shared` ne s'active qu'explicitement, par configuration côté
appelant (`use_shared(path)` en Python, ou l'équivalent C) — un build ou un test qui
n'appelle jamais cette fonction ne sait même pas qu'elle existe.

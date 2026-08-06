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

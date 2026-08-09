# T35 — La répétition : 2 000 parties cubeful contre GNU Backgammon

**Date** : 2026-08-09 · **Machine** : le bureau (8 cœurs / 16 fils) · **Build** : `NATIVE_FP=1`,
empreinte `7c725e7f46afa9c7` (les deux chemins d'évaluation, scalaire et lot).

C'est la répétition que la fiche T35 rend obligatoire avant d'engager le volume : la
configuration cubeful complète, au réglage de campagne, sur 1 000 paires dupliquées — assez pour
révéler un défaut d'échelle du harnais, pas assez pour conclure sur la force.

## Protocole (l'en-tête du journal, qui le fige)

| | |
|---|---|
| Nous | `gammonnet-2ply-f0/1/3-cube2` — pions 2-ply garde 3, videau 2-ply, table exacte en domaine, x de T34 |
| Eux | `gnubg-2ply-f0/1/3-cube2` — pions 2-ply même garde racine, `prune=1`, videau `cfevaluate` 2-ply |
| Règles | money, Jacoby (décisions et décompte), pas de beaver, plafond 64 |
| Volume | 1 000 paires dupliquées = 2 000 parties, graine `20260810` |
| Journal | `docs/mesures/t35-repetition.jsonl` — relu intégralement par `bench/report_t35.py` |

Joué en **trois lots** (836 paires à 11 ouvriers, arrêt SIGINT propre, reprise à 9 ouvriers
`nice -n 10` — demande utilisateur de garder le bureau utilisable) : la segmentation de la
campagne a donc déjà servi en conditions réelles.

## Ce que la répétition devait vérifier — l'échelle du harnais

| Contrôle | Résultat |
|---|---|
| Parties bloquées à la limite de tours | **0** sur 2 000 |
| Videau | 2,89 doubles/paire ; plus gros videau **32** ; toutes les puissances de 2 présentes |
| Fins par pass | 886 parties (44,3 %) — l'ordre attendu d'un money cubeful |
| Longueur | 42,3 tours/partie en moyenne |
| Reprise après arrêt | 836 paires sautées exactement, aucun doublon d'index |

**Verdict : aucun défaut d'échelle visible.** Le harnais joue, double, encaisse, reprend.

## Le chiffre — et ce qu'il n'est PAS

**ppg cubeful : −0,059, IC 95 % [−0,199 ; +0,081]** (bootstrap sur les paires).

Deux mille parties ne concluent rien : l'intervalle contient zéro largement, et il contient
aussi bien −0,15 que +0,08. La répétition mesure la **variance**, pas la force.

## Ce que la variance mesurée dit du volume

Écart-type par paire dupliquée : **2,27 points** (contre ~0,6 en cubeless — le videau multiplie
les enjeux, et 44 % des parties se règlent par pass). Conséquence, en extrapolant en √n :

| Volume | IC 95 % attendu sur le ppg |
|---|---|
| 2 000 parties (fait) | ±0,140 |
| 20 000 parties | ±0,044 |
| **100 000 parties (la fiche)** | **±0,020** |

**L'amendement de la fiche (±0,0076 à 100 000 parties) reposait sur la variance cubeless de
T11 ; en cubeful l'intervalle réel sera ~±0,020.** Si l'écart vrai est de l'ordre du +0,040
de T11, 100 000 parties le sépareront de zéro ; s'il est petit, la fiche prévoit déjà la
suite — augmenter le volume, pas conclure quand même.

## Le débit — mesuré, plus d'hypothèse

| Réglage | paires/s | s/partie | 100 000 parties money |
|---|---|---|---|
| 11 ouvriers | 0,0843 | 5,9 | **~6,9 jours** |
| 9 ouvriers, `nice -n 10` (bureau utilisable) | 0,0605 | 8,3 | **~9,6 jours** |

En lots interruptibles — `--minutes`, `--limit`, Ctrl-C ou extinction : la reprise est exacte
et a été exercée ici même.

## Suite

La campagne money (50 000 paires, même journal ou journal dédié `t35-money.jsonl`), puis la
moitié match. La métrique PR reste un complément à brancher, pas un préalable.

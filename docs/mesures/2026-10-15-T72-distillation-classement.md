# 2026-10-15 — T72 : un terme de classement entre coups frères

**Nature** : des **mesures**, sauf ce qui est marqué *hypothèse*. Suite de
`2026-10-15-T72-courbe-volume-distillation.md`. Sa conclusion était que l'élève de la forme du
professeur plafonne à environ trois fois sa perte en décision, avec un écart de validation de
0,002 : ce n'est pas la capacité qui manque, c'est l'objectif.

**Hypothèse testée** : un objectif ponctuel répartit sa précision sur toutes les lignes, alors
qu'une décision ne demande que l'**ordre** des coups d'un même jet.

## Protocole

- **Corpus** : `tools/build_distill_corpus.py`, 60 M lignes (616 parts), graine 20261013,
  28 processus, ε = 0,1, mochy, 700 s.
  - Étiquettes : la sortie 0-ply du professeur `cubeless_prob5_512_512_256_256`.
  - Champ nouveau `decisions` : il regroupe les frères d'une même position et d'un même jet.
  - Contenu : 2 483 274 décisions d'au moins deux coups dans les 51,2 M lignes d'entraînement
    (20,6 frères en moyenne). Validation : 4 parts, 19 334 décisions.
- **Entraînement** : `tools/distill_rank_t72.py`, 51,2 M lignes, cosinus 1 000 époques, un
  RTX 4090 par entraînement. On garde l'époque de meilleure BCE de validation.
  - Perte = BCE(élève, professeur) sur des lignes tirées uniformément, plus
    λ·KL(softmax(s_prof/T) ‖ softmax(s_élève/T)) sur 512 décisions entières par pas.
  - `s` est l'équité cubeless de **celui qui joue** : l'étiquette est vue par l'adversaire, d'où
    le signe. Un test vérifie que le premier frère d'un groupe est le meilleur coup du
    professeur.
  - **λ = 0 donne la recette de la courbe volume, par le même code** : l'ablation tient en un
    seul paramètre, sur le même corpus.
- **Jauge** : `bench/measure_t70.py --dump`, registre T70 money de 10 000 décisions, 2-ply
  `(0,1,5)`, `prune_32` à `k=12`, 18 processus sur melbaa.
  - Comparaisons **appariées** décision par décision (`bench/paired_dumps_t70.py`), IC 95 %
    bootstrap 10 000.
  - Une décision hors registre d'un côté est écartée de l'appariement (≈ 5 %, compté à part).
  - Les deux références `t72c` remesurées redonnent leurs pertes publiées au dernier chiffre.

Données brutes : `t72-rang/` (JSON de jauge, sorties par décision `.dump.jsonl.gz`, paires,
résumés d'entraînement, SHA-256 des modèles).

## Résultats

### Perte T70 par décision (non appariée, pour situer)

| Élève | λ | T | Perte T70 | Écart de validation | Regret 0-ply (validation) |
|---|---|---|---|---|---|
| cible 256-128-64 (91 456 MACs) | 0 | — | 0,00860 [0,00806 ; 0,00914] | 0,00426 | 0,00325 |
| cible | 0,25 | 0,02 | 0,00779 [0,00729 ; 0,00831] | 0,00862 | 0,00160 |
| cible | 1 | 0,02 | 0,00788 [0,00737 ; 0,00840] | 0,01210 | 0,00138 |
| cible | 1 | 0,05 | 0,00780 [0,00728 ; 0,00833] | 0,00785 | 0,00137 |
| cible | 4 | 0,02 | 0,00776 [0,00727 ; 0,00827] | 0,01890 | 0,00145 |
| prof 512-512-256-256 (560 384 MACs) | 0 | — | 0,00777 [0,00723 ; 0,00834] | 0,00211 | 0,00103 |
| prof | 0,25 | 0,02 | 0,00759 [0,00708 ; 0,00813] | 0,00504 | 0,00085 |
| prof | 1 | 0,02 | 0,00747 [0,00696 ; 0,00799] | 0,00690 | 0,00085 |
| **professeur** | | | **0,00266** [0,00253 ; 0,00279] | | |

### Appariée (candidat − référence ; négatif = le candidat perd moins)

| Candidat | Référence | Δ | IC 95 % | z | Décisions appariées |
|---|---|---|---|---|---|
| cible λ = 0,25 | cible λ = 0 | **−0,00081** | [−0,00118 ; −0,00046] | −4,41 | 9 444 |
| cible λ = 1, T = 0,02 | cible λ = 0 | **−0,00070** | [−0,00109 ; −0,00031] | −3,45 | 9 449 |
| cible λ = 1, T = 0,05 | cible λ = 0 | **−0,00078** | [−0,00111 ; −0,00045] | −4,60 | 9 470 |
| cible λ = 4 | cible λ = 0 | **−0,00085** | [−0,00122 ; −0,00049] | −4,42 | 9 472 |
| prof λ = 1 | prof λ = 0 | **−0,00032** | [−0,00060 ; −0,00005] | −2,26 | 9 599 |
| prof λ = 0,25 | prof λ = 0 | −0,00017 | [−0,00045 ; +0,00009] | −1,25 | 9 610 |
| cible λ = 4 | prof λ = 0 | −0,00001 | [−0,00039 ; +0,00034] | −0,05 | 9 568 |
| cible λ = 0,25 | prof λ = 0 | −0,00001 | [−0,00037 ; +0,00033] | −0,06 | 9 547 |
| cible λ = 4 | prof λ = 1 | +0,00027 | [−0,00005 ; +0,00058] | +1,68 | 9 565 |

## Ce que ça dit

- **Sur la forme cible, le classement est un gain résolu** : de −0,0007 à −0,00085 par
  décision, z entre 3,5 et 4,6. Il est insensible à la dose entre λ = 0,25 et 4, et à la
  température entre 0,02 et 0,05.
- **L'élève cible avec classement égale l'élève prof ponctuel**, à ±0,00036 près, avec six fois
  moins de MACs. C'est le résultat utile pour la vitesse.
- **Sur la forme prof, le gain est plus faible** : −0,00032 à λ = 1, juste résolu ; non résolu
  à λ = 0,25.
- **Le plafond demeure** : le meilleur élève, prof λ = 1, perd 0,00747 contre 0,00266 pour le
  professeur, soit 2,8 fois. Le classement explique une partie du retard du petit élève. Il
  n'explique pas celui de l'élève à pleine capacité.
- **Le regret 0-ply n'est pas une boussole fiable de T70.** L'élève prof λ = 0 a un meilleur
  regret 0-ply que l'élève cible λ = 1 (0,00103 contre 0,00138), pour une perte T70
  indistinguable. Le classement dégrade aussi le calibrage absolu (écart de validation ×2 à
  ×4), dont le 2-ply a besoin pour moyenner des feuilles de parents différents.
- **Un biais possible, non chiffré** : la part de décisions hors registre baisse avec le
  classement (cible 3,9 % → 3,2 %). Les élèves avec classement jouent plus souvent un coup que
  le registre a arbitré. Ces décisions sont écartées de l'appariement, jamais comptées zéro.

## Ce que ça ne dit pas — *hypothèses*

- *Ce qui reste du plafond n'est pas dans l'ordre à 0-ply.* La recherche 2-ply compare des
  moyennes de feuilles issues de positions différentes. Une erreur de calibrage commune à ces
  feuilles ne se compense pas : il faudrait un objectif sur les valeurs **après** la recherche.
  Ce serait distiller le 2-ply, ce que vise T71. Non testé.
- Rien sur la force en partie : T70 est une perte par décision disputée, pas un PR.
- Aucun élève n'est proposé à l'adoption. Le réseau servi, l'épingle et l'artefact sont
  inchangés. Une adoption serait une décision du propriétaire, et demanderait d'abord la mesure
  du coût natif et navigateur de la forme cible.

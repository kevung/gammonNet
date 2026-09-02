# Registre des idées étudiées

> **À quoi sert ce répertoire.** `CLAUDE.md` autorise « lire le code et le manuel de GNU
> Backgammon » et « réimplémenter des idées documentées ». C'est juste, et c'est insuffisant seul :
> l'autorisation ne dit pas **comment s'y prendre pour que la position reste défendable** quand
> plus personne ne se souvient de ce qui a été lu, ni quand.
>
> Ce registre est cette mémoire. Il coûte quelques lignes par idée et vaut la différence entre
> « nous avons réimplémenté une idée publiée » et « nous ne savons plus ».

## Le fondement, en trois phrases

**La GPL est une licence de droit d'auteur.** Elle régit la copie, la distribution et les œuvres
dérivées. Elle ne régit ni la lecture ni l'apprentissage.

**Le droit d'auteur protège l'expression, pas l'idée.** Directive 2009/24/CE, art. 1(2) : *« Les
idées et principes qui sont à la base de quelque élément que ce soit d'un programme
d'ordinateur… ne sont pas protégés par le droit d'auteur au titre de la présente directive. »*
Côté américain, 17 U.S.C. §102(b) dit la même chose.

**La CJUE l'a tranché pour les programmes.** *SAS Institute c. World Programming*, C-406/10,
2 mai 2012 : la **fonctionnalité** d'un programme, le langage de programmation et le format des
fichiers de données ne constituent pas une forme d'expression protégeable.

Donc : comprendre *comment* GNU Backgammon décide de doubler, et le réimplémenter depuis cette
compréhension, est licite.

## Où passe réellement la frontière

Elle n'est pas là où l'intuition la place. Ce qui fait basculer dans l'œuvre dérivée :

| Sûr | À proscrire |
|---|---|
| L'algorithme, le principe, la structure mathématique | Le code transcrit — **y compris traduit dans un autre langage ou reformaté**. La paraphrase reste un dérivé |
| Ce que le manuel documente | La structure, la séquence et l'organisation d'une routine, quand elles ne sont pas dictées par les mathématiques |
| Les tables de fin de partie — calcul exact reproductible, tranché en T33 | Les **constantes réglées à la main** : seuils, présélections de filtres, coefficients d'efficacité de videau. Ce sont le produit du travail de réglage de quelqu'un |
| La table Kazaross-XG2, œuvre de N. Kazaross, attribuée | Les poids, y compris ceux des réseaux d'élagage |
| Les **sorties** de GNU Backgammon comme mesure (FSF, GPL FAQ) | GNU Backgammon comme **source d'entraînement** — distiller ses évaluations dans notre réseau. Interdit par T03 et `BRIEF.md` §3.5 |

> **Le dernier point mérite d'être dit à voix haute**, parce que c'est le raccourci tentant quand
> on cherche précisément à battre gnubg : la FSF considère que la sortie d'un programme n'est en
> général pas couverte par le droit d'auteur sur son code, ce qui rend l'usage comme **oracle de
> mesure** parfaitement clair. Mais ce projet s'est donné une règle plus stricte que le droit —
> gnubg est un instrument de mesure, **jamais** une source d'apprentissage. Cette règle tient.

**Et le vrai risque n'est pas juridique, il est probatoire.** Une fois qu'on a lu la source, une
accusation de copie devient facile à formuler et coûteuse à réfuter. La parade est la traçabilité.
D'où ce fichier.

## Le protocole — trois niveaux

### Niveau 1 — la littérature publiée. *À privilégier systématiquement.*

Pour le videau, elle couvre l'essentiel : Rick Janowski (*Take-Points in Money Games*, 1993, et son
modèle d'efficacité de videau), la dérivation des points de prise depuis une table d'équité de
match, les écrits de Woolsey, Trice et Kazaross.

**Citer *cette* source, et pas gnubg, quand c'est de là que vient l'idée.** C'est plus exact, et
plus défendable.

### Niveau 2 — le manuel et la documentation publique de GNU Backgammon.

De la documentation. Citable et exploitable sans réserve : elle décrit les filtres de coups, les
réseaux d'élagage, les réglages de videau.

### Niveau 3 — le code source. *En dernier recours, et sous protocole.*

1. **Jamais avec notre fichier correspondant ouvert.** La lecture et l'écriture ne se font pas
   dans la même séance.
2. Une **note en français** dans ce répertoire décrit le mécanisme compris, et dit où il a été lu.
3. **L'implémentation se fait depuis la note**, pas depuis l'écran.
4. **Aucune constante transcrite.** On la re-règle sur nos propres mesures, et le rapport le dit.
5. L'entrée est portée au registre ci-dessous.

> **Option renforcée, disponible à faible coût ici** : pour une brique où le risque de suivre le
> code de trop près est réel, un vrai *clean room* — un agent lit et rédige la spécification, un
> autre implémente dans un worktree séparé **sans jamais voir gnubg**. À décider brique par brique.

## Recommandation pour le videau — *2026-08-06*

**Ne pas lire la source de GNU Backgammon pour T34.**

Le modèle de Janowski et la dérivation des points de prise depuis la table d'équité de match sont
publiés, complets, et suffisent à écrire la fiche de bout en bout. Garder la composante la plus
délicate du projet entièrement traçable à de la littérature publique est un avantage net, et il est
gratuit.

Si une question résiste malgré la littérature, le niveau 3 reste ouvert — mais elle est alors
consignée ici comme une question précise, pas comme une lecture d'exploration.

---

## Le registre

> Une ligne par idée effectivement reprise. **Ce qui a été repris** est toujours une idée ; **ce
> qui ne l'a pas été** nomme explicitement le code et les constantes.

| Date | Idée | Niveau | Source | Repris | Non repris |
|---|---|---|---|---|---|
| 2026-08-03 | Filtrage de coups : ne descendre en profondeur que sur les N meilleurs du niveau précédent | 2 | [Manuel gnubg, réseaux d'élagage](https://www.gnu.org/software/gnubg/manual/html_node/Pruning-neural-networks.html) | Le mécanisme | Les présélections de filtres de gnubg. Les tailles de garde ont été **mesurées** en T31, pas reprises |
| 2026-08-03 | Architecture « réseau cubeless + conversion après par la table d'équité de match » | 2 | Manuel gnubg ; `BRIEF.md` §6 | Le principe d'architecture | Aucun code. La table est celle de Kazaross, attribuée |
| 2026-08-04 | Base de fin de partie unilatérale : distribution du nombre de jets par programmation dynamique | — | Calcul exact, tranché en T33 | Le calcul, refait de zéro | La table de gnubg a servi de **croisement**, pas de source |
| 2026-08-06 | Bases `gnubg-OS` et `gnubg-TS` employées telles quelles en natif | — | `CLAUDE.md` : tables de fin de partie, quelle que soit leur origine | Les fichiers, comme données de calcul exact | Elles ne partent pas dans l'artefact navigateur — actif natif et de mesure |
| 2026-08-06 | **Format binaire de la base bilatérale** — 4 × uint16, `équité = brut/65535 × 2 − 1` | **2** | Arithmétique du fichier + `bearoffdump`, outil documenté livré avec gnubg | Le format, **déduit puis vérifié** | Aucun code source consulté. L'échelle a été **ajustée** contre `bearoffdump`, pas transcrite |
| 2026-08-06 | **Indexation combinatoire des positions de bearoff** | **2** | `gnubg.positionbearoff`, API Python publique de gnubg | La formule, **redérivée** et validée exhaustivement sur les 12 376 positions | Aucun code. `C(6+11, 6) = 12 376` : le compte dit lui-même qu'il s'agit d'un rang combinatoire, construction mathématique |
| 2026-08-06 | **Mode Python de GNU Backgammon comme oracle** | **2** | `gnubg --python`, documenté dans son aide | L'usage de l'interpréteur embarqué, `evaluate` et `cfevaluate` | Rien n'est copié. C'est l'usage prévu de l'outil, et la FSF est explicite sur la sortie d'un programme |
| 2026-08-06 | Réseaux d'élagage : un petit réseau classe, le gros note les survivants | 2 | Manuel gnubg | L'idée seule — **pas encore implémentée** | Leurs poids d'élagage sont GPL. Le nôtre devra être distillé de **notre** réseau |

*(Ce tableau se complète au fil des fiches. Une idée reprise sans ligne ici est un manquement au
protocole, pas un oubli véniel.)*

### Une note de méthode — elle a servi trois fois le 2026-08-06

**Le niveau 3 n'a jamais été nécessaire.** Trois questions qui semblaient exiger la lecture du code
source — le format binaire d'une base de fin de partie, l'indexation de ses positions, la sémantique
d'une évaluation cubeful — ont toutes été résolues au niveau 2 : l'arithmétique du fichier, les
outils documentés livrés avec gnubg (`bearoffdump`, le mode `--python`), et une **validation
exhaustive** contre le programme lui-même.

Et la provenance en sort **meilleure** qu'après une lecture de source. On peut montrer que la
formule a été redérivée et vérifiée sur les 12 376 cas — un fait qu'un tiers peut refaire. « Nous
avons lu, puis réécrit de mémoire » ne se vérifie pas.

La règle à retenir avant d'ouvrir le niveau 3 la prochaine fois : **chercher d'abord si le
programme peut répondre lui-même à la question.** Il est livré avec des outils faits pour cela.

## Études d'opportunité

Ce répertoire accueille aussi les **études** — des dossiers qui instruisent une question avant
qu'une fiche existe. Une étude n'ouvre rien : elle donne à la décision de quoi se prendre.

| Date | Étude | Question | Statut |
|---|---|---|---|
| 2026-08-19 | [Le videau appris sans a priori](2026-08-19-videau-appris-sans-a-priori.md) | Peut-on apprendre la gestion du videau **en match** sans MET ni formule de Janowski, au niveau de gnubg ? | Dossier. Rien d'ouvert ; conditionné à T35 |
| 2026-08-19 | [Le videau appris — plan détaillé](2026-08-19-plan-videau-appris.md) | Quel programme, et l'architecture du réseau est-elle en cause ? | Plan conditionnel, fiches T60-T69. Rien d'ouvert |
| 2026-08-26 | [Dépasser franchement gnubg — plan de recherche](../recherche/00-plan-depasser-gnubg.md) | Que faudrait-il pour dépasser nettement gnubg **tout en étant aussi rapide** ? | Plan de quatorze recherches approfondies, en trois vagues. Rien d'ouvert |
| 2026-09-02 | [Retours du portage Go](2026-09-02-retours-du-portage-go.md) | Que le portage Go de blunderDB a-t-il mesuré qui déplace ce qui est écrit ici ? | Quatre constats : la largeur 32 pourrait être ce qui rend le regroupement nécessaire ; la sparsité couche 1 rapporte ~6 % et non ~15 % ; précalculer les `metAfter` du videau vaut 1 % et `level_solve` en pèse 83 % ; « les doubles sont chers » est faux (écart réel 1,54×). Rien d'ouvert ici |
| 2026-09-02 | [Optimiser pour le navigateur](2026-09-02-optimiser-pour-le-navigateur.md) | Où va le temps d'une décision, et qu'est-ce qui atteint réellement le navigateur ? | **Fiches T84–T90 ouvertes.** Mesures d'entrée prises sur la machine de bureau. Le videau au score pèse ~2 µs par nœud (T85) ; la sparsité vaut ×1,16 en C et non 6 % ; trois des six postes du chantier Go sont des artefacts de langage ; l'artefact WebAssembly sous-exporte, et sans T86 rien n'atteint le navigateur |

## Sources

- Directive 2009/24/CE, art. 1(2) — <https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32009L0024>
- CJUE, *SAS Institute c. World Programming*, C-406/10 — <https://curia.europa.eu/juris/liste.jsf?num=C-406/10>
- FSF, GPL FAQ, *output of a GPL program* — <https://www.gnu.org/licenses/gpl-faq.html#WhatCaseIsOutputGPL>
- Manuel de GNU Backgammon — <https://www.gnu.org/software/gnubg/manual/>
- R. Janowski, *Take-Points in Money Games*, 1993 — modèle d'efficacité de videau

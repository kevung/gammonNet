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

*(Ce tableau se complète au fil des fiches. Une idée reprise sans ligne ici est un manquement au
protocole, pas un oubli véniel.)*

## Sources

- Directive 2009/24/CE, art. 1(2) — <https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32009L0024>
- CJUE, *SAS Institute c. World Programming*, C-406/10 — <https://curia.europa.eu/juris/liste.jsf?num=C-406/10>
- FSF, GPL FAQ, *output of a GPL program* — <https://www.gnu.org/licenses/gpl-faq.html#WhatCaseIsOutputGPL>
- Manuel de GNU Backgammon — <https://www.gnu.org/software/gnubg/manual/>
- R. Janowski, *Take-Points in Money Games*, 1993 — modèle d'efficacité de videau

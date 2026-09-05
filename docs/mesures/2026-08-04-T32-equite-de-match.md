# T32 — L'équité de match, et deux intuitions que la table a démenties

**Date** : 2026-08-04 · **Machine** : bureau (piste B, déplacée le 2026-08-04) ·
**Branche** : `t32-met`

> Une table de 625 nombres ne se relit pas. Ce qui se vérifie, ce sont ses **propriétés**, et sa
> concordance avec une implémentation indépendante. Un chiffre faux dans une table d'équité de
> match ne fait rien planter : il fait prendre un videau qu'il fallait passer, une fois sur mille,
> et personne ne le voit jamais.

## ⚠️ Chiffres rejoués après le correctif des règles *(2026-08-04)*

Le correctif de la machine de calcul sur l'ordre des dés (`505b22e`) a fait diverger les corpus à graine fixe
— voir la note en tête du [rapport T30](2026-08-03-T30-recherche.md). Les mesures du branchement
de la table dans la recherche ont été rejouées :

| | avant | après |
|---|---|---|
| 2-away/2-away contre money | 44/755 — 5,8 % | **29/789 — 3,7 %** |
| 25-away/25-away contre money | 3/755 — 0,4 % | **2/789 — 0,3 %** |

**La paire de contrôles garde tout son sens** : la table change les décisions là où elle doit, et
ne les change pas là où elle ne doit pas. Les valeurs de la table elle-même, elles, ne dépendent
d'aucun corpus et n'ont pas bougé.

## Ce qui a été construit

| | |
|---|---|
| `src/gn_met_table.h` | La table Kazaross-XG2, **générée** — 25×25 pré-Crawford, 24 entrées post-Crawford |
| `src/gn_met.h` / `.c` | Le tableau de bord : `gn_met_pre`, `gn_met_post`, `gn_met_after`, et **`gn_match_winning_chance`** |
| `python/gammonnet/met.py` | `MatchState`, la liaison ctypes |
| `tests/test_met.py` | 15 tests |
| `data/met_kazaross_xg2.json` | L'export canonique des 650 valeurs, et son empreinte |

**La conversion appelle `gn_probs_exclusive`, elle ne la refait pas.** T10 avait trouvé que
dénester naïvement les cinq probabilités produit `P(perte simple) = −1,5e-10` sur une position
réelle du corpus. Cette fonction est **exactement l'appelant** qui aurait porté cette
probabilité négative dans une équité de match.

## Les critères

| Critère de `PLAN.md` | Résultat |
|---|---|
| Antisymétrie `MET[i][j] + MET[j][i] = 1` sur toute la table | **exacte** — `max\|Δ\| = 0` sur les 625 entrées |
| Point de prise près du money ~25 % | **25,20 %**, mesuré *dans la table* par dichotomie |
| Valeurs coïncidant avec une implémentation de référence | **max\|Δ\| < 1e-6** contre une transcription indépendante, sur 649 entrées |
| `THIRD-PARTY.md` porte l'attribution | ✅ à **Neil Kazaross** |

### Le contrôle croisé, en deux temps

**D'abord contre une transcription indépendante** — et ce n'était pas suffisant. Les 625
entrées coïncident, **mais c'est de là qu'elles venaient** : cela vérifie la transcription, pas
la table.

**Puis contre GNU Backgammon lui-même**, ce qui change la nature du contrôle. GNU Backgammon
1.08.003 est installé sur cette machine et se pilote sans interface
(`gnubg --tty --quiet --no-rc`). Il annonce :

```
Match equity table: Kazaross XG2 25 point MET
(/usr/local/share/gnubg/met/Kazaross-XG2.xml)
```

Comparaison des **649 entrées** contre ce fichier :

| | |
|---|---|
| Pré-Crawford, 625 entrées | **`max\|Δ\| = 0.000e+00`** |
| Post-Crawford, 24 entrées | **`max\|Δ\| = 0.000e+00`** |

**La table est Kazaross-XG2**, vérifié contre le rendu faisant autorité — celui que GNU Backgammon
charge, et donc celui contre lequel toute comparaison future se fera. Ce n'est plus « on a copié
juste », c'est « c'est bien la bonne table ».

**Et cela répond à une question que T03 m'avait explicitement léguée** : *« Quelle table c'est n'a
pas été établi ici […] c'est une affirmation à vérifier en T32. »*

### Une troncature héritée, corrigée

Le XML porte **25** entrées post-Crawford ; la transcription témoin s'arrête à **24**. La
vingt-cinquième vaut `0,001230` — le poursuivant à 25-away, quasi désespéré mais atteignable dans
un match de 25 points.

La source de `tools/extract_met.py` est donc passée au XML — et depuis, c'est la seule qu'il
lit : un témoin plus court que la source ne peut pas en tenir lieu. La troncature était sans
conséquence pratique, **et c'est exactement pour cela qu'elle serait passée
inaperçue**.

Ce qui éprouve la table, ce sont ses **propriétés**, et elles sont indépendantes de sa source :

- antisymétrie exacte, diagonale à 0,5 exactement ;
- **monotonie** — à adversaire fixé, être plus près de l'arrivée vaut mieux. Trivial à énoncer, et
  c'est justement pour ça : une inversion d'indices produirait une table parfaitement
  antisymétrique et pourtant retournée ;
- **dentelure pair/impair** du post-Crawford — une table lissée par erreur, ou décalée d'un cran,
  perdrait cette dentelure sans perdre sa monotonie ;
- le **point de prise**, calculé dans la table et non par une formule.

---

# Deux intuitions démenties par la table

Trois tests ont échoué au premier passage. Deux d'entre eux étaient **faux**, et la table avait
raison — c'est le genre de chose qu'un test écrit après coup, pour confirmer, n'aurait jamais
révélé.

## 1. « Le post-Crawford est pire pour le poursuivant » — l'inverse est vrai

J'avais écrit : *« être privé du videau coûte au poursuivant, c'est tout l'objet de la règle de
Crawford »*. Le raisonnement est juste ; il s'appliquait au mauvais couple d'états.

| poursuivant | post-Crawford | pré-Crawford `(a, 1)` |
|---|---|---|
| 1 | 0,50000 | 0,50000 |
| **2** | **0,48803** | **0,32264** |
| 3 | 0,32264 | 0,24924 |
| 4 | 0,31002 | 0,18564 |

`pre(a, 1)` **est** la partie de Crawford — l'unique partie où le poursuivant n'a pas le videau.
Une fois passée, **il le récupère**. À 2-away il redouble aussitôt, et une partie gagnée emporte le
match : 0,488, presque une pièce lancée en l'air. La règle de Crawford protège le meneur **une
partie**, pas tout le reste du match.

Le test dit maintenant la bonne propriété : `post(a) > pre(a, 1)` pour tout `a ≥ 2`.

## 2. « À 1-away contre 1-away le poursuivant est perdant » — non, c'est 0,5 exactement

Le test exigeait `< 0,5` pour toutes les entrées post-Crawford. La première vaut **0,50000**, et
elle a raison : à 1-away contre 1-away, il n'y a plus de match, il y a **une partie**. Le videau ne
sert à rien puisque tout est déjà en jeu.

## 3. Un exemple mal choisi — le mien, pas celui de la table

Pour montrer qu'un gammon vaut plus en match qu'en money, j'avais pris **2-away/4-away, videau à
2**. Le test a échoué, et il avait raison : **à ce score un gain simple marque déjà deux points et
gagne le match.** Le gammon n'ajoute rien, et seule `P(gain)` compte — l'évaluation sans gammons,
mieux gagnante, l'emportait légitimement.

Le bon exemple est **2-away/2-away, videau à 1** : un gain simple ramène à 1-away, un gammon marque
deux points et **emporte le match**. À équité money identique (`+0,200` pour les deux), la
distribution gammonnante rend **0,5645** contre **0,5355** — près de trois points de MWC d'écart.

> **C'est la démonstration de la raison d'être de `gn_infer.h`.** Ces deux évaluations ont la même
> équité money. Un moteur qui rendrait un scalaire les déclarerait équivalentes à tous les scores.
> La différence n'existe que si l'on a gardé la distribution.

---

## Ce qui est refusé plutôt qu'extrapolé

**Au-delà de 25 points**, `BRIEF.md` §3.3 prévoit un repli sur le modèle de Zadeh. **Il n'est pas
implémenté**, et c'est un écart au périmètre de la fiche, assumé :

- les matchs de plus de 25 points ne se jouent pas ;
- un chemin de code que rien n'exerce est un passif, pas une fonctionnalité ;
- `gn_match_state_is_valid` **refuse** ces états, et un seul endroit serait à changer si le repli
  devenait souhaitable.

Sont refusés de même : un videau qui n'est pas une puissance de deux — il mettrait toutes les mises
à l'échelle de travers, silencieusement — et un joueur à 0-away, qui a déjà gagné.

## ⚠️ `gnubg-nn` n'utilise pas cette table — un confondant pour T34 et T35

En vérifiant la nôtre, une autre question s'est posée : et celle de l'oracle ?

| | |
|---|---|
| `gnubg-nn` 1.1.0a9 contre Kazaross-XG2 | **`max\|Δ\| = 2,679e-02`** sur 625 entrées |
| Pire écart | 8-away contre 15-away : oracle `+0,562000`, Kazaross `+0,588794` |

**L'oracle de T03 ne joue pas avec la même table.** Ses valeurs sont en outre **quantifiées à trois
décimales**, signature d'une table publiée à la main plutôt que d'un produit de rollouts — laquelle
exactement reste à établir.

**C'est un confondant sérieux pour T34 et pour la moitié match de T35.** Une décision de videau se
joue sur des marges bien inférieures à 0,027 d'équité : comparer nos décisions à celles de
`gnubg-nn` mesurerait surtout l'écart entre les **tables**, pas entre les **modèles de videau**.

**La sortie est identifiée** : GNU Backgammon lui-même, qui charge Kazaross-XG2 par défaut — donc
la même table que nous — et qui est scriptable. C'est d'ailleurs l'une des trois pistes que T11
citait pour expliquer son propre écart, et cela en fait le décideur commun aux trois tâches.

## Ce que T32 débloque, et ce qui reste ouvert

`gn_search.h` porte depuis T30 un avertissement dans son en-tête : au niveau intermédiaire d'une
recherche 2-ply, **l'adversaire doit maximiser son équité de match**, pas son équité cubeless. Un
2-ply qui s'en dispense est **faux en match, et l'erreur est invisible en money** — donc invisible
à tout test qui n'utiliserait que du money.

**La table existe désormais ; le brancher dans la recherche reste à faire.** C'est le prochain
morceau, et il coûtera une consultation de table par nœud — négligeable devant une évaluation
réseau.

## Reproduire

```bash
pytest tests/test_met.py -v
python tools/extract_met.py     # régénère src/gn_met_table.h depuis Kazaross-XG2.xml
```

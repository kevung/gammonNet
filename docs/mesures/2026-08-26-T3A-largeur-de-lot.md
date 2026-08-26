# T3A — 39 % du travail réseau part dans des voies mortes, et la largeur n'y peut rien

**Date** : 2026-08-26 · **Machine** : la machine de calcul · **Branche** : `t3a-largeur`

> **La question.** La fiche du branchement a établi que le temps d'une décision ne suit pas la
> facture d'évaluations. En remontant, une explication candidate est apparue dans
> `gn_evaluate_batch` : *« Forward EXACTLY GN_EVAL_BATCH lanes, `live` of which carry positions ;
> the rest are zero-filled and discarded »*. Le noyau calcule donc toujours 32 positions, même
> quand la fratrie n'en compte que vingt. Combien se perd ainsi, et une autre largeur ferait-elle
> mieux ?
>
> **La réponse.** Il s'en perd **39 %** — mesuré. Et **aucune autre largeur ne fait mieux** : 24
> gagne 1,3 %, tout le reste est pire, parfois beaucoup. Le gâchis est structurel, pas un mauvais
> réglage. Résultat négatif, et c'est le point : cette avenue est fermée pour de bon.

## Le remplissage, mesuré

Instrumentation `-DGN_BATCH_FILL_STATS`, 20 décisions 2-ply filtre `(0,1,3)` :

```
35 201 appels, 684 874 voies vivantes
remplissage moyen 19,5 / 32 = 60,8 %
```

**Deux voies sur cinq calculent du zéro et le jettent.** La distribution est franchement
bimodale :

| taille de demande | appels |
|---|---|
| exactement 32 | **10 996** — 31 % des appels |
| 1 à 31 | 24 205, étalés à peu près uniformément |

Le pic à 32 n'est pas un hasard : la passe superficielle de `rank_plays` vide son tampon dès
qu'il atteint `GN_EVAL_BATCH`, donc toute fratrie d'au moins 32 coups produit des demandes
pleines, et le reste tombe où il tombe.

## Pourquoi une autre largeur ne rachète rien

Balayage complet, même corpus, même machine, charge inférieure à 1 :

| largeur | s/décision | |
|---|---|---|
| 8 | 5,4221 | |
| 16 | 7,5896 | reproduit deux fois : 7,5876 puis 7,5697 |
| **24** | **1,9954** | le meilleur — **1,3 %** devant |
| **32** *(actuelle)* | 2,0214 | |
| 48 | 2,1904 | |
| 64 | 4,4586 | |

**Réduire la largeur ne gagne rien parce que le pic à 32 se retourne contre elle** : à largeur 24,
une fratrie de 32 coups ne tient plus en une demande mais en deux — 48 voies calculées au lieu de
32. Ce que la largeur récupère sur les petites fratries, elle le reperd sur les grandes, et le
solde est de 1,3 %.

**L'effondrement à 8, 16 et 64 n'est pas expliqué.** Il est reproductible et il ne vient pas de la
charge machine, mais rien dans la lecture de `forward_batch` — un triple nid de boucles ordinaire,
compilé en `-O3` — ne le rend évident. Il est consigné comme observation, pas comme conclusion :
ce serait exactement le genre de cause inventée que la règle 3 de `CLAUDE.md` interdit.

## Ce que cela ferme, et ce que cela laisse ouvert

**Fermé** : régler `GN_EVAL_BATCH` autrement. Le gâchis de 39 % est réel mais il tient à la
**distribution des tailles de fratrie**, pas à un mauvais choix de constante.

**Laissé ouvert** : le supprimer demanderait de remplir les lots **à travers les nœuds** plutôt
qu'à l'intérieur d'un seul — c'est-à-dire de réordonner la recherche pour rassembler les positions
d'un même niveau avant de les évaluer. Non mesuré, et d'un tout autre coût en complexité : la
largeur fixe est le dispositif qui garantit l'invariance au découpage bit à bit
(`tests/test_batch.py`), et tout regroupement devrait la préserver.

**Un chiffre pour situer l'enjeu** : récupérer les 39 % rendrait au mieux la décision ×1,6 — plus
que ce que le réseau d'élagage a rapporté (×1,36), et dans la même famille de gains. Ce n'est pas
un levier de force, c'est un levier de budget.

## L'outil reste

`-DGN_BATCH_FILL_STATS` est conservé, éteint par défaut : il compte les appels, les voies
vivantes et l'histogramme des tailles de demande. Toute question future sur le remplissage se
mesure au lieu de se supposer.

```bash
make CFLAGS="-O2 -std=c11 -Wall -Wextra -fPIC -DGN_BATCH_FILL_STATS" bench-decision
```

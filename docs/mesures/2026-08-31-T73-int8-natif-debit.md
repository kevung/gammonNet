# 2026-08-31 — Le débit du chemin int8 NATIF à travers `gn_search.c`, et pourquoi il perd encore

## Ce que ce document mesure, et pourquoi c'est différent du précédent

`docs/mesures/2026-08-31-T73-int8-debit-taille.md` comparait
`Int8NetworkEngine.choose()` (le lot orchestré en Python,
`Int8Network.forward_batch`) à `NetworkEngine.choose()` (`gn_best_play_0ply`,
un chemin C dédié) : ×1,30, le seuil DS-09 franchi. **Ce résultat reste
valable** — mais il ne dit rien du câblage natif dans `gn_search.c`, qui est
un chemin différent (`rank_plays`, la boucle qui domine toute la recherche à
toute profondeur, batchée via `gn_evaluate_batch`).

Ce document compare `SearchEngine(ply=0, model=…)` pour les deux formats —
**le même appelant, `rank_plays`, pour les deux** — sur `melbaa` au repos.

## Le résultat

| | décisions/s |
|---|---|
| `SearchEngine` ply=0, float32 | 457,2 |
| `SearchEngine` ply=0, int8 (natif, tampons statiques) | 178,4 |
| rapport | **×0,39** |

**Le chemin int8, câblé nativement dans `gn_search.c` et exercé par la
recherche réelle, perd encore contre float32 — de manière stable, avant et
après avoir retiré le malloc/free par appel** (×0,39 dans les deux cas :
178,4 déc/s avant l'optimisation des tampons statiques, 178,4 après —
l'optimisation n'a rien changé).

## Pourquoi les tampons statiques n'ont rien changé — et ce qui compte à la place

Deux bugs mémoire réels ont été trouvés et corrigés en écrivant ce chemin
(voir le commit qui l'a introduit) : un pas d'indexation qui utilisait la
largeur allouée au lieu du lot réel, et des tampons dimensionnés sur la
mauvaise couche — les deux vérifiés sous AddressSanitizer. Remplacer le
malloc/free par appel par des tampons statiques (précédent déjà établi côté
float32, `g_batch_a`/`g_batch_b`) était l'hypothèse évidente pour le retard —
elle était fausse : le débit n'a pas bougé.

**Le débit réel des décisions explique le résultat.** Mesuré sur 500
décisions (`melbaa`) : médiane de **11 candidats distincts** par décision,
moyenne 20,7, et **37,8 % des décisions ont moins de 8 candidats** — le seuil
où `accumulate_lane` (`gn_gemm_int8.c`) bascule de sa boucle vectorisée
(8 voies par tour, SSE2) à sa queue scalaire. Le micro-banc DS-09 a déjà
mesuré ce régime : ×0,79 au lot 1, **int8 PERD** en dessous du lot où la
vectorisation s'amortit. Une décision réelle n'atteint que rarement le lot 32
où le noyau gagne ×2,13 — la plupart tombent dans la zone perdante ou à peine
rentable que le micro-banc avait déjà nommée, jamais mesurée en situation
jusqu'ici.

## Ce que `gn_search.c` lui-même dit de ce genre de surprise

Le fichier porte déjà, dans son propre commentaire sur `rank_plays`, deux cas
où un chiffre isolé a prédit le mauvais sens une fois confronté à la
recherche réelle (le petit réseau d'élagage, scalaire vs batché) — et
conclut : *« this file has now produced two of them that did not survive
contact with the real search »*. **En voici un troisième** : le lot 32 mesuré
isolément (×2,13) ne prédit pas le débit en recherche réelle (×0,39), parce
que la recherche ne présente pas des lots de 32.

## Ce qui a été prouvé au passage, malgré le résultat de débit

- **Bit-exact** : `gn_evaluate_features`/`gn_evaluate_batch` natifs collent à
  `Int8Network` (déjà vérifiée contre la simulation PyTorch de la QAT) à
  1e-7 près, sur un balayage de tailles de lot qui traverse les frontières de
  tronçon (31/32/33, un tronçon final partiel à 65/100).
- **`gn_search.c` n'a eu besoin d'aucune ligne changée** pour faire tourner
  une recherche 1-ply réelle sur le modèle int8 — le design à backend opaque
  de `gn_infer.h` a tenu sa promesse. `SearchEngine(ply=1,
  model="models/qat_int8.bin")` choisit un coup légal et plausible
  (`5/4 7/4` sur 3-1, une ouverture standard).

## Ce que ceci implique, sans le trancher ici

Le gain net du chemin int8 dépend de la LARGEUR RÉELLE des lots qu'une
recherche présente — pas du meilleur point du noyau. Deux pistes, ni l'une ni
l'autre engagée :

1. **Regrouper plusieurs DÉCISIONS**, pas seulement les candidats d'une
   seule — élargirait le lot au prix d'une restructuration de `gn_search.c`
   plus profonde que ce document n'a mesuré.
2. **Mesurer le point de croisement exact** (le lot à partir duquel int8
   dépasse float32 EN RECHERCHE RÉELLE, pas au micro-banc) — non fait ici.

Aucune conclusion de déploiement ne se tire de ce document au-delà de son
propre chiffre : ×0,39, à ply=0, sur `melbaa`, un seul modèle.

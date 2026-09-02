# 2026-08-31 — Le débit et la taille du chemin int8 déployé

## Le résultat

Mesuré sur `melbaa` (14 cœurs, au repos, charge 0,66), `bench/bench_int8_throughput.py`.

| | float32 (référence) | int8 (`Int8Network`, tel que déployé) | rapport |
|---|---|---|---|
| forward seul, 1 position à la fois | 1 845 éval/s | 433 éval/s | **×0,23** |
| décision complète (tous les candidats) | 83 décisions/s | 18 décisions/s | **×0,22** |
| taille des poids | 2 113 592 octets | 540 228 octets | **×3,91 plus petit** |

**Le chemin int8, tel qu'il existe aujourd'hui, est environ 4,5 fois PLUS
LENT que float32 — pas plus rapide.** Il est bien ~4 fois plus compact.

## Ce n'est pas une surprise — c'était déjà écrit dans le micro-banc

`bench_gemm_int8.c` (DS-09, T73) a mesuré le noyau à **deux** points de
fonctionnement : au lot du moteur (32), ×2,13 à ×2,23 — le chiffre cité pour
franchir le seuil d'abandon. Mais aussi, dans le même passage, **au lot 1 :
×0,79 — int8 PERD**. `Int8Network.forward` évalue une position à la fois,
quatre appels `ctypes` séparés par décision (`relu_pc` × 4 couches) : exactement
le régime où le micro-banc annonçait la perte, plus le coût de la traversée
`ctypes` elle-même, qui ne l'aide pas.

Le seuil DS-09 (franchi, ×1,30 minimum) a toujours porté sur le **lot 32**,
jamais sur le lot 1 — la campagne T73 ne s'est jamais trompée là-dessus. Ce
qui manquait est de mesurer ce que **ce projet** exécute *réellement*
aujourd'hui, pas seulement le noyau isolé à son meilleur point.

## Ce que ça implique

Le gain de débit promis par int8 n'existe qu'**avec le lot** — c'est-à-dire en
évaluant plusieurs candidats d'une même décision (ou plusieurs décisions) en
un seul aller-retour `gn_gemm_int8_relu_pc`, exactement comme
`gn_evaluate_batch` le fait déjà côté float32 (`GN_EVAL_BATCH = 32`,
`bench/bench_batch.c` : ×2,21 mesuré). `Int8Network`/`Int8NetworkEngine`
n'implémentent aucun lot aujourd'hui — chaque candidat est une décision
séparée. Câbler le lot est un changement contenu (le noyau C le supporte
déjà, `batch` est un paramètre, pas une constante) mais réel : il change la
forme de `Int8Network.forward` (une position → cinq probabilités) en
quelque chose comme `Int8Network.forward_batch` (N positions → N×5
probabilités), et `Int8NetworkEngine.choose` doit être réécrit pour
présenter tous les candidats d'une décision en un seul appel plutôt qu'en
boucle.

**Non fait ici** : c'est une fiche de taille comparable à celle qui a produit
`Int8NetworkEngine`, pas une extension de ce banc. Le nombre qui compte pour
la décider est déjà public : ×2,13 au lot 32 contre ×0,79 au lot 1, et rien
entre les deux n'a été mesuré.

## Ce que ceci ne dit pas

- Rien n'est mesuré sur un lot partiel (2, 4, 8, 16) — la courbe entre ×0,79
  et ×2,13 n'est pas connue pour CE chemin (elle l'est pour le noyau nu,
  `docs/mesures/2026-08-27-T73-etat.md` et le JSON du micro-banc).
- Le débit `ctypes` lui-même (le coût du passage Python↔C, indépendant du
  noyau) n'est pas isolé — il fait partie du nombre mesuré, pas soustrait.
- Aucune mesure WebAssembly : `Int8Network` est un chemin Python natif, pas
  câblé dans `gn_wasm.c`.

## Mise à jour — le lot, câblé (2026-08-31, même jour)

`Int8Network.forward_batch` (un seul aller-retour `gn_gemm_int8_relu_pc` par
couche pour TOUS les candidats d'une décision, dédupliqués par résultat) et
`Int8NetworkEngine.choose` réécrit pour l'utiliser plutôt que boucler sur
`forward`. Bit-exact contre `forward` (testé : `forward_batch` sur N
positions rend exactement ce que N appels à `forward` rendraient).

Remesuré sur `melbaa`, mêmes conditions :

| | float32 | int8 (avec lot) | rapport |
|---|---|---|---|
| décision complète | 83 décisions/s | **108 décisions/s** | **×1,30** |

**Le seuil DS-09 (×1,30) est franchi en situation réelle, pas seulement au
banc du noyau nu.** `forward` seul (une position à la fois, sans lot) reste
inchangé à ×0,24 — c'est attendu et documenté plus haut : c'est
`forward_batch`, pas `forward`, qui est le chemin réellement rapide.

Un garde-fou du noyau est apparu en le mesurant : l'accumulateur de
`gn_gemm_int8_relu_pc` plafonne un lot à 256 (`int32_t[256]`, un plafond du
noyau, pas un réglage). Sur les 500 décisions de la marche aléatoire de ce
banc, **une** en a demandé 305 avant déduplication — la marche navigue vers
des positions qu'aucune partie réelle ne visite (aucune politique ne la
guide), pas un cas qui inquiète en jeu réel. `Int8NetworkEngine.choose`
déduplique déjà par résultat (plusieurs ordres de coups aboutissent souvent
à la même position, surtout aux doubles) ; le banc écarte simplement les
décisions qui dépassent encore le plafond après déduplication, et le dit.

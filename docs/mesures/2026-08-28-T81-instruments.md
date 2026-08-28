# T81/T82 — les instruments de falsification, passés sur la pile classique

**Date** : 2026-08-28 · **Banc** : `bench/instruments_t81.py` ·
**Données** : `docs/mesures/t81-instruments.json` · **Aucun poids entraîné.**

> **Ce que cette mesure établit** : les cinq instruments retrouvent ce qu'on sait déjà, donc ils
> sont utilisables sur un modèle appris. Et une quantité neuve tombe au passage — le **résidu de
> point fixe** de la pile classique, qui n'avait jamais été mesuré ici.

## 1. Les contrôles — la réponse était connue d'avance

| Contrôle | Attendu | Mesuré |
|---|---|---|
| Balayage du point de caisse contre la forme fermée `gn_cube_take_point` | identité | pire écart **3,0e-08** |
| Point de prise à videau **mort** (`x = 0`) | 0,25 — Janowski (1993) | **0,250000** |
| Point de prise à videau **vivant** (`x = 1`) | 0,20 — Janowski (1993) | **0,200000** |
| Antisymétrie `MWC(a,b) + MWC(b,a) = 1` | exacte | écart **0** |
| Monotonies en `away` (les deux sens) | exactes | écart **0** |
| Identité DMP à 1-away/1-away (les gammons ne valent rien) | exacte | écart **0** |
| Pivot -2/-1 Crawford | 32,31 % (Rockwell-Kazaross, DS-08 §B.2) | **32,26 %**, écart 4,6e-04 |
| Signature de parité du free drop dans la ligne post-Crawford | présente | présente partout |

Le balayage **n'interroge jamais le moteur sur son point de prise** : il regarde où le verdict
bascule. C'est ce qui le rend applicable tel quel à un modèle appris, qui n'a pas de point de
prise à déclarer.

La signature du free drop mérite d'être écrite, parce qu'elle est un *rythme* et non une valeur :
descendre d'un `away` impair au pair suivant coûte peu au poursuivant, descendre du pair à
l'impair suivant lui coûte beaucoup.

| `away` du poursuivant | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| MWC post-Crawford | 0,5000 | 0,4880 | 0,3226 | 0,3100 | 0,1901 | 0,1807 |
| coût du pas précédent | — | **0,0120** | 0,1654 | **0,0126** | 0,1199 | **0,0094** |

La fiche T82 exige que le modèle appris **trouve** le free drop. Le repère existe : c'est cette
alternance.

## 2. La mesure neuve — le résidu de point fixe

`MET(a,b)` est, par définition, la MWC du joueur au trait **au début d'une partie**. La pile
classique devrait donc rendre la cellule quand on lui demande d'évaluer la position initiale à ce
score. Elle ne la rend pas, et l'écart est le résidu de point fixe.

Évaluation de la position initiale par `cubeless_prob5_512_512_256_128` :
P(gain) 0,5136 · P(gammon) 0,1452 · P(gammon subi) 0,1334.

| Extraction | Écart absolu moyen | Cellules > 0,005 (sur 625) | Pire cellule |
|---|---|---|---|
| **cubeless** (les 5 probabilités converties par la table) | 0,00365 | **116** | 2-away/4-away, **+0,0538** |
| **cubeful** (Janowski aux `x` mesurés, videau centré) | 0,00302 | **35** | 2-away/1-away, **+0,1241** |

Trois faits, et pas un de plus :

1. **Le résidu moyen ne bouge presque pas** — 1,21×. Brancher le videau ne rapproche pas le moteur
   de la table en moyenne.
2. **Le désaccord large s'effondre** : 116 cellules au-delà du seuil annoncé passent à 35. Le
   videau explique le désaccord *large*, pas le désaccord *moyen*.
3. **La queue empire.** La pire cellule passe de +0,0538 (2-away/4-away, cubeless) à **+0,1241**
   (2-away/1-away, cubeful) — douze points de pourcentage de MWC, à un score où le videau est
   pratiquement forcé.

Le point 3 est un **désaccord à arbitrer par rollout de match, pas à expliquer** (règle T82). Il
est signalé, pas interprété : ni « la table a tort » ni « le moteur a tort » n'est établi ici.

## 3. Ce que ces chiffres servent

Ils ne disent rien sur un modèle appris — aucun n'existe. Ils donnent le **repère sans lequel son
propre écart à la table ne voudrait rien dire**. Un modèle appris de T82 qui rendrait un résidu
moyen de 0,003 ne serait ni bon ni mauvais dans l'absolu : il serait *au niveau de la pile
classique*. C'est cette phrase-là qu'on ne pouvait pas écrire avant aujourd'hui.

**Réserve de méthode** : le seuil de 0,005 est annoncé d'avance mais arbitraire ; il sépare, il ne
juge pas. Et Kazaross-XG2 est ici un **instrument**, jamais une entrée — rien de la table n'entre
dans des poids ni dans l'artefact distribué.

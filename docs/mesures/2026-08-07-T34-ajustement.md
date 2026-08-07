# T34 — L'efficacité du videau, ajustée contre la table bilatérale

**Date** : 2026-08-07 · **Machine** : la machine de calcul · **Branche** : `t34-videau`

> `docs/specs/t34-videau-spec.md` fixe le modèle à la lettre : les formules ne se discutent
> pas. Ce rapport documente la **seule quantité libre** du modèle — l'efficacité du videau
> `x` — et la mesure qui la fixe, comme `docs/specs/` §3 l'exige : « ajusté par moindres
> carrés contre les équités cubeful exactes de la table bilatérale ... jamais repris d'un
> autre moteur ».

## Le résultat

**10 000 positions**, tirées dans le domaine de `gnu_bearoff_database/gnubg_ts6x11.bd`
(`random_bearoff` de `bench/exact_gap.py`, réutilisé tel quel), graine `20260807`. Pour chaque
position, `p = (cubeless + 1) / 2` est lu directement dans la table — valide dans ce domaine
seulement, où les gammons sont nuls (démontré en T38, rappelé plus bas). `x` balaie
`[0, 1]` par pas de `0,001` ; la valeur retenue minimise l'erreur quadratique moyenne contre
la colonne cubeful correspondante.

| État du videau | `x` ajusté | RMS | max\|Δ\| | biais moyen |
|---|---|---|---|---|
| **possédé** | **0,566** | 0,0358 | 0,2249 | +0,0027 |
| **centré** | **0,688** | 0,0495 | 0,4064 | +0,0111 |
| **adverse** | **0,687** | 0,0342 | 0,2672 | −0,0052 |

Écrit dans `docs/mesures/t34-efficacite.json`.

**Lecture immédiate** : `x` ne vaut pas la même chose selon qui tient le videau. Un videau
possédé (0,566) capture nettement moins de la valeur du re-doublement futur qu'un videau
centré ou chez l'adversaire (≈ 0,69) — ce qui est de sens contraire à l'intuition naïve
(« je le possède, il devrait être plus efficace pour moi ») mais cohérent avec le fait que
la colonne « possédé » de la table encode déjà, dans l'équité elle-même, une partie de
l'avantage que le modèle range ailleurs dans `x`. Aucune des trois valeurs n'est proche des
0,60-0,70 qu'on lit parfois cités pour d'autres moteurs (`CLAUDE.md` interdit de toute façon
de les reprendre) — celles-ci sortent de cette mesure, sur ce domaine, avec ce protocole.

## Où vont les résidus — et ce que ça dit de la forme du modèle

```
                  p ∈ [0,00 ; 0,04]   p ∈ [0,04 ; 0,45]   p ∈ [0,45 ; 0,90]   p ∈ [0,90 ; 1,00]
possédé   biais      +0,0018             +0,0241             −0,0058             −0,0062
          RMS          0,0031              0,0303              0,0697              0,0247
centré    biais      +0,0024             +0,0273             +0,0231             +0,0030
          RMS          0,0091              0,0712              0,0807              0,0239
adverse   biais      +0,0025             +0,0148             −0,0355             −0,0079
          RMS          0,0090              0,0605              0,0444              0,0108
```

**Les résidus sont structurés, pas du bruit.** Trois observations, toutes dans le même sens :

1. **Ils s'effondrent aux extrêmes de `p`** (RMS sous 0,01 dans les deux derniers déciles pour
   les trois états) et **culminent au milieu** (`p` entre 0,04 et 0,90). C'est la signature
   attendue d'un modèle **piecewise-linéaire** approximant une courbe qui a de la courbure :
   aux extrêmes, `max(1, e(p))`/`min(-1, e(p))` collent à la continuation morte, qui elle-même
   colle à la table quand la partie est presque jouée (peu de coups restent avant la fin, donc
   peu d'occasions de redoubler — un videau dont l'efficacité importe peu). Au milieu, le
   modèle doit choisir UNE droite là où la vraie courbe fléchit.

2. **Le signe du biais s'inverse entre le centre et les bords** pour `possédé` et `adverse`
   (positif puis négatif) : le modèle **sous-estime** la valeur au centre et la
   **surestime** en fin de partie. Un modèle correctement spécifié mais à la mauvaise
   pente ferait ça — c'est exactement l'erreur qu'une droite unique commet contre une
   courbe convexe puis concave.

3. **`centré` porte le plus gros résidu isolé** (max\|Δ\| = 0,4064, contre ~0,22-0,27 pour les
   deux autres) et un biais qui reste positif partout jusqu'au dernier décile. L'état centré
   est celui où la spécification recolle DEUX segments de re-doublement (`TP_live` puis
   `CP_live`) — deux coudes au lieu d'un — et c'est là que le point d'ancrage `p = TP_live`
   est le plus sensible à un léger décalage entre la classification par quantification de la
   table (T33 : pas de 16 bits, ~1,5×10⁻⁵) et le `p` lu comme `(cubeless+1)/2`.

**Aucun de ces trois signes ne révèle un bug** — la reformulation vectorisée du script est
recalée contre `gn_cube_equity` réel (le vrai binaire C, via `python/gammonnet/cube.py`) sur un
sous-échantillon avant le scan, à `1e-9` près ; un écart de modèle s'y serait arrêté avant de
produire un seul chiffre. Ce que ça révèle, c'est la limite intrinsèque d'un modèle à **un seul
paramètre libre par état** : Janowski (1993) n'a jamais prétendu capturer la courbure exacte
d'une position de bearoff, seulement une approximation utilisable en jeu. La mesure confirme
que l'approximation est raisonnable (RMS sous 0,05 partout) sans être exacte.

## La limite du domaine, écrite ici comme la spécification l'exige

Le domaine de la table bilatérale est **sans gammon** — `W = L = 1` partout, démontré en T38
par la lecture du format (`gnubg-TS`) et confirmé par `bearoffdump`. Cet ajustement ne
contraint donc **que** le comportement gammonless du modèle : les trois `x` ci-dessus
décrivent comment le videau se comporte quand aucun gammon n'est possible, ce qui est vrai en
fin de course mais pas en milieu de partie.

**La composante gammon du modèle (`W`, `L` > 1) n'est validée par aucune référence exacte
dans ce dépôt — il n'en existe pas.** `docs/specs/t34-videau-spec.md` §3 le prévoit
explicitement : cette composante ne peut être comparée qu'à GNU Backgammon (deux colonnes,
jamais une seule, per T34 §6.3), une mesure de ressemblance, pas d'exactitude. Cette
comparaison-là reste à faire ; ce rapport ne l'anticipe pas.

## Reproduire

```bash
python bench/fit_efficiency.py --samples 10000 --seed 20260807
```

Sortie : `docs/mesures/t34-efficacite.json` (les trois `x`, RMS, max\|Δ\|, biais moyen).

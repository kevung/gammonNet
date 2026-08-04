# T31 — le filtre se comporte-t-il autrement en match ? Non.

**Date** : 2026-08-04 · **Machine** : bureau (piste B) · **Branche** : `t31-match`

> Le rapport de T31 chiffre le coût du filtre en **money** et pose sa propre limite : *« tout ceci
> est mesuré en money — un filtre devra être revérifié en match après T32 »*. T32 est faite, la
> table est branchée dans la recherche, et cette vérification devient possible.

## Le résultat

121 décisions — les mêmes que la référence de T31 — à **1-ply**, taux de désaccord avec la
recherche non filtrée **au même score** :

| garde | money | 2-away / 2-away | 4-away / 2-away | 2-away / 4-away | 25 / 25 *(témoin)* |
|---|---|---|---|---|---|
| 1 | 21,49 % | 23,14 % | 22,31 % | 20,66 % | 21,49 % |
| **3** | **3,31 %** | **3,31 %** | **3,31 %** | **2,48 %** | **3,31 %** |
| 5 | 0,00 % | 0,00 % | 0,00 % | 0,00 % | 0,00 % |

> **Le taux de désaccord ne bouge pas quand le score entre en jeu.** Le filtre se transporte du
> money au match sans se dégrader.

**Mon hypothèse n'est pas confirmée, et c'est le résultat.** J'attendais l'inverse : le filtre garde
les `k` meilleurs d'un **pré-tri**, et ce pré-tri classe par équité cubeless en money, par équité de
match en match. À 2-away/2-away un gammon emporte le match, donc un coup gammonnant relégué au
sixième rang par le tri money pouvait être le bon. **La mesure dit que le pré-tri classe assez
semblablement pour que cela ne morde pas** — au moins à partir de trois candidats gardés.

Les décomptes ne sont pas identiques d'un score à l'autre — 26, 28, 27, 25, 26 désaccords à la
garde 1 — donc la recherche **tient bien compte du score** ; ce sont les *taux* qui coïncident, pas
les décisions. Sans cette vérification, une égalité parfaite aurait signalé un score ignoré.

## Le contrôle qui valide la méthode, et que je n'avais pas prévu

Le rapport annonçait le 1-ply comme un **indicateur** du 2-ply, sans le démontrer. La colonne money
le démontre :

| garde | ce rapport, **1-ply** | T31, **2-ply** |
|---|---|---|
| 1 | 21,49 % | 20,66 % |
| 3 | 3,31 % | 2,63 % |
| 5 | 0,00 % | 0,00 % |

Les deux profondeurs donnent le même comportement de filtre à moins d'un point de pourcentage
près. **C'est ce qui autorise à lire les colonnes de score comme un indicateur du 2-ply**, et non
plus seulement à l'espérer.

## Ce que la colonne « perte » ne dit pas

| garde | money | 2-away / 2-away | 25 / 25 |
|---|---|---|---|
| 1 | 0,02818 | 0,01219 | 0,00175 |

**Ces trois nombres ne se comparent pas.** La ligne money est en **points**, les lignes de score en
**équité de match** (`2·MWC − 1`). À 25-away/25-away un point de money ne déplace presque pas
l'équité de match, d'où le 0,00175 — ce n'est pas un filtre qui coûterait moins cher, c'est une
autre unité.

**C'est le taux de désaccord qui se lit d'une ligne à l'autre**, parce qu'il est sans dimension.
Une lecture verticale de la colonne « perte » conclurait que le filtre devient gratuit dans les
matchs longs, ce qui serait faux.

Pour fixer un ordre de grandeur là où la conversion a un sens : à **2-away/2-away, garder trois
candidats coûte `0,000096` d'équité de match par décision**, soit environ **0,12 point de MWC par
partie** sur ~25 décisions.

## Ce qui n'est pas mesuré

- **1-ply, pas 2-ply.** Un 2-ply non filtré coûte ~3,8 M évaluations par décision ; 121 d'entre
  elles sont un travail pour `mochy`, pas pour le bureau. La colonne money ci-dessus montre que
  l'indicateur est fidèle, elle ne remplace pas la mesure.
- **121 décisions.** Le `0,00 %` de la garde 5 n'est pas zéro : c'est *aucun désaccord observé sur
  121*, dont la borne haute de Wilson est d'environ **3,0 %**. Même remarque que dans le rapport de
  T31, et même conclusion : resserrer cette borne ne changerait aucune décision.
- **Quatre scores.** Choisis pour être ceux où les gammons pèsent le plus, plus un témoin. Ce n'est
  pas un balayage.
- **Le videau est absent.** Il arrive en T34, et il peut déplacer le classement du pré-tri bien
  plus qu'un score ne le fait.

## Reproduire

```bash
make build CFLAGS="-O3 $(FP_RELAXED) -std=c11 -Wall -Wextra -fPIC" \
           VENDOR_CFLAGS="-O3 $(FP_RELAXED) -std=c11 -Wall -fPIC"
python bench/filter_in_match.py
```

**Compiler avec la réassociation.** Sans elle le banc met une heure et demie au lieu de sept
minutes — le facteur 4 mesuré en T21, que j'ai oublié d'appliquer à mon propre banc au premier
essai. Et la première version recalculait la recherche non filtrée pour **chaque taille de
filtre**, alors qu'elle n'en dépend pas : un facteur 3 supplémentaire, gratuit.

Les deux gaspillages étaient évitables avec des chiffres que le projet avait déjà mesurés. La
leçon est celle que `mochy` applique en commençant par `--probe` : **mesurer le coût d'une
décision avant d'en lancer deux mille.**

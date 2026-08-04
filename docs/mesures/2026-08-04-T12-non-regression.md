# T12 — Le corpus de non-régression

**Date** : 2026-08-04 · **Machine** : la machine de calcul · **Branche** : `t12-regression`

> Ce corpus ne dit pas que le réseau a raison. Il dit qu'il n'a pas **changé**. Sans lui, une
> dérive d'encodage, de chargeur ou de poids déplacerait mille mesures ultérieures d'un rien,
> sans que personne ne le remarque.

## Le corpus

**2 050 positions**, produites par la graine `20260804`, reproductibles
(`python tools/build_corpus_t12.py --check`). 489 Ko versionnés.

| Catégorie | Positions |
|---|---|
| contact | 700 |
| bearoff | 400 |
| barre | 400 |
| course | 400 |
| **backgame** | **150** |

**Les backgames sont construits, pas tirés.** Une marche aléatoire n'en produit pratiquement
jamais : tenir deux points profonds dans le jan adverse est une stratégie, pas un accident de
dés. Un corpus qui s'en remettrait au hasard aurait une case « backgame » vide tout en
paraissant complète — exactement le genre de trou que ce fichier existe pour éviter.

Chaque entrée fige :

- l'**identifiant de position** et le trait ;
- le **compte de pips** des deux joueurs — la sentinelle, une fois de plus ;
- une **empreinte des 196 caractéristiques** ;
- les **cinq probabilités brutes, au bit près**, en hexadécimal de leur `float32`.

L'hexadécimal n'est pas de la coquetterie : du texte décimal arrondirait, et un corpus incapable
de distinguer `0,5214856` de `0,5214855` ne peut pas détecter la dérive pour laquelle il existe.

L'encodage est vérifié **séparément** des sorties. Une dérive du codec et une dérive des poids
produisent le même symptôme ; les séparer dit lequel des deux a bougé, au lieu de laisser
chercher.

## Le seuil, et pourquoi il est à zéro

Le critère de T12 demande que le test **échoue** si l'on perturbe un poids d'un pour mille.
Première tentative avec une tolérance de `1e-5`, qui paraissait serrée : **elle laissait passer
la perturbation.**

**Mesuré** : perturber **un seul poids sur 528 389** d'un pour mille ne déplace les sorties que
de **5,05 × 10⁻⁶**. C'est-à-dire qu'un réseau de cette taille absorbe presque entièrement le
déplacement d'un de ses coefficients — résultat intéressant en soi, et fatal pour un seuil
choisi à vue.

D'où le seuil retenu : **`max|Δ| = 0`**, au bit près. C'est le contrôle le plus strict
disponible, et il ne coûte rien puisque le calcul est déterministe.

| Build | `max|Δ|` sur les 2 050 positions | Verdict |
|---|---|---|
| **Par défaut** (celui qui a produit le corpus) | **0,000e+00** | ✅ |
| `NATIVE_FP=1` (réassociation sûre) | 5,662e-07 | échec explicite, remède dans le message |
| `NATIVE_FP=1` + `GN_REGRESSION_TOLERANCE=1e-6` | 5,662e-07 | ✅ |

Le 5,66e-07 recoupe le 4,77e-07 mesuré par T21 sur la parité WebAssembly ↔ natif : c'est le même
phénomène, la réassociation des sommes de la passe avant.

## Le test détecte-t-il réellement ?

C'est le critère dur de T12, et il est vérifié par le test lui-même, à chaque exécution : une
copie du modèle est perturbée d'un pour mille sur un seul poids, puis rejouée contre le corpus.

| | `max|Δ|` |
|---|---|
| Poids perturbé, build par défaut | **5,051e-06** |
| Poids perturbé, build réassocié | **4,828e-06** |
| Tolérance la plus lâche acceptée | 1e-06 |

La perturbation reste visible **8,5 fois au-dessus** de la tolérance la plus permissive. Un test
de non-régression qui passerait quoi qu'il arrive ne protégerait rien ; celui-ci démontre le
contraire à chaque exécution, plutôt que de l'affirmer dans un commentaire.

Une dérive du **codec** est vérifiée de la même façon : une caractéristique déplacée de `1e-6`
change l'empreinte.

## Reproduire

```bash
make build                              # le build par défaut, celui du corpus
python tools/export_model.py
python tools/build_corpus_t12.py        # régénère ; --check vérifie l'existant
python -m pytest tests/test_regression.py -q
```

Sous `NATIVE_FP=1`, ajouter `GN_REGRESSION_TOLERANCE=1e-6`.

## Ce que cela ne couvre pas

- **Le videau et l'équité de match** n'entrent pas dans ces cinq sorties : ils viendront après
  elles (T32, T34), et devront avoir leur propre corpus.
- **Le corpus est indexé sur le modèle actuel.** S'il est remplacé — phase 4, ou simple
  requantification — il doit être régénéré, et la régénération est alors un **acte délibéré à
  justifier**, pas une correction de test qui échoue.

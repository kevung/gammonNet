# T34 — Spécification du modèle de videau

> **Statut** : spécification d'implémentation, dérivée et vérifiée par points d'ancrage numériques
> le 2026-08-07. L'implémentation suit ce document à la lettre ; tout écart est un bug ou une
> révision de ce document, jamais une improvisation silencieuse.
>
> **Provenance** : le modèle est celui de Rick Janowski (*Take-Points in Money Games*, 1993) —
> littérature publiée. Les formules ci-dessous sont **redérivées**, pas recopiées : le point de
> prise vivant a été retrouvé par la récursion de re-doublement et coïncide avec la forme fermée
> sur deux cas de contrôle indépendants. Aucune source de GNU Backgammon n'a été lue.

## 1. Notation

Du point de vue du joueur au trait, à partir des six issues exclusives (`gn_probs_exclusive`,
jamais re-dérivé — voir T10) :

| symbole | définition | domaine |
|---|---|---|
| `p` | P(gain), toute marge | [0, 1] |
| `W` | E[points \| gain] = 1 + P(gammon\|gain) + P(bg\|gain) | [1, 3] |
| `L` | E[points \| perte] | [1, 3] |
| `e(p)` | équité cubeless par unité de videau : `pW − (1−p)L` | [−3, 3] |
| `c` | valeur courante du videau | 1, 2, 4, … |
| `x` | efficacité du videau | [0, 1] |

Hypothèse du modèle, à écrire dans l'en-tête : `W` et `L` sont traités comme constants le long de
la trajectoire de `p`. C'est la simplification standard du modèle continu.

## 2. Les deux limites exactes

### Videau mort (`x = 0`)

Personne ne redoublera jamais : `E_dead = c · e(p)`. Linéaire en `p`.

Point de prise mort (on me double à `2c` ; passer = `−c`, prendre = `2c·e`) :

```
TP_dead = (L − 1/2) / (W + L)
```

Point de cash mort (miroir, W↔L) : `CP_dead = (L + 1/2) / (W + L)`.

### Videau vivant (`x = 1`), modèle continu

`p` évolue continûment, les deux joueurs doublent au point exact. **Dérivation du point de prise
par la récursion** (à reproduire en test) : je prends à `2c` et possède alors le videau ; mon
équité de possesseur est linéaire de `(0, −2L)` à `(CP, +2)` où `CP = 1 − TP′` est le point de
prise adverse ; l'indifférence `E(TP) = −1` donne le système

```
TP  = (L − 1/2)(1 − TP′) / (1 + L)
TP′ = (W − 1/2)(1 − TP)  / (1 + W)
```

dont la solution coïncide avec la forme fermée :

```
TP_live = (L − 1/2) / (W + L + 1/2)
CP_live = (L + 1)   / (W + L + 1/2)
```

**Ancrages numériques (tests obligatoires)** :
- gammonless `W = L = 1` : `TP_dead = 0,25`, `TP_live = 0,20`, `CP_dead = 0,75`, `CP_live = 0,80` ;
- `W = 2, L = 1` : `TP_dead = 1/6`, `TP_live = 0,5/3,5 = 1/7` — et la résolution numérique du
  système ci-dessus doit rendre `1/7` à mieux que `1e−12`.

### Équités vivantes, par état du videau (par unité de `c`)

Piecewise-linéaires en `p` ; « trop bon » traité par la continuation morte :

| état | forme |
|---|---|
| **je possède** | linéaire de `(0, −L)` à `(CP_live, +1)` ; au-delà : `max(1, e(p))` |
| **adversaire possède** | pour `p ≤ TP_live` : `min(−1, e(p))` ; linéaire de `(TP_live, −1)` à `(1, W)` |
| **centré** | `min(−1, e(p))` sous `TP_live` ; linéaire de `(TP_live, −1)` à `(CP_live, +1)` ; `max(1, e(p))` au-delà |

**Ancrages (gammonless, `p = 0,5`)** : possédé `+0,25`, adverse `−0,25`, centré `0` — les valeurs
classiques du modèle continu.

## 3. Le modèle interpolé

```
TP(x) = (L − 1/2) / (W + L + x/2)
CP(x) = (L + 1/2 + x/2) / (W + L + x/2)
E(x)  = (1 − x) · E_dead + x · E_live        (par état du videau)
```

`x` est **le seul paramètre libre**. Il est **ajusté par moindres carrés contre les équités
cubeful exactes de la table bilatérale** (les trois colonnes : possédé, centré, adverse), jamais
repris d'un autre moteur. L'ajustement rapporte : `x` par état, résidus (max|Δ|, RMS), et leur
structure.

> **Limite à écrire dans le rapport** : le domaine de la table est sans gammon (`W = L = 1`
> démontré en T38). L'ajustement ne contraint donc que le comportement gammonless. La composante
> gammon du modèle est validée par comparaison à GNU Backgammon (deux colonnes), pas par une
> référence exacte — il n'en existe pas.

## 4. La décision money

Le joueur au trait peut doubler si le videau est centré ou à lui.

```
E_nd = c · E(x; état courant)                         # ne pas doubler
E_dt = 2c · E(x; adversaire possède)                  # doubler, il prend
E_dp = +c                                             # doubler, il passe
E_double = min(E_dt, E_dp)                            # l'adversaire minimise mon équité
```

| verdict | condition |
|---|---|
| `TOO_GOOD` | `E_nd > E_dp` **et** `E_nd ≥ E_double` |
| `DOUBLE_PASS` | `E_dt ≥ E_dp` et pas trop bon |
| `DOUBLE_TAKE` | `E_double > E_nd` et l'adversaire prend |
| `NO_DOUBLE` | sinon |

La sortie porte **toujours** les équités des branches, pas seulement le verdict : une décision
juste de 0,001 et une juste de 0,5 ne sont pas la même décision.

**Jacoby** (money, videau centré à 1) : drapeau `jacoby` ; s'il est actif, la branche `E_nd`
est calculée avec `W` et `L` ramenés à 1 (les gammons ne comptent pas avant le premier double).
Défaut : actif en money, sans objet en match.

## 5. La décision en match

Même mécanique, sur l'échelle **MWC**, via `gn_met` :

- Ancres : `mwc(±k)` par issue via `gn_met_after` à l'enjeu `k` ; moyennes pondérées par les
  fractions de gammon → `MWCwin_avg(k)`, `MWClose_avg(k)`. La MWC morte est linéaire en `p`.
- Les bornes `TP_m(x)`, `CP_m(x)` se calculent par la même mécanique que le money sur cette
  échelle linéaire (enjeu doublé pour la branche prise), avec l'interpolation en `x` identique.
  **Simplification nommée (v1)** : pas de récursion de re-doublement complète à score — la
  correction vivante est celle du money transposée à l'échelle MWC. Validée par comparaison à
  `cfevaluate` de gnubg à plusieurs scores ; raffinée seulement si l'ampleur des désaccords
  l'exige.
- **Crawford** : on ne double jamais (videau hors jeu). **Post-Crawford** : aucun cas spécial
  codé — le double systématique du mené et le *free drop* du meneur doivent **émerger** de la
  comparaison MWC ; un test le vérifie plutôt qu'une branche ne l'impose.
- **Plafond** : gagner `k > away` points vaut exactement `away` ; vérifier que `gn_met_after` le
  garantit (test : 2-away, videau 4 ≡ videau 2), sinon plafonner dans `gn_cube`.

## 6. Plan de vérification (dans l'ordre)

1. **Propriétés** : ancrages numériques du §2 ; `TP(x)` décroissant en `x` ; `E(x)` entre mort et
   vivant ; équités croissantes en `p` ; continuité aux bornes ; possédé ≥ centré ≥ adverse pour
   tout `p` ; la résolution numérique du système de récursion coïncide avec la forme fermée.
2. **Ajustement exact** : `x` par moindres carrés sur ≥ 5 000 entrées échantillonnées de la table
   bilatérale, par état ; résidus rapportés. C'est la mesure qui fait de `x` une valeur mesurée.
3. **Comparaison gnubg (deux colonnes, jamais une seule)** : ≥ 5 000 décisions (contact et
   course), money puis scores {2-away/2-away, 4-away/2-away, 2-away/4-away, post-Crawford} ;
   taux d'accord par verdict, désaccords classés par ampleur. Aucun verdict de supériorité —
   l'accord mesure une ressemblance, et c'est tout ce qu'on affirme.
4. **Monotonies de match** : fenêtre de double et point de prise monotones au fil des scores
   testés (tests de propriété, comme T32).

## 7. Interfaces

`src/gn_cube.h` existe déjà (commit `02eb4fc`) et fait foi pour les signatures. Ajouter ce que ce
document impose de plus : le drapeau `jacoby`, et l'accès aux équités de branche dans
`GnCubeDecision` (déjà présent). Liaison Python `python/gammonnet/cube.py` sur le modèle de
`met.py`.

## 8. Phase 2 — le videau dans l'arbre *(ajouté le 2026-08-07)*

> Question posée par le propriétaire du projet : le videau ne doit-il pas entrer dans l'arbre de
> décision, comme gnubg semble le faire ? Réponse : oui, et voici la forme exacte que cela prend.

**Ce que font les moteurs de référence** — et ce qu'ils ne font pas. Pas de branchement explicite
double/prend/passe à chaque nœud (coût exponentiel) : la **formule d'équité cubeful est appliquée
aux feuilles**, avec l'état du videau de la racine, et cette valeur cube-consciente remonte par
l'expectiminimax. Trace indépendante dans `BRIEF.md` §3.2 : hedgehog-public embarque
l'expectiminimax et les formules de Janowski côte à côte.

**Les deux effets attendus** : (1) le choix de coup devient sensible à la possession du videau
(jeu hardi vers le cash quand on le possède, sobre sous la menace) ; (2) les décisions de videau
s'appuient sur la distribution à profondeur, pas sur l'évaluation statique de la racine.

**Étapes, dans l'ordre** :

1. **Propager la distribution.** La recherche ne remonte aujourd'hui qu'un scalaire ; les cinq
   probabilités ne sont exposées qu'au 0-ply. Étendre `gn_search` pour moyenner le vecteur des
   cinq probabilités sur les jets (au meilleur coup près), et l'exposer à toute profondeur. Le
   contrôle : au 0-ply, identique à l'existant ; à 1-ply, la moyenne pondérée à la main sur les
   21 jets d'une position figée coïncide.
2. **Valuation cubeful aux feuilles.** Un mode `use_cube` dans `GnSearchConfig` (état du videau +
   `x`) : `value_from_probs` applique `E(x)` du §3 (money) ou son transposé MWC (§5, match) au
   lieu de l'équité cubeless. Le max/min de l'arbre porte alors sur des valeurs cubeful.
   **Dans le domaine de la table bilatérale, les feuilles sont exactes** — `gn_bearoff_equities`
   fournit possédé/centré/adverse ; le repli modèle ne sert que hors domaine. C'est l'avantage de
   validation propre à ce dépôt : l'arbre cubeful se vérifie étage par étage.
3. **Validation** : (a) sur des positions de bearoff, la décision de videau à 1-ply coïncide avec
   la décision exacte lisible dans la table ; (b) taux d'accord des choix de coups cubeful contre
   gnubg en évaluation cubeful, deux colonnes comme toujours ; (c) l'effet « bold/safe » est
   VISIBLE : un corpus où possession du videau change le coup choisi, non vide, versionné.

**Hors périmètre, décidé** : le branchement explicite des actions de videau dans l'arbre. Aucun
moteur de référence documenté ne le fait pour l'évaluation ; les rollouts cubeful le modélisent,
et c'est là qu'il vivra si un jour on en a besoin.

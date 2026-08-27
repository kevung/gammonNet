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
l'expectiminimax. C'est l'agencement usuel : l'expectiminimax et les formules de Janowski
cohabitent, la conversion cubeful se faisant aux feuilles.

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

> **Constat d'implémentation** *(2026-08-08, étape 2)* — **où l'effet bold/safe peut vivre, et où
> il ne peut pas.** Dans la région linéaire médiane du modèle §3, les courbes « possédé » et
> « adverse » diffèrent d'une **constante** (½ par unité de videau — se lit dans les formes
> fermées du §2 : les deux rampes ont la même pente `W + L + ½`). L'ordre de deux coups n'y
> change donc jamais avec le possesseur. Constaté avant d'être compris : 245 décisions de
> contact au 0-ply, zéro choix modifié ; puis 1 260 décisions dans le domaine de la table
> bilatérale — feuilles **exactes**, saturations réelles — **73 choix modifiés** possédé vs
> adverse. Conséquence pour l'étape 3c : le corpus bold/safe se construit près des points de
> cash et de prise et dans le domaine exact, pas sur du contact médian ; et un effet de
> possession en plein contact ne peut venir que de la profondeur (les feuilles d'un 2-ply
> atteignent les saturations) ou du passage centré↔possédé (pentes différentes), jamais du
> 0-ply possédé↔adverse.

## 9. §5-v2 — la récursion de re-doublement à score *(ajouté le 2026-08-07)*

> La mesure §6.3 a localisé le défaut de la v1 : accord money 92–95 %, accord match 61–86 %, et
> les vingt pires désaccords tous à 2-away/4-away. Le mécanisme est identifié : à ce score, quand
> le meneur double, **le re-doublement du mené est gratuit** — un videau à 4 ne change plus rien
> pour un meneur à 2-away, mais fait jouer le match au mené. La v1, sans récursion, ne voit pas
> cette gratuité. La v2 la calcule exactement.

### Le principe

La chaîne de re-doublements **se termine d'elle-même** : dès que l'enjeu `k` couvre les deux
scores (`k ≥ away_on_roll` et `k ≥ away_opponent`), aucun re-doublement ne peut plus rien changer
— le videau est mort, et `M(p; k) = M_dead(p; k)` exactement. C'est le cas de base. La profondeur
de récursion est bornée par `⌈log₂ 25⌉ = 5`.

### La construction, par état et niveau d'enjeu `k`

Sur l'échelle MWC, du point de vue du joueur au trait, fractions de gammon conditionnelles
constantes (même simplification que la v1, énoncée) :

- **Ancres** : `M_dead(p; k) = p·MWCwin_avg(k) + (1−p)·MWClose_avg(k)`, linéaire en `p`.
  **Un passe concède `k` points SECS** — jamais pondérés gammon : `M_pass(k) = mwc(+k sec)`.
- **Mort partout** si `k` couvre les deux scores (cas de base).
- **Je possède (`k`)** : linéaire de `(0, MWClose_avg(k))` à `(CP, M_pass(k))`, puis
  `max(M_pass(k), M_dead(p;k))` (trop bon). `CP` résout `M_adverse(CP; 2k) = M_pass(k)` — la
  fonction adverse au niveau `2k` venant de la récursion, la résolution par bissection (les
  fonctions sont piecewise-linéaires monotones).
- **Adversaire possède** et **centré** : miroir et combinaison, comme au §2, avec les bornes
  résolues contre les fonctions récursives au niveau `2k`.
- **Interpolation** : `M(x) = (1−x)·M_dead + x·M_live` — le `x` money transporté, même réserve
  qu'au §3.
- **Crawford** : aucune branche de double. **Post-Crawford** : rien de spécial — le meneur à
  1-away déclenche le cas de base (tout gain finit le match), le double systématique du mené
  émerge de la récursion comme en v1.
- Mémoïser les fonctions par `(état, k)` ; le coût est négligeable.

### Les ancres de validation

1. **2-away/2-away** : doubler rend le videau mort (`k = 2` couvre les deux) — le verdict doit se
   réduire à la comparaison morte, et le double quasi systématique émerger.
2. **2-away/4-away, le meneur double** : après prise, la fonction du mené possédant à `2k = 4`
   est MORTE (4 couvre 4) et son re-doublement est gratuit — la réticence doctrinale du meneur
   doit ÉMERGER. C'est l'ancre décisive : celle que la v1 rate.
3. **Critère d'acceptation mesurable** : rejouer `bench/compare_cube.py` ; l'accord contesté au
   contexte 2-away/4-away doit remonter nettement (cible indicative : rejoindre l'ordre du money,
   ≥ 85 %, ou l'écart résiduel expliqué). Les autres contextes ne doivent pas se dégrader.
4. Tous les tests v1 restent verts — la v2 remplace le calcul des bornes de match, pas la
   mécanique de décision.

> **Révision de l'ancre 4, constatée à l'implémentation** *(2026-08-08)*. Un test v1 — «
> post-Crawford à away impair ne double pas systématiquement » — encodait un **artefact de la
> v1**, pas une propriété du jeu : post-Crawford, le double du mené est gratuit à **tout** score
> (concéder 1 ou 2 points est indifférent face à un meneur à la balle de match), et la récursion
> le fait émerger partout. Vérifié par sonde gnubg 1.08.003 **avant** de réviser le test
> (bearoff, p de 0,25 à 0,76, scores 3-away/1-away et 5-away/1-away : « Double, take » partout,
> des deux moteurs). Le test est révisé en son contraire — le double émerge à tout away — et la
> distinction pair/impair reste testée où elle vit réellement : dans le free drop du meneur.
> Tous les autres tests v1 restent verts sans modification.

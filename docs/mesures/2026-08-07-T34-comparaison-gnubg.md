# T34 §6.3 — Nos décisions de videau contre GNU Backgammon, mesurées

**Date** : 2026-08-07 · **Machine** : la machine de calcul · **Branche** : `t34-comparaison`

> **Ce que ce rapport affirme, et ce qu'il n'affirme pas.** L'accord mesuré ci-dessous est une
> **ressemblance**, jamais une supériorité — aucun des deux moteurs n'est arbitré contre une
> vérité indépendante. Le rollout cubeful qui pourrait trancher un désaccord **n'existe pas
> dans ce dépôt** ; c'est un travail futur, nommé plus bas, pas une omission de ce rapport.

## Le résultat, en une phrase

**30 000 décisions** (3 000 positions × 2 états de videau comparables × 5 contextes),
**81,3 %** [IC 95 % 80,9 ; 81,8] d'accord global avec GNU Backgammon 1.08.003, mais **67,6 %**
[66,9 ; 68,3] sur le **sous-ensemble contesté** — celui qui compte, puisque le taux global est
gonflé par les positions où les deux moteurs disent trivialement « ne double pas ». L'accord en
**money** (≈ 92-95 % global, 81-87 % contesté) est nettement meilleur qu'en **match** (61-86 %
global, 56-77 % contesté), et le plus gros du désaccord de match se concentre là où la
spécification avait déjà prévenu qu'il se concentrerait : les scores où le videau redoublé
atteint exactement l'« away » d'un joueur.

## Étape 0 — la sémantique de `cfevaluate`, établie par sonde

`tools/gnubg_server.py` rendait la sortie de `gnubg.cfevaluate` **non interprétée** — la
consigne de T34 était de fixer son sens avant toute mesure, par sonde et par documentation
publique, jamais par lecture du source de gnubg. Deux sources autorisées ont suffi :
`help(gnubg.cubeinfo)`, `help(gnubg.evaluate)`, `help(gnubg.cfevaluate)` — la documentation que
l'outil expose lui-même à l'exécution — et des positions construites à verdict attendu.

### Un bug trouvé avant même la première sonde utile

`help(gnubg.cubeinfo)` donne :

```
cubeinfo(...)
    arguments: [cube value, cube owner = 0/1, player on move = 0/1,
        match length (0 = money), score (tuple int, int),
        is crawford = 0/1, bg variant = 0/5]
    returns pos-info dictionary ( see 'cfevaluate' )
```

**Sept** arguments positionnels. `tools/gnubg_server.py::make_cubeinfo` en passait **neuf** —
elle intercalait `jacoby` et `beavers`, qui n'existent pas comme arguments positionnels de
`cubeinfo` : ils vivent dans le dictionnaire que `cubeinfo()` **rend**, et que `cfevaluate`
consomme tel quel (`help(gnubg.cfevaluate)` : `cube-info = dictionary: 'jacoby'=>0/1,
'crawford'=>0/1, 'move'=>0/1, 'beavers'=>0/1, 'cube'=>…, 'matchto'=>…, 'bgv'=>…, 'score'=>…,
'gammonprice'=…`).

Neuf arguments là où sept sont attendus ne lève **aucune exception Python** : le processus gnubg
entier meurt sans un mot, ce que `GnubgSession._read` ne peut alors distinguer d'un plantage
d'origine inconnue (« GNU Backgammon a fermé sa sortie sans répondre »). Personne ne l'avait
remarqué parce que rien n'appelait `evaluate`/`cfeval` avec un `state` avant que T34 §6.3 n'en
ait besoin — la première sonde de money (jacoby actif, videau centré) plantait le processus à
chaque appel.

**Corrigé** dans `tools/gnubg_server.py::make_cubeinfo` : appel à `cubeinfo()` avec les sept
arguments réels, puis `jacoby`/`beavers` écrasés **dans le dictionnaire rendu**, seulement si
l'appelant les a demandés explicitement. Documenté dans le code, commité séparément
(`8155354`).

### Ce que les sondes ont ensuite établi

| Question | Réponse, établie par sonde |
|---|---|
| `cube_owner` | `-1` centré ; égal à `move` = le joueur au trait le possède ; différent de `move` = l'adversaire le possède |
| `move` | fixé à `1` dans tout ce module (arbitraire mais cohérent) — vérifié sans effet sur une position symétrique, videau centré |
| `score` | `(points du joueur 0, points du joueur 1)` ; `score[move]` est le score **du joueur au trait**. Confirmé contre la signature du **double systématique post-Crawford** (mené à 2-away face à un meneur à 1-away, `crawford=0`) : seule l'affectation `score = (match_to − away_adversaire, match_to − away_trait)` avec `move=1` reproduit « Double » à toutes les `p` testées (0,05 → 0,95) ; l'affectation inversée rendait « Never double (dead cube) » partout — pas la signature attendue, et silencieusement fausse si on ne l'avait pas croisée |
| Jacoby par défaut | `matchto=0` → `jacoby=1` dans le dictionnaire que `cubeinfo()` rend ; `matchto>0` → `jacoby=0`. C'est la convention de gnubg lui-même pour « Jacoby s'applique en money, pas en match » — **la même règle que `docs/specs/t34-videau-spec.md` §4** énonce pour notre modèle, retrouvée ici sans lire aucun des deux sources |
| Effet de Jacoby, vérifié en vrai | une position certaine de gammon (cherchée dans `corpus()` par `win_gammon` maximal) passe de `'Too good to double, pass'` (Jacoby off) à `'Double, pass'` (Jacoby on), videau centré — le mécanisme que `test_cube.py::test_jacoby_removes_gammon_value_from_the_no_double_branch` vérifie de notre côté, retrouvé indépendamment du leur |

### Le format de retour, et la table de correspondance

`help(gnubg.cfevaluate)` : `returns: evaluation = tuple (floats optimal, nodouble, take, drop,
int recommendation, String recommendationtext)`. Seule la chaîne est utilisée — c'est ce que
la consigne de T34 anticipait (« la chaîne de verdict suffit probablement »), et le code
l'entier `recommendation` n'a pas de documentation publique au-delà de la chaîne qu'il indexe.

**Dix couples `(code, texte)` rencontrés**, sur plus de 4 000 appels de sonde couvrant tout
l'éventail de `p` (bearoff, du quasi-certain-perdu au quasi-certain-gagné), les trois
possesseurs du videau, Jacoby actif et inactif, Crawford et post-Crawford :

```
0  'Double, take'                       8  'Redouble, pass'
1  'Double, pass'                       9  'No redouble, take'
2  'No double, take'                    11 'Too good to redouble, pass'
4  'Too good to double, pass'           13 'Never double, take (dead cube)'
7  'Redouble, take'                     15 'Cube not available'
```

`classify_gnubg_verdict` (`bench/compare_cube.py`) mappe chacune de ces chaînes, et toute
variante construite du même vocabulaire, à nos quatre verdicts — dans cet ordre de priorité
(« too good » d'abord, puisque son texte contient aussi « double » et « pass ») :

| motif dans la chaîne (insensible à la casse) | verdict |
|---|---|
| `"too good"` | `TOO_GOOD` |
| `"cube not available"` | `NO_DOUBLE` (le videau appartient à l'adversaire) |
| `"never double"` | `NO_DOUBLE` (videau mort) |
| commence par `"no double"` ou `"no redouble"` | `NO_DOUBLE` |
| contient `"double"`/`"redouble"` et `"pass"` | `DOUBLE_PASS` |
| contient `"double"`/`"redouble"` et `"take"` | `DOUBLE_TAKE` |
| tout le reste | **lève**, ne devine jamais |

Aucune chaîne rencontrée durant la mesure complète (30 000 appels) n'a échappé à cette table —
le classificateur n'a jamais eu à lever.

## Le protocole

**Corpus** : 2 000 positions de contact (`bench/decision_loss.corpus`, graine `20260807`) +
1 000 positions de bearoff (`bench/exact_gap.random_bearoff`, graine `20260808`) — réutilisés
tels quels, pas régénérés. Construit en **5 s**.

**États de videau comparés** : centré et possédé par le joueur au trait. L'état « adverse » n'a
pas de décision à comparer — vérifié séparément (voir plus bas), jamais mêlé à la matrice de
confusion.

**Cinq contextes** par état : money (Jacoby actif des deux côtés — vérifié ci-dessus que le
`cubeinfo` de gnubg fait de même par défaut) et les quatre scores de la spécification :
2-away/2-away, 4-away/2-away, 2-away/4-away, post-Crawford (mené à 2-away, meneur à 1-away,
`crawford=False` — la partie de Crawford elle-même n'est pas ici : c'est une propriété de notre
seul modèle, déjà couverte par `tests/test_cube.py::test_crawford_never_doubles`, sans oracle
externe nécessaire).

**Notre côté** : `Network.evaluate` (0-ply) → `cube.decide` avec `x` lu dans
`docs/mesures/t34-efficacite.json` — `owned` (0,566) pour l'état possédé, `centered` (0,688)
pour l'état centré, jamais codé en dur. **Leur côté** : `gnubg.cfevaluate` au 0-ply, même
position, même état de videau, même contexte.

**Valeur du videau fixée à 1** dans toute la mesure — cette étude ne teste pas de redoublement
à une valeur supérieure ; une limite de portée nommée, pas un oubli.

## Le débit, mesuré

Pilote de 8 positions, série : **0,111 s/position** (80 décisions en 0,9 s) → projection
**~0,2 min** sur 26 processus pour les 3 000 positions. Volume complet : **30 000 décisions en
12,0 s** sur 26 processus — **mesuré**, pas extrapolé (`CLAUDE.md` règle 3). L'estimation du
pilote et la mesure réelle concordent.

## Le contrôle « adverse » — un petit échantillon, pas la matrice de confusion

60 positions, videau à l'adversaire, contextes money et 2-away/2-away (120 vérifications) :
**120/120** — les deux moteurs sont d'accord à 100 % qu'aucun double n'est possible quand
l'adversaire tient le videau. Aucune surprise attendue ici : c'est une propriété structurelle
des deux modèles (`test_cube.py::test_opponent_owned_cube_forces_no_double` du nôtre ; `'Cube
not available'` du leur), pas une mesure de force.

## Les taux d'accord

### Global et contesté

| | n | accord | IC 95 % |
|---|---:|---:|---|
| **global** | 30 000 | **81,3 %** | [80,9 ; 81,8] |
| **contesté** (≥ un moteur ≠ `NO_DOUBLE`) | 17 279 | **67,6 %** | [66,9 ; 68,3] |

Le taux global est gonflé par 12 721 positions où les deux moteurs disent trivialement « ne
double pas » (57,6 % à eux seuls de nos 15 041 `NO_DOUBLE`). **Le taux contesté est celui qui
compte** : 17 279 des 30 000 décisions — 57,6 % du volume — impliquaient un verdict actif d'au
moins un côté, et sur ce sous-ensemble l'accord tombe à 67,6 %.

### Par contexte et par état

| contexte | état | accord global | IC 95 % (global) | accord contesté | n contesté |
|---|---|---:|---|---:|---:|
| money | possédé | 92,4 % | [91,4 ; 93,3] | 80,8 % | 1 187 |
| money | centré | 94,5 % | [93,6 ; 95,2] | 86,9 % | 1 271 |
| 2-away/2-away | possédé | 75,3 % | [73,7 ; 76,8] | 58,2 % | 1 772 |
| 2-away/2-away | centré | 74,2 % | [72,6 ; 75,8] | 56,4 % | 1 772 |
| 4-away/2-away | possédé | 86,3 % | [85,0 ; 87,5] | 68,8 % | 1 319 |
| 4-away/2-away | centré | 80,4 % | [78,9 ; 81,7] | 59,6 % | 1 459 |
| 2-away/4-away | possédé | 86,4 % | [85,1 ; 87,5] | 67,5 % | 1 259 |
| 2-away/4-away | centré | 85,3 % | [83,8 ; 86,6] | 65,7 % | 1 289 |
| post-Crawford | possédé | 61,3 % | [59,6 ; 63,0] | 60,6 % | 2 951 |
| post-Crawford | centré | 77,4 % | [75,9 ; 78,9] | 77,4 % | 3 000 |

**Le money ressemble nettement mieux au verdict de gnubg que le match** (≈ 92-95 % global contre
61-86 %). C'est cohérent avec la structure même du modèle : en money, la seule composante
« ajustée sans référence exacte » est `W`/`L` (la valeur des gammons) — voir
`docs/mesures/2026-08-07-T34-ajustement.md`. En match, une seconde couche s'ajoute, nommée dès
`docs/specs/t34-videau-spec.md` §5 comme une **simplification v1** : *« pas de récursion de
re-doublement complète à score — la correction vivante est celle du money transposée à l'échelle
MWC »*. Cette mesure est précisément celle que la spécification appelait pour juger de l'ampleur
de cette simplification.

## La matrice de confusion (30 000 décisions, tous contextes confondus)

| nous ↓ / gnubg → | `NO_DOUBLE` | `DOUBLE_TAKE` | `DOUBLE_PASS` | `TOO_GOOD` |
|---|---:|---:|---:|---:|
| **`NO_DOUBLE`** | 12 721 | 2 243 | 76 | 1 |
| **`DOUBLE_TAKE`** | 644 | 2 213 | 1 173 | 25 |
| **`DOUBLE_PASS`** | 172 | 107 | 6 737 | 832 |
| **`TOO_GOOD`** | 95 | 1 | 229 | 2 731 |

Deux masses hors diagonale dominent, dans des sens opposés :

* **Nous disons `NO_DOUBLE`, gnubg dit `DOUBLE_TAKE`** (2 243 cas) — nous sommes plus prudents à
  doubler que gnubg, dans plus de cas que l'inverse (644 cas où nous doublons et gnubg ne le
  ferait pas).
* **Nous disons `DOUBLE_PASS`, gnubg dit `TOO_GOOD`** (832 cas, la deuxième plus grosse cellule
  hors diagonale). Sur les 3 589 fois où gnubg dit `TOO_GOOD` (somme de sa colonne), nous sommes
  d'accord 2 731 fois (76,1 %) mais restons sur `DOUBLE_PASS` les 832 autres (23,2 %) — nous
  franchissons le seuil « trop bon pour doubler » moins souvent que gnubg. Cohérent avec T37 :
  notre réseau sous-estime légèrement `P(gain-gammon)` (biais mesuré `−0,0024`, IC ne touchant
  pas zéro), ce qui pousse `W` un peu bas et retarde exactement ce basculement.

## Le foyer du désaccord, quantifié : le plafond du videau à `away = 2`

Les **20 pires désaccords par marge gnubg** — écart le plus large entre `nodouble` et
`min(take, drop)` côté gnubg — proviennent **tous** du contexte `2-away/4-away`, essentiellement
côté « possédé » :

| position (échantillon) | contexte | état | nous | marge nous | gnubg | marge gnubg |
|---|---|---|---|---:|---|---:|
| `tHcVAAMWz4MHAA` | 2-away/4-away | possédé | `DOUBLE_TAKE` | −0,0002 | `NO_DOUBLE` (*No redouble, take*) | **+1,2454** |
| `ZrsGIwCYdyMHAA` | 2-away/4-away | centré | `DOUBLE_TAKE` | −0,0047 | `NO_DOUBLE` (*No double, take*) | **+1,2185** |
| `tm0JAQPbPtgAAA` | 2-away/4-away | possédé | `DOUBLE_TAKE` | −0,0023 | `NO_DOUBLE` | **+1,2060** |
| … 17 autres, toutes `2-away/4-away`, marge gnubg de +1,03 à +1,20 | | | | | | |

*(liste complète des 20 : `docs/mesures/t34-comparaison.json`, `worst_disagreements`.)*

**Ce que révèle l'exemple le plus net** (`tHcVAAMWz4MHAA`, mover 2-away, adversaire 4-away,
état possédé, `p` réseau = 0,543) :

```
nous       equity_no_double = 0,7327   equity_double = 0,7329   (écart quasi nul → DOUBLE_TAKE)
gnubg      nodouble         = 0,2827   min(take,drop)  = −0,9626 (écart énorme → No double)
```

Notre `equity_no_double` (0,733) dépasse largement l'équité de match brute sans jamais avoir
tourné le videau, `2·MWC(p) − 1 = 0,433` (calculée directement par `MatchState.equity`,
elle-même déjà validée en T32) — un bond de +0,30 attribué à la seule valeur de posséder le
videau. **L'hypothèse retenue, cohérente avec la mécanique du modèle mais non tracée pas à pas
dans le code** : à `away = 2`, gagner exactement `cube = 2` points **plafonne** la MWC à 1,0 —
propriété déjà établie et testée (`test_cube.py::test_cube_value_is_capped_by_gn_met_after`,
confirmée ici en direct : `MatchState(2, 4).after(2, True) == 1.0`). Le modèle §3 suppose `W` et
`L` **constants le long de la trajectoire de `p`** ; près d'un plafond de MWC, cette hypothèse
est justement la plus fausse — la vraie courbe s'aplatit brutalement là où le modèle continue
en droite. C'est très exactement la « récursion de re-doublement complète à score » que
`docs/specs/t34-videau-spec.md` §5 nomme comme **absente** du v1, et que ce paragraphe dit
vouloir raffiner « seulement si l'ampleur des désaccords l'exige ». Cette mesure dit son
ampleur : concentrée, systématique, et localisée avec précision.

**Le même mécanisme apparaît côté post-Crawford** (le mené est, lui aussi, à 2-away) : un
sondage manuel sur 60 positions montre exactement les mêmes signatures — `DOUBLE_TAKE` chez
nous à marge quasi nulle contre `DOUBLE_PASS`/`TOO_GOOD` chez gnubg à marge large. C'est
`post-Crawford / possédé` qui a le plus bas taux d'accord de toute la table (61,3 %) — le
contexte où le joueur au trait est à `away = 2` **et** en train de redoubler son propre videau
vers `cube = 2`, le cas le plus direct du plafond.

**Nuance nécessaire, lue directement dans le tableau ci-dessus** : `2-away/4-away` — où le
joueur au trait est *aussi* à `away = 2` — a pourtant le **meilleur** taux d'accord global de
tous les contextes de match (86,4 % / 85,3 %), meilleur même que `4-away/2-away` où le joueur au
trait n'est pas à `away = 2`. Le mécanisme du plafond n'est donc pas la cause dominante du taux
d'accord global de ce contexte : il est **rare** dans ce corpus (une position sur beaucoup
suffisamment proche du seuil pour l'activer), mais **sévère** quand il frappe — c'est
précisément pourquoi les 20 pires désaccords par marge s'y concentrent tous sans que le taux
d'accord global n'en soit dominé. Fréquence et sévérité sont deux axes distincts d'un même
mécanisme, et cette mesure les distingue plutôt que de les confondre : le taux d'accord dit
« combien de fois », la liste des pires désaccords dit « combien ça coûte quand ça arrive ».
`post-Crawford / possédé`, à l'inverse, active le plafond sur la **totalité** du sous-échantillon
possédé (le mené y redouble presque systématiquement, par construction du modèle — voir
`test_cube.py::test_post_crawford_trailer_at_two_away_doubles_systematically`), ce qui explique
que son taux d'accord global, et pas seulement ses pires marges, en porte la trace.

**Ce que cette hypothèse n'explique pas** : `2-away/2-away` a lui aussi un taux d'accord modeste
(75,3 %/74,2 %, le deuxième plus bas après post-Crawford) alors que le mécanisme du plafond, tel
que décrit ci-dessus, ne devrait pas y être plus actif qu'en `2-away/4-away` — les deux ont
`away = 2` côté joueur au trait. Un score serré et symétrique est structurellement plus sensible
à n'importe quel écart entre les deux modèles (les décisions y sont plus souvent proches du
seuil, des deux côtés), ce qui peut suffire à expliquer un accord plus bas sans invoquer le
plafond. **Ceci est rapporté comme une observation mesurée et une hypothèse mécanique
plausible pour une partie du désaccord, pas comme un diagnostic complet ni tracé** : aucune
ligne de `gn_cube.c` n'a été relue pas à pas pour cette mesure — la consigne de T34 est de
rapporter un comportement surprenant, pas de le corriger.

## Les réserves, nommées

- **Aucun arbitrage n'est possible aujourd'hui.** Le rollout cubeful qui pourrait dire *lequel*
  des deux verdicts est correct sur un désaccord donné **n'existe pas dans ce dépôt** — c'est un
  travail futur, qui suppose un rollout jouant les deux branches (double et non-double)
  jusqu'au bout avec un videau vivant, jamais implémenté ici. Sans lui, l'accord mesuré reste une
  ressemblance, jamais un verdict de qui a raison.
- **`x` est ajusté en domaine sans gammon et transporté au contact comme hypothèse.** Le domaine
  de la table bilatérale qui a fixé `x` (`docs/mesures/2026-08-07-T34-ajustement.md`) est
  **gammonless** (`W = L = 1` partout, démontré en T38). Les 2 000 positions de contact de ce
  banc ont, elles, des gammons réels. Utiliser le même `x` là où il n'a jamais été mesuré est une
  hypothèse du modèle (§3 de la spécification l'assume explicitement), pas une extension
  validée — et une partie du désaccord mesuré ici pourrait lui être imputable plutôt qu'au
  plafond de `away`, sans qu'on puisse aujourd'hui départager les deux.
- **Cube fixé à 1.** Aucun redoublement à une valeur supérieure n'est testé.
- **0-ply des deux côtés.** Une décision de videau à profondeur supérieure — où l'arbre lui-même
  voit plus loin — n'est pas mesurée ici ; c'est la phase 2 de `docs/specs/t34-videau-spec.md`
  (§8), séparée de cette vérification.
- **`p` du réseau porte le biais de gammon mesuré en T37** (`win_gammon` sous-estimé de
  `−0,0024`, IC ne touchant pas zéro) — trop petit pour expliquer, à lui seul, une marge de
  +1,2 dans l'échelle de gnubg, mais il contribue au sens observé dans la matrice de confusion
  (`DOUBLE_PASS` chez nous là où gnubg dit `TOO_GOOD`).

## Reproduire

```bash
python bench/compare_cube.py --contact 2000 --bearoff 1000 --workers 26 \
    --out docs/mesures/t34-comparaison.json
```

Sortie complète : [`t34-comparaison.json`](t34-comparaison.json) (agrégats, matrice de
confusion, les 20 pires désaccords avec Position ID — pas les 30 000 lignes brutes, dans le
même esprit que `t38-exact-gap.json` et consorts).

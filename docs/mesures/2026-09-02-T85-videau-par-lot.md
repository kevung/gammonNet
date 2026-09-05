# T85 — Valuer le videau par lot sur les candidats

**Date** : 2026-09-02 · **Machine** : poste de bureau, AMD Ryzen 7 PRO 6850U (Zen 3,
8 cœurs physiques / 16 fils, AVX2), 14,4 Gio, Linux 7.1.9-arch1-2 · **Chaîne** : gcc 16.2.1 ·
**Branche** : `feat/t85-videau-par-lot`

> **La machine n'était pas au repos, et il faut le dire.** Deux autres chantiers tournaient
> pendant la séance (T84 : un `bench_sparsity` à 100 % d'un cœur en continu ; T86 : des builds
> Emscripten). La charge moyenne relevée à chaque mesure va de **1,6 à 18,3**. Aucun chiffre
> absolu de ce document ne doit être cité ; **tout ce qui est conclu l'est sur des rapports
> mesurés dos à dos**, et le §1 explique l'instrument qui rend ces rapports possibles malgré
> la dérive.

---

## 1. La mesure d'entrée, complétée — et l'instrument qu'elle a fallu construire

### Ce qui manquait

`docs/mesures/2026-09-02-optimisation-mesures-d-entree.md` §5 chiffre le videau à **~88 ms par
décision au score, 20-25 % du total**, et pose lui-même sa réserve :

> Les 88 ms sont un **produit de deux mesures**, pas un chronométrage. `bench_decision` ne sait
> pas activer `use_cube`, et le nombre de nœuds qui portent réellement une valuation de videau
> n'a pas été compté.

Le produit est `43 218 nœuds × 2 029 ns`. Ses deux facteurs sont douteux chacun pour sa raison :

- **Le nombre de nœuds** était le total des évaluations réseau (12 080 + 31 138), ce qui suppose
  qu'un nœud évalué porte exactement une valuation. C'est faux dans trois sens à la fois : un
  coup terminal est calculé et jamais valué, la table bilatérale court-circuite le modèle en
  money, et la passe profonde revalue des nœuds que la passe superficielle avait déjà valués.
- **Les 2 029 ns** viennent de `bench_cube`, une boucle serrée sur 2 000 distributions, où le
  modèle a le cache pour lui seul. Dans la recherche il le partage avec 2 Mio de poids.

### L'instrument

Trois ajouts, tous dans le commit `e0ba8aa` :

- `gn_search_cube_valuations()` — le **dénominateur compté**. Incrémenté là où `node_value`
  appelle réellement `gn_cube_value`, donc après le court-circuit bearoff et jamais sur un
  terminal.
- `bench_decision --cube[=x] --owner= --match=a/b --crawford --repeat=n` — le banc sait
  maintenant allumer ce que la fiche lui demandait de mesurer.
- **Les décisions sont enregistrées puis rejouées.** Allumer le videau change le meilleur coup :
  un pilote qui avance la partie avec ses propres réponses ne compare pas deux configurations,
  il compare deux parties. La marche est donc faite une fois, non chronométrée, par la
  configuration cubeless, et chaque exécution chronométrée rejoue exactement ces triplets
  (position, dés). Les chiffres cubeless publiés ne bougent pas d'un pouce : **33 799
  évaluations sans élagage, 12 080 / 31 138 à `k=12`**, identiques au relevé d'entrée.
- `--ab` — les deux configurations chronométrées **décision par décision dans le même
  processus**. C'est la pièce qui rend la séance exploitable : le plancher de bruit de cette
  machine est de ±8 % entre deux exécutions consécutives du même binaire, si bien qu'une
  différence obtenue en soustrayant deux exécutions entières porte plus d'erreur qu'elle n'en
  mesure. Le §1.3 le montre en acte.

### 1.1 Le dénominateur, compté

20 décisions, 2-ply, filtre (0,1,3), élagage `k=12` :

| | évaluations grand | évaluations petit | **valuations du videau** |
|---|---|---|---|
| money, videau centré | 12 054 | 31 080 | **43 134** |
| 5-away/5-away, videau centré | 12 061 | 31 101 | **43 163** |

Le produit supposait 43 218. Le compte dit **43 163**. Sur ce corpus la supposition était
juste à 0,13 % près — mais elle était une supposition, et elle ne l'est plus. (Elle ne le
resterait pas sur un corpus de fins de partie, où le court-circuit de la table bilatérale
retire des valuations en money.)

### 1.2 Le chronométrage

`--ab`, entrelacé, 20 décisions × 5 répétitions, médiane ; quatre exécutions successives :

**Au score (5-away/5-away, videau centré, x = 0,688)**

| exécution | sans videau | avec videau | coût | part | ns/valuation |
|---|---|---|---|---|---|
| 1 | 0,4438 | 0,5483 | 104,5 ms | **19,1 %** | 2 422 |
| 2 | 0,4605 | 0,5818 | 121,2 ms | **20,8 %** | 2 809 |
| 3 | 0,4259 | 0,5390 | 113,1 ms | **21,0 %** | 2 620 |
| 4 | 0,4809 | 0,6018 | 121,0 ms | **20,1 %** | 2 803 |

**Médiane : 20,5 % d'une décision au score, 2 711 ns par valuation.**

**En money (videau centré, x = 0,688)**

| exécution | sans videau | avec videau | coût | part |
|---|---|---|---|---|
| 1 | 0,4378 | 0,4349 | −2,9 ms | −0,7 % |
| 2 | 0,5259 | 0,5299 | +4,0 ms | +0,8 % |
| 3 | 0,6381 | 0,6368 | −1,3 ms | −0,2 % |
| 4 | 1,0715 | 1,0507 | −20,8 ms | −2,0 % |

**Le poste est nul en money** : les quatre relevés encadrent zéro. Le produit du relevé d'entrée
en attendait 0,6 ms, soit 0,15 % — indiscernable de zéro, et c'est bien ce que la mesure lit.
La quatrième exécution (charge 18,3) montre au passage ce que la séance valait en absolu.

### 1.3 Ce que l'entrelacement a changé, et pourquoi il fallait le construire

Les **mêmes** configurations, mesurées par soustraction de deux exécutions séparées au lieu de
l'entrelacement, sur la même demi-heure :

| | sans videau | avec videau | coût déduit |
|---|---|---|---|
| exécutions consécutives (`--repeat=5` chacune) | 0,4198 | 0,4696 | **49,8 ms — 10,6 %** |
| trois passes alternées, `--repeat=3` | 0,3853 / 0,3755 / 0,4020 | 0,5211 / 0,4675 / 0,5761 | **136 ms — 26 %** |
| entrelacé décision par décision | — | — | **113-121 ms — 20,5 %** |

**Un facteur 2,5 entre deux lectures du même poste, le même après-midi, sur la même machine.**
La conclusion de la fiche T85 se joue à un seuil de 5 % ; sans l'entrelacement, ce seuil aurait
été décidé par ce que le voisin faisait tourner.

### 1.4 Verdict de la mesure d'entrée

**Les 20-25 % annoncés par la fiche sont confirmés comme chronométrage : 20,5 % au score, zéro
en money.** Le produit était juste, et il ne l'était pas pour ses raisons — son numérateur
surestimait (2 029 ns contre 2 711 ns réels : le modèle est PLUS cher dans la recherche que dans
la boucle serrée de `bench_cube`, parce qu'il y partage le cache avec 2 Mio de poids) et son
dénominateur aussi (43 218 contre 43 163). Les deux erreurs allaient en sens contraire.

**Le poste est donc réel et il vaut d'être attaqué. La suite de ce document mesure ce que la
vectorisation sur candidats en rend.**

---

## 2. Ce qui a été fait, et la seule chose qui change

`level_solve` est une **chaîne de dépendances sérielle** : soixante pas, chacun une division dont
le résultat choisit l'entrée du pas suivant. Rien dans un processeur ne recouvre ça avec
soi-même. Trois niveaux, deux points de rupture par niveau, soixante pas : ≈ 360 divisions à la
file par candidat, ce qui, à ~20 cycles de latence pièce, **est** les 2,7 µs mesurés. Le poste
n'est pas du travail, c'est de la latence.

Les bissections de deux candidats ne partagent rien. `gn_cube_value_batch` les mène donc en pas
cadencé — itération par itération à travers les voies, plutôt que voie par voie à travers les
itérations — et la latence de l'une est payée par le travail de l'autre. La recherche a toujours
une fratrie entière en main quand elle value l'un de ses membres (`value_sweep`), donc les voies
sont là pour rien.

`build_levels` est coupé en deux à l'endroit où le lot en a besoin : `build_level_anchors`
(par candidat) et `resolve_levels` (par niveau, donc en lot).

**Ce qui n'a PAS été fait, délibérément** : hoister ou dédupliquer les consultations de la table
d'équité de match, alors même que `pass`, `cash` et les trois `gn_met_after` de `branch_mwc` ne
dépendent que de l'état et sont identiques dans toutes les voies. Le portage Go l'a écrit, mesuré
à 1 % et annulé. Chaque voie paie ici ses propres consultations, exactement comme le scalaire.

## 3. L'exactitude — quatre preuves, aucune tolérance

| preuve | portée | résultat |
|---|---|---|
| `tests/test_cube_batch.py`, accord avec le scalaire | 141 distributions réelles × 3 possessions × 7 états (money, 5/5, 2/4, videau à 2, 1/1, Crawford, 25/25) | `==`, **pas** `approx` — 21 cas, tous verts |
| `tests/test_cube_batch.py`, invariance au découpage | les mêmes, en un lot / en deux moitiés coupées à 37 / une par une | bits identiques |
| corpus T12, classements 0-ply au score | 200 positions × 3 possessions × 21 lancers = **12 600 classements**, videau actif à 5-away/5-away | `diff` = **0 ligne** |
| corpus T12, classements 2-ply `k=12` filtre (0,1,3) | 4 positions × 3 possessions × 21 lancers = **252 classements** | `diff` = **0 ligne** |

Les deux `diff` comparent les équités **en hexadécimal IEEE-754**, pas en décimal tronqué : une
divergence d'un bit se verrait. Et ils comparent l'ORDRE en même temps que les nombres, ce que la
leçon de T88 impose.

Le même `diff` 0-ply rejoué avec `GN_CUBE_BATCH` à **16** au lieu de 32 rend les mêmes 12 600
lignes : la largeur de voie est un paramètre de coût, jamais un paramètre du moteur.

Enfin, `make bench-cube` — qui appelle le **scalaire** — lit les mêmes valeurs qu'avant
(15,1 ns en money, 2 393 ns à 5-away/5-away) : le chemin scalaire n'a pas bougé, et la suite
complète passe (**479 réussis, 53 ignorés, 0 échec** ; `test_serve` est mis à part, il refuse de
démarrer faute de l'artefact float16 épinglé, ce qui est vrai sur `main` aussi).

## 4. Le gain — mesuré au score et en money séparément

Protocole : le binaire de référence est construit sur `e0ba8aa` (l'instrument de mesure, **sans**
l'optimisation), le binaire mesuré sur `23c5a64`. Les deux tournent en alternance, chacun avec
son `--ab` interne : la moitié cubeless est le **même code des deux côtés** et sert donc de
normalisateur à l'intérieur de chaque exécution. Huit paires, `--repeat=3`, charge de 1,3 à 20.

### Au score (5-away/5-away, videau centré)

| | référence | par lot | rapport |
|---|---|---|---|
| coût du videau, par décision | **103,6 ms** | **42,7 ms** | **×2,43** |
| par valuation | **2 401 ns** | **988 ns** | **×2,43** |
| part d'une décision | **19,35 %** | **9,05 %** | — |

Les huit paires, sans sélection :

| paire | réf. ms | lot ms | réf. ns | lot ns | réf. part | lot part |
|---|---|---|---|---|---|---|
| 1 | 105,1 | 47,3 | 2 434 | 1 097 | 20,1 % | 9,8 % |
| 2 | 103,4 | 42,9 | 2 396 | 995 | 19,4 % | 9,0 % |
| 3 | 93,9 | 41,5 | 2 175 | 962 | 15,8 % | 8,5 % |
| 4 | 103,8 | 42,4 | 2 405 | 982 | 19,3 % | 8,6 % |
| 5 | 127,4 | 44,1 | 2 951 | 1 022 | 20,2 % | 9,1 % |
| 6 | 111,6 | 35,4 | 2 585 | 820 | 18,9 % | 7,7 % |
| 7 | 95,9 | 40,1 | 2 221 | 929 | 19,7 % | 9,4 % |
| 8 | 97,1 | 46,8 | 2 250 | 1 085 | 18,4 % | 9,1 % |

**Sur la décision entière, au score : ×1,13, soit 11,4 % de moins.** (Les deux moitiés cubeless
étant le même code, `T_lot / T_réf = (1 − part_réf) / (1 − part_lot)` ; les huit paires rendent
0,886 / 0,886 / 0,920 / 0,883 / 0,878 / 0,879 / 0,886 / 0,898, médiane **0,886**.)

Le seuil d'abandon de la fiche est de **5 %** sur une décision au score. **11,4 % le passe deux
fois.**

### En money — rien, et rien n'était possible

Quatre paires :

| paire | référence | par lot |
|---|---|---|
| 1 | −0,1 % | +0,9 % |
| 2 | −0,2 % | +0,9 % |
| 3 | +0,7 % | −0,1 % |
| 4 | −1,6 % | +1,3 % |

Les huit relevés encadrent zéro des deux côtés. **C'est le résultat attendu et il est vérifié, pas
supposé** : le money reste sur le chemin scalaire, à dessein — le §1.2 y a mesuré le poste à zéro,
et une valuation money coûte 15 ns contre 2 400 ns au score. Publier un gain global moyenné aurait
caché ce fait ; c'est pourquoi la fiche demandait les deux séparément.

### La largeur de voie — un balayage NON concluant, et il faut le dire

`GN_CUBE_BATCH` recompilé, ns par valuation, mesures alternées :

| largeur | relevés |
|---|---|
| 8 | 1 787 |
| 16 | 1 197 / 1 058 / 991 |
| **32** | 1 047 / 887 / 982-1 097 (les huit paires ci-dessus) |
| 64 | 1 168 / 913 |

**8 est nettement moins bon** — trop peu de voies pour couvrir la latence d'une division. Entre
**16, 32 et 64 la mesure ne tranche pas**, et l'écart entre relevés d'une même largeur est plus
grand que l'écart entre largeurs. 32 est conservé parce qu'il est au milieu et que rien ne le
conteste, **pas** parce qu'il aurait gagné. C'est la même honnêteté que le §8 du relevé d'entrée,
et pour la même raison : un seul relevé par largeur sur une machine en dérive ne conclut rien.

## 5. La forme, pour toute autre écriture de ce modèle

**Le module WebAssembly l'a déjà** : c'est le même C, il suffit de reconstruire. **Le natif
aussi.** Ce qui suit est donc la forme telle qu'elle doit être reproduite partout où ce modèle
serait réécrit, énoncée en `docs/specs/t34-videau-spec.md` §7.1 — et c'est une obligation de
forme, pas une recette de performance :

1. Couper la construction des niveaux en deux — les **ancres** d'un niveau (par candidat) et la
   **résolution** des points de rupture (par niveau). La coupe est le tout de la fiche : c'est
   la seconde moitié qui se met en lot.
2. Une valuation par lot — `n` distributions, un seul état de videau, `n` valeurs en retour —
   menant les soixante pas de toutes les voies en pas cadencé, appelée depuis la boucle de
   fratrie, la seule qui ait des candidats en main.
3. **Les deux dispositifs d'exactitude, non négociables** : largeur de voie fixe (la queue tourne
   moins de voies) et nombre d'itérations fixe (soixante, toujours — jamais « jusqu'à
   convergence des voies », qui ferait dépendre une voie de ses voisines).
4. **Ne PAS hoister les consultations `metAfter`.** Elles sont identiques dans toutes les voies
   et c'est précisément le piège : ce gain a été mesuré à 1 %, et le travail annulé sur cette
   mesure.
5. Le money reste scalaire.
6. Le test à écrire avant le code : l'égalité **par candidat, au bit près**, contre la valuation
   une par une, plus l'invariance au découpage — `tests/test_cube_batch.py` en donne la forme.

**Ce qui NE se reprend pas** : la largeur 32. C'est un paramètre de coût, il se mesure dans le
runtime qui l'exécute, et le §4 ci-dessus dit que même ici la mesure ne le tranche pas.

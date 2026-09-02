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

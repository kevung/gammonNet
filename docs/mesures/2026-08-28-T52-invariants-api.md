# T52 — deux défauts silencieux dans « les N meilleurs coups », et le contrôle qui les tient

**Date** : 2026-08-28 · **Machine** : la machine de calcul · **Branche** : `main`

> **Ce qui s'est passé.** `v1.0.0` a été publiée, puis l'archive téléchargée et éprouvée comme le
> ferait un utilisateur. Deux appels successifs à `rankPlays` sur la même position ont rendu des
> classements différents. **Les deux défauts étaient invisibles** : probabilités plausibles,
> équités plausibles, ordre décroissant. Rien ne clochait, sauf les coups.
>
> **Portée.** Le WebAssembly seul, et seulement `rankPlays` — l'API a un jour. **Aucune mesure du
> dépôt n'est touchée** : PR, T35, T3C et toutes les campagnes passent par `python/gammonnet/
> search.py`, qui alloue le tampon complet. Vérifié appelant par appelant.

## Le premier — le tampon dimensionné sur la demande

`gnw_rank_plays` allouait `max_out` candidats, la taille demandée par l'appelant. Or `rank_plays`
tronque à la taille de son tampon **avant d'évaluer quoi que ce soit**, dans l'ordre de génération
des coups :

```c
int written = (count < max_out) ? count : max_out;   /* src/gn_search.c:578 */
```

Demander 3 coups faisait donc classer **3 coups arbitraires**. Mesuré sur l'ouverture 3-1, niveau
`normal` :

| `max` demandé | 2ᵉ coup rendu | son équité |
|---|---|---|
| 3 | `wnPwATDgc/ABMA` | **−0,1262** |
| 5 | `0HPiATDgc/ABMA` | −0,0085 |
| 20 | `4HPiASjgc/ABMA` | **−0,0029** |

Le meilleur coup, lui, était toujours juste : `bestPlay` alloue `MAX_PLAYS`, et le vrai meilleur
survit presque toujours aux premiers coups générés. C'est ce qui a rendu le défaut furtif.

**`src/gn_rollout.c` documentait exactement ce piège** — *« passing `max_out = 1` would make it
evaluate only the first legal play and call it the best, which is a different and much worse
engine »*. L'enrobage WebAssembly y est tombé quand même.

## Le second — deux échelles de profondeur dans une même liste

Corrigé le premier, le classement restait non monotone : à `filterTop = 3`, le 4ᵉ coup rendu
(−0,0080) était **meilleur** que le 3ᵉ (−0,0135). Le filtre de coups ne réévalue en profondeur que
ses `filterTop` premiers ; les suivants gardent l'équité d'une passe plus superficielle. Rendus
dans une même liste, les deux échelles se mélangent.

Contrôlé en variant le filtre, tout le reste égal :

| `filterTop` | classement décroissant ? |
|---|---|
| 3 | **non** — rompt à l'index 3 |
| 6 | **non** — rompt à l'index 6 |
| 0 (sans filtre) | **oui** |

`bestPlay` n'en souffrait pas : un filtre à 3 suffit pour désigner *le* meilleur. Une API qui
promet « les N meilleurs coups **avec leurs statistiques** » doit, elle, les avoir cherchés à la
même profondeur. `gnw_rank_plays` élargit donc le filtre à ce que l'appelant demande. **Le coût
monte avec N**, et c'est le prix juste.

## Ce qui n'est PAS un défaut, et qu'il ne faut pas corriger

Avec le filtre actif, les N meilleurs **dépendent** de N. Un filtre à N cherche en profondeur les N
coups les plus prometteurs d'une passe superficielle, et le vrai N-ième peut se trouver en dehors.
GNU Backgammon a la même propriété. L'invariant « top-N indépendant de N » n'est donc posé que
**filtre éteint** — là où il doit tenir, et là où il attrape le premier défaut.

## Le contrôle

`wasm/api_invariants.mjs`, cible `make wasm-api`, étape de CI, et **livré dans l'archive** sous
`verify/api_invariants.mjs`. Il pose cinq invariants :

1. filtre éteint, le préfixe de longueur N est indépendant de N ;
2. le classement est décroissant en équité — sans filtre, au niveau `normal`, et à filtre étroit ;
3. `rankPlays[0]` est le coup que rend `bestPlay` ;
4. chaque candidat porte cinq probabilités finies dans [0,1] ;
5. la décision de videau rend un verdict connu et des équités finies.

`package_artifact.py` **exécute** les deux scripts de `verify/` sur l'artefact produit avant de le
déclarer publiable. Une promesse qu'on ne tient pas soi-même avant de publier n'est pas une
garantie, c'est une intention.

## Ce que cet épisode dit du reste

La parité WebAssembly ↔ natif était verte pendant tout ce temps, à `0,000e+0` en scalaire. Elle
mesure que le module **calcule** comme le natif ; elle ne dit rien de ce qu'il **répond**. Les deux
défauts vivaient entre les deux, dans l'enrobage — la seule couche que ni les tests Python ni la
parité ne traversaient.

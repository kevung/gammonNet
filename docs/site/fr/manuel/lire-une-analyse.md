# Lire une analyse

## Les coups candidats

```javascript
const plays = evaluator.rankPlays("4HPwATDgc/ABMA", 0, 3, 1,
  { ...Evaluator.level("normal"), max: 5 });
```

Chaque candidat porte :

| Champ | Ce que c'est |
|---|---|
| `equity` | l'équité du coup, **du point de vue de celui qui le joue** |
| `resultId` | l'identifiant de la position atteinte |
| `probs` | les cinq probabilités, **du même point de vue que `equity`** : `[gain, gammon, backgammon, gammon adverse, backgammon adverse]` |

```{admonition} Un seul référentiel, depuis la v1.1.0
:class: note

Les cinq probabilités sont celles du **joueur qui joue le coup** — le même côté que l'`equity`
posée à côté d'elles, et le même que celui de `cubeDecision` et de `/v1/eval`. Vous pouvez le
vérifier vous-même : à `ply: 0`,

    2·gain + gammon + backgammon − gammon adverse − backgammon adverse − 1 = equity

C'est le contrôle qui a fermé le piège, parce qu'aucun autre ne le pouvait : une distribution
retournée reste parfaitement imbriquée, donc parfaitement plausible.

**Avant la v1.1.0**, `probs` décrivait la position *résultante* — donc l'adversaire — et un champ
`forMover` portait le retournement. `forMover` n'existe plus : le laisser à côté d'un `probs` déjà
retourné aurait recréé le piège. Un code qui l'utilisait lit `undefined`, ce qui est bruyant.
```

```{admonition} Le côté est le bon, la profondeur ne l'est pas
:class: warning

Au-delà de `ply: 0`, les cinq probabilités viennent de la **passe superficielle** qui a servi à
classer les coups, alors que l'équité vient de la recherche profonde. Elles restent une lecture
0-ply légitime de la position atteinte, mais l'identité ci-dessus ne tient plus, et ce ne sont pas
les nombres qui ont produit l'équité affichée à côté. `/v1/eval` tranche autrement : il les omet
dès `ply >= 1` plutôt que d'en montrer d'une autre profondeur.
```

Exemple réel, position de départ et jet 3-1, au niveau « normal » :

| # | Équité | Gain | Gammon | Backgammon | Gammon adv. | BG adv. |
|---|---|---|---|---|---|---|
| 1 | **+0,1669** | 0,5544 | 0,1725 | 0,0077 | 0,1180 | 0,0054 |
| 2 | −0,0084 | 0,4981 | 0,1422 | 0,0062 | 0,1442 | 0,0085 |
| 3 | −0,0361 | 0,4905 | 0,1308 | 0,0056 | 0,1425 | 0,0065 |

Le premier est `8/5 6/5` — le meilleur coup d'ouverture connu sur ce jet.

## La décision de videau

```javascript
const cube = evaluator.cubeDecision("4HPwATDgc/ABMA", 0, {
  owner: 0,             // 0 centré, 1 à vous, 2 à l'adversaire
  ply: 2, filterTop: 3, filterInner: 1,
  efficiency: 0.688,    // celle de l'état de possession — voir plus bas
});
```

Elle rend :

| Champ | Ce que c'est |
|---|---|
| `action` | `no-double`, `double-take`, `double-pass`, ou `too-good` |
| `equityNoDouble` | l'équité si vous ne doublez pas |
| `equityDouble` | l'équité si vous doublez |
| `takePoint` | le point de prise de l'adversaire |
| `probs` | les cinq probabilités de la position, avant le jet |

```{admonition} Pourquoi les deux équités, et pas seulement le verdict
:class: note

**Une décision juste à 0,001 près et une décision juste à 0,5 près ne sont pas la même décision.**
Le verdict seul le cache ; la marge le montre.
```

**Les efficacités sont mesurées**, une par état de possession — centré 0,688, possédé 0,566,
adverse 0,687. Elles sont ajustées sur les données de ce projet, jamais empruntées à une constante
publiée. Passez celle qui correspond à l'état du videau.

## Au score

Une même position ne se joue pas pareil en money et à 2-away :

```javascript
const plays = evaluator.rankPlays(id, 0, d1, d2, {
  ...Evaluator.level("normal"),
  useMatch: true, awayOnRoll: 2, awayOpponent: 4, cube: 1, crawford: false,
});
```

`awayOnRoll` et `awayOpponent` sont les points **restant à marquer**. Un score hors de la table
d'équité de match est **refusé**, pas rabattu silencieusement en money.

## La valuation cubeful du coup

Le videau ne change pas seulement la décision de doubler : il change **le coup**. Avec le videau en
main on joue vers l'encaissement ; avec le videau contre soi, on joue sobre.

```javascript
evaluator.rankPlays(id, 0, d1, d2, {
  ...Evaluator.level("normal"), cubeOwner: 1, efficiency: 0.566,
});
```

Mesuré sur une même position : **−0,167** avec le videau en main, **−0,449** avec le videau contre
soi.

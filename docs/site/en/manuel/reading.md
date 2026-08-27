# Reading an analysis

## Candidate moves

```javascript
const plays = evaluator.rankPlays("4HPwATDgc/ABMA", 0, 3, 1,
  { ...Evaluator.level("normal"), max: 5 });
```

| Field | What it is |
|---|---|
| `equity` | the equity of the move, **from the point of view of the player making it** |
| `resultId` | the identifier of the position reached |
| `probs` | the five probabilities of the **resulting** position |
| `forMover` | the same, **flipped** for display |

```{admonition} The probability trap
:class: warning

The five probabilities describe the **resulting** position — so they are seen by the **opponent**,
who now has the roll. That is the engine's convention, and flipping it silently would produce five
perfectly plausible, wrong numbers.

`forMover` does the conversion. Display that one.
```

Real example, opening position, roll 3-1, at the "normal" level:

| # | Equity | Win | Gammon | Backgammon | Opp. gammon | Opp. BG |
|---|---|---|---|---|---|---|
| 1 | **+0.1669** | 0.5544 | 0.1725 | 0.0077 | 0.1180 | 0.0054 |
| 2 | −0.0084 | 0.4981 | 0.1422 | 0.0062 | 0.1442 | 0.0085 |

The first is `8/5 6/5` — the known best opening play on that roll.

## The cube decision

```javascript
const cube = evaluator.cubeDecision("4HPwATDgc/ABMA", 0, {
  owner: 0,             // 0 centred, 1 yours, 2 the opponent's
  ply: 2, filterTop: 3, filterInner: 1,
  efficiency: 0.688,
});
```

| Field | What it is |
|---|---|
| `action` | `no-double`, `double-take`, `double-pass`, or `too-good` |
| `equityNoDouble` | the equity of not doubling |
| `equityDouble` | the equity of doubling |
| `takePoint` | the opponent's take point |
| `probs` | the five probabilities before the roll |

```{admonition} Why both equities, not just the verdict
:class: note

**A decision that is right by 0.001 and one that is right by 0.5 are not the same decision.** The
verdict alone hides that; the margin shows it.
```

**Cube efficiencies are measured**, one per ownership state — centred 0.688, owned 0.566, opponent's
0.687 — fitted on this project's own data, never borrowed from a published constant.

## At a match score

```javascript
const plays = evaluator.rankPlays(id, 0, d1, d2, {
  ...Evaluator.level("normal"),
  useMatch: true, awayOnRoll: 2, awayOpponent: 4, cube: 1, crawford: false,
});
```

A score outside the match equity table is **refused**, not silently reduced to money play.

## Cubeful move valuation

The cube changes not only whether you double, but **which move you play**: bold toward the cash when
you own it, sober when it is against you. Measured on one position: **−0.167** owning the cube,
**−0.449** with it against you.

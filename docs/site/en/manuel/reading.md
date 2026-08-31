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
| `probs` | the five probabilities, **from the same point of view as `equity`**: `[win, gammon, backgammon, opponent gammon, opponent backgammon]` |

```{admonition} One frame of reference, since v1.1.0
:class: note

The five probabilities are the **mover's** — the same side as the `equity` next to them, and the
same side as `cubeDecision` and `/v1/eval`. You can check it yourself: at `ply: 0`,

    2·win + gammon + backgammon − opp. gammon − opp. backgammon − 1 = equity

That is the check that closed the trap, because nothing else could: a mirrored distribution is
still perfectly nested, hence perfectly plausible.

**Before v1.1.0**, `probs` described the *resulting* position — the opponent's — and a `forMover`
field carried the flip. `forMover` is gone: leaving it beside an already-mirrored `probs` would
have rebuilt the trap. Code that used it now reads `undefined`, which is loud.
```

```{admonition} Right side, wrong depth
:class: warning

Past `ply: 0` the five probabilities come from the **shallow ranking pass**, while the equity comes
from the deep search. They remain a legitimate 0-ply reading of the position reached, but the
identity above no longer holds, and they are not the numbers that produced the equity beside them.
`/v1/eval` decides the other way: it omits them once `ply >= 1` rather than show a distribution
from a different depth.
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

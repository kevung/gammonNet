# Assumptions and limits

This page aims to be **exhaustive**. It lists what the project assumes, what it has not measured,
and what it has measured to its own disadvantage.

## Not measured

| | Why |
|---|---|
| **eXtreme Gammon** | No XG oracle exists in this repository. That half of the objective does not follow from equivalence to GNU Backgammon |
| **"Stronger" than GNU Backgammon** | The +0.0400 ppg measured cubeless does not reproduce with the cube wired in |
| **Strength of the pruned configuration** | Bounded at ~0.028 ppg over 10 000 pairs, not resolved: the expected effect (~0.013) is half the interval |
| **PR over a realistic mixture** | The corpus is contact-only; the measured PR is **probably pessimistic**, by an unquantified margin |
| **Mobile budget** | The penalty measured in August was ×2.12 to ×2.83 on two devices, not replayed since the optimisations |
| **Chromium** | Recent browser measurements are Firefox only |
| **The WebAssembly penalty itself** | Not replayed: the native baseline ran on a different machine from the browser, which would measure processor differences as much as target differences |
| **A per-terrain pruning `k`** | Races sit at 91.3 % agreement against 98.3 % in contact |
| **4-ply quality** | The depth exists and its cost is measured (100 to 257 s/decision); its value is not |

## Assumed

- **That the published reference's arbiter resembles ours.** Agreement at all three PR depths argues
  strongly; it does not prove.
- **That the Kazaross-XG2 match equity table is correct.** It is checked against GNU Backgammon's
  output, which tests agreement, not truth.
- **That measured cube efficiencies transport** outside the domain they were fitted on.

## Limits of the published artefact

- **The exact bearoff table is not included** — 1.2 GiB. Cost: **0.00028 equity per bearoff
  decision**, worst case 0.0919 on a single decision. **It is the tail, not the mean, that costs.**
- **The light variant is float16**, moving 0.015 % of decisions — ~1e-9 equity.
- **Pruning is on by default at `k = 12`**, costing +0.00023 equity per decision. Turning it off
  restores the previous search, bit for bit.

## Limits of the metrics

- **A PR against GNU Backgammon is reproducible only to ~±0.005** from build to build.
- **Equity scales do not compare across engines.** Ours is `2·MWC − 1`; gnubg's in a match context
  is EMG. They are affine in one another, so **rankings** compare and **magnitudes** do not.
- **Each arbiter favours itself** by construction. Hence two columns, neither published alone.

## Measured to our disadvantage

- **The network's edge vanishes under search**: +0.00247 equity per decision at 0-ply, **+0.00007 at
  2-ply**. What our network knows extra is precisely what two ply of search recover on their own.
- **Depth is not a strength lever**: a whole extra ply buys +0.00022 — inside the noise — for fifteen
  times the cost. Measured twice, with two arbiters.
- **We remain ~24× to ~56× slower than GNU Backgammon per decision.**
- **Four optimisation projections were refuted** by measurement, one of them going the wrong way.

## Errors found, and what they say about the apparatus

A measurement apparatus is judged by what it catches.

| Error | How it was caught |
|---|---|
| A 4.8-day campaign was measuring a crippled GNU Backgammon | A signature in the journal: 84.1 % of post-Crawford pairs at an impossible cube |
| A badly posed filter made 1-ply identical to 0-ply | The blocking PR check |
| An artefact shipped a table the engine cannot load | The module **refused** it instead of ignoring it |
| An equity moved by 3e-9 after a refactor | A bit-for-bit comparison |
| A match state not flipped in the match analysis | Review, before publication |

In every case what worked was a **refusal** or a **verification**, never an intuition.

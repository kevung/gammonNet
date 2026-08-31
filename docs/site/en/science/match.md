# Analysing a real match, decision by decision

## What this adds

The strength campaign returns a scalar over 50 000 pairs: **by how much**. It does not say **where**
the two engines differ, nor whether their disagreements matter. That is the first thing a user sees.

## Protocol

A real 7-point match played by humans in a tournament. 2-ply analysis, filter `(0,1,3)`, pruning
`k=12`, **at the real score and cube of each decision**.

**GNU Backgammon reads the file**: this repository reads neither `.mat` nor `.sgf` — a deliberate
boundary. It consumes only position identifiers, a score and a cube.

## Result

**139 decisions, agreement on the best move: 120/139 — 86.3 %.**

What each arbiter says the 19 disagreements cost:

| | Arbiter **gnubg** (EMG) | Arbiter **ours** (2·MWC−1) |
|---|---|---|
| median | **+0.0048** | +0.0009 |
| **maximum** | **+0.0195** | +0.0142 |
| below 0.01 | 13/19 | — |
| **above 0.05** | **0/19** | 0 |

## What this establishes

**It is the profile of an equivalent engine.** A weaker engine would betray itself through a
**tail** — a few disagreements at 0.05 or 0.10, on positions that decide a game. That tail does not
exist: the worst disagreement in the whole match is 0.0195, and GNU Backgammon itself only counts a
decision as mattering beyond ~0.05.

The two engines diverge **where several moves are close**, not where a game is decided.

```{admonition} This is not a strength measurement
:class: warning

139 decisions do not carry one. It is a **diagnostic**: it tells the nature of the disagreements,
not their weight over a season of play.
```

# Choosing a setting

A setting trades **time** for **quality**. Both are measured, and this page gives both — never one
without the other.

## The presets

| Preset | Internally | Native cost / decision | Browser cost / decision | A 7-point match *(≈130 decisions)* |
|---|---|---|---|---|
| **Instant** | 0-ply | 0.0013 s | 0.006 s | ~1 s |
| **Normal** | 2-ply `(0,1,3)`, pruning `k=12` | **0.306 s** | **2.7 s** | **74 s** *(8 workers)* |
| **Thorough** | 2-ply `(0,1,3)`, no pruning | 2.01 s | 9.8 s | ~4 min *(8 workers)* |

Browser costs are measured on **Firefox 154, SIMD build**, on an idle desktop machine. They depend
on the device; the measurement page ships so you can redo them.

## What pruning costs, and why `k = 12`

Measured over 300 contact decisions, arbiter = the unpruned search itself:

| `k` | Speed-up | Agreement with the unpruned search | Equity lost per decision |
|---|---|---|---|
| 3 | ×9.05 | 80.0 % | **+0.00389** |
| 5 | ×6.16 | 90.7 % | +0.00182 |
| 8 | ×4.75 | 96.3 % | +0.00031 |
| **12** | ×3.90 | **98.3 %** | **+0.00023** [−0.00000 ; +0.00067] |

```{admonition} Do not lower k without measuring
:class: warning

At `k = 3` the equity lost is **+0.00389 per decision** — **eighteen times what a whole extra ply
of search buys** (+0.00022, measured). That is not a "fast" setting: it is a setting that plays
worse.

`k = 12` is the only point on the curve where nothing measurable is paid.
```

**Races are the weak spot**: at `k = 12`, agreement is 91.3 % in races against 98.3 % in contact
positions. A per-terrain `k` has not been measured.

## Depth

| Depth | Native cost / decision | What it buys |
|---|---|---|
| 0-ply | 0.0013 s | the network alone |
| 1-ply | ~0.3 s | **the decisive gain**: PR 1.088 → 0.499 |
| 2-ply | 0.306 s *(pruned)* | PR 0.499 → 0.273 |
| 3-ply | 10.6 s *(pruned)* | **+0.00022 equity per decision — inside the noise** |

```{admonition} Depth beyond 2-ply is not a strength lever
:class: important

Measured twice, with two independent arbiters: going from 2-ply to 3-ply buys **+0.00022 equity per
decision** — inside the noise — for fifteen times the cost.

3-ply and 4-ply exist to **verify** that we stay level with GNU Backgammon at its own depths, not
to analyse games.
```

## Parallelism

The Web Worker pool reaches **×6.2 on eight threads** (26 667 evaluations/s measured). That is the
difference between **350 s** and **74 s** for a match.

| Workers | Evaluations/s | Speed-up |
|---|---|---|
| 1 | 4 301 | ×1 |
| 4 | 13 333 | ×3.1 |
| 8 | 26 667 | ×6.2 |

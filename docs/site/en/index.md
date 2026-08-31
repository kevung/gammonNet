# gammonNet

A **backgammon position evaluator**: a neural network, an expectiminimax search, a match equity
table and exact bearoff tables, compiled for the browser (WebAssembly) and for native use.

```{admonition} What this project claims, and how to check it
:class: important

**Equivalent to GNU Backgammon at 2-ply** — measured over 50 000 duplicate pairs in money play
(−0.0119 ppg, 95 % CI [−0.0310 ; +0.0074]) and 50 000 pairs in 7-point matches (50.42 % MWC,
[50.16 ; 50.69]).

**"Stronger" is not established**, and **eXtreme Gammon has not been measured**.

Every figure in this documentation points to its measurement record and to the command that
reproduces it. The published artefact ships what you need to **check for yourself** that it gives
the right answers, without taking our word for it.
```

## The three volumes

::::{grid} 1 1 3 3

:::{grid-item-card} User manual
:link: manuel/index
:link-type: doc

Install, pick a setting, read an analysis, verify the artefact. What to know before relying on it.
:::

:::{grid-item-card} Scientific documentation
:link: science/index
:link-type: doc

The architecture, the measurement protocol, the benchmarks, the optimisations — and **every
assumption and limit**, including the ones that do not flatter us.
:::

:::{grid-item-card} Developer documentation
:link: developpeur/index
:link-type: doc

Repository layout, the invariants that are invisible, how to reproduce every measurement.
:::

::::

## At a glance

| | |
|---|---|
| Strength, cubeful money | **−0.0119 ppg** [−0.0310 ; +0.0074], 50 000 pairs |
| Strength, 7-point match | **50.42 % MWC** [50.16 ; 50.69], 50 000 pairs |
| Error rate (PR), 2-ply | **0.273** [0.190 ; 0.364] — published reference: 0.22 |
| Move agreement with gnubg over a real match | **86.3 %**, no disagreement above 0.02 equity |
| Cost of one 2-ply decision, native | **0.306 s** |
| Cost of a 7-point match, browser, 8 workers | **74 s** |
| Artefact size | **1.06 MiB** of float16 weights |

```{toctree}
:hidden:
:maxdepth: 2

manuel/index
science/index
developpeur/index
```

---

*Version française : <a href="../fr/">/fr/</a>*

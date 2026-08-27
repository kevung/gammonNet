# Scientific documentation

```{toctree}
:maxdepth: 2

architecture
protocol
strength
pr
match
optimisations
limits
reproducing
```

## Who this is for

Anyone who wants to **judge** this engine rather than use it. It is written to be read by someone
who does not believe us, and organised so it can be contradicted: every figure carries its
protocol, its volume, its confidence interval, and the command that reproduces it.

## The question, as it was posed

> A backgammon position evaluator **at least as strong as GNU Backgammon and eXtreme Gammon**,
> distributable in a browser, whose every claim of strength is measured.

## The answer, as measured

| | Volume | Measure | 95 % CI |
|---|---|---|---|
| Strength, cubeful money | 50 000 pairs | **−0.0119 ppg** | [−0.0310 ; +0.0074] |
| Strength, 7-point match | 50 000 pairs | **50.42 % MWC** | [50.16 ; 50.69] |
| Error rate (PR), 2-ply | 600 decisions | **0.273** | [0.190 ; 0.364] |

**Equivalent to GNU Backgammon at 2-ply: confirmed.**
**"Stronger": not established.**
**eXtreme Gammon: not measured**, and that half of the objective does not follow from the other.

## The rule that governs this volume

> **A network given an input it has never seen returns five perfectly plausible probabilities.**

That is this domain's central failure mode, and it is **silent**. Two consequences shape the whole
project:

1. **The measurement harness was built before the model.** You cannot improve what you cannot
   measure.
2. **A model a build cannot evaluate is refused, never approximated.** A missing input defaulting
   to zero is a bug that does not show.

You will find several measurements here that **do not flatter us**, and several hypotheses the
measurement **refuted**. They are here because documentation containing only the good news would be
a brochure, not evidence.

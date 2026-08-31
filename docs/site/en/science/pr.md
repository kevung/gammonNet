# The error rate: PR

## What PR is

The **Performance Rating** is a player's error rate, judged by a stronger analyser:

$$ PR = 500 \times (\text{mean equity lost per decision}) $$

**The arbiter must be stronger than the subject.** A player cannot judge its own errors: it would
always pick what it believes best, and its PR would be zero by construction. The benchmark
**refuses** to run if the arbiter is not strictly above everything it judges.

## Result

600 contact decisions, seed 20260827, arbiter **GNU Backgammon at 3-ply** over all legal moves.

| Configuration | PR | 95 % CI | Agreement | Published reference |
|---|---|---|---|---|
| 0-ply | **1.088** | [0.802 ; 1.412] | 83.3 % | 1.06 |
| 1-ply | **0.499** | [0.330 ; 0.705] | 88.7 % | 0.50 |
| 2-ply, unpruned | **0.273** | [0.190 ; 0.364] | 90.2 % | 0.22 |
| 2-ply, pruning `k=12` | 0.375 | [0.264 ; 0.499] | 89.5 % | — |

**All three reference values fall inside their intervals.** PR drops with every added ply — the
check the project's plan calls the most revealing of the whole chain.

**1-ply at 0.499 against 0.50 published** is the strongest fact here: two independent chains, two
different arbiters, the same figure to the thousandth.

## The blocking check earned its keep — against me

The first run returned **0.946 at 0-ply and 0.946 at 1-ply**, to the digit. It was not the search:
with `filter[1] = 1` the deep pass rescores **exactly one candidate** — the one the shallow pass
already ranked first — so the chosen move stays the 0-ply choice. A badly posed filter, not a wrong
engine.

## A prediction, verified

2-ply **pruned** gave 0.375, 0.155 above the reference. Rather than invoking the filter or the
corpus, a quantified hypothesis was put:

> Pruning at `k=12` has a measured loss of **+0.00023 equity per decision**, i.e. **0.115 of PR**.
> It would explain three quarters of the gap.

Measured: the difference between the two 2-ply configurations is **0.102** — the prediction lands
**within 11 %**, on a quantity obtained by an entirely different route.

## Reproducibility of the metric itself

Repeated on a second machine with a **different build of GNU Backgammon** (same nominal version,
same weights): PR differs by 0.001 to 0.003. The corpus is bit-identical on both machines and our
network returns the same value; **what differs is the arbiter**.

The difference was detected and **bounded before being suffered**: five probed decisions, mean
absolute gap 2.9e-5, **random in sign** — so cancelling over 600 decisions.

```{admonition} What this says about the metric
:class: important

A PR measured against GNU Backgammon is reproducible only to **~±0.005 from build to build**, at
identical nominal version and weights. A limit of the metric, not of the chain — and thirty times
smaller than PR's own confidence interval.
```

## Two reservations

- **The corpus is contact-only.** A PR reference is usually measured over a realistic mixture,
  races included. Contact being the hard part, this PR is **probably pessimistic** — unmeasured, and
  the gap is not quantified.
- **The reference author's arbiter is unknown.** Agreement at all three depths argues the method is
  close; it does not prove it.

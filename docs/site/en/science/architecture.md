# The architecture, and why each piece exists

A backgammon evaluator is not a neural network. It is **five components**, each closing a gap the
others cannot.

## 1. The encoding: 196 features

A position becomes 196 numbers — the format the reused network expects, and the **bottleneck of the
project**: an error here is silent and contaminates every later measurement. The codec was validated
position by position against an independent generator before anything else was written.

```{admonition} A fact that matters later
:class: note

**The vector is nearly empty**: 26.0 non-zero entries out of 196 on average, and 38.3 for the
**union** over a 32-move sibling list — siblings differ by one move, so their non-zeros almost
coincide. That fact later yielded an exact speed-up.
```

## 2. The network: 196 → 512 → 512 → 256 → 128 → 5

Five **nested** outputs: P(win), P(win gammon), P(win backgammon), P(lose gammon), P(lose
backgammon). The weights are **Alexander Strehl's** (MIT), trained by self-play, and have **not**
been retrained.

The network is **cubeless** and **blind to the score**. Everything that follows exists to close
that.

## 3. Expectiminimax search: 0 to 4 ply

```
V(pos, 0) = cubeless money equity of pos, from pos.turn's point of view
V(pos, k) = Σ over the 21 rolls  w(roll) × max over plays ( −V(result, k−1) )
```

Weights are 1/36 for a double and 2/36 otherwise — and a test checks it rather than trusting it.

```{admonition} The negation, which fails silently
:class: warning

`GnPlay.result` has already **handed over the turn**. The value of a play, to the player making it,
is therefore the **negation** of what the network says about the resulting position.

Getting it backwards produces no crash and no warning: the engine plays its opponent's best move
with total confidence.
```

**Depth equivalence with GNU Backgammon is measured**, not assumed — see [](pr).

## 4. Match equity

The network being cubeless, playing at a score requires a **match equity table**: Kazaross-XG2, the
work of Neil Kazaross, with attribution.

```{admonition} The subtlety that is invisible in money play
:class: important

At an intermediate node, **the opponent maximises their match equity**, not their cubeless equity.
At 4-away/2-away a gammonish play is not worth what it is worth in money.

A 2-ply search that maximised cubeless equity at intermediate nodes is **wrong in match play** —
and **no money test would ever say so**.
```

The search therefore swaps the match state at every ply and works in `2·MWC − 1`: on that scale the
opponent's value is still the **negation**, exactly as in money play.

## 5. The cube

Janowski's model, at **measured** efficiency — never borrowed from a published constant. Three
efficiencies, one per ownership state: 0.688 / 0.566 / 0.687, fitted on our own data.

The cube acts in two places: the **decision** to double, take or pass; and **the choice of move**,
through cubeful leaf valuation.

## 6. Exact bearoff tables

In the endgame there is nothing left to estimate: the value is **exactly computable**.

**What it closes is quantified**: 0.00028 equity per bearoff decision, where GNU Backgammon consults
its own table and loses nothing. The worst case measured at 1-ply is 0.0919 on a single decision —
**it is the tail, not the mean, that costs**.

```{admonition} It does not ship
:class: warning

The table weighs **1.2 GiB**. No web artefact carries it. The published engine therefore falls back
on the network in the endgame, at the cost above. A real limit, not an oversight.
```

## The pruning network

A sixth component, distilled from **our own network** — never from GNU Backgammon: a 196 → 32 → 5
network, 92.5× cheaper per evaluation, which **sorts** moves so the big one only scores a handful.

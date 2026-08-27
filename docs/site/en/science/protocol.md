# The measurement protocol

## What a claim of strength must carry

Three things, always: **the protocol, the volume, the confidence interval**.

There is a quantitative reason: **below roughly a million games per pairing, differences between
good engines do not emerge from the noise.** A figure without its interval suggests a precision that
does not exist.

## Common dice

Comparing two engines on different games measures luck as much as skill. Every strength measurement
here uses **duplicate pairs**: the same game is played twice with the same dice, the engines
swapping seats.

- Variance drops by orders of magnitude.
- **An engine against itself totals exactly zero**, at any score. That is a test, and it earned its
  keep: the score had to be attached to the seat rather than travel with the engines for the
  property to hold.

Dice are a **pure function** of `(seed, trial, ply)` — nothing advances, nothing is carried between
calls. A stateful generator would be equivalent only as long as both variants consumed the same
number of draws, which they do not; the failure would be **silent**.

## Bootstrap over pairs, never over games

The two games of a pair share their dice: they are **not independent**. Bootstrapping over games
would give a falsely narrow interval.

## Two arbiters, never one

When two engines choose different moves, a third party is needed — and **no third party is
neutral**:

| Column | Arbiter | Bias |
|---|---|---|
| ours | rollout driven by our network | in our favour |
| theirs | GNU Backgammon at greater depth | in theirs |

**Neither is published alone.** The result that means something is the one where both columns agree
on the sign.

## The evaluation fingerprint

Every campaign journal carries a **fingerprint** of the engine that produced it. A numerically
different build is **refused** when the journal is opened, rather than silently mixing two engines
into one measurement. That is what lets a multi-day campaign be interrupted and resumed while
staying identical to a single run.

## What the project refuses

- **Concluding "it works" without running the command and reading its output.**
- **Deriving a performance figure from reading code.** This volume contains several projections the
  measurement refuted; they are kept for that reason.
- **Approximating instead of refusing.**

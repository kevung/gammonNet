# What to know before relying on it

## The strength, as measured

**Equivalent to GNU Backgammon at 2-ply.** −0.0119 ppg [−0.0310 ; +0.0074] over 50 000 pairs in
money play; 50.42 % MWC [50.16 ; 50.69] over 50 000 pairs in 7-point matches.

**"Stronger" is not established.** **eXtreme Gammon has not been measured.**

## The four things that change the answer

1. **The pruning setting.** At `k = 3` the engine is twice as fast as at 12 and loses **eighteen
   times** what a whole extra ply buys. Do not lower it without measuring.
2. **The worker pool.** Without it a match takes 350 s instead of 74.
3. **The score and the cube.** A position does not play the same in money and at 2-away. If you do
   not pass them, you get a *money* analysis whatever the real situation is.
4. **The exact bearoff table is not shipped** — it weighs 1.2 GiB. The endgame therefore falls back
   on the network, which costs **0.00028 equity per bearoff decision**. The worst case measured is
   0.0919 on a single decision: **it is the tail that costs, not the mean**.

## What the engine refuses to do

It **refuses** rather than approximates, deliberately:

- A model it cannot evaluate is **refused** — not loaded "as best it can".
- A score outside the match equity table **stops** the analysis.
- An unreadable position returns an error, not a plausible evaluation.

The reason is the central failure mode of this domain: **a network given an input it has never seen
returns five perfectly plausible probabilities**. A loud refusal beats a wrong number.

## What the project does not do

gammonNet **evaluates a position**. It does not read match files, manage games or users, and has no
interface. A position goes in, an evaluation comes out.

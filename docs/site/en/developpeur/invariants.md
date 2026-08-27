# The invariants that are invisible

These are properties a refactor can break **with no obvious test failing** and no message printed.
Each has cost something at least once.

## 1. Perspective

`GnPlay.result` has **handed over the turn**. The value of a play, to the player making it, is the
**negation** of what the network says about the resulting position.

Getting it backwards produces no crash and no warning: **the engine plays its opponent's best move
with total confidence.**

The same applies to the **match state** (the opponent is at `away_opponent`, not `away_on_roll`) and
to **cube ownership** (owned becomes opponent's). Both flip at every ply.

## 2. Bit-exactness

The project depends on it in three places: the **evaluation fingerprint** locking a campaign
journal; the **resumption** of an interrupted campaign, which must be identical to a single run; and
the **non-regression corpus**.

It is fragile in two ways:

**FMA contraction.** The compiler fuses `a×b + c` into an FMA — one rounding instead of two — and it
does so **depending on the shape of the surrounding code**. `-ffp-contract=off` is set on
`gn_search.c`, and only there: applying it to inference would move the network's outputs, hence the
fingerprint.

**Batch width.** The kernel always computes `GN_EVAL_BATCH` lanes: that is what guarantees a result
does not depend on how many sibling moves there are.

## 3. Cache neutrality

The cache replays the network's own answers; it invents none. **The pruning pass therefore may not
read it.**

If it did, a candidate would be scored by the **big** network when the cache holds it and by the
**small** one otherwise — the ranking, hence the move played, would depend on **evaluation
history**. Nothing would crash; runs would simply stop being reproducible.

And the small network must **never write** to that cache: one of its distributions stored there
would be served as the big network's for the rest of the process.

## 4. Dice purity

`roll_at` is a pure function of `(seed, trial, ply)`. Nothing advances, nothing is carried.

That is what makes common random numbers actually common across processes, orders and depths. A
stateful generator would be equivalent only while both variants consumed the same number of draws —
which they do not. The failure would be silent.

## 5. Refuse rather than approximate

- A model that cannot be evaluated is **refused**.
- A score outside the table **stops** the measurement.
- An unpairable GNU Backgammon move **stops** the measurement instead of being guessed — and that
  refusal is what revealed that the two generators sometimes keep different intermediates of the
  same compound move.

## 6. Never parse GNU Backgammon's move notation

Pairing is done **by resulting position**, reusing the already-verified codec. A second, unverified
way of reading a move is a source of silent error.

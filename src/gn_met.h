/*
 * gn_met.h -- from five probabilities to a match winning chance.
 *
 * The networks are cubeless and blind to the score. They emit five
 * probabilities; the score and the cube never enter the network. The conversion
 * happens HERE, afterwards, through the match equity table and the cube
 * position. That is the architecture of GNU Backgammon, and `BRIEF.md` section 6
 * explains why it is the only one that scales: a score-aware network would have
 * to learn a different function for every score and every cube level.
 *
 * WHY THIS FILE EXISTS AT ALL, rather than a scalar equity. `gn_infer.h` insists
 * that the distribution is the output and the money equity a mere projection.
 * This is the consumer that justifies the insistence: a match winning chance
 * needs P(gammon) and P(backgammon) separately, weighted by what each is worth
 * at THIS score. At 2-away/4-away a gammon often wins the match outright; in
 * money it is worth two points like any other. A scalar equity has already
 * thrown that away.
 *
 * ATTRIBUTION. The table is the work of **Neil Kazaross** -- see
 * `src/gn_met_table.h` and `THIRD-PARTY.md`.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_MET_H
#define GN_MET_H

#include "gn_infer.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The explicit table covers matches up to 25 points. See `gn_match_state_is_valid`
 * for what happens beyond -- it is refused, not extrapolated. */
#define GN_MET_MAX_AWAY 25

typedef struct {
    /* Points each player still needs. 1 means match point. Always >= 1: a
     * player who needs 0 points has already won, and there is nothing to
     * evaluate. */
    int away_on_roll;
    int away_opponent;

    /* Cube value: 1, 2, 4, 8, ... A game is worth `cube` times the stake. */
    int cube;

    /* Non-zero if the game being evaluated IS the Crawford game. Distinct from
     * "post-Crawford", which this module derives: if either player was already
     * at match point before the game, Crawford has been played. */
    int crawford;
} GnMatchState;

/*
 * Whether the state can be evaluated at all.
 *
 * Returns 1 if it can, 0 otherwise -- a non-positive away score, a cube that is
 * not a power of two, or a match longer than the explicit table covers.
 *
 * `BRIEF.md` section 3.3 foresees a Zadeh fallback beyond 25 points. It is not
 * implemented: matches longer than 25 points do not occur in play, and adding an
 * untested code path that nothing exercises would be a liability rather than a
 * feature. States beyond the table are therefore REFUSED. If the fallback is
 * ever wanted, this is the single place that has to change.
 */
int gn_match_state_is_valid(const GnMatchState *state);

/* The same state, seen from the other side of the table. Cube and Crawford
 * are shared facts; only the away scores trade places. Exported for the same
 * reason as `gn_cube_mirror`: the search and the rollout both swap at every
 * turn, and two readings of one swap is how they drift apart. */
GnMatchState gn_match_state_swap(GnMatchState state);

/*
 * Pre-Crawford table lookup: the match winning chance of a player who needs
 * `away_a` points against an opponent who needs `away_b`.
 *
 * Antisymmetric by construction: `pre(a, b) + pre(b, a) == 1`. Returns -1 for
 * an out-of-range request rather than clamping, because a clamped match equity
 * is a wrong number that looks right.
 */
double gn_met_pre(int away_a, int away_b);

/*
 * Post-Crawford: the TRAILER's match winning chance when the trailer needs
 * `away_trailer` points and the leader needs exactly 1.
 *
 * Returns -1 out of range.
 */
double gn_met_post(int away_trailer);

/*
 * The on-roll player's match winning chance if the game ends with `points`
 * going to one side.
 *
 * `on_roll_wins` selects which side. `points` is the raw number of points --
 * the caller has already multiplied by the cube.
 *
 * Returns -1 if the state is not evaluable.
 */
double gn_met_after(const GnMatchState *state, int points, int on_roll_wins);

/*
 * THE CONVERSION. The on-roll player's match winning chance, given the five
 * nested probabilities of the position.
 *
 * The six mutually exclusive outcomes come from `gn_probs_exclusive`, which is
 * called rather than reimplemented: T10 found that subtracting nested
 * probabilities naively yields a NEGATIVE probability on real positions, and
 * this function is exactly the consumer that would have carried it into a match
 * equity. The fragile subtraction is written once, there.
 *
 * Returns -1 if the state is not evaluable.
 */
double gn_match_winning_chance(const GnMatchState *state,
                               const float probs[GN_NUM_OUTPUTS]);

/*
 * Cubeless match equity, in the "equivalent to money" scale that engines print.
 *
 * `2 * mwc - 1`, so that 0 is an even match and +1 is a certain win. Convenient
 * for comparing against a money equity, and meaningless as an input to anything
 * else -- the match winning chance is the real quantity.
 */
double gn_match_equity(const GnMatchState *state,
                       const float probs[GN_NUM_OUTPUTS]);

#ifdef __cplusplus
}
#endif

#endif /* GN_MET_H */

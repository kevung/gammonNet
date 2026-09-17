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
 * This is the caller that justifies the insistence: a match winning chance
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
 * WHICH TABLE IS ACTIVE, AND HOW IT IS REPLACED.
 *
 * The compiled-in table is Kazaross-XG2 (`gn_met_table.h`). It is the default
 * and nothing has to be called to get it. Two callers need to replace it:
 *
 *   - T97, which COMPUTES a table from this engine's own play and has to
 *     consult the cells it has already produced while it produces the rest;
 *   - any artefact that ships a table of this project's own making.
 *
 * A mutable global is a way for a measurement to run against a table nobody
 * can name afterwards. That is why the name travels with the values and
 * `gn_met_name` exists: every bench that loads a table prints what it loaded.
 *
 * `gn_met_load` reads the `GNMET1` file `gn_met_write` produces. It REFUSES a
 * file whose sizes differ, whose values leave [0, 1], or that is truncated --
 * a match equity table half-read is a table of plausible wrong numbers.
 *
 * Returns 0 on success, negative on refusal. Not thread-safe: replace the
 * table before the workers start, never while they run.
 */
int gn_met_load(const char *path);

/*
 * Install a table held in memory. `pre` is `size * size` row-major, `post` is
 * `size` long, both indexed from away-1. Same refusals as `gn_met_load`.
 */
int gn_met_set(const double *pre, int pre_size,
               const double *post, int post_size, const char *name);

/* Back to the compiled-in table. */
void gn_met_reset(void);

/* The name of the active table. Never NULL. */
const char *gn_met_name(void);

/*
 * Pre-Crawford table lookup: the match winning chance of a player who needs
 * `away_a` points against an opponent who needs `away_b`.
 *
 * Antisymmetric for the compiled-in table: `pre(a, b) + pre(b, a) == 1`. A
 * table installed at runtime is antisymmetric only to the precision it was
 * computed with -- T97 verifies that on its output rather than imposing it,
 * since a table that imposes an identity cannot demonstrate it.
 *
 * Returns -1 for an out-of-range request rather than clamping, because a
 * clamped match equity is a wrong number that looks right.
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
 * this function is exactly the caller that would have carried it into a match
 * equity. The fragile subtraction is written once, there.
 *
 * Returns -1 if the state is not evaluable.
 */
double gn_match_winning_chance(const GnMatchState *state,
                               const float probs[GN_NUM_OUTPUTS]);

/*
 * Cubeless match equity on the MATCH scale: `2 * mwc - 1`, so that 0 is an even
 * match, +1 a certain match win and -1 a certain match loss.
 *
 * NOT the equity engines print. XG and GNUbg display NORMALISED equity
 * (GNUbg's `mwc2eq`), anchored on the CURRENT CUBE rather than on the match:
 *
 *     eq = (2*mwc - cash - pass) / (cash - pass)
 *
 * with `cash`/`pass` the MWC after collecting/conceding the cube's own value
 * dry (`gn_met_after(state, cube, ...)`). The value below is that same formula
 * with cash = 1 and pass = 0, so the two coincide at double match point and
 * NOWHERE else: at 5-away/5-away this scale is 6.4x smaller than the printed
 * one, and at a lopsided score it is shifted as well, `cash + pass` no longer
 * being 1.
 *
 * That makes it a valid INTERNAL scale -- a search ranking and a cube verdict
 * are invariant under any increasing affine map of the MWC, which is all this
 * is -- and a wrong one to hand to a user or to store next to another engine's
 * numbers. An earlier version of this comment called it "the equivalent to
 * money scale that engines print"; a caller believed it and displayed match
 * equities six times too small. Convert at the edge.
 */
double gn_match_equity(const GnMatchState *state,
                       const float probs[GN_NUM_OUTPUTS]);

#ifdef __cplusplus
}
#endif

#endif /* GN_MET_H */

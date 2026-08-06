/*
 * gn_rollout.h -- the independent arbiter (T39).
 *
 * WHY THIS EXISTS. Agreement with GNU Backgammon cannot establish that we are
 * BETTER than GNU Backgammon -- at best that we resemble it, and an engine that
 * resembles gnubg perfectly is exactly as good as gnubg, never better. Wherever
 * two engines disagree, something has to say which one was right. In the
 * bearoff domain the two-sided table says it exactly (see gn_bearoff). Outside
 * it, nothing does, and this is the substitute: play the position out many
 * times and average.
 *
 * THE RESERVATION, WHICH TRAVELS WITH EVERY RESULT. A rollout conducted BY our
 * network is biased in our favour -- it scores the future with the same
 * approximation that chose the move. A gnubg rollout is biased in theirs.
 * Neither column is presented alone; `PLAN.md` T39 makes that a criterion, not
 * a courtesy.
 *
 * ── THE THREE THINGS THAT MAKE THIS AFFORDABLE ──────────────────────
 *
 * 1. COMMON RANDOM NUMBERS. The quantity wanted is almost never one position's
 *    equity -- it is the DIFFERENCE between two candidate plays. Give both
 *    variants the same dice and the dice cancel; what remains is the difference.
 *    The dice here come from `seed` and the trial index alone, never from a
 *    running generator, so two rollouts launched from different positions in
 *    different processes still see identical sequences. A generator advanced by
 *    the play itself would break that silently, and the measurement would just
 *    be noisier for no visible reason.
 *
 * 2. TRUNCATION. A game played to the end is mostly noise accumulated after the
 *    interesting part. Stop after `truncate` plies and let the network score the
 *    position reached. That trades a little bias -- the network's own error at
 *    the horizon -- for a large variance reduction, and the trade is measurable:
 *    run the same corpus truncated and untruncated and compare.
 *
 * 3. A CHEAP POLICY. The rollout policy need not be the engine under test.
 *    0-ply is normally right: the arbiter's job is to sample the future, not to
 *    play it perfectly, and a 1-ply policy costs about five hundred times more
 *    per trial for a second-order improvement.
 *
 * ── WHAT IT DOES NOT DO ─────────────────────────────────────────────
 *
 * No cube. This rollout is cubeless, and a cubeful rollout is a different
 * object -- it has to decide, at every node, whether a player would double. That
 * belongs with T34, and building it on an unwritten cube model would produce
 * numbers that look like measurements.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_ROLLOUT_H
#define GN_ROLLOUT_H

#include "gn_infer.h"
#include "gn_rules.h"
#include "gn_search.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    /* Games played. The standard error falls as 1/sqrt(trials), so a factor of
     * two on precision costs a factor of four here -- which is why the common
     * dice above matter more than the trial count. */
    unsigned long trials;

    /*
     * Plies played before the network is asked. 0 plays the game out.
     *
     * A truncated rollout is NOT an approximation of a full one that happens to
     * be cheaper: it is a different estimator, with less variance and some bias.
     * Which is better depends on the network's accuracy at the horizon, and that
     * is measurable rather than arguable.
     */
    unsigned int truncate;

    /* The policy that plays the trial games. See note 3 above. */
    GnSearchConfig policy;

    /* Common random numbers. Two variants compared MUST share this. */
    unsigned long seed;
} GnRolloutConfig;

typedef struct {
    /* Mean cubeless money equity, from the point of view of the player on roll
     * in the position that was rolled out. */
    double equity;

    /* Standard error of that mean. Never report the equity without it: a
     * rollout without its interval is an opinion with decimals. */
    double standard_error;

    /* The five outcome frequencies, in the same nested convention as the
     * network: win, win-gammon, win-backgammon, lose-gammon, lose-backgammon.
     * Meaningful only for an untruncated rollout -- a truncated one ends on an
     * evaluation, not on an outcome, and these are then left at zero. */
    double frequencies[GN_NUM_OUTPUTS];

    unsigned long trials;
    /* Trials that hit the turn cap without finishing. Reported, never silently
     * counted as a draw. */
    unsigned long stalled;
} GnRolloutResult;

/* Sensible defaults: 1296 trials, truncated at 11 plies, 0-ply policy. */
GnRolloutConfig gn_rollout_config(unsigned long seed);

/*
 * Roll out `pos` and fill `out`. Returns 0 on success, -1 on error.
 *
 * The result is from `pos->turn`'s point of view, like everything else in this
 * codebase.
 */
int gn_rollout(const GnNetwork *net, const GnPosition *pos,
               const GnRolloutConfig *config, GnRolloutResult *out);

/*
 * Roll out each of `count` candidate positions under the SAME dice, and write
 * their equities to `equities` -- each from the point of view of the player who
 * moved INTO that position, so directly comparable as "how good was this play".
 *
 * This is the call an arbitration should use. Rolling the candidates out one by
 * one with separate seeds would work and would need roughly an order of
 * magnitude more trials for the same certainty on the difference.
 *
 * `standard_errors` may be NULL. It receives the error on each equity, which is
 * NOT the error on their difference -- the difference is far better determined,
 * precisely because the dice are shared. `gn_rollout_difference` gives that one.
 */
int gn_rollout_candidates(const GnNetwork *net, const GnPosition *results,
                          int count, const GnRolloutConfig *config,
                          double *equities, double *standard_errors);

/*
 * The difference between two candidates and the error ON THE DIFFERENCE,
 * computed from the paired trials rather than from the two marginals.
 *
 * Returns 0 on success. `difference` is `a - b`, from the point of view of the
 * player who moved.
 */
int gn_rollout_difference(const GnNetwork *net,
                          const GnPosition *a, const GnPosition *b,
                          const GnRolloutConfig *config,
                          double *difference, double *standard_error);

#ifdef __cplusplus
}
#endif

#endif /* GN_ROLLOUT_H */

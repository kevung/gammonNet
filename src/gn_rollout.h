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
 * ── THE CUBE (added 2026-08-08, once T34 existed to stand on) ───────
 *
 * The reservation above -- "building it on an unwritten cube model would
 * produce numbers that look like measurements" -- expired when T34 landed:
 * the cube model is written, fitted against the exact table, and measured.
 * With `use_cube`, every trial carries a LIVE cube: before each roll the
 * player who may double consults the cube decision -- the EXACT table
 * verdict inside the two-sided database's domain, the fitted model outside
 * it -- a pass ends the trial at the current stake, a take doubles it and
 * hands the cube over. Truncated trials are valued by the cubeful leaf value
 * at the horizon, times the cube. Equities are in units of the INITIAL cube.
 *
 * That in-domain exactness is also the non-bias control: on positions the
 * table covers, cube verdicts and checker play (via a cubeful policy) are
 * both optimal, so the rollout must reproduce the table's own cubeful equity
 * within its interval -- measured, not assumed (bench/rollout_bias.py).
 *
 * MATCH trials (added 2026-08-08): `use_match` ends the game AT THE SCORE --
 * points become the score reached, the score a match winning chance through
 * the equity table, Crawford and match wins included; the §9 recursion
 * prices the live cube and values truncated horizons. See the config note.
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

    /*
     * The live cube (see the header note). `cube_owner` is a GnCubeOwner as
     * seen by the player on roll in the position handed in; the rollout
     * mirrors it at every turn, like the search does. `cube_x[o]` is the
     * cube efficiency used when the state, seen from the decider, is `o` --
     * three values because the fit measured three (t34-efficacite.json), and
     * indexed by GnCubeOwner. `jacoby` is forwarded to the model's decision
     * (money semantics, spec §4). All ignored unless `use_cube`.
     */
    int use_cube;
    int cube_owner;
    double cube_x[3];
    int jacoby;

    /*
     * Skip the cube consultation at ply 0 -- the handed-in position's player
     * on roll has already passed their doubling point THIS turn; everyone
     * doubles freely from the next turn on.
     *
     * This is not a tuning knob; it selects which QUESTION the rollout
     * answers, and the two-sided table settled which is which (probe of
     * 2026-08-08): a race where the leader would gladly cash now but whose
     * future double windows are all worthless carries the SAME stored equity
     * for all four cube states -- so the stored cubeful equities exclude the
     * current turn's option, and only a deferred rollout can reproduce them.
     * Set it to arbitrate a cube DECISION (the "no double" branch means
     * exactly "I did not double this turn") and to hit the table's numbers;
     * clear it for a post-move position, whose opponent's turn begins with
     * their option intact.
     */
    int cube_defer_first;

    /*
     * Luck-based variance reduction (the idea gnubg documents; reimplemented
     * from the idea).
     *
     * At every ply the roll's LUCK is the 0-ply best-play equity under the
     * roll actually thrown, minus the probability-weighted average of that
     * quantity over all 21 rolls. Each term has expectation EXACTLY zero
     * given the position -- whatever evaluator computes it -- so subtracting
     * the trial's accumulated luck (signed to the rolled-out player's view,
     * scaled by the live cube at that ply) changes no expectation, only the
     * variance. A bad evaluator makes the reduction smaller, never the
     * answer wrong.
     *
     * The price is evaluating all 21 rolls' candidates at every ply, roughly
     * the cost of a 1-ply search per move played. Whether that buys more
     * certainty per second than spending the same time on extra trials is a
     * MEASUREMENT (bench/vr_gain.py), not a property of the idea.
     */
    int variance_reduction;

    /*
     * Stop on the confidence interval instead of a fixed count: once at least
     * `min_trials` trials are in, the rollout ends as soon as the standard
     * error of its mean falls to `target_se`, checked every 36 trials (a
     * whole roll family, so the opening dice stay balanced). Zero keeps the
     * fixed-count behaviour; `trials` is always the CAP, and a result that
     * hits the cap without reaching the target simply reports the error it
     * got -- the result carries its interval either way.
     *
     * Two rollouts compared under common dice may now stop at different
     * counts. For a difference that matters, use `gn_rollout_difference`,
     * which stops on the error OF THE DIFFERENCE -- the only criterion that
     * pairs the trials it keeps.
     */
    double target_se;
    unsigned long min_trials;

    /*
     * MATCH trials (the piece gn_rollout.h's own header note called "named,
     * not omitted" -- until now).
     *
     * `use_match` values every trial through the match equity table at
     * `match`, the state seen by the player on roll in the position handed
     * in; `match.cube` is the CURRENT cube value, so results come out in
     * match equity (2*MWC - 1), not in per-cube units. One GAME per trial:
     * a finished or cashed game becomes points, the points become the score
     * reached, and `gn_met_after` says what the match is then worth -- the
     * table prices all the following games, including Crawford sequences
     * and match wins. A truncated trial is valued by the §9 recursion at
     * the horizon (`gn_cube_value` with the state reached).
     *
     * `use_cube` keeps its meaning -- it turns the LIVE cube consultation on
     * -- but the decisions are priced by the §9 match model, never the money
     * one, and never the (money-only) exact table. Nobody is consulted
     * during the Crawford game, nor once the cube already covers both away
     * scores. An invalid `match` is refused at the door, not approximated.
     */
    int use_match;
    GnMatchState match;
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

    /* Cubeful trials only (zero otherwise): trials ended by a pass, and the
     * mean final cube in units of the initial one. A cashed game is NOT an
     * outcome frequency -- `frequencies` counts games played to the end, and
     * mixing the two would make both unreadable. */
    unsigned long cashed;
    double average_cube;

    /* Mean accumulated luck per trial, zero unless `variance_reduction`. Its
     * expectation is zero by construction, so a value many standard errors
     * from zero is the diagnostic that the correction itself is broken. The
     * uncorrected mean is `equity + average_luck`. */
    double average_luck;
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
/*
 * The most candidates one arbitration may price at once. Eight covers every
 * plausible play of a decision with room to spare; the paired accumulators are
 * stack arrays, and an unbounded `count` would be an unbounded frame.
 */
#define GN_ROLLOUT_MAX_CANDIDATES 8

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
/*
 * The arbitration call of T70: roll out `count` candidates under the SAME dice,
 * and report each one's equity, its difference to `pivot`, and the error ON
 * THAT DIFFERENCE, computed from the paired trials.
 *
 * This is `gn_rollout_difference` widened from two variants to `count`. It is
 * what lets one arbitration price EVERY plausible play of a decision rather
 * than the two that happened to be compared: a later candidate engine that
 * picks a different move is then scored from the same frozen ledger, at no
 * further cost. Rolling k candidates against a pivot pairwise would play
 * 2(k-1) trajectories; this plays k.
 *
 * A trial the engine declines to play for one candidate is dropped for all of
 * them -- an unpaired trial would silently destroy the very correlation that
 * makes the difference cheap to determine.
 *
 * `target_se` stops the rollout when EVERY non-pivot difference is inside it,
 * never on the pivot's own (identically zero). `equities` and `differences` are
 * required; `difference_errors` and `trials_done` may be NULL.
 *
 * Returns 0 on success, -1 on refusal -- including `count` above
 * GN_ROLLOUT_MAX_CANDIDATES.
 */
int gn_rollout_candidates_paired(const GnNetwork *net, const GnPosition *results,
                                 int count, const GnRolloutConfig *config,
                                 int pivot, double *equities,
                                 double *differences, double *difference_errors,
                                 unsigned long *trials_done);

int gn_rollout_difference(const GnNetwork *net,
                          const GnPosition *a, const GnPosition *b,
                          const GnRolloutConfig *config,
                          double *difference, double *standard_error);

/*
 * The dice, exposed. Not a convenience: the common-random-numbers mechanism is
 * the whole point of this module, and a test that cannot see the dice can only
 * observe that two rollouts agree -- which they also do when the dice are
 * broken and constant. That is exactly how the first version got through.
 */
void gn_rollout_roll(unsigned long seed, unsigned long trial, unsigned int ply,
                     int *d1, int *d2);

#ifdef __cplusplus
}
#endif

#endif /* GN_ROLLOUT_H */

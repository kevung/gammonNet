/*
 * gn_cube.h -- doubling: the cube model (T34).
 *
 * THE ARCHITECTURE, WHICH IS NOT NEGOTIABLE HERE
 *
 * The network is cubeless and blind to the score. It emits five probabilities;
 * the cube and the score never enter it. Everything below happens AFTERWARDS,
 * from that distribution -- which is why `gn_infer.h` insists the distribution
 * is the output and money equity a mere projection. A scalar equity has already
 * thrown away what a cube decision needs.
 *
 * That is GNU Backgammon's architecture, and `BRIEF.md` §6 explains why it is
 * the only one that scales: a score-aware network would have to learn a
 * different function for every score and every cube level.
 *
 * ── WHERE THE MODEL COMES FROM ──────────────────────────────────────
 *
 * Rick Janowski, *Take-Points in Money Games* (1993). The idea is one sentence:
 * a real cube is worth something between a DEAD cube -- one that will never be
 * turned again, so equity is just the cubeless equity times the stake -- and a
 * LIVE cube, one that can always be redoubled at the perfect moment. Real play
 * sits between the two, and a single **cube efficiency** parameter says where.
 *
 * This is published literature, not gnubg's code, and that is deliberate.
 * `docs/etudes/` recommends not reading GNU Backgammon's source for this fiche
 * at all: the model and the derivation of match take points from an equity table
 * are both public, they suffice, and keeping the most delicate component of the
 * project traceable to public literature is a free advantage.
 *
 * ── THE ONE CONSTANT WE REFUSE TO BORROW ────────────────────────────
 *
 * The cube efficiency is the model's only free parameter, and every engine
 * carries its own tuned value. Copying one would be copying someone's tuning
 * work, which `docs/etudes/` names explicitly as the thing not to take. Ours is
 * MEASURED, against the exact reference below, and the measurement is reported.
 *
 * ── HOW THIS GETS VERIFIED, AND WHY THAT IS UNUSUAL ─────────────────
 *
 * A cube model is normally checked by agreement with another engine, which
 * proves only resemblance. Here there is something better: the two-sided bearoff
 * database carries **exact cubeful equities** for three cube states -- owned,
 * centred, opponent-owns. In that domain the right answer is known, with no
 * rollout and no arbiter.
 *
 * So the model is fitted and checked where truth is available, and only then
 * carried into contact positions where it is not. The same discipline that made
 * T38 and T39 trustworthy.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_CUBE_H
#define GN_CUBE_H

#include "gn_infer.h"
#include "gn_met.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Who may turn the cube.
 *
 * Named rather than encoded as an owner id, because the three cases are not
 * symmetric and the asymmetry is the whole subject: a centred cube is an option
 * for both players, an owned cube is an option for exactly one.
 */
typedef enum {
    GN_CUBE_CENTRED = 0,   /* neither side owns it; either may double */
    GN_CUBE_OWNED = 1,     /* the player on roll owns it */
    GN_CUBE_OPPONENT = 2   /* the opponent owns it; the player on roll cannot double */
} GnCubeOwner;

/*
 * What a win and a loss are worth on average, in points, given the position.
 *
 * These are the two numbers Janowski's model needs beyond the winning chance,
 * and they are exactly what a scalar equity destroys. Derived from the five
 * nested probabilities via `gn_probs_exclusive` -- called, never reimplemented:
 * T10 found that denesting them naively yields a NEGATIVE probability on real
 * positions, and a cube decision is precisely the consumer that would carry it
 * into a doubling error.
 */
typedef struct {
    double win;              /* P(win), any margin */
    double win_points;       /* E[points | win]  -- at least 1 */
    double lose_points;      /* E[points | lose] -- at least 1 */
} GnCubeInputs;

/* Fill `out` from a distribution. Returns 0, or -1 if the distribution is not
 * usable (a win probability of exactly 0 or 1 leaves the conditional
 * expectations undefined, and they are then set to 1 rather than to NaN). */
int gn_cube_inputs(const float probs[GN_NUM_OUTPUTS], GnCubeInputs *out);

/*
 * The take point: the winning chance below which a double should be passed.
 *
 * `efficiency` in [0, 1] interpolates between a dead cube (0) and a fully live
 * one (1). Returns -1 for an unusable input rather than clamping, because a
 * clamped take point is a wrong number that looks right.
 */
double gn_cube_take_point(const GnCubeInputs *inputs, GnCubeOwner owner,
                          double efficiency);

/*
 * Cubeful money equity, in points, from the point of view of the player on
 * roll, for a cube currently at `cube` under `owner`.
 */
double gn_cube_equity(const GnCubeInputs *inputs, GnCubeOwner owner,
                      int cube, double efficiency);

/*
 * The cubeful value of one DISTRIBUTION, on the search's negating scale --
 * the leaf valuation of t34-videau-spec §8, step 2.
 *
 * `state == NULL` values in money points per unit of cube (Janowski §3);
 * otherwise in match equity `2 * MWC - 1` through the §9 recursion, at
 * `state`'s own cube value. Both scales NEGATE between sides provided the
 * caller mirrors `owner` (OWNED <-> OPPONENT) and swaps `state` along with
 * the perspective -- exactly what `gn_search`'s recursion does at each ply.
 * That antisymmetry is what lets an expectiminimax carry cubeful values with
 * the same negations it uses for cubeless ones, and a test holds it.
 *
 * In the Crawford game (`state->crawford`) there is no cube in play, and the
 * value is the DEAD one at the current stake -- the cubeless match equity --
 * whatever `owner` and `efficiency` say. Post-Crawford gets no special case:
 * the table already carries it.
 *
 * Returns the value, or sets `*failed` (when non-NULL) and returns 0.0 for a
 * distribution or state that cannot be valued -- refused, never approximated.
 */
double gn_cube_value(const float probs[GN_NUM_OUTPUTS], GnCubeOwner owner,
                     const GnMatchState *state, double efficiency, int *failed);

/*
 * The same valuation, for `n` distributions that share one cube state -- the
 * batched form of T85, and the reason it exists is not tidiness.
 *
 * WHAT IS SLOW, AND WHY A BATCH FIXES IT
 *
 * At a score the value of one node is the §9 recursion, and the recursion
 * spends nearly all of itself in `level_solve`: sixty bisection steps per
 * breakpoint, two breakpoints per level, three levels on a typical chain --
 * about 360 steps. Each step is a division whose result decides the next
 * step's input, so the whole thing is ONE serial dependency chain of
 * divisions. Measured: 2 711 ns per valuation inside the search
 * (docs/mesures/2026-09-02-T85-videau-par-lot.md §1), which is latency, not
 * work -- the arithmetic itself would fit in a fraction of that.
 *
 * The bisections of two different candidates are INDEPENDENT. Run `n` of them
 * in lockstep and the divisions of one lane fill the latency of another's:
 * same figure as `gn_evaluate_batch` on the network, same two devices of
 * exactness -- a FIXED lane width and a FIXED iteration count, so a lane's
 * sequence never depends on how many neighbours it travelled with.
 *
 * BIT FOR BIT, PER CANDIDATE. `out[j]` is exactly what `gn_cube_value` would
 * have returned for `probs[j]` alone: the arithmetic is not rearranged, only
 * its order of execution is. `tests/test_cube_batch.py` holds that equality
 * the way `tests/test_batch.py` holds the network's.
 *
 * `probs` is an array of `n` pointers to distributions -- the search's
 * candidates are not contiguous, and copying them to make them so would cost
 * more than the gather it saves. `state == NULL` (money) is valued by calling
 * the scalar path per item: the same measurement says the cube costs nothing
 * in money, and a gather for zero would be a cost with no other side.
 *
 * Returns 0 with `out[0..n)` written, or -1 if ANY candidate is unevaluable --
 * the same refusal the scalar makes, applied to the whole batch, which is
 * what its only caller (`value_sweep`) does with a single failure anyway.
 */
int gn_cube_value_batch(const float *const *probs, int n, GnCubeOwner owner,
                        const GnMatchState *state, double efficiency,
                        double *out);

/* The lane width. Public so a caller can size its gather with the same
 * number the kernel chunks by, exactly as `GN_EVAL_BATCH` is public for the
 * network's. It is a cost, never a result: `gn_cube_value_batch` accepts any
 * `n` and a lane's answer does not depend on how many lanes ran beside it. */
#define GN_CUBE_BATCH 32

/* What the on-roll player should do, and what the opponent should answer. */
typedef enum {
    GN_NO_DOUBLE = 0,
    GN_DOUBLE_TAKE = 1,
    GN_DOUBLE_PASS = 2,     /* doubling wins outright: the opponent must pass */
    GN_TOO_GOOD = 3         /* playing on is worth more than cashing */
} GnCubeAction;

/*
 * Spec §4's verdict table, exported raw: hand it the three branch values --
 * "don't double", "double, taken", "double, passed" -- on ANY common scale
 * (money points, MWC, exact table equities) and it answers. Exported because
 * the cubeful rollout (gn_rollout) and the exact-reference benches need the
 * SAME four comparisons as `gn_cube_decide`, and a second copy of a verdict
 * table is how two readings of one rule end up in one repository.
 */
GnCubeAction gn_cube_verdict(double e_nd, double e_dt, double e_dp);

/* The same cube, seen from the other side of the table: mine becomes theirs,
 * centred stays centred. The search and the rollout both mirror ownership at
 * every turn swap, for the same reason they swap the match state -- forgetting
 * it values every other ply with the wrong player holding the cube. */
GnCubeOwner gn_cube_mirror(GnCubeOwner owner);


typedef struct {
    GnCubeAction action;
    /* Equity of doubling and of not doubling, on the same scale, so the caller
     * can see the margin rather than only the verdict. A decision that is right
     * by 0.001 and one that is right by 0.5 are not the same decision. */
    double equity_no_double;
    double equity_double;
    /* The opponent's take point at this state, for reporting. */
    double take_point;
} GnCubeDecision;

/*
 * The money-game decision.
 *
 * `state` may be NULL for a pure money game. When it is not, the decision is
 * taken in MATCH WINNING CHANCE through the equity table, which is a different
 * question with a different answer -- at 2-away/2-away a gammon wins the match
 * and the whole doubling window moves. The score is NOT a correction applied to
 * a money verdict; it replaces it.
 *
 * `jacoby`: non-zero to apply the Jacoby rule -- gammons and backgammons do not
 * count before the cube has been turned. It affects only the "don't double"
 * branch (`docs/specs/t34-videau-spec.md` §4: `W` and `L` are both reset to 1
 * there, nowhere else), and only when it can actually matter: a centred cube in
 * a money game (`state == NULL`). Once the cube has been turned (`owner !=
 * GN_CUBE_CENTRED`) the flag is silently without effect, because Jacoby governs
 * the game *before* the first double, not after it -- and in a match the
 * question does not arise at all: the equity table already prices gammons at
 * the score, which is what Jacoby exists to approximate in money play.
 *
 * Returns 0, or -1 if the state is not evaluable (`gn_met.h` refuses rather
 * than extrapolating, and so does this).
 */
int gn_cube_decide(const float probs[GN_NUM_OUTPUTS], GnCubeOwner owner,
                   const GnMatchState *state, double efficiency, int jacoby,
                   GnCubeDecision *out);

#ifdef __cplusplus
}
#endif

#endif /* GN_CUBE_H */

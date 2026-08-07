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

/* What the on-roll player should do, and what the opponent should answer. */
typedef enum {
    GN_NO_DOUBLE = 0,
    GN_DOUBLE_TAKE = 1,
    GN_DOUBLE_PASS = 2,     /* doubling wins outright: the opponent must pass */
    GN_TOO_GOOD = 3         /* playing on is worth more than cashing */
} GnCubeAction;

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
 * Returns 0, or -1 if the state is not evaluable (`gn_met.h` refuses rather
 * than extrapolating, and so does this).
 */
int gn_cube_decide(const float probs[GN_NUM_OUTPUTS], GnCubeOwner owner,
                   const GnMatchState *state, double efficiency,
                   GnCubeDecision *out);

#ifdef __cplusplus
}
#endif

#endif /* GN_CUBE_H */

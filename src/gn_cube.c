/*
 * gn_cube.c -- the cube model. See gn_cube.h before editing, and
 * docs/specs/t34-videau-spec.md for the derivation this file follows to the
 * letter: every formula below has a paragraph number in that document, and a
 * discrepancy from it is a bug, never an improvisation.
 *
 * ONE SEPARATION THAT MATTERS THROUGHOUT THIS FILE. `docs/specs/` §2-3 defines
 * two DIFFERENT quantities that both depend on cube efficiency and both get
 * called "the take point" in conversation, and confusing them is the easiest
 * way to get this file wrong:
 *
 *   - `TP_live`, `CP_live` -- the FIXED breakpoints of the fully-live (x = 1)
 *     equity curve. They never move with `efficiency`; they are where the
 *     piecewise shape of `E_live` bends. Computed by `live_points()`.
 *   - `TP(x)`, `CP(x)` -- the ACTUAL take/cash points at the chosen
 *     efficiency, a separate closed form (§3). These are what a caller wants
 *     to know ("should I take"), not where a curve bends.
 *
 * `gn_cube_equity` blends the FIXED dead and live curves by `x` (§3's
 * `E(x) = (1-x)E_dead + x E_live`); it never touches `TP(x)`/`CP(x)`.
 * `gn_cube_take_point` computes only `TP(x)`/`CP(x)`; it never touches the
 * live curve's breakpoints. The two are algebraically related -- both trace
 * back to the same recursion -- but this file computes them independently,
 * exactly as the spec presents them, rather than deriving one from the other.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_cube.h"

#include <stddef.h>

/* ── Money: the Janowski model, per unit of cube ─────────────────────── */

/* Cubeless equity per unit of cube: `pW - (1-p)L`. Linear in `p` by
 * construction -- it is also `E_dead`, verbatim (spec §2: a dead cube is
 * never turned again, so cubeful and cubeless equity coincide). */
static double janowski_e(double p, double W, double L)
{
    return p * W - (1.0 - p) * L;
}

/* The fixed breakpoints of the x = 1 (fully live) equity curve. Closed form,
 * spec §2 -- verified there against the redouble recursion to 1e-12, and
 * against blunderDB's numbers are not consulted here (nothing here reads
 * another engine's constants; W and L come from THIS position only). */
static void live_points(double W, double L, double *tp_live, double *cp_live)
{
    const double denom = W + L + 0.5;

    *tp_live = (L - 0.5) / denom;
    *cp_live = (L + 1.0) / denom;
}

/*
 * The Janowski equity of ONE cube state, per unit of cube, at efficiency `x`.
 *
 * `dead` is `e(p)`, used unclamped for the dead branch and as the "too good"
 * continuation for the live one -- spec §2's own words, "trop bon traité par
 * la continuation morte": beyond the point where a live cube's value saturates
 * at the cash equivalent, playing on is scored by the plain cubeless equity,
 * because that IS what happens once nobody has anything left to gain by
 * turning the cube.
 */
static double janowski_equity(double p, double W, double L, GnCubeOwner owner,
                              double efficiency)
{
    double tp_live, cp_live, dead, live;

    live_points(W, L, &tp_live, &cp_live);
    dead = janowski_e(p, W, L);

    switch (owner) {
    case GN_CUBE_OWNED:
        /* (0, -L) to (CP_live, +1); beyond, max(1, e(p)). */
        if (p <= cp_live) {
            live = -L + (1.0 + L) * (p / cp_live);
        } else {
            live = (dead > 1.0) ? dead : 1.0;
        }
        break;

    case GN_CUBE_OPPONENT:
        /* Below TP_live, min(-1, e(p)); above, (TP_live, -1) to (1, W). */
        if (p <= tp_live) {
            live = (dead < -1.0) ? dead : -1.0;
        } else {
            live = -1.0 + (W + 1.0) * ((p - tp_live) / (1.0 - tp_live));
        }
        break;

    case GN_CUBE_CENTRED:
    default:
        /* min(-1, e(p)) below TP_live; (TP_live,-1) to (CP_live,1); above,
         * max(1, e(p)). The centred curve is the other two glued together. */
        if (p <= tp_live) {
            live = (dead < -1.0) ? dead : -1.0;
        } else if (p <= cp_live) {
            live = -1.0 + 2.0 * ((p - tp_live) / (cp_live - tp_live));
        } else {
            live = (dead > 1.0) ? dead : 1.0;
        }
        break;
    }

    return (1.0 - efficiency) * dead + efficiency * live;
}

/* ── Public: distribution -> (p, W, L) ───────────────────────────────── */

int gn_cube_inputs(const float probs[GN_NUM_OUTPUTS], GnCubeInputs *out)
{
    double outcomes[GN_NUM_EXCLUSIVE];
    double win, lose;

    if (!probs || !out)
        return -1;

    /* Called, not reimplemented -- see gn_infer.h for the negative-probability
     * trap this sidesteps. */
    gn_probs_exclusive(probs, outcomes);

    win = outcomes[GN_E_WIN_SINGLE] + outcomes[GN_E_WIN_G] + outcomes[GN_E_WIN_BG];
    lose = outcomes[GN_E_LOSE_SINGLE] + outcomes[GN_E_LOSE_G] + outcomes[GN_E_LOSE_BG];

    out->win = win;

    /* p = 0 or p = 1 leaves one of the two conditional expectations averaged
     * over zero mass. The header is explicit: set it to 1 (a plain single
     * game), not NaN -- a degenerate distribution should not poison every
     * caller that multiplies by it downstream. */
    out->win_points = (win > 0.0)
        ? (1.0 * outcomes[GN_E_WIN_SINGLE] + 2.0 * outcomes[GN_E_WIN_G] +
           3.0 * outcomes[GN_E_WIN_BG]) / win
        : 1.0;
    out->lose_points = (lose > 0.0)
        ? (1.0 * outcomes[GN_E_LOSE_SINGLE] + 2.0 * outcomes[GN_E_LOSE_G] +
           3.0 * outcomes[GN_E_LOSE_BG]) / lose
        : 1.0;

    return 0;
}

/*
 * The take point, `TP(x)` or `CP(x)` of spec §3 -- picked by `owner`.
 *
 * `owner == GN_CUBE_OWNED` means *I* hold the cube and am weighing whether to
 * turn it: the number that matters then is not my own take point (nobody can
 * double me) but the boundary, on MY winning chance, past which MY opponent
 * would no longer take -- `CP(x)`. `GnCubeDecision.take_point` documents this
 * exact use: "the opponent's take point, for reporting" when I am the one
 * about to double.
 *
 * `owner == GN_CUBE_CENTRED` or `GN_CUBE_OPPONENT` means the cube could still
 * land on ME: the number that matters is MY OWN take point, `TP(x)`.
 *
 * Both formulas are functions of my own (W, L) only -- the opponent's side
 * never needs its own inputs, because the recursion in spec §2 already
 * folds it in by symmetry (their win points are my lose points, and vice
 * versa). That symmetry is exactly what makes `TP_live`'s closed form not
 * need a second set of probabilities.
 */
double gn_cube_take_point(const GnCubeInputs *inputs, GnCubeOwner owner,
                          double efficiency)
{
    double W, L, denom;

    if (!inputs)
        return -1.0;

    W = inputs->win_points;
    L = inputs->lose_points;
    denom = W + L + efficiency / 2.0;
    if (denom <= 0.0)
        return -1.0;

    if (owner == GN_CUBE_OWNED)
        return (L + 0.5 + efficiency / 2.0) / denom;   /* CP(x) */
    return (L - 0.5) / denom;                          /* TP(x) */
}

double gn_cube_equity(const GnCubeInputs *inputs, GnCubeOwner owner,
                      int cube, double efficiency)
{
    if (!inputs)
        return 0.0;
    return (double) cube *
           janowski_equity(inputs->win, inputs->win_points, inputs->lose_points,
                           owner, efficiency);
}

/* ── Match: the same mechanism, transposed to MWC ────────────────────── */

/*
 * `docs/specs/` §5's "v1 simplification": the money model's redouble
 * recursion is not re-solved on the MWC scale (that is a genuinely different,
 * harder problem, and the spec defers it). Instead, this reuses the money
 * model's (TP_live, CP_live) -- the SHAPE of the correction, in winning-chance
 * space -- and re-expresses only the four values the shape interpolates
 * between, this time as match winning chances read from `gn_met_after`
 * instead of as points. Four anchors replace money's four constants:
 *
 *   money -L (dead, p=0)  <->  `lose0`  MWC of the lose branch's own gammon mix
 *   money +W (dead, p=1)  <->  `win1`   MWC of the win branch's own gammon mix
 *   money -1 (cash a pass) <-> `pass`   MWC of passing this stake outright
 *   money +1 (cash a take) <-> `cash`   MWC of the opponent passing outright
 *
 * `e(p) = pW - (1-p)L` STAYS a function of `p`, evaluated fresh at whatever
 * `p` a caller asks about -- money's `janowski_e()` does exactly that. The
 * match analogue, `(1-p)*lose0 + p*win1`, must do the same: `lose0`/`win1`
 * are the p-INDEPENDENT structural anchors (like `L`/`W`), and the MWC-dead
 * curve is built from them at the QUERIED `p` inside `match_equity`, never
 * cached at the position's own actual `p`. An earlier version of this file
 * cached `gn_match_winning_chance(state, probs)` once per anchor set and
 * reused it regardless of the `p` being evaluated -- correct only at the
 * one `p` it was computed for, and silently wrong at every other `p` the
 * take-point bisection below needs to probe. Caught by that bisection
 * itself returning a "take point" that moved with the position's `p`, which
 * a take point -- a property of the STATE, not of any one position -- must
 * never do.
 */
typedef struct {
    double lose0;  /* MWC of the lose branch's gammon mix, weight fixed at p=0 */
    double win1;   /* MWC of the win branch's gammon mix, weight fixed at p=1 */
    double pass;   /* MWC of passing an offer worth this stake outright */
    double cash;   /* MWC of the opponent passing my double at this stake */
} GnMatchAnchors;

/* The weighted MWC average of one branch (win, or lose) at `stake`, folding in
 * the position's own single/gammon/backgammon mix within that branch. Falls
 * back to a plain single game when the branch carries no mass -- the least
 * committal answer, and one that is never actually weighted into anything by
 * a zero (1-p) or p anyway (see `match_equity` below). */
static double branch_mwc(const GnMatchState *state, const double outcomes[GN_NUM_EXCLUSIVE],
                         int stake, int on_roll_wins, int *ok)
{
    double single, gammon, bg, mass, m1, m2, m3;

    if (on_roll_wins) {
        single = outcomes[GN_E_WIN_SINGLE];
        gammon = outcomes[GN_E_WIN_G];
        bg = outcomes[GN_E_WIN_BG];
    } else {
        single = outcomes[GN_E_LOSE_SINGLE];
        gammon = outcomes[GN_E_LOSE_G];
        bg = outcomes[GN_E_LOSE_BG];
    }
    mass = single + gammon + bg;

    m1 = gn_met_after(state, 1 * stake, on_roll_wins);
    m2 = gn_met_after(state, 2 * stake, on_roll_wins);
    m3 = gn_met_after(state, 3 * stake, on_roll_wins);
    if (m1 < 0.0 || m2 < 0.0 || m3 < 0.0) {
        *ok = 0;
        return 0.0;
    }
    if (mass <= 0.0)
        return m1;

    return (single / mass) * m1 + (gammon / mass) * m2 + (bg / mass) * m3;
}

static int match_anchors(const GnMatchState *state, const double outcomes[GN_NUM_EXCLUSIVE],
                         int stake, GnMatchAnchors *out)
{
    int ok = 1;

    out->lose0 = branch_mwc(state, outcomes, stake, 0, &ok);
    out->win1 = branch_mwc(state, outcomes, stake, 1, &ok);
    out->pass = gn_met_after(state, stake, 0);
    out->cash = gn_met_after(state, stake, 1);
    if (out->pass < 0.0 || out->cash < 0.0)
        ok = 0;

    return ok;
}

/* Same piecewise shape as `janowski_equity`, anchors substituted -- see the
 * table at the top of this section for the correspondence. `tp_live`/
 * `cp_live` are the MONEY breakpoints (spec §5: "l'interpolation en x
 * identique"), computed once from (W, L) and passed in rather than
 * recomputed per anchor set, since they do not depend on the stake.
 *
 * `dead` is recomputed HERE, at the `p` this particular call is asked about
 * -- never cached in `GnMatchAnchors`. See the comment on that struct for
 * why: this function is the bisection target of `match_take_point` below,
 * called at many `p` that are not the position's actual one. */
static double match_equity(const GnMatchAnchors *a, double p, double tp_live,
                           double cp_live, GnCubeOwner owner, double efficiency)
{
    const double dead = (1.0 - p) * a->lose0 + p * a->win1;
    double live;

    switch (owner) {
    case GN_CUBE_OWNED:
        if (p <= cp_live) {
            live = a->lose0 + (a->cash - a->lose0) * (p / cp_live);
        } else {
            live = (a->cash > dead) ? a->cash : dead;
        }
        break;

    case GN_CUBE_OPPONENT:
        if (p <= tp_live) {
            live = (a->pass < dead) ? a->pass : dead;
        } else {
            live = a->pass + (a->win1 - a->pass) * ((p - tp_live) / (1.0 - tp_live));
        }
        break;

    case GN_CUBE_CENTRED:
    default:
        if (p <= tp_live) {
            live = (a->pass < dead) ? a->pass : dead;
        } else if (p <= cp_live) {
            live = a->pass + (a->cash - a->pass) * ((p - tp_live) / (cp_live - tp_live));
        } else {
            live = (a->cash > dead) ? a->cash : dead;
        }
        break;
    }

    return (1.0 - efficiency) * dead + efficiency * live;
}

/*
 * The opponent's take point, on the match scale, at a specific state.
 *
 * Unlike money's `CP(x)` -- a closed form -- there is no closed form here:
 * `match_equity` is an affine blend of `gn_met_after` lookups, not a rational
 * function of `p`. So this bisects, exactly as `tests/test_met.py` already
 * does to recover a take point that has no closed form of its own. Relies on
 * equities being monotone increasing in `p` (spec §6.1's own property test
 * covers exactly this, for both money and match).
 *
 * This is what makes `GnCubeDecision.take_point` state-dependent in match play
 * -- reusing money's constant `CP(x)` here would silently report the same
 * number at every score, and the doubling window's monotony across scores
 * (spec §6.4) would have nothing real to test.
 */
static double match_take_point(const GnMatchAnchors *anchors, double tp_live,
                               double cp_live, double efficiency, double target)
{
    double low = 0.0, high = 1.0;
    int i;

    for (i = 0; i < 60; i++) {
        const double mid = 0.5 * (low + high);
        const double value = match_equity(anchors, mid, tp_live, cp_live,
                                          GN_CUBE_OPPONENT, efficiency);
        if (value < target) {
            low = mid;
        } else {
            high = mid;
        }
    }
    return 0.5 * (low + high);
}

/* ── The decision, money and match sharing one verdict table ─────────── */

/*
 * Spec §4's table, applied to whatever (e_nd, e_dt, e_dp, e_double) the caller
 * hands in -- money points or match MWC, the comparisons read the same way in
 * either scale. Kept as one function so the two branches of `gn_cube_decide`
 * cannot silently diverge on the verdict logic itself.
 */
static GnCubeAction verdict(double e_nd, double e_dt, double e_dp, double e_double)
{
    if (e_nd > e_dp && e_nd >= e_double)
        return GN_TOO_GOOD;
    if (e_dt >= e_dp)
        return GN_DOUBLE_PASS;
    if (e_double > e_nd)
        return GN_DOUBLE_TAKE;
    return GN_NO_DOUBLE;
}

int gn_cube_decide(const float probs[GN_NUM_OUTPUTS], GnCubeOwner owner,
                   const GnMatchState *state, double efficiency, int jacoby,
                   GnCubeDecision *out)
{
    GnCubeInputs inputs;

    if (!probs || !out)
        return -1;
    if (gn_cube_inputs(probs, &inputs) != 0)
        return -1;

    if (state == NULL) {
        /* Money. Jacoby (spec §4): only the "don't double" branch is affected,
         * and only before the cube has ever been turned -- see gn_cube.h for
         * why `owner != GN_CUBE_CENTRED` silently disables the flag. Passing
         * W = L = 1 into `janowski_equity` re-derives that call's OWN
         * TP_live/CP_live as the gammonless (0.20, 0.80) pair too, which is
         * exactly "play as if gammons did not exist," not a partial patch. */
        double w_nd = inputs.win_points;
        double l_nd = inputs.lose_points;
        double e_nd, e_dt, e_dp, e_double;

        if (jacoby && owner == GN_CUBE_CENTRED) {
            w_nd = 1.0;
            l_nd = 1.0;
        }

        e_nd = janowski_equity(inputs.win, w_nd, l_nd, owner, efficiency);
        e_dt = 2.0 * janowski_equity(inputs.win, inputs.win_points, inputs.lose_points,
                                     GN_CUBE_OPPONENT, efficiency);
        e_dp = 1.0;
        e_double = (e_dt < e_dp) ? e_dt : e_dp;

        out->equity_no_double = e_nd;
        out->equity_double = e_double;
        out->take_point = gn_cube_take_point(&inputs, GN_CUBE_OWNED, efficiency);

        /* A cube the opponent owns cannot be turned by the player on roll --
         * gn_cube.h's GN_CUBE_OPPONENT. The verdict table presupposes doubling
         * is an option (spec §4: "le joueur au trait PEUT doubler si..."), so
         * outside that precondition there is nothing to weigh. */
        out->action = (owner == GN_CUBE_OPPONENT)
            ? GN_NO_DOUBLE
            : verdict(e_nd, e_dt, e_dp, e_double);
        return 0;
    }

    /* Match. */
    if (!gn_match_state_is_valid(state))
        return -1;

    {
        double outcomes[GN_NUM_EXCLUSIVE];
        double tp_live, cp_live;
        GnMatchAnchors anchors_c0, anchors_2c0;
        double e_nd, e_dt, e_dp, e_double;

        gn_probs_exclusive(probs, outcomes);
        live_points(inputs.win_points, inputs.lose_points, &tp_live, &cp_live);

        if (!match_anchors(state, outcomes, state->cube, &anchors_c0))
            return -1;
        if (!match_anchors(state, outcomes, 2 * state->cube, &anchors_2c0))
            return -1;

        e_nd = match_equity(&anchors_c0, inputs.win, tp_live, cp_live, owner, efficiency);
        e_dt = match_equity(&anchors_2c0, inputs.win, tp_live, cp_live, GN_CUBE_OPPONENT,
                            efficiency);
        e_dp = anchors_c0.cash;
        e_double = (e_dt < e_dp) ? e_dt : e_dp;

        out->equity_no_double = e_nd;
        out->equity_double = e_double;
        out->take_point = match_take_point(&anchors_2c0, tp_live, cp_live, efficiency, e_dp);

        /*
         * Two forced branches, and only one of them is a rule.
         *
         * `state->crawford`: the Crawford game has no cube in play at all --
         * spec §5 states this as flat fact, not something to derive.
         *
         * Post-Crawford, by contrast, gets NO special case: the trailer's
         * mandatory double and the leader's free drop are supposed to fall
         * out of `verdict()` on their own, because `gn_met_after` already
         * encodes the post-Crawford table (gn_met.c). If they didn't emerge,
         * the fix would belong in the MWC anchors above, never in a branch
         * added here to force the "right" answer.
         */
        out->action = state->crawford ? GN_NO_DOUBLE
            : (owner == GN_CUBE_OPPONENT) ? GN_NO_DOUBLE
            : verdict(e_nd, e_dt, e_dp, e_double);
        return 0;
    }
}

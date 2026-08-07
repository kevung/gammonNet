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

/* ── Match: the redouble recursion at the score (spec §9, v2) ────────── */

/*
 * The money model's live curve exists in closed form because money is
 * scale-invariant: doubling the stake doubles every equity, so one recursion
 * step looks like every other. A match score breaks that symmetry -- §6.3
 * measured exactly where: at 2-away/4-away the leader's cube dies at 2 while
 * the trailer's redouble to 4 is free, and the v1 transposition (money's
 * breakpoints carried onto the MWC scale) cannot see that asymmetry.
 *
 * So the live curves are rebuilt HERE, per stake level `k`, by the §9
 * recursion. The chain terminates on its own: once `k` covers both away
 * scores, no further cube turn can change anything -- the cube is dead and
 * `M(p; k) = M_dead(p; k)` exactly. Level `k`'s breakpoints are then resolved
 * by bisection against the level-`2k` curves coming out of the recursion:
 *
 *   TP(k) solves  M_own(p; 2k)  = pass(k)   -- I take a double and own at 2k
 *   CP(k) solves  M_opp(p; 2k)  = cash(k)   -- the opponent takes mine at 2k
 *
 * Two invariants carried over from v1, both learned the hard way there:
 *
 *   - The dead curve is recomputed at whatever `p` a call asks about, never
 *     cached at the position's own `p` -- the bisections below probe many `p`
 *     that are not the position's, and a cached MWC is silently wrong at
 *     every one of them.
 *   - A pass concedes `k` DRY points (§9: "jamais pondérés gammon") -- the
 *     gammon mix belongs to games that are played out, not conceded.
 *
 * Gammon fractions are held constant along the recursion, the same named
 * simplification as everywhere else in this file. Efficiency enters ONCE, at
 * the top: the recursion builds the fully-live curves, and the caller blends
 * `(1-x)*dead + x*live` exactly as money's §3 does -- levels inside the
 * recursion are live, because the live limit is what the recursion defines.
 */
typedef struct {
    int dead;         /* base case: `stake` covers both away scores */
    double lose_avg;  /* MWClose_avg(k): losing, at this position's gammon mix */
    double win_avg;   /* MWCwin_avg(k): winning, same mix */
    double pass;      /* MWC after conceding `k` dry points */
    double cash;      /* MWC after collecting `k` dry points */
    double tp;        /* my take point, resolved against level 2k */
    double cp;        /* the opponent's take point, resolved against level 2k */
} GnMatchLevel;

/* The chain from the current cube up to the first dead level. Away scores are
 * at most GN_MET_MAX_AWAY = 25, so a chain from cube 1 is 1,2,4,8,16,32 --
 * six levels; ⌈log₂ 25⌉ = 5 doublings, the bound §9 states. Eight leaves
 * room to always materialise the 2c level even when c is already dead. */
#define GN_CUBE_MAX_LEVELS 8

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

/* `M_dead(p; k)`: linear in `p` between the two gammon-mix anchors, evaluated
 * at the QUERIED `p` -- see the section comment for why it is never cached. */
static double level_dead(const GnMatchLevel *lv, double p)
{
    return (1.0 - p) * lv->lose_avg + p * lv->win_avg;
}

/*
 * The fully-live curve of one stake level -- `janowski_equity`'s piecewise
 * shape with this LEVEL's anchors and breakpoints. On a dead level the shape
 * collapses to the dead line for every cube state: §9's base case, "mort
 * partout", is a return statement, not a special caller.
 *
 * Monotone non-decreasing in `p` for each state (each branch rises, and the
 * min/max clamps splice non-decreasing pieces) -- the property every
 * bisection below stands on.
 */
static double level_live(const GnMatchLevel *lv, double p, GnCubeOwner owner)
{
    const double dead = level_dead(lv, p);

    if (lv->dead)
        return dead;

    switch (owner) {
    case GN_CUBE_OWNED:
        if (p <= lv->cp)
            return lv->lose_avg + (lv->cash - lv->lose_avg) * (p / lv->cp);
        return (dead > lv->cash) ? dead : lv->cash;

    case GN_CUBE_OPPONENT:
        if (p <= lv->tp)
            return (dead < lv->pass) ? dead : lv->pass;
        return lv->pass + (lv->win_avg - lv->pass) * ((p - lv->tp) / (1.0 - lv->tp));

    case GN_CUBE_CENTRED:
    default:
        if (p <= lv->tp)
            return (dead < lv->pass) ? dead : lv->pass;
        if (p <= lv->cp)
            return lv->pass + (lv->cash - lv->pass) * ((p - lv->tp) / (lv->cp - lv->tp));
        return (dead > lv->cash) ? dead : lv->cash;
    }
}

/* `M(x) = (1-x)*M_dead + x*M_live` -- §9's interpolation, money's §3 verbatim. */
static double level_blend(const GnMatchLevel *lv, double p, GnCubeOwner owner,
                          double efficiency)
{
    return (1.0 - efficiency) * level_dead(lv, p) +
           efficiency * level_live(lv, p, owner);
}

/* The `p` where a monotone level curve crosses `target` -- the §9 bisection
 * ("les fonctions sont piecewise-linéaires monotones"). `blend < 0` bisects
 * the fully-live curve (breakpoint resolution inside the recursion);
 * otherwise the curve blended at that efficiency (the reported take point). */
static double level_solve(const GnMatchLevel *lv, GnCubeOwner owner,
                          double blend, double target)
{
    double low = 0.0, high = 1.0;
    int i;

    for (i = 0; i < 60; i++) {
        const double mid = 0.5 * (low + high);
        const double value = (blend < 0.0)
            ? level_live(lv, mid, owner)
            : level_blend(lv, mid, owner, blend);
        if (value < target) {
            low = mid;
        } else {
            high = mid;
        }
    }
    return 0.5 * (low + high);
}

/*
 * Build the §9 chain: `levels[0]` at the current cube, each next level at
 * double the stake, ending on the first dead level -- and never before
 * `levels[1]`, because the caller always needs the 2c level for the
 * double/take branch, even when the current cube is already dead.
 *
 * Returns the number of levels, or 0 to REFUSE (an unevaluable state, or a
 * chain that failed to die within the array -- unreachable while the table
 * caps away scores at 25, and refused rather than approximated if that cap
 * ever moves).
 *
 * Breakpoints are then resolved backwards, deepest first, so each level's
 * bisection targets a fully-built `2k` level. This iterative form IS §9's
 * memoised recursion: each (state, k) is computed once, from the base case
 * down.
 */
static int build_levels(const GnMatchState *state,
                        const double outcomes[GN_NUM_EXCLUSIVE],
                        GnMatchLevel levels[GN_CUBE_MAX_LEVELS])
{
    int count = 0;
    int stake = state->cube;
    int i;

    for (;;) {
        GnMatchLevel *lv = &levels[count];
        int ok = 1;

        lv->dead = (stake >= state->away_on_roll && stake >= state->away_opponent);
        lv->lose_avg = branch_mwc(state, outcomes, stake, 0, &ok);
        lv->win_avg = branch_mwc(state, outcomes, stake, 1, &ok);
        lv->pass = gn_met_after(state, stake, 0);
        lv->cash = gn_met_after(state, stake, 1);
        lv->tp = 0.0;
        lv->cp = 1.0;
        if (!ok || lv->pass < 0.0 || lv->cash < 0.0)
            return 0;

        count++;
        if (count >= 2 && lv->dead)
            break;
        if (count == GN_CUBE_MAX_LEVELS)
            return 0;
        stake *= 2;
    }

    for (i = count - 2; i >= 0; i--) {
        levels[i].tp = level_solve(&levels[i + 1], GN_CUBE_OWNED, -1.0,
                                   levels[i].pass);
        levels[i].cp = level_solve(&levels[i + 1], GN_CUBE_OPPONENT, -1.0,
                                   levels[i].cash);
    }
    return count;
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
        GnMatchLevel levels[GN_CUBE_MAX_LEVELS];
        double e_nd, e_dt, e_dp, e_double;

        gn_probs_exclusive(probs, outcomes);

        /* The §9 chain: levels[0] is the current cube (the "no double"
         * curve), levels[1] the doubled stake the opponent would own after a
         * take. Everything deeper exists only to resolve these two. */
        if (build_levels(state, outcomes, levels) < 2)
            return -1;

        e_nd = level_blend(&levels[0], inputs.win, owner, efficiency);
        e_dt = level_blend(&levels[1], inputs.win, GN_CUBE_OPPONENT, efficiency);
        e_dp = levels[0].cash;
        e_double = (e_dt < e_dp) ? e_dt : e_dp;

        out->equity_no_double = e_nd;
        out->equity_double = e_double;
        /* The opponent's take point at the doubled stake, on the curve the
         * decision actually used -- blended at this efficiency, bisected
         * because no closed form survives the score (v1's reasoning, which
         * the recursion does not change). */
        out->take_point = level_solve(&levels[1], GN_CUBE_OPPONENT, efficiency,
                                      e_dp);

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

/*
 * gn_policy.c -- the stateless playing policy. See gn_policy.h and
 * docs/specs/politique-spec.md, which this file follows to the letter.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_policy.h"

#include <stdlib.h>
#include <string.h>

#include "gn_bearoff.h"

/* T34's measurement, as T35's loop read it from docs/mesures/t34-efficacite.json:
 * the decimal there is printed with the trailing ulp, and the doubles below are
 * those exact doubles -- a rounded 0.688 would move nothing visible and would
 * still be a different engine from the one T35 measured.
 * tests/test_policy.py reads the file and holds the equality. */
static const double EFFICIENCY[3] = {
    0.6880000000000001,   /* GN_CUBE_CENTRED */
    0.5660000000000001,   /* GN_CUBE_OWNED */
    0.687                 /* GN_CUBE_OPPONENT */
};

double gn_policy_efficiency(int owner)
{
    return (owner >= 0 && owner <= 2) ? EFFICIENCY[owner] : -1.0;
}

/* ── Exact certain-loss reading (spec §5.5) ─────────────────────────── */

typedef enum { GOAL_ALL_OFF, GOAL_ONE_OFF, GOAL_OUT_OF_ZONE } Goal;

/* Distance, in pips, from point index `i` to bearing off, for `side`. */
static int distance(int side, int i)
{
    return (side == GN_WHITE) ? i + 1 : GN_NUM_POINTS - i;
}

static int owns(const GnPosition *pos, int side, int i)
{
    return side == GN_WHITE ? pos->points[i] > 0 : pos->points[i] < 0;
}

static int count_at(const GnPosition *pos, int i)
{
    return abs(pos->points[i]);
}

/* No contact: nobody on the bar, and every checker of one side past every
 * checker of the other. WHITE runs towards index 0, BLACK towards 23. */
static int is_race(const GnPosition *pos)
{
    int white_back = -1, black_back = GN_NUM_POINTS;
    if (pos->bar[GN_WHITE] || pos->bar[GN_BLACK])
        return 0;
    for (int i = 0; i < GN_NUM_POINTS; i++) {
        if (pos->points[i] > 0)
            white_back = i;
        if (pos->points[i] < 0 && black_back == GN_NUM_POINTS)
            black_back = i;
    }
    return white_back < black_back;
}

/* Checkers of `side` in the opponent's home board (its last six points). */
static int in_zone(const GnPosition *pos, int side)
{
    int n = pos->bar[side];
    for (int i = 0; i < GN_NUM_POINTS; i++)
        if (owns(pos, side, i) && distance(side, i) > 18)
            n += count_at(pos, i);
    return n;
}

static int goal_reached(const GnPosition *pos, int side, Goal goal)
{
    switch (goal) {
    case GOAL_ALL_OFF: return pos->off[side] == GN_NUM_CHECKERS;
    case GOAL_ONE_OFF: return pos->off[side] >= 1;
    case GOAL_OUT_OF_ZONE: return in_zone(pos, side) == 0;
    }
    return 0;
}

/*
 * A lower bound on the pips `side` must travel before `goal` can hold. Pure
 * arithmetic, so it can only ever discard a branch that is truly out of reach:
 * a roll moves at most 24 pips.
 */
static int pips_needed(const GnPosition *pos, int side, Goal goal)
{
    int need = 0;
    switch (goal) {
    case GOAL_ALL_OFF:
        return gn_position_pip_count(pos, side);
    case GOAL_ONE_OFF:
        /* Every checker must be home (distance <= 6), then one more pip. */
        for (int i = 0; i < GN_NUM_POINTS; i++)
            if (owns(pos, side, i) && distance(side, i) > 6)
                need += count_at(pos, i) * (distance(side, i) - 6);
        return need + 1;
    case GOAL_OUT_OF_ZONE:
        for (int i = 0; i < GN_NUM_POINTS; i++)
            if (owns(pos, side, i) && distance(side, i) > 18)
                need += count_at(pos, i) * (distance(side, i) - 18);
        return need;
    }
    return 0;
}

/* The 21 rolls, largest first: an existential search finds its witness
 * soonest among the big rolls, and the order changes no answer. */
static const signed char ROLLS[21][2] = {
    {6, 6}, {5, 5}, {4, 4}, {6, 5}, {3, 3}, {6, 4}, {5, 4}, {6, 3}, {5, 3},
    {2, 2}, {6, 2}, {4, 3}, {5, 2}, {6, 1}, {4, 2}, {5, 1}, {1, 1}, {3, 2},
    {4, 1}, {3, 1}, {2, 1}
};

/*
 * A lower bound on the DICE `side` must spend before `goal` can hold: a die
 * moves one checker at most six pips, so a checker `e` pips short of where the
 * goal wants it needs ceil(e / 6) dice. A roll offers at most four. Sharper
 * than the pip bound whenever the distance is spread over many checkers.
 */
static int dice_needed(const GnPosition *pos, int side, Goal goal)
{
    const int edge = (goal == GOAL_ALL_OFF) ? 0 : (goal == GOAL_ONE_OFF) ? 6 : 18;
    int need = 0;
    for (int i = 0; i < GN_NUM_POINTS; i++) {
        if (owns(pos, side, i) && distance(side, i) > edge)
            need += count_at(pos, i) * ((distance(side, i) - edge + 5) / 6);
    }
    /* ONE_OFF also needs the die that bears the checker off. */
    return need + (goal == GOAL_ONE_OFF ? 1 : 0);
}

/* `exists` = 1: can `side` reach `goal` within `k` rolls for SOME dice?
 * `exists` = 0: is it SURE to, whatever the dice? Either way the player picks
 * the play, and the plays are tried closest-to-the-goal first -- an order that,
 * like the rolls', only decides how soon the answer is found, never which.
 * Valid only in a race, where the other side cannot interfere. */
static int reach(const GnPosition *pos, int side, Goal goal, int k, int exists,
                 GnPlay *buffer)
{
    if (goal_reached(pos, side, goal))
        return 1;
    if (k == 0)
        return 0;
    if (pips_needed(pos, side, goal) > 24 * k || dice_needed(pos, side, goal) > 4 * k)
        return 0;
    if (goal == GOAL_ALL_OFF) {
        const int left = GN_NUM_CHECKERS - pos->off[side];
        /* A roll bears off at most four checkers, and a non-double -- which
         * the dice can always deal -- at most two. */
        if (left > (exists ? 4 : 2) * k)
            return 0;
    }

    GnPosition mover = *pos;
    mover.turn = (unsigned char)side;
    GnPlay *plays = buffer;
    GnPlay *next = buffer + GN_MAX_PLAYS;
    static _Thread_local int need[GN_POLICY_RESIGN_HORIZON + 1][GN_MAX_PLAYS];
    int *order = need[k - 1 < GN_POLICY_RESIGN_HORIZON ? k - 1 : GN_POLICY_RESIGN_HORIZON];

    for (int r = 0; r < 21; r++) {
        const int n = gn_legal_plays(&mover, ROLLS[r][0], ROLLS[r][1], plays,
                                     GN_MAX_PLAYS);
        int ok = 0;
        if (n < 0)
            return 0;   /* unreadable: never claim a certainty */
        if (n == 0)
            ok = reach(&mover, side, goal, k - 1, exists, next);
        for (int j = 0; j < n && !ok; j++) {
            if (goal_reached(&plays[j].result, side, goal))
                ok = 1;
        }
        if (!ok && k > 1 && n > 0) {
            /* Closest first: pick the next best by a selection walk, so a
             * witness found early stops the whole enumeration. */
            for (int j = 0; j < n; j++)
                order[j] = pips_needed(&plays[j].result, side, goal);
            for (int tried = 0; tried < n && !ok; tried++) {
                int best = -1;
                for (int j = 0; j < n; j++)
                    if (order[j] >= 0 && (best < 0 || order[j] < order[best]))
                        best = j;
                order[best] = -1;
                ok = reach(&plays[best].result, side, goal, k - 1, exists, next);
            }
        }
        if (exists && ok)
            return 1;
        if (!exists && !ok)
            return 0;
    }
    return exists ? 0 : 1;
}

int gn_policy_certain_loss(const GnPosition *pos)
{
    if (pos == NULL || !gn_position_is_valid(pos) || gn_position_is_over(pos))
        return 0;
    if (!is_race(pos))
        return 0;

    const int me = pos->turn;
    const int opp = 1 - me;
    /* One buffer per recursion level: depth <= horizon, plus the root. */
    GnPlay *buffer = malloc(sizeof(GnPlay) * (size_t)GN_MAX_PLAYS
                            * (GN_POLICY_RESIGN_HORIZON + 1));
    if (buffer == NULL)
        return 0;

    int value = 0;
    for (int k = 1; k <= GN_POLICY_RESIGN_HORIZON; k++) {
        if (!reach(pos, opp, GOAL_ALL_OFF, k, 0, buffer))
            continue;
        if (reach(pos, me, GOAL_ALL_OFF, k, 1, buffer))
            continue;

        /* The loss is certain: the opponent is done within k rolls, and the
         * player, who rolls first, cannot be done within k. The opponent
         * cannot be done before `soonest` rolls, so the player gets at least
         * that many. */
        int soonest = 1;
        while (soonest < k && !reach(pos, opp, GOAL_ALL_OFF, soonest, 1, buffer))
            soonest++;

        const int single = pos->off[me] > 0
            || reach(pos, me, GOAL_ONE_OFF, soonest, 0, buffer);
        const int gammon = pos->off[me] == 0
            && !reach(pos, me, GOAL_ONE_OFF, k, 1, buffer);
        if (single) {
            value = 1;
        } else if (gammon) {
            const int backgammon = !reach(pos, me, GOAL_OUT_OF_ZONE, k, 1, buffer);
            const int no_backgammon = in_zone(pos, me) == 0
                || reach(pos, me, GOAL_OUT_OF_ZONE, soonest, 0, buffer);
            value = backgammon ? 3 : (no_backgammon ? 2 : 0);
        }
        break;
    }
    free(buffer);
    return value;
}

/* ── The composition ─────────────────────────────────────────────────── */

static void invert(const float in[GN_NUM_OUTPUTS], float out[GN_NUM_OUTPUTS])
{
    out[GN_P_WIN] = 1.0f - in[GN_P_WIN];
    out[GN_P_WIN_G] = in[GN_P_LOSE_G];
    out[GN_P_WIN_BG] = in[GN_P_LOSE_BG];
    out[GN_P_LOSE_G] = in[GN_P_WIN_G];
    out[GN_P_LOSE_BG] = in[GN_P_WIN_BG];
}

static int is_power_of_two(int n)
{
    return n >= 1 && (n & (n - 1)) == 0;
}

/* The search shape of `level`, money or match at the current cube, cubeless
 * -- T35's player (spec §5.1). Returns 0, or -1 when the level prunes and
 * there is no pruning network, or the match state is outside the table. */
static int level_config(const GnSearchLevel *level, const GnNetwork *prune_net,
                        const GnDecision *d, GnSearchConfig *config)
{
    if (d->use_match) {
        const GnMatchState state = {d->away_on_roll, d->away_opponent, d->cube,
                                    d->crawford};
        *config = gn_search_config_match(level->ply, &state);
        if (!config->use_match)
            return -1;
    } else {
        *config = gn_search_config(level->ply);
    }
    memcpy(config->filter, level->filter, sizeof(config->filter));
    memcpy(config->filter_extra, level->filter_extra, sizeof(config->filter_extra));
    memcpy(config->filter_threshold, level->filter_threshold,
           sizeof(config->filter_threshold));
    if (level->prune_k > 0) {
        if (prune_net == NULL)
            return -1;   /* another configuration than the name announces */
        gn_search_use_prune(config, prune_net, level->prune_k);
    }
    return 0;
}

static int validate(const GnDecision *d)
{
    if (!gn_position_is_valid(&d->position) || gn_position_is_over(&d->position))
        return -1;
    if (d->pending < GN_PENDING_MOVE || d->pending > GN_PENDING_RESIGN)
        return -1;
    if (!is_power_of_two(d->cube))
        return -1;
    if (d->cube_owner < GN_CUBE_CENTRED || d->cube_owner > GN_CUBE_OPPONENT)
        return -1;
    /* A turned cube has an owner and an unturned one has none (beavers are
     * outside the policy, spec §7). */
    if ((d->cube == 1) != (d->cube_owner == GN_CUBE_CENTRED))
        return -1;
    if (d->use_match) {
        const GnMatchState state = {d->away_on_roll, d->away_opponent, d->cube,
                                    d->crawford};
        if (!gn_match_state_is_valid(&state))
            return -1;
        /* The Crawford game is a 1-away game with no cube in play. */
        if (d->crawford && ((d->away_on_roll != 1 && d->away_opponent != 1)
                            || d->cube != 1))
            return -1;
    }
    if (d->pending == GN_PENDING_MOVE
        && (d->d1 < 1 || d->d1 > 6 || d->d2 < 1 || d->d2 > 6))
        return -1;
    if (d->pending == GN_PENDING_RESIGN
        && (d->resign_value < 1 || d->resign_value > 3))
        return -1;
    return 0;
}

static int decide_move(const GnNetwork *net, const GnSearchLevel *level,
                       const GnNetwork *prune_net, const GnDecision *d,
                       GnAction *out)
{
    GnPlay *plays = malloc(sizeof(GnPlay) * (size_t)GN_MAX_PLAYS);
    if (plays == NULL)
        return -1;
    const int n = gn_legal_plays(&d->position, d->d1, d->d2, plays, GN_MAX_PLAYS);
    if (n < 0) {
        free(plays);
        return -1;
    }
    out->kind = GN_ACTION_MOVE;
    if (n == 0) {
        out->play.num_moves = 0;
        out->play.result = d->position;
        gn_position_swap_turn(&out->play.result);
        free(plays);
        return 0;
    }
    if (n == 1) {
        out->play = plays[0];
        free(plays);
        return 0;
    }
    free(plays);

    GnSearchConfig config;
    if (level_config(level, prune_net, d, &config) != 0)
        return -1;
    GnCandidate best;
    if (gn_best_play(net, &d->position, d->d1, d->d2, &config, &best) != 0)
        return -1;
    out->play = best.play;
    out->searched = 1;
    out->equity_a = best.equity;
    return 0;
}

/* The pre-roll distribution at the level, from the player on roll's side. */
static int pre_roll_probs(const GnNetwork *net, const GnSearchLevel *level,
                          const GnNetwork *prune_net, const GnDecision *d,
                          float probs[GN_NUM_OUTPUTS])
{
    GnSearchConfig config;
    if (level_config(level, prune_net, d, &config) != 0)
        return -1;
    return gn_search_probs(net, &d->position, &config, probs);
}

/* The money exact table, when one is installed and knows the position. */
static int exact_equities(const GnDecision *d, double equities[4])
{
    const GnBearoff *table = gn_bearoff_shared();
    if (d->use_match || table == NULL || !gn_bearoff_contains(table, &d->position))
        return 0;
    /* Only where no gammon is possible -- what makes the Jacoby rule moot on
     * this path (decide_cube). The shipped table (11 checkers) never holds
     * anything else; a wider one would, and is then not consulted here. */
    if (d->position.off[GN_WHITE] == 0 || d->position.off[GN_BLACK] == 0)
        return 0;
    return gn_bearoff_equities(table, &d->position, equities);
}

static int decide_cube(const GnNetwork *net, const GnSearchLevel *level,
                       const GnNetwork *prune_net, const GnDecision *d,
                       GnAction *out)
{
    out->kind = GN_ACTION_ROLL;

    int value = gn_policy_certain_loss(&d->position);
    if (value > 0) {
        if (!d->use_match && d->jacoby && d->cube_owner == GN_CUBE_CENTRED)
            value = 1;   /* an unturned cube under Jacoby pays a single game */
        out->kind = GN_ACTION_RESIGN;
        out->resign_value = value;
        return 0;
    }

    if (d->cube_owner == GN_CUBE_OPPONENT)
        return 0;
    if (d->use_match && (d->crawford || d->cube >= d->away_on_roll))
        return 0;

    double e_nd, e_dt, e_dp;
    GnCubeAction verdict;
    double exact[4];
    if (exact_equities(d, exact)) {
        /* No Jacoby adjustment, deliberately: the table only holds positions
         * where both sides have borne off at least four checkers, so no
         * gammon is possible there (gn_bearoff.h), and gammons are all that
         * Jacoby removes. */
        e_nd = (d->cube_owner == GN_CUBE_CENTRED) ? exact[2] : exact[1];
        e_dt = 2.0 * exact[3];
        e_dp = 1.0;
        verdict = gn_cube_verdict(e_nd, e_dt, e_dp);
        out->equity_a = e_nd;
        out->equity_b = (e_dt < e_dp) ? e_dt : e_dp;
    } else {
        float probs[GN_NUM_OUTPUTS];
        if (pre_roll_probs(net, level, prune_net, d, probs) != 0)
            return -1;
        const GnMatchState state = {d->away_on_roll, d->away_opponent, d->cube,
                                    d->crawford};
        GnCubeDecision decision;
        if (gn_cube_decide(probs, (GnCubeOwner)d->cube_owner,
                           d->use_match ? &state : NULL,
                           EFFICIENCY[d->cube_owner], d->jacoby, &decision) != 0)
            return -1;
        verdict = decision.action;
        out->equity_a = decision.equity_no_double;
        out->equity_b = decision.equity_double;
    }
    out->searched = 1;

    /* Double on double/take and double/pass -- except the OPTIONAL double, a
     * double/pass that is worth exactly what not doubling is (spec §5.2). */
    if ((verdict == GN_DOUBLE_TAKE || verdict == GN_DOUBLE_PASS)
        && !(verdict == GN_DOUBLE_PASS && out->equity_b == out->equity_a))
        out->kind = GN_ACTION_DOUBLE;
    return 0;
}

static int decide_take(const GnNetwork *net, const GnSearchLevel *level,
                       const GnNetwork *prune_net, const GnDecision *d,
                       GnAction *out)
{
    /* Seen from the doubler, who is on roll: a cube the taker owns cannot be
     * turned, and the Crawford game has none (spec §5.3). */
    if (d->cube_owner == GN_CUBE_OPPONENT || (d->use_match && d->crawford))
        return -1;

    const double x_taken = EFFICIENCY[GN_CUBE_OPPONENT];
    double e_dt, e_dp;   /* the doubler's side, T35's comparison */
    double exact[4];
    if (exact_equities(d, exact)) {
        e_dt = 2.0 * exact[3];
        e_dp = 1.0;
    } else {
        float probs[GN_NUM_OUTPUTS];
        if (pre_roll_probs(net, level, prune_net, d, probs) != 0)
            return -1;
        if (d->use_match) {
            const GnMatchState state = {d->away_on_roll, d->away_opponent,
                                        d->cube, d->crawford};
            const GnMatchState doubled = {d->away_on_roll, d->away_opponent,
                                          2 * d->cube, d->crawford};
            int failed = 0;
            e_dt = gn_cube_value(probs, GN_CUBE_OPPONENT, &doubled, x_taken,
                                 &failed);
            if (failed)
                return -1;
            const double cash = gn_met_after(&state, d->cube, 1);
            if (cash < 0.0)
                return -1;
            e_dp = 2.0 * cash - 1.0;
        } else {
            GnCubeInputs inputs;
            if (gn_cube_inputs(probs, &inputs) != 0)
                return -1;
            e_dt = 2.0 * gn_cube_equity(&inputs, GN_CUBE_OPPONENT, 1, x_taken);
            e_dp = 1.0;
        }
    }
    out->searched = 1;
    /* Reported from the taker's side, on the scale every other case uses:
     * points per current cube in money, the taker's MWC at a match score
     * (e = 2·MWC − 1 seen from the doubler). The verdict itself is T35's
     * comparison on the doubler's numbers, untouched. */
    if (d->use_match) {
        out->equity_a = (1.0 - e_dt) / 2.0;
        out->equity_b = (1.0 - e_dp) / 2.0;
    } else {
        out->equity_a = -e_dt;
        out->equity_b = -e_dp;
    }
    out->kind = (e_dt < e_dp) ? GN_ACTION_TAKE : GN_ACTION_PASS;
    return 0;
}

static int decide_resign_offer(const GnNetwork *net, const GnSearchLevel *level,
                               const GnNetwork *prune_net, const GnDecision *d,
                               GnAction *out)
{
    float resigner[GN_NUM_OUTPUTS], mine[GN_NUM_OUTPUTS];
    if (pre_roll_probs(net, level, prune_net, d, resigner) != 0)
        return -1;
    invert(resigner, mine);

    double accept, play_on;
    if (d->use_match) {
        /* The decider's view: the away scores trade places. */
        const GnMatchState state = {d->away_opponent, d->away_on_roll, d->cube,
                                    d->crawford};
        accept = gn_met_after(&state, d->resign_value * d->cube, 1);
        play_on = gn_match_winning_chance(&state, mine);
        if (accept < 0.0 || play_on < 0.0)
            return -1;
    } else {
        accept = (double)d->resign_value;
        play_on = (d->jacoby && d->cube_owner == GN_CUBE_CENTRED)
            ? 2.0 * (double)mine[GN_P_WIN] - 1.0
            : (double)gn_money_equity(mine);
    }
    out->searched = 1;
    out->equity_a = accept;
    out->equity_b = play_on;
    out->kind = (accept >= play_on) ? GN_ACTION_ACCEPT : GN_ACTION_REJECT;
    return 0;
}

int gn_policy_decide_level(const GnNetwork *net, const GnNetwork *prune_net,
                           const GnSearchLevel *level,
                           const GnDecision *decision, GnAction *out)
{
    if (out == NULL)
        return -1;
    memset(out, 0, sizeof(*out));
    if (net == NULL || level == NULL || decision == NULL || validate(decision) != 0)
        return -1;

    int rc = -1;
    switch (decision->pending) {
    case GN_PENDING_MOVE:
        rc = decide_move(net, level, prune_net, decision, out);
        break;
    case GN_PENDING_CUBE:
        rc = decide_cube(net, level, prune_net, decision, out);
        break;
    case GN_PENDING_TAKE:
        rc = decide_take(net, level, prune_net, decision, out);
        break;
    case GN_PENDING_RESIGN:
        rc = decide_resign_offer(net, level, prune_net, decision, out);
        break;
    }
    if (rc != 0)
        memset(out, 0, sizeof(*out));
    return rc;
}

int gn_policy_decide(const GnNetwork *net, const GnNetwork *prune_net,
                     const char *level, const GnDecision *decision,
                     GnAction *out)
{
    const GnSearchLevel *shape = (level != NULL) ? gn_search_level(level) : NULL;
    if (shape == NULL) {
        if (out != NULL)
            memset(out, 0, sizeof(*out));
        return -1;
    }
    return gn_policy_decide_level(net, prune_net, shape, decision, out);
}

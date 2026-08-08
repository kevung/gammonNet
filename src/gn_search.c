/*
 * gn_search.c -- expectiminimax over dice. See gn_search.h for the recursion,
 * the perspective rule, and what this deliberately does not do.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_search.h"

#include "gn_bearoff.h"
#include "gn_choose.h"
#include "gn_cube.h"
#include "gn_evalcache.h"

#include <stdlib.h>
#include <string.h>

/* A position has at most a few hundred legal plays; 2048 is the bound the rules
 * layer already uses, and reusing it keeps one number instead of two. */
#define MAX_PLAYS 2048

typedef struct {
    signed char d1, d2;
    double weight;
} GnRoll;

/*
 * The 21 distinct rolls with their probabilities.
 *
 * Built once, at first use, rather than written out by hand: a table of 21
 * literals is 21 chances to mistype a weight, and the error would be a silent
 * bias in every evaluation rather than a crash.
 */
static GnRoll g_rolls[GN_NUM_ROLLS];
static int g_rolls_ready = 0;

static void build_rolls(void)
{
    if (g_rolls_ready) {
        return;
    }
    int n = 0;
    for (int a = 1; a <= 6; a++) {
        for (int b = a; b <= 6; b++) {
            g_rolls[n].d1 = (signed char)a;
            g_rolls[n].d2 = (signed char)b;
            g_rolls[n].weight = (a == b) ? (1.0 / 36.0) : (2.0 / 36.0);
            n++;
        }
    }
    g_rolls_ready = 1;
}

/* Deliberately not thread-local: this project has no threads yet, and a
 * counter that pretended to be thread-safe without being tested as such would
 * be worse than one that is honestly single-threaded. */
static unsigned long g_evaluations = 0;

unsigned long gn_search_evaluations(void) { return g_evaluations; }
void gn_search_reset_evaluations(void) { g_evaluations = 0; }

/*
 * The single place a leaf position becomes five probabilities (T38, T3A).
 *
 * Three sources are tried in order, each cheaper to skip than the one after
 * it:
 *
 *   1. The exact bearoff table, if one is installed. A hit is exact, and
 *      costs one memory read.
 *   2. The evaluation cache, if one is installed (T3A). A hit is the network's
 *      own past answer for this EXACT position -- see gn_evalcache.h for why
 *      that makes it safe to return without re-running the network -- and it
 *      also costs about one memory read plus a 29-byte comparison.
 *   3. The network itself: the one source that was ever expensive.
 *
 * `g_evaluations` counts ONLY step 3. A bearoff hit was never a network
 * evaluation (T38's distinction), and neither is a cache hit: it is the
 * SAME evaluation, counted once, when it first happened. Counting it twice
 * would make the cache look like it does nothing, and counting it zero times
 * for the miss that populated the cache would undercount the real cost.
 * `gn_evalcache_hits()` / `_misses()` are the separate counters that make the
 * cache's own contribution measurable.
 *
 * Both call sites that used to invoke `gn_evaluate` directly on a leaf go
 * through here now: `leaf_value` and the shallow pass of `rank_plays`.
 */
static int evaluate_position(const GnNetwork *net, const GnPosition *pos,
                             float probs[GN_NUM_OUTPUTS])
{
    const GnBearoff *table = gn_bearoff_shared();
    if (table != NULL && gn_bearoff_probs(table, pos, probs)) {
        return 0;
    }

    GnEvalCache *cache = gn_evalcache_shared();
    if (cache != NULL && gn_evalcache_lookup(cache, pos, probs)) {
        return 0;
    }

    if (gn_evaluate(net, pos, probs) != 0) {
        return -1;
    }
    g_evaluations++;
    if (cache != NULL) {
        gn_evalcache_store(cache, pos, probs);
    }
    return 0;
}

GnSearchConfig gn_search_config(int ply)
{
    GnSearchConfig config;
    memset(&config, 0, sizeof(config));
    config.ply = (ply < 0) ? 0 : (ply > GN_MAX_PLY ? GN_MAX_PLY : ply);
    return config;
}

GnSearchConfig gn_search_config_match(int ply, const GnMatchState *state)
{
    GnSearchConfig config = gn_search_config(ply);
    if (state == NULL || !gn_match_state_is_valid(state)) {
        /* Refused, not degraded. Falling back to money here would produce a
         * search that is wrong in a match and says nothing about it. */
        config.ply = 0;
        return config;
    }
    config.use_match = 1;
    config.match = *state;
    return config;
}

/* The same position, seen from the other side of the table. One reading of
 * the swap for the whole repository: gn_met.h owns it. */
static GnMatchState swap_sides(GnMatchState state)
{
    return gn_match_state_swap(state);
}

/* The same cube, seen from the other side of the table: mine becomes theirs,
 * a centred cube is centred for everyone. Mirrored at every ply for exactly
 * the reason the match state is swapped -- forgetting it would value every
 * odd ply with the wrong player holding the cube, plausibly. */
static int mirror_owner(int owner)
{
    if (owner == GN_CUBE_OWNED)
        return GN_CUBE_OPPONENT;
    if (owner == GN_CUBE_OPPONENT)
        return GN_CUBE_OWNED;
    return GN_CUBE_CENTRED;
}

void gn_search_use_cube(GnSearchConfig *config, int owner, double efficiency)
{
    if (config == NULL) {
        return;
    }
    config->use_cube = 1;
    config->cube_owner = owner;
    config->cube_x = efficiency;
}

/*
 * Turn a distribution into a value, from the point of view of the player whose
 * `state` this is.
 *
 * Money equity or match equity, on the SAME scale: both are 0 for an even
 * position and negate between sides. That is what lets one recursion serve
 * both, and why the match path works in `2 * MWC - 1` rather than raw winning
 * chances.
 *
 * Takes probabilities rather than a position on purpose: the caller has often
 * already paid for the evaluation, and re-running it here would double the cost
 * of the single dominant operation in this file.
 */
static double value_from_probs(const float probs[GN_NUM_OUTPUTS],
                               const GnSearchConfig *config, GnMatchState state,
                               int *failed)
{
    if (!config->use_match) {
        return (double)gn_money_equity(probs);
    }
    const double equity = gn_match_equity(&state, probs);
    if (equity <= -2.0) {
        if (failed) *failed = 1;
        return 0.0;
    }
    return equity;
}

/*
 * The value of one evaluated node -- cubeless (`value_from_probs`) or, under
 * `use_cube`, the cube model at this node's owner (t34-videau-spec §8).
 *
 * Takes the position as well as its distribution because the exact shortcut
 * needs it: in the two-sided table's money domain the four cubeful equities
 * are stored, and reading one beats modelling it. Only money -- the table
 * stores points, and turning them into a MWC would need the distribution
 * anyway, which is exactly the model path below.
 */
static double node_value(const GnPosition *pos,
                         const float probs[GN_NUM_OUTPUTS],
                         const GnSearchConfig *config, GnMatchState state,
                         int owner, int *failed)
{
    if (!config->use_cube) {
        return value_from_probs(probs, config, state, failed);
    }

    if (!config->use_match) {
        const GnBearoff *table = gn_bearoff_shared();
        double equities[4];
        if (table != NULL && gn_bearoff_equities(table, pos, equities)) {
            /* gn_bearoff.h's order: cubeless, owned, centred, opponent --
             * indexed by GnCubeOwner {CENTRED=0, OWNED=1, OPPONENT=2}. */
            static const int index_of_owner[3] = {2, 1, 3};
            return equities[index_of_owner[owner]];
        }
    }

    int cube_failed = 0;
    const double value = gn_cube_value(probs, (GnCubeOwner)owner,
                                       config->use_match ? &state : NULL,
                                       config->cube_x, &cube_failed);
    if (cube_failed) {
        if (failed) *failed = 1;
        return 0.0;
    }
    return value;
}

/* The value of a leaf: evaluate once, then convert. */
static double leaf_value(const GnNetwork *net, const GnPosition *pos,
                         const GnSearchConfig *config, GnMatchState state,
                         int owner, int *failed)
{
    float probs[GN_NUM_OUTPUTS];
    if (evaluate_position(net, pos, probs) != 0) {
        if (failed) *failed = 1;
        return 0.0;
    }
    return node_value(pos, probs, config, state, owner, failed);
}

/* The value of a finished game, from the point of view of `pos->turn` -- who
 * is the loser. Computed, never evaluated. */
static double terminal_value(const GnPosition *pos, const GnSearchConfig *config,
                             GnMatchState state)
{
    if (!config->use_match) {
        return gn_terminal_equity(pos);
    }
    const int winner = gn_position_winner(pos);
    const int stake = gn_game_value(pos, winner);
    if (stake < 0) {
        return 0.0;
    }
    /* `pos->turn` names the loser, so the player to move never wins here. */
    const double mwc = gn_met_after(&state, stake * state.cube, 0);
    return (mwc < 0.0) ? 0.0 : 2.0 * mwc - 1.0;
}

double gn_terminal_equity(const GnPosition *pos)
{
    if (pos == NULL || !gn_position_is_over(pos)) {
        return 0.0;
    }

    const int winner = gn_position_winner(pos);

    /*
     * `gn_game_value` from T04 already decides plain / gammon / backgammon.
     * Reimplementing that rule here would put two readings of it in one
     * repository, and the day they disagreed, nothing would say which one the
     * measurements had used. It is called, not copied.
     */
    const int stake = gn_game_value(pos, winner);
    if (stake < 0) {
        return 0.0;
    }

    /* `pos->turn` names the loser at a terminal position -- see gn_rules.h. */
    return (pos->turn == (unsigned char)winner) ? (double)stake : -(double)stake;
}

/* Equity of `pos` from `pos->turn`'s point of view, dice not yet rolled.
 * `owner` is the cube as `pos->turn` sees it (unused unless `use_cube`). */
static double position_equity(const GnNetwork *net, const GnPosition *pos,
                              const GnSearchConfig *config, int depth,
                              GnMatchState state, int owner);

static int compare_candidates(const void *a, const void *b)
{
    const double x = ((const GnCandidate *)a)->equity;
    const double y = ((const GnCandidate *)b)->equity;
    /* Best first. */
    return (x < y) - (x > y);
}

/*
 * Rank the plays for one roll at `depth`, writing them best-first.
 *
 * At depth 0 each play costs one network evaluation. Deeper, the plays are
 * first ranked by a 0-ply pass, then the survivors -- all of them if no filter
 * is set -- are re-scored by the recursion. Ranking shallow before searching
 * deep is what makes a filter possible at all, and it is also why an unfiltered
 * search still pays for the shallow pass: a cost worth naming, since it is
 * roughly one extra evaluation per play.
 */
static int rank_plays(const GnNetwork *net, const GnPosition *pos,
                      int d1, int d2, const GnSearchConfig *config, int depth,
                      GnMatchState state, int owner, GnCandidate *out,
                      int max_out)
{
    if (net == NULL || pos == NULL || out == NULL || max_out <= 0) {
        return -1;
    }

    GnPlay *plays = malloc(sizeof(GnPlay) * MAX_PLAYS);
    if (plays == NULL) {
        return -1;
    }

    const int count = gn_legal_plays(pos, d1, d2, plays, MAX_PLAYS);
    if (count <= 0) {
        free(plays);
        return (count < 0) ? -1 : 0;
    }

    const int written = (count < max_out) ? count : max_out;

    /* Shallow pass: rank every play by the network alone. */
    for (int i = 0; i < count && i < max_out; i++) {
        out[i].play = plays[i];

        const GnPosition *result = &plays[i].result;
        /* The result has handed the turn over, so everything about it is seen
         * from the opponent's side -- including the score. */
        const GnMatchState theirs = swap_sides(state);

        if (gn_position_is_over(result)) {
            /* Computed, never evaluated -- see gn_terminal_equity. */
            memset(out[i].probs, 0, sizeof(out[i].probs));
            out[i].equity = -terminal_value(result, config, theirs);
            continue;
        }

        /* Evaluated ONCE. `probs` keeps the raw distribution -- it describes
         * the position, not the score -- and only `equity` is score-aware. */
        if (evaluate_position(net, result, out[i].probs) != 0) {
            free(plays);
            return -1;
        }

        int failed = 0;
        const double value = node_value(result, out[i].probs, config, theirs,
                                        mirror_owner(owner), &failed);
        if (failed) {
            free(plays);
            return -1;
        }
        /* The negation: the answer was the opponent's. */
        out[i].equity = -value;
    }
    free(plays);

    qsort(out, (size_t)written, sizeof(GnCandidate), compare_candidates);

    if (depth <= 0) {
        return written;
    }

    int searched = written;
    const int filter = config->filter[depth];
    if (filter > 0 && filter < searched) {
        searched = filter;
    }

    for (int i = 0; i < searched; i++) {
        const GnPosition *result = &out[i].play.result;
        if (gn_position_is_over(result)) {
            continue; /* already exact */
        }
        /*
         * `depth`, not `depth - 1`. A decision at depth k scores each play at
         * -V(result, k): the k counts the opponent's rolls to enumerate AFTER
         * the play, and the play itself is not one of them.
         *
         * Written as `depth - 1` first, and the mistake was instructive: at
         * 1-ply the deep pass then recomputed exactly what the shallow pass had
         * already computed. Nothing crashed, the equity still moved -- the
         * other entry point was right -- and only the ranking gave it away, by
         * never once differing from 0-ply over 114 decisions.
         */
        out[i].equity = -position_equity(net, result, config, depth,
                                         swap_sides(state),
                                         mirror_owner(owner));
    }

    /* Re-rank: the deep pass is allowed to disagree with the shallow one, and
     * if it never did, the deep pass would be pointless. */
    qsort(out, (size_t)searched, sizeof(GnCandidate), compare_candidates);
    return written;
}

static double position_equity(const GnNetwork *net, const GnPosition *pos,
                              const GnSearchConfig *config, int depth,
                              GnMatchState state, int owner)
{
    if (gn_position_is_over(pos)) {
        return terminal_value(pos, config, state);
    }

    if (depth <= 0) {
        return leaf_value(net, pos, config, state, owner, NULL);
    }

    build_rolls();

    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return 0.0;
    }

    double total = 0.0;
    for (int r = 0; r < GN_NUM_ROLLS; r++) {
        const int count = rank_plays(net, pos, g_rolls[r].d1, g_rolls[r].d2,
                                     config, depth - 1, state, owner,
                                     candidates, MAX_PLAYS);

        double best;
        if (count > 0) {
            best = candidates[0].equity;
        } else {
            /*
             * No legal play: the turn simply passes. Not an error -- a closed
             * board or a hopeless bar entry produces it, and treating it as one
             * would silently drop those branches from the average.
             */
            GnPosition passed = *pos;
            gn_position_swap_turn(&passed);
            best = -position_equity(net, &passed, config, depth - 1,
                                    swap_sides(state), mirror_owner(owner));
        }
        total += g_rolls[r].weight * best;
    }

    free(candidates);
    return total;
}

/* ── The distribution at depth (t34-videau-spec §8, step 1) ──────────── */

/* The same distribution, seen from the other side of the table. The nested
 * encoding makes this a swap plus one complement: my gammon losses are the
 * opponent's gammon wins, and P(win) partitions. */
static void invert_probs(const float in[GN_NUM_OUTPUTS],
                         float out[GN_NUM_OUTPUTS])
{
    out[GN_P_WIN] = 1.0f - in[GN_P_WIN];
    out[GN_P_WIN_G] = in[GN_P_LOSE_G];
    out[GN_P_WIN_BG] = in[GN_P_LOSE_BG];
    out[GN_P_LOSE_G] = in[GN_P_WIN_G];
    out[GN_P_LOSE_BG] = in[GN_P_WIN_BG];
}

/* The distribution of a finished game -- all mass on the one outcome that
 * happened. Computed, never evaluated, like `gn_terminal_equity`. */
static void terminal_probs(const GnPosition *pos, float out[GN_NUM_OUTPUTS])
{
    const int winner = gn_position_winner(pos);
    const int stake = gn_game_value(pos, winner);
    const int we_won = (pos->turn == (unsigned char)winner);

    out[GN_P_WIN] = we_won ? 1.0f : 0.0f;
    out[GN_P_WIN_G] = (we_won && stake >= 2) ? 1.0f : 0.0f;
    out[GN_P_WIN_BG] = (we_won && stake >= 3) ? 1.0f : 0.0f;
    out[GN_P_LOSE_G] = (!we_won && stake >= 2) ? 1.0f : 0.0f;
    out[GN_P_LOSE_BG] = (!we_won && stake >= 3) ? 1.0f : 0.0f;
}

/*
 * The §8 recursion: the distribution follows the play the SCALAR recursion
 * would choose. `rank_plays` picks the best play with the configured
 * valuation; only what happens to the winner's distribution is new here.
 *
 * A separate walk rather than a widening of `position_equity`: the price is
 * re-walking one subtree per node (paid only when a caller actually asks for
 * a distribution -- once per cube decision, never per move choice), the
 * reward is that the equity path is untouched, byte for byte, so T12's
 * non-regression corpus keeps meaning what it meant. With the T3A cache
 * installed the re-walk's network evaluations are all hits anyway.
 */
static int position_probs(const GnNetwork *net, const GnPosition *pos,
                          const GnSearchConfig *config, int depth,
                          GnMatchState state, int owner,
                          float out[GN_NUM_OUTPUTS])
{
    if (gn_position_is_over(pos)) {
        terminal_probs(pos, out);
        return 0;
    }

    if (depth <= 0) {
        return evaluate_position(net, pos, out);
    }

    build_rolls();

    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return -1;
    }

    double total[GN_NUM_OUTPUTS] = {0.0, 0.0, 0.0, 0.0, 0.0};
    for (int r = 0; r < GN_NUM_ROLLS; r++) {
        const int count = rank_plays(net, pos, g_rolls[r].d1, g_rolls[r].d2,
                                     config, depth - 1, state, owner,
                                     candidates, MAX_PLAYS);
        if (count < 0) {
            free(candidates);
            return -1;
        }

        float theirs[GN_NUM_OUTPUTS];
        int failed;
        if (count > 0) {
            /* The best play's own distribution, at the depth its equity was
             * scored at -- `depth - 1`, mirroring `-V(result, depth - 1)`. */
            failed = position_probs(net, &candidates[0].play.result, config,
                                    depth - 1, swap_sides(state),
                                    mirror_owner(owner), theirs);
        } else {
            /* No legal play: the turn passes, exactly as in the scalar
             * recursion -- dropping the branch would bias the average. */
            GnPosition passed = *pos;
            gn_position_swap_turn(&passed);
            failed = position_probs(net, &passed, config, depth - 1,
                                    swap_sides(state), mirror_owner(owner),
                                    theirs);
        }
        if (failed != 0) {
            free(candidates);
            return -1;
        }

        float mine[GN_NUM_OUTPUTS];
        invert_probs(theirs, mine);
        for (int i = 0; i < GN_NUM_OUTPUTS; i++) {
            total[i] += g_rolls[r].weight * (double)mine[i];
        }
    }

    free(candidates);
    for (int i = 0; i < GN_NUM_OUTPUTS; i++) {
        out[i] = (float)total[i];
    }
    return 0;
}

int gn_search_probs(const GnNetwork *net, const GnPosition *pos,
                    const GnSearchConfig *config, float out[GN_NUM_OUTPUTS])
{
    if (net == NULL || pos == NULL || config == NULL || out == NULL) {
        return -1;
    }
    return position_probs(net, pos, config, config->ply, config->match,
                          config->cube_owner, out);
}

int gn_search_plays(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                    const GnSearchConfig *config,
                    GnCandidate *out, int max_out)
{
    if (config == NULL) {
        return -1;
    }
    return rank_plays(net, pos, d1, d2, config, config->ply, config->match,
                      config->cube_owner, out, max_out);
}

int gn_best_play(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                 const GnSearchConfig *config, GnCandidate *out)
{
    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return -1;
    }
    const int count = gn_search_plays(net, pos, d1, d2, config,
                                      candidates, MAX_PLAYS);
    if (count > 0 && out != NULL) {
        *out = candidates[0];
    }
    free(candidates);
    return (count > 0) ? 0 : -1;
}

double gn_search_equity(const GnNetwork *net, const GnPosition *pos,
                        const GnSearchConfig *config)
{
    if (net == NULL || pos == NULL || config == NULL) {
        return 0.0;
    }
    return position_equity(net, pos, config, config->ply, config->match,
                           config->cube_owner);
}

/*
 * gn_search.c -- expectiminimax over dice. See gn_search.h for the recursion,
 * the perspective rule, and what this deliberately does not do.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_search.h"

#include "gn_choose.h"

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

GnSearchConfig gn_search_config(int ply)
{
    GnSearchConfig config;
    memset(&config, 0, sizeof(config));
    config.ply = (ply < 0) ? 0 : (ply > GN_MAX_PLY ? GN_MAX_PLY : ply);
    return config;
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

/* Equity of `pos` from `pos->turn`'s point of view, dice not yet rolled. */
static double position_equity(const GnNetwork *net, const GnPosition *pos,
                              const GnSearchConfig *config, int depth);

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
                      GnCandidate *out, int max_out)
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
        if (gn_position_is_over(result)) {
            /* Computed, never evaluated -- see gn_terminal_equity. */
            memset(out[i].probs, 0, sizeof(out[i].probs));
            out[i].equity = -gn_terminal_equity(result);
            continue;
        }

        if (gn_evaluate(net, result, out[i].probs) != 0) {
            free(plays);
            return -1;
        }
        g_evaluations++;
        /* The negation: the network answered for the opponent. */
        out[i].equity = -(double)gn_money_equity(out[i].probs);
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
        out[i].equity = -position_equity(net, result, config, depth);
    }

    /* Re-rank: the deep pass is allowed to disagree with the shallow one, and
     * if it never did, the deep pass would be pointless. */
    qsort(out, (size_t)searched, sizeof(GnCandidate), compare_candidates);
    return written;
}

static double position_equity(const GnNetwork *net, const GnPosition *pos,
                              const GnSearchConfig *config, int depth)
{
    if (gn_position_is_over(pos)) {
        return gn_terminal_equity(pos);
    }

    if (depth <= 0) {
        float probs[GN_NUM_OUTPUTS];
        if (gn_evaluate(net, pos, probs) != 0) {
            return 0.0;
        }
        g_evaluations++;
        return (double)gn_money_equity(probs);
    }

    build_rolls();

    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return 0.0;
    }

    double total = 0.0;
    for (int r = 0; r < GN_NUM_ROLLS; r++) {
        const int count = rank_plays(net, pos, g_rolls[r].d1, g_rolls[r].d2,
                                     config, depth - 1, candidates, MAX_PLAYS);

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
            best = -position_equity(net, &passed, config, depth - 1);
        }
        total += g_rolls[r].weight * best;
    }

    free(candidates);
    return total;
}

int gn_search_plays(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                    const GnSearchConfig *config,
                    GnCandidate *out, int max_out)
{
    if (config == NULL) {
        return -1;
    }
    return rank_plays(net, pos, d1, d2, config, config->ply, out, max_out);
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
    return position_equity(net, pos, config, config->ply);
}

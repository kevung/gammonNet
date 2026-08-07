/*
 * gn_choose.c -- 0-ply move choice. See gn_choose.h before editing.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_choose.h"

#include "gn_bearoff.h"
#include "gn_encoding.h"

#include <stddef.h>

/* Same thread-local reasoning as gn_rules_reference.c: the round-robin runs one
 * chooser per core, and a shared buffer would corrupt every one of them at once
 * while still handing each a well-formed play. */
#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L && !defined(__STDC_NO_THREADS__)
#define GN_THREAD_LOCAL _Thread_local
#elif defined(__GNUC__)
#define GN_THREAD_LOCAL __thread
#else
#define GN_THREAD_LOCAL
#endif

int gn_game_value(const GnPosition *pos, int winner)
{
    int loser;
    int i, first, last;

    if (!gn_position_is_over(pos))
        return -1;
    if (winner != GN_WHITE && winner != GN_BLACK)
        return -1;

    loser = (winner == GN_WHITE) ? GN_BLACK : GN_WHITE;

    if (pos->off[loser] > 0)
        return 1;
    if (pos->bar[loser] > 0)
        return 3;

    /* The winner's home board — indices 0-5 for WHITE, 18-23 for BLACK. Not a
     * fixed end of the array: a constant here would be right for one colour. */
    if (winner == GN_WHITE) {
        first = 0;
        last = 5;
    } else {
        first = 18;
        last = GN_NUM_POINTS - 1;
    }

    for (i = first; i <= last; i++) {
        int n = pos->points[i];

        if (loser == GN_BLACK ? (n < 0) : (n > 0))
            return 3;
    }

    return 2;
}

int gn_best_play_0ply(const GnNetwork *net, const GnPosition *pos,
                      int d1, int d2, GnPlay *out)
{
    static GN_THREAD_LOCAL GnPlay plays[GN_MAX_PLAYS];
    float features[GN_NUM_FEATURES];
    float probs[GN_NUM_OUTPUTS];
    int count;
    int i;
    int best = -1;
    float best_equity = 0.0f;

    if (!net || !pos || !out)
        return -1;

    count = gn_legal_plays(pos, d1, d2, plays, GN_MAX_PLAYS);
    if (count < 0)
        return -1;
    if (count == 0)
        return 0;

    for (i = 0; i < count; i++) {
        const GnPosition *result = &plays[i].result;
        float equity;

        if (gn_position_is_over(result)) {
            /* The mover has just won. Score the stake exactly rather than ask
             * the network to estimate a position with no continuation. The
             * value is from the OPPONENT's side, like everything else here. */
            int value = gn_game_value(result, pos->turn);

            if (value < 0)
                return -1;
            equity = (float) -value;
        } else {
            /* The exact table first, same rule as gn_search.c's
             * `evaluate_position`: a hit is exact and free of the network, a
             * miss falls back to it unchanged. See gn_bearoff.h for why this
             * needs no lock. */
            const GnBearoff *table = gn_bearoff_shared();
            if (table != NULL && gn_bearoff_probs(table, result, probs)) {
                equity = gn_money_equity(probs);
            } else {
                if (gn_encode(result, features) != 0)
                    return -1;
                if (gn_evaluate_features(net, features, probs) != 0)
                    return -1;
                equity = gn_money_equity(probs);
            }
        }

        /* MINIMISE: `result` is seen by the opponent, who is now on roll. */
        if (best < 0 || equity < best_equity) {
            best = i;
            best_equity = equity;
        }
    }

    *out = plays[best];
    return 1;
}

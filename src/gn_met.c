/*
 * gn_met.c -- see gn_met.h for what this converts and why it exists.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_met.h"

#include <stddef.h>

#include "gn_met_table.h"

int gn_match_state_is_valid(const GnMatchState *state)
{
    if (state == NULL) {
        return 0;
    }
    if (state->away_on_roll < 1 || state->away_opponent < 1) {
        return 0;
    }
    if (state->away_on_roll > GN_MET_MAX_AWAY ||
        state->away_opponent > GN_MET_MAX_AWAY) {
        return 0;
    }
    /* A cube is a power of two, from 1 up. Anything else is a caller error,
     * and silently accepting it would scale every outcome wrongly. */
    if (state->cube < 1 || (state->cube & (state->cube - 1)) != 0) {
        return 0;
    }
    return 1;
}

double gn_met_pre(int away_a, int away_b)
{
    if (away_a < 1 || away_b < 1 ||
        away_a > GN_MET_MAX_AWAY || away_b > GN_MET_MAX_AWAY) {
        return -1.0;
    }
    return GN_MET_PRE[away_a - 1][away_b - 1];
}

double gn_met_post(int away_trailer)
{
    if (away_trailer < 1 || away_trailer > GN_MET_POST_SIZE) {
        return -1.0;
    }
    return GN_MET_POST[away_trailer - 1];
}

double gn_met_after(const GnMatchState *state, int points, int on_roll_wins)
{
    if (!gn_match_state_is_valid(state) || points < 1) {
        return -1.0;
    }

    /* Away scores AFTER the game. Only the winner's decreases. */
    int mine = state->away_on_roll;
    int theirs = state->away_opponent;
    if (on_roll_wins) {
        mine -= points;
    } else {
        theirs -= points;
    }

    /* The match is over. No table to consult -- these are certainties. */
    if (mine <= 0) {
        return 1.0;
    }
    if (theirs <= 0) {
        return 0.0;
    }

    /*
     * Post-Crawford applies once the Crawford game has been played -- either
     * because the game just evaluated WAS it, or because a player was already
     * at match point when it started, which means Crawford is behind us.
     *
     * The two are genuinely different situations and produce the same answer
     * here, which is why they share a branch; conflating them in the caller's
     * head is another matter, hence the comment.
     */
    const int crawford_is_behind_us =
        state->crawford ||
        state->away_on_roll == 1 ||
        state->away_opponent == 1;

    if (crawford_is_behind_us) {
        if (mine == 1) {
            /* We lead at match point; they trail by `theirs`. The table gives
             * the TRAILER's chance, so ours is its complement. */
            const double trailer = gn_met_post(theirs);
            return (trailer < 0.0) ? -1.0 : 1.0 - trailer;
        }
        if (theirs == 1) {
            const double trailer = gn_met_post(mine);
            return (trailer < 0.0) ? -1.0 : trailer;
        }
        /*
         * Neither side is at match point after the game, yet Crawford is
         * behind us: an ordinary post-Crawford position, which the
         * pre-Crawford table describes correctly. The free drop that makes
         * post-Crawford asymmetric only exists while one side is 1-away.
         */
    }

    return gn_met_pre(mine, theirs);
}

double gn_match_winning_chance(const GnMatchState *state,
                               const float probs[GN_NUM_OUTPUTS])
{
    if (!gn_match_state_is_valid(state) || probs == NULL) {
        return -1.0;
    }

    /*
     * Called, not reimplemented. T10 found that subtracting the nested
     * probabilities in double yields P(lose single) = -1.5e-10 on a real
     * position of the corpus -- a negative probability, and this function is
     * precisely where it would have entered a match equity.
     */
    double outcomes[GN_NUM_EXCLUSIVE];
    gn_probs_exclusive(probs, outcomes);

    /* Each outcome, its stake in points, and who collects it. */
    static const int STAKE[GN_NUM_EXCLUSIVE] = {1, 2, 3, 1, 2, 3};
    static const int WE_WIN[GN_NUM_EXCLUSIVE] = {1, 1, 1, 0, 0, 0};

    double total = 0.0;
    for (int i = 0; i < GN_NUM_EXCLUSIVE; i++) {
        if (outcomes[i] == 0.0) {
            continue;
        }
        const double mwc =
            gn_met_after(state, STAKE[i] * state->cube, WE_WIN[i]);
        if (mwc < 0.0) {
            return -1.0;
        }
        total += outcomes[i] * mwc;
    }
    return total;
}

double gn_match_equity(const GnMatchState *state,
                       const float probs[GN_NUM_OUTPUTS])
{
    const double mwc = gn_match_winning_chance(state, probs);
    return (mwc < 0.0) ? -2.0 : 2.0 * mwc - 1.0;
}

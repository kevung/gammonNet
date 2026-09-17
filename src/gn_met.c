/*
 * gn_met.c -- see gn_met.h for what this converts and why it exists.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_met.h"

#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>

#include "gn_met_table.h"

/* ── The active table ─────────────────────────────────────────────────
 *
 * Pointers, not a copy: the default costs nothing and stays `const`. A table
 * installed at runtime lands in the two buffers below and the pointers move.
 */

#define GN_MET_NAME_MAX 64
#define GN_MET_MAGIC    "GNMET1\0\0"

static const double *g_pre = &GN_MET_PRE[0][0];
static const double *g_post = GN_MET_POST;
static char g_name[GN_MET_NAME_MAX] = "kazaross-xg2";

static double g_loaded_pre[GN_MET_SIZE * GN_MET_SIZE];
static double g_loaded_post[GN_MET_POST_SIZE];

/* A match winning chance outside [0, 1] is not a rounding accident. NaN
 * compares false against everything, which is why the test has this shape
 * rather than the two rejections spelled out. */
static int is_a_chance(double value)
{
    return (value >= 0.0 && value <= 1.0);
}

int gn_met_set(const double *pre, int pre_size,
               const double *post, int post_size, const char *name)
{
    if (pre == NULL || post == NULL) {
        return -1;
    }
    if (pre_size != GN_MET_SIZE || post_size != GN_MET_POST_SIZE) {
        return -2;
    }
    for (int i = 0; i < pre_size * pre_size; i++) {
        if (!is_a_chance(pre[i])) {
            return -3;
        }
    }
    for (int i = 0; i < post_size; i++) {
        if (!is_a_chance(post[i])) {
            return -3;
        }
    }

    memcpy(g_loaded_pre, pre, sizeof(double) * (size_t)(pre_size * pre_size));
    memcpy(g_loaded_post, post, sizeof(double) * (size_t)post_size);
    g_pre = g_loaded_pre;
    g_post = g_loaded_post;

    snprintf(g_name, sizeof(g_name), "%s", name != NULL ? name : "unnamed");
    return 0;
}

int gn_met_load(const char *path)
{
    if (path == NULL) {
        return -1;
    }

    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return -1;
    }

    char magic[8];
    int32_t sizes[2];
    char name[GN_MET_NAME_MAX];
    double pre[GN_MET_SIZE * GN_MET_SIZE];
    double post[GN_MET_POST_SIZE];
    int status = -4;

    if (fread(magic, 1, sizeof(magic), file) != sizeof(magic) ||
        memcmp(magic, GN_MET_MAGIC, sizeof(magic)) != 0) {
        status = -5;
        goto done;
    }
    if (fread(sizes, sizeof(int32_t), 2, file) != 2) {
        goto done;
    }
    if (sizes[0] != GN_MET_SIZE || sizes[1] != GN_MET_POST_SIZE) {
        status = -2;
        goto done;
    }
    if (fread(name, 1, sizeof(name), file) != sizeof(name)) {
        goto done;
    }
    name[sizeof(name) - 1] = '\0';

    const size_t pre_count = (size_t)(sizes[0] * sizes[0]);
    if (fread(pre, sizeof(double), pre_count, file) != pre_count) {
        goto done;
    }
    if (fread(post, sizeof(double), (size_t)sizes[1], file) != (size_t)sizes[1]) {
        goto done;
    }

    status = gn_met_set(pre, sizes[0], post, sizes[1], name);

done:
    fclose(file);
    return status;
}

void gn_met_reset(void)
{
    g_pre = &GN_MET_PRE[0][0];
    g_post = GN_MET_POST;
    snprintf(g_name, sizeof(g_name), "%s", "kazaross-xg2");
}

const char *gn_met_name(void)
{
    return g_name;
}

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

GnMatchState gn_match_state_swap(GnMatchState state)
{
    const int mine = state.away_on_roll;
    state.away_on_roll = state.away_opponent;
    state.away_opponent = mine;
    return state;
}

double gn_met_pre(int away_a, int away_b)
{
    if (away_a < 1 || away_b < 1 ||
        away_a > GN_MET_MAX_AWAY || away_b > GN_MET_MAX_AWAY) {
        return -1.0;
    }
    return g_pre[(away_a - 1) * GN_MET_SIZE + (away_b - 1)];
}

double gn_met_post(int away_trailer)
{
    if (away_trailer < 1 || away_trailer > GN_MET_POST_SIZE) {
        return -1.0;
    }
    return g_post[away_trailer - 1];
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

/*
 * gn_encoding.c -- the 196-feature codec. See gn_encoding.h before editing.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_encoding.h"

#include <math.h>
#include <string.h>

/*
 * Scales, written the way `encoding.py` writes them.
 *
 * The arithmetic type matters and is not a detail. numpy evaluates
 * `off * (1.0 / 15)` in DOUBLE and then rounds the result into a float32 array.
 * Computing the same product in float32 throughout gives a different last bit
 * for some counts — and T02 demands `max|Δ| = 0`, not "close enough". So every
 * product below is formed in double and cast once, at the end.
 */
#define GN_BAR_SCALE 0.5
#define GN_OFF_SCALE (1.0 / 15.0)

/* ── Encoding ───────────────────────────────────────────────────────── */

/* The 4-unit thermometer of `_encode_checkers`: 1, 2, 3, then (n-3)/2. */
static void encode_checkers(float *x, int offset, int count)
{
    if (count >= 1)
        x[offset] = 1.0f;
    if (count >= 2)
        x[offset + 1] = 1.0f;
    if (count >= 3) {
        x[offset + 2] = 1.0f;
        if (count >= 4)
            x[offset + 3] = (float) ((count - 3) * 0.5);
    }
}

int gn_encode(const GnPosition *pos, float *out)
{
    int me, opponent;
    int i;

    if (!gn_position_is_valid(pos))
        return -1;

    memset(out, 0, GN_NUM_FEATURES * sizeof(float));

    me = pos->turn;
    opponent = (me == GN_WHITE) ? GN_BLACK : GN_WHITE;

    for (i = 0; i < GN_NUM_POINTS; i++) {
        int n = pos->points[i];
        int count;
        int slot;

        if (n == 0)
            continue;

        /*
         * `slot` is where this physical point lands in the feature vector.
         * WHITE reads the board in index order; BLACK reads it mirrored, so
         * that its home board occupies the same features as WHITE's does. Get
         * this backwards and nothing crashes — the evaluations simply stop
         * meaning what they say.
         */
        slot = (me == GN_WHITE) ? i : (GN_NUM_POINTS - 1 - i);

        if ((n > 0) == (me == GN_WHITE)) {
            count = (n > 0) ? n : -n;
            encode_checkers(out, GN_MY_BLOCK_OFFSET + slot * GN_FEATURES_PER_POINT, count);
        } else {
            count = (n > 0) ? n : -n;
            encode_checkers(out, GN_OPP_BLOCK_OFFSET + slot * GN_FEATURES_PER_POINT, count);
        }
    }

    out[GN_MY_BAR_INDEX] = (float) (pos->bar[me] * GN_BAR_SCALE);
    out[GN_MY_OFF_INDEX] = (float) (pos->off[me] * GN_OFF_SCALE);
    out[GN_OPP_BAR_INDEX] = (float) (pos->bar[opponent] * GN_BAR_SCALE);
    out[GN_OPP_OFF_INDEX] = (float) (pos->off[opponent] * GN_OFF_SCALE);

    return 0;
}

/* ── Decoding ───────────────────────────────────────────────────────── */

/*
 * Invert the thermometer. Returns the checker count, or -1 if the four units
 * are not a shape the encoder could have produced — a lit unit above an unlit
 * one, or a fourth unit that is not a whole number of halves.
 */
static int decode_checkers(const float *x, int offset)
{
    float u0 = x[offset], u1 = x[offset + 1], u2 = x[offset + 2], u3 = x[offset + 3];
    int extra;

    if (u0 == 0.0f)
        return (u1 == 0.0f && u2 == 0.0f && u3 == 0.0f) ? 0 : -1;
    if (u0 != 1.0f)
        return -1;

    if (u1 == 0.0f)
        return (u2 == 0.0f && u3 == 0.0f) ? 1 : -1;
    if (u1 != 1.0f)
        return -1;

    if (u2 == 0.0f)
        return (u3 == 0.0f) ? 2 : -1;
    if (u2 != 1.0f)
        return -1;

    if (u3 == 0.0f)
        return 3;
    if (u3 < 0.0f)
        return -1;

    /* u3 = (count - 3) * 0.5, so count = 3 + 2 * u3, and 2 * u3 must be whole. */
    extra = (int) lrintf(u3 * 2.0f);
    if ((float) (extra * 0.5) != u3)
        return -1;

    return 3 + extra;
}

/* Recover a small non-negative count from `value = count * scale`. */
static int decode_scaled(float value, double scale, int max)
{
    int count;

    if (value < 0.0f)
        return -1;

    count = (int) lrint((double) value / scale);
    if (count < 0 || count > max)
        return -1;

    /* Re-encode and demand the exact same float back: anything else was not
     * produced by this encoder. */
    if ((float) (count * scale) != value)
        return -1;

    return count;
}

int gn_decode(const float *features, int turn, GnPosition *out)
{
    int me, opponent;
    int slot;
    int bar_me, off_me, bar_opp, off_opp;

    if (turn != GN_WHITE && turn != GN_BLACK)
        return -1;

    me = turn;
    opponent = (me == GN_WHITE) ? GN_BLACK : GN_WHITE;

    memset(out, 0, sizeof(*out));
    out->turn = (unsigned char) turn;

    for (slot = 0; slot < GN_NUM_POINTS; slot++) {
        int mine = decode_checkers(features, GN_MY_BLOCK_OFFSET + slot * GN_FEATURES_PER_POINT);
        int theirs = decode_checkers(features, GN_OPP_BLOCK_OFFSET + slot * GN_FEATURES_PER_POINT);
        int index;

        if (mine < 0 || theirs < 0)
            return -1;
        if (mine && theirs)
            return -1; /* one colour per point */

        /* Undo the mirroring applied by gn_encode. */
        index = (me == GN_WHITE) ? slot : (GN_NUM_POINTS - 1 - slot);

        if (mine)
            out->points[index] = (signed char) ((me == GN_WHITE) ? mine : -mine);
        else if (theirs)
            out->points[index] = (signed char) ((opponent == GN_WHITE) ? theirs : -theirs);
    }

    bar_me = decode_scaled(features[GN_MY_BAR_INDEX], GN_BAR_SCALE, GN_NUM_CHECKERS);
    off_me = decode_scaled(features[GN_MY_OFF_INDEX], GN_OFF_SCALE, GN_NUM_CHECKERS);
    bar_opp = decode_scaled(features[GN_OPP_BAR_INDEX], GN_BAR_SCALE, GN_NUM_CHECKERS);
    off_opp = decode_scaled(features[GN_OPP_OFF_INDEX], GN_OFF_SCALE, GN_NUM_CHECKERS);

    if (bar_me < 0 || off_me < 0 || bar_opp < 0 || off_opp < 0)
        return -1;

    out->bar[me] = (unsigned char) bar_me;
    out->off[me] = (unsigned char) off_me;
    out->bar[opponent] = (unsigned char) bar_opp;
    out->off[opponent] = (unsigned char) off_opp;

    return gn_position_is_valid(out) ? 0 : -1;
}

/* ── The pip sentinel, read from the vector ─────────────────────────── */

int gn_pip_count_from_features(const float *features, int side)
{
    int block, bar_index;
    int pips = 0;
    int slot;
    int bar;

    if (side == GN_SIDE_ON_ROLL) {
        block = GN_MY_BLOCK_OFFSET;
        bar_index = GN_MY_BAR_INDEX;
    } else if (side == GN_SIDE_OPPONENT) {
        block = GN_OPP_BLOCK_OFFSET;
        bar_index = GN_OPP_BAR_INDEX;
    } else {
        return -1;
    }

    /*
     * BOTH blocks use the on-roll player's board orientation — the opponent
     * block is NOT written from the opponent's own point of view. So slot s
     * denotes the same physical point in either block, and that point is
     * (s + 1) pips from home for the on-roll player but (24 - s) pips from
     * home for the opponent, who travels the other way.
     *
     * Reading the opponent's pips as (s + 1) is a mistake that costs nothing
     * visible: it yields a plausible number for every position, and it happens
     * to be right on any position symmetric enough to look like a sanity check.
     */
    for (slot = 0; slot < GN_NUM_POINTS; slot++) {
        int count = decode_checkers(features, block + slot * GN_FEATURES_PER_POINT);

        if (count < 0)
            return -1;
        pips += count * ((side == GN_SIDE_ON_ROLL) ? (slot + 1) : (GN_NUM_POINTS - slot));
    }

    bar = decode_scaled(features[bar_index], GN_BAR_SCALE, GN_NUM_CHECKERS);
    if (bar < 0)
        return -1;

    return pips + bar * 25;
}

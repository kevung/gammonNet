/*
 * gn_position_id.c -- Position ID and XGID. See gn_position_id.h first.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_position_id.h"

#include <stdio.h>
#include <string.h>

/* ── GNU Backgammon Position ID ─────────────────────────────────────── */

/*
 * The key is 80 bits. For each of the two players, for each of 25 slots (24
 * points then the bar), write as many 1 bits as there are checkers, then a
 * single 0 bit. The opponent's half comes first. Bits fill each byte from its
 * least significant end.
 *
 * Slots are SELF-RELATIVE: slot s of a player's half holds the checkers that
 * are (s + 1) pips from bearing off FOR THAT PLAYER. The two halves therefore
 * run in opposite directions across the physical board.
 */

/*
 * Sized 65 rather than 64 so the string literal keeps its terminating NUL.
 * Declared [64] the initialiser exactly fills the array and the NUL is dropped,
 * which GCC 15 and later report (-Wunterminated-string-initialization). Only
 * the first 64 bytes are ever read, so the truncation was harmless — but this
 * repository holds its own sources to compiler silence, and the warning is
 * invisible on a machine with an older compiler.
 */
static const char BASE64[65] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static int base64_value(char c)
{
    const char *p = memchr(BASE64, c, 64);

    return p ? (int) (p - BASE64) : -1;
}

/* Fill `half[25]` with `player`'s checkers, in that player's own slot order. */
static void self_relative_half(const GnPosition *pos, int player, int *half)
{
    int i;

    memset(half, 0, 25 * sizeof(int));

    for (i = 0; i < GN_NUM_POINTS; i++) {
        int n = pos->points[i];

        if (player == GN_WHITE && n > 0) {
            /* Index i is WHITE's point (i + 1), so WHITE's slot is i. */
            half[i] = n;
        } else if (player == GN_BLACK && n < 0) {
            /* Index i is BLACK's point (24 - i), so BLACK's slot is 23 - i. */
            half[GN_NUM_POINTS - 1 - i] = -n;
        }
    }

    half[24] = pos->bar[player];
}

int gn_position_id(const GnPosition *pos, char *out)
{
    unsigned char key[10];
    int halves[2][25];
    int me, opponent;
    unsigned int bit = 0;
    int side, slot, k;

    if (!gn_position_is_valid(pos))
        return -1;

    me = pos->turn;
    opponent = (me == GN_WHITE) ? GN_BLACK : GN_WHITE;

    self_relative_half(pos, opponent, halves[0]);
    self_relative_half(pos, me, halves[1]);

    memset(key, 0, sizeof(key));

    for (side = 0; side < 2; side++) {
        for (slot = 0; slot < 25; slot++) {
            int n;

            for (n = 0; n < halves[side][slot]; n++) {
                if (bit >= 80)
                    return -1;
                key[bit / 8] |= (unsigned char) (1u << (bit % 8));
                bit++;
            }
            bit++; /* the terminating zero */
            if (bit > 80)
                return -1;
        }
    }

    /* Base64 of ten bytes: three full triples, then the remaining byte. */
    for (k = 0; k < 3; k++) {
        const unsigned char *p = key + k * 3;

        out[k * 4 + 0] = BASE64[p[0] >> 2];
        out[k * 4 + 1] = BASE64[((p[0] & 0x03) << 4) | (p[1] >> 4)];
        out[k * 4 + 2] = BASE64[((p[1] & 0x0F) << 2) | (p[2] >> 6)];
        out[k * 4 + 3] = BASE64[p[2] & 0x3F];
    }
    out[12] = BASE64[key[9] >> 2];
    out[13] = BASE64[(key[9] & 0x03) << 4];
    out[14] = '\0';

    return 0;
}

int gn_position_from_id(const char *id, int turn, GnPosition *out)
{
    unsigned char key[10];
    int halves[2][25];
    unsigned int bit = 0;
    int me, opponent;
    int side, slot, i;

    if (turn != GN_WHITE && turn != GN_BLACK)
        return -1;
    if (!id || strlen(id) != 14)
        return -1;

    /*
     * Two different bit orders meet here, and they are not interchangeable.
     * The key packs its checker bits from the LEAST significant end of each
     * byte; base64 packs six-bit groups from the MOST significant end. So undo
     * the base64 first, byte by byte, and only then walk the key's own bits.
     */
    {
        int v[14];

        for (i = 0; i < 14; i++) {
            v[i] = base64_value(id[i]);
            if (v[i] < 0)
                return -1;
        }

        for (i = 0; i < 3; i++) {
            const int *g = v + i * 4;
            unsigned char *p = key + i * 3;

            p[0] = (unsigned char) ((g[0] << 2) | (g[1] >> 4));
            p[1] = (unsigned char) (((g[1] & 0x0F) << 4) | (g[2] >> 2));
            p[2] = (unsigned char) (((g[2] & 0x03) << 6) | g[3]);
        }
        key[9] = (unsigned char) ((v[12] << 2) | (v[13] >> 4));

        /* The identifier carries 84 bits for 80 bits of key. The four spare
         * bits are padding and must be zero; anything else is not an
         * identifier this encoder could have produced. */
        if (v[13] & 0x0F)
            return -1;
    }

    memset(halves, 0, sizeof(halves));
    for (side = 0; side < 2; side++) {
        for (slot = 0; slot < 25; slot++) {
            int count = 0;

            while (bit < 80 && (key[bit / 8] & (1u << (bit % 8)))) {
                count++;
                bit++;
                if (count > GN_NUM_CHECKERS)
                    return -1;
            }
            bit++; /* the terminating zero */
            halves[side][slot] = count;
        }
    }

    me = turn;
    opponent = (me == GN_WHITE) ? GN_BLACK : GN_WHITE;

    memset(out, 0, sizeof(*out));
    out->turn = (unsigned char) turn;

    for (slot = 0; slot < GN_NUM_POINTS; slot++) {
        int mine = halves[1][slot];
        int theirs = halves[0][slot];
        int index;

        if (mine) {
            index = (me == GN_WHITE) ? slot : (GN_NUM_POINTS - 1 - slot);
            if (out->points[index])
                return -1;
            out->points[index] = (signed char) ((me == GN_WHITE) ? mine : -mine);
        }
        if (theirs) {
            index = (opponent == GN_WHITE) ? slot : (GN_NUM_POINTS - 1 - slot);
            if (out->points[index])
                return -1;
            out->points[index] = (signed char) ((opponent == GN_WHITE) ? theirs : -theirs);
        }
    }

    out->bar[me] = (unsigned char) halves[1][24];
    out->bar[opponent] = (unsigned char) halves[0][24];

    /* Borne-off checkers are implied by the fifteen that are not on the board. */
    out->off[me] = (unsigned char) (GN_NUM_CHECKERS - gn_position_checker_count(out, me));
    out->off[opponent] =
        (unsigned char) (GN_NUM_CHECKERS - gn_position_checker_count(out, opponent));

    return gn_position_is_valid(out) ? 0 : -1;
}

/* ── XGID ───────────────────────────────────────────────────────────── */

int gn_position_from_xgid(const char *xgid, GnPosition *out, GnXgidFields *fields)
{
    GnXgidFields parsed;
    const char *board;
    char dice[8] = {0};
    int i;

    if (!xgid)
        return -1;
    if (strncmp(xgid, "XGID=", 5) == 0)
        xgid += 5;
    board = xgid;

    if (strlen(board) < 26 || board[26] != ':')
        return -1;

    memset(&parsed, 0, sizeof(parsed));
    memset(out, 0, sizeof(*out));

    for (i = 0; i < 26; i++) {
        char c = board[i];
        int count;
        int index;

        if (c == '-')
            continue;

        if (c >= 'A' && c <= 'O') {
            count = c - 'A' + 1;
            if (i == 0)
                return -1; /* slot 0 belongs to the lowercase player's bar */
            if (i == 25) {
                out->bar[GN_WHITE] = (unsigned char) count;
                continue;
            }
            index = i - 1;
            out->points[index] = (signed char) count;
        } else if (c >= 'a' && c <= 'o') {
            count = c - 'a' + 1;
            if (i == 25)
                return -1; /* slot 25 belongs to the uppercase player's bar */
            if (i == 0) {
                out->bar[GN_BLACK] = (unsigned char) count;
                continue;
            }
            index = i - 1;
            out->points[index] = (signed char) -count;
        } else {
            return -1;
        }
    }

    if (sscanf(board + 27, "%d:%d:%d:%7[^:]:%d:%d:%d:%d:%d",
               &parsed.cube_power, &parsed.cube_owner, &parsed.turn, dice,
               &parsed.score_upper, &parsed.score_lower, &parsed.flags,
               &parsed.match_length, &parsed.max_cube) != 9)
        return -1;

    if (strlen(dice) >= 2 && dice[0] >= '0' && dice[0] <= '6'
        && dice[1] >= '0' && dice[1] <= '6') {
        parsed.die1 = dice[0] - '0';
        parsed.die2 = dice[1] - '0';
    }

    /* +1 is the uppercase player, -1 the lowercase one. */
    out->turn = (unsigned char) ((parsed.turn < 0) ? GN_BLACK : GN_WHITE);

    out->off[GN_WHITE] =
        (unsigned char) (GN_NUM_CHECKERS - gn_position_checker_count(out, GN_WHITE));
    out->off[GN_BLACK] =
        (unsigned char) (GN_NUM_CHECKERS - gn_position_checker_count(out, GN_BLACK));

    if (fields)
        *fields = parsed;

    return gn_position_is_valid(out) ? 0 : -1;
}

int gn_xgid(const GnPosition *pos, const GnXgidFields *fields, char *out)
{
    GnXgidFields f;
    char board[27];
    int i;

    if (!gn_position_is_valid(pos))
        return -1;

    if (fields) {
        f = *fields;
    } else {
        memset(&f, 0, sizeof(f));
        f.turn = (pos->turn == GN_WHITE) ? 1 : -1;
        f.max_cube = 10;
    }

    for (i = 0; i < 26; i++)
        board[i] = '-';
    board[26] = '\0';

    for (i = 0; i < GN_NUM_POINTS; i++) {
        int n = pos->points[i];

        if (n > 0)
            board[i + 1] = (char) ('A' + n - 1);
        else if (n < 0)
            board[i + 1] = (char) ('a' - n - 1);
    }

    if (pos->bar[GN_BLACK])
        board[0] = (char) ('a' + pos->bar[GN_BLACK] - 1);
    if (pos->bar[GN_WHITE])
        board[25] = (char) ('A' + pos->bar[GN_WHITE] - 1);

    if (snprintf(out, GN_XGID_LENGTH, "XGID=%s:%d:%d:%d:%d%d:%d:%d:%d:%d:%d",
                 board, f.cube_power, f.cube_owner, f.turn, f.die1, f.die2,
                 f.score_upper, f.score_lower, f.flags, f.match_length,
                 f.max_cube) >= GN_XGID_LENGTH)
        return -1;

    return 0;
}

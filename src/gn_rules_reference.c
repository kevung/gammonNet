/*
 * gn_rules_reference.c -- gn_rules.h implemented on the reference rules engine.
 *
 * The backend is alexstrehl/backgammon-ai-engine's `c_engine/bg_engine.c`
 * (MIT, pinned in tools/fetch_vendor.py, recorded in THIRD-PARTY.md). It is
 * reused rather than rewritten because it is already in agreement with the
 * 196-feature encoding the network expects; writing a second rules engine would
 * add a way to disagree with the network and buy nothing.
 *
 * Everything backend-specific lives in this file. `gn_rules.h` names none of it.
 *
 * The two representations agree on their conventions today — signed points with
 * WHITE bearing off towards index 0 — but the conversions below are written out
 * field by field on purpose. An agreement that holds by coincidence should not
 * be load-bearing, and a struct copy would keep working right up until the day
 * the backend changed a field.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_rules.h"

#include <string.h>

#include "bg_engine.h"

/* Compile-time agreement on the shared constants. If the backend ever changes
 * one of these, this file must fail to build rather than quietly disagree. */
#if GN_NUM_POINTS != NUM_POINTS
#error "gn_rules.h and bg_engine.h disagree on the number of points"
#endif
#if GN_MAX_MOVES_PER_PLAY != MAX_MOVES_PER_PLAY
#error "gn_rules.h and bg_engine.h disagree on the sub-moves per play"
#endif
#if GN_WHITE != WHITE || GN_BLACK != BLACK
#error "gn_rules.h and bg_engine.h disagree on the player codes"
#endif

/* C11 thread-local storage where available. Without it the scratch buffer below
 * is shared, which is safe only single-threaded — hence the loud fallback. */
#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L && !defined(__STDC_NO_THREADS__)
#define GN_THREAD_LOCAL _Thread_local
#elif defined(__GNUC__)
#define GN_THREAD_LOCAL __thread
#else
#define GN_THREAD_LOCAL
#warning "no thread-local storage: gn_legal_plays is not safe to call concurrently"
#endif

/* ── Conversions ────────────────────────────────────────────────────── */

static void to_backend(const GnPosition *pos, BoardState *out)
{
    int i;

    for (i = 0; i < GN_NUM_POINTS; i++)
        out->points[i] = pos->points[i];

    out->bar[GN_WHITE] = pos->bar[GN_WHITE];
    out->bar[GN_BLACK] = pos->bar[GN_BLACK];
    out->off[GN_WHITE] = pos->off[GN_WHITE];
    out->off[GN_BLACK] = pos->off[GN_BLACK];
    out->turn = pos->turn;
}

static void from_backend(const BoardState *state, GnPosition *out)
{
    int i;

    for (i = 0; i < GN_NUM_POINTS; i++)
        out->points[i] = (signed char) state->points[i];

    out->bar[GN_WHITE] = (unsigned char) state->bar[GN_WHITE];
    out->bar[GN_BLACK] = (unsigned char) state->bar[GN_BLACK];
    out->off[GN_WHITE] = (unsigned char) state->off[GN_WHITE];
    out->off[GN_BLACK] = (unsigned char) state->off[GN_BLACK];
    out->turn = (unsigned char) state->turn;
}

/* The backend uses the same sentinel values; map them explicitly anyway. */
static signed char move_endpoint(int backend_value)
{
    if (backend_value == BAR_SENTINEL)
        return GN_BAR;
    if (backend_value == OFF_SENTINEL)
        return GN_OFF;
    return (signed char) backend_value;
}

/* ── Position queries ───────────────────────────────────────────────── */

void gn_position_initial(GnPosition *out)
{
    BoardState state;

    board_init(&state);
    from_backend(&state, out);
}

int gn_position_pip_count(const GnPosition *pos, int player)
{
    int pips = 0;
    int i;

    if (player != GN_WHITE && player != GN_BLACK)
        return -1;

    for (i = 0; i < GN_NUM_POINTS; i++) {
        int n = pos->points[i];

        if (player == GN_WHITE && n > 0) {
            /* Index i is WHITE's point (i + 1): that many pips left to travel. */
            pips += n * (i + 1);
        } else if (player == GN_BLACK && n < 0) {
            /* Index i is BLACK's point (24 - i). */
            pips += (-n) * (GN_NUM_POINTS - i);
        }
    }

    /* A checker on the bar re-enters on the opponent's home board and has the
     * full 25 pips to travel. */
    pips += pos->bar[player] * 25;

    return pips;
}

int gn_position_checker_count(const GnPosition *pos, int player)
{
    int total = 0;
    int i;

    if (player != GN_WHITE && player != GN_BLACK)
        return -1;

    for (i = 0; i < GN_NUM_POINTS; i++) {
        int n = pos->points[i];

        if (player == GN_WHITE && n > 0)
            total += n;
        else if (player == GN_BLACK && n < 0)
            total += -n;
    }

    return total + pos->bar[player] + pos->off[player];
}

int gn_position_is_valid(const GnPosition *pos)
{
    int i;

    if (pos->turn != GN_WHITE && pos->turn != GN_BLACK)
        return 0;

    for (i = 0; i < GN_NUM_POINTS; i++) {
        int n = pos->points[i];

        if (n > GN_NUM_CHECKERS || n < -GN_NUM_CHECKERS)
            return 0;
    }

    if (pos->bar[GN_WHITE] > GN_NUM_CHECKERS || pos->bar[GN_BLACK] > GN_NUM_CHECKERS)
        return 0;
    if (pos->off[GN_WHITE] > GN_NUM_CHECKERS || pos->off[GN_BLACK] > GN_NUM_CHECKERS)
        return 0;

    if (gn_position_checker_count(pos, GN_WHITE) != GN_NUM_CHECKERS)
        return 0;
    if (gn_position_checker_count(pos, GN_BLACK) != GN_NUM_CHECKERS)
        return 0;

    return 1;
}

int gn_position_is_over(const GnPosition *pos)
{
    return pos->off[GN_WHITE] == GN_NUM_CHECKERS
        || pos->off[GN_BLACK] == GN_NUM_CHECKERS;
}

int gn_position_winner(const GnPosition *pos)
{
    if (pos->off[GN_WHITE] == GN_NUM_CHECKERS)
        return GN_WHITE;
    if (pos->off[GN_BLACK] == GN_NUM_CHECKERS)
        return GN_BLACK;
    return -1;
}

void gn_position_swap_turn(GnPosition *pos)
{
    pos->turn = (unsigned char) (pos->turn == GN_WHITE ? GN_BLACK : GN_WHITE);
}

/* ── Legal play generation ──────────────────────────────────────────── */

int gn_legal_plays(const GnPosition *pos, int d1, int d2,
                   GnPlay *out_plays, int max_plays)
{
    /* Scratch for the backend's own Play layout. Thread-local: the round-robin
     * harness runs one generator per core, and a shared static would corrupt
     * every one of them at once — silently, since each thread would still get a
     * well-formed list of somebody's legal plays. */
    static GN_THREAD_LOCAL Play backend_plays[GN_MAX_PLAYS];
    BoardState state;
    int count;
    int i;
    int m;

    if (!gn_position_is_valid(pos))
        return -1;
    if (d1 < 1 || d1 > 6 || d2 < 1 || d2 > 6)
        return -1;
    if (max_plays <= 0)
        return -1;

    to_backend(pos, &state);

    count = get_legal_plays(&state, d1, d2, backend_plays, GN_MAX_PLAYS);
    if (count < 0)
        return -1;

    /*
     * The backend drops plays past its buffer without saying so (bg_engine.c:864
     * appends only `if (ctx->count < ctx->max_plays)`), so a full buffer cannot
     * be told apart from a position that happens to have exactly that many
     * plays. Treat a full buffer as failure. Refusing a position that genuinely
     * had GN_MAX_PLAYS of them is the cheap error; returning a search that never
     * saw the moves it was missing is the expensive one.
     */
    if (count >= GN_MAX_PLAYS)
        return -1;

    if (count > max_plays)
        return -1;

    for (i = 0; i < count; i++) {
        const Play *src = &backend_plays[i];
        GnPlay *dst = &out_plays[i];

        dst->num_moves = src->num_moves;
        for (m = 0; m < GN_MAX_MOVES_PER_PLAY; m++) {
            if (m < src->num_moves) {
                dst->moves[m].from = move_endpoint(src->moves[m].src);
                dst->moves[m].to = move_endpoint(src->moves[m].dst);
            } else {
                dst->moves[m].from = 0;
                dst->moves[m].to = 0;
            }
        }

        /* The backend already switched the turn on every resulting state. */
        from_backend(&src->resulting_state, &dst->result);
    }

    return count;
}

/*
 * gn_rules.h -- gammonNet position representation and legal play generation.
 *
 * This is gammonNet's OWN interface. Its implementation currently delegates to
 * the rules engine of alexstrehl/backgammon-ai-engine (MIT, see THIRD-PARTY.md),
 * which is already in agreement with the encoding the network expects. Nothing
 * above this header knows that. Swapping the backend means rewriting one .c file.
 *
 * This header knows nothing about evaluation, search, or the cube. A position
 * goes in, its legal successors come out.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_RULES_H
#define GN_RULES_H

#ifdef __cplusplus
extern "C" {
#endif

/* ── Constants ──────────────────────────────────────────────────────── */

#define GN_WHITE 0
#define GN_BLACK 1

#define GN_NUM_POINTS   24
#define GN_NUM_CHECKERS 15

/* A play is at most four sub-moves (doubles). */
#define GN_MAX_MOVES_PER_PLAY 4

/*
 * Capacity of a legal-play buffer.
 *
 * This is a working bound, not a proven one. The largest count observed over
 * the T01 corpus is recorded in docs/mesures/ ; the margin here is wide enough
 * that reaching it means something is wrong. gn_legal_plays REFUSES at capacity
 * rather than returning a truncated list — see its contract below.
 */
#define GN_MAX_PLAYS 2048

/* Sentinels used in GnMove.from / GnMove.to. */
#define GN_BAR (-1)
#define GN_OFF (-2)

/* ── Position ───────────────────────────────────────────────────────── */

/*
 * THE CONVENTION. Read this before touching anything that produces or consumes
 * a GnPosition — a mistake here does not crash, it produces plausible and wrong
 * results, and it poisons every measurement downstream.
 *
 *   points[i]        a SIGNED checker count. Positive is that many WHITE
 *                    checkers on the point, negative that many BLACK checkers,
 *                    zero is empty. A point never holds both colours.
 *
 *   Index i denotes point (i + 1) for WHITE and point (24 - i) for BLACK.
 *   Equivalently: WHITE bears off towards index 0, BLACK towards index 23.
 *   So index 0 is WHITE's ace point and BLACK's 24 point.
 *
 *   bar[p] / off[p]  checkers of player p on the bar / borne off. Unsigned.
 *
 *   turn             the player who acts NEXT. gn_legal_plays returns successors
 *                    whose turn is already the opponent's, so at a terminal
 *                    position turn names the LOSER.
 *
 * The types are deliberately narrow. A point holds at most 15 checkers, so
 * signed char suffices — and it makes this struct incompatible in layout with
 * the backend's, which forces the adapter to convert field by field instead of
 * silently memcpy-ing two structures that only happen to agree today.
 */
typedef struct {
    signed char points[GN_NUM_POINTS];
    unsigned char bar[2];
    unsigned char off[2];
    unsigned char turn;
} GnPosition;

/* ── Move / Play ────────────────────────────────────────────────────── */

typedef struct {
    signed char from; /* point index 0-23, or GN_BAR */
    signed char to;   /* point index 0-23, or GN_OFF */
} GnMove;

typedef struct {
    GnMove moves[GN_MAX_MOVES_PER_PLAY];
    int num_moves;
    GnPosition result; /* turn already switched to the opponent */
} GnPlay;

/* ── Position queries ───────────────────────────────────────────────── */

/* Standard starting position, WHITE to act. */
void gn_position_initial(GnPosition *out);

/*
 * Pip count for `player`: the number of pips that player must still travel to
 * bear off every checker. A checker on the bar counts 25.
 *
 * This is the project's cheapest sentinel. `BRIEF.md` §6 keeps it for exactly
 * that: if a translated position's pip count is not the one intended, whatever
 * follows is meaningless. Use it whenever a position crosses a format boundary.
 */
int gn_position_pip_count(const GnPosition *pos, int player);

/* Total checkers belonging to `player`, on points, bar and off. Must be 15. */
int gn_position_checker_count(const GnPosition *pos, int player);

/*
 * Structural validity: 15 checkers each, no point holding both colours, no
 * count out of range, turn in {GN_WHITE, GN_BLACK}. Returns 1 if valid.
 *
 * This says nothing about reachability — a position can be structurally valid
 * and unreachable by legal play. It is a guard against corrupt input, not a
 * legality proof.
 */
int gn_position_is_valid(const GnPosition *pos);

/* 1 if a player has borne off all 15 checkers. */
int gn_position_is_over(const GnPosition *pos);

/* GN_WHITE, GN_BLACK, or -1 if the game is not over. */
int gn_position_winner(const GnPosition *pos);

/* Flip whose turn it is, in place. Checkers are untouched. */
void gn_position_swap_turn(GnPosition *pos);

/* ── Legal play generation ──────────────────────────────────────────── */

/*
 * Fill `out_plays` with every distinct legal play for pos->turn given the dice,
 * and return how many there are. Dice are 1-6 and may be equal (doubles, four
 * sub-moves). Returns 0 when the player has no legal play — a real and legal
 * outcome, not an error.
 *
 * Enforces the full rules: entering from the bar first, using as many dice as
 * possible, using the larger die when only one can be played, exact and
 * over-bearing off. Plays that reach the same position by a different order of
 * sub-moves are returned once.
 *
 * Returns -1 if the position is not valid, if the dice are out of range, if
 * `max_plays` is too small, or if generation hit its internal capacity.
 *
 * A truncated list is NEVER returned. This matters more than it looks: the
 * backend engine drops plays past its buffer capacity without any signal, and a
 * silently short list of candidate moves is indistinguishable from a position
 * that genuinely has fewer options — it would simply make the search quietly
 * blind to the moves it never saw. Refused, not approximated.
 */
int gn_legal_plays(const GnPosition *pos, int d1, int d2,
                   GnPlay *out_plays, int max_plays);

#ifdef __cplusplus
}
#endif

#endif /* GN_RULES_H */

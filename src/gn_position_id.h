/*
 * gn_position_id.h -- reading and writing the usual position identifiers.
 *
 * Two formats, and they are NOT verified to the same degree. Say so wherever
 * this matters:
 *
 *   GNU Backgammon Position ID   cross-checked against an independent
 *                                implementation (gnubg-nn) over 10 000
 *                                positions. See docs/mesures/.
 *
 *   XGID                         anchored on the canonical opening identifier
 *                                and on round-trip; no independent
 *                                implementation was available to check it
 *                                against. Treat its orientation as established
 *                                but not oracle-verified.
 *
 * Neither format is reimplemented from anyone's source: both are documented
 * formats, and a format is not a work. GNU Backgammon is used here only as an
 * instrument to check our output, which is what `CLAUDE.md` allows.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_POSITION_ID_H
#define GN_POSITION_ID_H

#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 14 characters plus the terminator. */
#define GN_POSITION_ID_LENGTH 15

/* "XGID=" + 26 board characters + the ten colon-separated fields. */
#define GN_XGID_LENGTH 64

/* ── GNU Backgammon Position ID ─────────────────────────────────────── */

/*
 * Write the Position ID of `pos`, seen by `pos->turn`, into `out`
 * (GN_POSITION_ID_LENGTH bytes). Returns 0, or -1 if the position is invalid.
 *
 * The identifier encodes the checkers only. Whose turn it is, the cube and the
 * score are NOT in it — two positions differing only by the player on roll
 * share an identifier, seen from their respective movers.
 */
int gn_position_id(const GnPosition *pos, char *out);

/*
 * Parse a Position ID into a position with `turn` on roll.
 * Returns 0, or -1 if the identifier is malformed or does not describe a valid
 * position.
 */
int gn_position_from_id(const char *id, int turn, GnPosition *out);

/* ── XGID ───────────────────────────────────────────────────────────── */

/*
 * The fields of an XGID other than the checkers. gammonNet does not act on any
 * of them yet — the cube is T34 and the match score is T32 — but they are
 * carried through parsing and formatting so that an identifier survives a
 * round-trip instead of being silently stripped of half its meaning.
 */
typedef struct {
    int cube_power;    /* cube value as a power of two: 0 means a centred 1 */
    int cube_owner;    /* 1 the uppercase player, -1 the lowercase one, 0 centred */
    int turn;          /* 1 the uppercase player is on roll, -1 the lowercase one */
    int die1, die2;    /* 0 0 when no roll has been made */
    int score_upper;   /* points already scored */
    int score_lower;
    int flags;         /* Crawford / Jacoby, as XG writes it */
    int match_length;  /* 0 for a money game */
    int max_cube;      /* maximum cube power */
} GnXgidFields;

/*
 * Parse an XGID. `fields` may be NULL if only the checkers are wanted.
 *
 * The board maps as follows, established by reproducing the canonical opening
 * identifier point for point against an independent starting position:
 *
 *   board character 0        the lowercase player's bar
 *   board characters 1-24    our point indices 0-23, in order
 *   board character 25       the uppercase player's bar
 *   'A'-'O'                  1-15 checkers of the uppercase player (our WHITE)
 *   'a'-'o'                  1-15 checkers of the lowercase player (our BLACK)
 *   '-'                      an empty point
 *
 * Borne-off checkers are not written in an XGID; they are implied by the
 * fifteen that are not on the board or the bar.
 *
 * Returns 0, or -1 if the identifier is malformed or not a valid position.
 */
int gn_position_from_xgid(const char *xgid, GnPosition *out, GnXgidFields *fields);

/*
 * Write an XGID for `pos` into `out` (GN_XGID_LENGTH bytes). `fields` may be
 * NULL, in which case the non-checker fields describe a cubeless money game
 * with no roll made and the turn taken from `pos->turn`.
 * Returns 0, or -1 if the position is invalid.
 */
int gn_xgid(const GnPosition *pos, const GnXgidFields *fields, char *out);

#ifdef __cplusplus
}
#endif

#endif /* GN_POSITION_ID_H */

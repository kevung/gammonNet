/*
 * gn_bearoff.h -- the exact endgame, consulted instead of estimated (T38).
 *
 * T38 measured what this closes: on bearoff decisions our network alone loses
 * **0,00028 point of equity per decision** against perfect play, while GNU
 * Backgammon loses essentially nothing -- because it consults a table and we do
 * not. That gap is not a modelling problem, it is a missing lookup.
 *
 * ── WHY A TABLE OF EQUITIES CAN ANSWER A QUESTION ABOUT DISTRIBUTIONS ──
 *
 * The rest of this engine speaks in five nested probabilities, never in a
 * scalar: `gn_infer.h` insists on it, and `gn_met.h` explains why -- a match
 * equity needs P(gammon) separately, and a scalar has already thrown it away.
 * A two-sided table gives only an equity, so at first sight it cannot feed match
 * play.
 *
 * It can, and the reason is arithmetic rather than a concession:
 *
 *   The table covers at most `chequers` men on the board per side, out of
 *   fifteen. With `chequers = 11`, EACH SIDE HAS ALREADY BORNE OFF AT LEAST
 *   FOUR. A gammon requires the loser to have borne off none. **So no position
 *   in this table can end in a gammon.**
 *
 * Therefore, in the table's domain, the distribution is fully determined by the
 * equity:
 *
 *   P(gammon) = P(backgammon) = 0   on both sides
 *   equity    = P(win) - P(lose) = 2 P(win) - 1
 *   P(win)    = (equity + 1) / 2
 *
 * This is checked rather than assumed: `gn_bearoff_probs` refuses any position
 * whose checker counts would leave a gammon possible, even if the index would
 * have been in range.
 *
 * ── THE REFUSAL, WHICH IS THE POINT OF THE MODULE ───────────────────
 *
 * `gn_bearoff_probs` returns 1 when the table knows, 0 when it does not, and
 * NEVER a nearby value. A position just outside the domain that quietly
 * received a neighbour's equity would produce a plausible and wrong evaluation
 * -- the exact failure `CLAUDE.md` names. Refused, never approximated.
 *
 * ── PROVENANCE ──────────────────────────────────────────────────────
 *
 * The file format and the position indexing were established WITHOUT reading
 * any GNU Backgammon source: from the arithmetic of the file, from
 * `bearoffdump` (a documented tool shipped with gnubg), and by validating the
 * index exhaustively against gnubg over all 12 376 positions. See
 * `python/gammonnet/bearoff.py` and the register in `docs/etudes/`.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_BEAROFF_H
#define GN_BEAROFF_H

#include "gn_infer.h"
#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct GnBearoff GnBearoff;

/*
 * Open a two-sided database. Returns NULL if the file is absent, is not a
 * `gnubg-TS` database, or if its size does not match the header it declares --
 * a file read with the wrong stride yields plausible equities from end to end,
 * so the size check is a correctness control and not a formality.
 *
 * The file is memory-mapped, not read: it is 1.2 GiB, and a measurement that
 * touches a small part of the domain should not pay for the rest.
 */
GnBearoff *gn_bearoff_open(const char *path);
void gn_bearoff_close(GnBearoff *table);

/* Points and checkers the database covers, as declared by its own header. */
int gn_bearoff_points(const GnBearoff *table);
int gn_bearoff_chequers(const GnBearoff *table);

/*
 * Whether the table knows this position. A predicate, tested, never assumed.
 *
 * Requires: the game is not over, nobody is on the bar, every remaining checker
 * of each side is within its first `points` points, and neither side has more
 * than `chequers` on the board.
 */
int gn_bearoff_contains(const GnBearoff *table, const GnPosition *pos);

/*
 * The exact distribution, from `pos->turn`'s point of view.
 *
 * Returns 1 and fills `probs` when the table knows the position, 0 when it does
 * not -- and then `probs` is left untouched, so a caller that forgets to check
 * the return value gets whatever it had, not a fabricated answer.
 */
int gn_bearoff_probs(const GnBearoff *table, const GnPosition *pos,
                     float probs[GN_NUM_OUTPUTS]);

/*
 * The four exact equities as the database stores them: cubeless, then cubeful
 * with the cube owned by the player on roll, centred, and owned by the
 * opponent.
 *
 * Returns 1 on success, 0 if the position is outside the table. **T34 will want
 * this**: it is a cube model's only exact reference, and fitting a cube
 * efficiency against it is what makes the fitted value a measurement rather than
 * a borrowed constant.
 */
int gn_bearoff_equities(const GnBearoff *table, const GnPosition *pos,
                        double equities[4]);

/*
 * The combinatorial rank gnubg assigns to one side's checker distribution.
 *
 * `side[i]` is the number of checkers on the point that is `i + 1` pips from
 * bearing off. Exposed because it is the piece most likely to be wrong and the
 * least likely to announce it -- a wrong index reads a real entry for a
 * different position and returns a perfectly plausible number.
 */
long gn_bearoff_index(const int *side, int points);

/*
 * ── THE SHARED TABLE (T38) ──────────────────────────────────────────
 *
 * `gn_search.c` and `gn_choose.c` consult the exact table instead of the
 * network whenever a leaf position falls in its domain. Threading a `const
 * GnBearoff *` through every search entry point would touch every signature
 * in this project for one optional lookup, so instead the table is a single
 * module-level pointer, set once by the caller before any search runs.
 *
 * NOT LOCKED, ON PURPOSE: this project's parallelism is by PROCESS (see
 * `bench/exact_gap.py`, one `ProcessPoolExecutor` worker per core), never by
 * thread. A pointer set once before the first search and only read afterwards
 * needs no synchronisation under that model. If threads are ever introduced
 * here, this assumption must be revisited alongside them -- see the same
 * reasoning for `g_evaluations` in `gn_search.c`.
 *
 * Defaults to NULL: without a call to `gn_bearoff_set_shared`, nothing about
 * a search changes, and the T12 regression corpus stays exactly as measured.
 */

/* Install (or clear, with NULL) the table consulted by the search. The table
 * itself is owned by the caller -- this module never opens or closes one. */
void gn_bearoff_set_shared(const GnBearoff *table);

/* The table currently installed, or NULL if none. */
const GnBearoff *gn_bearoff_shared(void);

/*
 * How many leaf evaluations the shared table has answered since the last
 * reset. Distinct from `gn_search_evaluations()`: a position served by the
 * table is NOT a network evaluation, and the two counters must never be
 * conflated -- the throughput measurements in `bench/` depend on that
 * distinction.
 */
unsigned long gn_bearoff_shared_hits(void);
void gn_bearoff_shared_reset_hits(void);

#ifdef __cplusplus
}
#endif

#endif /* GN_BEAROFF_H */

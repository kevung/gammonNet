/*
 * gn_choose.h -- 0-ply move choice, entirely in C.
 *
 * Not search: search is T30. This is the base move chooser — generate the legal
 * plays, evaluate each resulting position once, keep the best. It exists in C
 * rather than in the Python binding for one measured reason: T05 established
 * that the binding costs a factor of about ten, because it builds a Python
 * object per legal play, roughly eighteen per decision. A round-robin at the
 * volume `BRIEF.md` §5 requires cannot pay that.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_CHOOSE_H
#define GN_CHOOSE_H

#include "gn_infer.h"
#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Choose the best play for `pos->turn` at 0-ply, writing it to `out`.
 *
 * Returns 1 when a play was chosen, 0 when the player has no legal play (a real
 * outcome, not an error), and -1 on failure.
 *
 * THE SIGN IS THE SUBTLETY. A resulting position has already handed the turn
 * over, so the network's five probabilities describe the OPPONENT's chances.
 * The play to keep is therefore the one that MINIMISES the evaluation of its
 * own result. Reading it the other way produces an engine that plays
 * deliberately badly and reports nothing — a round-robin would simply show a
 * large negative number that looks like a weak model rather than a bug.
 *
 * A play that ends the game is not evaluated: a finished position has no
 * continuation to estimate. It is scored directly at its stake — 1, 2 or 3
 * points — which is exact, where the network could only approximate it.
 */
int gn_best_play_0ply(const GnNetwork *net, const GnPosition *pos,
                      int d1, int d2, GnPlay *out);

/*
 * The stake of a finished position, from the winner's side: 1 for a plain win,
 * 2 for a gammon, 3 for a backgammon. Returns -1 if the game is not over.
 */
int gn_game_value(const GnPosition *pos, int winner);

#ifdef __cplusplus
}
#endif

#endif /* GN_CHOOSE_H */

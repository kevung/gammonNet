/*
 * gn_search.h -- expectiminimax over dice: 0-ply to 3-ply.
 *
 * THE PERSPECTIVE RULE, WHICH IS WHERE THIS GOES WRONG SILENTLY
 *
 * `gn_evaluate` answers from `pos->turn`'s point of view, and `GnPlay.result`
 * already has the turn switched to the opponent. So the value of a play, to the
 * player who made it, is the NEGATION of the network's answer on the resulting
 * position. Get that backwards and the engine plays its opponent's best move
 * with total confidence -- no crash, no warning, and a perfectly plausible
 * output. Every negation in the implementation is there for this reason.
 *
 * THE RECURSION
 *
 *   V(pos, 0) = cubeless money equity of pos, from pos->turn's point of view
 *   V(pos, k) = SUM over the 21 distinct rolls of
 *                   w(roll) * max over plays of ( -V(play.result, k - 1) )
 *
 * and a decision with known dice at depth k scores each play at
 * `-V(play.result, k)`. So 0-ply asks the network about each resulting
 * position; 1-ply enumerates one opponent roll first; and so on.
 *
 * Dice weights are 1/36 for a double and 2/36 otherwise. They sum to exactly
 * 1 -- 6 * (1/36) + 15 * (2/36) -- and a test checks it rather than trusting it.
 *
 * WHAT THIS IS NOT
 *
 * Cubeless, money only. The match-play subtlety `PLAN.md` warns about -- at an
 * intermediate level the opponent maximises MATCH equity, not cubeless equity --
 * is deliberately absent, because the match equity table (T32) does not exist
 * yet. That absence is invisible in money play, which is precisely why it is
 * written here rather than left to be discovered: a 2-ply search that maximises
 * cubeless equity at intermediate nodes is WRONG in a match, and no money test
 * will ever say so.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_SEARCH_H
#define GN_SEARCH_H

#include "gn_infer.h"
#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 3-ply is the deepest this project measures; beyond that the branching makes
 * the question academic before it makes it expensive. */
#define GN_MAX_PLY 3

/* The 21 distinct rolls, and nothing more: (1,1) and (2,1) are rolls, (1,2) is
 * the same roll as (2,1) counted twice. */
#define GN_NUM_ROLLS 21

typedef struct {
    /* Search depth for the decision. 0 evaluates each resulting position
     * directly; each further ply enumerates one more opponent roll. */
    int ply;

    /*
     * Move filter: how many candidates survive to be searched deeper, per ply.
     * `filter[d]` applies at depth d, 0 meaning no filtering.
     *
     * This is T31's mechanism and what makes 2-ply practicable: the candidates
     * are ranked by a shallow search and only the best few are re-searched
     * deeply. It trades quality for speed, so the trade must be MEASURED, never
     * assumed -- a filter that "changes nothing" has not been measured.
     */
    int filter[GN_MAX_PLY + 1];
} GnSearchConfig;

/* Depth `ply`, no filtering. The honest baseline every filter is measured
 * against. */
GnSearchConfig gn_search_config(int ply);

typedef struct {
    GnPlay play;
    /* Of the resulting position, so from the OPPONENT's point of view. Only
     * meaningful at ply 0; deeper, the value comes from the search. */
    float probs[GN_NUM_OUTPUTS];
    /* Cubeless money equity of the play, from the point of view of the player
     * who made it. Already negated. */
    double equity;
} GnCandidate;

/*
 * Rank the legal plays for `pos` and dice (d1, d2), best first.
 *
 * Writes at most `max_out` candidates and returns how many were written, or -1
 * on error. A position with no legal play yields zero candidates -- that is a
 * legitimate outcome of the rules, not a failure, and the caller must handle
 * the turn simply passing.
 */
int gn_search_plays(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                    const GnSearchConfig *config,
                    GnCandidate *out, int max_out);

/*
 * The best play, or -1 if there is none (no legal play, or an error).
 */
int gn_best_play(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                 const GnSearchConfig *config, GnCandidate *out);

/*
 * Equity of a position whose dice are NOT yet rolled, from `pos->turn`'s point
 * of view -- `V(pos, k)` above.
 *
 * This is what a cube decision will need (T34): the value of the position
 * before the roll, not after a particular one.
 */
double gn_search_equity(const GnNetwork *net, const GnPosition *pos,
                        const GnSearchConfig *config);

/*
 * Exact equity of a finished game, from `pos->turn`'s point of view.
 *
 * `pos->turn` names the LOSER at a terminal position (see `gn_rules.h`), so
 * this is always negative: -1 plain, -2 gammon, -3 backgammon. Returns 0 if the
 * game is not over.
 *
 * Exposed because it is a genuine trap: handing a finished game to the network
 * asks it about an input it was never trained on, and it will answer -- with
 * five plausible numbers. Terminal positions are computed, never evaluated.
 */
double gn_terminal_equity(const GnPosition *pos);

/* Number of network evaluations consumed by the last search on this thread.
 * The unit T21 measures; a decision cost is this count times the cost of an
 * evaluation, and having it makes that a measurement rather than a guess. */
unsigned long gn_search_evaluations(void);
void gn_search_reset_evaluations(void);

#ifdef __cplusplus
}
#endif

#endif /* GN_SEARCH_H */

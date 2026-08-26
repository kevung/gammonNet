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
 * MATCH PLAY, AND THE SUBTLETY THAT IS INVISIBLE IN MONEY
 *
 * `PLAN.md` warns that at an intermediate level the opponent maximises MATCH
 * equity, not cubeless equity. At 4-away/2-away a gammonish move is not worth
 * what it is worth in money, and an engine that ignores this plays the wrong
 * move with complete confidence. **No money test will ever say so.**
 *
 * Set `use_match` and the search values every node through the match equity
 * table instead. Two things make that work:
 *
 *   1. Values are MATCH EQUITIES, `2 * MWC - 1`, not raw winning chances. On
 *      that scale the opponent's value is still the NEGATION, exactly as in
 *      money, so every negation in this file stays correct. Working in raw MWC
 *      would mean replacing each negation with `1 - x`, and missing one is the
 *      kind of error that produces plausible numbers.
 *
 *   2. The match state is SWAPPED at every ply. If the root player is at
 *      2-away against 4-away, the opponent one ply down is at 4-away against
 *      2-away. A state that failed to swap would optimise the wrong player's
 *      score -- again, plausibly.
 *
 * The cube is still absent: the search is cubeless, and `state.cube` merely
 * scales the stakes. Doubling decisions are T34.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_SEARCH_H
#define GN_SEARCH_H

#include "gn_infer.h"
#include "gn_met.h"
#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * The deepest search this engine will build.
 *
 * Raised from 3 to 4 on 2026-08-26, for one reason: gnubg offers a 4-ply
 * setting and a move filter for it (`show rollout`), so a comparison at that
 * depth needs the depth to exist. It is NOT a claim that 4-ply is useful --
 * T36 measured a whole extra ply at +0,00022 equity per decision, inside the
 * noise, and nothing since has moved that.
 *
 * What it costs is the honest reason this ceiling existed. Each ply multiplies
 * the tree by the twenty-one rolls times the surviving candidates: measured on
 * this build, a 3-ply decision at guard (0,1,1,5) costs 70,6 s unpruned and
 * 12,2 s with the pruning network. A 4-ply decision is that again, times the
 * width of one more level -- minutes at best, and the caller is expected to
 * know it. `bench/cost_by_depth.py` says what it really is rather than what
 * this comment guesses.
 */
#define GN_MAX_PLY 4

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

    /* Non-zero to value nodes through the match equity table rather than as
     * cubeless money. See the note above. */
    int use_match;

    /* The match state as seen by the player to move AT THE ROOT. The search
     * swaps it as it descends; the caller never has to. */
    GnMatchState match;

    /*
     * Cubeful leaf valuation -- t34-videau-spec §8, step 2.
     *
     * When `use_cube` is set, leaves are valued through the cube model at
     * efficiency `cube_x` (money §3, or the §9 match recursion when
     * `use_match` is also set) instead of cubeless. `cube_owner` (a
     * GnCubeOwner) is the cube as seen by the player to move AT THE ROOT;
     * the search mirrors it (OWNED <-> OPPONENT) at every ply, exactly as it
     * swaps the match state -- the caller never has to.
     *
     * No double/take/pass branches in the tree: the cube-aware value is
     * applied at the LEAVES and rides the same expectiminimax -- what the
     * reference engines do, and §8 records why. The expected effect is on
     * MOVE CHOICE (bold toward the cash with the cube, sober under it); the
     * cube DECISION consumes `gn_search_probs` plus `gn_cube_decide`,
     * outside this module.
     *
     * In the two-sided bearoff table's domain, money leaves are EXACT --
     * `gn_bearoff_equities`, no model. §8's own validation lever.
     */
    int use_cube;
    int cube_owner;
    double cube_x;

    /*
     * The pruning network (T3A), and how many candidates it lets through.
     *
     * The shallow pass of `rank_plays` is where a filtered search spends
     * almost everything: at every depth it asks the BIG network about every
     * legal play, only to keep `filter[depth]` of them. A pruning network is
     * a small network -- 196->32->5, distilled from the big one, MEASURED at
     * 92.5x cheaper per evaluation -- that does the sorting, so the big one
     * only ever scores the `prune_k` survivors.
     *
     * `prune_k == 0`, or a NULL `prune_net`, means the mechanism is OFF and
     * the search runs exactly as it did before -- bit for bit. That default
     * is deliberate: this changes what the engine plays, so it must be opted
     * into, and measured against the unpruned search rather than assumed.
     *
     * WHAT IT COSTS IN QUALITY, AND WHY k IS NOT FREE
     *
     * The small network is an approximation of the big one's ordering, not of
     * its values. Measured (docs/mesures/2026-08-07-T3A-elagage.md): the big
     * network's own best play is inside the small one's top 5 in 94.2% of
     * contact decisions and 83.6% of race decisions. The other 5.8% / 16.4%
     * are plays the search can no longer choose, at any depth, because they
     * never reach it. Lowering k buys speed with exactly that currency.
     *
     * WHAT `rank_plays` RETURNS WHEN THIS IS ON
     *
     * Only the survivors -- at most `prune_k` candidates, never all the legal
     * plays. The alternative was to return the rest carrying the SMALL
     * network's probabilities, and five plausible numbers from the wrong
     * network is the exact failure `CLAUDE.md` rule 2 is about. A caller that
     * needs every legal play scored by the big network must turn pruning off.
     *
     * `prune_k` is raised to `filter[depth]` where that is larger: pruning
     * below the filter would silently search fewer candidates than the caller
     * asked for, and no test would see it.
     */
    const GnNetwork *prune_net;
    int prune_k;
} GnSearchConfig;

/* Add pruning to a config. `k` is the number of candidates the small network
 * lets through to the big one; `k <= 0` or `net == NULL` turns it off. */
void gn_search_use_prune(GnSearchConfig *config, const GnNetwork *prune_net,
                         int k);

/* Add cubeful leaf valuation to a config (money or match, per `use_match`).
 * `owner` is the cube as the ROOT player sees it. `efficiency` is MEASURED
 * (bench/fit_efficiency.py) -- never a borrowed constant. */
void gn_search_use_cube(GnSearchConfig *config, int owner, double efficiency);

/* Depth `ply`, no filtering, cubeless money. The honest baseline every filter
 * is measured against. */
GnSearchConfig gn_search_config(int ply);

/* The same, valued through the match equity table. Returns a configuration
 * with `ply` clamped to 0 if `state` is not evaluable -- a search that silently
 * fell back to money at an unrepresentable score would be the exact failure
 * this module exists to avoid. Check `use_match` on the result. */
GnSearchConfig gn_search_config_match(int ply, const GnMatchState *state);

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
 * The pre-roll DISTRIBUTION at depth `config->ply`, from `pos->turn`'s point
 * of view -- the §8 (t34-videau-spec) companion of `gn_search_equity`.
 *
 * At depth 0 it is exactly what `evaluate_position` answers (bearoff table,
 * cache, or network -- same three sources, same order). Deeper, it is the
 * roll-weighted average of the best play's own distribution, one perspective
 * inversion per ply -- the best play being chosen by the SAME valuation the
 * equity recursion uses (money or match, same filter), so the distribution
 * describes the game the search would actually play.
 *
 * Why this exists: a cube decision at depth needs the five probabilities, not
 * the scalar the search returns -- and the two must never come from different
 * walks. Both money and match valuations are LINEAR in the distribution, so
 * `gn_search_equity(config)` equals the valuation of this vector at any
 * depth; a test holds that identity rather than trusting it.
 *
 * Returns 0, or -1 on error (and `out` is then untouched).
 */
int gn_search_probs(const GnNetwork *net, const GnPosition *pos,
                    const GnSearchConfig *config, float out[GN_NUM_OUTPUTS]);

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

/* Number of PRUNING-network evaluations consumed by the last search on this
 * thread. Kept separate from `gn_search_evaluations` on purpose: every cost
 * figure this project has published is in big-network evaluations, and
 * folding two units 92.5x apart into one counter would make all of them
 * incomparable. `gn_search_reset_evaluations` resets both. */
unsigned long gn_search_prune_evaluations(void);

#ifdef __cplusplus
}
#endif

#endif /* GN_SEARCH_H */

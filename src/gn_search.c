/*
 * gn_search.c -- expectiminimax over dice. See gn_search.h for the recursion,
 * the perspective rule, and what this deliberately does not do.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_search.h"

#include "gn_bearoff.h"
#include "gn_choose.h"
#include "gn_cube.h"
#include "gn_evalcache.h"

#include <stdlib.h>
#include <string.h>

/* A position has at most a few hundred legal plays; 2048 is the bound the rules
 * layer already uses, and reusing it keeps one number instead of two. */
#define MAX_PLAYS 2048

typedef struct {
    signed char d1, d2;
    double weight;
} GnRoll;

/*
 * The 21 distinct rolls with their probabilities.
 *
 * Built once, at first use, rather than written out by hand: a table of 21
 * literals is 21 chances to mistype a weight, and the error would be a silent
 * bias in every evaluation rather than a crash.
 */
static GnRoll g_rolls[GN_NUM_ROLLS];
static int g_rolls_ready = 0;

static void build_rolls(void)
{
    if (g_rolls_ready) {
        return;
    }
    int n = 0;
    for (int a = 1; a <= 6; a++) {
        for (int b = a; b <= 6; b++) {
            g_rolls[n].d1 = (signed char)a;
            g_rolls[n].d2 = (signed char)b;
            g_rolls[n].weight = (a == b) ? (1.0 / 36.0) : (2.0 / 36.0);
            n++;
        }
    }
    g_rolls_ready = 1;
}

/* Deliberately not thread-local: this project has no threads yet, and a
 * counter that pretended to be thread-safe without being tested as such would
 * be worse than one that is honestly single-threaded. */
static unsigned long g_evaluations = 0;

unsigned long gn_search_evaluations(void) { return g_evaluations; }
static unsigned long g_prune_evaluations = 0;

unsigned long gn_search_prune_evaluations(void) { return g_prune_evaluations; }

void gn_search_reset_evaluations(void)
{
    g_evaluations = 0;
    g_prune_evaluations = 0;
}

/*
 * The single place a leaf position becomes five probabilities (T38, T3A).
 *
 * Three sources are tried in order, each cheaper to skip than the one after
 * it:
 *
 *   1. The exact bearoff table, if one is installed. A hit is exact, and
 *      costs one memory read.
 *   2. The evaluation cache, if one is installed (T3A). A hit is the network's
 *      own past answer for this EXACT position -- see gn_evalcache.h for why
 *      that makes it safe to return without re-running the network -- and it
 *      also costs about one memory read plus a 29-byte comparison.
 *   3. The network itself: the one source that was ever expensive.
 *
 * `g_evaluations` counts ONLY step 3. A bearoff hit was never a network
 * evaluation (T38's distinction), and neither is a cache hit: it is the
 * SAME evaluation, counted once, when it first happened. Counting it twice
 * would make the cache look like it does nothing, and counting it zero times
 * for the miss that populated the cache would undercount the real cost.
 * `gn_evalcache_hits()` / `_misses()` are the separate counters that make the
 * cache's own contribution measurable.
 *
 * Both call sites that used to invoke `gn_evaluate` directly on a leaf go
 * through here now: `leaf_value` and the shallow pass of `rank_plays`.
 */
/* Steps 1 and 2 alone: the exact table, then the cache. Returns 1 on a hit
 * (probs filled), 0 on a miss. Split out so the batched shallow pass of
 * `rank_plays` can gather its misses and forward them together. */
/*
 * Step 1 alone: the exact table. Split out for the pruning pass, and the
 * reason is not tidiness.
 *
 * THE CACHE IS NEUTRAL, AND THE PRUNING PASS MUST NOT END THAT
 *
 * T3A measured and holds that the evaluation cache changes no result: it
 * replays the big network's own answers, so a warm cache and a cold one
 * produce the same search, bit for bit -- which is what lets a T35 campaign
 * be segmented and resumed and still be identical to a run in one go.
 *
 * A pruning pass that consulted the cache would end that property in the
 * worst possible way. The same candidate would be ranked by the BIG
 * network's value when the cache happens to hold it and by the SMALL
 * network's when it does not, so the ranking -- and therefore which plays
 * survive, and therefore the move played -- would depend on evaluation
 * history. Nothing would crash; runs would simply stop being reproducible,
 * and the measurement apparatus would stop meaning what it says.
 *
 * The exact table has no such problem: it is stateless, and hits the same
 * positions on every run.
 */
static int evaluate_exact(const GnPosition *pos, float probs[GN_NUM_OUTPUTS])
{
    const GnBearoff *table = gn_bearoff_shared();
    return (table != NULL && gn_bearoff_probs(table, pos, probs)) ? 1 : 0;
}

static int evaluate_cheap(const GnPosition *pos, float probs[GN_NUM_OUTPUTS])
{
    if (evaluate_exact(pos, probs)) {
        return 1;
    }

    GnEvalCache *cache = gn_evalcache_shared();
    if (cache != NULL && gn_evalcache_lookup(cache, pos, probs)) {
        return 1;
    }
    return 0;
}

/* The bookkeeping of step 3, shared by the scalar and batched paths: one
 * network evaluation happened for `pos` — count it, remember it. */
static void evaluated(const GnPosition *pos, const float probs[GN_NUM_OUTPUTS])
{
    g_evaluations++;
    GnEvalCache *cache = gn_evalcache_shared();
    if (cache != NULL) {
        gn_evalcache_store(cache, pos, probs);
    }
}

static int evaluate_position(const GnNetwork *net, const GnPosition *pos,
                             float probs[GN_NUM_OUTPUTS])
{
    if (evaluate_cheap(pos, probs)) {
        return 0;
    }
    if (gn_evaluate(net, pos, probs) != 0) {
        return -1;
    }
    evaluated(pos, probs);
    return 0;
}

GnSearchConfig gn_search_config(int ply)
{
    GnSearchConfig config;
    memset(&config, 0, sizeof(config));
    config.ply = (ply < 0) ? 0 : (ply > GN_MAX_PLY ? GN_MAX_PLY : ply);
    return config;
}

GnSearchConfig gn_search_config_match(int ply, const GnMatchState *state)
{
    GnSearchConfig config = gn_search_config(ply);
    if (state == NULL || !gn_match_state_is_valid(state)) {
        /* Refused, not degraded. Falling back to money here would produce a
         * search that is wrong in a match and says nothing about it. */
        config.ply = 0;
        return config;
    }
    config.use_match = 1;
    config.match = *state;
    return config;
}

/* The same position, seen from the other side of the table. One reading of
 * the swap for the whole repository: gn_met.h owns it. */
static GnMatchState swap_sides(GnMatchState state)
{
    return gn_match_state_swap(state);
}

/* The same cube, seen from the other side of the table: mine becomes theirs,
 * a centred cube is centred for everyone. Mirrored at every ply for exactly
 * the reason the match state is swapped -- forgetting it would value every
 * odd ply with the wrong player holding the cube, plausibly. */
static int mirror_owner(int owner)
{
    if (owner == GN_CUBE_OWNED)
        return GN_CUBE_OPPONENT;
    if (owner == GN_CUBE_OPPONENT)
        return GN_CUBE_OWNED;
    return GN_CUBE_CENTRED;
}

void gn_search_use_prune(GnSearchConfig *config, const GnNetwork *prune_net,
                         int k)
{
    if (config == NULL) {
        return;
    }
    if (prune_net == NULL || k <= 0) {
        config->prune_net = NULL;
        config->prune_k = 0;
        return;
    }
    config->prune_net = prune_net;
    config->prune_k = k;
}

void gn_search_use_cube(GnSearchConfig *config, int owner, double efficiency)
{
    if (config == NULL) {
        return;
    }
    config->use_cube = 1;
    config->cube_owner = owner;
    config->cube_x = efficiency;
}

/*
 * Turn a distribution into a value, from the point of view of the player whose
 * `state` this is.
 *
 * Money equity or match equity, on the SAME scale: both are 0 for an even
 * position and negate between sides. That is what lets one recursion serve
 * both, and why the match path works in `2 * MWC - 1` rather than raw winning
 * chances.
 *
 * Takes probabilities rather than a position on purpose: the caller has often
 * already paid for the evaluation, and re-running it here would double the cost
 * of the single dominant operation in this file.
 */
static double value_from_probs(const float probs[GN_NUM_OUTPUTS],
                               const GnSearchConfig *config, GnMatchState state,
                               int *failed)
{
    if (!config->use_match) {
        return (double)gn_money_equity(probs);
    }
    const double equity = gn_match_equity(&state, probs);
    if (equity <= -2.0) {
        if (failed) *failed = 1;
        return 0.0;
    }
    return equity;
}

/*
 * The value of one evaluated node -- cubeless (`value_from_probs`) or, under
 * `use_cube`, the cube model at this node's owner (t34-videau-spec §8).
 *
 * Takes the position as well as its distribution because the exact shortcut
 * needs it: in the two-sided table's money domain the four cubeful equities
 * are stored, and reading one beats modelling it. Only money -- the table
 * stores points, and turning them into a MWC would need the distribution
 * anyway, which is exactly the model path below.
 */
static double node_value(const GnPosition *pos,
                         const float probs[GN_NUM_OUTPUTS],
                         const GnSearchConfig *config, GnMatchState state,
                         int owner, int *failed)
{
    if (!config->use_cube) {
        return value_from_probs(probs, config, state, failed);
    }

    if (!config->use_match) {
        const GnBearoff *table = gn_bearoff_shared();
        double equities[4];
        if (table != NULL && gn_bearoff_equities(table, pos, equities)) {
            /* gn_bearoff.h's order: cubeless, owned, centred, opponent --
             * indexed by GnCubeOwner {CENTRED=0, OWNED=1, OPPONENT=2}. */
            static const int index_of_owner[3] = {2, 1, 3};
            return equities[index_of_owner[owner]];
        }
    }

    int cube_failed = 0;
    const double value = gn_cube_value(probs, (GnCubeOwner)owner,
                                       config->use_match ? &state : NULL,
                                       config->cube_x, &cube_failed);
    if (cube_failed) {
        if (failed) *failed = 1;
        return 0.0;
    }
    return value;
}

/* The value of a leaf: evaluate once, then convert. */
static double leaf_value(const GnNetwork *net, const GnPosition *pos,
                         const GnSearchConfig *config, GnMatchState state,
                         int owner, int *failed)
{
    float probs[GN_NUM_OUTPUTS];
    if (evaluate_position(net, pos, probs) != 0) {
        if (failed) *failed = 1;
        return 0.0;
    }
    return node_value(pos, probs, config, state, owner, failed);
}

/* The value of a finished game, from the point of view of `pos->turn` -- who
 * is the loser. Computed, never evaluated. */
static double terminal_value(const GnPosition *pos, const GnSearchConfig *config,
                             GnMatchState state)
{
    if (!config->use_match) {
        return gn_terminal_equity(pos);
    }
    const int winner = gn_position_winner(pos);
    const int stake = gn_game_value(pos, winner);
    if (stake < 0) {
        return 0.0;
    }
    /* `pos->turn` names the loser, so the player to move never wins here. */
    const double mwc = gn_met_after(&state, stake * state.cube, 0);
    return (mwc < 0.0) ? 0.0 : 2.0 * mwc - 1.0;
}

double gn_terminal_equity(const GnPosition *pos)
{
    if (pos == NULL || !gn_position_is_over(pos)) {
        return 0.0;
    }

    const int winner = gn_position_winner(pos);

    /*
     * `gn_game_value` from T04 already decides plain / gammon / backgammon.
     * Reimplementing that rule here would put two readings of it in one
     * repository, and the day they disagreed, nothing would say which one the
     * measurements had used. It is called, not copied.
     */
    const int stake = gn_game_value(pos, winner);
    if (stake < 0) {
        return 0.0;
    }

    /* `pos->turn` names the loser at a terminal position -- see gn_rules.h. */
    return (pos->turn == (unsigned char)winner) ? (double)stake : -(double)stake;
}

/* Equity of `pos` from `pos->turn`'s point of view, dice not yet rolled.
 * `owner` is the cube as `pos->turn` sees it (unused unless `use_cube`). */
static double position_equity(const GnNetwork *net, const GnPosition *pos,
                              const GnSearchConfig *config, int depth,
                              GnMatchState state, int owner);
static int rank_plays_deepen(const GnNetwork *net, const GnSearchConfig *config,
                             int depth, GnMatchState state, int owner,
                             GnCandidate *out, int written);
/* All the mass on the one outcome that happened. Declared here because the
 * shallow fill needs it: a play that ends the game has a distribution, and it
 * is a KNOWN one -- see `shallow_fill`. */
static void terminal_probs(const GnPosition *pos, float out[GN_NUM_OUTPUTS]);

static int compare_candidates(const void *a, const void *b)
{
    const double x = ((const GnCandidate *)a)->equity;
    const double y = ((const GnCandidate *)b)->equity;
    /* Best first. */
    return (x < y) - (x > y);
}

/*
 * Fill `out[0..n).probs` -- the sibling loop that dominates the whole search,
 * at every depth.
 *
 * Three sweeps, so the network sees its positions in BATCHES (T35): gather
 * what the cheap sources cannot answer, forward those together
 * (`gn_evaluate_batch`, bit-identical per item -- see gn_infer.h), then the
 * caller values everything. Same evaluations, same answers, same ranking; the
 * weights are read once per batch instead of once per position, which is the
 * entire point (bench/bench_batch.c, x2,21).
 *
 * `is_prune` says which network this is, and it changes two things, both of
 * them load-bearing:
 *
 *   - the cheap sources. The big network may use the exact table AND the
 *     cache; the pruning network may use the exact table only. See
 *     `evaluate_exact` for why the cache is off limits here.
 *   - the bookkeeping. A pruning evaluation is counted on its own counter and
 *     is NEVER stored in the cache. One small-network distribution written
 *     into that cache would be served as the big network's answer for the
 *     rest of the process, to every later search, silently -- the single most
 *     damaging line this feature could have contained.
 *
 * Terminal positions are computed, never evaluated (see gn_terminal_equity).
 * The value sweep takes their equity from `terminal_value` and never reads
 * their `probs` -- but a CALLER does, and a zero vector is not "no answer",
 * it is a perfectly formed distribution saying the game is lost outright.
 * A play that bears off the last checker has a distribution, and it is known
 * exactly: `terminal_probs` writes it. This costs nothing (no evaluation) and
 * closes the one place where `GnCandidate.probs` used to be plausible and
 * wrong -- CLAUDE.md rule 2's failure mode, on the last play of every game.
 *
 * WHY BOTH NETWORKS BATCH, AGAINST WHAT THE MICRO-BENCHMARK SAID
 *
 * Batching exists to read the weights once for many positions -- worth a great
 * deal for 2 MiB of big-network weights, and seemingly nothing for 25 KiB of
 * small-network weights that never leave cache. Isolated, that shows up
 * clearly (`make bench-encoding`, 20 000 real positions, this build):
 *
 *     big network    scalar 0.35026 ms   batched 0.04119 ms   x8.5 faster
 *     small network  scalar 0.00426 ms   batched 0.00641 ms   x1.5 SLOWER
 *
 * So the pruning pass was written scalar. Then it was measured IN THE SEARCH,
 * same corpus, same 8 workers, identical evaluation counts either way
 * (bench/prune_search.py, 48 contact decisions, k=5):
 *
 *     scalar pruning pass    1.720 s/decision
 *     batched pruning pass   1.582 s/decision   <- 8% faster
 *
 * The isolated number predicted the wrong direction. It measures a tight loop
 * over one array; the search interleaves the pass with move generation and
 * recursion, and the batch path evidently keeps its locality better there.
 * The in-situ measurement decides, so both networks batch.
 *
 * Worth keeping in mind before the next per-evaluation figure is turned into
 * a search-level conclusion: this file has now produced two of them that did
 * not survive contact with the real search.
 */
#ifdef GN_BATCH_FILL_STATS
/* Le remplissage PAR RÉSEAU. `gn_evaluate_batch` ne sait pas lequel on lui
 * donne ; ici on le sait. Le noyau calcule toujours GN_EVAL_BATCH voies, donc
 * ce qui manque au remplissage est du travail jeté — et l'élagage change le
 * remplissage du grand réseau, ce qui est précisément la question. */
unsigned long gn_fill_calls[2] = {0, 0};
unsigned long gn_fill_live[2] = {0, 0};
#endif

static int shallow_fill(const GnNetwork *net, GnCandidate *out, int n,
                        int is_prune)
{
    int pending[GN_EVAL_BATCH];
    const GnPosition *batch_pos[GN_EVAL_BATCH];
    float batch_probs[GN_EVAL_BATCH][GN_NUM_OUTPUTS];
    int n_pending = 0;

    for (int i = 0; i <= n; i++) {
        if (i < n) {
            const GnPosition *result = &out[i].play.result;

            if (gn_position_is_over(result)) {
                terminal_probs(result, out[i].probs);
                continue;
            }
            if (is_prune ? evaluate_exact(result, out[i].probs)
                         : evaluate_cheap(result, out[i].probs)) {
                continue;
            }
            pending[n_pending++] = i;
            if (n_pending < GN_EVAL_BATCH) {
                continue;
            }
        } else if (n_pending == 0) {
            break;
        }

        /* The batch is full, or the loop has run out of plays: forward it. */
        for (int b = 0; b < n_pending; b++) {
            batch_pos[b] = &out[pending[b]].play.result;
        }
#ifdef GN_BATCH_FILL_STATS
        gn_fill_calls[is_prune ? 1 : 0]++;
        gn_fill_live[is_prune ? 1 : 0] += (unsigned long)n_pending;
#endif
        if (gn_evaluate_batch(net, batch_pos, n_pending, batch_probs) != 0) {
            return -1;
        }
        for (int b = 0; b < n_pending; b++) {
            memcpy(out[pending[b]].probs, batch_probs[b],
                   sizeof(batch_probs[b]));
            if (is_prune) {
                g_prune_evaluations++;
            } else {
                evaluated(batch_pos[b], batch_probs[b]);
            }
        }
        n_pending = 0;
    }
    return 0;
}

/*
 * Probabilities become equities, from the mover's side. `probs` keeps the raw
 * distribution -- it describes the position, not the score -- and only
 * `equity` is score-aware.
 */
static int value_sweep(GnCandidate *out, int n, const GnSearchConfig *config,
                       GnMatchState theirs, int owner)
{
    for (int i = 0; i < n; i++) {
        const GnPosition *result = &out[i].play.result;

        if (gn_position_is_over(result)) {
            out[i].equity = -terminal_value(result, config, theirs);
            continue;
        }

        int failed = 0;
        const double value = node_value(result, out[i].probs, config, theirs,
                                        mirror_owner(owner), &failed);
        if (failed) {
            return -1;
        }
        /* The negation: the answer was the opponent's. */
        out[i].equity = -value;
    }
    return 0;
}

/*
 * Rank the plays for one roll at `depth`, writing them best-first.
 *
 * At depth 0 each play costs one network evaluation. Deeper, the plays are
 * first ranked by a 0-ply pass, then the survivors -- all of them if no filter
 * is set -- are re-scored by the recursion. Ranking shallow before searching
 * deep is what makes a filter possible at all, and it is also why an unfiltered
 * search still pays for the shallow pass: a cost worth naming, since it is
 * roughly one extra evaluation per play.
 *
 * With a pruning network configured (T3A), that shallow pass is done by the
 * SMALL network first, and only its best `prune_k` survivors are shown to the
 * big one -- which is also why this function then returns at most `prune_k`
 * candidates rather than every legal play. See `GnSearchConfig::prune_net`.
 */
/* How many candidates the pruning pass lets through at `depth`, or 0 when
 * pruning is off. Never below `filter[depth]`: pruning under the filter would
 * search fewer candidates than the caller asked for, and the ranking would
 * look perfectly normal while doing it. */
static int prune_keep(const GnSearchConfig *config, int depth)
{
    if (config->prune_net == NULL || config->prune_k <= 0) {
        return 0;
    }
    int keep = config->prune_k;
    if (depth >= 0 && depth <= GN_MAX_PLY && config->filter[depth] > keep) {
        keep = config->filter[depth];
    }
    return keep;
}

/*
 * PHASE ONE -- the legal plays, and the pruning pass over them.
 *
 * Split out from `rank_plays` so a caller enumerating 21 rolls can run all
 * twenty-one pruning passes back to back before any of the big network's.
 * That is not a tidiness refactor; it is the whole point, and the number
 * behind it is measured (docs/mesures/2026-08-26-T3A-regroupement.md):
 * interleaved with the big network the small one costs 0.0227 ms per
 * evaluation, and running alone in the same search 0.00199 ms -- eleven times
 * less. Its 25 KiB of weights are its entire advantage, and 2 MiB of big
 * network between two calls evicts them every time.
 *
 * Leaves `out[0..returned)` carrying the SMALL network's probabilities when
 * pruning fired. They are not an answer; `rank_plays_finish` overwrites them.
 */
static int rank_plays_prune(const GnPosition *pos, int d1, int d2,
                            const GnSearchConfig *config, int depth,
                            GnMatchState state, int owner, GnCandidate *out,
                            int max_out)
{
    if (pos == NULL || out == NULL || max_out <= 0) {
        return -1;
    }

    GnPlay *plays = malloc(sizeof(GnPlay) * MAX_PLAYS);
    if (plays == NULL) {
        return -1;
    }

    const int count = gn_legal_plays(pos, d1, d2, plays, MAX_PLAYS);
    if (count <= 0) {
        free(plays);
        return (count < 0) ? -1 : 0;
    }

    int written = (count < max_out) ? count : max_out;
    for (int i = 0; i < written; i++) {
        out[i].play = plays[i];
    }
    free(plays);

    const int keep = prune_keep(config, depth);
    if (keep > 0 && written > keep) {
        /* The result has handed the turn over, so everything about it is seen
         * from the opponent's side -- including the score. */
        const GnMatchState theirs = swap_sides(state);

        if (shallow_fill(config->prune_net, out, written, 1) != 0) {
            return -1;
        }
        if (value_sweep(out, written, config, theirs, owner) != 0) {
            return -1;
        }
        qsort(out, (size_t)written, sizeof(GnCandidate), compare_candidates);
        /* The survivors, and nothing else: what is dropped here carries the
         * SMALL network's probabilities, and no caller may see those.
         * gn_search.h states the contract. */
        written = keep;
    }
    return written;
}

/*
 * PHASE TWO -- the big network over what survived, then the deep pass.
 *
 * `written` is what phase one returned. Everything here is exactly what
 * `rank_plays` always did after the pruning pass, moved verbatim so the two
 * orders -- interleaved and grouped -- cannot drift apart.
 */
static int rank_plays_finish(const GnNetwork *net,
                             const GnSearchConfig *config, int depth,
                             GnMatchState state, int owner, GnCandidate *out,
                             int written)
{
    if (net == NULL || out == NULL || written <= 0) {
        return (written < 0) ? -1 : written;
    }

    const GnMatchState theirs = swap_sides(state);

    if (shallow_fill(net, out, written, 0) != 0) {
        return -1;
    }
    if (value_sweep(out, written, config, theirs, owner) != 0) {
        return -1;
    }

    qsort(out, (size_t)written, sizeof(GnCandidate), compare_candidates);

    return rank_plays_deepen(net, config, depth, state, owner, out, written);
}

/*
 * PHASE THREE -- the deep pass over the best `filter[depth]` candidates.
 *
 * Split out so the grouped path can reach it after doing the big network's
 * shallow pass its own way. `rank_plays_finish` is now this plus the shallow
 * pass in front of it, so the two orders cannot drift apart.
 */
static int rank_plays_deepen(const GnNetwork *net, const GnSearchConfig *config,
                             int depth, GnMatchState state, int owner,
                             GnCandidate *out, int written)
{
    if (depth <= 0) {
        return written;
    }

    int searched = written;
    const int filter = config->filter[depth];
    if (filter > 0 && filter < searched) {
        searched = filter;
    }

    for (int i = 0; i < searched; i++) {
        const GnPosition *result = &out[i].play.result;
        if (gn_position_is_over(result)) {
            continue; /* already exact */
        }
        /*
         * `depth`, not `depth - 1`. A decision at depth k scores each play at
         * -V(result, k): the k counts the opponent's rolls to enumerate AFTER
         * the play, and the play itself is not one of them.
         *
         * Written as `depth - 1` first, and the mistake was instructive: at
         * 1-ply the deep pass then recomputed exactly what the shallow pass had
         * already computed. Nothing crashed, the equity still moved -- the
         * other entry point was right -- and only the ranking gave it away, by
         * never once differing from 0-ply over 114 decisions.
         */
        out[i].equity = -position_equity(net, result, config, depth,
                                         swap_sides(state),
                                         mirror_owner(owner));
    }

    /* Re-rank: the deep pass is allowed to disagree with the shallow one, and
     * if it never did, the deep pass would be pointless. */
    qsort(out, (size_t)searched, sizeof(GnCandidate), compare_candidates);
    return written;
}

static int rank_plays(const GnNetwork *net, const GnPosition *pos,
                      int d1, int d2, const GnSearchConfig *config, int depth,
                      GnMatchState state, int owner, GnCandidate *out,
                      int max_out)
{
    if (net == NULL) {
        return -1;
    }
    const int written = rank_plays_prune(pos, d1, d2, config, depth, state,
                                         owner, out, max_out);
    if (written <= 0) {
        return written;
    }
    return rank_plays_finish(net, config, depth, state, owner, out, written);
}

static double position_equity(const GnNetwork *net, const GnPosition *pos,
                              const GnSearchConfig *config, int depth,
                              GnMatchState state, int owner)
{
    if (gn_position_is_over(pos)) {
        return terminal_value(pos, config, state);
    }

    if (depth <= 0) {
        return leaf_value(net, pos, config, state, owner, NULL);
    }

    build_rolls();

    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return 0.0;
    }

    /*
     * THE GROUPING, AND WHY IT IS WORTH A SEPARATE CODE PATH
     *
     * With pruning on, the twenty-one rolls below would otherwise alternate
     * small network, big network, small, big -- about 1 400 times per
     * decision. The small network's whole advantage is that its 25 KiB of
     * weights stay in cache, and 2 MiB of big network between two of its
     * calls evicts them every time. MEASURED: 0.00199 ms per evaluation when
     * it runs alone in this same search, 0.0227 ms interleaved -- eleven
     * times more.
     *
     * So when pruning is on, phase one runs for ALL rolls first, then phase
     * two. The results are IDENTICAL either way, and not by luck: the pruning
     * pass neither reads nor writes the evaluation cache (see
     * `evaluate_exact`), so nothing it does can depend on, or change, what
     * the big passes have done. `tests/test_search_prune.py` holds that
     * equality bit for bit rather than trusting this paragraph.
     */
    const int keep = prune_keep(config, depth - 1);
    if (keep > 0) {
        GnCandidate *grouped = malloc(sizeof(GnCandidate) * GN_NUM_ROLLS
                                      * (size_t)keep);
        int *counts = malloc(sizeof(int) * GN_NUM_ROLLS);
        if (grouped == NULL || counts == NULL) {
            free(grouped);
            free(counts);
            free(candidates);
            return 0.0;
        }

        /* Phase one, twenty-one times over: the small network stays hot. */
        for (int r = 0; r < GN_NUM_ROLLS; r++) {
            const int n = rank_plays_prune(pos, g_rolls[r].d1, g_rolls[r].d2,
                                           config, depth - 1, state, owner,
                                           candidates, MAX_PLAYS);
            counts[r] = (n < 0) ? 0 : ((n > keep) ? keep : n);
            if (counts[r] > 0) {
                memcpy(grouped + (size_t)r * keep, candidates,
                       sizeof(GnCandidate) * (size_t)counts[r]);
            }
        }

        /*
         * PHASE TWO, AND THE REASON THE GROUPING EARNS ITS KEEP
         *
         * The big network's shallow pass is run ONCE over the survivors of
         * all twenty-one rolls, not once per roll. That is where the win is,
         * and the measurement that found it is blunt: with pruning at k=5 the
         * big network's batches carry 4.7 positions out of 32 -- a 14.5 %
         * fill -- so it still computed 831 136 lanes to deliver 120 834
         * evaluations. Pruning removed 82 % of the evaluations and 26 % of
         * the work. Twenty-one rolls' survivors put together fill the batches
         * instead.
         *
         * Safe because `gn_evaluate_batch` is bit-identical per item however
         * the positions are grouped (gn_infer.h, tests/test_batch.py): which
         * neighbours a position travels with cannot change its answer.
         *
         * The match state does not depend on the roll -- `theirs` is the same
         * for all twenty-one -- so one value sweep per roll is still correct,
         * and each roll keeps its own ranking.
         */
        int total_live = 0;
        for (int r = 0; r < GN_NUM_ROLLS; r++) {
            total_live += counts[r];
        }
        if (total_live > 0) {
            GnCandidate *dense = malloc(sizeof(GnCandidate) * (size_t)total_live);
            if (dense == NULL) {
                free(grouped); free(counts); free(candidates);
                return 0.0;
            }
            int at = 0;
            for (int r = 0; r < GN_NUM_ROLLS; r++) {
                for (int i = 0; i < counts[r]; i++) {
                    dense[at++] = grouped[(size_t)r * keep + i];
                }
            }
            if (shallow_fill(net, dense, total_live, 0) != 0) {
                free(dense); free(grouped); free(counts); free(candidates);
                return 0.0;
            }
            at = 0;
            for (int r = 0; r < GN_NUM_ROLLS; r++) {
                for (int i = 0; i < counts[r]; i++) {
                    grouped[(size_t)r * keep + i] = dense[at++];
                }
            }
            free(dense);
        }

        const GnMatchState theirs = swap_sides(state);
        double sum = 0.0;
        for (int r = 0; r < GN_NUM_ROLLS; r++) {
            GnCandidate *slot = grouped + (size_t)r * keep;
            double best;
            if (counts[r] > 0) {
                /* The probabilities are already in place; only the valuation,
                 * the ranking and the deep pass remain. */
                if (value_sweep(slot, counts[r], config, theirs, owner) != 0) {
                    free(grouped); free(counts); free(candidates);
                    return 0.0;
                }
                qsort(slot, (size_t)counts[r], sizeof(GnCandidate),
                      compare_candidates);
                const int n = rank_plays_deepen(net, config, depth - 1, state,
                                                owner, slot, counts[r]);
                best = (n > 0) ? slot[0].equity : 0.0;
            } else {
                GnPosition passed = *pos;
                gn_position_swap_turn(&passed);
                best = -position_equity(net, &passed, config, depth - 1,
                                        swap_sides(state), mirror_owner(owner));
            }
            sum += g_rolls[r].weight * best;
        }

        free(grouped);
        free(counts);
        free(candidates);
        return sum;
    }

    double total = 0.0;
    for (int r = 0; r < GN_NUM_ROLLS; r++) {
        const int count = rank_plays(net, pos, g_rolls[r].d1, g_rolls[r].d2,
                                     config, depth - 1, state, owner,
                                     candidates, MAX_PLAYS);

        double best;
        if (count > 0) {
            best = candidates[0].equity;
        } else {
            /*
             * No legal play: the turn simply passes. Not an error -- a closed
             * board or a hopeless bar entry produces it, and treating it as one
             * would silently drop those branches from the average.
             */
            GnPosition passed = *pos;
            gn_position_swap_turn(&passed);
            best = -position_equity(net, &passed, config, depth - 1,
                                    swap_sides(state), mirror_owner(owner));
        }
        total += g_rolls[r].weight * best;
    }

    free(candidates);
    return total;
}

/* ── The distribution at depth (t34-videau-spec §8, step 1) ──────────── */

/* The same distribution, seen from the other side of the table. The nested
 * encoding makes this a swap plus one complement: my gammon losses are the
 * opponent's gammon wins, and P(win) partitions. */
static void invert_probs(const float in[GN_NUM_OUTPUTS],
                         float out[GN_NUM_OUTPUTS])
{
    out[GN_P_WIN] = 1.0f - in[GN_P_WIN];
    out[GN_P_WIN_G] = in[GN_P_LOSE_G];
    out[GN_P_WIN_BG] = in[GN_P_LOSE_BG];
    out[GN_P_LOSE_G] = in[GN_P_WIN_G];
    out[GN_P_LOSE_BG] = in[GN_P_WIN_BG];
}

/* The distribution of a finished game -- all mass on the one outcome that
 * happened. Computed, never evaluated, like `gn_terminal_equity`. */
static void terminal_probs(const GnPosition *pos, float out[GN_NUM_OUTPUTS])
{
    const int winner = gn_position_winner(pos);
    const int stake = gn_game_value(pos, winner);
    const int we_won = (pos->turn == (unsigned char)winner);

    out[GN_P_WIN] = we_won ? 1.0f : 0.0f;
    out[GN_P_WIN_G] = (we_won && stake >= 2) ? 1.0f : 0.0f;
    out[GN_P_WIN_BG] = (we_won && stake >= 3) ? 1.0f : 0.0f;
    out[GN_P_LOSE_G] = (!we_won && stake >= 2) ? 1.0f : 0.0f;
    out[GN_P_LOSE_BG] = (!we_won && stake >= 3) ? 1.0f : 0.0f;
}

/*
 * The §8 recursion: the distribution follows the play the SCALAR recursion
 * would choose. `rank_plays` picks the best play with the configured
 * valuation; only what happens to the winner's distribution is new here.
 *
 * A separate walk rather than a widening of `position_equity`: the price is
 * re-walking one subtree per node (paid only when a caller actually asks for
 * a distribution -- once per cube decision, never per move choice), the
 * reward is that the equity path is untouched, byte for byte, so T12's
 * non-regression corpus keeps meaning what it meant. With the T3A cache
 * installed the re-walk's network evaluations are all hits anyway.
 */
static int position_probs(const GnNetwork *net, const GnPosition *pos,
                          const GnSearchConfig *config, int depth,
                          GnMatchState state, int owner,
                          float out[GN_NUM_OUTPUTS])
{
    if (gn_position_is_over(pos)) {
        terminal_probs(pos, out);
        return 0;
    }

    if (depth <= 0) {
        return evaluate_position(net, pos, out);
    }

    build_rolls();

    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return -1;
    }

    double total[GN_NUM_OUTPUTS] = {0.0, 0.0, 0.0, 0.0, 0.0};
    for (int r = 0; r < GN_NUM_ROLLS; r++) {
        const int count = rank_plays(net, pos, g_rolls[r].d1, g_rolls[r].d2,
                                     config, depth - 1, state, owner,
                                     candidates, MAX_PLAYS);
        if (count < 0) {
            free(candidates);
            return -1;
        }

        float theirs[GN_NUM_OUTPUTS];
        int failed;
        if (count > 0) {
            /* The best play's own distribution, at the depth its equity was
             * scored at -- `depth - 1`, mirroring `-V(result, depth - 1)`. */
            failed = position_probs(net, &candidates[0].play.result, config,
                                    depth - 1, swap_sides(state),
                                    mirror_owner(owner), theirs);
        } else {
            /* No legal play: the turn passes, exactly as in the scalar
             * recursion -- dropping the branch would bias the average. */
            GnPosition passed = *pos;
            gn_position_swap_turn(&passed);
            failed = position_probs(net, &passed, config, depth - 1,
                                    swap_sides(state), mirror_owner(owner),
                                    theirs);
        }
        if (failed != 0) {
            free(candidates);
            return -1;
        }

        float mine[GN_NUM_OUTPUTS];
        invert_probs(theirs, mine);
        for (int i = 0; i < GN_NUM_OUTPUTS; i++) {
            total[i] += g_rolls[r].weight * (double)mine[i];
        }
    }

    free(candidates);
    for (int i = 0; i < GN_NUM_OUTPUTS; i++) {
        out[i] = (float)total[i];
    }
    return 0;
}

int gn_search_probs(const GnNetwork *net, const GnPosition *pos,
                    const GnSearchConfig *config, float out[GN_NUM_OUTPUTS])
{
    if (net == NULL || pos == NULL || config == NULL || out == NULL) {
        return -1;
    }
    return position_probs(net, pos, config, config->ply, config->match,
                          config->cube_owner, out);
}

int gn_search_plays(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                    const GnSearchConfig *config,
                    GnCandidate *out, int max_out)
{
    if (config == NULL) {
        return -1;
    }
    return rank_plays(net, pos, d1, d2, config, config->ply, config->match,
                      config->cube_owner, out, max_out);
}

int gn_best_play(const GnNetwork *net, const GnPosition *pos, int d1, int d2,
                 const GnSearchConfig *config, GnCandidate *out)
{
    GnCandidate *candidates = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (candidates == NULL) {
        return -1;
    }
    const int count = gn_search_plays(net, pos, d1, d2, config,
                                      candidates, MAX_PLAYS);
    if (count > 0 && out != NULL) {
        *out = candidates[0];
    }
    free(candidates);
    return (count > 0) ? 0 : -1;
}

double gn_search_equity(const GnNetwork *net, const GnPosition *pos,
                        const GnSearchConfig *config)
{
    if (net == NULL || pos == NULL || config == NULL) {
        return 0.0;
    }
    return position_equity(net, pos, config, config->ply, config->match,
                           config->cube_owner);
}

/*
 * gn_rollout.c -- see gn_rollout.h for what this is for and what it refuses to do.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_rollout.h"

#include "gn_bearoff.h"
#include "gn_cube.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

/* A trial that has not ended by this many plies is abandoned and reported. Two
 * engines shuffling checkers can in principle wander a long time; a cap keeps a
 * measurement from hanging, and every abandoned trial is counted rather than
 * quietly averaged in as a draw. */
#define MAX_PLIES 4000

/* A cube past 2^20 changes nothing a money equity can express and would only
 * march toward integer overflow; further doubles are refused there. In real
 * trials the cube stays in single digits -- `average_cube` says so. */
#define MAX_CUBE (1L << 20)

/*
 * ── The dice, and why they are computed rather than drawn ────────────
 *
 * `roll_at` is a pure function of (seed, trial, ply). Nothing advances, nothing
 * is carried between calls. That is what makes common random numbers actually
 * common: two candidate plays explored in different orders, in different
 * processes, at different depths of the caller's own recursion, still see the
 * same dice at the same (trial, ply).
 *
 * A running generator would be equivalent ONLY as long as both variants
 * consumed exactly the same number of draws -- which they do not, since one may
 * end the game a ply earlier than the other. The failure would be silent: the
 * measurement would simply be noisier, and nothing would say why.
 *
 * The mixer is SplitMix64. It is not cryptography and does not need to be; what
 * it needs is to decorrelate nearby (trial, ply) pairs, which it does.
 */
static unsigned long long mix64(unsigned long long z)
{
    z += 0x9E3779B97F4A7C15ULL;
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

static void roll_at(unsigned long seed, unsigned long trial, unsigned int ply,
                    int *d1, int *d2)
{
    const unsigned long long value =
        mix64(((unsigned long long)seed << 32) ^ ((unsigned long long)trial << 12)
              ^ (unsigned long long)ply);
    *d1 = (int)((value >> 3) % 6u) + 1;
    *d2 = (int)((value >> 17) % 6u) + 1;
}

/*
 * The opening of a trial is NOT an opening roll. The position handed in already
 * says whose turn it is; re-deciding that from a die comparison would silently
 * hand the move to the wrong player half the time.
 */

/* Terminal value, from the point of view of `pos->turn` -- which at a finished
 * position names the LOSER, so this is always negative. Mirrors
 * `gn_terminal_equity`, which is the authority. */
static double terminal_equity(const GnPosition *pos)
{
    return gn_terminal_equity(pos);
}

/*
 * The cube verdict at one node of a trial, seen from the player on roll.
 *
 * Inside the two-sided table's domain the verdict is EXACT -- the three
 * stored cubeful equities feed spec §4's table directly, no model and no
 * `x`. Outside it, the fitted model decides (`gn_cube_decide`, money). This
 * is the same exact-first discipline as the search's leaf valuation, and it
 * is what makes the in-domain rollout a non-bias control rather than a
 * model echoing itself.
 */
static int cube_action(const GnNetwork *net, const GnPosition *pos, int owner,
                       const GnRolloutConfig *config, GnCubeAction *action)
{
    const GnBearoff *table = gn_bearoff_shared();
    double equities[4];

    if (table != NULL && gn_bearoff_equities(table, pos, equities)) {
        /* gn_bearoff.h's order: cubeless, owned, centred, opponent. */
        static const int index_of_owner[3] = {2, 1, 3};
        *action = gn_cube_verdict(equities[index_of_owner[owner]],
                                  2.0 * equities[3], 1.0);
        return 0;
    }

    float probs[GN_NUM_OUTPUTS];
    GnCubeDecision decision;
    if (gn_evaluate(net, pos, probs) != 0)
        return -1;
    if (gn_cube_decide(probs, (GnCubeOwner)owner, NULL,
                       config->cube_x[owner], config->jacoby, &decision) != 0)
        return -1;
    *action = decision.action;
    return 0;
}

/*
 * One trial. Returns the equity from `start`'s turn's point of view.
 *
 * `outcome` receives the signed points (positive if the player on roll at
 * `start` won), or 0 when the trial was truncated or abandoned; `finished` says
 * which.
 */
static int play_trial(const GnNetwork *net, const GnPosition *start,
                      const GnRolloutConfig *config, unsigned long trial,
                      double *equity, int *outcome, int *finished,
                      int *cashed, long *final_cube)
{
    GnPosition pos = *start;
    const int hero = (int)start->turn;

    /* The live cube of this trial: `owner` is always as seen by the player
     * on roll in `pos`, mirrored at every turn swap. Equities stay in units
     * of the INITIAL cube -- `cube` starts at 1 whatever the caller's real
     * stake, exactly as the cubeless rollout works per unit. */
    int owner = config->cube_owner;
    long cube = 1;

    /* The policy is copied so its cube viewpoint can follow the trial: a
     * cube-aware policy (`policy.use_cube`) must choose each move with the
     * CURRENT owner as the mover sees it, not the root's. */
    GnSearchConfig policy = config->policy;

    *outcome = 0;
    *finished = 0;
    *cashed = 0;
    *final_cube = 1;

    /*
     * The candidate buffer is allocated ONCE per trial, not once per ply.
     * `gn_search_plays` needs the whole buffer to rank at all -- passing
     * `max_out = 1` would make it evaluate only the first legal play and call it
     * the best, which is a different and much worse engine.
     */
    GnCandidate *buffer = malloc(sizeof(GnCandidate) * GN_MAX_PLAYS);
    if (buffer == NULL) {
        return -1;
    }

    for (unsigned int ply = 0; ply < MAX_PLIES; ply++) {
        if (gn_position_is_over(&pos)) {
            /* `gn_terminal_equity` answers for `pos.turn`, the loser. Translate
             * to the hero's point of view. */
            const double loser_equity = terminal_equity(&pos) * (double)cube;
            *equity = ((int)pos.turn == hero) ? loser_equity : -loser_equity;
            *outcome = (int)(-terminal_equity(&pos)) * (((int)pos.turn == hero) ? -1 : 1);
            *finished = 1;
            *final_cube = cube;
            free(buffer);
            return 0;
        }

        if (config->truncate && ply >= config->truncate) {
            /* The horizon: the network scores the position reached. Its answer
             * is for `pos.turn`; translate as above. */
            float probs[GN_NUM_OUTPUTS];
            if (gn_evaluate(net, &pos, probs) != 0) {
                free(buffer);
                return -1;
            }
            double value;
            if (config->use_cube) {
                /* The model's live curves already price every future double,
                 * so the horizon value is the cubeful leaf value times the
                 * stake reached -- the same valuation the search's leaves
                 * use, at the efficiency measured for this cube state. */
                int failed = 0;
                value = gn_cube_value(probs, (GnCubeOwner)owner, NULL,
                                      config->cube_x[owner], &failed)
                        * (double)cube;
                if (failed) {
                    free(buffer);
                    return -1;
                }
            } else {
                value = (double)gn_money_equity(probs);
            }
            *equity = ((int)pos.turn == hero) ? value : -value;
            *final_cube = cube;
            free(buffer);
            return 0;
        }

        if (config->use_cube && cube < MAX_CUBE
            && (ply > 0 || !config->cube_defer_first)
            && (owner == GN_CUBE_CENTRED || owner == GN_CUBE_OWNED)) {
            GnCubeAction action;
            if (cube_action(net, &pos, owner, config, &action) != 0) {
                free(buffer);
                return -1;
            }
            if (action == GN_DOUBLE_PASS) {
                /* The opponent concedes the CURRENT stake -- a pass never
                 * pays the doubled cube, spec §4. Not an outcome frequency:
                 * the game was not played out (`cashed`, not `finished`). */
                *equity = ((int)pos.turn == hero) ? (double)cube : -(double)cube;
                *cashed = 1;
                *final_cube = cube;
                free(buffer);
                return 0;
            }
            if (action == GN_DOUBLE_TAKE) {
                cube *= 2;
                owner = GN_CUBE_OPPONENT;
            }
            /* TOO_GOOD and NO_DOUBLE both mean: play on. */
        }

        int d1, d2;
        roll_at(config->seed, trial, ply, &d1, &d2);

        /*
         * `gn_search_plays`, NOT `gn_best_play`. The latter returns 0 on success
         * and -1 for BOTH "no legal play" and "error", so it cannot tell a
         * legitimate pass from a failure -- and reading its 0 as "no play"
         * produced a rollout in which the position never moved. Nothing crashed;
         * a perfectly plausible +0.619393 came out; only a standard error of
         * EXACTLY zero gave it away, because every trial had played the same
         * non-game.
         *
         * Here the count says which is which: negative is an error, zero is a
         * legitimate pass, positive is a play.
         */
        if (policy.use_cube) {
            policy.cube_owner = owner;
        }
        const int count = gn_search_plays(net, &pos, d1, d2, &policy,
                                          buffer, GN_MAX_PLAYS);
        if (count < 0) {
            free(buffer);
            return -1;
        }
        if (count == 0) {
            /* No legal play is an outcome of the rules, not a failure: the turn
             * simply passes. */
            gn_position_swap_turn(&pos);
            owner = (int)gn_cube_mirror((GnCubeOwner)owner);
            continue;
        }
        pos = buffer[0].play.result;
        owner = (int)gn_cube_mirror((GnCubeOwner)owner);
    }

    /* Abandoned. Reported by the caller, never averaged in. */
    free(buffer);
    *equity = 0.0;
    return 1;
}

void gn_rollout_roll(unsigned long seed, unsigned long trial, unsigned int ply,
                     int *d1, int *d2)
{
    roll_at(seed, trial, ply, d1, d2);
}

GnRolloutConfig gn_rollout_config(unsigned long seed)
{
    GnRolloutConfig config;
    memset(&config, 0, sizeof(config));
    /* 1296 = 36^2: a whole number of two-roll sequences, which keeps the
     * opening dice balanced when the caller does not shuffle them further. */
    config.trials = 1296;
    /* Eleven plies reaches well past the tactical horizon of most positions
     * while cutting the tail that carries most of the variance. It is a
     * starting point to be MEASURED against an untruncated run, not a
     * constant to be trusted. */
    config.truncate = 11;
    config.policy = gn_search_config(0);
    config.seed = seed;
    return config;
}

int gn_rollout(const GnNetwork *net, const GnPosition *pos,
               const GnRolloutConfig *config, GnRolloutResult *out)
{
    if (net == NULL || pos == NULL || config == NULL || out == NULL) {
        return -1;
    }

    memset(out, 0, sizeof(*out));

    double sum = 0.0;
    double sum_squares = 0.0;
    double sum_cube = 0.0;
    unsigned long counted = 0;

    for (unsigned long trial = 0; trial < config->trials; trial++) {
        double equity;
        int outcome, finished, cashed;
        long final_cube;
        const int status = play_trial(net, pos, config, trial, &equity,
                                      &outcome, &finished, &cashed,
                                      &final_cube);
        if (status < 0) {
            return -1;
        }
        if (status == 1) {
            out->stalled++;
            continue;
        }

        sum += equity;
        sum_squares += equity * equity;
        sum_cube += (double)final_cube;
        if (cashed) {
            out->cashed++;
        }
        counted++;

        if (finished) {
            /* Nested convention, as the network emits it. */
            if (outcome > 0) {
                out->frequencies[0] += 1.0;
                if (outcome >= 2) out->frequencies[1] += 1.0;
                if (outcome >= 3) out->frequencies[2] += 1.0;
            } else {
                if (outcome <= -2) out->frequencies[3] += 1.0;
                if (outcome <= -3) out->frequencies[4] += 1.0;
            }
        }
    }

    out->trials = counted;
    if (counted == 0) {
        return -1;
    }

    out->equity = sum / (double)counted;
    out->average_cube = config->use_cube ? sum_cube / (double)counted : 0.0;
    if (counted > 1) {
        const double variance =
            (sum_squares - sum * sum / (double)counted) / (double)(counted - 1);
        out->standard_error = sqrt(variance > 0.0 ? variance / (double)counted : 0.0);
    }

    /* Frequencies only mean something for an untruncated rollout; a truncated
     * one ends on an evaluation, not on an outcome. Left at zero rather than
     * filled with a fraction of the trials, which would look like a
     * distribution and be one only in part. Cubeful trials ended by a pass are
     * NOT in them either -- those games were conceded, not played out, and
     * `cashed` reports them; the frequencies are fractions of ALL counted
     * trials, so with a live cube they no longer sum to about 1. */
    if (config->truncate) {
        memset(out->frequencies, 0, sizeof(out->frequencies));
    } else {
        for (int i = 0; i < GN_NUM_OUTPUTS; i++) {
            out->frequencies[i] /= (double)counted;
        }
    }
    return 0;
}

int gn_rollout_candidates(const GnNetwork *net, const GnPosition *results,
                          int count, const GnRolloutConfig *config,
                          double *equities, double *standard_errors)
{
    if (net == NULL || results == NULL || config == NULL || equities == NULL
        || count <= 0) {
        return -1;
    }

    for (int i = 0; i < count; i++) {
        GnRolloutResult result;
        if (gn_rollout(net, &results[i], config, &result) != 0) {
            return -1;
        }
        /* `results[i]` has already handed the turn over, so the rollout answered
         * for the OPPONENT. The mover's equity is the negation -- the same
         * negation that runs through gn_search.c, and the same one that turns an
         * engine into its own opponent when it is forgotten. */
        equities[i] = -result.equity;
        if (standard_errors != NULL) {
            standard_errors[i] = result.standard_error;
        }
    }
    return 0;
}

int gn_rollout_difference(const GnNetwork *net,
                          const GnPosition *a, const GnPosition *b,
                          const GnRolloutConfig *config,
                          double *difference, double *standard_error)
{
    if (net == NULL || a == NULL || b == NULL || config == NULL
        || difference == NULL) {
        return -1;
    }

    double sum = 0.0;
    double sum_squares = 0.0;
    unsigned long counted = 0;

    for (unsigned long trial = 0; trial < config->trials; trial++) {
        double equity_a, equity_b;
        int outcome, finished, cashed;
        long final_cube;

        /* THE SAME TRIAL INDEX ON BOTH SIDES. That is the entire mechanism:
         * `roll_at` is a pure function of (seed, trial, ply), so both variants
         * meet identical dice at identical plies, and the dice cancel out of the
         * difference. */
        int status = play_trial(net, a, config, trial, &equity_a, &outcome,
                                &finished, &cashed, &final_cube);
        if (status < 0) return -1;
        if (status == 1) continue;

        status = play_trial(net, b, config, trial, &equity_b, &outcome,
                            &finished, &cashed, &final_cube);
        if (status < 0) return -1;
        if (status == 1) continue;

        /* Both are seen by the opponent -- each result has handed the turn over.
         * Negating both would leave the difference unchanged in magnitude but
         * flip its sign, so it is done once, here, deliberately. */
        const double paired = -(equity_a - equity_b);
        sum += paired;
        sum_squares += paired * paired;
        counted++;
    }

    if (counted == 0) {
        return -1;
    }

    *difference = sum / (double)counted;
    if (standard_error != NULL) {
        double error = 0.0;
        if (counted > 1) {
            const double variance =
                (sum_squares - sum * sum / (double)counted) / (double)(counted - 1);
            error = sqrt(variance > 0.0 ? variance / (double)counted : 0.0);
        }
        *standard_error = error;
    }
    return 0;
}

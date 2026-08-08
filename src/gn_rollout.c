/*
 * gn_rollout.c -- see gn_rollout.h for what this is for and what it refuses to do.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_rollout.h"

#include "gn_bearoff.h"
#include "gn_cube.h"
#include "gn_met.h"

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
                       const GnRolloutConfig *config, const GnMatchState *state,
                       GnCubeAction *action)
{
    /* The exact table's stored cubeful equities are MONEY equities; at a
     * score they answer a different question, so the table only ever decides
     * money trials. Match verdicts always go through the §9 recursion. */
    if (state == NULL) {
        const GnBearoff *table = gn_bearoff_shared();
        double equities[4];

        if (table != NULL && gn_bearoff_equities(table, pos, equities)) {
            /* gn_bearoff.h's order: cubeless, owned, centred, opponent. */
            static const int index_of_owner[3] = {2, 1, 3};
            *action = gn_cube_verdict(equities[index_of_owner[owner]],
                                      2.0 * equities[3], 1.0);
            return 0;
        }
    }

    float probs[GN_NUM_OUTPUTS];
    GnCubeDecision decision;
    if (gn_evaluate(net, pos, probs) != 0)
        return -1;
    if (gn_cube_decide(probs, (GnCubeOwner)owner, state,
                       config->cube_x[owner], config->jacoby, &decision) != 0)
        return -1;
    *action = decision.action;
    return 0;
}

/*
 * Best-play cubeless equity for one specific roll, from the MOVER's point of
 * view, at 0-ply. This is the evaluator behind the luck correction; its only
 * obligations are to be FIXED (the same h everywhere) and cheap. A roll with
 * no legal play is worth the position itself, turn passed -- an outcome of the
 * rules, not a failure.
 */
static int roll_equity(const GnNetwork *net, const GnPosition *pos,
                       int d1, int d2, const GnSearchConfig *zero,
                       GnCandidate *buffer, double *out)
{
    const int count = gn_search_plays(net, pos, d1, d2, zero,
                                      buffer, GN_MAX_PLAYS);
    if (count < 0) {
        return -1;
    }
    if (count == 0) {
        GnPosition passed = *pos;
        gn_position_swap_turn(&passed);
        float probs[GN_NUM_OUTPUTS];
        if (gn_evaluate(net, &passed, probs) != 0) {
            return -1;
        }
        /* The evaluation answers for the opponent, now on roll. */
        *out = -(double)gn_money_equity(probs);
        return 0;
    }
    *out = buffer[0].equity;
    return 0;
}

/*
 * The luck of throwing (d1, d2) here: best-play equity under that roll minus
 * the 21-roll weighted average, mover's point of view. Zero-mean given `pos`
 * by construction -- the actual roll is one of the terms being averaged.
 */
static int roll_luck(const GnNetwork *net, const GnPosition *pos,
                     int d1, int d2, const GnSearchConfig *zero,
                     GnCandidate *buffer, double *out)
{
    const int lo = d1 < d2 ? d1 : d2;
    const int hi = d1 < d2 ? d2 : d1;
    double expected = 0.0;
    double actual = 0.0;

    for (int i = 1; i <= 6; i++) {
        for (int j = i; j <= 6; j++) {
            double equity;
            if (roll_equity(net, pos, i, j, zero, buffer, &equity) != 0) {
                return -1;
            }
            expected += equity * ((i == j) ? 1.0 : 2.0) / 36.0;
            if (i == lo && j == hi) {
                actual = equity;
            }
        }
    }
    *out = actual - expected;
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
                      int *cashed, long *final_cube, double *luck)
{
    GnPosition pos = *start;
    const int hero = (int)start->turn;

    /* The live cube of this trial: `owner` is always as seen by the player
     * on roll in `pos`, mirrored at every turn swap. Equities stay in units
     * of the INITIAL cube -- `cube` starts at 1 whatever the caller's real
     * stake, exactly as the cubeless rollout works per unit. */
    int owner = config->cube_owner;

    /* Money trials count in units of the initial cube; match trials carry
     * the REAL cube, because the score reached depends on it. `state` is
     * always as seen by the player on roll in `pos`, swapped at every turn
     * exactly like `owner` is mirrored. */
    long cube = config->use_match ? config->match.cube : 1;
    GnMatchState state = config->match;

    /* The policy is copied so its cube viewpoint can follow the trial: a
     * cube-aware policy (`policy.use_cube`) must choose each move with the
     * CURRENT owner as the mover sees it, not the root's. */
    GnSearchConfig policy = config->policy;

    *outcome = 0;
    *finished = 0;
    *cashed = 0;
    *final_cube = 1;
    *luck = 0.0;

    /* The luck evaluator: fixed, cheap, and the SAME whatever the policy --
     * a correction whose h drifted with the policy would still be zero-mean,
     * but no two measurements would be comparable. */
    const GnSearchConfig zero = gn_search_config(0);

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
            double loser_value;
            if (config->use_match) {
                /* The game becomes points, the points a score, the score a
                 * match winning chance -- `gn_met_after` handles Crawford
                 * being behind us and the match being over outright. */
                const int points = (int)(-terminal_equity(&pos)) * (int)cube;
                const double mwc = gn_met_after(&state, points, 0);
                if (mwc < 0.0) {
                    free(buffer);
                    return -1;
                }
                loser_value = 2.0 * mwc - 1.0;
            } else {
                loser_value = terminal_equity(&pos) * (double)cube;
            }
            *equity = ((int)pos.turn == hero) ? loser_value : -loser_value;
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
            if (config->use_match && config->use_cube) {
                /* §9 recursion at the horizon: the state reached carries its
                 * own cube, so no scaling -- the value IS match equity. */
                int failed = 0;
                value = gn_cube_value(probs, (GnCubeOwner)owner, &state,
                                      config->cube_x[owner], &failed);
                if (failed) {
                    free(buffer);
                    return -1;
                }
            } else if (config->use_match) {
                /* Frozen cube: the horizon is worth its cubeless match
                 * winning chance at the state reached. */
                const double mwc = gn_match_winning_chance(&state, probs);
                if (mwc < 0.0) {
                    free(buffer);
                    return -1;
                }
                value = 2.0 * mwc - 1.0;
            } else if (config->use_cube) {
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

        /* Nobody doubles during the Crawford game, and a cube that already
         * covers both away scores is dead -- doubling it changes no score
         * either game end could reach. */
        const int match_cube_is_dead =
            config->use_match
            && (state.crawford
                || (cube >= state.away_on_roll && cube >= state.away_opponent));

        if (config->use_cube && cube < MAX_CUBE && !match_cube_is_dead
            && (ply > 0 || !config->cube_defer_first)
            && (owner == GN_CUBE_CENTRED || owner == GN_CUBE_OWNED)) {
            GnCubeAction action;
            if (cube_action(net, &pos, owner, config,
                            config->use_match ? &state : NULL, &action) != 0) {
                free(buffer);
                return -1;
            }
            if (action == GN_DOUBLE_PASS) {
                /* The opponent concedes the CURRENT stake -- a pass never
                 * pays the doubled cube, spec §4. Not an outcome frequency:
                 * the game was not played out (`cashed`, not `finished`). */
                double winner_value;
                if (config->use_match) {
                    const double mwc = gn_met_after(&state, (int)cube, 1);
                    if (mwc < 0.0) {
                        free(buffer);
                        return -1;
                    }
                    winner_value = 2.0 * mwc - 1.0;
                } else {
                    winner_value = (double)cube;
                }
                *equity = ((int)pos.turn == hero) ? winner_value : -winner_value;
                *cashed = 1;
                *final_cube = cube;
                free(buffer);
                return 0;
            }
            if (action == GN_DOUBLE_TAKE) {
                cube *= 2;
                owner = GN_CUBE_OPPONENT;
                state.cube = (int)cube;
            }
            /* TOO_GOOD and NO_DOUBLE both mean: play on. */
        }

        int d1, d2;
        roll_at(config->seed, trial, ply, &d1, &d2);

        if (config->variance_reduction) {
            /* The buffer is free here -- the policy's search below refills it.
             * The luck is the mover's; translate to the hero's view and scale
             * by the live cube, like every other equity in the trial. */
            double this_luck;
            if (roll_luck(net, &pos, d1, d2, &zero, buffer, &this_luck) != 0) {
                free(buffer);
                return -1;
            }
            if (config->use_match) {
                /* The luck evaluator speaks money-per-unit-cube; a match
                 * trial is scored in match equity. The bridge is the span
                 * of a plain game at the current cube: winning it versus
                 * losing it moves the match equity by 2*(win - lose) for a
                 * swing of 2 money points -- so (win - lose) per point. Any
                 * fixed scale keeps the correction zero-mean; a wrong one
                 * would only shrink the reduction, visibly, in the se. */
                const double win = gn_met_after(&state, (int)cube, 1);
                const double lose = gn_met_after(&state, (int)cube, 0);
                if (win < 0.0 || lose < 0.0) {
                    free(buffer);
                    return -1;
                }
                this_luck *= win - lose;
            } else {
                this_luck *= (double)cube;
            }
            *luck += ((int)pos.turn == hero) ? this_luck : -this_luck;
        }

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
        if (policy.use_match) {
            /* A match-aware policy chooses each move at the score and cube
             * the trial has REACHED, as the mover sees them. */
            policy.match = state;
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
            state = gn_match_state_swap(state);
            continue;
        }
        pos = buffer[0].play.result;
        owner = (int)gn_cube_mirror((GnCubeOwner)owner);
        state = gn_match_state_swap(state);
    }

    /* Abandoned. Reported by the caller, never averaged in. */
    free(buffer);
    *equity = 0.0;
    return 1;
}

/* Standard error of the running mean; HUGE_VAL below two trials so no stop
 * rule can trigger on a sample that cannot even estimate its spread. */
static double running_se(double sum, double sum_squares, unsigned long n)
{
    if (n < 2) {
        return HUGE_VAL;
    }
    const double variance =
        (sum_squares - sum * sum / (double)n) / (double)(n - 1);
    return sqrt(variance > 0.0 ? variance / (double)n : 0.0);
}

/* The stop-on-interval rule, checked on whole roll families only. */
static int interval_reached(const GnRolloutConfig *config, double sum,
                            double sum_squares, unsigned long counted)
{
    if (config->target_se <= 0.0 || counted % 36 != 0
        || counted < config->min_trials) {
        return 0;
    }
    return running_se(sum, sum_squares, counted) <= config->target_se;
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
    if (config->use_match && !gn_match_state_is_valid(&config->match)) {
        /* Refused, never approximated: a rollout that silently valued a
         * 30-point match as money would look exactly like a measurement. */
        return -1;
    }

    memset(out, 0, sizeof(*out));

    double sum = 0.0;
    double sum_squares = 0.0;
    double sum_cube = 0.0;
    double sum_luck = 0.0;
    unsigned long counted = 0;

    for (unsigned long trial = 0; trial < config->trials; trial++) {
        double equity, luck;
        int outcome, finished, cashed;
        long final_cube;
        const int status = play_trial(net, pos, config, trial, &equity,
                                      &outcome, &finished, &cashed,
                                      &final_cube, &luck);
        if (status < 0) {
            return -1;
        }
        if (status == 1) {
            out->stalled++;
            continue;
        }

        /* The corrected estimator: same expectation, less dice. */
        const double corrected = equity - luck;
        sum += corrected;
        sum_squares += corrected * corrected;
        sum_luck += luck;
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

        if (interval_reached(config, sum, sum_squares, counted)) {
            break;
        }
    }

    out->trials = counted;
    if (counted == 0) {
        return -1;
    }

    out->equity = sum / (double)counted;
    out->average_luck = sum_luck / (double)counted;
    out->average_cube = config->use_cube ? sum_cube / (double)counted : 0.0;
    if (counted > 1) {
        out->standard_error = running_se(sum, sum_squares, counted);
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
    if (config->use_match && !gn_match_state_is_valid(&config->match)) {
        return -1;
    }

    double sum = 0.0;
    double sum_squares = 0.0;
    unsigned long counted = 0;

    for (unsigned long trial = 0; trial < config->trials; trial++) {
        double equity_a, equity_b, luck_a, luck_b;
        int outcome, finished, cashed;
        long final_cube;

        /* THE SAME TRIAL INDEX ON BOTH SIDES. That is the entire mechanism:
         * `roll_at` is a pure function of (seed, trial, ply), so both variants
         * meet identical dice at identical plies, and the dice cancel out of the
         * difference. */
        int status = play_trial(net, a, config, trial, &equity_a, &outcome,
                                &finished, &cashed, &final_cube, &luck_a);
        if (status < 0) return -1;
        if (status == 1) continue;

        status = play_trial(net, b, config, trial, &equity_b, &outcome,
                            &finished, &cashed, &final_cube, &luck_b);
        if (status < 0) return -1;
        if (status == 1) continue;

        /* Both are seen by the opponent -- each result has handed the turn over.
         * Negating both would leave the difference unchanged in magnitude but
         * flip its sign, so it is done once, here, deliberately.
         *
         * With variance reduction on, each side is corrected by its OWN luck:
         * the common dice already cancel the shared luck, the correction mops
         * up what remains after the trajectories diverge. */
        const double paired = -((equity_a - luck_a) - (equity_b - luck_b));
        sum += paired;
        sum_squares += paired * paired;
        counted++;

        /* Stopping on the error of the DIFFERENCE -- see the header note. */
        if (interval_reached(config, sum, sum_squares, counted)) {
            break;
        }
    }

    if (counted == 0) {
        return -1;
    }

    *difference = sum / (double)counted;
    if (standard_error != NULL) {
        *standard_error = counted > 1 ? running_se(sum, sum_squares, counted) : 0.0;
    }
    return 0;
}

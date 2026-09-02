/*
 * bench_decision.c -- one 2-ply decision, end to end, without Python.
 *
 * WHY
 *
 * `docs/mesures/2026-08-26-T3A-branchement.md` established that big-network
 * evaluations no longer bound a decision: removing 4.7x of them moved the
 * time by under 3%. What DOES bound it was named there as a question, not an
 * answer -- move generation, position copies, sorting, recursion.
 *
 * Answering it needs a driver with nothing else in the frame. The Python
 * benches measure ctypes and process contention along with the search; this
 * one measures the search. It is also the thing to run under callgrind, which
 * counts instructions exactly rather than sampling:
 *
 *     valgrind --tool=callgrind --callgrind-out-file=cg.out \
 *         build/bench_decision models/cubeless_prob5_512_512_256_128.bin 3
 *     callgrind_annotate cg.out | head -40
 *
 * The setting is T35's: 2-ply, filter (0,1,3). Any other setting would measure
 * a decision this project does not make.
 *
 *   bench_decision <model.bin> [decisions] [prune.bin] [k] [options]
 *
 * OPTIONS -- ADDED BY T85, AND WHY THEY EXIST
 *
 *   --cube[=x]        value leaves through the cube model (`use_cube`)
 *   --owner=centred|owned|opponent    the root cube state (default centré)
 *   --match=a/b       value at a score, a-away on roll against b-away
 *   --crawford        that score is the Crawford game
 *   --repeat=n        time the whole set n times and report the MEDIAN
 *   --ab              alternate the configuration WITH and WITHOUT the cube,
 *                     decision by decision, and report both
 *
 * `docs/mesures/2026-09-02-optimisation-mesures-d-entree.md` §5 could only
 * state the cost of the cube in a decision as a PRODUCT -- a per-call cost
 * from `bench_cube` times a node count -- and said so in its own reserve,
 * because this program could not switch the cube on. It can now, so that
 * figure is a timing.
 *
 * THE DECISIONS ARE RECORDED FIRST, THEN TIMED
 *
 * Turning the cube on changes which play is best, so a driver that advances
 * the game with its own answers would measure a DIFFERENT sequence of
 * positions in each configuration -- and a cubeless/cubeful comparison would
 * be partly a comparison of two games. So the walk is done once, untimed, by
 * the baseline (cubeless) configuration, and every timed run replays exactly
 * those (position, dice) triples. The cubeless numbers are unchanged by this:
 * the recorded walk IS the walk this program has always done.
 *
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gn_cube.h"
#include "gn_infer.h"
#include "gn_met.h"
#include "gn_rules.h"
#include "gn_search.h"

#define MAX_PLAYS 2048
#define DEFAULT_DECISIONS 20
#define MAX_DECISIONS 4096

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static unsigned long g_state = 20260826UL;

static int roll(void)
{
    g_state = g_state * 6364136223846793005UL + 1442695040888963407UL;
    return (int)((g_state >> 33) % 6) + 1;
}

static int compare_doubles(const void *a, const void *b)
{
    const double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

/* Cube efficiencies as MEASURED (docs/mesures/2026-08-07-T34-ajustement.md),
 * indexed by ownership -- centred, owned, opponent's. Same table as
 * bench/bench_cube.c: there is no single default, and inventing one for every
 * ownership state is a mistake this project has already made once. */
static const double EFFICIENCY[3] = {0.688, 0.566, 0.687};

typedef struct {
    GnPosition pos;
    int d1, d2;
} GnDecisionCase;

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr,
                "usage: %s <model.bin> [decisions] [prune.bin] [k] "
                "[--cube[=x]] [--owner=centred|owned|opponent] "
                "[--match=a/b] [--crawford] [--repeat=n]\n", argv[0]);
        return 2;
    }

    /* Positional arguments, options anywhere: the four positionals are the
     * interface every published measurement used, and the options are new. */
    const char *positional[8];
    int positionals = 0;
    int use_cube = 0, crawford = 0, repeat = 1, ab = 0;
    int owner = GN_CUBE_CENTRED;
    double efficiency = -1.0;
    int away_on_roll = 0, away_opponent = 0;

    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "--", 2) != 0) {
            if (positionals < 8) {
                positional[positionals++] = argv[i];
            }
            continue;
        }
        if (strncmp(argv[i], "--cube", 6) == 0) {
            use_cube = 1;
            if (argv[i][6] == '=') {
                efficiency = atof(argv[i] + 7);
            }
        } else if (strncmp(argv[i], "--owner=", 8) == 0) {
            const char *v = argv[i] + 8;
            if (strcmp(v, "owned") == 0) owner = GN_CUBE_OWNED;
            else if (strcmp(v, "opponent") == 0) owner = GN_CUBE_OPPONENT;
            else if (strcmp(v, "centred") == 0) owner = GN_CUBE_CENTRED;
            else { fprintf(stderr, "possesseur inconnu : %s\n", v); return 2; }
        } else if (strncmp(argv[i], "--match=", 8) == 0) {
            if (sscanf(argv[i] + 8, "%d/%d", &away_on_roll, &away_opponent) != 2
                || away_on_roll <= 0 || away_opponent <= 0) {
                fprintf(stderr, "score illisible : %s\n", argv[i] + 8);
                return 2;
            }
        } else if (strcmp(argv[i], "--crawford") == 0) {
            crawford = 1;
        } else if (strcmp(argv[i], "--ab") == 0) {
            ab = 1;
        } else if (strncmp(argv[i], "--repeat=", 9) == 0) {
            repeat = atoi(argv[i] + 9);
            if (repeat < 1) repeat = 1;
        } else {
            fprintf(stderr, "option inconnue : %s\n", argv[i]);
            return 2;
        }
    }
    if (positionals < 1) {
        fprintf(stderr, "modèle manquant\n");
        return 2;
    }

    int decisions = (positionals > 1) ? atoi(positional[1]) : DEFAULT_DECISIONS;
    if (decisions < 1) decisions = 1;
    if (decisions > MAX_DECISIONS) decisions = MAX_DECISIONS;

    GnNetwork *net = gn_network_load(positional[0]);
    if (net == NULL) {
        fprintf(stderr, "modèle refusé : %s\n", positional[0]);
        return 1;
    }
    GnNetwork *prune = NULL;
    int k = 0;
    if (positionals > 3) {
        prune = gn_network_load(positional[2]);
        k = atoi(positional[3]);
        if (prune == NULL) {
            fprintf(stderr, "réseau d'élagage refusé : %s\n", positional[2]);
            return 1;
        }
    }

    /* The baseline: cubeless money, the configuration every published figure
     * of this bench used, and the one that records the walk. */
    GnSearchConfig baseline = gn_search_config(2);
    baseline.filter[1] = 1;
    baseline.filter[2] = 3;
    if (prune != NULL) {
        gn_search_use_prune(&baseline, prune, k);
    }

    /* The configuration actually timed. */
    GnSearchConfig config = baseline;
    GnMatchState state;
    memset(&state, 0, sizeof(state));
    if (away_on_roll > 0) {
        state.away_on_roll = away_on_roll;
        state.away_opponent = away_opponent;
        state.cube = 1;
        state.crawford = crawford;
        GnSearchConfig at_score = gn_search_config_match(2, &state);
        if (!at_score.use_match) {
            fprintf(stderr, "score inévaluable : %d-away/%d-away\n",
                    away_on_roll, away_opponent);
            return 1;
        }
        config.use_match = 1;
        config.match = state;
    }
    if (use_cube) {
        gn_search_use_cube(&config, owner,
                           (efficiency >= 0.0) ? efficiency
                                               : EFFICIENCY[owner]);
    }

    /*
     * THE A/B COMPANION, AND WHY IT IS INTERLEAVED PER DECISION
     *
     * The machine these measurements are taken on is shared, and the entry
     * relevé of 2026-09-02 measured its own noise floor at +-8 % between two
     * consecutive runs of the SAME binary and +-22 % across a session. A cube
     * cost obtained by subtracting two whole runs is therefore a difference of
     * two numbers each carrying more error than the difference itself.
     *
     * `--ab` times the two configurations decision by decision inside one
     * process: whatever the machine is doing, it is doing it to both. The
     * ratio survives a drift that would swamp the two absolutes.
     */
    GnSearchConfig config_a = config;
    config_a.use_cube = 0;

    GnCandidate *out = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    GnDecisionCase *cases = malloc(sizeof(GnDecisionCase) * (size_t)decisions);
    double *samples = malloc(sizeof(double) * (size_t)repeat);
    double *samples_a = malloc(sizeof(double) * (size_t)repeat);
    if (out == NULL || cases == NULL || samples == NULL || samples_a == NULL) {
        return 1;
    }

    /* ── The walk, untimed: record the decisions, do not measure them. ─── */
    GnPosition pos;
    gn_position_initial(&pos);
    int done = 0;

    while (done < decisions) {
        if (gn_position_is_over(&pos)) {
            gn_position_initial(&pos);
            continue;
        }
        const int d1 = roll(), d2 = roll();
        const int count = gn_search_plays(net, &pos, d1, d2, &baseline, out,
                                          MAX_PLAYS);
        /* Positions from real play, and only those with a genuine choice: a
         * forced move is not a decision, and averaging it in would flatter
         * the cost. */
        if (count > 1) {
            cases[done].pos = pos;
            cases[done].d1 = d1;
            cases[done].d2 = d2;
            done++;
        }
        if (count > 0) {
            pos = out[0].play.result;
        } else {
            gn_position_swap_turn(&pos);
        }
    }

    /* ── The timed runs, over exactly those decisions. ──────────────────── */
    unsigned long big = 0, small = 0, cube_nodes = 0;

    for (int r = 0; r < repeat; r++) {
        double total = 0.0, total_a = 0.0;
        big = small = cube_nodes = 0;
        for (int i = 0; i < decisions; i++) {
            if (ab) {
                const double start_a = now_seconds();
                gn_search_plays(net, &cases[i].pos, cases[i].d1, cases[i].d2,
                                &config_a, out, MAX_PLAYS);
                total_a += now_seconds() - start_a;
            }
            gn_search_reset_evaluations();
            const double start = now_seconds();
            gn_search_plays(net, &cases[i].pos, cases[i].d1, cases[i].d2,
                            &config, out, MAX_PLAYS);
            total += now_seconds() - start;
            big += gn_search_evaluations();
            small += gn_search_prune_evaluations();
            cube_nodes += gn_search_cube_valuations();
        }
        samples[r] = total / decisions;
        samples_a[r] = total_a / decisions;
    }
    qsort(samples, (size_t)repeat, sizeof(double), compare_doubles);
    qsort(samples_a, (size_t)repeat, sizeof(double), compare_doubles);
    const double median = samples[repeat / 2];
    const double median_a = samples_a[repeat / 2];

#ifdef GN_BATCH_FILL_STATS
    {
        extern unsigned long gn_batch_fill_calls, gn_batch_fill_live;
        extern unsigned long gn_batch_fill_hist[];
        printf("\ntaille des demandes de lot (le noyau calcule toujours %d voies) :\n",
               GN_EVAL_BATCH);
        printf("  %lu appels, %lu voies vivantes, remplissage moyen %.1f/%d "
               "= %.1f %%\n", gn_batch_fill_calls, gn_batch_fill_live,
               (double)gn_batch_fill_live / (double)gn_batch_fill_calls,
               GN_EVAL_BATCH,
               100.0 * (double)gn_batch_fill_live
                   / ((double)gn_batch_fill_calls * GN_EVAL_BATCH));
        printf("  histogramme :");
        for (int i = 1; i <= 256; i++) {
            if (gn_batch_fill_hist[i]) {
                printf(" %d:%lu", i, gn_batch_fill_hist[i]);
            }
        }
        printf("\n");
    }
#endif
#ifdef GN_BATCH_FILL_STATS
    {
        extern unsigned long gn_fill_calls[2], gn_fill_live[2];
        static const char *label[2] = {"grand", "petit"};
        printf("\nremplissage par réseau (le noyau calcule toujours %d voies) :\n",
               GN_EVAL_BATCH);
        for (int s = 0; s < 2; s++) {
            if (!gn_fill_calls[s]) continue;
            printf("  %-6s %8lu appels, %9lu voies vivantes, "
                   "remplissage %.1f/%d = %.1f %%  → %lu voies calculées\n",
                   label[s], gn_fill_calls[s], gn_fill_live[s],
                   (double)gn_fill_live[s] / (double)gn_fill_calls[s],
                   GN_EVAL_BATCH,
                   100.0 * (double)gn_fill_live[s]
                       / ((double)gn_fill_calls[s] * GN_EVAL_BATCH),
                   gn_fill_calls[s] * GN_EVAL_BATCH);
        }
    }
#endif
    printf("%d décisions 2-ply filtre (0,1,3)%s\n", decisions,
           (prune != NULL) ? ", élagage actif" : "");
    if (config.use_match) {
        printf("  score : %d-away/%d-away%s\n", away_on_roll, away_opponent,
               crawford ? ", Crawford" : "");
    } else {
        printf("  money\n");
    }
    if (use_cube) {
        static const char *owner_label[3] = {"centré", "possédé", "adverse"};
        printf("  videau : actif, %s, efficacité %.3f\n", owner_label[owner],
               config.cube_x);
    } else {
        printf("  videau : inactif (cubeless)\n");
    }
    printf("  %.4f s/décision", median);
    if (repeat > 1) {
        printf("  (médiane de %d ; min %.4f, max %.4f)", repeat, samples[0],
               samples[repeat - 1]);
    }
    printf("\n");
    printf("  %lu évaluations du grand réseau par décision\n",
           big / (unsigned long)decisions);
    if (prune != NULL) {
        printf("  %lu évaluations du petit réseau par décision\n",
               small / (unsigned long)decisions);
    }
    /* The denominator T85 needed: nodes REALLY valued by the model, counted
     * rather than assumed equal to the evaluation count. */
    printf("  %lu valuations du videau par décision\n",
           cube_nodes / (unsigned long)decisions);
    if (ab) {
        const double delta = median - median_a;
        printf("  A/B entrelacé : sans videau %.4f s, avec %.4f s\n",
               median_a, median);
        printf("    le videau coûte %.1f ms/décision, %.1f %% du total, "
               "%.1f ns/valuation\n", delta * 1e3, 100.0 * delta / median,
               (cube_nodes == 0) ? 0.0
                   : delta * 1e9 / ((double)cube_nodes / decisions));
    }

    free(samples_a);
    free(samples);
    free(cases);
    free(out);
    gn_network_free(net);
    if (prune != NULL) {
        gn_network_free(prune);
    }
    return 0;
}

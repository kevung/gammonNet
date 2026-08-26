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
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "gn_infer.h"
#include "gn_rules.h"
#include "gn_search.h"

#define MAX_PLAYS 2048
#define DEFAULT_DECISIONS 20

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

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <model.bin> [decisions] [prune.bin] [k]\n",
                argv[0]);
        return 2;
    }
    const int decisions = (argc > 2) ? atoi(argv[2]) : DEFAULT_DECISIONS;

    GnNetwork *net = gn_network_load(argv[1]);
    if (net == NULL) {
        fprintf(stderr, "modèle refusé : %s\n", argv[1]);
        return 1;
    }
    GnNetwork *prune = NULL;
    int k = 0;
    if (argc > 4) {
        prune = gn_network_load(argv[3]);
        k = atoi(argv[4]);
        if (prune == NULL) {
            fprintf(stderr, "réseau d'élagage refusé : %s\n", argv[3]);
            return 1;
        }
    }

    GnSearchConfig config = gn_search_config(2);
    config.filter[1] = 1;
    config.filter[2] = 3;
    if (prune != NULL) {
        gn_search_use_prune(&config, prune, k);
    }

    GnCandidate *out = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (out == NULL) {
        return 1;
    }

    /* Positions from real play, and only those with a genuine choice: a
     * forced move is not a decision, and averaging it in would flatter the
     * cost. */
    GnPosition pos;
    gn_position_initial(&pos);
    int done = 0;
    double total = 0.0;
    unsigned long big = 0, small = 0;

    while (done < decisions) {
        if (gn_position_is_over(&pos)) {
            gn_position_initial(&pos);
            continue;
        }
        const int d1 = roll(), d2 = roll();

        gn_search_reset_evaluations();
        const double start = now_seconds();
        const int count = gn_search_plays(net, &pos, d1, d2, &config, out,
                                          MAX_PLAYS);
        const double elapsed = now_seconds() - start;

        if (count > 1) {
            total += elapsed;
            big += gn_search_evaluations();
            small += gn_search_prune_evaluations();
            done++;
        }
        if (count > 0) {
            pos = out[0].play.result;
        } else {
            gn_position_swap_turn(&pos);
        }
    }

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
    printf("%d décisions 2-ply filtre (0,1,3)%s\n", decisions,
           (prune != NULL) ? ", élagage actif" : "");
    printf("  %.4f s/décision\n", total / decisions);
    printf("  %lu évaluations du grand réseau par décision\n", big / (unsigned long)decisions);
    if (prune != NULL) {
        printf("  %lu évaluations du petit réseau par décision\n",
               small / (unsigned long)decisions);
    }

    free(out);
    gn_network_free(net);
    if (prune != NULL) {
        gn_network_free(prune);
    }
    return 0;
}

/*
 * bench_kernel.c -- T84. The batch width, tranchée par des intrinsèques.
 *
 * WHAT MAKES THIS DIFFERENT FROM bench_batch.c
 *
 * `bench_batch.c` takes its width as a RUN-TIME variable, so the compiler emits
 * one vector path plus an epilogue and the curve it draws is its own shape, not
 * the kernel's. It also lacks the layer-1 sparsity, and it evaluates positions
 * drawn from anywhere in the reference rather than the SIBLING sets the search
 * actually batches. It answers "does batching pay, and does it stay bit for
 * bit"; it cannot answer "which width".
 *
 * This program is compiled ONCE PER WIDTH, `GN_EVAL_BATCH` being a compile-time
 * constant, with the shipped kernel and the shipped sparsity, and it evaluates
 * sibling batches. It reports which kernel the build compiled, so no figure can
 * be quoted without its code.
 *
 * Three numbers, in increasing order of honesty:
 *
 *   1. raw batch throughput on sibling lots -- the kernel alone;
 *   2. max|Δ| against the scalar path, position by position. Must be 0. A width
 *      that changes an answer is not a faster width, it is a different engine;
 *   3. a whole 2-ply (0,1,3) k=12 decision -- the only number that includes the
 *      search's own cost, and therefore the only one that can say whether the
 *      grouping of the 21 rolls still earns its three phases.
 *
 *   bench_kernel <model.bin> <prune.bin> [repetitions] [decisions]
 *
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 199309L

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gn_infer.h"
#include "gn_rules.h"
#include "gn_search.h"

#define MAX_PLAYS 2048
#define NUM_LOTS 96

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int compare_doubles(const void *a, const void *b)
{
    const double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static unsigned long long g_state = 20260902ULL;

static int roll(void)
{
    g_state = g_state * 6364136223846793005ULL + 1442695040888963407ULL;
    return (int)((g_state >> 33) % 6) + 1;
}

/*
 * SIBLING lots: the resulting positions of the legal plays of one board and one
 * roll. Exactly what `gn_search.c` hands to `gn_evaluate_batch`, and NOT what
 * `bench_batch.c` measures. The lot size is the compiled width, so a narrow
 * build gets more, smaller lots over the same positions -- which is the point:
 * the comparison is at equal WORK, not at equal number of calls.
 */
typedef struct { GnPosition board[GN_EVAL_BATCH]; } Lot;

static int fill_sibling_lots(Lot *lots, int wanted)
{
    GnPlay *plays = malloc(sizeof(GnPlay) * MAX_PLAYS);
    if (plays == NULL) return 0;
    GnPosition pos;
    gn_position_initial(&pos);
    int got = 0;
    for (int guard = 0; got < wanted && guard < 400000; guard++) {
        if (gn_position_is_over(&pos)) { gn_position_initial(&pos); continue; }
        const int d1 = roll(), d2 = roll();
        const int count = gn_legal_plays(&pos, d1, d2, plays, MAX_PLAYS);
        if (count >= GN_EVAL_BATCH) {
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                lots[got].board[n] = plays[n].result;
            }
            got++;
        }
        if (count > 0) pos = plays[count / 2].result;
        else gn_position_swap_turn(&pos);
    }
    free(plays);
    return got;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <model.bin> <prune.bin> [repetitions] [decisions]\n",
                argv[0]);
        return 2;
    }
    const int repetitions = (argc > 3) ? atoi(argv[3]) : 7;
    const int decisions = (argc > 4) ? atoi(argv[4]) : 12;

    GnNetwork *big = gn_network_load(argv[1]);
    GnNetwork *small = gn_network_load(argv[2]);
    if (big == NULL || small == NULL) {
        fprintf(stderr, "modèle refusé\n");
        return 1;
    }

    printf("largeur %d, noyau %s\n", gn_batch_width(), gn_batch_kernel());

    Lot *lots = malloc(sizeof(Lot) * NUM_LOTS);
    float (*out)[GN_NUM_OUTPUTS] = malloc(sizeof(*out) * GN_EVAL_BATCH);
    float (*expected)[GN_NUM_OUTPUTS] = malloc(sizeof(*expected) * GN_EVAL_BATCH);
    double *samples = malloc(sizeof(double) * (size_t)repetitions);
    if (!lots || !out || !expected || !samples) return 1;
    const int lot_count = fill_sibling_lots(lots, NUM_LOTS);
    if (lot_count == 0) {
        /* Refused, not measured on nothing. This fired once, and it was worth
         * the check: `unsigned long` is 32 bits on wasm32, so a PRNG shifting
         * by 33 produced the same die forever and the generator never found a
         * roll with 32 plays. A bench that prints 0,0 éval/s and carries on is
         * how a meaningless number reaches a table. */
        fprintf(stderr, "aucune fratrie de %d positions trouvée\n", GN_EVAL_BATCH);
        return 1;
    }

    /* 2. Bit-exactness, FIRST: a measurement of a wrong kernel is worthless. */
    double worst = 0.0;
    for (int l = 0; l < lot_count; l++) {
        const GnPosition *pointers[GN_EVAL_BATCH];
        for (int n = 0; n < GN_EVAL_BATCH; n++) pointers[n] = &lots[l].board[n];
        if (gn_evaluate_batch(big, pointers, GN_EVAL_BATCH, out) != 0) return 1;
        for (int n = 0; n < GN_EVAL_BATCH; n++) {
            if (gn_evaluate(big, &lots[l].board[n], expected[n]) != 0) return 1;
            for (int k = 0; k < GN_NUM_OUTPUTS; k++) {
                const double delta = fabs((double)out[n][k] - (double)expected[n][k]);
                if (delta > worst) worst = delta;
            }
        }
    }
    printf("  bit à bit contre le chemin scalaire : max|Δ| = %.3e%s\n", worst,
           worst == 0.0 ? "  (bit à bit)" : "  ← PAS bit à bit");

    /* 1. Raw batch throughput, sibling lots, median of `repetitions`. */
    for (int r = 0; r < repetitions + 1; r++) {
        const double start = now_seconds();
        for (int l = 0; l < lot_count; l++) {
            const GnPosition *pointers[GN_EVAL_BATCH];
            for (int n = 0; n < GN_EVAL_BATCH; n++) pointers[n] = &lots[l].board[n];
            if (gn_evaluate_batch(big, pointers, GN_EVAL_BATCH, out) != 0) return 1;
        }
        if (r > 0) samples[r - 1] = now_seconds() - start;
    }
    qsort(samples, (size_t)repetitions, sizeof(double), compare_doubles);
    const double evaluations = (double)lot_count * GN_EVAL_BATCH;
    printf("  débit du noyau (grand réseau, fratries) : %.1f éval/s"
           "  [%d lots de %d]\n",
           evaluations / samples[repetitions / 2], lot_count, GN_EVAL_BATCH);

    /* 3. A whole decision. */
    GnSearchConfig config = gn_search_config(2);
    config.filter[1] = 1;
    config.filter[2] = 3;
    gn_search_use_prune(&config, small, 12);
    GnCandidate *plays = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (plays == NULL) return 1;

    for (int r = 0; r < repetitions + 1; r++) {
        g_state = 20260826ULL;
        GnPosition pos;
        gn_position_initial(&pos);
        int done = 0;
        double total = 0.0;
        unsigned long big_evals = 0, small_evals = 0;
        while (done < decisions) {
            if (gn_position_is_over(&pos)) { gn_position_initial(&pos); continue; }
            const int d1 = roll(), d2 = roll();
            gn_search_reset_evaluations();
            const double start = now_seconds();
            const int count = gn_search_plays(big, &pos, d1, d2, &config, plays,
                                              MAX_PLAYS);
            const double elapsed = now_seconds() - start;
            if (count > 1) {
                total += elapsed;
                big_evals += gn_search_evaluations();
                small_evals += gn_search_prune_evaluations();
                done++;
            }
            if (count > 0) pos = plays[0].play.result;
            else gn_position_swap_turn(&pos);
        }
        if (r > 0) samples[r - 1] = total / decisions;
        if (r == repetitions) {
            printf("  évaluations par décision : grand %lu, petit %lu\n",
                   big_evals / (unsigned long)decisions,
                   small_evals / (unsigned long)decisions);
        }
    }
    qsort(samples, (size_t)repetitions, sizeof(double), compare_doubles);
    printf("  décision 2-ply (0,1,3) k=12 : %.4f s  (min %.4f, médiane de %d)\n",
           samples[repetitions / 2], samples[0], repetitions);

#ifdef GN_BATCH_FILL_STATS
    /*
     * The direct evidence about the GROUPING, and the reason this block exists
     * in a width bench: a lane the kernel computes without a position on it is
     * work thrown away, and the grouping of the 21 rolls exists to stop that
     * happening. Its fill rate PER WIDTH is what says whether the grouping is
     * still earning its three phases in `rank_plays` at a narrower width -- a
     * narrow batch fills itself, a wide one needs help.
     */
    {
        extern unsigned long gn_fill_calls[2], gn_fill_live[2];
        static const char *label[2] = {"grand", "petit"};
        printf("  remplissage des voies (le noyau en calcule toujours %d) :\n",
               GN_EVAL_BATCH);
        for (int sl = 0; sl < 2; sl++) {
            if (!gn_fill_calls[sl]) continue;
            printf("    %-6s %8lu appels, remplissage %.1f/%d = %.1f %%,"
                   " %lu voies calculées\n",
                   label[sl], gn_fill_calls[sl],
                   (double)gn_fill_live[sl] / (double)gn_fill_calls[sl],
                   GN_EVAL_BATCH,
                   100.0 * (double)gn_fill_live[sl]
                       / ((double)gn_fill_calls[sl] * GN_EVAL_BATCH),
                   gn_fill_calls[sl] * (unsigned long)GN_EVAL_BATCH);
        }
    }
#endif

    free(lots); free(out); free(expected); free(samples); free(plays);
    gn_network_free(big);
    gn_network_free(small);
    return 0;
}

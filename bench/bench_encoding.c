/*
 * bench_encoding.c -- what a search evaluation actually costs, encoding included.
 *
 * WHY THIS EXISTS
 *
 * `bench_infer.c` times `gn_evaluate_features` over already-encoded vectors,
 * and says so: encoding is deliberately excluded, because the WebAssembly
 * comparison it feeds excludes it too. Every per-evaluation cost this project
 * has published comes from that bench -- including T3A's "the pruning network
 * is 92.5x cheaper per evaluation".
 *
 * A SEARCH does not get to exclude encoding. It holds positions, not feature
 * vectors, and `gn_evaluate` encodes every one of them. Encoding costs the
 * same whichever network is asked, so it is a floor under the small network
 * and nearly nothing under the big one -- which is exactly the difference
 * between a 92.5x ratio and what a pruned search really delivers.
 *
 * This bench measures the three quantities that settle it, on the same
 * positions: encoding alone, evaluation with encoding, evaluation without.
 *
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gn_encoding.h"
#include "gn_infer.h"
#include "gn_rules.h"

#define MAX_PLAYS 3072
#define DEFAULT_POSITIONS 20000
#define DEFAULT_REPETITIONS 5

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

/* A fixed, self-contained generator: the corpus must not depend on Python, and
 * it must be the same on every run. */
static unsigned long g_state = 20260826UL;

static int roll(void)
{
    g_state = g_state * 6364136223846793005UL + 1442695040888963407UL;
    return (int)((g_state >> 33) % 6) + 1;
}

/* Positions from real play: random legal moves from the opening. Random
 * BOARDS would be a different measurement -- encoding cost depends on how
 * many points are occupied. */
static int build_positions(GnPosition *out, int count)
{
    GnPlay *plays = malloc(sizeof(GnPlay) * MAX_PLAYS);
    if (plays == NULL) {
        return -1;
    }
    GnPosition pos;
    gn_position_initial(&pos);
    int written = 0;

    while (written < count) {
        if (gn_position_is_over(&pos)) {
            gn_position_initial(&pos);
            continue;
        }
        out[written++] = pos;
        const int d1 = roll(), d2 = roll();
        const int n = gn_legal_plays(&pos, d1, d2, plays, MAX_PLAYS);
        if (n > 0) {
            pos = plays[(int)((g_state >> 17) % (unsigned long)n)].result;
        } else {
            gn_position_swap_turn(&pos);
        }
    }
    free(plays);
    return 0;
}

static double best_of(double *samples, int n)
{
    double best = samples[0];
    for (int i = 1; i < n; i++) {
        if (samples[i] < best) {
            best = samples[i];
        }
    }
    return best;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <grand.bin> <petit.bin> [positions] [repetitions]\n",
                argv[0]);
        return 2;
    }
    const int count = (argc > 3) ? atoi(argv[3]) : DEFAULT_POSITIONS;
    const int repetitions = (argc > 4) ? atoi(argv[4]) : DEFAULT_REPETITIONS;

    GnPosition *positions = malloc(sizeof(GnPosition) * (size_t)count);
    float *features = malloc(sizeof(float) * (size_t)count * GN_NUM_FEATURES);
    float *outputs = malloc(sizeof(float) * (size_t)count * GN_NUM_OUTPUTS);
    double *samples = malloc(sizeof(double) * (size_t)repetitions);
    if (positions == NULL || features == NULL || outputs == NULL ||
        samples == NULL || build_positions(positions, count) != 0) {
        fprintf(stderr, "corpus impossible\n");
        return 1;
    }

    printf("corpus : %d positions de vraie partie, %d répétitions "
           "(le meilleur temps est retenu)\n\n", count, repetitions);

    /* 1. Encoding alone. */
    for (int i = 0; i < count; i++) {
        gn_encode(&positions[i], features + (size_t)i * GN_NUM_FEATURES);
    }
    for (int r = 0; r < repetitions; r++) {
        const double start = now_seconds();
        for (int i = 0; i < count; i++) {
            gn_encode(&positions[i], features + (size_t)i * GN_NUM_FEATURES);
        }
        samples[r] = now_seconds() - start;
    }
    const double encode_ms = 1e3 * best_of(samples, repetitions) / count;
    printf("  encodage seul (gn_encode)              %9.5f ms\n", encode_ms);

    for (int a = 1; a <= 2; a++) {
        GnNetwork *net = gn_network_load(argv[a]);
        if (net == NULL) {
            fprintf(stderr, "modèle refusé : %s\n", argv[a]);
            return 1;
        }
        const char *label = (a == 1) ? "grand" : "petit";

        /* 2. Without encoding -- what bench_infer.c reports. */
        for (int i = 0; i < count; i++) {
            gn_evaluate_features(net, features + (size_t)i * GN_NUM_FEATURES,
                                 outputs + (size_t)i * GN_NUM_OUTPUTS);
        }
        for (int r = 0; r < repetitions; r++) {
            const double start = now_seconds();
            for (int i = 0; i < count; i++) {
                gn_evaluate_features(net, features + (size_t)i * GN_NUM_FEATURES,
                                     outputs + (size_t)i * GN_NUM_OUTPUTS);
            }
            samples[r] = now_seconds() - start;
        }
        const double bare_ms = 1e3 * best_of(samples, repetitions) / count;

        /* 3. With encoding -- what a search pays. */
        for (int r = 0; r < repetitions; r++) {
            const double start = now_seconds();
            for (int i = 0; i < count; i++) {
                gn_evaluate(net, &positions[i],
                            outputs + (size_t)i * GN_NUM_OUTPUTS);
            }
            samples[r] = now_seconds() - start;
        }
        const double full_ms = 1e3 * best_of(samples, repetitions) / count;

        printf("\n  %s : features -> sorties (bench_infer) %9.5f ms\n",
               label, bare_ms);
        printf("  %s : position -> sorties (recherche)   %9.5f ms   "
               "dont encodage %.1f %%\n",
               label, full_ms, 100.0 * (full_ms - bare_ms) / full_ms);
        gn_network_free(net);
    }

    free(samples); free(outputs); free(features); free(positions);
    return 0;
}

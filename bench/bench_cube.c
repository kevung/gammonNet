/*
 * bench_cube.c -- what one cube decision costs, money and at a score.
 *
 * WHY
 *
 * The Go port of this engine wrote, measured and then REVERTED the obvious
 * cube optimisation (pre-computing the match-equity lookups): 1 %, under the
 * noise floor. Its decomposition of `build_levels` said why -- the lookups are
 * 11 % of it and `level_solve` is 83 %, and every bisection iteration is a
 * division on the critical path plus an unpredictable branch.
 *
 * That decomposition is about the SHAPE of gn_cube.c, so it transposes here.
 * The absolute cost does not: it was measured in Go. This program measures it
 * in C, because `CLAUDE.md` rule 3 says a performance conclusion is measured,
 * not deduced -- and because the candidate that WOULD pay (valuing the cube in
 * a batch over the candidate plays, as the network already is) cannot be
 * sized without knowing what one decision costs today.
 *
 *   bench_cube <model.bin> <reference.bin> [repetitions]
 *
 * The distributions are real: the reference corpus is evaluated once by the
 * network, and the five probabilities it returns are what the cube model is
 * then handed. Feeding it synthetic vectors would measure the bisection on a
 * distribution the engine never produces.
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

#define DEFAULT_REPETITIONS 11

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

/* Cube efficiencies as MEASURED (docs/mesures/2026-08-07-T34-ajustement.md),
 * indexed by ownership -- centred, owned, opponent's. There is no single
 * default: picking one for every ownership state is the mistake this project
 * has already made once in the WebAssembly wrapper. */
static const double EFFICIENCY[3] = {0.688, 0.566, 0.687};

/* `gn_cube_value` and not `gn_cube_decide` is what the SEARCH calls: one call
 * per evaluated node under `use_cube` (gn_search.c:289). Timing only the
 * decision would miss the post that actually scales with the tree. */
static double time_value(const float *probs, int count, GnCubeOwner owner,
                         const GnMatchState *state, int repetitions,
                         unsigned long *checksum)
{
    double *samples = malloc((size_t)repetitions * sizeof(double));
    if (samples == NULL) {
        return -1.0;
    }
    for (int r = 0; r < repetitions; r++) {
        const double start = now_seconds();
        for (int i = 0; i < count; i++) {
            int failed = 0;
            const double v = gn_cube_value(probs + (size_t)i * GN_NUM_OUTPUTS,
                                           owner, state,
                                           EFFICIENCY[(int)owner], &failed);
            if (!failed) {
                *checksum += (unsigned long)(v * 1e6);
            }
        }
        samples[r] = now_seconds() - start;
    }
    qsort(samples, (size_t)repetitions, sizeof(double), compare_doubles);
    const double median = samples[repetitions / 2];
    free(samples);
    return median;
}

static double time_pass(const float *probs, int count, GnCubeOwner owner,
                        const GnMatchState *state, int repetitions,
                        unsigned long *checksum)
{
    double *samples = malloc((size_t)repetitions * sizeof(double));
    if (samples == NULL) {
        return -1.0;
    }
    for (int r = 0; r < repetitions; r++) {
        const double start = now_seconds();
        for (int i = 0; i < count; i++) {
            GnCubeDecision out;
            if (gn_cube_decide(probs + (size_t)i * GN_NUM_OUTPUTS, owner,
                               state, EFFICIENCY[(int)owner], 1, &out) == 0) {
                *checksum += (unsigned long)out.action;
            }
        }
        samples[r] = now_seconds() - start;
    }
    qsort(samples, (size_t)repetitions, sizeof(double), compare_doubles);
    const double median = samples[repetitions / 2];
    free(samples);
    return median;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <model.bin> <reference.bin> [repetitions]\n",
                argv[0]);
        return 2;
    }
    const int repetitions = (argc > 3) ? atoi(argv[3]) : DEFAULT_REPETITIONS;

    GnNetwork *net = gn_network_load(argv[1]);
    if (net == NULL) {
        fprintf(stderr, "modèle refusé : %s\n", argv[1]);
        return 1;
    }

    FILE *reference = fopen(argv[2], "rb");
    if (reference == NULL) {
        fprintf(stderr, "repère introuvable : %s\n", argv[2]);
        gn_network_free(net);
        return 1;
    }
    char magic[4];
    int header[3];
    if (fread(magic, 1, 4, reference) != 4 || memcmp(magic, "GNRF", 4) != 0 ||
        fread(header, sizeof(int), 3, reference) != 3) {
        fprintf(stderr, "repère malformé\n");
        fclose(reference);
        gn_network_free(net);
        return 1;
    }
    const int count = header[0], num_features = header[1];
    if (num_features != GN_NUM_FEATURES) {
        fprintf(stderr, "repère à %d caractéristiques, %d attendues\n",
                num_features, GN_NUM_FEATURES);
        fclose(reference);
        gn_network_free(net);
        return 1;
    }
    float *features = malloc((size_t)count * num_features * sizeof(float));
    float *probs = malloc((size_t)count * GN_NUM_OUTPUTS * sizeof(float));
    if (features == NULL || probs == NULL ||
        fread(features, sizeof(float), (size_t)count * num_features, reference)
            != (size_t)count * num_features) {
        fprintf(stderr, "lecture du repère incomplète\n");
        free(features); free(probs); fclose(reference); gn_network_free(net);
        return 1;
    }
    fclose(reference);

    for (int i = 0; i < count; i++) {
        gn_evaluate_features(net, features + (size_t)i * num_features,
                             probs + (size_t)i * GN_NUM_OUTPUTS);
    }

    unsigned long checksum = 0;
    /* Warm-up: the match-equity table is 25x25 doubles read on first touch. */
    time_pass(probs, count, GN_CUBE_CENTRED, NULL, 1, &checksum);

    const GnMatchState even5 = {5, 5, 1, 0};
    const GnMatchState even2 = {2, 2, 1, 0};

    struct { const char *label; GnCubeOwner owner; const GnMatchState *state; }
    cases[] = {
        {"money, centré",        GN_CUBE_CENTRED,  NULL},
        {"money, possédé",       GN_CUBE_OWNED,    NULL},
        {"money, adverse",       GN_CUBE_OPPONENT, NULL},
        {"5-away/5-away, centré", GN_CUBE_CENTRED, &even5},
        {"5-away/5-away, possédé", GN_CUBE_OWNED,  &even5},
        {"2-away/2-away, centré", GN_CUBE_CENTRED, &even2},
    };

    printf("%d distributions réelles, %d répétitions (médiane)\n",
           count, repetitions);
    printf("%-26s %12s %12s\n", "cas", "ms/passe", "ns/décision");
    for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); c++) {
        const double median = time_pass(probs, count, cases[c].owner,
                                        cases[c].state, repetitions, &checksum);
        printf("%-26s %12.4f %12.1f\n", cases[c].label, median * 1e3,
               median * 1e9 / (double)count);
    }

    printf("\ngn_cube_value — l'appel que la recherche fait à CHAQUE nœud\n");
    printf("%-26s %12s %12s\n", "cas", "ms/passe", "ns/nœud");
    for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); c++) {
        const double median = time_value(probs, count, cases[c].owner,
                                         cases[c].state, repetitions, &checksum);
        printf("%-26s %12.4f %12.1f\n", cases[c].label, median * 1e3,
               median * 1e9 / (double)count);
    }
    printf("(somme de contrôle %lu — empêche l'élimination du calcul)\n",
           checksum);

    free(features);
    free(probs);
    gn_network_free(net);
    return 0;
}

/*
 * bench_infer.c -- native evaluations per second, the baseline T21 compares to.
 *
 * In C, not through the Python binding. T05 measured that binding at a factor
 * of ten on the rules path -- 6 928 positions per second with Python objects
 * built, 71 052 for the same C call alone. A WebAssembly penalty computed
 * against a Python-wrapped baseline would be measuring ctypes, not the browser.
 *
 * The loop here is the same loop `gnw_evaluate_batch` runs: `gn_evaluate_features`
 * over a contiguous block of already-encoded vectors. Encoding is deliberately
 * outside the timed region -- T21 is about the network, and the browser bench
 * excludes it too. Comparing a timed encode against an untimed one is how a
 * penalty gets invented rather than measured.
 *
 *   bench_infer <model.bin> <reference.bin> [repetitions]
 *
 * SPDX-License-Identifier: MIT
 */

/* `-std=c11` est strict : sans cette macro, `clock_gettime` et
 * `CLOCK_MONOTONIC` restent cachés derrière POSIX. */
#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gn_infer.h"

#define DEFAULT_REPETITIONS 11

static double now_seconds(void)
{
    struct timespec ts;
    /* MONOTONIC: a wall clock can step sideways under NTP mid-measurement. */
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int compare_doubles(const void *a, const void *b)
{
    const double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <model.bin> <reference.bin> [repetitions]\n", argv[0]);
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
    float *outputs = malloc((size_t)count * GN_NUM_OUTPUTS * sizeof(float));
    if (features == NULL || outputs == NULL ||
        fread(features, sizeof(float), (size_t)count * num_features, reference)
            != (size_t)count * num_features) {
        fprintf(stderr, "lecture du repère incomplète\n");
        free(features); free(outputs); fclose(reference); gn_network_free(net);
        return 1;
    }
    fclose(reference);

    /* Warm-up: the first pass pays for cold caches on 2 MiB of weights and on
     * 1.5 MiB of features. It is not what we are timing. */
    for (int i = 0; i < count; i++) {
        gn_evaluate_features(net, features + (size_t)i * num_features,
                             outputs + (size_t)i * GN_NUM_OUTPUTS);
    }

    double *samples = malloc((size_t)repetitions * sizeof(double));
    for (int r = 0; r < repetitions; r++) {
        const double start = now_seconds();
        for (int i = 0; i < count; i++) {
            gn_evaluate_features(net, features + (size_t)i * num_features,
                                 outputs + (size_t)i * GN_NUM_OUTPUTS);
        }
        samples[r] = now_seconds() - start;
    }

    /* Median, not mean: one descheduled run should not move the number. */
    qsort(samples, (size_t)repetitions, sizeof(double), compare_doubles);
    const double median = samples[repetitions / 2];

    printf("{\n");
    printf("  \"target\": \"native\",\n");
    printf("  \"positions\": %d,\n", count);
    printf("  \"repetitions\": %d,\n", repetitions);
    printf("  \"medianMs\": %.6f,\n", median * 1000.0);
    printf("  \"fastestMs\": %.6f,\n", samples[0] * 1000.0);
    printf("  \"slowestMs\": %.6f,\n", samples[repetitions - 1] * 1000.0);
    printf("  \"evalsPerSecond\": %.1f,\n", count / median);
    printf("  \"msPerEval\": %.6f\n", median * 1000.0 / count);
    printf("}\n");

    free(samples); free(features); free(outputs);
    gn_network_free(net);
    return 0;
}

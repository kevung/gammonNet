/*
 * bench_batch.c -- does evaluating positions in batches actually help?
 *
 * T21 measured 13 143 evaluations per second natively, each one re-reading the
 * whole 2.0 MiB of weights. That is about 27.6 GiB/s of weight traffic, which
 * is the order of magnitude a laptop memory subsystem sustains -- so the
 * forward pass is plausibly BANDWIDTH-bound rather than compute-bound. If that
 * is true, evaluating B positions against each weight row at once should read
 * the weights once per B evaluations and go markedly faster.
 *
 * Plausibly. This program exists to find out, because `CLAUDE.md` rule 3 says a
 * performance conclusion is measured, not deduced.
 *
 * THE POINT OF THE LAYOUT. Activations are held feature-major -- `act[j * B + n]`
 * is feature j of batch item n -- so that the inner loop over the batch is
 * contiguous and vectorisable. For each output i and each item n, the sum over j
 * runs in EXACTLY the order the scalar path uses. The arithmetic per output is
 * therefore unchanged, and the results are expected bit for bit identical, not
 * merely close. The program checks that rather than assuming it: a speed-up
 * bought with a silent change of results would be worth nothing here.
 *
 *   bench_batch <model.bin> <reference.bin> [repetitions]
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
#include "nn_eval.h"

#define MAX_BATCH 64
#define MAX_WIDTH 1024

static const int BATCH_SIZES[] = {1, 2, 4, 8, 16, 32};
#define NUM_BATCH_SIZES ((int)(sizeof(BATCH_SIZES) / sizeof(BATCH_SIZES[0])))

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

static float relu(float x) { return x > 0.0f ? x : 0.0f; }
static float sigmoid(float x) { return 1.0f / (1.0f + expf(-x)); }

/*
 * Forward B positions at once.
 *
 * `in` is feature-major: in[j * B + n]. `out` receives the five probabilities
 * of item n at out[n * GN_NUM_OUTPUTS + ...], post-clamp, matching what
 * `gn_evaluate_features` returns.
 */
static void forward_batch(const NNModel *model, const float *in, int batch,
                          float *out)
{
    static float buf_a[MAX_WIDTH * MAX_BATCH];
    static float buf_b[MAX_WIDTH * MAX_BATCH];

    const float *current = in;
    float *next = buf_a;
    const int total_layers = model->num_hidden + 1;

    for (int L = 0; L < total_layers; L++) {
        const int rows = model->layer_out[L];
        const int cols = model->layer_in[L];
        const float *W = model->weight[L];
        const float *bias = model->bias[L];
        const int is_output = (L == model->num_hidden);

        for (int i = 0; i < rows; i++) {
            float acc[MAX_BATCH];
            for (int n = 0; n < batch; n++) {
                acc[n] = bias[i];
            }

            /* The weight row is read once and reused across the batch. This
             * single reordering is the whole hypothesis. The order of the sum
             * over j, per (i, n), is unchanged. */
            const float *w_row = W + (size_t)i * cols;
            for (int j = 0; j < cols; j++) {
                const float w = w_row[j];
                const float *column = current + (size_t)j * batch;
                for (int n = 0; n < batch; n++) {
                    acc[n] += w * column[n];
                }
            }

            float *row_out = next + (size_t)i * batch;
            for (int n = 0; n < batch; n++) {
                row_out[n] = is_output ? sigmoid(acc[n]) : relu(acc[n]);
            }
        }

        current = next;
        next = (next == buf_a) ? buf_b : buf_a;
    }

    /* Un-transpose the five outputs and apply the same nested-event clamp the
     * reference reduction applies -- see nn_eval.c:211-215. Skipping it here
     * would make the comparison below meaningless. */
    for (int n = 0; n < batch; n++) {
        float p[GN_NUM_OUTPUTS];
        for (int k = 0; k < GN_NUM_OUTPUTS; k++) {
            p[k] = current[(size_t)k * batch + n];
        }
        if (p[1] > p[0]) p[1] = p[0];
        const float lose = 1.0f - p[0];
        if (p[3] > lose) p[3] = lose;
        if (p[2] > p[1]) p[2] = p[1];
        if (p[4] > p[3]) p[4] = p[3];
        for (int k = 0; k < GN_NUM_OUTPUTS; k++) {
            out[(size_t)n * GN_NUM_OUTPUTS + k] = p[k];
        }
    }
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <model.bin> <reference.bin> [repetitions]\n", argv[0]);
        return 2;
    }
    const int repetitions = (argc > 3) ? atoi(argv[3]) : 7;

    NNModel model;
    if (nn_load(&model, argv[1]) != 0) {
        fprintf(stderr, "modèle illisible\n");
        return 1;
    }
    if (model.activation != NN_ACTIVATION_RELU ||
        model.output_mode != NN_OUTPUT_PROB5) {
        /* Specialised on the retained model rather than generalised: this is a
         * measurement, and a wrong answer from an untested branch would be
         * worse than no answer. Refused, not approximated. */
        fprintf(stderr, "ce banc ne traite que relu + prob5\n");
        nn_free(&model);
        return 1;
    }

    FILE *reference = fopen(argv[2], "rb");
    char magic[4];
    int header[3];
    if (reference == NULL || fread(magic, 1, 4, reference) != 4 ||
        memcmp(magic, "GNRF", 4) != 0 ||
        fread(header, sizeof(int), 3, reference) != 3) {
        fprintf(stderr, "repère malformé\n");
        return 1;
    }
    const int count = header[0], num_features = header[1];

    float *features = malloc((size_t)count * num_features * sizeof(float));
    if (fread(features, sizeof(float), (size_t)count * num_features, reference)
        != (size_t)count * num_features) {
        fprintf(stderr, "repère incomplet\n");
        return 1;
    }
    float *expected = malloc((size_t)count * GN_NUM_OUTPUTS * sizeof(float));
    if (fread(expected, sizeof(float), (size_t)count * GN_NUM_OUTPUTS, reference)
        != (size_t)count * GN_NUM_OUTPUTS) {
        fprintf(stderr, "sorties du repère incomplètes\n");
        return 1;
    }
    fclose(reference);

    float *transposed = malloc((size_t)num_features * MAX_BATCH * sizeof(float));
    float *outputs = malloc((size_t)count * GN_NUM_OUTPUTS * sizeof(float));
    double *samples = malloc((size_t)repetitions * sizeof(double));

    printf("%-7s %14s %12s %10s %14s\n",
           "lot", "éval/s", "ms/éval", "gain", "max|Δ| repère");

    double baseline = 0.0;

    for (int b = 0; b < NUM_BATCH_SIZES; b++) {
        const int batch = BATCH_SIZES[b];
        const int usable = (count / batch) * batch;

        for (int r = 0; r < repetitions + 1; r++) {
            const double start = now_seconds();
            for (int base = 0; base < usable; base += batch) {
                for (int j = 0; j < num_features; j++) {
                    for (int n = 0; n < batch; n++) {
                        transposed[(size_t)j * batch + n] =
                            features[(size_t)(base + n) * num_features + j];
                    }
                }
                forward_batch(&model, transposed, batch,
                              outputs + (size_t)base * GN_NUM_OUTPUTS);
            }
            /* The first pass is a warm-up and is discarded. */
            if (r > 0) samples[r - 1] = now_seconds() - start;
        }

        qsort(samples, (size_t)repetitions, sizeof(double), compare_doubles);
        const double median = samples[repetitions / 2];
        const double rate = usable / median;
        if (batch == 1) baseline = rate;

        double worst = 0.0;
        for (int i = 0; i < usable * GN_NUM_OUTPUTS; i++) {
            const double delta = fabs((double)outputs[i] - (double)expected[i]);
            if (delta > worst) worst = delta;
        }

        printf("%-7d %14.1f %12.5f %9.2fx %14.3e%s\n",
               batch, rate, median * 1000.0 / usable, rate / baseline, worst,
               worst == 0.0 ? "  (bit à bit)" : "");
    }

    free(features); free(expected); free(transposed); free(outputs); free(samples);
    nn_free(&model);
    return 0;
}

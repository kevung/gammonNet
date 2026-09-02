/*
 * bench_gemm_int8.c -- int8 against float32, on the shapes this project runs.
 *
 * THE DECISION THIS BENCHMARK MAKES
 *
 * DS-09 sets an abandonment threshold: if the DETERMINISTIC int8 path gains
 * less than 1.3x over float32, the complexity of int8 is not worth carrying and
 * the verdict is published as such. That threshold is the whole reason this
 * program runs BEFORE any quantisation-aware training is written. Building a
 * QAT pipeline and then discovering the kernel does not pay would be the exact
 * failure mode `CLAUDE.md` rule 3 exists to prevent.
 *
 * So: no conclusion about int8 is drawn anywhere in this project until this
 * program has run on a quiet machine and its number has been read.
 *
 * WHAT IS COMPARED
 *
 * The five layers of the embedded network (196 -> 512 -> 512 -> 256 -> 128 -> 5)
 * at the fixed batch width the engine forwards, plus the batch sweep that lets
 * the ISA question of T73 be asked: T21 measured x2.21 from batching in Wasm
 * against x8.5 natively, and the explanation on offer is that the native build
 * has FMA and VNNI while the Wasm one has neither. Compiling this program with
 * `-mno-fma -mno-avx2 -msse2` and comparing the batch curve tests that
 * explanation instead of repeating it.
 *
 * Both paths compute the same layer from the same weights. The float path is
 * the batch kernel's arithmetic in the same feature-major layout, so the
 * comparison is kernel against kernel and not layout against layout.
 *
 *   bench_gemm_int8 [repetitions] [--json <path>]
 *
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 199309L

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gn_gemm_int8.h"

#define MAX_BATCH 32
#define MAX_ROWS 512
#define MAX_COLS 512

static const struct { int rows, cols; const char *name; } LAYERS[] = {
    {512, 196, "in:196->512"},
    {512, 512, "h1:512->512"},
    {256, 512, "h2:512->256"},
    {128, 256, "h3:256->128"},
    {5, 128, "out:128->5"},
};
#define NUM_LAYERS ((int)(sizeof(LAYERS) / sizeof(LAYERS[0])))

/* GN_EVAL_BATCH de gn_infer.h : la largeur fixe que le moteur forward. Répétée
 * plutôt qu'incluse pour que ce programme se compile sans le reste. */
#define ENGINE_BATCH 32

static const int BATCHES[] = {1, 2, 4, 8, 16, 32};
#define NUM_BATCHES ((int)(sizeof(BATCHES) / sizeof(BATCHES[0])))

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static unsigned long rng_state = 88172645463325252UL;
static unsigned long xorshift(void)
{
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return rng_state;
}

/* The float32 comparison path: the same arithmetic as the batch kernel, in the
 * same feature-major layout, so that what is timed is int8 against float and
 * not one memory layout against another. */
static void gemm_f32(const float *weights, int rows, int cols,
                     const float *bias, const float *input, int batch,
                     float *out)
{
    for (int i = 0; i < rows; i++) {
        const float *row = weights + (size_t)i * cols;
        float *dst = out + (size_t)i * batch;
        for (int n = 0; n < batch; n++) {
            dst[n] = bias[i];
        }
        for (int j = 0; j < cols; j++) {
            const float w = row[j];
            const float *column = input + (size_t)j * batch;
            for (int n = 0; n < batch; n++) {
                dst[n] += w * column[n];
            }
        }
    }
}

int main(int argc, char **argv)
{
    long repetitions = argc > 1 ? strtol(argv[1], NULL, 10) : 2000;
    const char *json_path = NULL;
    for (int i = 1; i < argc - 1; i++) {
        if (strcmp(argv[i], "--json") == 0) json_path = argv[i + 1];
    }
    if (repetitions <= 0) repetitions = 2000;

    static int8_t w8[MAX_ROWS * MAX_COLS];
    static float wf[MAX_ROWS * MAX_COLS];
    static int32_t b32[MAX_ROWS];
    static float bf[MAX_ROWS];
    static uint8_t in8[MAX_COLS * MAX_BATCH];
    static float inf[MAX_COLS * MAX_BATCH];
    static uint8_t out8[MAX_ROWS * MAX_BATCH];
    static float outf[MAX_ROWS * MAX_BATCH];

    for (int i = 0; i < MAX_ROWS * MAX_COLS; i++) {
        w8[i] = (int8_t)(xorshift() % 255 - 127);
        wf[i] = (float)w8[i] * (1.0f / 127.0f);
    }
    for (int i = 0; i < MAX_ROWS; i++) {
        b32[i] = (int32_t)(xorshift() % 20001) - 10000;
        bf[i] = (float)b32[i] * (1.0f / 16384.0f);
    }
    for (int i = 0; i < MAX_COLS * MAX_BATCH; i++) {
        in8[i] = (uint8_t)(xorshift() % 128);
        inf[i] = (float)in8[i] * (1.0f / 127.0f);
    }

    printf("# bench_gemm_int8 -- int8 contre float32\n");
    printf("# chemin int8 dispatché : %s\n", gn_gemm_int8_path());
    printf("# marge int32 à 512 entrées : x%.1f\n", gn_gemm_int8_headroom(512));
    printf("# %ld répétitions par point\n\n", repetitions);
    printf("%-14s %6s %12s %12s %8s %14s %14s\n",
           "couche", "lot", "int8 op/s", "f32 op/s", "gain", "int8 MAC/s", "f32 MAC/s");

    FILE *json = json_path ? fopen(json_path, "w") : NULL;
    if (json) {
        fprintf(json, "{\n  \"path\": \"%s\",\n  \"repetitions\": %ld,\n"
                      "  \"headroom_512\": %.3f,\n  \"points\": [\n",
                gn_gemm_int8_path(), repetitions, gn_gemm_int8_headroom(512));
    }

    /* Le verdict porte sur la largeur que le moteur forward RÉELLEMENT
     * (GN_EVAL_BATCH = 32). Les autres largeurs sont instructives -- elles
     * disent où bascule l'avantage vectoriel -- mais prendre le pire de toutes
     * ferait échouer le seuil sur un lot de 1 que le moteur ne demande jamais.
     * Un seuil appliqué à un point de fonctionnement fictif ne protège rien. */
    int first = 1;
    double worst_gain = 1e30, best_gain = 0.0;
    double worst_engine_gain = 1e30, best_engine_gain = 0.0;
    for (int L = 0; L < NUM_LAYERS; L++) {
        const int rows = LAYERS[L].rows, cols = LAYERS[L].cols;
        for (int bi = 0; bi < NUM_BATCHES; bi++) {
            const int batch = BATCHES[bi];

            /* Warm-up: the first pass over 512x512 weights is a cold-cache
             * measurement of the memory system, not of the kernel. */
            gn_gemm_int8_relu(w8, rows, cols, b32, in8, batch, 7, out8);
            gemm_f32(wf, rows, cols, bf, inf, batch, outf);

            double t = now_seconds();
            for (long r = 0; r < repetitions; r++) {
                gn_gemm_int8_relu(w8, rows, cols, b32, in8, batch, 7, out8);
            }
            const double t_int8 = now_seconds() - t;

            t = now_seconds();
            for (long r = 0; r < repetitions; r++) {
                gemm_f32(wf, rows, cols, bf, inf, batch, outf);
            }
            const double t_f32 = now_seconds() - t;

            const double macs = (double)rows * cols * batch;
            const double ops_int8 = (double)repetitions / t_int8;
            const double ops_f32 = (double)repetitions / t_f32;
            const double gain = t_f32 / t_int8;
            if (gain < worst_gain) worst_gain = gain;
            if (gain > best_gain) best_gain = gain;
            if (batch == ENGINE_BATCH) {
                if (gain < worst_engine_gain) worst_engine_gain = gain;
                if (gain > best_engine_gain) best_engine_gain = gain;
            }

            printf("%-14s %6d %12.0f %12.0f %7.2fx %14.3e %14.3e\n",
                   LAYERS[L].name, batch, ops_int8, ops_f32, gain,
                   ops_int8 * macs, ops_f32 * macs);
            if (json) {
                fprintf(json, "%s    {\"layer\": \"%s\", \"rows\": %d, \"cols\": %d,"
                              " \"batch\": %d, \"int8_ops\": %.1f, \"f32_ops\": %.1f,"
                              " \"gain\": %.4f, \"int8_macs\": %.4e, \"f32_macs\": %.4e}",
                        first ? "" : ",\n", LAYERS[L].name, rows, cols, batch,
                        ops_int8, ops_f32, gain, ops_int8 * macs, ops_f32 * macs);
                first = 0;
            }
        }
    }

    printf("\n# gain int8, toutes largeurs : de x%.2f à x%.2f\n",
           worst_gain, best_gain);
    printf("# gain int8 AU LOT DU MOTEUR (%d) : de x%.2f à x%.2f  <- le verdict\n",
           ENGINE_BATCH, worst_engine_gain, best_engine_gain);
    printf("# seuil d'abandon DS-09 : x1.30 sur le chemin déterministe.\n");
    printf("# %s\n", worst_engine_gain >= 1.30
           ? "Seuil franchi sur toutes les couches, au lot du moteur."
           : "SEUIL NON FRANCHI sur au moins une couche -- verdict à publier (DS-09).");
    if (json) {
        fprintf(json, "\n  ],\n  \"worst_gain\": %.4f,\n  \"best_gain\": %.4f,\n"
                      "  \"engine_batch\": %d,\n"
                      "  \"worst_gain_at_engine_batch\": %.4f,\n"
                      "  \"best_gain_at_engine_batch\": %.4f,\n"
                      "  \"threshold\": 1.30,\n  \"threshold_met\": %s\n}\n",
                worst_gain, best_gain, ENGINE_BATCH, worst_engine_gain,
                best_engine_gain, worst_engine_gain >= 1.30 ? "true" : "false");
        fclose(json);
        printf("# → %s\n", json_path);
    }
    return 0;
}

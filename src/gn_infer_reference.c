/*
 * gn_infer_reference.c -- `gn_infer.h` on top of the reference C engine.
 *
 * Everything backend-specific lives in this one file, exactly as
 * `gn_rules_reference.c` does for the rules. Swapping inference engines --
 * which is what T22 will decide, on measurements rather than on taste -- means
 * rewriting this `.c` and nothing else.
 *
 * The backend is `vendor/backgammon-ai-engine/c_inference/nn_eval.c`
 * (Alexander Strehl, MIT, commit pinned by `tools/fetch_vendor.py`).
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_infer.h"

#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "nn_eval.h"

#include "gn_int8_model.h"
#include "gn_tile.h"

#ifdef GN_KERNEL_INTRINSICS
#include "gn_kernel_f32.h"
#endif

/*
 * Two backends behind one opaque type -- the design `gn_infer.h` already
 * commits to ("the backend is deliberately invisible here"). `format`
 * decides which of `model`/`int8` is live; every entry point below branches
 * on it once, at the top, rather than leaving it implicit in which field
 * happens to be non-zero.
 */
enum GnNetworkFormat { GN_NETWORK_FLOAT, GN_NETWORK_INT8 };

struct GnNetwork {
    enum GnNetworkFormat format;
    NNModel model;          /* valid when format == GN_NETWORK_FLOAT */
    GnInt8Model int8_model; /* valid when format == GN_NETWORK_INT8 */
#ifdef GN_BATCH_SPARSITY_SWITCH
    /* T89 ONLY. Compiled out of the shipped library, exactly like
     * GN_BATCH_FILL_STATS: the layer-1 sparsity is not a run-time choice, it
     * is the kernel. What T89 needs and could not get otherwise is to turn it
     * off ON ONE NETWORK AT A TIME -- the ×1,16 published on 2026-09-02 is the
     * two networks together, and the registry's 78 % claim is about the small
     * one alone. `gn_search.c` holds both networks and hands them to
     * `gn_evaluate_batch` without saying which is which, so the flag has to
     * live on the network rather than in a global. */
    int sparsity;   /* 1 = compact the live columns (the shipped behaviour) */
    int slot;       /* 0 = big, 1 = small; a label for the counters below */
#endif
};

#ifdef GN_BATCH_SPARSITY_SWITCH
unsigned long gn_sparsity_calls[2] = {0, 0};
unsigned long gn_sparsity_active[2] = {0, 0};
unsigned long gn_sparsity_widest[2] = {0, 0};

void gn_batch_sparsity_set(GnNetwork *net, int enabled)
{
    if (net != NULL) {
        net->sparsity = enabled ? 1 : 0;
    }
}

void gn_batch_sparsity_label(GnNetwork *net, int slot)
{
    if (net != NULL && (slot == 0 || slot == 1)) {
        net->slot = slot;
    }
}

void gn_batch_sparsity_reset(void)
{
    for (int i = 0; i < 2; i++) {
        gn_sparsity_calls[i] = 0;
        gn_sparsity_active[i] = 0;
        gn_sparsity_widest[i] = 0;
    }
}
#endif

/* IEEE 754 binary16 -> binary32. Exact : tout demi-flottant fini est un
 * flottant simple, et les deux formats partagent leur arrondi. */
static float from_half(unsigned short h)
{
    const unsigned int sign = (unsigned int)(h >> 15) << 31;
    unsigned int exponent = (h >> 10) & 0x1Fu;
    unsigned int mantissa = h & 0x3FFu;
    unsigned int bits;

    if (exponent == 0) {
        if (mantissa == 0) {
            bits = sign;                      /* +/-0 */
        } else {
            /* Sous-normal en binary16, normal en binary32 : on renormalise. */
            exponent = 127 - 15 + 1;
            while ((mantissa & 0x400u) == 0) {
                mantissa <<= 1;
                exponent--;
            }
            mantissa &= 0x3FFu;
            bits = sign | (exponent << 23) | (mantissa << 13);
        }
    } else if (exponent == 0x1Fu) {
        bits = sign | 0x7F800000u | (mantissa << 13);   /* inf / NaN */
    } else {
        bits = sign | ((exponent + 127 - 15) << 23) | (mantissa << 13);
    }

    float value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

/*
 * Le format de DISTRIBUTION (T50) : `BGN6`, identique au `.bin` sauf que les
 * poids sont des demi-flottants. Les biais restent en float32 — 0,27 % du
 * fichier, et l'endroit où une perte de précision se propagerait le plus.
 *
 * Ce qui coûte dans un navigateur n'est pas le calcul mais le
 * TÉLÉCHARGEMENT : 2,1 Mio avant la première évaluation, 1,06 Mio en float16
 * (mesuré ×1,99). Ce que la précision coûte est mesuré ailleurs
 * (`docs/mesures/2026-08-04-quantification.md`) : 0,015 % des décisions
 * déplacées, ~1e-9 d'équité.
 *
 * À l'exécution rien ne change : le modèle rendu est en float32, comme
 * l'autre. Ce format transporte, il ne calcule pas.
 *
 * DEUX LECTEURS POUR UN FORMAT, et ce qui les tient ensemble : le `.bin`
 * float32 est lu par le lecteur vendoré (`nn_load`), celui-ci par le code
 * ci-dessous. Le risque est qu'ils dérivent. `tests/test_fp16.py` l'interdit
 * en exigeant que le modèle emballé se relise EXACTEMENT égal au modèle
 * d'origine arrondi en float16 — un désaccord d'en-tête, d'ordre ou de forme
 * y casse immédiatement.
 */
static int load_fp16(NNModel *model, const char *path)
{
    memset(model, 0, sizeof(*model));

    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return -1;
    }

    char magic[4];
    if (fread(magic, 1, 4, file) != 4 || memcmp(magic, "BGN6", 4) != 0) {
        fclose(file);
        return -1;
    }
    if (fread(&model->num_hidden, 4, 1, file) != 1 ||
        fread(&model->input_size, 4, 1, file) != 1 ||
        fread(&model->activation, 4, 1, file) != 1 ||
        fread(&model->output_mode, 4, 1, file) != 1 ||
        model->num_hidden < 1 || model->num_hidden > NN_MAX_LAYERS) {
        fclose(file);
        return -1;
    }
    for (int i = 0; i < model->num_hidden; i++) {
        if (fread(&model->hidden_sizes[i], 4, 1, file) != 1) {
            fclose(file);
            return -1;
        }
    }

    int previous = model->input_size, widest = model->input_size;
    for (int i = 0; i < model->num_hidden; i++) {
        model->layer_in[i] = previous;
        model->layer_out[i] = model->hidden_sizes[i];
        previous = model->hidden_sizes[i];
        if (previous > widest) {
            widest = previous;
        }
    }
    model->layer_in[model->num_hidden] = previous;
    model->layer_out[model->num_hidden] =
        (model->output_mode == NN_OUTPUT_PROB5) ? NN_PROB5_OUTPUTS : 1;
    if (model->layer_out[model->num_hidden] > widest) {
        widest = model->layer_out[model->num_hidden];
    }

    for (int i = 0; i <= model->num_hidden; i++) {
        const size_t rows = (size_t)model->layer_out[i];
        const size_t cols = (size_t)model->layer_in[i];
        model->weight[i] = malloc(rows * cols * sizeof(float));
        model->bias[i] = malloc(rows * sizeof(float));
        unsigned short *packed = malloc(rows * cols * sizeof(unsigned short));
        if (!model->weight[i] || !model->bias[i] || !packed ||
            fread(packed, sizeof(unsigned short), rows * cols, file)
                != rows * cols ||
            fread(model->bias[i], sizeof(float), rows, file) != rows) {
            free(packed);
            fclose(file);
            nn_free(model);
            return -1;
        }
        for (size_t k = 0; k < rows * cols; k++) {
            model->weight[i][k] = from_half(packed[k]);
        }
        free(packed);
    }
    fclose(file);

    model->buf_a = malloc((size_t)widest * sizeof(float));
    model->buf_b = malloc((size_t)widest * sizeof(float));
    if (!model->buf_a || !model->buf_b) {
        nn_free(model);
        return -1;
    }
    return 0;
}

/* Le magic du fichier, sans le lire deux fois en entier. */
static int is_fp16(const char *path)
{
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return 0;
    }
    char magic[4] = {0};
    const int read = (int)fread(magic, 1, 4, file);
    fclose(file);
    return read == 4 && memcmp(magic, "BGN6", 4) == 0;
}

GnNetwork *gn_network_load(const char *path)
{
    if (path == NULL) {
        return NULL;
    }

    GnNetwork *net = calloc(1, sizeof(*net));
    if (net == NULL) {
        return NULL;
    }
#ifdef GN_BATCH_SPARSITY_SWITCH
    net->sparsity = 1;   /* the shipped behaviour is the default */
    net->slot = 0;
#endif

    if (gn_int8_model_is(path)) {
        net->format = GN_NETWORK_INT8;
        if (gn_int8_model_load(&net->int8_model, path) != 0) {
            free(net);
            return NULL;
        }
        /* Same refusal as the float path, same reason: an input size that
         * is not ours was trained on a different encoding. There is no
         * "output mode" to check here -- `BGQ8` has no other mode, prob5 is
         * the only shape `tools/export_qat_int8.py` ever writes. */
        if (net->int8_model.input_size != GN_NUM_FEATURES) {
            gn_int8_model_free(&net->int8_model);
            free(net);
            return NULL;
        }
        return net;
    }

    net->format = GN_NETWORK_FLOAT;
    const int loaded = is_fp16(path) ? load_fp16(&net->model, path)
                                     : nn_load(&net->model, path);
    if (loaded != 0) {
        free(net);
        return NULL;
    }

    /*
     * Two refusals rather than two silent approximations.
     *
     * A model that is not prob5 reduces to an aggregated money equity. It
     * would load, evaluate, and produce numbers -- wrong ones for match play,
     * with nothing to show for it. A model whose input size is not ours was
     * trained on a different encoding; feeding it our 196 features is the
     * textbook way to get five plausible, meaningless probabilities.
     */
    if (net->model.output_mode != NN_OUTPUT_PROB5 ||
        net->model.input_size != GN_NUM_FEATURES) {
        nn_free(&net->model);
        free(net);
        return NULL;
    }

    return net;
}

void gn_network_free(GnNetwork *net)
{
    if (net == NULL) {
        return;
    }
    if (net->format == GN_NETWORK_INT8) {
        gn_int8_model_free(&net->int8_model);
    } else {
        nn_free(&net->model);
    }
    free(net);
}

int gn_network_input_size(const GnNetwork *net)
{
    if (net == NULL) {
        return -1;
    }
    return net->format == GN_NETWORK_INT8 ? net->int8_model.input_size
                                          : net->model.input_size;
}

int gn_evaluate_features(const GnNetwork *net, const float *features,
                         float probs[GN_NUM_OUTPUTS])
{
    if (net == NULL || features == NULL || probs == NULL) {
        return -1;
    }

    if (net->format == GN_NETWORK_INT8) {
        return gn_int8_model_evaluate(&net->int8_model, features, 1, probs);
    }

    /*
     * `nn_forward_prob5` returns the money equity and fills `probs` with the
     * five post-clamp probabilities. We drop the equity: it is the reduction
     * `PLAN.md` warns about, and callers who want it ask `gn_money_equity`
     * explicitly, from the distribution they were given.
     */
    (void)nn_forward_prob5(&net->model, features, probs);
    return 0;
}

int gn_evaluate(const GnNetwork *net, const GnPosition *pos,
                float probs[GN_NUM_OUTPUTS])
{
    if (net == NULL || pos == NULL || probs == NULL) {
        return -1;
    }

    float features[GN_NUM_FEATURES];
    if (gn_encode(pos, features) != 0) {
        return -1;
    }

    return gn_evaluate_features(net, features, probs);
}

/* ── Batched evaluation (T35) ──────────────────────────────────────────
 *
 * The kernel is bench/bench_batch.c's `forward_batch`, moved here verbatim in
 * everything that matters: activations feature-major (`act[j * B + n]`), each
 * weight row read once and reused across the batch, and the sum over j per
 * (output, item) in EXACTLY the scalar order — which is what makes the
 * results bit-identical to `gn_evaluate`. T21 measured that property on the
 * 2000-position reference (max|Δ| = 0), and tests/test_batch.py holds it.
 *
 * Static buffers, like the scalar path's model-owned ones: this project is
 * single-threaded per process (parallelism is by process, see arena.py), and
 * a buffer that pretended to be thread-safe without being tested as such
 * would be worse than one that is honestly not.
 */

#define BATCH_MAX_WIDTH 1024

static float g_batch_a[BATCH_MAX_WIDTH * GN_EVAL_BATCH];
static float g_batch_b[BATCH_MAX_WIDTH * GN_EVAL_BATCH];
static float g_batch_in[GN_NUM_FEATURES * GN_EVAL_BATCH];

static int batch_kernel_applies(const NNModel *model)
{
    if (model->activation != NN_ACTIVATION_RELU ||
        model->output_mode != NN_OUTPUT_PROB5) {
        return 0;
    }
    for (int L = 0; L <= model->num_hidden; L++) {
        if (model->layer_in[L] > BATCH_MAX_WIDTH ||
            model->layer_out[L] > BATCH_MAX_WIDTH) {
            return 0;
        }
    }
    return 1;
}

/* Which kernel this build actually compiled, so that no measurement is ever
 * reported without saying which code produced it. */
const char *gn_batch_kernel(void)
{
#ifdef GN_KERNEL_INTRINSICS
    /* Built once, not recomputed: the tile is a compile-time constant and the
     * caller prints it beside every figure. */
    static char name[64];
    if (name[0] == '\0') {
        snprintf(name, sizeof(name), "%s intrinsèques, %d lignes x %d vecteurs de %d",
                 GN_KERNEL_NAME, GN_KERNEL_ROWS, GN_KERNEL_VECS, GN_VEC_LANES);
    }
    return name;
#else
    return "auto-vectorisé";
#endif
}

int gn_batch_width(void) { return GN_EVAL_BATCH; }

static float batch_relu(float x) { return x > 0.0f ? x : 0.0f; }
static float batch_sigmoid(float x) { return 1.0f / (1.0f + expf(-x)); }

/*
 * Forward EXACTLY GN_EVAL_BATCH lanes, `live` of which carry positions; the
 * rest are zero-filled and discarded.
 *
 * The fixed trip count is not a style choice, it is THE correctness device:
 * with a variable batch width the compiler emits different vector/epilogue
 * paths for different widths, and under `-fassociative-math` those paths sum
 * in different orders — the result of a position then depends on how many
 * siblings it happened to be batched with, which tests/test_batch.py showed
 * before this shape and forbids since. One compiled path, one summation
 * order, whatever the chunk.
 */
static void forward_batch(const NNModel *model, const float *in, int live,
                          const int *nonzero, int n_nonzero,
                          float (*out)[GN_NUM_OUTPUTS])
{
    const float *current = in;
    float *next = g_batch_a;
    const int total_layers = model->num_hidden + 1;

    /* Les colonnes vivantes, rassemblées une fois : le noyau les relira
     * `rows` fois (512 pour le grand réseau), donc la compaction s'amortit
     * immédiatement. */
    static float packed_in[GN_NUM_FEATURES * GN_EVAL_BATCH];
    if (nonzero != NULL) {
        for (int idx = 0; idx < n_nonzero; idx++) {
            memcpy(packed_in + (size_t)idx * GN_EVAL_BATCH,
                   in + (size_t)nonzero[idx] * GN_EVAL_BATCH,
                   sizeof(float) * GN_EVAL_BATCH);
        }
    }

    for (int L = 0; L < total_layers; L++) {
        const int rows = model->layer_out[L];
        const int cols = model->layer_in[L];
        const float *W = model->weight[L];
        const float *bias = model->bias[L];
        const int is_output = (L == model->num_hidden);

        /* The live source for this layer: compacted at layer 0 when the
         * sparsity applies, dense otherwise. Choosing it ONCE per layer rather
         * than per row keeps the two kernels below reading the same thing. */
        const int packed = (L == 0 && nonzero != NULL);
        const float *source = packed ? packed_in : current;
        const int count = packed ? n_nonzero : cols;

#ifdef GN_KERNEL_INTRINSICS
        /* T84: the hand-written kernel, tiled over GN_KERNEL_ROWS output rows
         * so that a narrow batch is not one dependent chain of adds. The
         * summation order per (i, n) is the scalar one, unchanged -- see
         * gn_kernel_f32.h. */
        int i = 0;
        for (; i + GN_KERNEL_ROWS <= rows; i += GN_KERNEL_ROWS) {
            float acc[GN_KERNEL_ROWS * GN_EVAL_BATCH];
            for (int r = 0; r < GN_KERNEL_ROWS; r++) {
                for (int n = 0; n < GN_EVAL_BATCH; n++) {
                    acc[r * GN_EVAL_BATCH + n] = bias[i + r];
                }
            }
            if (packed) {
                float packed_w[GN_KERNEL_ROWS * GN_NUM_FEATURES];
                for (int r = 0; r < GN_KERNEL_ROWS; r++) {
                    const float *w_row = W + (size_t)(i + r) * cols;
                    for (int idx = 0; idx < n_nonzero; idx++) {
                        packed_w[r * n_nonzero + idx] = w_row[nonzero[idx]];
                    }
                }
                gn_kernel_block(acc, packed_w, source, count);
            } else {
                gn_kernel_block(acc, W + (size_t)i * cols, source, count);
            }
            for (int r = 0; r < GN_KERNEL_ROWS; r++) {
                float *row_out = next + (size_t)(i + r) * GN_EVAL_BATCH;
                const float *a = acc + r * GN_EVAL_BATCH;
                for (int n = 0; n < GN_EVAL_BATCH; n++) {
                    row_out[n] = is_output ? batch_sigmoid(a[n])
                                           : batch_relu(a[n]);
                }
            }
        }
        for (; i < rows; i++) {
            float acc[GN_EVAL_BATCH];
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                acc[n] = bias[i];
            }
            const float *w_row = W + (size_t)i * cols;
            if (packed) {
                float packed_w[GN_NUM_FEATURES];
                for (int idx = 0; idx < n_nonzero; idx++) {
                    packed_w[idx] = w_row[nonzero[idx]];
                }
                gn_kernel_row(acc, packed_w, source, count);
            } else {
                gn_kernel_row(acc, w_row, source, count);
            }
            float *row_out = next + (size_t)i * GN_EVAL_BATCH;
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                row_out[n] = is_output ? batch_sigmoid(acc[n]) : batch_relu(acc[n]);
            }
        }
#else
        for (int i = 0; i < rows; i++) {
            float acc[GN_EVAL_BATCH];
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                acc[n] = bias[i];
            }

            /* The weight row is read once and reused across the batch. This
             * single reordering is the whole speed-up. The order of the sum
             * over j, per (i, n), is unchanged. */
            const float *w_row = W + (size_t)i * cols;
            if (packed) {
                /* Compacted: the weights of the live features gathered once
                 * into a contiguous row, so the inner loop streams instead of
                 * jumping. The first attempt indexed `w_row[nonzero[idx]]`
                 * directly and was SLOWER than the dense loop despite doing a
                 * fifth of the multiplications -- the access pattern beat the
                 * operation count. */
                float packed_w[GN_NUM_FEATURES];
                for (int idx = 0; idx < n_nonzero; idx++) {
                    packed_w[idx] = w_row[nonzero[idx]];
                }
                for (int idx = 0; idx < count; idx++) {
                    const float w = packed_w[idx];
                    const float *column = source + (size_t)idx * GN_EVAL_BATCH;
                    for (int n = 0; n < GN_EVAL_BATCH; n++) {
                        acc[n] += w * column[n];
                    }
                }
            } else {
                for (int j = 0; j < count; j++) {
                    const float w = w_row[j];
                    const float *column = source + (size_t)j * GN_EVAL_BATCH;
                    for (int n = 0; n < GN_EVAL_BATCH; n++) {
                        acc[n] += w * column[n];
                    }
                }
            }

            float *row_out = next + (size_t)i * GN_EVAL_BATCH;
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                row_out[n] = is_output ? batch_sigmoid(acc[n]) : batch_relu(acc[n]);
            }
        }
#endif

        current = next;
        next = (next == g_batch_a) ? g_batch_b : g_batch_a;
    }

    /* Un-transpose the five LIVE outputs and apply the nested-event clamp in
     * the order prob5_reduce applies it (nn_eval.c) — p1 against p0 first, so
     * the p2 clamp reads the CLAMPED p1. */
    for (int n = 0; n < live; n++) {
        float p[GN_NUM_OUTPUTS];
        for (int k = 0; k < GN_NUM_OUTPUTS; k++) {
            p[k] = current[(size_t)k * GN_EVAL_BATCH + n];
        }
        if (p[1] > p[0]) p[1] = p[0];
        const float lose = 1.0f - p[0];
        if (p[3] > lose) p[3] = lose;
        if (p[2] > p[1]) p[2] = p[1];
        if (p[4] > p[3]) p[4] = p[3];
        for (int k = 0; k < GN_NUM_OUTPUTS; k++) {
            out[n][k] = p[k];
        }
    }
}

#ifdef GN_BATCH_FILL_STATS
#define GN_BATCH_STATS_MAX 256
/* Instrumentation temporaire (T3A, largeur de lot) : combien de voies sur
 * GN_EVAL_BATCH portent réellement une position. Le noyau en calcule toujours
 * GN_EVAL_BATCH — voir forward_batch — donc tout ce qui manque ici est du
 * travail jeté. Compilée seulement sous -DGN_BATCH_FILL_STATS. */
unsigned long gn_batch_fill_calls = 0;
unsigned long gn_batch_fill_live = 0;
unsigned long gn_batch_fill_hist[GN_BATCH_STATS_MAX + 1] = {0};
#endif

int gn_evaluate_batch(const GnNetwork *net,
                      const GnPosition *const *positions, int count,
                      float (*probs)[GN_NUM_OUTPUTS])
{
    if (net == NULL || positions == NULL || probs == NULL || count < 0) {
        return -1;
    }

    if (net->format == GN_NETWORK_INT8) {
        if (count == 0) {
            return 0;
        }
        /* Row-major, the layout `gn_int8_model_evaluate` expects; it
         * transposes to feature-major itself, chunked at the kernel's
         * measured batch width -- not this function's concern twice.
         * `probs[count][GN_NUM_OUTPUTS]` is already contiguous row-major
         * float, so it doubles as the flat output buffer directly. */
        float *features = malloc((size_t)count * GN_NUM_FEATURES * sizeof(float));
        if (features == NULL) {
            return -1;
        }
        int status = 0;
        for (int n = 0; n < count && status == 0; n++) {
            if (gn_encode(positions[n], features + (size_t)n * GN_NUM_FEATURES) != 0) {
                status = -1;
            }
        }
        if (status == 0) {
            status = gn_int8_model_evaluate(&net->int8_model, features, count,
                                            &probs[0][0]);
        }
        free(features);
        return status;
    }

#ifdef GN_BATCH_FILL_STATS
    /* La taille de la DEMANDE, pas du tronçon : c'est elle qui permet de
     * calculer, hors ligne, le gâchis qu'une autre largeur fixe donnerait. */
    gn_batch_fill_calls++;
    gn_batch_fill_live += (unsigned long)count;
    if (count >= 1 && count <= GN_BATCH_STATS_MAX) {
        gn_batch_fill_hist[count]++;
    } else if (count > GN_BATCH_STATS_MAX) {
        gn_batch_fill_hist[0]++;
    }
#endif

    if (!batch_kernel_applies(&net->model)) {
        /* Same answers, no speed-up: the kernel was never verified on this
         * model shape, and an unverified fast path is how silent wrongness
         * ships. See gn_infer.h. */
        for (int n = 0; n < count; n++) {
            if (gn_evaluate(net, positions[n], probs[n]) != 0) {
                return -1;
            }
        }
        return 0;
    }

    for (int base = 0; base < count; base += GN_EVAL_BATCH) {
        const int chunk = (count - base < GN_EVAL_BATCH) ? count - base
                                                         : GN_EVAL_BATCH;

        /* Encode row-major first — gn_encode validates and refuses, exactly
         * as the scalar door does — then transpose to feature-major, at the
         * FIXED width the kernel forwards (dead lanes zeroed and discarded:
         * see forward_batch for why the width never varies). */
        memset(g_batch_in, 0, sizeof(g_batch_in));
        unsigned char seen[GN_NUM_FEATURES];
        memset(seen, 0, sizeof(seen));
        float features[GN_NUM_FEATURES];
        for (int n = 0; n < chunk; n++) {
            if (gn_encode(positions[base + n], features) != 0) {
                return -1;
            }
            for (int j = 0; j < GN_NUM_FEATURES; j++) {
                g_batch_in[(size_t)j * GN_EVAL_BATCH + n] = features[j];
                if (features[j] != 0.0f) {
                    seen[j] = 1;
                }
            }
        }
        /* Which features the input layer has to look at at all -- noted while
         * transposing, which already walks all 196. See forward_batch. */
        int nonzero[GN_NUM_FEATURES];
        int n_nonzero = 0;
        for (int j = 0; j < GN_NUM_FEATURES; j++) {
            if (seen[j]) {
                nonzero[n_nonzero++] = j;
            }
        }

#ifdef GN_BATCH_SPARSITY_SWITCH
        gn_sparsity_calls[net->slot]++;
        gn_sparsity_active[net->slot] += (unsigned long)n_nonzero;
        if ((unsigned long)n_nonzero > gn_sparsity_widest[net->slot]) {
            gn_sparsity_widest[net->slot] = (unsigned long)n_nonzero;
        }
        forward_batch(&net->model, g_batch_in, chunk,
                      net->sparsity ? nonzero : NULL, n_nonzero,
                      probs + base);
#else
        forward_batch(&net->model, g_batch_in, chunk, nonzero, n_nonzero,
                      probs + base);
#endif
    }
    return 0;
}

float gn_money_equity(const float probs[GN_NUM_OUTPUTS])
{
    /* nn_eval.c:217. See the derivation in gn_infer.h. */
    return 2.0f * probs[GN_P_WIN] + probs[GN_P_WIN_G] + probs[GN_P_WIN_BG]
           - probs[GN_P_LOSE_G] - probs[GN_P_LOSE_BG] - 1.0f;
}

void gn_probs_exclusive(const float probs[GN_NUM_OUTPUTS],
                        double out[GN_NUM_EXCLUSIVE])
{
    if (probs == NULL || out == NULL) {
        return;
    }

    const double win      = probs[GN_P_WIN];
    const double win_g    = probs[GN_P_WIN_G];
    const double win_bg   = probs[GN_P_WIN_BG];
    const double lose_g   = probs[GN_P_LOSE_G];
    const double lose_bg  = probs[GN_P_LOSE_BG];

    /* Floored at zero: see the note in gn_infer.h. The nesting the engine
     * enforces holds in float32, and widening to double can expose a margin
     * of about 1e-10 that float32 could not represent. */
    const double values[GN_NUM_EXCLUSIVE] = {
        win - win_g,
        win_g - win_bg,
        win_bg,
        (1.0 - win) - lose_g,
        lose_g - lose_bg,
        lose_bg,
    };

    for (int i = 0; i < GN_NUM_EXCLUSIVE; i++) {
        out[i] = values[i] > 0.0 ? values[i] : 0.0;
    }
}

int gn_probs_are_nested(const float probs[GN_NUM_OUTPUTS])
{
    if (probs == NULL) {
        return 0;
    }
    return probs[GN_P_WIN_G] <= probs[GN_P_WIN]
        && probs[GN_P_WIN_BG] <= probs[GN_P_WIN_G]
        && probs[GN_P_LOSE_G] <= 1.0f - probs[GN_P_WIN]
        && probs[GN_P_LOSE_BG] <= probs[GN_P_LOSE_G];
}

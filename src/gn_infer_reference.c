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
#include <string.h>

#include "nn_eval.h"

struct GnNetwork {
    NNModel model;
};

GnNetwork *gn_network_load(const char *path)
{
    if (path == NULL) {
        return NULL;
    }

    GnNetwork *net = calloc(1, sizeof(*net));
    if (net == NULL) {
        return NULL;
    }

    if (nn_load(&net->model, path) != 0) {
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
    nn_free(&net->model);
    free(net);
}

int gn_network_input_size(const GnNetwork *net)
{
    return (net == NULL) ? -1 : net->model.input_size;
}

int gn_evaluate_features(const GnNetwork *net, const float *features,
                         float probs[GN_NUM_OUTPUTS])
{
    if (net == NULL || features == NULL || probs == NULL) {
        return -1;
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
                          float (*out)[GN_NUM_OUTPUTS])
{
    const float *current = in;
    float *next = g_batch_a;
    const int total_layers = model->num_hidden + 1;

    for (int L = 0; L < total_layers; L++) {
        const int rows = model->layer_out[L];
        const int cols = model->layer_in[L];
        const float *W = model->weight[L];
        const float *bias = model->bias[L];
        const int is_output = (L == model->num_hidden);

        for (int i = 0; i < rows; i++) {
            float acc[GN_EVAL_BATCH];
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                acc[n] = bias[i];
            }

            /* The weight row is read once and reused across the batch. This
             * single reordering is the whole speed-up. The order of the sum
             * over j, per (i, n), is unchanged. */
            const float *w_row = W + (size_t)i * cols;
            for (int j = 0; j < cols; j++) {
                const float w = w_row[j];
                const float *column = current + (size_t)j * GN_EVAL_BATCH;
                for (int n = 0; n < GN_EVAL_BATCH; n++) {
                    acc[n] += w * column[n];
                }
            }

            float *row_out = next + (size_t)i * GN_EVAL_BATCH;
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                row_out[n] = is_output ? batch_sigmoid(acc[n]) : batch_relu(acc[n]);
            }
        }

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
        float features[GN_NUM_FEATURES];
        for (int n = 0; n < chunk; n++) {
            if (gn_encode(positions[base + n], features) != 0) {
                return -1;
            }
            for (int j = 0; j < GN_NUM_FEATURES; j++) {
                g_batch_in[(size_t)j * GN_EVAL_BATCH + n] = features[j];
            }
        }

        forward_batch(&net->model, g_batch_in, chunk, probs + base);
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

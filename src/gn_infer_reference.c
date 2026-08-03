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

#include <stdlib.h>

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

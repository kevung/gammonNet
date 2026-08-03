/*
 * gn_wasm.c -- the WebAssembly face of the evaluator.
 *
 * A shim, deliberately thin. Everything it exposes already exists in
 * `src/gn_infer.h`; what it adds is the two things a browser needs and a native
 * process does not:
 *
 *   1. Loading a model from BYTES rather than from a path. The model arrives
 *      over `fetch`, and there is no filesystem to point at.
 *   2. A single-network global. A page evaluates with one network at a time,
 *      and threading a handle through the JS boundary would buy nothing.
 *
 * On the file trick: `nn_load` of the reference engine takes a path. Rather
 * than fork it -- which would mean maintaining a second reader of the `.bin`
 * format, the exact thing `tools/export_model.py` refuses to do for the writer
 * -- the bytes are written into Emscripten's in-memory filesystem and the path
 * handed to the unmodified loader. MEMFS is RAM; there is no device behind it.
 * The cost is one transient copy of the model, about 2 MiB, freed immediately.
 *
 * SPDX-License-Identifier: MIT
 */

#include <emscripten.h>
#include <stdio.h>
#include <stdlib.h>

#include "gn_encoding.h"
#include "gn_infer.h"

static GnNetwork *g_network = NULL;

/* MEMFS, not a real path: RAM that `fopen` happens to understand. */
static const char *MODEL_PATH = "/gammonnet-model.bin";

/*
 * Load a network from a byte buffer.
 *
 * Returns 0 on success. Every non-zero return is a refusal, never a
 * degraded mode:
 *   -1  the buffer could not be staged
 *   -2  the model was rejected by `gn_network_load` -- unreadable, not prob5,
 *       or expecting an input size that is not ours
 */
EMSCRIPTEN_KEEPALIVE
int gnw_load_model(const unsigned char *bytes, int length)
{
    if (bytes == NULL || length <= 0) {
        return -1;
    }

    if (g_network != NULL) {
        gn_network_free(g_network);
        g_network = NULL;
    }

    FILE *staged = fopen(MODEL_PATH, "wb");
    if (staged == NULL) {
        return -1;
    }
    size_t written = fwrite(bytes, 1, (size_t)length, staged);
    fclose(staged);
    if (written != (size_t)length) {
        remove(MODEL_PATH);
        return -1;
    }

    g_network = gn_network_load(MODEL_PATH);
    remove(MODEL_PATH);

    return (g_network == NULL) ? -2 : 0;
}

EMSCRIPTEN_KEEPALIVE
int gnw_is_loaded(void)
{
    return g_network != NULL;
}

EMSCRIPTEN_KEEPALIVE
int gnw_num_features(void)
{
    return GN_NUM_FEATURES;
}

EMSCRIPTEN_KEEPALIVE
int gnw_num_outputs(void)
{
    return GN_NUM_OUTPUTS;
}

/*
 * Evaluate an encoded feature vector. `out` receives the five probabilities.
 * Returns 0, or -1 if no network is loaded.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_evaluate_features(const float *features, float *out)
{
    if (g_network == NULL) {
        return -1;
    }
    return gn_evaluate_features(g_network, features, out);
}

/*
 * Evaluate `count` feature vectors laid out back to back.
 *
 * The bench path, and eventually the search path. One boundary crossing for
 * many evaluations: at 0-ply speeds the JS/WASM call overhead would otherwise
 * be a large share of what we are trying to measure, and we would be timing
 * the boundary rather than the network.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_evaluate_batch(const float *features, float *out, int count)
{
    if (g_network == NULL || count < 0) {
        return -1;
    }
    for (int i = 0; i < count; i++) {
        if (gn_evaluate_features(g_network,
                                 features + (size_t)i * GN_NUM_FEATURES,
                                 out + (size_t)i * GN_NUM_OUTPUTS) != 0) {
            return -1;
        }
    }
    return 0;
}

EMSCRIPTEN_KEEPALIVE
float gnw_money_equity(const float *probs)
{
    return gn_money_equity(probs);
}

EMSCRIPTEN_KEEPALIVE
void gnw_free_model(void)
{
    if (g_network != NULL) {
        gn_network_free(g_network);
        g_network = NULL;
    }
}

/*
 * Whether this build was compiled with WASM SIMD.
 *
 * T21 compares a SIMD build against a scalar one, and the only thing worse
 * than an unmeasured penalty is a measurement that silently timed the wrong
 * binary. The flag is baked in at compile time so a loaded module can always
 * say which one it is.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_has_simd(void)
{
#ifdef __wasm_simd128__
    return 1;
#else
    return 0;
#endif
}

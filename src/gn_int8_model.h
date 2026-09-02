/*
 * gn_int8_model.h -- loading and forwarding the `BGQ8` int8 model format
 * (`tools/export_qat_int8.py`), through the deterministic int8 GEMM
 * (`gn_gemm_int8.h`).
 *
 * Kept separate from `gn_infer_reference.c` the way `gn_rules_reference.c`
 * and `gn_gemm_int8.c` already are: one file, one backend concern.
 * `gn_infer_reference.c` is the only caller -- it owns the opaque
 * `GnNetwork`, detects the file format, and dispatches here for the int8
 * branch. Nothing outside `gn_infer_reference.c` should include this header.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_INT8_MODEL_H
#define GN_INT8_MODEL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GN_INT8_NUM_OUTPUTS 5

typedef struct {
    int rows;
    int cols;
    int8_t *weights;   /* rows * cols */
    int32_t *bias;      /* rows */
    int32_t *shifts;    /* rows */
} GnInt8Layer;

typedef struct {
    int num_hidden;
    int input_size;
    float input_scale;
    int *hidden_sizes;         /* num_hidden */
    float *output_scales;      /* num_hidden */
    GnInt8Layer *layers;       /* num_hidden */
    float *head_weight;        /* GN_INT8_NUM_OUTPUTS x hidden_sizes[num_hidden-1] */
    float *head_bias;          /* GN_INT8_NUM_OUTPUTS */
} GnInt8Model;

/*
 * True if `path` starts with the `BGQ8` magic -- read once, cheaply, so the
 * caller can pick a loader without loading twice on the wrong one.
 */
int gn_int8_model_is(const char *path);

/*
 * Load a `BGQ8` file into `model` (zeroed first). Returns 0, or -1 on any
 * malformed input -- a truncated file, a shift outside 0..31 (the kernel
 * would refuse it at evaluation time; refusing at load time costs less), a
 * layer whose accumulator headroom is below 1.0
 * (`gn_gemm_int8_headroom`). Never approximated.
 */
int gn_int8_model_load(GnInt8Model *model, const char *path);

void gn_int8_model_free(GnInt8Model *model);

/*
 * `count` already-encoded feature rows (row-major, `count x input_size`,
 * the SAME layout `gn_encode` fills) -> `count x GN_INT8_NUM_OUTPUTS`
 * probabilities, row-major. Chunks internally through the kernel's batch
 * width; the caller does not chunk.
 *
 * Returns 0, or -1 if any layer's kernel call is refused.
 */
int gn_int8_model_evaluate(const GnInt8Model *model, const float *features,
                           int count, float *probs);

#ifdef __cplusplus
}
#endif

#endif /* GN_INT8_MODEL_H */

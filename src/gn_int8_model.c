/* gn_int8_model.c -- see gn_int8_model.h. */

#include "gn_int8_model.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gn_gemm_int8.h"

/* The chunk width this file forwards the kernel at. Not a kernel limit
 * (`gn_gemm_int8_relu_pc`'s accumulator caps a call at 256) -- it is the
 * width `bench_gemm_int8.c` actually measured DS-09's threshold at (×2,13),
 * and the width `gn_evaluate_batch`'s float32 path already chunks the
 * search's candidate lists at (`GN_EVAL_BATCH`). Matching it means a
 * decision's candidates get exactly the batch this project has evidence
 * for, not a wider one nobody has measured. */
#define GN_INT8_CHUNK 32

#define ACTIVATION_MAX 127

static int read_i32(FILE *f, int *out)
{
    return fread(out, sizeof(int32_t), 1, f) == 1;
}

static int read_f32(FILE *f, float *out)
{
    return fread(out, sizeof(float), 1, f) == 1;
}

int gn_int8_model_is(const char *path)
{
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return 0;
    }
    char magic[4] = {0};
    const int read = (int)fread(magic, 1, 4, file);
    fclose(file);
    return read == 4 && memcmp(magic, "BGQ8", 4) == 0;
}

void gn_int8_model_free(GnInt8Model *model)
{
    if (model == NULL) {
        return;
    }
    if (model->layers != NULL) {
        for (int i = 0; i < model->num_hidden; i++) {
            free(model->layers[i].weights);
            free(model->layers[i].bias);
            free(model->layers[i].shifts);
        }
    }
    free(model->layers);
    free(model->hidden_sizes);
    free(model->output_scales);
    free(model->head_weight);
    free(model->head_bias);
    memset(model, 0, sizeof(*model));
}

int gn_int8_model_load(GnInt8Model *model, const char *path)
{
    memset(model, 0, sizeof(*model));

    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return -1;
    }

    char magic[4];
    int32_t num_hidden = 0, input_size = 0;
    float input_scale = 0.0f;

    if (fread(magic, 1, 4, file) != 4 || memcmp(magic, "BGQ8", 4) != 0 ||
        !read_i32(file, &num_hidden) || num_hidden <= 0 ||
        !read_i32(file, &input_size) || input_size <= 0 ||
        !read_f32(file, &input_scale)) {
        fclose(file);
        return -1;
    }

    model->num_hidden = num_hidden;
    model->input_size = input_size;
    model->input_scale = input_scale;
    model->hidden_sizes = calloc((size_t)num_hidden, sizeof(int));
    model->output_scales = calloc((size_t)num_hidden, sizeof(float));
    model->layers = calloc((size_t)num_hidden, sizeof(GnInt8Layer));
    if (model->hidden_sizes == NULL || model->output_scales == NULL ||
        model->layers == NULL) {
        fclose(file);
        gn_int8_model_free(model);
        return -1;
    }

    for (int i = 0; i < num_hidden; i++) {
        int32_t size = 0;
        if (!read_i32(file, &size) || size <= 0) {
            fclose(file);
            gn_int8_model_free(model);
            return -1;
        }
        model->hidden_sizes[i] = size;
    }
    for (int i = 0; i < num_hidden; i++) {
        if (!read_f32(file, &model->output_scales[i])) {
            fclose(file);
            gn_int8_model_free(model);
            return -1;
        }
    }

    int cols = input_size;
    for (int i = 0; i < num_hidden; i++) {
        const int rows = model->hidden_sizes[i];
        GnInt8Layer *layer = &model->layers[i];
        layer->rows = rows;
        layer->cols = cols;

        /* Refused here rather than discovered mid-evaluation: the kernel
         * assumes this precondition, it does not re-check it per call. */
        if (gn_gemm_int8_headroom(cols) < 1.0) {
            fclose(file);
            gn_int8_model_free(model);
            return -1;
        }

        layer->weights = malloc((size_t)rows * cols);
        layer->bias = malloc((size_t)rows * sizeof(int32_t));
        layer->shifts = malloc((size_t)rows * sizeof(int32_t));
        if (layer->weights == NULL || layer->bias == NULL ||
            layer->shifts == NULL) {
            fclose(file);
            gn_int8_model_free(model);
            return -1;
        }
        if (fread(layer->weights, 1, (size_t)rows * cols, file) !=
                (size_t)rows * cols ||
            fread(layer->bias, sizeof(int32_t), rows, file) != (size_t)rows ||
            fread(layer->shifts, sizeof(int32_t), rows, file) != (size_t)rows) {
            fclose(file);
            gn_int8_model_free(model);
            return -1;
        }
        for (int r = 0; r < rows; r++) {
            /* The kernel refuses a shift outside 0..31 at evaluation time;
             * refusing a whole model at load time, once, costs less than
             * discovering it position by position. */
            if (layer->shifts[r] < 0 || layer->shifts[r] > 31) {
                fclose(file);
                gn_int8_model_free(model);
                return -1;
            }
        }
        cols = rows;
    }

    const int width = model->hidden_sizes[num_hidden - 1];
    model->head_weight = malloc((size_t)GN_INT8_NUM_OUTPUTS * width * sizeof(float));
    model->head_bias = malloc((size_t)GN_INT8_NUM_OUTPUTS * sizeof(float));
    if (model->head_weight == NULL || model->head_bias == NULL) {
        fclose(file);
        gn_int8_model_free(model);
        return -1;
    }
    if (fread(model->head_weight, sizeof(float), (size_t)GN_INT8_NUM_OUTPUTS * width, file) !=
            (size_t)GN_INT8_NUM_OUTPUTS * width ||
        fread(model->head_bias, sizeof(float), GN_INT8_NUM_OUTPUTS, file) !=
            GN_INT8_NUM_OUTPUTS) {
        fclose(file);
        gn_int8_model_free(model);
        return -1;
    }

    fclose(file);
    return 0;
}

/* One chunk of at most GN_INT8_CHUNK positions, already quantised
 * feature-major in `input` (`input_size x chunk`). Returns the last hidden
 * layer's output, feature-major (`width x chunk`), still on its uint8 grid
 * -- the caller dequantises and runs the float head. */
static int forward_chunk(const GnInt8Model *model, const uint8_t *input,
                         int chunk, uint8_t *scratch_a, uint8_t *scratch_b)
{
    const uint8_t *activations = input;
    uint8_t *out = scratch_a;
    uint8_t *other = scratch_b;

    for (int i = 0; i < model->num_hidden; i++) {
        const GnInt8Layer *layer = &model->layers[i];
        if (gn_gemm_int8_relu_pc(layer->weights, layer->rows, layer->cols,
                                 layer->bias, activations, chunk,
                                 layer->shifts, out) != 0) {
            return -1;
        }
        activations = out;
        uint8_t *swap = out;
        out = other;
        other = swap;
    }
    /* `activations` points at whichever of scratch_a/scratch_b the LAST
     * layer wrote -- the caller reads it from there, not from `out`, which
     * after the final swap points at the buffer about to be reused. */
    if (activations != scratch_a) {
        memcpy(scratch_a, activations,
              (size_t)model->hidden_sizes[model->num_hidden - 1] * chunk);
    }
    return 0;
}

int gn_int8_model_evaluate(const GnInt8Model *model, const float *features,
                           int count, float *probs)
{
    if (model == NULL || features == NULL || probs == NULL || count < 0) {
        return -1;
    }
    if (count == 0) {
        return 0;
    }

    const int input_size = model->input_size;
    const int width = model->hidden_sizes[model->num_hidden - 1];

    /* The ping-pong scratch buffers hold whichever hidden layer's output is
     * widest, not necessarily the LAST one: this network narrows
     * (512, 512, 256, 128), but nothing here assumes narrowing is the only
     * shape a model will ever have. Sizing by `width` (the last layer's,
     * 128) instead of this maximum (512, layers 0 and 1) let
     * `gn_gemm_int8_relu_pc` write past the allocation on every layer
     * wider than the last -- found by AddressSanitizer, not by the earlier
     * count=1 check, which happens to touch only the narrowing tail. */
    int max_width = input_size;
    for (int i = 0; i < model->num_hidden; i++) {
        if (model->hidden_sizes[i] > max_width) {
            max_width = model->hidden_sizes[i];
        }
    }

    uint8_t *quantised = malloc((size_t)input_size * GN_INT8_CHUNK);
    uint8_t *scratch_a = malloc((size_t)max_width * GN_INT8_CHUNK);
    uint8_t *scratch_b = malloc((size_t)max_width * GN_INT8_CHUNK);
    float *dequantised = malloc((size_t)width * GN_INT8_CHUNK * sizeof(float));
    if (quantised == NULL || scratch_a == NULL || scratch_b == NULL ||
        dequantised == NULL) {
        free(quantised);
        free(scratch_a);
        free(scratch_b);
        free(dequantised);
        return -1;
    }

    int status = 0;
    for (int base = 0; base < count && status == 0; base += GN_INT8_CHUNK) {
        const int chunk = (count - base < GN_INT8_CHUNK) ? count - base
                                                          : GN_INT8_CHUNK;

        /* Row-major features in, feature-major quantised uint8 out --
         * `input[j*chunk + n]`, the EXACT stride `gn_gemm_int8_relu_pc`
         * reads (its own `batch` argument, which IS `chunk` here -- not
         * the buffers' allocated width `GN_INT8_CHUNK`, wide only so one
         * allocation serves every chunk including a final partial one or a
         * lone `gn_evaluate_features` call at chunk=1). Using the
         * allocated width as the stride instead of `chunk` was exactly the
         * bug this comment now warns against: at chunk=1 the kernel reads
         * `input[j]` while this loop would have written `input[j*32]` --
         * every value scattered 32 slots from where it was read. */
        for (int n = 0; n < chunk; n++) {
            const float *row = features + (size_t)(base + n) * input_size;
            for (int j = 0; j < input_size; j++) {
                const long q = lroundf(row[j] / model->input_scale);
                quantised[(size_t)j * chunk + n] =
                    (uint8_t)(q < 0 ? 0 : (q > ACTIVATION_MAX ? ACTIVATION_MAX : q));
            }
        }

        if (forward_chunk(model, quantised, chunk, scratch_a, scratch_b) != 0) {
            status = -1;
            break;
        }

        const float last_scale = model->output_scales[model->num_hidden - 1];
        for (int j = 0; j < width; j++) {
            for (int n = 0; n < chunk; n++) {
                dequantised[(size_t)j * chunk + n] =
                    (float)scratch_a[(size_t)j * chunk + n] * last_scale;
            }
        }

        for (int n = 0; n < chunk; n++) {
            for (int k = 0; k < GN_INT8_NUM_OUTPUTS; k++) {
                float total = model->head_bias[k];
                const float *row = model->head_weight + (size_t)k * width;
                for (int j = 0; j < width; j++) {
                    total += row[j] * dequantised[(size_t)j * chunk + n];
                }
                probs[(size_t)(base + n) * GN_INT8_NUM_OUTPUTS + k] =
                    1.0f / (1.0f + expf(-total));
            }
        }
    }

    free(quantised);
    free(scratch_a);
    free(scratch_b);
    free(dequantised);
    return status;
}

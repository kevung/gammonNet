/* T73 -- the deterministic int8 GEMM. See gn_gemm_int8.h for the guarantee and
 * the overflow proof it rests on. */

#include "gn_gemm_int8.h"

#include <stddef.h>

#include "gn_tile.h"

#if defined(__wasm_simd128__)
#  include <wasm_simd128.h>
#  define GN_INT8_SIMD128 1
#elif defined(__AVX2__)
#  include <immintrin.h>
#  define GN_INT8_AVX2 1
#elif defined(__SSE2__) || defined(__x86_64__)
#  include <emmintrin.h>
#  define GN_INT8_SSE2 1
#endif

#define GN_INT8_PRODUCT_MAX 16129 /* 127 * 127 */

/*
 * The lane tile every vector path below steps the batch dimension by: eight
 * uint8 activations widened to eight int32 accumulators, which is one 128-bit
 * register of each on both SIMD128 and SSE2/AVX2.
 *
 * Named rather than spelled `8` in three loop conditions, and rounded with
 * `gn_round_down_multiple` rather than with a mask, so that the day this
 * becomes a tile the hardware chooses -- T84 parameterises the float kernel's
 * width -- the loop bound is still a multiple of the tile. See `gn_tile.h` for
 * the Go-port bug this shape forecloses. The assertion below is not idle: the
 * scalar tail makes any positive tile CORRECT, and a power of two is what makes
 * the widening pair (`extmul_low`/`extmul_high`, `unpacklo`/`unpackhi`) split
 * the register evenly.
 */
#define GN_INT8_LANES 8
GN_STATIC_ASSERT_POWER_OF_TWO(GN_INT8_LANES);

double gn_gemm_int8_headroom(int cols)
{
    if (cols <= 0) {
        return 0.0;
    }
    /* 2147483647 rather than INT32_MAX spelled out, so the bound is legible in
     * the same units as the product it is compared against. */
    return 2147483647.0 / ((double)cols * (double)GN_INT8_PRODUCT_MAX);
}

static int arguments_refused(const int8_t *weights, int rows, int cols,
                             const uint8_t *input, int batch, const void *out)
{
    if (weights == NULL || input == NULL || out == NULL) return 1;
    if (rows <= 0 || cols <= 0 || batch <= 0) return 1;
    /* The guarantee's precondition, checked and not assumed. */
    if (gn_gemm_int8_headroom(cols) < 1.0) return 1;
    return 0;
}

int gn_gemm_int8_raw_reference(const int8_t *weights, int rows, int cols,
                               const int32_t *bias, const uint8_t *input,
                               int batch, int32_t *out)
{
    if (arguments_refused(weights, rows, cols, input, batch, out)) {
        return -1;
    }
    for (int i = 0; i < rows; i++) {
        const int8_t *row = weights + (size_t)i * cols;
        int32_t *dst = out + (size_t)i * batch;
        for (int n = 0; n < batch; n++) {
            dst[n] = bias != NULL ? bias[i] : 0;
        }
        for (int j = 0; j < cols; j++) {
            const int32_t w = row[j];
            if (w == 0) {
                /* Sparsity is worth a branch here and nowhere else: skipping a
                 * zero weight cannot change a sum of integers, so this is a
                 * speed-up that provably does not move a single bit. */
                continue;
            }
            const uint8_t *column = input + (size_t)j * batch;
            for (int n = 0; n < batch; n++) {
                dst[n] += w * (int32_t)column[n];
            }
        }
    }
    return 0;
}

#if defined(GN_INT8_SIMD128)

/* WebAssembly SIMD128. `i32x4.dot_i16x8_s` multiplies eight int16 pairs and
 * adds them pairwise into four int32 -- the exact semantics of x86's
 * `_mm_madd_epi16`, which is why the two paths agree bit for bit without
 * anything being arranged. Both are fully specified: no rounding, no
 * flush-to-zero, no reassociation freedom for the compiler to exercise. */
static void accumulate_lane(int32_t *dst, int32_t w, const uint8_t *column,
                            int batch)
{
    const v128_t weight = wasm_i16x8_splat((int16_t)w);
    const int tiled = gn_round_down_multiple(batch, GN_INT8_LANES);
    int n = 0;
    for (; n < tiled; n += GN_INT8_LANES) {
        const v128_t bytes = wasm_v128_load64_zero(column + n);
        const v128_t widened = wasm_u16x8_extend_low_u8x16(bytes);
        const v128_t low = wasm_i32x4_extmul_low_i16x8(widened, weight);
        const v128_t high = wasm_i32x4_extmul_high_i16x8(widened, weight);
        wasm_v128_store(dst + n, wasm_i32x4_add(wasm_v128_load(dst + n), low));
        wasm_v128_store(dst + n + 4,
                        wasm_i32x4_add(wasm_v128_load(dst + n + 4), high));
    }
    for (; n < batch; n++) {
        dst[n] += w * (int32_t)column[n];
    }
}

const char *gn_gemm_int8_path(void) { return "simd128"; }

#elif defined(GN_INT8_AVX2) || defined(GN_INT8_SSE2)

static void accumulate_lane(int32_t *dst, int32_t w, const uint8_t *column,
                            int batch)
{
    const __m128i weight = _mm_set1_epi16((short)w);
    const int tiled = gn_round_down_multiple(batch, GN_INT8_LANES);
    int n = 0;
    for (; n < tiled; n += GN_INT8_LANES) {
        const __m128i bytes = _mm_loadl_epi64((const __m128i *)(column + n));
        const __m128i widened = _mm_unpacklo_epi8(bytes, _mm_setzero_si128());
        /* Low and high halves separately: the activations are 0..127 and the
         * weights -128..127, so every product fits int16 with room, and the
         * widening to int32 loses nothing. */
        const __m128i lo = _mm_mullo_epi16(widened, weight);
        const __m128i hi = _mm_mulhi_epi16(widened, weight);
        const __m128i first = _mm_unpacklo_epi16(lo, hi);
        const __m128i second = _mm_unpackhi_epi16(lo, hi);
        _mm_storeu_si128((__m128i *)(dst + n),
                         _mm_add_epi32(_mm_loadu_si128((const __m128i *)(dst + n)),
                                       first));
        _mm_storeu_si128((__m128i *)(dst + n + 4),
                         _mm_add_epi32(_mm_loadu_si128((const __m128i *)(dst + n + 4)),
                                       second));
    }
    for (; n < batch; n++) {
        dst[n] += w * (int32_t)column[n];
    }
}

#  if defined(GN_INT8_AVX2)
const char *gn_gemm_int8_path(void) { return "avx2"; }
#  else
const char *gn_gemm_int8_path(void) { return "sse2"; }
#  endif

#else

static void accumulate_lane(int32_t *dst, int32_t w, const uint8_t *column,
                            int batch)
{
    for (int n = 0; n < batch; n++) {
        dst[n] += w * (int32_t)column[n];
    }
}

const char *gn_gemm_int8_path(void) { return "scalar"; }

#endif

int gn_gemm_int8_raw(const int8_t *weights, int rows, int cols,
                     const int32_t *bias, const uint8_t *input, int batch,
                     int32_t *out)
{
    if (arguments_refused(weights, rows, cols, input, batch, out)) {
        return -1;
    }
    for (int i = 0; i < rows; i++) {
        const int8_t *row = weights + (size_t)i * cols;
        int32_t *dst = out + (size_t)i * batch;
        for (int n = 0; n < batch; n++) {
            dst[n] = bias != NULL ? bias[i] : 0;
        }
        for (int j = 0; j < cols; j++) {
            const int32_t w = row[j];
            if (w == 0) {
                continue;
            }
            accumulate_lane(dst, w, input + (size_t)j * batch, batch);
        }
    }
    return 0;
}

int gn_gemm_int8_relu(const int8_t *weights, int rows, int cols,
                      const int32_t *bias, const uint8_t *input, int batch,
                      int shift, uint8_t *out)
{
    if (arguments_refused(weights, rows, cols, input, batch, out)) {
        return -1;
    }
    if (shift < 0 || shift > 31) {
        return -1;
    }

    /* One row at a time, so the int32 accumulators for a whole layer never have
     * to exist at once: at 512 rows x 32 lanes that would be 64 KiB of live
     * state, which is most of a WebAssembly instance's L1 budget. */
    int32_t accumulator[256];
    if (batch > (int)(sizeof accumulator / sizeof accumulator[0])) {
        return -1;
    }

    for (int i = 0; i < rows; i++) {
        const int8_t *row = weights + (size_t)i * cols;
        for (int n = 0; n < batch; n++) {
            accumulator[n] = bias != NULL ? bias[i] : 0;
        }
        for (int j = 0; j < cols; j++) {
            const int32_t w = row[j];
            if (w == 0) {
                continue;
            }
            accumulate_lane(accumulator, w, input + (size_t)j * batch, batch);
        }
        uint8_t *dst = out + (size_t)i * batch;
        for (int n = 0; n < batch; n++) {
            /* An ARITHMETIC right shift on a negative accumulator rounds
             * towards minus infinity, which is well defined in C23 and, on
             * every compiler this project targets, in practice before it. The
             * clamp to zero happens after, so the direction of that rounding
             * can only matter for values that were about to be clamped anyway.
             * A rounding multiply here would be the one place the two targets
             * could disagree; a shift cannot. */
            const int32_t scaled = accumulator[n] >> shift;
            dst[n] = scaled <= 0 ? 0
                   : (scaled >= GN_INT8_ACTIVATION_MAX
                          ? (uint8_t)GN_INT8_ACTIVATION_MAX
                          : (uint8_t)scaled);
        }
    }
    return 0;
}

int gn_gemm_int8_relu_pc(const int8_t *weights, int rows, int cols,
                         const int32_t *bias, const uint8_t *input, int batch,
                         const int32_t *shifts, uint8_t *out)
{
    /* Same kernel as `gn_gemm_int8_relu`, ONE requantisation shift PER ROW
     * instead of one for the whole layer. Training quantises weights
     * per-channel (`QuantizedLinear.quantized_weight`, one scale per output
     * neuron -- deliberately, a layer-wide scale would waste resolution on
     * every channel narrower than the widest one). A single layer-wide shift
     * cannot represent that without discarding exactly the precision QAT was
     * trained to keep, so a deployed per-channel-trained model needs this. The
     * accumulation loop is untouched -- it does not know about shift at all,
     * per-row or otherwise -- only the epilogue changes. */
    if (arguments_refused(weights, rows, cols, input, batch, out)) {
        return -1;
    }
    if (shifts == NULL) {
        return -1;
    }

    int32_t accumulator[256];
    if (batch > (int)(sizeof accumulator / sizeof accumulator[0])) {
        return -1;
    }

    for (int i = 0; i < rows; i++) {
        if (shifts[i] < 0 || shifts[i] > 31) {
            return -1;
        }
    }

    for (int i = 0; i < rows; i++) {
        const int8_t *row = weights + (size_t)i * cols;
        for (int n = 0; n < batch; n++) {
            accumulator[n] = bias != NULL ? bias[i] : 0;
        }
        for (int j = 0; j < cols; j++) {
            const int32_t w = row[j];
            if (w == 0) {
                continue;
            }
            accumulate_lane(accumulator, w, input + (size_t)j * batch, batch);
        }
        uint8_t *dst = out + (size_t)i * batch;
        const int shift = shifts[i];
        for (int n = 0; n < batch; n++) {
            const int32_t scaled = accumulator[n] >> shift;
            dst[n] = scaled <= 0 ? 0
                   : (scaled >= GN_INT8_ACTIVATION_MAX
                          ? (uint8_t)GN_INT8_ACTIVATION_MAX
                          : (uint8_t)scaled);
        }
    }
    return 0;
}

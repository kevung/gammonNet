/*
 * gn_kernel_f32.h -- the batch inner loop, written by hand.
 *
 * T84. WHAT QUESTION THIS ANSWERS, AND WHY IT IS NOT "8 OR 32"
 *
 * `GN_EVAL_BATCH` is 32 because the search groups the 21 rolls so that a batch
 * is full. That grouping costs three phases in `gn_search.c`'s `rank_plays`.
 * The question T84 asks is whether it still earns them once the kernel is
 * written by hand -- because every previous width sweep measured something
 * else. T3A named it: gcc does not vectorise the hot loop below 24, so testing
 * a width of 8 with the compiler's auto-vectoriser is falling off a cliff, not
 * measuring the machine.
 *
 * WHAT THE COMPILER DOES AND WHAT IT WILL NOT DO
 *
 * Read from `-fopt-info-vec` on 2026-09-02: the shipped kernel is vectorised
 * "using 16 byte vectors and unroll factor 4" -- SSE, four floats, because the
 * default native build targets baseline x86-64 and has no AVX2. Auto-
 * vectorisation covers the batch dimension `n` and nothing else.
 *
 * It will not tile over the OUTPUT ROWS, and that is exactly what a narrow
 * batch needs. At width 8 with 8-wide vectors there is one accumulator, so the
 * loop over `j` is a chain of dependent `addps`, four cycles apart, whatever
 * the width of the vector. Accumulating R rows against the same column breaks
 * that chain into R independent ones and reads the column once for R rows. The
 * kernel below therefore always holds EIGHT vector accumulators, arranged as
 * `GN_KERNEL_ROWS` rows of `GN_KERNEL_VECS` vectors -- 1x8, 2x4, 4x2 or 8x1
 * depending on the compiled width and the target's lane count.
 *
 * BIT-EXACTNESS, WHICH IS NOT NEGOTIABLE
 *
 * Vectorising over `n` does not touch the summation order: lane `n` sums over
 * `j` in exactly the scalar order, independently of every other lane. Tiling
 * over rows does not either -- row `i` is a different sum. So this kernel is
 * bit-identical to the scalar path BY CONSTRUCTION, at every width, and
 * `bench_kernel` checks it rather than trusting the argument.
 *
 * The one way to lose it is FMA: `_mm256_fmadd_ps` rounds once where mul-then-
 * add rounds twice. The multiplies and adds below are written separately AND
 * the translation unit is compiled `-ffp-contract=off`, because gcc is
 * otherwise free to contract even explicitly written intrinsics.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_KERNEL_F32_H
#define GN_KERNEL_F32_H

#include "gn_infer.h"
#include "gn_tile.h"

/* ── One vector of floats, per target ────────────────────────────────── */

#if defined(GN_KERNEL_FORCE_SCALAR)
#  define GN_VEC_LANES 1
#  define GN_KERNEL_NAME "scalaire (forcé)"
#elif defined(__wasm_simd128__)
#  include <wasm_simd128.h>
#  define GN_VEC_LANES 4
#  define GN_KERNEL_NAME "simd128"
typedef v128_t gnv;
#  define gnv_load(p)      wasm_v128_load(p)
#  define gnv_store(p, v)  wasm_v128_store((p), (v))
#  define gnv_splat(x)     wasm_f32x4_splat(x)
#  define gnv_mul(a, b)    wasm_f32x4_mul((a), (b))
#  define gnv_add(a, b)    wasm_f32x4_add((a), (b))
#elif defined(__AVX__)
#  include <immintrin.h>
#  define GN_VEC_LANES 8
#  define GN_KERNEL_NAME "avx"
typedef __m256 gnv;
#  define gnv_load(p)      _mm256_loadu_ps(p)
#  define gnv_store(p, v)  _mm256_storeu_ps((p), (v))
#  define gnv_splat(x)     _mm256_set1_ps(x)
#  define gnv_mul(a, b)    _mm256_mul_ps((a), (b))
#  define gnv_add(a, b)    _mm256_add_ps((a), (b))
#elif defined(__SSE2__) || defined(__x86_64__)
#  include <emmintrin.h>
#  define GN_VEC_LANES 4
#  define GN_KERNEL_NAME "sse2"
typedef __m128 gnv;
#  define gnv_load(p)      _mm_loadu_ps(p)
#  define gnv_store(p, v)  _mm_storeu_ps((p), (v))
#  define gnv_splat(x)     _mm_set1_ps(x)
#  define gnv_mul(a, b)    _mm_mul_ps((a), (b))
#  define gnv_add(a, b)    _mm_add_ps((a), (b))
#else
#  define GN_VEC_LANES 1
#  define GN_KERNEL_NAME "scalaire"
#endif

#if GN_VEC_LANES == 1
typedef float gnv;
#  define gnv_load(p)      (*(p))
#  define gnv_store(p, v)  (*(p) = (v))
#  define gnv_splat(x)     (x)
#  define gnv_mul(a, b)    ((a) * (b))
#  define gnv_add(a, b)    ((a) + (b))
#  ifndef GN_KERNEL_NAME
#    define GN_KERNEL_NAME "scalaire"
#  endif
#endif

/*
 * The width must be a whole number of vectors, so that there is ONE compiled
 * path and no epilogue -- the property `forward_batch` rests on for its
 * bit-exactness across chunk sizes. This is T90's assertion, on its first real
 * consumer: at a width that is not a multiple of the lane count the build stops
 * here instead of growing a tail loop nobody measured.
 */
GN_STATIC_ASSERT_MULTIPLE_OF(GN_EVAL_BATCH, GN_VEC_LANES);

#define GN_KERNEL_VECS (GN_EVAL_BATCH / GN_VEC_LANES)

/*
 * Eight vector accumulators, always. Below eight the dependent-add chain shows;
 * above eight the register file spills. So the row tile is whatever makes the
 * product eight -- 8x1, 4x2, 2x4, 1x8 -- and at a width so wide that one row
 * already fills eight vectors, the tile is one row and the chain is broken by
 * the width itself.
 */
#if GN_KERNEL_VECS >= 8
#  define GN_KERNEL_ROWS 1
#else
#  define GN_KERNEL_ROWS (8 / GN_KERNEL_VECS)
#endif

/*
 * acc[r][n] += sum over k of weights[r * count + k] * columns[k * W + n],
 * for r < GN_KERNEL_ROWS and n < GN_EVAL_BATCH.
 *
 * `columns` is feature-major with stride GN_EVAL_BATCH -- the layout the batch
 * path already uses, dense or compacted, because the compaction gathers into
 * exactly the same shape.
 */
static inline void gn_kernel_block(float *acc, const float *weights,
                                   const float *columns, int count)
{
    gnv a[GN_KERNEL_ROWS][GN_KERNEL_VECS];
    for (int r = 0; r < GN_KERNEL_ROWS; r++) {
        for (int v = 0; v < GN_KERNEL_VECS; v++) {
            a[r][v] = gnv_load(acc + r * GN_EVAL_BATCH + v * GN_VEC_LANES);
        }
    }

    for (int k = 0; k < count; k++) {
        const float *column = columns + (size_t)k * GN_EVAL_BATCH;
        gnv col[GN_KERNEL_VECS];
        for (int v = 0; v < GN_KERNEL_VECS; v++) {
            col[v] = gnv_load(column + v * GN_VEC_LANES);
        }
        /* The column is read ONCE and reused across the row tile -- the same
         * reordering the batch kernel already applies to the weight row, now
         * applied to the other operand. */
        for (int r = 0; r < GN_KERNEL_ROWS; r++) {
            const gnv w = gnv_splat(weights[(size_t)r * count + k]);
            for (int v = 0; v < GN_KERNEL_VECS; v++) {
                a[r][v] = gnv_add(a[r][v], gnv_mul(w, col[v]));
            }
        }
    }

    for (int r = 0; r < GN_KERNEL_ROWS; r++) {
        for (int v = 0; v < GN_KERNEL_VECS; v++) {
            gnv_store(acc + r * GN_EVAL_BATCH + v * GN_VEC_LANES, a[r][v]);
        }
    }
}

/* The same for a single row: the tail of a layer whose row count is not a
 * multiple of the tile (the output layer has five). */
static inline void gn_kernel_row(float *acc, const float *weights,
                                 const float *columns, int count)
{
    gnv a[GN_KERNEL_VECS];
    for (int v = 0; v < GN_KERNEL_VECS; v++) {
        a[v] = gnv_load(acc + v * GN_VEC_LANES);
    }
    for (int k = 0; k < count; k++) {
        const float *column = columns + (size_t)k * GN_EVAL_BATCH;
        const gnv w = gnv_splat(weights[k]);
        for (int v = 0; v < GN_KERNEL_VECS; v++) {
            a[v] = gnv_add(a[v], gnv_mul(w, gnv_load(column + v * GN_VEC_LANES)));
        }
    }
    for (int v = 0; v < GN_KERNEL_VECS; v++) {
        gnv_store(acc + v * GN_VEC_LANES, a[v]);
    }
}

#endif /* GN_KERNEL_F32_H */

/*
 * gn_tile.h -- widths, tiles, and the rounding that assumes nothing.
 *
 * WHY THIS FILE EXISTS
 *
 * A tiled kernel walks its dimension in full tiles and then finishes the
 * remainder by hand. It therefore needs the largest multiple of `tile` that
 * does not exceed `n`. The obvious way to write that is
 *
 *     rounded = n & ~(tile - 1);          // WRONG unless tile is 2^k
 *
 * and it is wrong in the worst possible way: it is CORRECT for every tile the
 * code happens to use today, and silently out of bounds for the first one that
 * is not a power of two. The Go port of this engine shipped exactly that line.
 * At tile 6 and n = 195 it yields 194 -- which is not a multiple of 6 -- so the
 * loop `for (j = 0; j < rounded; j += tile)` reaches j = 192 and reads
 * row[192..197] out of a row of 195. The tests did not catch it because the
 * tile was 4 when they were written. `GN_EVAL_BATCH` is 32 here, so the C side
 * has never been wrong; this header exists so that it cannot start being wrong
 * the day a width stops being a power of two, which is precisely what T84's
 * hand-written kernel makes possible.
 *
 * The rule this header enforces:
 *
 *   - `gn_round_down_multiple` where the tile is not GUARANTEED to be a power
 *     of two. It costs essentially nothing when it is: with a compile-time
 *     constant tile, gcc -O3 emits `andl $-8` for tile 8 -- the very
 *     instruction the mask form emits -- plus a `test`/`cmov` pair for the
 *     non-positive guard, and a multiply-shift for tile 6. Read from the
 *     generated assembly on 2026-09-02, not assumed. Those two extra
 *     instructions are paid ONCE per kernel call, not once per element.
 *   - `GN_STATIC_ASSERT_POWER_OF_TWO` where a power of two IS assumed, so the
 *     assumption is stated to the compiler rather than to the reader.
 *
 * A comment saying "tile must be a power of two" is not a guard rail. A build
 * that stops is.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_TILE_H
#define GN_TILE_H

/*
 * `_Static_assert` is C11 and this project compiles at `-std=c11` on every
 * target (native gcc/clang, Emscripten). The fallback is there so that a
 * consumer copying this header into an older dialect gets a diagnostic rather
 * than a silent no-check.
 */
#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
#  define GN_STATIC_ASSERT(condition, message) _Static_assert(condition, message)
#else
#  define GN_STATIC_ASSERT_CAT_(a, b) a##b
#  define GN_STATIC_ASSERT_ID_(a, b) GN_STATIC_ASSERT_CAT_(a, b)
#  define GN_STATIC_ASSERT(condition, message) \
      typedef char GN_STATIC_ASSERT_ID_(gn_static_assert_, __LINE__)[(condition) ? 1 : -1]
#endif

/*
 * A constant expression, usable inside `_Static_assert`. Zero is NOT a power of
 * two here: a tile of zero is a division by zero downstream, and a width of
 * zero is a kernel that computes nothing. Both should fail the assertion.
 */
/* A compile-time constant, spelled out in a message or a report. */
#define GN_STRINGIFY_(x) #x
#define GN_STRINGIFY(x) GN_STRINGIFY_(x)

#define GN_IS_POWER_OF_TWO(n) ((n) > 0 && ((n) & ((n) - 1)) == 0)

/* State the assumption to the compiler. Use it wherever a mask, a shift or an
 * `&`-based rounding stands in for a division. */
#define GN_STATIC_ASSERT_POWER_OF_TWO(n) \
    GN_STATIC_ASSERT(GN_IS_POWER_OF_TWO(n), #n " must be a power of two")

/* The other assumption a tiled kernel makes, and the one that actually matters
 * for a fixed-width kernel: that the width divides evenly into tiles, so the
 * scalar tail is empty and every lane goes through the same code path. */
#define GN_STATIC_ASSERT_MULTIPLE_OF(n, tile) \
    GN_STATIC_ASSERT((tile) > 0 && (n) % (tile) == 0, \
                     #n " must be a whole number of " #tile "-wide tiles")

/*
 * The largest multiple of `tile` that does not exceed `n`.
 *
 * Assumes nothing about `tile` beyond being positive. Returns 0 for a
 * non-positive tile rather than dividing by zero -- a kernel that then loops
 * zero times and falls entirely into its scalar tail is slow, which is a
 * failure mode one can see, unlike reading past the end of a matrix.
 *
 * POSTCONDITION, and it is the whole point: the result is <= n AND is an exact
 * multiple of `tile`. `n & ~(tile - 1)` satisfies the first and violates the
 * second, which is why it can overrun.
 */
static inline int gn_round_down_multiple(int n, int tile)
{
    if (tile <= 0 || n <= 0) {
        return 0;
    }
    return n - (n % tile);
}

#endif /* GN_TILE_H */

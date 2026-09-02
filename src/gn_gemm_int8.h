/*
 * T73 -- the deterministic int8 GEMM.
 *
 * WHY THIS EXISTS, AND WHAT IT GUARANTEES
 *
 * The project's bit-for-bit guarantee (native == WebAssembly, to the last bit)
 * cost real effort in float32: the reference gap of 4.77e-07 across seven
 * platforms is what a careful float kernel gets you, not what it gives you for
 * free. Float addition is not associative, so any change in summation order --
 * a different vector width, an FMA contraction, a compiler's epilogue -- moves
 * the answer.
 *
 * Integer addition IS associative and commutative. Provided nothing overflows,
 * every summation order yields the SAME int32, on every target, forever. So the
 * int8 path does not merely preserve the bit-for-bit guarantee: it makes it
 * unconditional. Scalar, SIMD128, SSE2, AVX2 -- same bits, by construction and
 * not by care.
 *
 * That conditional is the whole burden of proof, and it is discharged here:
 * every product is bounded by 127*127 = 16129, so `cols` of them sum to at most
 * cols * 16129. At cols = 512 that is 8,258,048, which is 2^31 / 260. Even the
 * widest layer this project will plausibly train leaves more than two orders of
 * magnitude of headroom. `gn_gemm_int8_headroom` returns it, and the callers
 * check rather than assume.
 *
 * WHAT THIS FILE IS NOT
 *
 * It is not an NNUE incremental accumulator -- DS-04 ruled that out for this
 * project (dense inputs, batched evaluation), and it is not the relaxed-dot
 * 7-bit path either. Relaxed SIMD gives a further speed-up on Chrome, Firefox
 * and Android but NOT on Safari/iOS, and its result is implementation-defined:
 * it is opt-in, detected at run time, and lives OUTSIDE this guarantee. Nothing
 * in this header may be compiled to relaxed instructions.
 *
 * No GPL code was read to write this. `i32x4.dot_i16x8_s` and `_mm_madd_epi16`
 * are instructions documented by their vendors; using an instruction is not
 * deriving from a program that also uses it.
 */

#ifndef GN_GEMM_INT8_H
#define GN_GEMM_INT8_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * The ClippedReLU ceiling. Activations live in 0..127 so that they fit an int8
 * with the sign bit unused, which is what lets a weight (also int8) multiply
 * them without a widening step the vector units would charge for.
 */
#define GN_INT8_ACTIVATION_MAX 127

/*
 * How much int32 headroom a layer of `cols` inputs leaves, as a factor. Above
 * 1.0 the layer cannot overflow whatever order the terms are summed in, which
 * is exactly the condition the bit-for-bit guarantee rests on. Callers must
 * check it; the kernels assume it.
 */
double gn_gemm_int8_headroom(int cols);

/*
 * One quantised layer, batched.
 *
 *   weights   int8, row-major, `rows` x `cols`
 *   bias      int32, `rows`, already scaled to the accumulator's units
 *   input     uint8 activations in 0..GN_INT8_ACTIVATION_MAX, FEATURE-MAJOR:
 *             `cols` x `batch`, so lane `n` of input `j` is input[j*batch + n].
 *             Feature-major is what makes one weight row serve the whole batch
 *             from a single read -- the same layout the float batch kernel uses.
 *   batch     number of live lanes; must be the fixed kernel width
 *   shift     requantisation, a POWER OF TWO expressed as a right shift. Scale
 *             factors are constrained to powers of two at training time so that
 *             rescaling is a shift and not a multiply-round -- a shift is exact
 *             and identical everywhere, a rounding multiply is neither.
 *   out       uint8, `rows` x `batch`, feature-major, ClippedReLU applied
 *
 * Returns 0, or -1 on a refused argument -- including a layer whose headroom is
 * below 1.0. An unverified fast path is how silent wrongness ships.
 */
int gn_gemm_int8_relu(const int8_t *weights, int rows, int cols,
                      const int32_t *bias, const uint8_t *input, int batch,
                      int shift, uint8_t *out);

/*
 * The same, but `shifts` is ONE PER ROW instead of one for the whole layer.
 * Training quantises weights per-channel (one scale per output neuron); a
 * layer-wide shift cannot represent that scale WITHOUT throwing away exactly
 * the precision QAT was trained to keep. Deploying a per-channel-trained
 * model needs this entry point, not `gn_gemm_int8_relu`.
 *
 * `shifts` has `rows` entries. Same bounds as `shift` above, checked per row.
 */
int gn_gemm_int8_relu_pc(const int8_t *weights, int rows, int cols,
                         const int32_t *bias, const uint8_t *input, int batch,
                         const int32_t *shifts, uint8_t *out);

/*
 * The same, without activation or requantisation: raw int32 accumulators,
 * `rows` x `batch`, feature-major. This is the output layer, whose five values
 * become probabilities in float -- the only place a float appears on this path.
 */
int gn_gemm_int8_raw(const int8_t *weights, int rows, int cols,
                     const int32_t *bias, const uint8_t *input, int batch,
                     int32_t *out);

/*
 * The scalar reference, always compiled, never dispatched over. Tests compare
 * the dispatched kernel against it; if they ever differ, the claim of this
 * header is false and the build should fail rather than ship.
 */
int gn_gemm_int8_raw_reference(const int8_t *weights, int rows, int cols,
                               const int32_t *bias, const uint8_t *input,
                               int batch, int32_t *out);

/*
 * Which path the build actually dispatches to: "scalar", "simd128", "sse2" or
 * "avx2". Reported by the micro-benchmark so that a number always says which
 * kernel produced it.
 */
const char *gn_gemm_int8_path(void);

#ifdef __cplusplus
}
#endif

#endif /* GN_GEMM_INT8_H */

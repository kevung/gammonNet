/*
 * gn_infer.h -- network inference: a position in, five probabilities out.
 *
 * THE DISTRIBUTION IS THE OUTPUT. THE EQUITY IS A CONVENIENCE.
 *
 * That inversion is the whole point of this header. The reference engine's
 * `nn_forward` returns a cubeless money equity and fills the five
 * probabilities only if asked. Match play needs the opposite: the match
 * equity table converts a *distribution* into match winning chances, and a
 * scalar money equity has already thrown away what it needs. `PLAN.md` calls
 * this out as the trap of T10, so the interface is shaped to make the trap
 * unreachable — `gn_evaluate` cannot return an equity, only probabilities.
 *
 * The five outputs, in the order the reference engine establishes:
 *
 *   probs[0]  P(the on-roll player wins at all)
 *   probs[1]  P(wins a gammon or better)
 *   probs[2]  P(wins a backgammon)
 *   probs[3]  P(loses a gammon or better)
 *   probs[4]  P(loses a backgammon)
 *
 * They are NESTED, not exclusive: probs[1] counts backgammons too. The order
 * is not taken on trust from a comment. It is forced by the equity formula at
 * `vendor/backgammon-ai-engine/c_inference/nn_eval.c:217`,
 *
 *     E = 2*p0 + p1 + p2 - p3 - p4 - 1
 *
 * which is the algebraic consequence of that reading and of no other:
 *
 *     1*(p0-p1) + 2*(p1-p2) + 3*p2          winning single, gammon, backgammon
 *   - 1*((1-p0)-p3) - 2*(p3-p4) - 3*p4      losing the same three ways
 *   = 2*p0 + p1 + p2 - p3 - p4 - 1
 *
 * Permute the five and the identity breaks. `model.py:284` agrees in prose
 * ("canonical order: P(win), P(wg), P(wbg), P(lg), P(lbg)"), but the algebra
 * is what makes it checkable.
 *
 * A network handed an input it has never seen returns five perfectly
 * plausible numbers and says nothing about it. Every entry point here refuses
 * rather than approximates.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_INFER_H
#define GN_INFER_H

#include "gn_encoding.h"
#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GN_NUM_OUTPUTS 5

#define GN_P_WIN       0
#define GN_P_WIN_G     1
#define GN_P_WIN_BG    2
#define GN_P_LOSE_G    3
#define GN_P_LOSE_BG   4

/* Opaque: the backend is deliberately invisible here. T22 will decide which
 * inference engine we ship, and that decision must not reach this header. */
typedef struct GnNetwork GnNetwork;

/*
 * Load a network from a flat `.bin` file (magic "BGNN").
 *
 * Returns NULL if the file is missing, malformed, or declares something this
 * build cannot evaluate — a refusal, never a fallback. In particular a model
 * whose output mode is not prob5 is refused: it emits an aggregated money
 * equity, which is unusable in match play, and silently so.
 */
GnNetwork *gn_network_load(const char *path);

void gn_network_free(GnNetwork *net);

/* Number of input features the network expects. Must equal GN_NUM_FEATURES
 * for any model this project uses; checked at load time. */
int gn_network_input_size(const GnNetwork *net);

/*
 * Evaluate a position. Encodes it, runs the network, writes the five
 * probabilities.
 *
 * Returns 0 on success, -1 if the position is not structurally valid. There is
 * no third outcome and no default vector: an input the network has never seen
 * is refused here rather than answered plausibly.
 */
int gn_evaluate(const GnNetwork *net, const GnPosition *pos,
                float probs[GN_NUM_OUTPUTS]);

/*
 * Evaluate a feature vector that the caller has already encoded.
 *
 * The path the search will use, once it holds its own encoded positions. It
 * skips validation of the board because there is no board to validate — the
 * caller owns that responsibility, and `gn_evaluate` is the safe door.
 */
int gn_evaluate_features(const GnNetwork *net, const float *features,
                         float probs[GN_NUM_OUTPUTS]);

/* Largest number of positions one gn_evaluate_batch call forwards together.
 * 32 is where bench/bench_batch.c measured the bandwidth win (×2,21); larger
 * counts are handled by the caller chunking.
 *
 * OVERRIDABLE AT COMPILE TIME (`-DGN_EVAL_BATCH=8`), and only so that T84 can
 * measure what a narrow width costs with the width still a COMPILE-TIME
 * CONSTANT. That distinction is the whole reason the question was open: a bench
 * whose width is a run-time variable emits a different vector/epilogue path and
 * measures its own shape, not the kernel's (`bench/bench_batch.c` says so about
 * itself). It is not a run-time setting and there is no dispatch on it. */
#ifndef GN_EVAL_BATCH
#define GN_EVAL_BATCH 32
#endif

/*
 * Evaluate up to `count` positions in one pass over the weights.
 *
 * BIT-IDENTICAL to calling gn_evaluate once per position — not merely close.
 * The batch kernel reorders WHICH position a weight row multiplies next, but
 * the summation order per (output, position) is exactly the scalar order —
 * the property bench/bench_batch.c states and T21 verified on the 2000
 * -position reference (max|Δ| = 0). A speed-up bought with a silent change of
 * results would be worth nothing here.
 *
 * Models the batch kernel was never verified on (activation other than relu,
 * output mode other than prob5, layers wider than the kernel's buffers) fall
 * back to the scalar path per item: same answers, no speed-up, no refusal.
 *
 * Returns 0 on success, -1 if any position is refused — in which case the
 * whole call is refused, exactly as the scalar loop would have stopped.
 */
int gn_evaluate_batch(const GnNetwork *net,
                      const GnPosition *const *positions, int count,
                      float (*probs)[GN_NUM_OUTPUTS]);

/*
 * The same, entered from FEATURES the caller already holds, laid out row-major
 * (`count` vectors of GN_NUM_FEATURES).
 *
 * BIT-IDENTICAL to calling gn_evaluate_features once per vector, for the same
 * reason gn_evaluate_batch is: the kernel parallelises over positions, not over
 * the summation. The chunks that do not fill GN_EVAL_BATCH lanes go through the
 * scalar door instead of forwarding a mostly empty batch — which is only
 * allowed BECAUSE the two agree bit for bit.
 *
 * T91 added it for `gnw_evaluate_batch`, the WebAssembly export that gammonGo's
 * `analyze()` calls with hundreds of vectors at a time and that used to loop
 * the scalar path — the loop whose single accumulator was the whole reason the
 * artifact carried `-fassociative-math`.
 */
int gn_evaluate_features_batch(const GnNetwork *net, const float *features,
                               int count, float (*probs)[GN_NUM_OUTPUTS]);

/*
 * Which batch kernel this build compiled ("auto-vectorisé", or the hand-written
 * one with its target and its row x vector tile), and at what width.
 *
 * Reported by every batch benchmark, so that a number always says which code
 * produced it -- the same discipline `gn_gemm_int8_path` already imposes on the
 * int8 side. T84 measures three widths and two kernels; a table of six figures
 * with no such label would be six figures nobody can reproduce.
 */
const char *gn_batch_kernel(void);
int gn_batch_width(void);

/*
 * Cubeless money equity, in points, from a distribution.
 *
 * Offered because it is genuinely useful for money play and for comparing
 * against engines that print it. It is a projection of the distribution, so it
 * loses information: never feed it to the match equity table.
 */
float gn_money_equity(const float probs[GN_NUM_OUTPUTS]);

/*
 * Whether a distribution satisfies the nested-event inequalities:
 *
 *   probs[1] <= probs[0]        a gammon is a win
 *   probs[2] <= probs[1]        a backgammon is a gammon
 *   probs[3] <= 1 - probs[0]    a gammon loss is a loss
 *   probs[4] <= probs[3]
 *
 * Returns 1 if they hold, 0 otherwise. The five outputs come from five
 * independent sigmoids, so nothing in the network guarantees them; the
 * reference engine clamps them, and this is how we check the clamp actually
 * ran. A distribution that violates these is not a distribution.
 */
int gn_probs_are_nested(const float probs[GN_NUM_OUTPUTS]);

#define GN_NUM_EXCLUSIVE 6

#define GN_E_WIN_SINGLE   0
#define GN_E_WIN_G        1
#define GN_E_WIN_BG       2
#define GN_E_LOSE_SINGLE  3
#define GN_E_LOSE_G       4
#define GN_E_LOSE_BG      5

/*
 * Turn the nested probabilities into the six MUTUALLY EXCLUSIVE outcomes:
 * winning a single game, a gammon, a backgammon, and losing the same three.
 *
 * Every consumer that converts an evaluation into an equity needs this
 * decomposition, and every one of them would otherwise write the same four
 * subtractions. Writing them once, here, is not a convenience -- it is where a
 * real trap is disarmed.
 *
 * The trap: nesting is enforced in float32, which is the arithmetic the
 * network and the reference engine use. In float32 a P(win) of 1.5e-10 makes
 * `1.0f - P(win)` exactly 1.0f, so P(lose gammon) = 1.0 satisfies the
 * inequality and nothing is clamped -- correctly. Widen the same five numbers
 * to double and the margin reappears: `(1 - P(win)) - P(lose gammon)` comes out
 * at -1.5e-10. A NEGATIVE PROBABILITY, arriving in a match equity table, with
 * nothing to show for it. Observed on a real position of the T10 corpus, not
 * imagined.
 *
 * So this function subtracts in double and floors each outcome at zero. The
 * six sum to 1 to within float32 rounding; they are never negative.
 */
void gn_probs_exclusive(const float probs[GN_NUM_OUTPUTS],
                        double out[GN_NUM_EXCLUSIVE]);

#ifdef __cplusplus
}
#endif

#endif /* GN_INFER_H */

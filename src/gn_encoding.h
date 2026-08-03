/*
 * gn_encoding.h -- position <-> 196-feature network input.
 *
 * THE MOST DANGEROUS FILE IN THIS REPOSITORY.
 *
 * An error here does not crash. It produces five perfectly plausible
 * probabilities that are wrong, and it contaminates every measurement taken
 * afterwards without ever looking broken. `PLAN.md` calls T02 the bottleneck of
 * the project for this reason: nothing measurable exists before it, and a
 * mistake in it invalidates everything after it.
 *
 * The layout is `encoding.py`'s `perspective196`, reproduced exactly — the
 * network was trained on it, so "exactly" means bit for bit, not "equivalent".
 *
 *   MY block (98)   24 points x 4 thermometer units       = 96
 *                   my bar   * 0.5                        =  1
 *                   my off   / 15.0                       =  1
 *   OPP block (98)  the same, for the opponent            = 98
 *                                                   total = 196
 *
 * Always from the ON-ROLL player's point of view. When BLACK is on roll the
 * point indices are MIRRORED (index i becomes 23 - i), so that "my home board"
 * always occupies the same features. The network learns a single function,
 * P(the on-roll player wins | board).
 *
 * The four cube inputs of the cubeful variants are deliberately absent: the
 * model this project retains is cubeless.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_ENCODING_H
#define GN_ENCODING_H

#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GN_NUM_FEATURES 196

#define GN_FEATURES_PER_POINT 4
#define GN_MY_BLOCK_OFFSET    0
#define GN_MY_BAR_INDEX       96
#define GN_MY_OFF_INDEX       97
#define GN_OPP_BLOCK_OFFSET   98
#define GN_OPP_BAR_INDEX      194
#define GN_OPP_OFF_INDEX      195

/*
 * Write the 196 features of `pos`, seen by `pos->turn`.
 *
 * `out` must have room for GN_NUM_FEATURES floats. Returns 0 on success, -1 if
 * the position is not structurally valid — refused, never approximated. A
 * network handed an input it has never seen returns five plausible numbers and
 * says nothing about it.
 */
int gn_encode(const GnPosition *pos, float *out);

/*
 * Recover a position from its 196 features, given whose turn it is.
 *
 * The turn must be supplied because the encoding is deliberately blind to
 * absolute colour: that is the whole point of a perspective encoding, and it is
 * why the network needs only one function instead of two. What the features do
 * determine is every checker's placement relative to the on-roll player.
 *
 * Returns 0 on success, -1 if the features do not describe a valid position
 * (a malformed thermometer, a non-integral bar or off count, a checker total
 * that is not 15).
 */
int gn_decode(const float *features, int turn, GnPosition *out);

/*
 * Pip count read straight out of a feature vector, for the on-roll player
 * (player 0) or the opponent (player 1).
 *
 * The sentinel `BRIEF.md` §6 keeps: computed from the vector rather than from
 * the position, it catches an encoding mistake that a position-side check would
 * agree with. Returns -1 if the vector is malformed.
 */
int gn_pip_count_from_features(const float *features, int side);

#define GN_SIDE_ON_ROLL  0
#define GN_SIDE_OPPONENT 1

#ifdef __cplusplus
}
#endif

#endif /* GN_ENCODING_H */

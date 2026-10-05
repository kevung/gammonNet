/*
 * gn_policy.h -- a stateless playing policy: one decision in, one action out.
 *
 * `docs/specs/politique-spec.md` is the specification; this header is its
 * contract. Everything a whole match needs from the engine, answered one
 * decision at a time, with nothing kept between calls: the game, the dice,
 * the score and the clock stay with whoever calls. Two identical calls return
 * the same action, bit for bit, in any order.
 *
 * Nothing here computes anything new. Every number comes from a function this
 * library already exports and has already measured -- `gn_best_play`,
 * `gn_search_probs`, `gn_cube_decide`, `gn_cube_value`, `gn_met_after`. What
 * is written here is the COMPOSITION -- the referential, the owner of the
 * cube, the score seen from the side on roll, the efficiency per cube state,
 * the dead-cube guards -- because every caller that recomposed it was one
 * more chance to get it silently wrong. Two pieces are new: the taker's
 * answer to a double (spec §5.3), and the exact reading of a certain loss
 * (spec §5.5).
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_POLICY_H
#define GN_POLICY_H

#include "gn_cube.h"
#include "gn_infer.h"
#include "gn_met.h"
#include "gn_rules.h"
#include "gn_search.h"

#ifdef __cplusplus
extern "C" {
#endif

/* What is waiting to be decided. The DECIDER follows from it (spec §3):
 * the player on roll for MOVE and CUBE, the opponent for TAKE and RESIGN. */
typedef enum {
    GN_PENDING_MOVE = 0,    /* dice rolled: the player on roll moves */
    GN_PENDING_CUBE = 1,    /* before rolling: resign, double or roll */
    GN_PENDING_TAKE = 2,    /* the player on roll doubled: take or pass */
    GN_PENDING_RESIGN = 3   /* the player on roll offers to resign: accept or reject */
} GnPending;

typedef enum {
    GN_ACTION_MOVE = 0,
    GN_ACTION_ROLL = 1,
    GN_ACTION_DOUBLE = 2,
    GN_ACTION_RESIGN = 3,
    GN_ACTION_TAKE = 4,
    GN_ACTION_PASS = 5,
    GN_ACTION_ACCEPT = 6,
    GN_ACTION_REJECT = 7
} GnActionKind;

/*
 * The decision. ONE referential: the player on roll's. `position.turn` names
 * that player; the score and the cube owner are seen from them, exactly as in
 * `GnSearchConfig`. The caller never turns anything around.
 */
typedef struct {
    GnPosition position;
    GnPending pending;
    int d1, d2;             /* GN_PENDING_MOVE only, 1..6 */
    int cube;               /* 1, 2, 4, ... money and match alike */
    int cube_owner;         /* GnCubeOwner, seen from the player on roll */
    int jacoby;             /* money only; without effect at a match score */
    int use_match;          /* 0 money, 1 match */
    int away_on_roll;
    int away_opponent;
    int crawford;           /* this game IS the Crawford game */
    int resign_value;       /* GN_PENDING_RESIGN only: 1, 2 or 3 points per cube */
} GnDecision;

typedef struct {
    GnActionKind kind;
    /* GN_ACTION_MOVE: the play. `num_moves == 0` when there is no legal play,
     * and `result` is then the position with the turn passed. Zero elsewhere. */
    GnPlay play;
    /* GN_ACTION_RESIGN: 1, 2 or 3 -- the certain value. 0 elsewhere. */
    int resign_value;
    /* 1 when a search or an evaluation ran, 0 for every shortcut. */
    int searched;
    /* The two numbers the decision compared, from the DECIDER's side, on the
     * scale spec §5 names per case; 0 when nothing was computed. */
    double equity_a;
    double equity_b;
} GnAction;

/*
 * The cube efficiency the policy uses, indexed by GnCubeOwner as seen by the
 * player whose cube state is valued: T34's measurement
 * (`docs/mesures/t34-efficacite.json`), the doubles T35's match loop read from
 * that file. Exposed so a test can hold them to the measurement.
 */
double gn_policy_efficiency(int owner);

/* The horizon, in rolls, of the exact certain-loss reading (spec §5.5). */
#define GN_POLICY_RESIGN_HORIZON 2

/*
 * Decide. `level` is a canonical level name (`gn_search_level`): "instant",
 * "normal" or "thorough", and nothing else. `prune_net` is required when the
 * level prunes and ignored otherwise.
 *
 * Returns 0 with `out` written, or -1 for a refused input -- invalid or
 * finished position, dice out of range, unknown level, a pruning level with
 * no pruning network, a match state outside the table, an incoherent cube, a
 * resignation value outside 1..3, a double the rules forbid. Refused, never
 * approximated; `out` is zeroed on refusal.
 */
int gn_policy_decide(const GnNetwork *net, const GnNetwork *prune_net,
                     const char *level, const GnDecision *decision,
                     GnAction *out);

/*
 * The same, for an explicit search shape rather than a named level -- what
 * `gn_policy_decide` calls once it has looked the name up. Exists so a
 * measurement can run the policy at a shape that is not canonical (T35's own,
 * to show the composition changes nothing it measured); the named form is
 * the surface.
 */
int gn_policy_decide_level(const GnNetwork *net, const GnNetwork *prune_net,
                           const GnSearchLevel *level,
                           const GnDecision *decision, GnAction *out);

/*
 * The exact certain-loss reading on its own (spec §5.5), from `pos->turn`'s
 * side, `pos->turn` about to roll. Returns the certain value of the loss --
 * 1, 2 or 3 -- or 0 when the loss is not certain, or its value is not, within
 * the horizon. Never consults the network. Jacoby is the caller's to apply.
 */
int gn_policy_certain_loss(const GnPosition *pos);

#ifdef __cplusplus
}
#endif

#endif /* GN_POLICY_H */

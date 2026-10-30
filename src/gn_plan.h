/*
 * gn_plan.h -- one decision, cut into tasks that share nothing (issue #36).
 *
 * `docs/specs/decision-decomposee-spec.md` is the specification; this header
 * is its contract. A PLAN is a decision in progress: what was asked, and what
 * the search has settled so far. It advances by WAVES; each wave is a list of
 * TASKS, each task one roll of one chance node (`gn_search.h`), runnable on
 * any instance holding the same networks -- in any order, on any thread or
 * process, with no memory shared with the planner.
 *
 * THE GUARANTEE. Recombined, the tasks give the decision the search gives in
 * one piece, BIT FOR BIT: the same candidates in the same order with the same
 * equities, the same distribution, the same cube verdict, the same action.
 * Not by imitation: the plan drives the search's own root (`gn_search_root_*`),
 * a task runs the search's own roll functions, and the recombination is the
 * chance node's own sum in roll order. Only the evaluation COUNT differs (a
 * task fills its batches alone, and a cache is per instance); it is reported,
 * never promised.
 *
 * Plans and tasks travel as BYTES -- an explicit little-endian encoding,
 * versioned, so a plan can cross a `postMessage` or a process boundary and be
 * resumed by an instance that never saw it begin. Each task carries the
 * FINGERPRINTS of the networks and of the exact table the plan was made with;
 * an instance holding others refuses it rather than computing a plausible
 * answer to a different question.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_PLAN_H
#define GN_PLAN_H

#include <stddef.h>
#include <stdint.h>

#include "gn_policy.h"
#include "gn_search.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GN_PLAN_VERSION 1

typedef enum {
    /* `gn_search_plays` -> the ranked candidates (bestPlay keeps the first). */
    GN_PLAN_MOVE = 1,
    /* `gn_search_probs`, then `gn_cube_decide` on that distribution. */
    GN_PLAN_CUBE = 2,
    /* `gn_policy_decide_split`: the policy, its one search decomposed. */
    GN_PLAN_POLICY = 3,
    /* `gn_search_equity` AND `gn_search_probs` of a position before the roll. */
    GN_PLAN_POSITION = 4
} GnPlanKind;

/* What an instance holds that a task's answer depends on. Zero means "none
 * loaded" for the prune network and the table; the model's must be set. The
 * evaluation cache is not here: it changes no result. */
typedef struct {
    uint64_t model;
    uint64_t prune;
    uint64_t bearoff;
} GnPlanFingerprint;

/* FNV-1a, 64 bits -- the fingerprint of a byte buffer. */
uint64_t gn_plan_fingerprint_bytes(const unsigned char *bytes, size_t length);

/* The cube decision's own parameters (GN_PLAN_CUBE). */
typedef struct {
    int owner;              /* GnCubeOwner, seen from the player on roll */
    int use_match;
    GnMatchState state;     /* used when `use_match` */
    double efficiency;
    int jacoby;
} GnPlanCube;

typedef struct {
    int kind;                    /* GnPlanKind */
    GnPlanFingerprint fp;

    /* The search the plan decomposes. `config.prune_net` is never stored:
     * `config.prune_k > 0` says pruning is on, and the instance running a
     * task supplies its own network -- whose fingerprint must match. */
    int search;                  /* 0 settled, else the GN_PLAN_* that drives it */
    GnSearchConfig config;
    GnPosition position;
    int d1, d2;

    GnPlanCube cube;             /* GN_PLAN_CUBE */
    GnDecision decision;         /* GN_PLAN_POLICY */
    char level[16];              /* GN_PLAN_POLICY */
    int policy_need;             /* GnPolicyNeedKind recorded at begin */
    GnAction action;             /* GN_PLAN_POLICY, once done */

    /* What is settled. */
    GnCandidate *candidates;     /* GN_PLAN_MOVE search: heap, `capacity` */
    int capacity;
    int written;
    GnRootWaves waves;
    float probs[GN_NUM_OUTPUTS];
    double equity;
    int done;
    unsigned long evaluations;   /* planner's and every task's, summed */
    uint64_t wave_key;           /* ties the current wave's results to it */
} GnPlan;

/* One task's answer, as `gn_plan_advance` takes it back. */
typedef struct {
    int index;                   /* the task's index in its wave */
    uint64_t wave_key;           /* copied from the task */
    double value;                /* GN_TASK_ROLL_EQUITY */
    float probs[GN_NUM_OUTPUTS]; /* GN_TASK_ROLL_PROBS */
    unsigned long evaluations;   /* what the task cost (not guaranteed) */
} GnPlanResult;

/*
 * Begin a plan. Runs what is cheap and must be ranked first (the root's
 * shallow pass, a policy shortcut, a 0-ply evaluation), then emits the first
 * wave. `prune_net` is the planner's own pruning network (required when
 * `config.prune_k > 0` or the level prunes). For GN_PLAN_POLICY `config` is
 * ignored (the level builds its own), `position` / dice come from `decision`.
 * Returns 0, or -1 for a refusal -- the same refusals as the search in one
 * piece. `gn_plan_free` releases it either way.
 */
int gn_plan_begin_move(GnPlan *plan, const GnNetwork *net,
                       const GnNetwork *prune_net, const GnPlanFingerprint *fp,
                       const GnPosition *pos, int d1, int d2,
                       const GnSearchConfig *config);
int gn_plan_begin_cube(GnPlan *plan, const GnNetwork *net,
                       const GnNetwork *prune_net, const GnPlanFingerprint *fp,
                       const GnPosition *pos, const GnSearchConfig *config,
                       const GnPlanCube *cube);
int gn_plan_begin_position(GnPlan *plan, const GnNetwork *net,
                           const GnNetwork *prune_net,
                           const GnPlanFingerprint *fp, const GnPosition *pos,
                           const GnSearchConfig *config);
int gn_plan_begin_policy(GnPlan *plan, const GnNetwork *net,
                         const GnNetwork *prune_net,
                         const GnPlanFingerprint *fp, const char *level,
                         const GnDecision *decision);

void gn_plan_free(GnPlan *plan);

/* Tasks in the current wave (0 once `done`). */
int gn_plan_task_count(const GnPlan *plan);

/* Task `index` of the current wave. Returns 0, or -1. */
int gn_plan_task(const GnPlan *plan, int index, GnSearchTask *task);

/*
 * Settle the current wave from its results -- exactly one per task, in ANY
 * order, each carrying the wave's key -- then emit the next wave, or finish.
 * `net` / `prune_net` are the planner's (a policy replays its decision with
 * them). Returns 0, or -1 (plan untouched as a decision: refuse it) for a
 * missing, duplicated or foreign result or a failed task.
 */
int gn_plan_advance(GnPlan *plan, const GnNetwork *net,
                    const GnNetwork *prune_net, const GnPlanResult *results,
                    int count);

/* Run a task under the decision's `config` with this instance's networks
 * (`prune_net` replaces whatever `config.prune_net` says; required when
 * `config.prune_k > 0`). Fills `value`, `probs` and `evaluations` of `out`.
 * Returns 0, -1 for a failed or refused task, -2 when this instance cannot
 * prune and the plan does. */
int gn_plan_run_task(const GnNetwork *net, const GnNetwork *prune_net,
                     const GnSearchConfig *config, const GnSearchTask *task,
                     GnPlanResult *out);

/* The same from a task's bytes, after checking that its fingerprints are
 * `mine` -- all of `out` filled, index and wave key included. Returns 0, -1
 * for a malformed or failed task, -2 for networks or a table other than the
 * plan's. */
int gn_plan_run_encoded(const GnNetwork *net, const GnNetwork *prune_net,
                        const GnPlanFingerprint *mine,
                        const unsigned char *bytes, size_t length,
                        GnPlanResult *out);

/* ── The settled decision (only once `done`) ─────────────────────────── */

/* GN_PLAN_MOVE: the ranked candidates, as `gn_search_plays` writes them. */
int gn_plan_candidates(const GnPlan *plan, const GnCandidate **out);

/* GN_PLAN_CUBE: `gn_cube_decide` on the settled distribution. */
int gn_plan_cube_decision(const GnPlan *plan, GnCubeDecision *out,
                          float probs[GN_NUM_OUTPUTS]);

/* GN_PLAN_POLICY: the action, replayed at the last `gn_plan_advance` (or at
 * begin, for a shortcut). */
int gn_plan_policy_action(const GnPlan *plan, GnAction *out);

/* GN_PLAN_POSITION: the scalar recursion and the distribution. */
int gn_plan_position(const GnPlan *plan, double *equity,
                     float probs[GN_NUM_OUTPUTS]);

/* ── Bytes ───────────────────────────────────────────────────────────── */

/* Encode into `buffer` (NULL to ask the size). Returns the size, or -1. */
long gn_plan_encode(const GnPlan *plan, unsigned char *buffer, size_t capacity);
/* Decode; `plan` must be freed. Returns 0, or -1 for a malformed buffer. */
int gn_plan_decode(const unsigned char *buffer, size_t length, GnPlan *plan);

/* A task, self-contained: version, fingerprints, wave key, index, the
 * decision's config and the task itself. Fixed size. */
#define GN_PLAN_TASK_BYTES 256
int gn_plan_encode_task(const GnPlan *plan, int index,
                        unsigned char out[GN_PLAN_TASK_BYTES]);
/* Decode a task; `config.prune_net` is left NULL for the runner to supply. */
int gn_plan_decode_task(const unsigned char *buffer, size_t length,
                        GnPlanFingerprint *fp, uint64_t *wave_key, int *index,
                        GnSearchConfig *config, GnSearchTask *task);

/* ── The same, plan in bytes in and out: no state between calls ───────
 *
 * What the WebAssembly face and the Python binding call. A plan returned in
 * `*out` is malloc'd: release it with `gn_plan_bytes_free`. Every function
 * decodes the plan it is given and encodes the one it returns; nothing is
 * kept on the instance.
 */
long gn_plan_bytes_move(const GnNetwork *net, const GnNetwork *prune_net,
                        const GnPlanFingerprint *fp, const GnPosition *pos,
                        int d1, int d2, const GnSearchConfig *config,
                        unsigned char **out);
long gn_plan_bytes_cube(const GnNetwork *net, const GnNetwork *prune_net,
                        const GnPlanFingerprint *fp, const GnPosition *pos,
                        const GnSearchConfig *config, const GnPlanCube *cube,
                        unsigned char **out);
long gn_plan_bytes_position(const GnNetwork *net, const GnNetwork *prune_net,
                            const GnPlanFingerprint *fp, const GnPosition *pos,
                            const GnSearchConfig *config, unsigned char **out);
long gn_plan_bytes_policy(const GnNetwork *net, const GnNetwork *prune_net,
                          const GnPlanFingerprint *fp, const char *level,
                          const GnDecision *decision, unsigned char **out);
long gn_plan_bytes_advance(const GnNetwork *net, const GnNetwork *prune_net,
                           const unsigned char *plan, size_t length,
                           const GnPlanResult *results, int count,
                           unsigned char **out);
void gn_plan_bytes_free(unsigned char *plan);

/* Summary of a plan: writes [kind, done, task count, evaluations (low 31
 * bits), wave, policy need]. Returns 0, or -1. */
int gn_plan_bytes_info(const unsigned char *plan, size_t length, int info[6]);

/* All the tasks of the current wave, GN_PLAN_TASK_BYTES each, into `out`
 * (room for `max`). Returns how many, or -1. */
int gn_plan_bytes_tasks(const unsigned char *plan, size_t length,
                        unsigned char *out, int max);

/* The settled decision, read back from bytes (plan done). */
int gn_plan_bytes_candidates(const unsigned char *plan, size_t length,
                             GnCandidate *out, int max);
int gn_plan_bytes_cube_decision(const unsigned char *plan, size_t length,
                                GnCubeDecision *out,
                                float probs[GN_NUM_OUTPUTS]);
int gn_plan_bytes_action(const unsigned char *plan, size_t length,
                         GnAction *out);
int gn_plan_bytes_position_value(const unsigned char *plan, size_t length,
                                 double *equity, float probs[GN_NUM_OUTPUTS]);
/* The total evaluation count (not guaranteed equal to the search in one
 * piece's: see the header). */
long gn_plan_bytes_evaluations(const unsigned char *plan, size_t length);

#ifdef __cplusplus
}
#endif

#endif /* GN_PLAN_H */

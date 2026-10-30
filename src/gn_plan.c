/*
 * gn_plan.c -- one decision, cut into tasks that share nothing. See gn_plan.h
 * for the contract and docs/specs/decision-decomposee-spec.md for the why.
 *
 * Nothing here searches. The root's waves are `gn_search_root_*`, a task is
 * `gn_search_task_run`, the recombinations are `gn_search_chance_*`, the cube
 * verdict is `gn_cube_decide`, the policy is `gn_policy_decide_split`. What
 * this file owns is the BOOKKEEPING -- which task is which slot of which
 * candidate -- and the bytes a plan and a task travel as.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_plan.h"

#include "gn_cube.h"

#include <stdlib.h>
#include <string.h>

enum { SEARCH_NONE = 0, SEARCH_MOVE = 1, SEARCH_PROBS = 2, SEARCH_POSITION = 3 };

uint64_t gn_plan_fingerprint_bytes(const unsigned char *bytes, size_t length)
{
    uint64_t h = 1469598103934665603ULL;
    for (size_t i = 0; i < length; i++) {
        h ^= bytes[i];
        h *= 1099511628211ULL;
    }
    return h;
}

/* ── Bookkeeping ─────────────────────────────────────────────────────── */

/* The candidates of the active wave that need tasks, in ranking order. */
static int move_live(const GnPlan *plan, int *live)
{
    int n = 0;
    GnSearchTask probe;
    for (int i = 0; i < plan->waves.count; i++) {
        const int rc = gn_search_root_task(&plan->config, plan->candidates,
                                           &plan->waves, i, 0, &probe);
        if (rc < 0) {
            return -1;
        }
        if (rc == 0) {
            if (live != NULL) live[n] = i;
            n++;
        }
    }
    return n;
}

/* Tasks per live candidate of the active wave: one per roll, or the whole
 * node when the wave is too shallow to be worth cutting. */
static int move_split(const GnPlan *plan)
{
    return (plan->waves.depth >= gn_search_root_split_depth()) ? GN_NUM_ROLLS : 1;
}

int gn_plan_task_count(const GnPlan *plan)
{
    if (plan == NULL || plan->done) {
        return 0;
    }
    switch (plan->search) {
    case SEARCH_MOVE: {
        const int n = plan->waves.active ? move_live(plan, NULL) : 0;
        return (n < 0) ? 0 : n * move_split(plan);
    }
    case SEARCH_PROBS:
        return GN_NUM_ROLLS;
    case SEARCH_POSITION:
        return 2 * GN_NUM_ROLLS;
    }
    return 0;
}

int gn_plan_task(const GnPlan *plan, int index, GnSearchTask *task)
{
    if (plan == NULL || task == NULL || index < 0
        || index >= gn_plan_task_count(plan)) {
        return -1;
    }
    const int r = index % GN_NUM_ROLLS;
    if (plan->search == SEARCH_MOVE) {
        int *live = malloc(sizeof(int) * (size_t)plan->waves.count);
        if (live == NULL || move_live(plan, live) < 0) {
            free(live);
            return -1;
        }
        const int split = move_split(plan);
        const int i = live[index / split];
        free(live);
        return (gn_search_root_task(&plan->config, plan->candidates,
                                    &plan->waves, i, index % split, task) == 0)
                   ? 0 : -1;
    }
    /* The pre-roll searches' own root: `gn_search_probs` and
     * `gn_search_equity` start at (ply, match, cube_owner) of the config. */
    memset(task, 0, sizeof(*task));
    task->kind = (index < GN_NUM_ROLLS) ? GN_TASK_ROLL_PROBS : GN_TASK_ROLL_EQUITY;
    task->pos = plan->position;
    task->depth = plan->config.ply;
    task->state = plan->config.match;
    task->owner = plan->config.cube_owner;
    task->roll = r;
    return 0;
}

static void refresh_key(GnPlan *plan);

/* A policy's search is settled: replay the decision with its answer. */
static int finish_policy(GnPlan *plan, const GnNetwork *net,
                         const GnNetwork *prune_net)
{
    GnPolicyAnswer answer;
    memset(&answer, 0, sizeof(answer));
    answer.request.kind = (GnPolicyNeedKind)plan->policy_need;
    answer.request.position = plan->position;
    answer.request.d1 = plan->d1;
    answer.request.d2 = plan->d2;
    answer.request.config = plan->config;
    if (plan->policy_need == GN_POLICY_NEED_BEST_PLAY) {
        answer.found = plan->written > 0;
        if (answer.found) {
            answer.best = plan->candidates[0];
        }
    } else {
        memcpy(answer.probs, plan->probs, sizeof(answer.probs));
    }
    GnPolicyNeed need;
    return gn_policy_decide_split(net, prune_net, plan->level, &plan->decision,
                                  &answer, &need, &plan->action) == 0 ? 0 : -1;
}

/* After a wave is settled (or at begin): skip waves that need no task, and
 * mark the plan done when the search is. */
static int settle(GnPlan *plan, const GnNetwork *net, const GnNetwork *prune_net)
{
    if (plan->search == SEARCH_MOVE) {
        while (plan->waves.active && gn_plan_task_count(plan) == 0) {
            gn_search_root_next(&plan->config, plan->candidates, &plan->waves);
        }
        if (plan->waves.active) {
            refresh_key(plan);
            return 0;
        }
    } else if (plan->search != SEARCH_NONE && !plan->done) {
        refresh_key(plan);
        return 0;   /* the pre-roll searches settle in one wave */
    }
    plan->search = SEARCH_NONE;
    if (plan->kind == GN_PLAN_POLICY && plan->policy_need != GN_POLICY_NEED_NONE) {
        if (finish_policy(plan, net, prune_net) != 0) {
            return -1;
        }
    }
    plan->done = 1;
    plan->wave_key = 0;
    return 0;
}

static void plan_reset(GnPlan *plan, int kind, const GnPlanFingerprint *fp)
{
    memset(plan, 0, sizeof(*plan));
    plan->kind = kind;
    if (fp != NULL) {
        plan->fp = *fp;
    }
}

/* The search the plan decomposes, begun: what is cheap runs here. */
static int begin_search(GnPlan *plan, int search, const GnNetwork *net,
                        const GnNetwork *prune_net)
{
    plan->config.prune_net = (plan->config.prune_k > 0) ? prune_net : NULL;
    if (plan->config.prune_k > 0 && prune_net == NULL) {
        return -1;   /* another search than the one asked for */
    }
    gn_search_reset_evaluations();

    if (search == SEARCH_MOVE) {
        plan->candidates = malloc(sizeof(GnCandidate) * (size_t)GN_MAX_PLAYS);
        if (plan->candidates == NULL) {
            return -1;
        }
        plan->capacity = GN_MAX_PLAYS;
        plan->written = gn_search_root_begin(net, &plan->position, plan->d1,
                                             plan->d2, &plan->config,
                                             plan->candidates, GN_MAX_PLAYS,
                                             &plan->waves);
        plan->evaluations = gn_search_evaluations();
        if (plan->written < 0) {
            return -1;
        }
        plan->search = SEARCH_MOVE;
        return settle(plan, net, prune_net);
    }

    /* The pre-roll searches: at 0-ply, or on a finished game, there is no roll
     * to enumerate and the search answers at once -- through itself. */
    if (plan->config.ply < 1 || gn_position_is_over(&plan->position)) {
        if (gn_search_probs(net, &plan->position, &plan->config, plan->probs) != 0) {
            return -1;
        }
        if (search == SEARCH_POSITION) {
            plan->equity = gn_search_equity(net, &plan->position, &plan->config);
        }
        plan->evaluations = gn_search_evaluations();
        plan->search = SEARCH_NONE;
        return settle(plan, net, prune_net);
    }
    plan->search = search;
    return settle(plan, net, prune_net);
}

int gn_plan_begin_move(GnPlan *plan, const GnNetwork *net,
                       const GnNetwork *prune_net, const GnPlanFingerprint *fp,
                       const GnPosition *pos, int d1, int d2,
                       const GnSearchConfig *config)
{
    if (plan == NULL) return -1;
    plan_reset(plan, GN_PLAN_MOVE, fp);
    if (net == NULL || pos == NULL || config == NULL) return -1;
    plan->config = *config;
    plan->position = *pos;
    plan->d1 = d1;
    plan->d2 = d2;
    return begin_search(plan, SEARCH_MOVE, net, prune_net);
}

int gn_plan_begin_cube(GnPlan *plan, const GnNetwork *net,
                       const GnNetwork *prune_net, const GnPlanFingerprint *fp,
                       const GnPosition *pos, const GnSearchConfig *config,
                       const GnPlanCube *cube)
{
    if (plan == NULL) return -1;
    plan_reset(plan, GN_PLAN_CUBE, fp);
    if (net == NULL || pos == NULL || config == NULL || cube == NULL) return -1;
    plan->config = *config;
    plan->position = *pos;
    plan->cube = *cube;
    return begin_search(plan, SEARCH_PROBS, net, prune_net);
}

int gn_plan_begin_position(GnPlan *plan, const GnNetwork *net,
                           const GnNetwork *prune_net,
                           const GnPlanFingerprint *fp, const GnPosition *pos,
                           const GnSearchConfig *config)
{
    if (plan == NULL) return -1;
    plan_reset(plan, GN_PLAN_POSITION, fp);
    if (net == NULL || pos == NULL || config == NULL) return -1;
    plan->config = *config;
    plan->position = *pos;
    return begin_search(plan, SEARCH_POSITION, net, prune_net);
}

int gn_plan_begin_policy(GnPlan *plan, const GnNetwork *net,
                         const GnNetwork *prune_net,
                         const GnPlanFingerprint *fp, const char *level,
                         const GnDecision *decision)
{
    if (plan == NULL) return -1;
    plan_reset(plan, GN_PLAN_POLICY, fp);
    if (net == NULL || level == NULL || decision == NULL
        || strlen(level) >= sizeof(plan->level)) {
        return -1;
    }
    strcpy(plan->level, level);
    plan->decision = *decision;

    GnPolicyNeed need;
    const int rc = gn_policy_decide_split(net, prune_net, level, decision, NULL,
                                          &need, &plan->action);
    if (rc < 0) {
        return -1;
    }
    if (rc == 0) {
        plan->done = 1;   /* a shortcut: no search at all */
        return 0;
    }
    plan->policy_need = need.kind;
    plan->config = need.config;
    plan->position = need.position;
    plan->d1 = need.d1;
    plan->d2 = need.d2;
    return begin_search(plan, need.kind == GN_POLICY_NEED_BEST_PLAY
                                  ? SEARCH_MOVE : SEARCH_PROBS,
                        net, prune_net);
}

void gn_plan_free(GnPlan *plan)
{
    if (plan == NULL) return;
    free(plan->candidates);
    plan->candidates = NULL;
    plan->capacity = 0;
}

int gn_plan_advance(GnPlan *plan, const GnNetwork *net,
                    const GnNetwork *prune_net, const GnPlanResult *results,
                    int count)
{
    if (plan == NULL || plan->done || (count > 0 && results == NULL)) {
        return -1;
    }
    const int expected = gn_plan_task_count(plan);
    if (count != expected || expected == 0) {
        return -1;
    }
    /* Exactly one result per task, from THIS wave -- by index, so the order
     * they come back in cannot matter. */
    const GnPlanResult **by_index = calloc((size_t)count, sizeof(*by_index));
    if (by_index == NULL) return -1;
    for (int k = 0; k < count; k++) {
        const GnPlanResult *res = &results[k];
        if (res->index < 0 || res->index >= count || by_index[res->index] != NULL
            || res->wave_key != plan->wave_key) {
            free(by_index);
            return -1;
        }
        by_index[res->index] = res;
    }
    for (int k = 0; k < count; k++) {
        plan->evaluations += by_index[k]->evaluations;
    }

    if (plan->search == SEARCH_MOVE) {
        int *live = malloc(sizeof(int) * (size_t)plan->waves.count);
        if (live == NULL || move_live(plan, live) < 0) {
            free(live);
            free(by_index);
            return -1;
        }
        const int split = move_split(plan);
        double best[GN_NUM_ROLLS];
        for (int k = 0; k < count / split; k++) {
            if (split == 1) {
                /* The whole node came back: `deepen_one`'s negation. */
                plan->candidates[live[k]].equity = -by_index[k]->value;
                continue;
            }
            for (int r = 0; r < GN_NUM_ROLLS; r++) {
                best[r] = by_index[k * GN_NUM_ROLLS + r]->value;
            }
            gn_search_root_settle(plan->candidates, live[k], best);
        }
        free(live);
        gn_search_root_next(&plan->config, plan->candidates, &plan->waves);
    } else {
        float mine[GN_NUM_ROLLS][GN_NUM_OUTPUTS];
        for (int r = 0; r < GN_NUM_ROLLS; r++) {
            memcpy(mine[r], by_index[r]->probs, sizeof(mine[r]));
        }
        gn_search_chance_probs(mine, plan->probs);
        if (plan->search == SEARCH_POSITION) {
            double best[GN_NUM_ROLLS];
            for (int r = 0; r < GN_NUM_ROLLS; r++) {
                best[r] = by_index[GN_NUM_ROLLS + r]->value;
            }
            plan->equity = gn_search_chance_equity(best);
        }
        plan->search = SEARCH_NONE;
    }
    free(by_index);
    plan->config.prune_net = (plan->config.prune_k > 0) ? prune_net : NULL;
    return settle(plan, net, prune_net);
}

int gn_plan_run_task(const GnNetwork *net, const GnNetwork *prune_net,
                     const GnSearchConfig *config, const GnSearchTask *task,
                     GnPlanResult *out)
{
    if (net == NULL || config == NULL || task == NULL || out == NULL) {
        return -1;
    }
    GnSearchConfig mine = *config;
    if (mine.prune_k > 0) {
        if (prune_net == NULL) {
            return -2;   /* the plan prunes, this instance cannot */
        }
        mine.prune_net = prune_net;
    } else {
        mine.prune_net = NULL;
    }
    gn_search_reset_evaluations();
    const int rc = gn_search_task_run(net, &mine, task, &out->value, out->probs);
    out->evaluations = gn_search_evaluations();
    return rc;
}

/* ── The settled decision ────────────────────────────────────────────── */

int gn_plan_candidates(const GnPlan *plan, const GnCandidate **out)
{
    if (plan == NULL || !plan->done || out == NULL) return -1;
    *out = plan->candidates;
    return plan->written;
}

int gn_plan_cube_decision(const GnPlan *plan, GnCubeDecision *out,
                          float probs[GN_NUM_OUTPUTS])
{
    if (plan == NULL || !plan->done || plan->kind != GN_PLAN_CUBE || out == NULL) {
        return -1;
    }
    if (probs != NULL) {
        memcpy(probs, plan->probs, sizeof(float) * GN_NUM_OUTPUTS);
    }
    return gn_cube_decide(plan->probs, (GnCubeOwner)plan->cube.owner,
                          plan->cube.use_match ? &plan->cube.state : NULL,
                          plan->cube.efficiency, plan->cube.jacoby, out);
}

int gn_plan_policy_action(const GnPlan *plan, GnAction *out)
{
    if (plan == NULL || !plan->done || plan->kind != GN_PLAN_POLICY || out == NULL) {
        return -1;
    }
    *out = plan->action;
    return 0;
}

int gn_plan_position(const GnPlan *plan, double *equity,
                     float probs[GN_NUM_OUTPUTS])
{
    if (plan == NULL || !plan->done || plan->kind != GN_PLAN_POSITION) return -1;
    if (equity != NULL) *equity = plan->equity;
    if (probs != NULL) memcpy(probs, plan->probs, sizeof(float) * GN_NUM_OUTPUTS);
    return 0;
}

/* ── Bytes: explicit little-endian, whatever the host ────────────────── */

typedef struct {
    unsigned char *p;   /* NULL: count only */
    size_t cap, len;
    int bad;
} Writer;

static void put(Writer *w, const void *src, size_t n)
{
    if (w->p != NULL) {
        if (w->len + n > w->cap) {
            w->bad = 1;
        } else {
            memcpy(w->p + w->len, src, n);
        }
    }
    w->len += n;
}

static void put_u32(Writer *w, uint32_t v)
{
    unsigned char b[4] = {(unsigned char)v, (unsigned char)(v >> 8),
                          (unsigned char)(v >> 16), (unsigned char)(v >> 24)};
    put(w, b, 4);
}

static void put_i32(Writer *w, int v) { put_u32(w, (uint32_t)v); }

static void put_u64(Writer *w, uint64_t v)
{
    put_u32(w, (uint32_t)v);
    put_u32(w, (uint32_t)(v >> 32));
}

static void put_f64(Writer *w, double v)
{
    uint64_t bits;
    memcpy(&bits, &v, sizeof(bits));
    put_u64(w, bits);
}

static void put_f32(Writer *w, float v)
{
    uint32_t bits;
    memcpy(&bits, &v, sizeof(bits));
    put_u32(w, bits);
}

typedef struct {
    const unsigned char *p;
    size_t len, at;
    int bad;
} Reader;

static void get(Reader *r, void *dst, size_t n)
{
    if (r->at + n > r->len) {
        r->bad = 1;
        memset(dst, 0, n);
        return;
    }
    memcpy(dst, r->p + r->at, n);
    r->at += n;
}

static uint32_t get_u32(Reader *r)
{
    unsigned char b[4];
    get(r, b, 4);
    return (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16)
        | ((uint32_t)b[3] << 24);
}

static int get_i32(Reader *r) { return (int)get_u32(r); }

static uint64_t get_u64(Reader *r)
{
    const uint64_t lo = get_u32(r);
    return lo | ((uint64_t)get_u32(r) << 32);
}

static double get_f64(Reader *r)
{
    const uint64_t bits = get_u64(r);
    double v;
    memcpy(&v, &bits, sizeof(v));
    return v;
}

static float get_f32(Reader *r)
{
    const uint32_t bits = get_u32(r);
    float v;
    memcpy(&v, &bits, sizeof(v));
    return v;
}

static void put_position(Writer *w, const GnPosition *p)
{
    put(w, p->points, GN_NUM_POINTS);
    put(w, p->bar, 2);
    put(w, p->off, 2);
    put(w, &p->turn, 1);
}

static void get_position(Reader *r, GnPosition *p)
{
    get(r, p->points, GN_NUM_POINTS);
    get(r, p->bar, 2);
    get(r, p->off, 2);
    get(r, &p->turn, 1);
}

static void put_match(Writer *w, const GnMatchState *m)
{
    put_i32(w, m->away_on_roll);
    put_i32(w, m->away_opponent);
    put_i32(w, m->cube);
    put_i32(w, m->crawford);
}

static void get_match(Reader *r, GnMatchState *m)
{
    m->away_on_roll = get_i32(r);
    m->away_opponent = get_i32(r);
    m->cube = get_i32(r);
    m->crawford = get_i32(r);
}

/* Every field of the config but the pruning network's address. */
static void put_config(Writer *w, const GnSearchConfig *c)
{
    put_i32(w, c->ply);
    for (int d = 0; d <= GN_MAX_PLY; d++) put_i32(w, c->filter[d]);
    for (int d = 0; d <= GN_MAX_PLY; d++) put_i32(w, c->filter_extra[d]);
    for (int d = 0; d <= GN_MAX_PLY; d++) put_f64(w, c->filter_threshold[d]);
    put_i32(w, c->use_match);
    put_match(w, &c->match);
    put_i32(w, c->use_cube);
    put_i32(w, c->cube_owner);
    put_f64(w, c->cube_x);
    put_i32(w, c->prune_k);
    put_i32(w, c->root_stage_ply);
    put_i32(w, c->root_stage_filter);
    put_i32(w, c->root_stage_filter_extra);
    put_f64(w, c->root_stage_filter_threshold);
}

static void get_config(Reader *r, GnSearchConfig *c)
{
    memset(c, 0, sizeof(*c));
    c->ply = get_i32(r);
    for (int d = 0; d <= GN_MAX_PLY; d++) c->filter[d] = get_i32(r);
    for (int d = 0; d <= GN_MAX_PLY; d++) c->filter_extra[d] = get_i32(r);
    for (int d = 0; d <= GN_MAX_PLY; d++) c->filter_threshold[d] = get_f64(r);
    c->use_match = get_i32(r);
    get_match(r, &c->match);
    c->use_cube = get_i32(r);
    c->cube_owner = get_i32(r);
    c->cube_x = get_f64(r);
    c->prune_k = get_i32(r);
    c->root_stage_ply = get_i32(r);
    c->root_stage_filter = get_i32(r);
    c->root_stage_filter_extra = get_i32(r);
    c->root_stage_filter_threshold = get_f64(r);
    c->prune_net = NULL;
}

static void put_play(Writer *w, const GnPlay *p)
{
    for (int m = 0; m < GN_MAX_MOVES_PER_PLAY; m++) {
        put(w, &p->moves[m].from, 1);
        put(w, &p->moves[m].to, 1);
    }
    put_i32(w, p->num_moves);
    put_position(w, &p->result);
}

static void get_play(Reader *r, GnPlay *p)
{
    for (int m = 0; m < GN_MAX_MOVES_PER_PLAY; m++) {
        get(r, &p->moves[m].from, 1);
        get(r, &p->moves[m].to, 1);
    }
    p->num_moves = get_i32(r);
    get_position(r, &p->result);
}

static void put_fp(Writer *w, const GnPlanFingerprint *fp)
{
    put_u64(w, fp->model);
    put_u64(w, fp->prune);
    put_u64(w, fp->bearoff);
}

static void get_fp(Reader *r, GnPlanFingerprint *fp)
{
    fp->model = get_u64(r);
    fp->prune = get_u64(r);
    fp->bearoff = get_u64(r);
}

static const unsigned char PLAN_MAGIC[4] = {'G', 'N', 'D', 'P'};
static const unsigned char TASK_MAGIC[4] = {'G', 'N', 'D', 'T'};

static void put_plan(Writer *w, const GnPlan *plan, uint64_t key)
{
    put(w, PLAN_MAGIC, 4);
    put_u32(w, GN_PLAN_VERSION);
    put_i32(w, plan->kind);
    put_fp(w, &plan->fp);
    put_i32(w, plan->search);
    put_config(w, &plan->config);
    put_position(w, &plan->position);
    put_i32(w, plan->d1);
    put_i32(w, plan->d2);

    put_i32(w, plan->cube.owner);
    put_i32(w, plan->cube.use_match);
    put_match(w, &plan->cube.state);
    put_f64(w, plan->cube.efficiency);
    put_i32(w, plan->cube.jacoby);

    const GnDecision *d = &plan->decision;
    put_position(w, &d->position);
    put_i32(w, (int)d->pending);
    put_i32(w, d->d1);
    put_i32(w, d->d2);
    put_i32(w, d->cube);
    put_i32(w, d->cube_owner);
    put_i32(w, d->jacoby);
    put_i32(w, d->use_match);
    put_i32(w, d->away_on_roll);
    put_i32(w, d->away_opponent);
    put_i32(w, d->crawford);
    put_i32(w, d->resign_value);
    put(w, plan->level, sizeof(plan->level));
    put_i32(w, plan->policy_need);

    put_i32(w, plan->written);
    put_i32(w, plan->waves.written);
    put_i32(w, plan->waves.active);
    put_i32(w, plan->waves.wave);
    put_i32(w, plan->waves.depth);
    put_i32(w, plan->waves.count);
    for (int i = 0; i < plan->written; i++) {
        const GnCandidate *c = &plan->candidates[i];
        put_play(w, &c->play);
        for (int k = 0; k < GN_NUM_OUTPUTS; k++) put_f32(w, c->probs[k]);
        put_f64(w, c->equity);
    }
    for (int k = 0; k < GN_NUM_OUTPUTS; k++) put_f32(w, plan->probs[k]);
    put_f64(w, plan->equity);
    put_i32(w, plan->done);
    put_u64(w, (uint64_t)plan->evaluations);

    const GnAction *a = &plan->action;
    put_i32(w, (int)a->kind);
    put_play(w, &a->play);
    put_i32(w, a->resign_value);
    put_i32(w, a->searched);
    put_f64(w, a->equity_a);
    put_f64(w, a->equity_b);

    put_u64(w, key);
}

/* The wave's key: the fingerprint of the plan as it stands when the wave is
 * emitted. Two waves -- of one plan or of two -- share it only by collision. */
static void refresh_key(GnPlan *plan)
{
    Writer count = {NULL, 0, 0, 0};
    put_plan(&count, plan, 0);
    unsigned char *buf = malloc(count.len);
    if (buf == NULL) {
        plan->wave_key ^= 0x9e3779b97f4a7c15ULL;   /* still changes */
        return;
    }
    Writer w = {buf, count.len, 0, 0};
    put_plan(&w, plan, 0);
    plan->wave_key = gn_plan_fingerprint_bytes(buf, w.len) | 1ULL;
    free(buf);
}

long gn_plan_encode(const GnPlan *plan, unsigned char *buffer, size_t capacity)
{
    if (plan == NULL) return -1;
    Writer w = {buffer, capacity, 0, 0};
    put_plan(&w, plan, plan->wave_key);
    return w.bad ? -1 : (long)w.len;
}

int gn_plan_decode(const unsigned char *buffer, size_t length, GnPlan *plan)
{
    if (buffer == NULL || plan == NULL) return -1;
    memset(plan, 0, sizeof(*plan));
    Reader r = {buffer, length, 0, 0};
    unsigned char magic[4];
    get(&r, magic, 4);
    if (r.bad || memcmp(magic, PLAN_MAGIC, 4) != 0 || get_u32(&r) != GN_PLAN_VERSION) {
        return -1;
    }
    plan->kind = get_i32(&r);
    get_fp(&r, &plan->fp);
    plan->search = get_i32(&r);
    get_config(&r, &plan->config);
    get_position(&r, &plan->position);
    plan->d1 = get_i32(&r);
    plan->d2 = get_i32(&r);

    plan->cube.owner = get_i32(&r);
    plan->cube.use_match = get_i32(&r);
    get_match(&r, &plan->cube.state);
    plan->cube.efficiency = get_f64(&r);
    plan->cube.jacoby = get_i32(&r);

    GnDecision *d = &plan->decision;
    get_position(&r, &d->position);
    d->pending = (GnPending)get_i32(&r);
    d->d1 = get_i32(&r);
    d->d2 = get_i32(&r);
    d->cube = get_i32(&r);
    d->cube_owner = get_i32(&r);
    d->jacoby = get_i32(&r);
    d->use_match = get_i32(&r);
    d->away_on_roll = get_i32(&r);
    d->away_opponent = get_i32(&r);
    d->crawford = get_i32(&r);
    d->resign_value = get_i32(&r);
    get(&r, plan->level, sizeof(plan->level));
    plan->level[sizeof(plan->level) - 1] = '\0';
    plan->policy_need = get_i32(&r);

    plan->written = get_i32(&r);
    plan->waves.written = get_i32(&r);
    plan->waves.active = get_i32(&r);
    plan->waves.wave = get_i32(&r);
    plan->waves.depth = get_i32(&r);
    plan->waves.count = get_i32(&r);
    if (r.bad || plan->written < 0 || plan->written > GN_MAX_PLAYS
        || plan->waves.count < 0 || plan->waves.count > plan->written) {
        return -1;
    }
    if (plan->kind == GN_PLAN_MOVE
        || (plan->kind == GN_PLAN_POLICY
            && plan->policy_need == GN_POLICY_NEED_BEST_PLAY)) {
        /* Room for the whole legal list, as `gn_search_plays` is given. */
        plan->candidates = calloc((size_t)GN_MAX_PLAYS, sizeof(GnCandidate));
        if (plan->candidates == NULL) return -1;
        plan->capacity = GN_MAX_PLAYS;
    }
    for (int i = 0; i < plan->written; i++) {
        if (plan->candidates == NULL) return -1;
        GnCandidate *c = &plan->candidates[i];
        get_play(&r, &c->play);
        for (int k = 0; k < GN_NUM_OUTPUTS; k++) c->probs[k] = get_f32(&r);
        c->equity = get_f64(&r);
    }
    for (int k = 0; k < GN_NUM_OUTPUTS; k++) plan->probs[k] = get_f32(&r);
    plan->equity = get_f64(&r);
    plan->done = get_i32(&r);
    plan->evaluations = (unsigned long)get_u64(&r);

    GnAction *a = &plan->action;
    a->kind = (GnActionKind)get_i32(&r);
    get_play(&r, &a->play);
    a->resign_value = get_i32(&r);
    a->searched = get_i32(&r);
    a->equity_a = get_f64(&r);
    a->equity_b = get_f64(&r);

    plan->wave_key = get_u64(&r);
    return (r.bad || r.at != length) ? -1 : 0;
}

int gn_plan_encode_task(const GnPlan *plan, int index,
                        unsigned char out[GN_PLAN_TASK_BYTES])
{
    GnSearchTask task;
    if (out == NULL || gn_plan_task(plan, index, &task) != 0) {
        return -1;
    }
    memset(out, 0, GN_PLAN_TASK_BYTES);
    Writer w = {out, GN_PLAN_TASK_BYTES, 0, 0};
    put(&w, TASK_MAGIC, 4);
    put_u32(&w, GN_PLAN_VERSION);
    put_fp(&w, &plan->fp);
    put_u64(&w, plan->wave_key);
    put_i32(&w, index);
    put_config(&w, &plan->config);
    put_i32(&w, task.kind);
    put_position(&w, &task.pos);
    put_i32(&w, task.depth);
    put_match(&w, &task.state);
    put_i32(&w, task.owner);
    put_i32(&w, task.roll);
    return w.bad ? -1 : 0;
}

int gn_plan_decode_task(const unsigned char *buffer, size_t length,
                        GnPlanFingerprint *fp, uint64_t *wave_key, int *index,
                        GnSearchConfig *config, GnSearchTask *task)
{
    if (buffer == NULL || length != GN_PLAN_TASK_BYTES || fp == NULL
        || wave_key == NULL || index == NULL || config == NULL || task == NULL) {
        return -1;
    }
    Reader r = {buffer, length, 0, 0};
    unsigned char magic[4];
    get(&r, magic, 4);
    if (r.bad || memcmp(magic, TASK_MAGIC, 4) != 0 || get_u32(&r) != GN_PLAN_VERSION) {
        return -1;
    }
    get_fp(&r, fp);
    *wave_key = get_u64(&r);
    *index = get_i32(&r);
    get_config(&r, config);
    memset(task, 0, sizeof(*task));
    task->kind = get_i32(&r);
    get_position(&r, &task->pos);
    task->depth = get_i32(&r);
    get_match(&r, &task->state);
    task->owner = get_i32(&r);
    task->roll = get_i32(&r);
    return r.bad ? -1 : 0;
}

int gn_plan_run_encoded(const GnNetwork *net, const GnNetwork *prune_net,
                        const GnPlanFingerprint *mine,
                        const unsigned char *bytes, size_t length,
                        GnPlanResult *out)
{
    if (mine == NULL || out == NULL) {
        return -1;
    }
    memset(out, 0, sizeof(*out));
    GnPlanFingerprint theirs;
    GnSearchConfig config;
    GnSearchTask task;
    if (gn_plan_decode_task(bytes, length, &theirs, &out->wave_key, &out->index,
                            &config, &task) != 0) {
        return -1;
    }
    /* Another network, another pruner, another table: another question. The
     * answer would be perfectly plausible -- and would recombine silently
     * into a decision no instance ever made. */
    if (theirs.model != mine->model || theirs.prune != mine->prune
        || theirs.bearoff != mine->bearoff) {
        return -2;
    }
    return gn_plan_run_task(net, prune_net, &config, &task, out);
}

/* ── Bytes in, bytes out ─────────────────────────────────────────────── */

static long emit(GnPlan *plan, int rc, unsigned char **out)
{
    long size = -1;
    *out = NULL;
    if (rc == 0) {
        size = gn_plan_encode(plan, NULL, 0);
        unsigned char *buf = (size > 0) ? malloc((size_t)size) : NULL;
        if (buf == NULL || gn_plan_encode(plan, buf, (size_t)size) != size) {
            free(buf);
            size = -1;
        } else {
            *out = buf;
        }
    }
    gn_plan_free(plan);
    return size;
}

long gn_plan_bytes_move(const GnNetwork *net, const GnNetwork *prune_net,
                        const GnPlanFingerprint *fp, const GnPosition *pos,
                        int d1, int d2, const GnSearchConfig *config,
                        unsigned char **out)
{
    if (out == NULL) return -1;
    GnPlan plan;
    const int rc = gn_plan_begin_move(&plan, net, prune_net, fp, pos, d1, d2, config);
    return emit(&plan, rc, out);
}

long gn_plan_bytes_cube(const GnNetwork *net, const GnNetwork *prune_net,
                        const GnPlanFingerprint *fp, const GnPosition *pos,
                        const GnSearchConfig *config, const GnPlanCube *cube,
                        unsigned char **out)
{
    if (out == NULL) return -1;
    GnPlan plan;
    const int rc = gn_plan_begin_cube(&plan, net, prune_net, fp, pos, config, cube);
    return emit(&plan, rc, out);
}

long gn_plan_bytes_position(const GnNetwork *net, const GnNetwork *prune_net,
                            const GnPlanFingerprint *fp, const GnPosition *pos,
                            const GnSearchConfig *config, unsigned char **out)
{
    if (out == NULL) return -1;
    GnPlan plan;
    const int rc = gn_plan_begin_position(&plan, net, prune_net, fp, pos, config);
    return emit(&plan, rc, out);
}

long gn_plan_bytes_policy(const GnNetwork *net, const GnNetwork *prune_net,
                          const GnPlanFingerprint *fp, const char *level,
                          const GnDecision *decision, unsigned char **out)
{
    if (out == NULL) return -1;
    GnPlan plan;
    const int rc = gn_plan_begin_policy(&plan, net, prune_net, fp, level, decision);
    return emit(&plan, rc, out);
}

long gn_plan_bytes_advance(const GnNetwork *net, const GnNetwork *prune_net,
                           const unsigned char *bytes, size_t length,
                           const GnPlanResult *results, int count,
                           unsigned char **out)
{
    if (out == NULL) return -1;
    *out = NULL;
    GnPlan plan;
    if (gn_plan_decode(bytes, length, &plan) != 0) {
        gn_plan_free(&plan);
        return -1;
    }
    const int rc = gn_plan_advance(&plan, net, prune_net, results, count);
    return emit(&plan, rc, out);
}

void gn_plan_bytes_free(unsigned char *plan)
{
    free(plan);
}

int gn_plan_bytes_info(const unsigned char *bytes, size_t length, int info[6])
{
    GnPlan plan;
    if (info == NULL || gn_plan_decode(bytes, length, &plan) != 0) {
        gn_plan_free(&plan);
        return -1;
    }
    info[0] = plan.kind;
    info[1] = plan.done;
    info[2] = gn_plan_task_count(&plan);
    info[3] = (int)(plan.evaluations & 0x7fffffffUL);
    info[4] = plan.waves.wave;
    info[5] = plan.policy_need;
    gn_plan_free(&plan);
    return 0;
}

int gn_plan_bytes_tasks(const unsigned char *bytes, size_t length,
                        unsigned char *out, int max)
{
    GnPlan plan;
    if (gn_plan_decode(bytes, length, &plan) != 0) {
        gn_plan_free(&plan);
        return -1;
    }
    const int n = gn_plan_task_count(&plan);
    int rc = n;
    if (n > max || (n > 0 && out == NULL)) {
        rc = -1;
    } else {
        for (int k = 0; k < n; k++) {
            if (gn_plan_encode_task(&plan, k, out + (size_t)k * GN_PLAN_TASK_BYTES) != 0) {
                rc = -1;
                break;
            }
        }
    }
    gn_plan_free(&plan);
    return rc;
}

int gn_plan_bytes_candidates(const unsigned char *bytes, size_t length,
                             GnCandidate *out, int max)
{
    GnPlan plan;
    if (gn_plan_decode(bytes, length, &plan) != 0 || !plan.done) {
        gn_plan_free(&plan);
        return -1;
    }
    const GnCandidate *c = NULL;
    const int n = gn_plan_candidates(&plan, &c);
    const int k = (n < max) ? n : max;
    if (k > 0 && out != NULL) {
        memcpy(out, c, sizeof(GnCandidate) * (size_t)k);
    }
    gn_plan_free(&plan);
    return (n < 0) ? -1 : k;
}

int gn_plan_bytes_cube_decision(const unsigned char *bytes, size_t length,
                                GnCubeDecision *out,
                                float probs[GN_NUM_OUTPUTS])
{
    GnPlan plan;
    int rc = -1;
    if (gn_plan_decode(bytes, length, &plan) == 0) {
        rc = gn_plan_cube_decision(&plan, out, probs);
    }
    gn_plan_free(&plan);
    return rc;
}

int gn_plan_bytes_action(const unsigned char *bytes, size_t length,
                         GnAction *out)
{
    GnPlan plan;
    int rc = -1;
    if (gn_plan_decode(bytes, length, &plan) == 0) {
        rc = gn_plan_policy_action(&plan, out);
    }
    gn_plan_free(&plan);
    return rc;
}

int gn_plan_bytes_position_value(const unsigned char *bytes, size_t length,
                                 double *equity, float probs[GN_NUM_OUTPUTS])
{
    GnPlan plan;
    int rc = -1;
    if (gn_plan_decode(bytes, length, &plan) == 0) {
        rc = gn_plan_position(&plan, equity, probs);
    }
    gn_plan_free(&plan);
    return rc;
}

long gn_plan_bytes_evaluations(const unsigned char *bytes, size_t length)
{
    GnPlan plan;
    long n = -1;
    if (gn_plan_decode(bytes, length, &plan) == 0) {
        n = (long)plan.evaluations;
    }
    gn_plan_free(&plan);
    return n;
}

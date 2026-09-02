/*
 * bench_sparsity.c -- T89. What does the layer-1 sparsity actually buy, PER
 * NETWORK and PER KIND OF BATCH?
 *
 * WHY THIS EXISTS
 *
 * The compaction of the live input columns is shipped (`gn_infer_reference.c`,
 * `forward_batch`) and measured at ×1,161 back to back on 2026-09-02. That
 * number is the TWO NETWORKS TOGETHER. The optimisation registry of 2026-08-26
 * predicts ~78 % on the small one alone, because its layer 1 carries 97,5 % of
 * its MACs -- and the small network consumes 76,6 to 93,5 % of the lanes a
 * decision computes. Nobody has separated the two, here or in the Go port.
 *
 * The second thing nobody had separated is the KIND of batch. `bench_batch.c`
 * evaluates positions drawn from anywhere in the reference, so the union of
 * their active features is wide. The search never does that: it batches the
 * legal plays of ONE position and one roll -- a SIBLING SET, which differ by a
 * checker or two and whose union is far narrower. The Go port had to add a
 * separate sibling bench to get an honest number: on eight unrelated boards the
 * union climbed to ~64 of 196 and the transformation became a 9 % LOSS; on a
 * sibling set it was ~32. That distinction is carried here.
 *
 * WHAT IT MEASURES
 *
 *   A. Throughput of `gn_evaluate_batch`, sparsity on vs off, for each network
 *      and each kind of batch, alternated A/B inside the same second.
 *   B. The union width itself -- how many of the 196 features a batch touches.
 *   C. A whole 2-ply decision under four settings: sparsity on both networks
 *      (what ships), on the big one only, on the small one only, on neither.
 *      This is the only measurement that answers "what does each network
 *      contribute to the ×1,16", because it is the only one where both are
 *      driven by the search in their real proportions.
 *
 * The binary is built with -DGN_BATCH_SPARSITY_SWITCH, which is compiled out of
 * the shipped library: the sparsity is not a run-time option, it is the kernel.
 *
 *   bench_sparsity <model.bin> <prune.bin> [repetitions] [decisions]
 *
 * SPDX-License-Identifier: MIT
 */

#define _POSIX_C_SOURCE 199309L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "gn_infer.h"
#include "gn_rules.h"
#include "gn_search.h"

/* Defined in gn_infer_reference.c under -DGN_BATCH_SPARSITY_SWITCH. */
void gn_batch_sparsity_set(GnNetwork *net, int enabled);
void gn_batch_sparsity_label(GnNetwork *net, int slot);
void gn_batch_sparsity_reset(void);
extern unsigned long gn_sparsity_calls[2];
extern unsigned long gn_sparsity_active[2];
extern unsigned long gn_sparsity_widest[2];

#define MAX_PLAYS 2048
#define NUM_LOTS 64

static double now_seconds(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int compare_doubles(const void *a, const void *b)
{
    const double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}

static unsigned long g_state = 20260902UL;

static int roll(void)
{
    g_state = g_state * 6364136223846793005UL + 1442695040888963407UL;
    return (int)((g_state >> 33) % 6) + 1;
}

/* ── The two kinds of batch ──────────────────────────────────────────── */

typedef struct {
    GnPosition board[GN_EVAL_BATCH];
} Lot;

/*
 * A SIBLING batch: the resulting positions of the legal plays of one board and
 * one roll -- exactly what `gn_search.c` hands to `gn_evaluate_batch`. Only
 * rolls with at least GN_EVAL_BATCH distinct plays are kept, so that every lot
 * is full and the A/B compares equal work.
 */
static int fill_sibling_lots(Lot *lots, int wanted)
{
    GnPlay *plays = malloc(sizeof(GnPlay) * MAX_PLAYS);
    if (plays == NULL) {
        return 0;
    }
    GnPosition pos;
    gn_position_initial(&pos);
    int got = 0;
    for (int guard = 0; got < wanted && guard < 200000; guard++) {
        if (gn_position_is_over(&pos)) {
            gn_position_initial(&pos);
            continue;
        }
        const int d1 = roll(), d2 = roll();
        const int count = gn_legal_plays(&pos, d1, d2, plays, MAX_PLAYS);
        if (count >= GN_EVAL_BATCH) {
            for (int n = 0; n < GN_EVAL_BATCH; n++) {
                lots[got].board[n] = plays[n].result;
            }
            got++;
        }
        if (count > 0) {
            pos = plays[count / 2].result;   /* wander, do not follow the engine */
        } else {
            gn_position_swap_turn(&pos);
        }
    }
    free(plays);
    return got;
}

/*
 * An UNRELATED batch: GN_EVAL_BATCH boards taken from different games and
 * different stages, which is what `bench_batch.c` measures without saying so.
 */
static int fill_unrelated_lots(Lot *lots, int wanted)
{
    GnPlay *plays = malloc(sizeof(GnPlay) * MAX_PLAYS);
    if (plays == NULL) {
        return 0;
    }
    GnPosition pos;
    gn_position_initial(&pos);
    int got = 0, slot = 0;
    for (int guard = 0; got < wanted && guard < 400000; guard++) {
        if (gn_position_is_over(&pos)) {
            gn_position_initial(&pos);
            continue;
        }
        const int d1 = roll(), d2 = roll();
        const int count = gn_legal_plays(&pos, d1, d2, plays, MAX_PLAYS);
        if (count <= 0) {
            gn_position_swap_turn(&pos);
            continue;
        }
        pos = plays[(unsigned)roll() % (unsigned)count].result;
        /* One board every seven plies: far enough apart that two lanes of the
         * same lot share nothing but the rules. */
        if (guard % 7 == 0) {
            lots[got].board[slot++] = pos;
            if (slot == GN_EVAL_BATCH) {
                slot = 0;
                got++;
            }
        }
    }
    free(plays);
    return got;
}

/* ── A. throughput, per network, per kind of batch ───────────────────── */

static double timed_pass(GnNetwork *net, const Lot *lots, int lot_count,
                         float (*out)[GN_NUM_OUTPUTS])
{
    const GnPosition *pointers[GN_EVAL_BATCH];
    const double start = now_seconds();
    for (int l = 0; l < lot_count; l++) {
        for (int n = 0; n < GN_EVAL_BATCH; n++) {
            pointers[n] = &lots[l].board[n];
        }
        if (gn_evaluate_batch(net, pointers, GN_EVAL_BATCH, out) != 0) {
            return -1.0;
        }
    }
    return now_seconds() - start;
}

static void measure_kind(GnNetwork *net, const char *net_name, int slot,
                         const Lot *lots, int lot_count, const char *kind_name,
                         int repetitions, float (*out)[GN_NUM_OUTPUTS],
                         double *samples_on, double *samples_off)
{
    gn_batch_sparsity_label(net, slot);

    /* Warm-up, discarded: the first pass faults in the weights. */
    gn_batch_sparsity_set(net, 1);
    (void)timed_pass(net, lots, lot_count, out);

    /* A/B ALTERNATED, not one block then the other: the machine drifts by
     * ±20 % across a session (2026-09-02), and a block layout would put that
     * drift straight into the ratio. */
    for (int r = 0; r < repetitions; r++) {
        gn_batch_sparsity_set(net, 1);
        samples_on[r] = timed_pass(net, lots, lot_count, out);
        gn_batch_sparsity_set(net, 0);
        samples_off[r] = timed_pass(net, lots, lot_count, out);
    }
    gn_batch_sparsity_set(net, 1);

    qsort(samples_on, (size_t)repetitions, sizeof(double), compare_doubles);
    qsort(samples_off, (size_t)repetitions, sizeof(double), compare_doubles);
    const double on = samples_on[repetitions / 2];
    const double off = samples_off[repetitions / 2];
    const double evaluations = (double)lot_count * GN_EVAL_BATCH;

    printf("  %-6s %-12s %12.1f %12.1f %10.3fx\n", net_name, kind_name,
           evaluations / on, evaluations / off, off / on);
}

static void report_union(const char *kind_name, int slot)
{
    if (gn_sparsity_calls[slot] == 0) {
        return;
    }
    printf("  %-12s union moyenne %5.1f / %d entrées  (max %lu)\n", kind_name,
           (double)gn_sparsity_active[slot] / (double)gn_sparsity_calls[slot],
           GN_NUM_FEATURES, gn_sparsity_widest[slot]);
}

/* ── C. a whole decision, settings compared PAIRWISE ─────────────────── */

typedef struct { int big_on, small_on; } Setting;

/*
 * Time ONE decision under one setting. The seed is not touched here: the caller
 * drives the position sequence so that both settings of a pair see the same
 * board and the same roll.
 */
static double one_decision(GnNetwork *net, GnNetwork *prune,
                           const GnPosition *pos, int d1, int d2,
                           Setting setting, GnCandidate *out, int *count_out)
{
    gn_batch_sparsity_set(net, setting.big_on);
    gn_batch_sparsity_set(prune, setting.small_on);

    GnSearchConfig config = gn_search_config(2);
    config.filter[1] = 1;
    config.filter[2] = 3;
    gn_search_use_prune(&config, prune, 12);

    const double start = now_seconds();
    *count_out = gn_search_plays(net, pos, d1, d2, &config, out, MAX_PLAYS);
    return now_seconds() - start;
}

/*
 * PAIRED A/B, and it is the whole point of this section.
 *
 * The 2026-09-02 entry measurement puts this machine's noise floor at ±8 %
 * between consecutive runs of the SAME binary and ±22 % across a session. A
 * decomposition built from four independently timed blocks reads whatever the
 * load did between them -- measured here, three runs of exactly that shape gave
 * +2,1 %, +3,0 % and +8,2 % for the same quantity.
 *
 * So each decision is timed under BOTH settings back to back, on the same board
 * and the same roll, in the order A B B A -- the palindrome cancels any
 * first-versus-second advantage. The statistic is the median of the per-decision
 * ratios, not the ratio of two medians: drift within a few hundred milliseconds
 * is what is left, and that is small.
 */
static double paired_ratio(GnNetwork *net, GnNetwork *prune, int decisions,
                           Setting a, Setting b, double *median_a,
                           double *median_b)
{
    GnCandidate *out = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    double *ratios = malloc(sizeof(double) * (size_t)decisions);
    double *times_a = malloc(sizeof(double) * (size_t)decisions);
    double *times_b = malloc(sizeof(double) * (size_t)decisions);
    if (!out || !ratios || !times_a || !times_b) {
        return -1.0;
    }

    g_state = 20260826UL;
    GnPosition pos;
    gn_position_initial(&pos);
    int done = 0;

    while (done < decisions) {
        if (gn_position_is_over(&pos)) {
            gn_position_initial(&pos);
            continue;
        }
        const int d1 = roll(), d2 = roll();
        int count = 0;
        const double a1 = one_decision(net, prune, &pos, d1, d2, a, out, &count);
        if (count > 1) {
            const double b1 = one_decision(net, prune, &pos, d1, d2, b, out, &count);
            const double b2 = one_decision(net, prune, &pos, d1, d2, b, out, &count);
            const double a2 = one_decision(net, prune, &pos, d1, d2, a, out, &count);
            times_a[done] = a1 + a2;
            times_b[done] = b1 + b2;
            ratios[done] = (a1 + a2) / (b1 + b2);
            done++;
        }
        if (count > 0) {
            pos = out[0].play.result;
        } else {
            gn_position_swap_turn(&pos);
        }
    }

    qsort(ratios, (size_t)decisions, sizeof(double), compare_doubles);
    qsort(times_a, (size_t)decisions, sizeof(double), compare_doubles);
    qsort(times_b, (size_t)decisions, sizeof(double), compare_doubles);
    const double result = ratios[decisions / 2];
    *median_a = times_a[decisions / 2] / 2.0;
    *median_b = times_b[decisions / 2] / 2.0;
    free(out); free(ratios); free(times_a); free(times_b);
    return result;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr,
                "usage: %s <model.bin> <prune.bin> [repetitions] [decisions]\n",
                argv[0]);
        return 2;
    }
    const int repetitions = (argc > 3) ? atoi(argv[3]) : 7;
    const int decisions = (argc > 4) ? atoi(argv[4]) : 12;

    GnNetwork *big = gn_network_load(argv[1]);
    GnNetwork *small = gn_network_load(argv[2]);
    if (big == NULL || small == NULL) {
        fprintf(stderr, "modèle refusé\n");
        return 1;
    }

    Lot *siblings = malloc(sizeof(Lot) * NUM_LOTS);
    Lot *unrelated = malloc(sizeof(Lot) * NUM_LOTS);
    float (*out)[GN_NUM_OUTPUTS] = malloc(sizeof(*out) * GN_EVAL_BATCH);
    double *on = malloc(sizeof(double) * (size_t)repetitions);
    double *off = malloc(sizeof(double) * (size_t)repetitions);
    if (!siblings || !unrelated || !out || !on || !off) {
        return 1;
    }

    const int sibling_lots = fill_sibling_lots(siblings, NUM_LOTS);
    const int unrelated_lots = fill_unrelated_lots(unrelated, NUM_LOTS);
    printf("T89 — la sparsité de la couche 1, par réseau et par type de lot\n");
    printf("lot fixe de %d positions ; %d lots fratrie, %d lots quelconques ;"
           " médiane de %d, A/B alterné\n\n",
           GN_EVAL_BATCH, sibling_lots, unrelated_lots, repetitions);

    /* B. the union width, per kind. Measured on the small network's slot for
     *    the sibling lots and the big one's for the unrelated lots is NOT what
     *    we want -- the union is a property of the BATCH, not of the network,
     *    so each kind gets its own slot and its own reset. */
    printf("B. la largeur de l'union — ce que le noyau doit lire\n");
    gn_batch_sparsity_reset();
    gn_batch_sparsity_label(big, 0);
    (void)timed_pass(big, siblings, sibling_lots, out);
    report_union("fratrie", 0);
    gn_batch_sparsity_reset();
    gn_batch_sparsity_label(big, 0);
    (void)timed_pass(big, unrelated, unrelated_lots, out);
    report_union("quelconques", 0);
    printf("\n");

    printf("A. débit, sparsité activée / désactivée\n");
    printf("  %-6s %-12s %12s %12s %10s\n", "réseau", "lot", "avec éval/s",
           "sans éval/s", "gain");
    measure_kind(big, "grand", 0, siblings, sibling_lots, "fratrie",
                 repetitions, out, on, off);
    measure_kind(big, "grand", 0, unrelated, unrelated_lots, "quelconques",
                 repetitions, out, on, off);
    measure_kind(small, "petit", 1, siblings, sibling_lots, "fratrie",
                 repetitions, out, on, off);
    measure_kind(small, "petit", 1, unrelated, unrelated_lots, "quelconques",
                 repetitions, out, on, off);
    printf("\n");

    printf("C. une décision 2-ply (0,1,3) k=12 — A/B APPARIÉ par décision\n");
    printf("   %d décisions, ordre A B B A, médiane des rapports par décision\n",
           decisions);

    static const Setting none = {0, 0}, big_only = {1, 0}, small_only = {0, 1},
                         both = {1, 1};

    /* Warm-up: the first decision of the process faults in 2,0 Mio of weights. */
    {
        double a, b;
        (void)paired_ratio(big, small, 2, both, both, &a, &b);
    }

    double t_none, t_big, t_small, t_both, unused;
    const double r_big = paired_ratio(big, small, decisions, none, big_only,
                                      &t_none, &t_big);
    const double r_small = paired_ratio(big, small, decisions, none, small_only,
                                        &unused, &t_small);
    const double r_both = paired_ratio(big, small, decisions, none, both,
                                       &unused, &t_both);
    const double r_added = paired_ratio(big, small, decisions, big_only, both,
                                        &unused, &unused);

    printf("\n  %-34s %12s %10s\n", "comparaison", "s/décision", "gain");
    printf("  %-34s %12.4f %9s\n", "aucune sparsité", t_none, "—");
    printf("  %-34s %12.4f %9.3fx\n", "grand seul", t_big, r_big);
    printf("  %-34s %12.4f %9.3fx\n", "petit seul", t_small, r_small);
    printf("  %-34s %12.4f %9.3fx\n", "les deux (ce qui est livré)", t_both, r_both);

    printf("\n  décomposition :\n");
    printf("    ce que le GRAND réseau apporte seul : %+6.1f %%\n",
           100.0 * (r_big - 1.0));
    printf("    ce que le PETIT réseau apporte seul : %+6.1f %%\n",
           100.0 * (r_small - 1.0));
    printf("    les deux ensemble                   : %+6.1f %%\n",
           100.0 * (r_both - 1.0));
    printf("    ce que le PETIT ajoute au GRAND     : %+6.1f %%"
           "  ← le seuil d'abandon de T89 est 5 %%\n",
           100.0 * (r_added - 1.0));

    free(siblings); free(unrelated); free(out); free(on); free(off);
    gn_network_free(big);
    gn_network_free(small);
    return 0;
}

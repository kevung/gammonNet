/*
 * tie_census.c -- how often do two candidate plays hold the SAME equity?
 *
 * WHY
 *
 * T88 says the ranking is not deterministic across targets: `qsort` is not
 * stable, so the order of two candidates that tie depends on the libc. The
 * fix is cheap; the question the fix does NOT answer is how often the case
 * arises, and `CLAUDE.md` rule 3 forbids answering that by reading code.
 *
 * So this driver sweeps a corpus, runs a real decision on every (position,
 * roll) pair, and counts -- with the library built `-DGN_TIE_CENSUS` --
 *
 *   - the sorts that hold at least one pair of BIT-EQUAL equities,
 *   - those pairs,
 *   - and the ones that matter most: a cut (the pruning cut `prune_k`, or the
 *     deep-pass filter) landing BETWEEN two equal equities. That one does not
 *     merely permute the answer, it changes which plays are searched, and the
 *     equities then diverge far above the 1e-6 the parity harness watches.
 *
 * It also dumps the ranking itself (`--dump`), which is what makes a
 * before/after comparison possible: the equities cannot show a permutation,
 * the ORDER of the resulting position identifiers can.
 *
 * The corpus is read with a deliberately dumb scanner -- `"position_id": "…"`
 * and `"turn": n` -- rather than a JSON parser. One line, two fields, no
 * dependency.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gn_infer.h"
#include "gn_position_id.h"
#include "gn_rules.h"
#include "gn_search.h"

#define MAX_PLAYS 2048
#define MAX_LINE 4096

#ifdef GN_TIE_CENSUS
extern unsigned long long gn_tie_sorts, gn_tie_items, gn_tie_sorts_with_tie;
extern unsigned long long gn_tie_pairs, gn_tie_cuts, gn_tie_cuts_split;
#endif

static int field_string(const char *line, const char *key, char *out, size_t n)
{
    const char *p = strstr(line, key);
    if (p == NULL) return -1;
    p = strchr(p + strlen(key), '"');
    if (p == NULL) return -1;
    p++;
    const char *end = strchr(p, '"');
    if (end == NULL || (size_t)(end - p) >= n) return -1;
    memcpy(out, p, (size_t)(end - p));
    out[end - p] = '\0';
    return 0;
}

static int field_int(const char *line, const char *key, int *out)
{
    const char *p = strstr(line, key);
    if (p == NULL) return -1;
    *out = atoi(p + strlen(key));
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr,
                "usage: %s <model.bin> <corpus.jsonl> [ply] [prune.bin] [k] "
                "[max_positions] [--dump]\n", argv[0]);
        return 2;
    }
    const char *model_path = argv[1];
    const char *corpus_path = argv[2];
    const int ply = (argc > 3) ? atoi(argv[3]) : 0;
    const char *prune_path = (argc > 4 && argv[4][0] != '-') ? argv[4] : NULL;
    const int k = (argc > 5) ? atoi(argv[5]) : 0;
    const int max_positions = (argc > 6) ? atoi(argv[6]) : 0;
    int dump = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--dump") == 0) dump = 1;
    }

    GnNetwork *net = gn_network_load(model_path);
    if (net == NULL) {
        fprintf(stderr, "modèle refusé : %s\n", model_path);
        return 1;
    }
    GnNetwork *prune = NULL;
    if (prune_path != NULL && k > 0) {
        prune = gn_network_load(prune_path);
        if (prune == NULL) {
            fprintf(stderr, "réseau d'élagage refusé : %s\n", prune_path);
            return 1;
        }
    }

    /* The canonical shape, so the census describes the decision the project
     * actually makes: 2-ply filter (0,1,3). At ply 0 the filters are inert. */
    GnSearchConfig config = gn_search_config(ply);
    config.filter[1] = 1;
    config.filter[2] = 3;
    if (prune != NULL) {
        gn_search_use_prune(&config, prune, k);
    }

    FILE *f = fopen(corpus_path, "r");
    if (f == NULL) {
        fprintf(stderr, "corpus illisible : %s\n", corpus_path);
        return 1;
    }

    GnCandidate *out = malloc(sizeof(GnCandidate) * MAX_PLAYS);
    if (out == NULL) return 1;

    char line[MAX_LINE];
    char id[64];
    long positions = 0, decisions = 0, ranked = 0;
    long decisions_with_tie = 0, decisions_ambiguous_best = 0;

    while (fgets(line, sizeof(line), f) != NULL) {
        int turn = 0;
        if (field_string(line, "\"position_id\":", id, sizeof(id)) != 0) continue;
        if (field_int(line, "\"turn\":", &turn) != 0) continue;

        GnPosition pos;
        if (gn_position_from_id(id, turn, &pos) != 0) continue;
        if (gn_position_is_over(&pos)) continue;
        positions++;

        /* All twenty-one rolls: a census over one roll per position would be
         * a census of that roll. */
        for (int d1 = 1; d1 <= 6; d1++) {
            for (int d2 = d1; d2 <= 6; d2++) {
                const int count = gn_search_plays(net, &pos, d1, d2, &config,
                                                  out, MAX_PLAYS);
                if (count <= 0) continue;
                decisions++;
                if (count > 1) ranked++;

                int tied = 0;
                for (int i = 1; i < count; i++) {
                    if (out[i].equity == out[i - 1].equity) tied = 1;
                }
                if (tied) decisions_with_tie++;
                /* The one that changes the ANNOUNCED move: the top two are
                 * equal, so which is played depends on the sort alone. */
                if (count > 1 && out[0].equity == out[1].equity) {
                    decisions_ambiguous_best++;
                }

                if (dump) {
                    printf("%s %d %d %d %d", id, turn, d1, d2, count);
                    for (int i = 0; i < count; i++) {
                        char rid[32];
                        if (gn_position_id(&out[i].play.result, rid) != 0) {
                            strcpy(rid, "?");
                        }
                        /* The equity as BITS: a printed decimal hides the
                         * very equality this instrument is looking for. */
                        unsigned long long bits;
                        double e = out[i].equity;
                        memcpy(&bits, &e, sizeof(bits));
                        printf(" %s:%016llx", rid, bits);
                    }
                    printf("\n");
                }
            }
        }
        if (max_positions > 0 && positions >= max_positions) break;
    }
    fclose(f);

    fprintf(stderr, "\ncensus des ex æquo — ply %d, élagage k=%d\n", ply, k);
    fprintf(stderr, "  positions            : %ld\n", positions);
    fprintf(stderr, "  décisions            : %ld (dont %ld à plus d'un coup)\n",
            decisions, ranked);
    fprintf(stderr, "  décisions AVEC un ex æquo bit-à-bit dans le classement rendu : "
            "%ld (%.4f %%)\n", decisions_with_tie,
            decisions ? 100.0 * (double)decisions_with_tie / (double)decisions : 0.0);
    fprintf(stderr, "  décisions dont le MEILLEUR coup est ex æquo : %ld (%.4f %%)\n",
            decisions_ambiguous_best,
            ranked ? 100.0 * (double)decisions_ambiguous_best / (double)ranked : 0.0);
#ifdef GN_TIE_CENSUS
    fprintf(stderr, "  tris                 : %llu (%llu candidats)\n",
            gn_tie_sorts, gn_tie_items);
    fprintf(stderr, "  tris avec ex æquo    : %llu (%.4f %%), %llu paires\n",
            gn_tie_sorts_with_tie,
            gn_tie_sorts ? 100.0 * (double)gn_tie_sorts_with_tie / (double)gn_tie_sorts : 0.0,
            gn_tie_pairs);
    fprintf(stderr, "  coupes (élagage/filtre) : %llu, dont %llu TOMBANT DANS un ex æquo "
            "(%.4f %%)\n", gn_tie_cuts, gn_tie_cuts_split,
            gn_tie_cuts ? 100.0 * (double)gn_tie_cuts_split / (double)gn_tie_cuts : 0.0);
#else
    fprintf(stderr, "  (bibliothèque compilée sans -DGN_TIE_CENSUS : "
            "compteurs internes indisponibles)\n");
#endif
    free(out);
    return 0;
}

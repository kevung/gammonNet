/*
 * gn_bearoff.c -- see gn_bearoff.h for what this refuses to do, and why.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_bearoff.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

/* Established by the arithmetic of the file, not assumed: the header is 40
 * bytes of ASCII, and 1 225 323 048 - 40 is exactly 12 376 x 12 376 x 8. */
#define HEADER_BYTES 40
#define ENTRY_BYTES 8

/* Binomial coefficients up to the sizes this indexing needs. Computed rather
 * than tabulated, and in `long` because C(17,6) is small but the products in a
 * naive factorial form are not. */
static long binomial(int n, int k)
{
    if (k < 0 || k > n) {
        return 0;
    }
    if (k > n - k) {
        k = n - k;
    }
    long result = 1;
    for (int i = 0; i < k; i++) {
        result = result * (n - i) / (i + 1);
    }
    return result;
}

struct GnBearoff {
    int points;
    int chequers;
    long positions;
    const unsigned char *data; /* the entries, header already skipped */
    void *mapping;
    size_t mapped_bytes;
};

long gn_bearoff_index(const int *side, int points)
{
    int total = 0;
    for (int i = 0; i < points; i++) {
        total += side[i];
    }

    /* Offset: every distribution of fewer than `total` checkers comes first.
     * sum_{s<t} C(s+p-1, p-1) = C(t+p-1, p), the hockey-stick identity. */
    long index = binomial(total + points - 1, points);

    int remaining = total;
    for (int i = 0; i < points; i++) {
        const int left = points - i - 1;
        /* Anything carrying MORE checkers on this point sorts before us:
         * within a total, the order is reverse-lexicographic. */
        for (int value = side[i] + 1; value <= remaining; value++) {
            const int rest = remaining - value;
            if (left > 0) {
                index += binomial(rest + left - 1, left - 1);
            } else if (rest == 0) {
                index += 1;
            }
        }
        remaining -= side[i];
    }
    return index;
}

GnBearoff *gn_bearoff_open(const char *path)
{
    if (path == NULL) {
        return NULL;
    }

    const int fd = open(path, O_RDONLY);
    if (fd < 0) {
        return NULL;
    }

    char header[HEADER_BYTES + 1];
    if (read(fd, header, HEADER_BYTES) != (ssize_t)HEADER_BYTES) {
        close(fd);
        return NULL;
    }
    header[HEADER_BYTES] = '\0';

    int points = 0, chequers = 0;
    if (sscanf(header, "gnubg-TS-%d-%d", &points, &chequers) != 2
        || points <= 0 || chequers <= 0) {
        close(fd);
        return NULL;
    }

    struct stat info;
    if (fstat(fd, &info) != 0) {
        close(fd);
        return NULL;
    }

    const long positions = binomial(points + chequers, points);
    const size_t expected =
        (size_t)HEADER_BYTES + (size_t)positions * (size_t)positions * ENTRY_BYTES;
    if ((size_t)info.st_size != expected) {
        /* A file read with the wrong stride returns plausible equities from one
         * end to the other. This check is the only thing standing between that
         * and every measurement downstream. */
        close(fd);
        return NULL;
    }

    void *mapping = mmap(NULL, expected, PROT_READ, MAP_SHARED, fd, 0);
    close(fd);
    if (mapping == MAP_FAILED) {
        return NULL;
    }

    GnBearoff *table = malloc(sizeof(GnBearoff));
    if (table == NULL) {
        munmap(mapping, expected);
        return NULL;
    }
    table->points = points;
    table->chequers = chequers;
    table->positions = positions;
    table->mapping = mapping;
    table->mapped_bytes = expected;
    table->data = (const unsigned char *)mapping + HEADER_BYTES;
    return table;
}

void gn_bearoff_close(GnBearoff *table)
{
    if (table == NULL) {
        return;
    }
    munmap(table->mapping, table->mapped_bytes);
    free(table);
}

int gn_bearoff_points(const GnBearoff *table)
{
    return (table != NULL) ? table->points : 0;
}

int gn_bearoff_chequers(const GnBearoff *table)
{
    return (table != NULL) ? table->chequers : 0;
}

/*
 * Both sides, each in its OWN orientation: `side[i]` is the count on the point
 * `i + 1` pips from bearing off, for that player. The two arrays describe
 * PHYSICALLY OPPOSITE points -- White bears off towards index 0, Black towards
 * index 23. Confusing them would flip the table without breaking anything.
 *
 * Returns 0 when a checker lies outside the covered points.
 */
static int split_sides(const GnBearoff *table, const GnPosition *pos,
                       int *white, int *black)
{
    memset(white, 0, sizeof(int) * (size_t)table->points);
    memset(black, 0, sizeof(int) * (size_t)table->points);

    for (int i = 0; i < GN_NUM_POINTS; i++) {
        const int n = pos->points[i];
        if (n > 0) {
            if (i >= table->points) {
                return 0;
            }
            white[i] += n;
        } else if (n < 0) {
            const int j = GN_NUM_POINTS - 1 - i;
            if (j >= table->points) {
                return 0;
            }
            black[j] += -n;
        }
    }
    return 1;
}

int gn_bearoff_contains(const GnBearoff *table, const GnPosition *pos)
{
    if (table == NULL || pos == NULL) {
        return 0;
    }
    if (gn_position_is_over(pos)) {
        return 0;
    }
    if (pos->bar[GN_WHITE] || pos->bar[GN_BLACK]) {
        return 0;
    }

    int white[GN_NUM_POINTS], black[GN_NUM_POINTS];
    if (!split_sides(table, pos, white, black)) {
        return 0;
    }

    int white_total = 0, black_total = 0;
    for (int i = 0; i < table->points; i++) {
        white_total += white[i];
        black_total += black[i];
    }
    if (white_total > table->chequers || black_total > table->chequers) {
        return 0;
    }
    /* A side with nothing on the board has already won; that is a finished game
     * and `gn_position_is_over` should have caught it. Refuse rather than index
     * an empty distribution into a live lookup. */
    return (white_total > 0 && black_total > 0);
}

int gn_bearoff_equities(const GnBearoff *table, const GnPosition *pos,
                        double equities[4])
{
    if (!gn_bearoff_contains(table, pos) || equities == NULL) {
        return 0;
    }

    int white[GN_NUM_POINTS], black[GN_NUM_POINTS];
    split_sides(table, pos, white, black);

    const int *mine = (pos->turn == GN_WHITE) ? white : black;
    const int *theirs = (pos->turn == GN_WHITE) ? black : white;

    const long a = gn_bearoff_index(mine, table->points);
    const long b = gn_bearoff_index(theirs, table->points);
    if (a < 0 || a >= table->positions || b < 0 || b >= table->positions) {
        return 0;
    }

    const unsigned char *entry =
        table->data + ((size_t)a * (size_t)table->positions + (size_t)b) * ENTRY_BYTES;

    for (int i = 0; i < 4; i++) {
        /* Four little-endian uint16. Scale established against `bearoffdump`:
         * [0, 65535] maps onto [-1, +1]. Read byte by byte rather than through a
         * uint16_t pointer, so the code does not depend on the host's alignment
         * rules or byte order. */
        const unsigned raw =
            (unsigned)entry[2 * i] | ((unsigned)entry[2 * i + 1] << 8);
        equities[i] = (double)raw / 65535.0 * 2.0 - 1.0;
    }
    return 1;
}

int gn_bearoff_probs(const GnBearoff *table, const GnPosition *pos,
                     float probs[GN_NUM_OUTPUTS])
{
    if (probs == NULL) {
        return 0;
    }

    double equities[4];
    if (!gn_bearoff_equities(table, pos, equities)) {
        return 0;
    }

    /*
     * NO GAMMON IS POSSIBLE HERE, and it is checked rather than assumed.
     *
     * The table covers at most `chequers` men on the board per side out of
     * fifteen, so each side has already borne off at least `15 - chequers`. A
     * gammon needs the loser to have borne none. With chequers = 11 the margin
     * is four, but a database built with chequers = 15 would leave none -- so
     * the condition is tested, not trusted to the header we happen to have.
     */
    if (pos->off[GN_WHITE] == 0 || pos->off[GN_BLACK] == 0) {
        return 0;
    }

    const double win = (equities[0] + 1.0) / 2.0;
    probs[0] = (float)(win < 0.0 ? 0.0 : (win > 1.0 ? 1.0 : win));
    probs[1] = 0.0f;
    probs[2] = 0.0f;
    probs[3] = 0.0f;
    probs[4] = 0.0f;
    return 1;
}

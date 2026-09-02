/*
 * tile_asan.c -- the tile rounding, exercised at a tile that is NOT a power of
 * two, under AddressSanitizer.
 *
 * T90. `gn_tile.h` explains the trap; this program is the reason the
 * explanation is not merely a comment. It does three things, and the third is
 * the one a comment cannot do:
 *
 *   1. checks the POSTCONDITION of `gn_round_down_multiple` over a sweep of
 *      widths and tiles -- result <= n, and an exact multiple of the tile;
 *   2. checks that the mask form `n & ~(tile - 1)` VIOLATES that postcondition
 *      at tile 6, so the trap is recorded as a verified fact rather than as a
 *      story about another repository;
 *   3. runs a real tiled reduction, at tile 6, over a HEAP row of exactly
 *      `cols` floats. Under ASan a single element read past the end aborts the
 *      program. Written with the mask, step 3 reads row[192..197] out of 195 --
 *      which is exactly what the Go port shipped. Written with
 *      `gn_round_down_multiple`, it cannot.
 *
 * Static buffers would defeat the point: ASan poisons the redzone around a heap
 * allocation, and a fixed-size array would simply have room. The row is
 * malloc'd, sized to the width, and freed.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <stdlib.h>

#include "gn_tile.h"

/* The header's macros must themselves hold on the constants this project uses,
 * or the guard rail is decorative. */
GN_STATIC_ASSERT_POWER_OF_TWO(32);
GN_STATIC_ASSERT_MULTIPLE_OF(32, 8);
GN_STATIC_ASSERT(!GN_IS_POWER_OF_TWO(6), "6 is not a power of two");
GN_STATIC_ASSERT(!GN_IS_POWER_OF_TWO(0), "zero is not a power of two here");

static int failures = 0;

static void check(int condition, const char *what)
{
    if (!condition) {
        printf("  ÉCHEC : %s\n", what);
        failures++;
    }
}

/*
 * The shape of every tiled kernel in this project: full tiles first, scalar
 * tail after. `rounded` is the only thing that varies between the safe and the
 * unsafe writing, which is why it is a parameter here.
 */
static double tiled_sum(const float *row, int cols, int tile, int rounded)
{
    double total = 0.0;
    int j = 0;
    for (; j < rounded; j += tile) {
        for (int t = 0; t < tile; t++) {
            total += (double)row[j + t];
        }
    }
    for (; j < cols; j++) {
        total += (double)row[j];
    }
    return total;
}

int main(int argc, char **argv)
{
    const int trap = (argc > 1 && argv[1][0] == '-' && argv[1][1] == '-'
                      && argv[1][2] == 't');

    /*
     * `--trap` is the NEGATIVE half of this test, and it is the half that makes
     * ASan load-bearing: it runs the mask form on an exactly-sized heap row and
     * is EXPECTED to die with a heap-buffer-overflow. `tests/test_tile.py`
     * asserts that it does. Without it, a build where ASan silently did nothing
     * would still report success on everything below.
     */
    if (trap) {
        const int cols = 195, tile = 6;
        float *row = malloc((size_t)cols * sizeof(float));
        if (row == NULL) {
            return 1;
        }
        for (int j = 0; j < cols; j++) {
            row[j] = 1.0f;
        }
        const double bad = tiled_sum(row, cols, tile, cols & ~(tile - 1));
        printf("le masque n'a PAS débordé (somme %.0f) — ASan est-il actif ?\n", bad);
        free(row);
        return 0;   /* Reaching here at all is the failure. */
    }

    printf("T90 — l'arrondi des tuiles, tuile 6, sous ASan\n");

    /* 1. The postcondition, over every tile a kernel might plausibly pick and
     *    a range of widths that straddles the interesting remainders. */
    for (int tile = 1; tile <= 33; tile++) {
        for (int n = 0; n <= 260; n++) {
            const int rounded = gn_round_down_multiple(n, tile);
            check(rounded <= n, "l'arrondi dépasse la largeur");
            check(rounded % tile == 0, "l'arrondi n'est pas un multiple de la tuile");
            check(n - rounded < tile, "l'arrondi laisse une tuile entière au reste");
        }
    }
    check(gn_round_down_multiple(195, 6) == 192, "195 arrondi à 6 vaut 192");
    check(gn_round_down_multiple(196, 32) == 192, "196 arrondi à 32 vaut 192");
    /* A tile of zero would be a division by zero. Refused, not undefined. */
    check(gn_round_down_multiple(195, 0) == 0, "tuile nulle refusée");
    check(gn_round_down_multiple(195, -4) == 0, "tuile négative refusée");

    /* 2. The mask form, and the exact input on which it breaks. It agrees with
     *    the safe form for every power of two -- which is why nothing caught
     *    it -- and produces a NON-MULTIPLE at tile 6. */
    for (int tile = 1; tile <= 64; tile *= 2) {
        for (int n = 0; n <= 260; n++) {
            check((n & ~(tile - 1)) == gn_round_down_multiple(n, tile),
                  "masque et arrondi divergent sur une puissance de deux");
        }
    }
    {
        const int masked = 195 & ~(6 - 1);
        check(masked == 194, "le masque à tuile 6 rend bien 194");
        check(masked % 6 != 0, "194 n'est pas un multiple de 6 — le piège");
        check(masked > gn_round_down_multiple(195, 6),
              "le masque dépasse l'arrondi correct");
    }

    /* 3. The kernel itself. 195 floats on the heap, tile 6. */
    const int cols = 195, tile = 6;
    float *row = malloc((size_t)cols * sizeof(float));
    if (row == NULL) {
        return 1;
    }
    for (int j = 0; j < cols; j++) {
        row[j] = 1.0f;
    }
    const double safe = tiled_sum(row, cols, tile,
                                  gn_round_down_multiple(cols, tile));
    check(safe == (double)cols, "la réduction tuilée ne somme pas la ligne");

    /*
     * The unsafe writing, run here on a row deliberately over-sized so that the
     * suite can OBSERVE the fault instead of dying of it: the mask makes the
     * kernel walk 198 elements (indices 0..197) of a 195-element row. Dying of
     * it is what `--trap` above is for.
     */
    {
        const int over = cols + tile;
        float *padded = malloc((size_t)over * sizeof(float));
        if (padded == NULL) {
            free(row);
            return 1;
        }
        for (int j = 0; j < over; j++) {
            padded[j] = (j < cols) ? 1.0f : 1000.0f;
        }
        const double bad = tiled_sum(padded, cols, tile, cols & ~(tile - 1));
        check(bad != (double)cols,
              "le masque devrait lire hors de la ligne — il ne le fait pas");
        printf("  le masque lit %d éléments (indices 0..%d) d'une ligne de %d,"
               " somme %.0f au lieu de %d\n",
               198, 197, cols, bad, cols);
        free(padded);
    }
    free(row);

    if (failures == 0) {
        printf("  tout tient : postcondition, piège du masque, noyau à tuile 6\n");
        return 0;
    }
    printf("  %d échec(s)\n", failures);
    return 1;
}

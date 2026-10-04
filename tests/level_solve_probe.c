/*
 * level_solve_probe.c -- the conventions of the level inversion, on
 * hand-built levels. `level_solve` is static, so this translation unit
 * includes gn_cube.c itself; tests/test_cube.py builds and runs it.
 *
 * Prints one `name value` line per probe, value in %.17g.
 *
 * SPDX-License-Identifier: MIT
 */
#include "../src/gn_cube.c"

#include <stdio.h>

static void probe(const char *name, double value)
{
    printf("%s %.17g\n", name, value);
}

int main(void)
{
    /* A live level with distinct anchors: f(0) = 0.1, f(1) = 0.9. */
    GnMatchLevel live = { 0, 0.1, 0.9, 0.3, 0.7, 0.25, 0.75 };
    /* A flat middle piece: pass == cash, between tp and cp. */
    GnMatchLevel flat = { 0, 0.1, 0.9, 0.5, 0.5, 0.25, 0.75 };
    /* A NaN anchor, as a NaN distribution would leave it. */
    GnMatchLevel poisoned = { 0, NAN, 0.9, 0.3, 0.7, 0.25, 0.75 };

    probe("below_f0_live", level_solve(&live, GN_CUBE_CENTRED, -1.0, 0.05));
    probe("at_f0_live", level_solve(&live, GN_CUBE_CENTRED, -1.0, 0.1));
    probe("above_f1_live", level_solve(&live, GN_CUBE_CENTRED, -1.0, 0.95));
    probe("at_f1_live", level_solve(&live, GN_CUBE_CENTRED, -1.0, 0.9));
    probe("below_f0_blend", level_solve(&live, GN_CUBE_OPPONENT, 0.688, 0.05));
    probe("above_f1_blend", level_solve(&live, GN_CUBE_OPPONENT, 0.688, 0.95));
    probe("at_pass", level_solve(&live, GN_CUBE_CENTRED, -1.0, 0.3));
    probe("flat_left_bound", level_solve(&flat, GN_CUBE_CENTRED, -1.0, 0.5));
    probe("nan_target", level_solve(&live, GN_CUBE_CENTRED, -1.0, NAN));
    probe("nan_target_blend", level_solve(&live, GN_CUBE_CENTRED, 0.688, NAN));
    probe("nan_curve", level_solve(&poisoned, GN_CUBE_CENTRED, -1.0, 0.5));
    probe("nan_curve_blend", level_solve(&poisoned, GN_CUBE_OWNED, 0.688, 0.5));
    return 0;
}

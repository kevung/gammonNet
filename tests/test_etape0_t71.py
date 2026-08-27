"""T71 étape 0 — l'appariement, le signe, et le seuil.

Ce banc décide si T71 existe. Ses trois façons de se tromper en silence sont
un signe inversé (l'élève déclaré meilleur), un z gonflé par une variance
calculée sur les moyennes séparées au lieu de la différence appariée, et un
seuil qu'on aurait relâché pour faire passer la fiche. Les trois rendent un
nombre présentable. D'où des différences écrites à la main.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from etape0_t71 import (  # noqa: E402
    UNPAIRABLE_ALARM,
    Z_THRESHOLD,
    paired_bootstrap,
)


def test_no_difference_is_no_advantage_and_no_z():
    deltas = [0.0] * 200
    mean, low, high, z = paired_bootstrap(deltas, [1.0] * 200, 2000, 1)
    assert mean == pytest.approx(0.0)
    assert low == pytest.approx(0.0)
    assert high == pytest.approx(0.0)
    assert z == 0.0


def test_the_sign_says_professeur_when_the_student_loses_more():
    """`delta = perte(élève) − perte(professeur)` : positif = professeur devant.

    Le sens de cette soustraction est la seule chose qui sépare « distiller la
    recherche » de « distiller le réseau nu dans lui-même ». Un signe inversé
    n'a aucun symptôme : le banc conclurait, avec un z superbe, dans l'autre
    sens.
    """
    teacher_losses = [0.001] * 100
    student_losses = [0.021] * 100
    deltas = [s - t for s, t in zip(student_losses, teacher_losses)]
    mean, low, _high, _z = paired_bootstrap(deltas, [1.0] * 100, 2000, 1)
    assert mean == pytest.approx(0.020)
    assert low > 0


def test_the_pairing_sees_what_two_separate_means_cannot():
    """La raison d'être de la fiche, en un test.

    Un professeur devant de 0,002 par décision, sur des positions dont la perte
    varie de 0 à 0,2. Les moyennes séparées ont un intervalle bien plus large
    que l'avance elle-même ; leur différence appariée la sort du bruit.
    """
    import random
    import statistics

    rng = random.Random(11)
    positions = [abs(rng.gauss(0.05, 0.05)) for _ in range(4000)]
    teacher = positions
    student = [p + 0.002 for p in positions]
    deltas = [s - t for s, t in zip(student, teacher)]

    mean, low, high, z = paired_bootstrap(deltas, [1.0] * len(deltas), 2000, 5)
    assert mean == pytest.approx(0.002, abs=1e-9)
    assert low > 0
    assert z > Z_THRESHOLD

    # La largeur que rendraient deux notations lues séparément : l'écart-type de
    # la position, pas celui de la différence. Ordre de grandeur au-dessus.
    unpaired_halfwidth = 1.96 * statistics.pstdev(positions) / len(positions) ** 0.5
    assert unpaired_halfwidth > (high - low)


def test_a_professeur_behind_comes_out_negative():
    deltas = [-0.004] * 500
    mean, _low, high, _z = paired_bootstrap(deltas, [1.0] * 500, 2000, 1)
    assert mean < 0
    assert high < 0


def test_the_weight_undoes_the_stratification_here_too():
    """Le corpus sur-représente les classes rares ; le poids les remet à leur
    fréquence. Sans lui, une avance concentrée sur les backgames se lirait comme
    une avance générale."""
    deltas = [0.10, 0.10, 0.00, 0.00]
    weights = [0.1, 0.1, 1.9, 1.9]
    mean, _low, _high, _z = paired_bootstrap(deltas, weights, 2000, 1)
    assert mean == pytest.approx(0.005)


def test_the_interval_tightens_with_the_number_of_decisions():
    import random

    rng = random.Random(3)
    small = [rng.gauss(0.002, 0.01) for _ in range(50)]
    large = [rng.gauss(0.002, 0.01) for _ in range(5000)]
    _m1, lo1, hi1, _z1 = paired_bootstrap(small, [1.0] * len(small), 2000, 7)
    _m2, lo2, hi2, _z2 = paired_bootstrap(large, [1.0] * len(large), 2000, 7)
    assert (hi2 - lo2) < (hi1 - lo1) / 5


def test_an_empty_pairing_is_zero_and_not_a_crash():
    assert paired_bootstrap([], [], 100, 1) == (0.0, 0.0, 0.0, 0.0)


def test_the_bootstrap_is_reproducible():
    deltas = [0.001, 0.002, -0.003, 0.004, 0.005]
    first = paired_bootstrap(deltas, [1.0] * 5, 1000, 42)
    second = paired_bootstrap(deltas, [1.0] * 5, 1000, 42)
    assert first == second


def test_the_thresholds_are_the_fiches_and_not_softened():
    """T71 demande z > 3, pas z > 2. Le corpus étant conditionné sur le 2-ply,
    la marge absorbe une part de ce conditionnement — la relâcher rendrait le
    verdict décoratif."""
    assert Z_THRESHOLD >= 3.0
    assert 0.0 < UNPAIRABLE_ALARM <= 0.20

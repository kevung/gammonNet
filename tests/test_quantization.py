"""T73 — les primitives de quantification : échelles, décalages, refus.

Ce qui est vérifié ici n'est pas « la quantification est précise » — cela se
mesure en jeu, pas en test — mais que l'arithmétique fait ce qu'elle annonce :
aucune saturation muette, aucun décalage négatif, et une déquantification
exacte. Ces trois-là, s'ils cèdent, rendent des nombres plausibles.
"""

from __future__ import annotations

import math

import pytest

from gammonnet.quantization import (
    ACTIVATION_MAX,
    WEIGHT_MAX,
    accumulator_headroom,
    clipped_relu,
    dequantize_per_channel,
    power_of_two_shift,
    quantize_per_channel,
    requantization_shift,
    scale_of,
)


@pytest.mark.parametrize("maximum", [0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 7.3, 100.0])
def test_the_scale_covers_the_maximum_without_saturating(maximum):
    """La propriété qui compte : rien n'écrête."""
    shift = power_of_two_shift(maximum)
    assert maximum / scale_of(shift) <= WEIGHT_MAX + 1e-9


@pytest.mark.parametrize("maximum", [0.001, 0.1, 1.0, 7.3, 100.0])
def test_the_scale_is_the_finest_that_does_not_saturate(maximum):
    """Un cran plus fin écrêterait — c'est ce qui borne le choix par le haut.

    Écrit d'abord à l'envers (« la plus grande échelle »), ce test a échoué sur
    un code correct. La description était fausse, pas l'arithmétique.
    """
    shift = power_of_two_shift(maximum)
    finer = scale_of(shift + 1)
    assert maximum / finer > WEIGHT_MAX


def test_a_zero_tensor_is_not_a_crash():
    assert power_of_two_shift(0.0) == 0
    quantized, shifts = quantize_per_channel([[0.0, 0.0]])
    assert quantized == [[0, 0]]
    assert shifts == [0]


def test_the_scale_is_always_a_power_of_two():
    """La propriété dont dépend toute la garantie bit-à-bit."""
    for maximum in (0.003, 0.42, 1.7, 96.0):
        scale = scale_of(power_of_two_shift(maximum))
        assert math.log2(scale) == int(math.log2(scale))


def test_per_channel_protects_a_small_neuron_from_a_large_one():
    """Le cas qui justifie le per-channel : deux lignes d'échelles très
    différentes. Par tenseur, la petite serait écrasée à zéro."""
    rows = [[1e-3, -1e-3], [100.0, -100.0]]
    quantized, shifts = quantize_per_channel(rows)
    assert shifts[0] != shifts[1]
    # La petite ligne garde de la résolution : elle n'est pas nulle.
    assert any(value != 0 for value in quantized[0])
    assert max(abs(v) for v in quantized[0]) > WEIGHT_MAX // 2


def test_dequantization_is_exact():
    """Entier × puissance de deux : le produit est représentable exactement."""
    rows = [[0.5, -0.25, 0.125], [3.0, -1.5, 0.0]]
    quantized, shifts = quantize_per_channel(rows)
    back = dequantize_per_channel(quantized, shifts)
    for row_back, shift in zip(back, shifts):
        for value in row_back:
            assert value % scale_of(shift) == 0.0 or value == 0.0


def test_nothing_exceeds_the_symmetric_bound():
    rows = [[10.0, -10.0, 5.0], [0.1, -0.1, 0.05]]
    quantized, _shifts = quantize_per_channel(rows)
    for row in quantized:
        assert all(-WEIGHT_MAX <= value <= WEIGHT_MAX for value in row)


def test_the_requantization_shift_is_the_difference_of_scales():
    assert requantization_shift(7, 6, 6) == 7
    assert requantization_shift(10, 4, 8) == 6


def test_a_negative_shift_is_refused_and_not_tolerated():
    """Un décalage à gauche inventerait de la dynamique. Il doit lever, pas
    passer : des activations plausibles et fausses sont le mode de défaillance
    que la règle 2 de CLAUDE.md nomme."""
    with pytest.raises(ValueError):
        requantization_shift(4, 4, 12)


def test_the_clipped_relu_clips_at_both_ends():
    assert clipped_relu(-5.0) == 0.0
    assert clipped_relu(0.0) == 0.0
    assert clipped_relu(60.0) == 60.0
    assert clipped_relu(1000.0) == float(ACTIVATION_MAX)


def test_the_headroom_matches_the_c_side():
    """Le pipeline doit refuser au moment de l'entraînement ce que le noyau
    refuserait à l'exportation — pas après des heures de GPU."""
    from gammonnet.gemm_int8 import headroom as c_headroom
    for cols in (196, 256, 512, 1024, 16_384):
        assert accumulator_headroom(cols) == pytest.approx(c_headroom(cols))

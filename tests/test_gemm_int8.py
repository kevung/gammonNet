"""T73 — le noyau int8 : bit pour bit, et la borne qui le garantit.

La promesse de `src/gn_gemm_int8.h` est forte — *tout* chemin vectoriel rend
exactement ce que rend le scalaire, sur toute plateforme — et elle repose sur un
seul fait : l'addition int32 est associative tant que rien ne déborde. Ces tests
attaquent les deux moitiés : l'égalité, et la borne.

Un écart ici ne serait pas une imprécision. Ce serait la garantie du projet,
fausse.
"""

from __future__ import annotations

import random

import pytest

from gammonnet.gemm_int8 import ACTIVATION_MAX, headroom, path, raw, relu, relu_pc

#: Les formes du réseau embarqué (196 → 512 → 512 → 256 → 128 → 5), plus des
#: formes tordues : c'est dans les épilogues que les noyaux vectoriels se
#: trompent, jamais au milieu d'une boucle bien alignée.
SHAPES = [(512, 196), (512, 512), (256, 512), (128, 256), (5, 128),
          (7, 13), (1, 1), (3, 9), (17, 5)]


def sample(rows: int, cols: int, batch: int, seed: int):
    rng = random.Random(seed)
    weights = [rng.randint(-128, 127) for _ in range(rows * cols)]
    bias = [rng.randint(-10_000, 10_000) for _ in range(rows)]
    activations = [rng.randint(0, ACTIVATION_MAX) for _ in range(cols * batch)]
    return weights, bias, activations


@pytest.mark.parametrize("rows,cols", SHAPES)
@pytest.mark.parametrize("batch", [1, 3, 8, 9, 16, 31, 32])
def test_the_dispatched_kernel_equals_the_scalar_reference(rows, cols, batch):
    weights, bias, activations = sample(rows, cols, batch, seed=rows * 31 + cols)
    fast = raw(weights, rows, cols, bias, activations, batch)
    slow = raw(weights, rows, cols, bias, activations, batch, reference=True)
    assert fast == slow, f"{path()} diverge du scalaire en {rows}×{cols} lot {batch}"


@pytest.mark.parametrize("rows,cols", [(512, 512), (128, 256)])
def test_the_arithmetic_worst_case_still_agrees(rows, cols):
    """Toutes les activations au plafond, les poids alternés aux deux bornes.

    C'est le cas qui déborderait en premier si la borne était fausse, et celui
    où un noyau qui saturerait au lieu d'élargir se trahirait.
    """
    batch = 32
    weights = [127 if i % 2 else -128 for i in range(rows * cols)]
    activations = [ACTIVATION_MAX] * (cols * batch)
    fast = raw(weights, rows, cols, None, activations, batch)
    slow = raw(weights, rows, cols, None, activations, batch, reference=True)
    assert fast == slow


def test_the_headroom_is_the_promised_factor():
    """×260 à 512 entrées : la garantie n'est pas juste vraie, elle est large."""
    assert headroom(512) == pytest.approx(2147483647.0 / (512 * 16129))
    assert headroom(512) > 250
    assert headroom(196) > 600


def test_a_layer_without_headroom_is_refused_and_not_approximated():
    """Au-delà de ~16 600 entrées la borne tombe sous 1 : le noyau refuse.

    C'est la règle 2 de `CLAUDE.md` appliquée à l'arithmétique — un débordement
    silencieux rendrait cinq probabilités parfaitement plausibles.
    """
    assert headroom(16_384) > 1.0
    assert headroom(200_000) < 1.0
    with pytest.raises(ValueError):
        raw([0] * 200_000, 1, 200_000, None, [0] * 200_000, 1)


def test_the_clipped_relu_clamps_at_both_ends():
    rows, cols, batch = 4, 8, 4
    # Un poids positif fort et des activations au plafond saturent en haut ;
    # le même en négatif est écrasé à zéro.
    weights = [127] * (cols * 2) + [-128] * (cols * 2)
    activations = [ACTIVATION_MAX] * (cols * batch)
    out = relu(weights, rows, cols, None, activations, batch, shift=0)
    assert out[: 2 * batch] == [ACTIVATION_MAX] * (2 * batch)
    assert out[2 * batch:] == [0] * (2 * batch)


def test_the_shift_is_exact_and_not_a_rounding_multiply():
    """Le décalage doit être l'arithmétique du C, à la puissance de deux près —
    c'est le seul endroit où les deux cibles pourraient diverger, et un décalage
    ne le peut pas."""
    rows, cols, batch = 1, 4, 1
    weights = [1, 1, 1, 1]
    activations = [100, 100, 100, 100]  # accumulateur = 400
    assert relu(weights, rows, cols, None, activations, batch, shift=0) == [127]
    assert relu(weights, rows, cols, None, activations, batch, shift=2) == [100]
    assert relu(weights, rows, cols, None, activations, batch, shift=3) == [50]
    assert relu(weights, rows, cols, None, activations, batch, shift=10) == [0]


def test_a_zero_weight_changes_nothing():
    """La parcimonie est un raccourci qui ne peut PAS déplacer un bit : sauter
    un zéro dans une somme d'entiers est exact, pas approché."""
    rows, cols, batch = 6, 32, 8
    weights, bias, activations = sample(rows, cols, batch, seed=5)
    sparse = [0 if i % 3 else w for i, w in enumerate(weights)]
    dense_equivalent = list(sparse)
    assert raw(sparse, rows, cols, bias, activations, batch) == \
           raw(dense_equivalent, rows, cols, bias, activations, batch, reference=True)


def test_refusals_are_refusals():
    with pytest.raises(ValueError):
        raw([1], 0, 1, None, [1], 1)
    with pytest.raises(ValueError):
        raw([1], 1, 1, None, [1], 0)
    with pytest.raises(ValueError):
        relu([1], 1, 1, None, [1], 1, shift=-1)
    with pytest.raises(ValueError):
        relu([1], 1, 1, None, [1], 1, shift=32)


def test_the_path_is_named_so_a_number_can_say_who_produced_it():
    assert path() in {"scalar", "simd128", "sse2", "avx2"}


# ── Le décalage par canal : ce que la QAT entraîne réellement ──────────────


@pytest.mark.parametrize("rows,cols", SHAPES)
@pytest.mark.parametrize("batch", [1, 8, 32])
def test_relu_pc_with_uniform_shifts_equals_relu(rows, cols, batch):
    """Un même décalage répété `rows` fois doit rendre exactement `relu` —
    `relu_pc` n'est pas une arithmétique différente, seulement plus fine."""
    weights, bias, activations = sample(rows, cols, batch, seed=rows * 17 + cols)
    shift = 5
    uniform = relu(weights, rows, cols, bias, activations, batch, shift=shift)
    per_channel = relu_pc(weights, rows, cols, bias, activations, batch,
                          shifts=[shift] * rows)
    assert uniform == per_channel


def test_relu_pc_shifts_are_genuinely_independent_per_row():
    """Chaque rangée doit répondre à SON PROPRE décalage, pas à celui de la
    rangée voisine — la raison d'être de cette fonction."""
    rows, cols, batch = 3, 4, 1
    weights = [1, 1, 1, 1] * rows
    activations = [100, 100, 100, 100]  # accumulateur = 400 par rangée
    out = relu_pc(weights, rows, cols, None, activations, batch,
                  shifts=[0, 2, 3])
    assert out == [127, 100, 50]  # mêmes valeurs que le test scalaire de `relu`


def test_relu_pc_matches_a_manual_per_row_reference():
    """Reconstruit la sortie rangée par rangée avec `raw` (accumulateurs bruts,
    non décalés) et un décalage propre à chaque rangée — une seconde voie,
    indépendante de `relu_pc`, vers le même nombre."""
    rows, cols, batch = 6, 32, 8
    weights, bias, activations = sample(rows, cols, batch, seed=99)
    shifts = [(i * 3) % 8 for i in range(rows)]

    accumulators = raw(weights, rows, cols, bias, activations, batch)
    expected = []
    for i in range(rows):
        row_acc = accumulators[i * batch:(i + 1) * batch]
        for value in row_acc:
            scaled = value >> shifts[i]
            expected.append(max(0, min(ACTIVATION_MAX, scaled)))

    assert relu_pc(weights, rows, cols, bias, activations, batch, shifts) == expected


def test_relu_pc_refuses_a_shift_out_of_range_on_any_row():
    with pytest.raises(ValueError):
        relu_pc([1] * 4, 2, 2, None, [1, 1], 1, shifts=[0, -1])
    with pytest.raises(ValueError):
        relu_pc([1] * 4, 2, 2, None, [1, 1], 1, shifts=[32, 0])

"""T70 — l'escalade : ce qui est tranché, ce qui est borné, ce qui reste ouvert.

`resolution_of` décide où s'arrête l'arbitrage de chaque décision, donc combien
la campagne coûte et ce que le registre garantit. Un défaut ici ne plante pas :
il rend un registre trop cher, ou pire, un registre bon marché dont les valeurs
ne tiennent pas ce qu'elles promettent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from arbitrate_t70 import decided, resolution_of  # noqa: E402

MARGIN = 0.005


def test_the_pivot_is_always_resolved():
    """Sa différence à lui-même est identiquement nulle, sans incertitude."""
    states = resolution_of([0.0, -0.02], [0.0, 0.001], pivot=0, margin=MARGIN)
    assert states[0] == "resolved"


def test_a_tight_interval_is_resolved():
    # 1,96 × 0,002 = 0,0039 < 0,005
    states = resolution_of([0.0, -0.01], [0.0, 0.002], pivot=0, margin=MARGIN)
    assert states[1] == "resolved"


def test_a_clearly_dominated_candidate_needs_no_precision():
    """Le levier qui rend la campagne soutenable : un coup dont on sait avec
    certitude qu'il est bien pire n'a pas besoin d'être prix finement.

    Écart -0,20, erreur 0,02 : l'intervalle est vingt fois trop large pour la
    résolution, et pourtant -0,20 + 0,039 = -0,161 reste franchement sous
    -0,005. Le classement ne peut pas basculer.
    """
    states = resolution_of([0.0, -0.20], [0.0, 0.02], pivot=0, margin=MARGIN)
    assert states[1] == "dominated"


def test_a_close_and_imprecise_candidate_stays_open():
    """Le cas qui doit coûter cher, parce que lui seul peut changer le verdict.

    Écart -0,004, erreur 0,02 : ce candidat pourrait être meilleur que le
    pivot. C'est exactement ce que la passe 3 est là pour trancher.
    """
    states = resolution_of([0.0, -0.004], [0.0, 0.02], pivot=0, margin=MARGIN)
    assert states[1] == "open"


def test_a_candidate_that_might_beat_the_pivot_is_never_dominated():
    """Un écart POSITIF ne peut jamais être classé dominé, quelle que soit son
    erreur — ce serait déclarer tranché un candidat qui gagne."""
    for error in (0.0001, 0.01, 1.0):
        states = resolution_of([0.0, +0.05], [0.0, error], pivot=0, margin=MARGIN)
        assert states[1] != "dominated"


def test_the_boundary_of_domination_is_where_the_interval_ends():
    """Juste au-dessus du seuil : encore ouvert. Juste en dessous : dominé.

    -d + 1,96e < -margin. Avec e = 0,01, 1,96e = 0,0196 ; il faut donc
    d < -0,0246 pour dominer.
    """
    open_case = resolution_of([0.0, -0.024], [0.0, 0.01], pivot=0, margin=MARGIN)
    dominated = resolution_of([0.0, -0.026], [0.0, 0.01], pivot=0, margin=MARGIN)
    assert open_case[1] == "open"
    assert dominated[1] == "dominated"


def test_decided_is_exactly_the_absence_of_open():
    assert decided([0.0, -0.20, -0.01], [0.0, 0.02, 0.002], 0, MARGIN)
    assert not decided([0.0, -0.20, -0.004], [0.0, 0.02, 0.02], 0, MARGIN)


def test_a_non_zero_pivot_works_the_same():
    """Le pivot est le meilleur selon gnubg 3-ply, pas forcément le premier."""
    states = resolution_of([-0.30, 0.0, -0.002], [0.05, 0.0, 0.001],
                           pivot=1, margin=MARGIN)
    assert states == ["dominated", "resolved", "resolved"]


@pytest.mark.parametrize("margin", [0.0025, 0.005, 0.010, 0.020])
def test_a_looser_margin_never_leaves_more_open(margin):
    """Relâcher la résolution ne peut qu'aider : c'est le levier de coût, et il
    doit être monotone, sans quoi le régler serait deviner."""
    differences = [0.0, -0.006, -0.05, -0.001]
    errors = [0.0, 0.004, 0.02, 0.003]
    tight = resolution_of(differences, errors, 0, 0.001).count("open")
    loose = resolution_of(differences, errors, 0, margin).count("open")
    assert loose <= tight

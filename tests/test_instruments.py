"""Les instruments de T81/T82 retrouvent-ils ce qu'on sait déjà ?

Ce fichier est le garde-fou de `python/gammonnet/instruments.py` : il fige les
réponses **connues d'avance**, celles qu'un extracteur correct doit rendre. Un
extracteur qui dérive se trahit ici plutôt que dans une campagne.

Les ancrages sont publiés, pas mesurés chez nous : Janowski (1993) pour les
points de prise sans gammon, Rockwell-Kazaross pour le pivot -2/-1 Crawford.
"""

from __future__ import annotations

import pytest

from gammonnet import instruments as I
from gammonnet.cube import CubeOwner
from gammonnet.infer import Evaluation
from gammonnet.met import MatchState


@pytest.fixture(scope="module")
def read_table() -> dict[tuple[int, int], float]:
    return I.read_met(25)


@pytest.fixture(scope="module")
def post_row() -> dict[int, float]:
    return I.post_crawford_row(25)


@pytest.mark.parametrize("x,expected", [(0.0, 0.25), (1.0, 0.20)])
def test_take_point_retrouve_les_valeurs_de_manuel(x: float, expected: float) -> None:
    """Janowski (1993), sans gammon : 0,25 à videau mort, 0,20 à videau vivant.

    Le balayage ne demande pas son point de prise au moteur ; il observe où le
    verdict bascule. C'est ce qui le rendra applicable à un modèle appris.
    """
    assert I.swept_take_point(x) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("x", [0.0, 0.3, 0.566, 0.687, 0.688, 1.0])
def test_le_balayage_retrouve_la_forme_fermee(x: float) -> None:
    assert I.swept_cash_point(x) == pytest.approx(I.analytic_cash_point(x), abs=1e-6)
    assert I.swept_take_point(x) == pytest.approx(I.analytic_take_point(x), abs=1e-6)


def test_la_fenetre_de_double_est_ordonnee() -> None:
    """Doubler avant de encaisser : le point de double précède le point de caisse."""
    x = 0.688
    assert I.swept_double_point(x) < I.swept_cash_point(x)


def test_frontier_refuse_un_intervalle_sans_bascule() -> None:
    """Un instrument qui ne trouve rien doit le dire, pas rendre un nombre."""
    with pytest.raises(ValueError):
        I.frontier(lambda _p: True)


def test_antisymetrie(read_table) -> None:
    assert I.check_antisymmetry(read_table).passed


def test_monotonies(read_table) -> None:
    assert I.check_monotonicity(read_table).passed


def test_identite_dmp() -> None:
    """À 1-away/1-away les gammons ne valent rien : une ancre exacte, gratuite."""
    check = I.check_dmp(lambda s, e: s.winning_chance(e))
    assert check.passed, check.worst_case


def test_pivot_crawford(read_table) -> None:
    """Le repère public de toute MET moderne : 32,31 % chez Rockwell-Kazaross."""
    check = I.check_pivot(read_table)
    assert check.passed
    assert read_table[(2, 1)] == pytest.approx(0.3226, abs=5e-4)


def test_signature_de_parite_du_free_drop(post_row) -> None:
    """Le free drop laisse un rythme, pas une valeur : petit pas vers le pair,
    grand pas vers l'impair."""
    assert I.check_free_drop(post_row).passed
    assert post_row[1] - post_row[2] < post_row[2] - post_row[3]


def test_la_met_lue_est_l_identite(read_table) -> None:
    """`read_met` ne mesure pas : elle fixe les conventions. Si elle cessait
    d'être l'identité de la table, c'est l'indexation qui aurait dérivé."""
    from gammonnet import met

    assert read_table[(3, 5)] == pytest.approx(met.pre_crawford(3, 5))
    assert read_table[(1, 1)] == pytest.approx(0.5)


def test_le_residu_se_calcule_sur_les_cellules_communes() -> None:
    implicit = {(1, 1): 0.55, (2, 1): 0.30}
    reference = {(1, 1): 0.50, (2, 1): 0.32, (9, 9): 0.5}
    residual = I.met_residual(implicit, reference)
    assert len(residual.cells) == 2
    assert residual.cells[(1, 1)] == pytest.approx(0.05)
    assert residual.worst[0] == (1, 1)
    assert [k for k, _ in residual.above(0.03)] == [(1, 1)]


def test_le_residu_refuse_deux_tables_disjointes() -> None:
    with pytest.raises(ValueError):
        I.met_residual({(1, 1): 0.5}, {(2, 2): 0.5})


def test_implicit_met_interroge_bien_le_moteur() -> None:
    """L'extracteur passe un `MatchState` complet, videau centré — c'est ce que
    verra le modèle appris."""
    seen: list[MatchState] = []

    def _spy(state: MatchState) -> float:
        seen.append(state)
        return 0.5

    table = I.implicit_met(_spy, max_away=3)
    assert len(table) == 9
    assert all(s.cube == 1 and not s.crawford for s in seen)


def test_gammonless_est_bien_sans_gammon() -> None:
    evaluation = I.gammonless(0.42)
    assert evaluation == Evaluation(0.42, 0.0, 0.0, 0.0, 0.0)
    assert evaluation.money_equity == pytest.approx(2 * 0.42 - 1)


def test_le_cubeful_et_le_cubeless_ne_disent_pas_la_meme_chose() -> None:
    """Le contrôle qui justifie d'avoir DEUX extractions : elles diffèrent, et
    c'est l'écart qui porte l'information sur ce que vaut le videau."""
    opening = Evaluation(0.5136, 0.1452, 0.0064, 0.1334, 0.0053)
    state = MatchState(2, 4, cube=1)
    efficiency = (0.688, 0.566, 0.687)
    cubeless = I.classic_mwc_at_start(opening)(state)
    cubeful = I.classic_cubeful_mwc_at_start(opening, efficiency)(state)
    assert cubeless != pytest.approx(cubeful, abs=1e-4)
    assert 0.0 < cubeful < 1.0


def test_les_proprietes_se_rendent_toutes_ensemble(read_table, post_row) -> None:
    checks = I.all_properties(read_table, lambda s, e: s.winning_chance(e), post_row)
    assert len(checks) == 5
    assert all(c.passed for c in checks)
    assert {c.as_dict()["name"] for c in checks} == {
        "antisymétrie",
        "monotonies",
        "identité DMP",
        "pivot -2/-1 Crawford",
        "signature de parité du free drop",
    }

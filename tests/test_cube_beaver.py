"""Beaver et raccoon (`docs/specs/t34-videau-spec.md` §4bis), contre un oracle écrit ici.

L'oracle ne lit rien de `gn_cube.c` : il refait le modèle de Janowski depuis
le tableau du §2 et l'interpolation du §3, puis l'arithmétique du beaver
(×2, ×4, ×8 du videau) et la table du §4. Les ancrages en forme close sont
dérivés à la main et cités par la spécification ; les cas limites tombent
exactement sur une égalité, là où un `<` devenu `<=` se verrait.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from gammonnet.cube import CubeAction, CubeOwner, decide
from gammonnet.infer import Evaluation
from gammonnet.met import MatchState


def evaluation(p: float, wg: float = 0.0, lg: float = 0.0) -> Evaluation:
    return Evaluation(win=p, win_gammon=wg, win_backgammon=0.0,
                      lose_gammon=lg, lose_backgammon=0.0)


# ── L'oracle ─────────────────────────────────────────────────────────

def _line(p, x0, y0, x1, y1):
    return y0 + (y1 - y0) * (p - x0) / (x1 - x0)


def oracle_equity(p, W, L, owner, x):
    """Spec §2 (courbe vivante par état) et §3 (mélange mort/vivant)."""
    dead = p * W - (1 - p) * L
    tp = (L - 0.5) / (W + L + 0.5)
    cp = (L + 1) / (W + L + 0.5)
    if owner == CubeOwner.OWNED:
        live = _line(p, 0, -L, cp, 1) if p <= cp else _line(p, cp, 1, 1, W)
    elif owner == CubeOwner.OPPONENT:
        live = _line(p, 0, -L, tp, -1) if p <= tp else _line(p, tp, -1, 1, W)
    else:
        if p <= tp:
            live = _line(p, 0, -L, tp, -1)
        elif p <= cp:
            live = _line(p, tp, -1, cp, 1)
        else:
            live = _line(p, cp, 1, 1, W)
    return (1 - x) * dead + x * live


def oracle_verdict(e_nd, e_answer, e_dp):
    e_double = min(e_answer, e_dp)
    if e_nd > e_dp and e_nd >= e_double:
        return CubeAction.TOO_GOOD
    if e_answer >= e_dp:
        return CubeAction.DOUBLE_PASS
    if e_double > e_nd:
        return CubeAction.DOUBLE_TAKE
    return CubeAction.NO_DOUBLE


def oracle(p, wg, lg, owner, x, jacoby):
    W = 1 + wg / p
    L = 1 + lg / (1 - p)
    if jacoby and owner == CubeOwner.CENTRED:
        e_nd = oracle_equity(p, 1.0, 1.0, owner, x)
    else:
        e_nd = oracle_equity(p, W, L, owner, x)
    theirs = oracle_equity(p, W, L, CubeOwner.OPPONENT, x)
    mine = oracle_equity(p, W, L, CubeOwner.OWNED, x)
    e_dt, e_dp = 2 * theirs, 1.0
    raccoon = 8 * mine > 4 * theirs
    e_bv = 8 * mine if raccoon else 4 * theirs
    beaver = e_bv < e_dt and e_bv < e_dp
    answer = min(e_dt, e_bv)
    if owner == CubeOwner.OPPONENT:
        return CubeAction.NO_DOUBLE, min(answer, e_dp), e_dt, e_bv, False, False
    return (oracle_verdict(e_nd, answer, e_dp), min(answer, e_dp), e_dt, e_bv,
            beaver, raccoon)


# Multiples de 1/64 : exacts en float32, donc p, W, L sont ceux de l'oracle.
GRID_P = [k / 64 for k in range(1, 64)]
GRID_GAMMONS = [(0.0, 0.0), (1 / 64, 0.0), (0.0, 1 / 64), (1 / 16, 1 / 32)]
GRID_X = [0.0, 0.25, 0.68, 1.0]


def _cases():
    for p in GRID_P:
        for wg, lg in GRID_GAMMONS:
            if wg > p or lg > 1 - p:
                continue
            for x in GRID_X:
                for owner in CubeOwner:
                    for jacoby in (False, True):
                        yield p, wg, lg, x, owner, jacoby


def test_the_engine_agrees_with_the_oracle_on_the_whole_grid():
    checked = 0
    for p, wg, lg, x, owner, jacoby in _cases():
        got = decide(evaluation(p, wg, lg), owner, x, jacoby=jacoby, beaver=True).beaver
        action, e_double, e_dt, e_bv, beaver, raccoon = oracle(p, wg, lg, owner, x, jacoby)
        case = (p, wg, lg, x, owner, jacoby)
        assert got.equity_take == pytest.approx(e_dt, abs=1e-12), case
        assert got.equity_beaver == pytest.approx(e_bv, abs=1e-12), case
        assert got.equity_double == pytest.approx(e_double, abs=1e-12), case
        assert got.beaver is beaver, case
        assert got.raccoon is raccoon, case
        assert got.action == action, case
        checked += 1
    assert checked > 3000


def test_the_flag_never_moves_the_plain_fields():
    """Drapeau allumé ou éteint, les champs du §4 sont identiques bit à bit."""
    for p, wg, lg, x, owner, jacoby in _cases():
        off = decide(evaluation(p, wg, lg), owner, x, jacoby=jacoby)
        on = decide(evaluation(p, wg, lg), owner, x, jacoby=jacoby, beaver=True)
        assert off.beaver is None
        assert (on.action, on.equity_no_double, on.equity_double, on.take_point) == (
            off.action, off.equity_no_double, off.equity_double, off.take_point)


def test_beaver_is_money_only():
    state = MatchState(away_on_roll=5, away_opponent=5, cube=1, crawford=False)
    plain = decide(evaluation(0.4), CubeOwner.CENTRED, 0.68, state=state)
    asked = decide(evaluation(0.4), CubeOwner.CENTRED, 0.68, state=state, beaver=True)
    assert asked.beaver is None
    assert asked == plain


# ── Ancrages en forme close (spec §4bis), seuils et égalités ─────────

def _at(p, x, wg=0.0, owner=CubeOwner.CENTRED):
    return decide(evaluation(p, wg), owner, x, jacoby=False, beaver=True).beaver


@pytest.mark.parametrize("p, beaver, raccoon", [
    (0.25, True, False),
    (0.5 - 1 / 64, True, False),
    (0.5, False, False),            # e = 0 : tout est nul, l'égalité est une prise
    (0.5 + 1 / 64, False, True),
    (0.75, False, True),
])
def test_dead_cube_gammonless_thresholds(p, beaver, raccoon):
    got = _at(p, 0.0)
    e = 2 * p - 1
    assert (got.beaver, got.raccoon) == (beaver, raccoon)
    assert got.equity_take == pytest.approx(2 * e, abs=1e-12)
    assert got.equity_beaver == pytest.approx(8 * e if raccoon else 4 * e, abs=1e-12)


def test_dead_cube_gammonless_verdicts_match_the_plain_ones():
    """À x = 0, un double n'est juste que si e > 0, et alors personne ne beave."""
    assert _at(0.25, 0.0).action == CubeAction.NO_DOUBLE
    assert _at(0.5, 0.0).action == CubeAction.NO_DOUBLE
    assert _at(0.625, 0.0).action == CubeAction.DOUBLE_TAKE
    assert _at(0.75 - 1 / 64, 0.0).action == CubeAction.DOUBLE_TAKE
    assert _at(0.75, 0.0).action == CubeAction.DOUBLE_PASS       # 2e = 1 : §4, E_dt ≥ E_dp


@pytest.mark.parametrize("p, beaver, raccoon", [
    (0.125, True, False),           # sous TP_live : E(adv.) = −1, le raccoon perd
    (0.1875, True, False),
    (0.25, True, True),             # entre 0,2 et 1/3 : beaver puis raccoon
    (0.3125, True, True),
    (0.34375, False, True),         # au-dessus de 1/3 : la menace du raccoon dissuade
    (0.5, False, True),
])
def test_live_cube_gammonless_thresholds(p, beaver, raccoon):
    got = _at(p, 1.0)
    theirs = -1.0 if p <= 0.2 else 2.5 * p - 1.5
    mine = 2.5 * p - 1 if p <= 0.8 else 1.0
    assert (got.beaver, got.raccoon) == (beaver, raccoon)
    assert got.equity_take == pytest.approx(2 * theirs, abs=1e-12)
    assert got.equity_beaver == pytest.approx(8 * mine if raccoon else 4 * theirs, abs=1e-12)


def test_live_cube_beaver_boundary_is_a_third():
    """8·(2,5p − 1) = 2·(2,5p − 1,5) en p = 1/3 : l'égalité est une simple prise."""
    third = Fraction(1, 3)
    assert 8 * (Fraction(5, 2) * third - 1) == 2 * (Fraction(5, 2) * third - Fraction(3, 2))
    assert _at(1 / 3 - 1e-6, 1.0).beaver
    assert not _at(1 / 3 + 1e-6, 1.0).beaver


def test_dead_cube_with_gammons_thresholds():
    """W = 2, L = 1, x = 0 : e = 3p − 1, beaver sous 1/3, raccoon au-dessus."""
    assert _at(0.25, 0.0, wg=0.25).beaver
    assert not _at(0.25, 0.0, wg=0.25).raccoon
    assert not _at(0.375, 0.0, wg=0.375).beaver
    assert _at(0.375, 0.0, wg=0.375).raccoon
    got = _at(0.25, 0.0, wg=0.25)
    assert got.equity_beaver == pytest.approx(4 * (3 * 0.25 - 1), abs=1e-12)


def test_beaver_never_makes_doubling_better():
    """Une option de plus pour l'adversaire ne rend jamais le double meilleur :
    E_double avec beaver ≤ E_double du §4."""
    for p, wg, lg, x, owner, jacoby in _cases():
        if owner == CubeOwner.OPPONENT:
            continue
        d = decide(evaluation(p, wg, lg), owner, x, jacoby=jacoby, beaver=True)
        assert d.beaver.equity_double <= d.equity_double + 1e-15


def test_opponent_owned_cube_has_nothing_to_answer():
    got = _at(0.25, 0.68, owner=CubeOwner.OPPONENT)
    assert got.action == CubeAction.NO_DOUBLE
    assert not got.beaver and not got.raccoon

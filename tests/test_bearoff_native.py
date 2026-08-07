"""Le lecteur C contre le lecteur Python — deux façons de se tromper, croisées.

Le C est ce qui tourne dans la recherche ; le Python est la référence lisible,
elle-même validée exhaustivement contre `bearoffdump`. Les deux existent, donc
les deux peuvent diverger — et une divergence ne se verrait **nulle part**,
puisque chacun rendrait un nombre parfaitement plausible pris à un endroit du
fichier. C'est exactement le mode de défaillance que ce dépôt traque, et le seul
remède est de les faire répondre ensemble.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from gammonnet.bearoff import (
    NativeBearoff,
    TwoSidedBearoff,
    bearoff_index,
)
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position

DATABASE = Path(os.environ.get(
    "GNUBG_TS_DATABASE",
    Path(__file__).resolve().parent.parent / "gnu_bearoff_database" / "gnubg_ts6x11.bd",
))

pytestmark = pytest.mark.skipif(
    not DATABASE.exists(),
    reason=f"base bilatérale absente : {DATABASE}. Voir docs/prerequis.md",
)


@pytest.fixture(scope="module")
def tables():
    with TwoSidedBearoff(DATABASE) as python_side, NativeBearoff(DATABASE) as c_side:
        yield python_side, c_side


def all_sides(points: int, chequers: int):
    def rec(remaining, left):
        if left == 0:
            yield ()
            return
        for n in range(remaining + 1):
            for rest in rec(remaining - n, left - 1):
                yield (n,) + rest
    return list(rec(chequers, points))


def race(white_points, black_points, turn=WHITE):
    points = [0] * NUM_POINTS
    for i, n in enumerate(white_points):
        points[i] = n
    for j, n in enumerate(black_points):
        points[NUM_POINTS - 1 - j] = -n
    return Position(points=tuple(points), bar=(0, 0),
                    off=(15 - sum(white_points), 15 - sum(black_points)), turn=turn)


def test_the_index_agrees_over_the_whole_domain(tables):
    """Tout le domaine, pas un échantillon : il n'y a que 12 376 cas."""
    python_side, _ = tables
    sides = all_sides(python_side.points, python_side.chequers)
    mismatched = [s for s in sides
                  if NativeBearoff.index(s, python_side.points)
                  != bearoff_index(s, python_side.points)]
    assert not mismatched, f"{len(mismatched)} indices divergent, ex. {mismatched[:3]}"


def test_the_equities_agree_on_real_positions(tables):
    """Les quatre colonnes, sur des positions tirées dans tout le domaine."""
    python_side, c_side = tables
    rng = random.Random(20260807)

    examined = 0
    while examined < 200:
        white = [rng.randrange(4) for _ in range(6)]
        black = [rng.randrange(4) for _ in range(6)]
        if not sum(white) or not sum(black):
            continue
        if sum(white) > 11 or sum(black) > 11:
            continue
        position = race(white, black, turn=WHITE if examined % 2 else BLACK)
        if not python_side.contains(position):
            continue
        examined += 1

        assert c_side.contains(position), "le C refuse ce que le Python accepte"
        mine = python_side.equity(position)
        theirs = c_side.equities(position)
        assert theirs is not None
        # Même fichier, même index, même échelle : l'accord doit être exact au
        # flottant près, pas approché.
        assert abs(mine.cubeless - theirs.cubeless) < 1e-12
        assert abs(mine.owned - theirs.owned) < 1e-12
        assert abs(mine.centered - theirs.centered) < 1e-12
        assert abs(mine.opponent_owns - theirs.opponent_owns) < 1e-12

    assert examined == 200


def test_membership_agrees_including_just_outside(tables):
    """La frontière, des deux côtés, et par les deux lecteurs."""
    python_side, c_side = tables

    for position, expected in (
        (race([11, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0]), True),
        (race([1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1]), True),
        (race([12, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0]), False),
        (race([1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0]), False),
    ):
        assert python_side.contains(position) is expected
        assert c_side.contains(position) is expected


def test_a_checker_on_the_bar_is_refused_by_both(tables):
    python_side, c_side = tables
    base = race([1, 1], [1, 1])
    on_bar = Position(points=base.points, bar=(1, 0),
                      off=(base.off[WHITE] - 1, base.off[BLACK]), turn=WHITE)
    assert not python_side.contains(on_bar)
    assert not c_side.contains(on_bar)


# ── Ce que le C ajoute : la distribution ────────────────────────────


def test_the_distribution_carries_no_gammon(tables):
    """Aucun gammon n'est possible dans le domaine de la table.

    Chaque camp y a déjà sorti au moins `15 - chequers` pions, soit quatre, et
    un gammon exige que le perdant n'en ait sorti aucun. C'est ce qui permet à
    une table d'ÉQUITÉS de nourrir une recherche qui parle en DISTRIBUTIONS.
    """
    _, c_side = tables
    rng = random.Random(3)

    examined = 0
    while examined < 60:
        white = [rng.randrange(3) for _ in range(6)]
        black = [rng.randrange(3) for _ in range(6)]
        if not sum(white) or not sum(black):
            continue
        position = race(white, black)
        probs = c_side.probs(position)
        if probs is None:
            continue
        examined += 1

        win, wg, wbg, lg, lbg = probs
        assert 0.0 <= win <= 1.0
        assert (wg, wbg, lg, lbg) == (0.0, 0.0, 0.0, 0.0)
    assert examined == 60


def test_the_distribution_matches_the_equity(tables):
    """`P(gain) = (équité + 1) / 2` — sans gammon, l'équité détermine tout."""
    python_side, c_side = tables
    rng = random.Random(5)

    examined = 0
    while examined < 60:
        white = [rng.randrange(3) for _ in range(6)]
        black = [rng.randrange(3) for _ in range(6)]
        if not sum(white) or not sum(black):
            continue
        position = race(white, black)
        probs = c_side.probs(position)
        if probs is None:
            continue
        examined += 1
        expected = (python_side.equity(position).cubeless + 1.0) / 2.0
        assert abs(probs[0] - expected) < 1e-6
    assert examined == 60


def test_outside_the_table_returns_nothing_rather_than_something(tables):
    """Refusé, jamais approximé — et le tampon de l'appelant reste intact."""
    _, c_side = tables
    outside = race([1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0])
    assert c_side.contains(outside) is False
    assert c_side.equities(outside) is None
    assert c_side.probs(outside) is None


def test_a_bad_file_is_refused_at_open(tmp_path):
    """Un fichier dont la taille ne suit pas son en-tête serait lu de travers
    d'un bout à l'autre, en rendant des équités plausibles."""
    fake = tmp_path / "faux.bd"
    fake.write_bytes(b"gnubg-TS-06-11-1" + b"x" * 23 + b"\n" + b"\0" * 64)
    with pytest.raises(ValueError):
        NativeBearoff(fake)

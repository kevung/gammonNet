"""T38 — la base bilatérale, et les trois façons de la lire de travers.

Un lecteur de table exacte se trompe **silencieusement** : il rend un nombre
plausible pris au mauvais endroit. Les trois erreurs possibles sont l'index,
l'échelle, et l'orientation, et chacune a ici son contrôle.

L'oracle est `bearoffdump`, l'outil livré et documenté avec GNU Backgammon. Il
est indépendant de notre lecteur : lui lit le fichier avec le code de gnubg,
nous avec le nôtre.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
from math import comb
from pathlib import Path

import pytest

from gammonnet.bearoff import TwoSidedBearoff, bearoff_index
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
def table():
    with TwoSidedBearoff(DATABASE) as live:
        yield live


def all_sides(points: int, chequers: int):
    """Toutes les répartitions d'au plus `chequers` pions sur `points` points."""
    def rec(remaining, left):
        if left == 0:
            yield ()
            return
        for n in range(remaining + 1):
            for rest in rec(remaining - n, left - 1):
                yield (n,) + rest
    return list(rec(chequers, points))


# ── L'index ─────────────────────────────────────────────────────────


def test_index_is_a_bijection_onto_the_whole_range(table):
    """Chaque position a un indice, chaque indice une position, sans trou.

    Une indexation qui laisserait un trou ou un doublon lirait une entrée pour
    une autre, sans jamais sortir du fichier — donc sans jamais lever.
    """
    sides = all_sides(table.points, table.chequers)
    assert len(sides) == comb(table.points + table.chequers, table.points)

    indices = [bearoff_index(side, table.points) for side in sides]
    assert sorted(indices) == list(range(len(sides)))


def test_index_matches_the_documented_ordering(table):
    """Les premiers indices, tels que GNU Backgammon les numérote."""
    assert bearoff_index((0, 0, 0, 0, 0, 0), 6) == 0
    assert bearoff_index((1, 0, 0, 0, 0, 0), 6) == 1
    assert bearoff_index((0, 1, 0, 0, 0, 0), 6) == 2
    assert bearoff_index((0, 0, 0, 0, 0, 1), 6) == 6
    assert bearoff_index((2, 0, 0, 0, 0, 0), 6) == 7
    assert bearoff_index((0, 0, 0, 0, 0, 11), 6) == 12375


# ── L'échelle et le fichier ─────────────────────────────────────────


def test_header_is_read_rather_than_assumed(table):
    assert (table.points, table.chequers) == (6, 11)
    assert table.positions == 12376
    # 40 octets d'en-tête + 12376^2 x 8 : la taille du fichier confirme la
    # structure, elle n'est pas supposée.
    assert DATABASE.stat().st_size == 40 + table.positions ** 2 * 8


@pytest.mark.skipif(shutil.which("bearoffdump") is None,
                    reason="bearoffdump absent")
def test_agrees_with_bearoffdump(table):
    """LE contrôle : notre lecteur contre celui de GNU Backgammon.

    Sur un échantillon tiré au hasard dans tout le domaine. Un désaccord ici
    dénonce l'index ou l'échelle, et aucun des deux ne se voit autrement.
    """
    rng = random.Random(20260806)
    worst = 0.0

    for _ in range(40):
        player = rng.randrange(table.positions)
        opponent = rng.randrange(table.positions)
        index = player * table.positions + opponent

        output = subprocess.run(
            ["bearoffdump", "-n", str(index), str(DATABASE)],
            capture_output=True, text=True, timeout=120,
        ).stdout

        expected = {}
        for line in output.splitlines():
            for key, label in (("cubeless", "Cubeless equity"),
                               ("owned", "Owned cube"),
                               ("centered", "Centered cube"),
                               ("opponent_owns", "Opponent owns cube")):
                if line.strip().startswith(label):
                    expected[key] = float(line.split(":")[1])

        assert len(expected) == 4, f"dump illisible pour l'index {index}"

        raw = table.raw(player, opponent)
        ours = {
            key: value / 65535.0 * 2.0 - 1.0
            for key, value in zip(
                ("cubeless", "owned", "centered", "opponent_owns"), raw)
        }
        for key, value in expected.items():
            # `bearoffdump` imprime quatre décimales ; l'écart admis est celui
            # de son arrondi, pas un seuil choisi pour faire passer le test.
            worst = max(worst, abs(ours[key] - value))
            assert abs(ours[key] - value) <= 5e-5, (
                f"index {index}, {key} : nous {ours[key]:+.6f}, "
                f"bearoffdump {value:+.4f}"
            )

    assert worst < 5e-5


# ── L'orientation ───────────────────────────────────────────────────


def race(white_points, black_points, turn=WHITE, white_off=None, black_off=None):
    """Une position de course : chacun ses pions sur ses premiers points."""
    points = [0] * NUM_POINTS
    for i, n in enumerate(white_points):
        points[i] = n
    for j, n in enumerate(black_points):
        points[NUM_POINTS - 1 - j] = -n
    off_w = 15 - sum(white_points) if white_off is None else white_off
    off_b = 15 - sum(black_points) if black_off is None else black_off
    return Position(points=tuple(points), bar=(0, 0), off=(off_w, off_b), turn=turn)


def test_a_won_race_is_worth_one(table):
    """Un pion à sortir, un jet à jouer, l'adversaire loin : l'équité vaut +1.

    Le contrôle le plus simple qui distingue une orientation juste d'une
    orientation inversée — laquelle rendrait -1 sans rien signaler.
    """
    position = race([1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 5], turn=WHITE)
    assert table.contains(position)
    assert table.equity(position).cubeless == pytest.approx(1.0, abs=1e-4)


def test_the_mirror_position_reads_the_same_entry(table):
    """La même position vue de l'autre côté doit donner la même équité.

    Miroiter les pions ET le trait décrit exactement la même partie. Une
    orientation qui se tromperait donnerait deux nombres différents pour une
    seule réalité.
    """
    rng = random.Random(11)
    for _ in range(30):
        white = [rng.randrange(4) for _ in range(6)]
        black = [rng.randrange(4) for _ in range(6)]
        if sum(white) == 0 or sum(black) == 0:
            continue
        if sum(white) > 11 or sum(black) > 11:
            continue

        direct = race(white, black, turn=WHITE)
        mirrored = race(black, white, turn=BLACK)

        assert table.contains(direct) and table.contains(mirrored)
        assert table.equity(direct).cubeless == pytest.approx(
            table.equity(mirrored).cubeless, abs=1e-9)


# ── L'appartenance : un prédicat, jamais une supposition ────────────


def test_membership_is_tested_at_the_boundary(table):
    """Juste dedans, juste dehors, et la frontière est vérifiée des deux côtés."""
    inside = race([11, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0])
    assert table.contains(inside)

    too_many = race([12, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0])
    assert not table.contains(too_many), "12 pions dépassent la table 6x11"

    too_far = race([1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0])
    assert not table.contains(too_far), "un pion au 7e point sort du domaine"


def test_a_checker_on_the_bar_is_outside(table):
    position = race([1, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0])
    on_bar = Position(points=position.points, bar=(1, 0),
                      off=(position.off[WHITE] - 1, position.off[BLACK]),
                      turn=WHITE)
    assert not table.contains(on_bar)


def test_outside_the_table_raises_rather_than_approximating(table):
    """Refusé, jamais approximé.

    C'est la règle de `CLAUDE.md` appliquée littéralement. Une valeur voisine
    rendue en silence pour une position hors table serait une équité plausible
    et fausse — précisément le mode de défaillance que ce dépôt traque.
    """
    outside = race([1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0])
    with pytest.raises(KeyError):
        table.equity(outside)

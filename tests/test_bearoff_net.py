"""T78 — le réseau distillé : son domaine, ses poids, et les deux façons de mentir.

Le réseau distillé remplace une table de 1,2 Gio par 81 Kio de poids. Il hérite
donc du mode de défaillance des tables — rendre un nombre plausible pris au
mauvais endroit — sans hériter du fichier qui permettrait de le vérifier à
l'exécution. Deux contrôles, ici, l'un pour chaque façon de se tromper :

* **le domaine.** `bearoff_net.contains` et `bearoff_net.position_sides` sont
  une seconde écriture de ce que `bearoff.TwoSidedBearoff` sait déjà faire —
  écrite exprès, pour que l'inférence ne dépende pas du fichier de 1,2 Gio. Deux
  écritures peuvent diverger, et une divergence ne se verrait nulle part : le
  réseau répondrait pour une position retournée, ou refuserait d'en connaître
  une qu'il connaît. Les deux sont donc croisées ici, sur des positions tirées
  au hasard.
* **les poids.** Un fichier relu doit rendre exactement les mêmes sorties, au
  bit près, et une version de caractéristiques qui ne correspond pas doit lever
  plutôt que d'être réinterprétée.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import pytest

from gammonnet.bearoff import TwoSidedBearoff
from gammonnet.bearoff_net import (
    CHEQUERS, FEATURE_VERSION, INPUT_SIZE, POINTS, SIDE_FEATURES, BearoffNet,
    contains, position_sides, side_features,
)
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position

DATABASE = Path(os.environ.get(
    "GNUBG_TS_DATABASE",
    Path(__file__).resolve().parent.parent / "gnu_bearoff_database" / "gnubg_ts6x11.bd",
))


@pytest.fixture(scope="module")
def net() -> BearoffNet:
    """Un réseau aux poids arbitraires : ce qui est testé ici est la plomberie."""
    rng = np.random.default_rng(20260828)
    layers = [
        (rng.normal(size=(INPUT_SIZE, 16)).astype(np.float32) * 0.1,
         rng.normal(size=16).astype(np.float32) * 0.1),
        (rng.normal(size=(16, 1)).astype(np.float32) * 0.1,
         rng.normal(size=1).astype(np.float32) * 0.1),
    ]
    return BearoffNet(layers)


def random_position(rng: random.Random, max_point: int, chequers: int) -> Position:
    """Une position quelconque, dans ou hors du domaine selon `max_point`."""
    points = [0] * NUM_POINTS
    for player in (WHITE, BLACK):
        for _ in range(rng.randint(1, chequers)):
            point = rng.randrange(max_point)
            if player == WHITE:
                points[point] += 1
            else:
                points[NUM_POINTS - 1 - point] -= 1
    white = sum(n for n in points if n > 0)
    black = -sum(n for n in points if n < 0)
    return Position(points=tuple(points), bar=(0, 0),
                    off=(15 - white, 15 - black), turn=WHITE)


def test_features_have_the_declared_width():
    features = side_features(np.array([[2, 1, 0, 0, 3, 0], [0, 0, 0, 0, 0, 0]]))
    assert features.shape == (2, SIDE_FEATURES)
    assert features.dtype == np.float32


def test_weights_survive_a_round_trip(net, tmp_path):
    mine = np.array([[2, 1, 0, 0, 3, 0], [1, 0, 0, 0, 0, 0]])
    theirs = np.array([[1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 2, 0]])
    before = net.equities_from_counts(mine, theirs)

    path = tmp_path / "net.bin"
    net.save(path)
    after = BearoffNet.load(path).equities_from_counts(mine, theirs)

    # Au bit près : un aller-retour qui « arrondit » rendrait les mesures
    # publiées inapplicables aux poids publiés.
    assert np.array_equal(before, after)


def test_a_foreign_feature_version_is_refused(net):
    with pytest.raises(ValueError):
        BearoffNet(net.layers, feature_version=FEATURE_VERSION + 1)


def test_a_batch_agrees_with_itself(net):
    """Un lot et des appels unitaires donnent la même chose — **à l'epsilon près**.

    Et pas au bit près : `numpy` délègue le produit matriciel à un BLAS qui
    change d'ordre d'accumulation avec la forme du lot. L'écart mesuré est de
    l'ordre de 1e-8, sans effet sur un classement de coups dont les écarts
    utiles sont mille fois plus grands — mais il est réel, et c'est pourquoi le
    banc évalue les candidats d'une décision **en un seul lot** : le
    classement reste alors invariant par construction plutôt que par chance.

    La garantie bit-à-bit du projet porte sur le chemin C (natif contre
    WebAssembly), pas sur ce chemin numpy, qui sert à mesurer et à entraîner.
    """
    mine = np.array([[2, 1, 0, 0, 3, 0], [1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 1]])
    theirs = np.array([[1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 2, 0], [3, 0, 0, 0, 0, 0]])
    batch = net.equities_from_counts(mine, theirs)
    one_by_one = np.array([
        net.equities_from_counts(mine[i:i + 1], theirs[i:i + 1])[0]
        for i in range(mine.shape[0])
    ])
    assert np.allclose(batch, one_by_one, rtol=0.0, atol=1e-6)


def test_the_bar_and_the_outfield_are_outside_the_domain(net):
    rng = random.Random(7)
    outside = random_position(rng, max_point=NUM_POINTS, chequers=CHEQUERS)
    # Un pion hors du jan intérieur suffit ; s'il n'y en a pas, on en met un.
    points = list(outside.points)
    points[10] += 1
    outside = Position(points=tuple(points), bar=outside.bar,
                       off=(outside.off[0] - 1, outside.off[1]), turn=WHITE)
    assert not contains(outside)
    with pytest.raises(KeyError):
        net.equity(outside)

    inside = random_position(random.Random(3), max_point=POINTS, chequers=CHEQUERS)
    on_bar = Position(points=inside.points, bar=(1, 0),
                      off=(inside.off[0] - 1, inside.off[1]), turn=WHITE)
    assert not contains(on_bar)


@pytest.mark.skipif(not DATABASE.exists(),
                    reason=f"base bilatérale absente : {DATABASE}")
def test_the_domain_is_the_table_s_domain():
    """Le prédicat et la décomposition, croisés contre le lecteur de T38.

    Les deux tirages comptent : des positions du domaine, pour vérifier que le
    réseau ne refuse pas ce qu'il connaît, et des positions plus larges, pour
    vérifier qu'il ne répond pas pour ce qu'il ignore.
    """
    rng = random.Random(20260828)
    with TwoSidedBearoff(DATABASE) as table:
        for max_point in (POINTS, 8, NUM_POINTS):
            for _ in range(400):
                position = random_position(rng, max_point, CHEQUERS + 2)
                assert contains(position) == table.contains(position)
                if not contains(position):
                    continue
                mine, theirs = position_sides(position)
                reference = table._sides(position)
                assert (mine, theirs) == (reference[0], reference[1])

"""La capacité du générateur de coups : une borne prouvée, pas observée.

Une fois joués les k sous-coups d'un doublet, la position atteinte -- coups
frappants compris, puisqu'un pion touche chaque point qu'il traverse -- ne
dépend que du multiensemble des couples (point de départ, nombre de pas) des
pions joués. Des pions qui partagent un point sont interchangeables : un point
qui porte n pions contribue les partitions de sa part des k pas en au plus n
parts. Le compte, pour une répartition des quinze pions, est donc le coefficient
de x^k du produit de ces séries génératrices ; où sont les points n'y change
rien, seule compte la partition de 15.

Ce fichier recalcule ce maximum sur toutes les partitions de 15 et vérifie que
les capacités du C le couvrent, puis montre une position réelle au-delà de
l'ancienne capacité.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

from gammonnet import WHITE, Position
from gammonnet.rules import MAX_MOVES_PER_PLAY, MAX_PLAYS, NUM_CHECKERS

SRC = Path(__file__).resolve().parent.parent / "src"


def c_constant(path: Path, name: str) -> int:
    match = re.search(rf"^#define\s+{name}\s+(\d+)\b", path.read_text(), re.MULTILINE)
    assert match, f"{name} introuvable dans {path}"
    return int(match.group(1))


@lru_cache(maxsize=None)
def partitions_at_most(j: int, parts: int, largest: int) -> int:
    """Partitions de j en au plus `parts` parts, aucune plus grande que `largest`."""
    if j == 0:
        return 1
    if parts == 0 or largest == 0:
        return 0
    return sum(partitions_at_most(j - p, parts - 1, p) for p in range(min(j, largest), 0, -1))


def trajectory_bound(k: int) -> int:
    """Le plus grand nombre de positions distinctes après k sous-coups d'un même dé."""
    best = 0

    def walk(left: int, largest: int, poly: list[int]) -> None:
        nonlocal best
        if left == 0:
            best = max(best, poly[k])
            return
        for n in range(min(left, largest), 0, -1):
            factor = [partitions_at_most(j, n, j) for j in range(k + 1)]
            nxt = [0] * (k + 1)
            for a in range(k + 1):
                for b in range(k + 1 - a):
                    nxt[a + b] += poly[a] * factor[b]
            walk(left - n, n, nxt)

    walk(NUM_CHECKERS, NUM_CHECKERS, [1] + [0] * k)
    return best


def test_trajectory_bound_is_the_binomial():
    """C(k+14, k) : 1, 15, 120, 680, 3060 -- atteint avec quinze pions isolés."""
    assert [trajectory_bound(k) for k in range(MAX_MOVES_PER_PLAY + 1)] == [1, 15, 120, 680, 3060]


def test_capacities_cover_the_proven_bound():
    """Les tampons couvrent la borne, sur toutes les répartitions des quinze pions.

    Deux bornes, parce que le moteur de règles en a deux usages :
      * la liste RENDUE ne garde que les coups qui jouent le plus de dés, donc
        au plus le maximum à profondeur 4 ;
      * le tampon de TRAVAIL du moteur reçoit aussi les nœuds terminaux plus
        courts, avant leur filtrage : il doit tenir toutes les profondeurs.
    """
    deepest = trajectory_bound(MAX_MOVES_PER_PLAY)
    every_depth = sum(trajectory_bound(k) for k in range(MAX_MOVES_PER_PLAY + 1))

    gn_max_plays = c_constant(SRC / "gn_rules.h", "GN_MAX_PLAYS")
    backend_plays = c_constant(SRC / "gn_rules_reference.c", "BACKEND_MAX_PLAYS")

    assert gn_max_plays >= deepest
    assert MAX_PLAYS == gn_max_plays, "la liaison Python doit répéter la constante du C"
    assert backend_plays >= every_depth


# Quinze pions blancs isolés, quatre blancs noirs touchables, onze noirs sortis.
WIDEST_DOUBLE = Position(
    points=(-1, -1, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, -1, 1, 1, 1, -1, 1, 1, 0, 1, 1),
    bar=(0, 0),
    off=(0, 11),
    turn=WHITE,
)


def test_a_double_with_more_than_2048_distinct_plays():
    """Sur 1-1, les coups frappants séparent des coups qui sinon coïncideraient.

    La position dépasse 2048 coups distincts : la génération doit les rendre
    tous, et ce sont exactement ceux de GNU Backgammon.
    """
    assert WIDEST_DOUBLE.is_valid()
    plays = WIDEST_DOUBLE.legal_plays(1, 1)

    assert len(plays) > 2048
    assert len({play.result for play in plays}) == len(plays)

    gnubg_nn = pytest.importorskip("gnubg_nn", reason="gnubg-nn absent — lancer `make venv`")
    from gammonnet import gnubg_board as gb

    ours = {gb.key(play.result, on_roll=WIDEST_DOUBLE.turn) for play in plays}
    theirs = set(gnubg_nn.moves(gb.to_gnubg(WIDEST_DOUBLE), 1, 1, 0))
    assert ours == theirs

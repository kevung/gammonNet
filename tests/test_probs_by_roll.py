"""Le backup par jet : la moyenne des 21 est la distribution, au bit près.

`gn_search_probs_by_roll` n'existe que parce que la boucle racine de
`gn_search_probs` forme déjà ces 21 vecteurs avant de les moyenner. Cette
justification n'a de valeur que si la moyenne redonne exactement la
distribution — sinon la nouvelle sortie décrit un autre calcul, et la
volatilité qu'on en tire ne serait pas celle de la recherche qui joue.

C'est cette identité qui est tenue ici, pas supposée.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from gammonnet.arena import BLACK, opening_roll
from gammonnet.infer import Network
from gammonnet.rules import Position
from gammonnet.search import (
    NUM_ROLLS,
    SearchConfig,
    position_probs,
    probs_by_roll,
    search_plays,
)

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"

#: float32 de bout en bout : l'écart admissible est celui de l'accumulation,
#: pas une tolérance de confort. Mesuré à ~3e-08 sur les positions du banc.
TOLERANCE = 1e-6


pytestmark = pytest.mark.skipif(not MODEL.exists(),
                                reason="poids absents (models/ est gitignoré)")


@pytest.fixture(scope="module")
def network():
    return Network.load(str(MODEL))


def walked(network, seed: int, plies: int) -> Position:
    """Une position de milieu de partie, atteinte par le moteur lui-même."""
    rng = random.Random(seed)
    position = Position.initial()
    first, d1, d2 = opening_roll(rng)
    if first == BLACK:
        position = position.swapped_turn()
    for _ in range(plies):
        if position.is_over():
            break
        ranked = search_plays(network, position, d1, d2, SearchConfig(ply=0))
        if ranked:
            position = ranked[0].play.result
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    return position


@pytest.mark.parametrize("seed", [3, 11, 29])
@pytest.mark.parametrize("ply", [1, 2])
def test_the_weighted_mean_of_the_rolls_is_the_distribution(network, seed, ply):
    position = walked(network, seed, 8)
    config = SearchConfig(ply=ply)

    rolls, weights = probs_by_roll(network, position, config)
    expected = position_probs(network, position, config)

    assert len(rolls) == NUM_ROLLS
    assert sum(weights) == pytest.approx(1.0, abs=1e-12)
    for index in range(5):
        mean = sum(weights[r] * rolls[r].as_tuple()[index]
                   for r in range(NUM_ROLLS))
        assert mean == pytest.approx(expected.as_tuple()[index], abs=TOLERANCE)


def test_the_weights_are_the_dice_and_nothing_else(network):
    """1/36 pour un double, 2/36 sinon — 21 jets, pas 36."""
    position = walked(network, 5, 6)
    _, weights = probs_by_roll(network, position, SearchConfig(ply=1))

    doubles = [w for w in weights if w == pytest.approx(1.0 / 36.0)]
    others = [w for w in weights if w == pytest.approx(2.0 / 36.0)]
    assert len(doubles) == 6
    assert len(others) == 15


def test_a_pruned_search_keeps_the_identity(network):
    """L'élagage change ce que la recherche joue, jamais l'identité."""
    if not PRUNE.exists():
        pytest.skip("réseau d'élagage absent")
    small = Network.load(str(PRUNE))
    position = walked(network, 17, 10)
    config = SearchConfig(ply=2, prune_net=small, prune_k=12)

    rolls, weights = probs_by_roll(network, position, config)
    expected = position_probs(network, position, config)
    for index in range(5):
        mean = sum(weights[r] * rolls[r].as_tuple()[index]
                   for r in range(NUM_ROLLS))
        assert mean == pytest.approx(expected.as_tuple()[index], abs=TOLERANCE)


def test_zero_ply_is_refused_rather_than_answered(network):
    """Sans jet énuméré il n'y a pas de dispersion — et zéro serait un mensonge."""
    position = walked(network, 2, 4)
    with pytest.raises(ValueError):
        probs_by_roll(network, position, SearchConfig(ply=0))


def test_a_finished_game_is_refused(network):
    """Une partie finie se calcule, elle ne s'évalue pas (règle 2)."""
    position = walked(network, 4242, 300)
    if not position.is_over():
        pytest.skip("la marche n'a pas atteint une fin de partie")
    with pytest.raises(ValueError):
        probs_by_roll(network, position, SearchConfig(ply=1))

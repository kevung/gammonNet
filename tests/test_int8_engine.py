"""T73 — `Int8NetworkEngine` : le chemin int8 réel, capable de JOUER.

`tools/measure_qat_decision_loss.py` mesure déjà la qualité du chemin int8
sur des décisions isolées. Ce fichier vérifie l'autre moitié : que
`Int8NetworkEngine` est un `Engine` au sens du protocole d'`arena.py` — il
choisit toujours un coup légal, il se laisse piqueler pour les ouvriers d'un
round-robin, et il termine des parties complètes sans lever.

Ce n'est PAS un test de force. Aucune conclusion de niveau de jeu n'est
tirée ici — seulement que l'engin fonctionne comme un `Engine`.
"""

from __future__ import annotations

import pickle
import random
from pathlib import Path

import pytest

from gammonnet import Position
from gammonnet.arena import (
    Int8NetworkEngine,
    RandomEngine,
    derive_seed,
    play_game,
    play_pair,
)

MODEL = Path(__file__).resolve().parent.parent / "models" / "qat_int8.bin"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(),
    reason=f"{MODEL.name} absent — `python tools/export_qat_int8.py`")


def walk(count: int, seed: int) -> list[tuple[Position, int, int]]:
    rng = random.Random(seed)
    out = []
    position = Position.initial()
    while len(out) < count:
        if position.is_over():
            position = Position.initial()
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        out.append((position, d1, d2))
        plays = position.legal_plays(d1, d2)
        position = rng.choice(plays).result if plays else position.swapped_turn()
    return out


@pytest.fixture(scope="module")
def engine() -> Int8NetworkEngine:
    return Int8NetworkEngine()


def test_it_always_chooses_a_legal_play(engine):
    rng = random.Random(1)
    for position, d1, d2 in walk(150, seed=20260831):
        plays = position.legal_plays(d1, d2)
        chosen = engine.choose(position, d1, d2, rng)
        if not plays:
            assert chosen is None
        else:
            assert chosen in plays


def test_it_is_picklable_before_loading():
    """A round-robin ships engines to worker processes; a loaded network is
    a live ctypes handle into THIS process and would not survive that trip
    -- the same reason `NetworkEngine`/`SearchEngine` load lazily. Pickling
    before first use, and unpickling into a fresh, still-unloaded copy, is
    the property that makes that safe."""
    engine = Int8NetworkEngine()
    clone = pickle.loads(pickle.dumps(engine))
    assert clone._network is None
    assert clone.name == engine.name
    rng = random.Random(1)
    position = Position.initial()
    d1, d2 = 3, 1
    assert clone.choose(position, d1, d2, rng) in position.legal_plays(d1, d2)


def test_it_plays_complete_games_against_a_random_opponent(engine):
    """No crash, no illegal state, over several full games -- the
    integration test that a unit-level 'returns a legal play' cannot give:
    a whole game is many decisions in a row, each depending on the last."""
    opponent = RandomEngine()
    for index in range(3):
        seed = derive_seed(20260831, "int8-vs-random", index)
        dice = random.Random(seed)
        white_rng = random.Random(seed ^ 1)
        black_rng = random.Random(seed ^ 2)
        result = play_game(engine, opponent, dice, white_rng, black_rng)
        assert isinstance(result.points, int)
        assert not result.stalled


def test_a_duplicate_pair_runs_end_to_end(engine):
    """`play_pair` is the harness `bench/measure_pr_t30.py`-style tools
    actually use -- confirming it accepts this engine is what makes
    `Int8NetworkEngine` usable there, not just constructible."""
    opponent = RandomEngine()
    result = play_pair(engine, opponent, pairs=2, base_seed=20260831)
    assert result.pairs == 2
    assert result.games == 4

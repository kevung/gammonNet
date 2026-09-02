"""T73 — le format `BGQ8` chargé et exécuté NATIVEMENT (`gn_network_load`,
`gn_evaluate_batch`), pas seulement via `Int8Network` (ctypes orchestré
depuis Python).

`GnNetwork` était une seule forme (`NNModel`, float32/fp16) derrière un type
opaque — exactement le design que `gn_infer.h` revendiquait déjà (« the
backend is deliberately invisible here »). Ce fichier vérifie que le second
format tient CETTE promesse : tout ce qui appelle `Network.load` — y compris
`gn_search.c`, sans qu'il ait besoin de savoir qu'un second format existe —
fonctionne sans changement.

Le test qui compte n'est pas « ça charge » : c'est que ce chemin natif rend
EXACTEMENT ce que `Int8Network` (déjà vérifié contre la simulation PyTorch
de la QAT, `test_infer_int8.py`) rend — sinon l'un des deux ment sur ce que
le noyau calcule réellement.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.arena import SearchEngine  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.infer_int8 import Int8Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

MODEL = ROOT / "models" / "qat_int8.bin"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(),
    reason=f"{MODEL.name} absent — `python tools/export_qat_int8.py`")


def walk(count: int, seed: int) -> list[Position]:
    rng = random.Random(seed)
    out: list[Position] = []
    position = Position.initial()
    while len(out) < count:
        if position.is_over():
            position = Position.initial()
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if plays:
            out.append(position)
            position = rng.choice(plays).result
        else:
            position = position.swapped_turn()
    return out


def test_gn_network_load_recognises_the_bgq8_format():
    net = Network.load(MODEL)
    try:
        assert net.input_size == 196
    finally:
        net.close()


def test_evaluate_features_matches_int8network_single():
    """`gn_evaluate` / `gn_evaluate_features`, the single-position door."""
    native = Network.load(MODEL)
    python_side = Int8Network.load(MODEL)
    try:
        for position in walk(30, seed=1):
            features = codec.encode(position)
            a = native.evaluate_features(features).as_tuple()
            b = python_side.forward(features)
            assert max(abs(x - y) for x, y in zip(a, b)) < 1e-5
    finally:
        native.close()


@pytest.mark.parametrize("count", [1, 5, 31, 32, 33, 65, 100])
def test_evaluate_batch_matches_int8network_across_chunk_boundaries(count):
    """The regression this guards against (2026-08-31): the scratch buffers
    inside `gn_int8_model_evaluate` were sized by the LAST hidden layer's
    width instead of the widest one, and the feature-major stride used the
    allocated chunk width instead of the actual chunk size -- both silent
    at count=1 or exactly 32, both a heap overflow (caught by
    AddressSanitizer) as soon as a layer was WIDER than the last, or a
    chunk was NARROWER than 32. `count` sweeps both a single position, a
    lone final partial chunk (33, 65), and the exact boundary (31, 32) on
    purpose.
    """
    native = Network.load(MODEL)
    python_side = Int8Network.load(MODEL)
    try:
        positions = walk(count, seed=count)
        native_out = native.evaluate_batch(positions)
        python_out = python_side.forward_batch(
            [codec.encode(p) for p in positions])
        for a_eval, b in zip(native_out, python_out):
            a = a_eval.as_tuple()
            assert max(abs(x - y) for x, y in zip(a, b)) < 1e-5
    finally:
        native.close()


def test_search_engine_runs_a_real_search_over_the_int8_model():
    """`gn_search.c` never learned int8 exists -- it only ever calls
    `gn_evaluate_batch` through the opaque `GnNetwork*`. This is the payoff
    of that design: a 1-ply search over an int8 model needs zero lines
    changed in the search engine itself. Not a force claim -- only that the
    search runs, refuses nothing, and returns one of the legal plays."""
    engine = SearchEngine(ply=1, model=str(MODEL), name="int8-1ply-test")
    rng = random.Random(7)
    for position in walk(5, seed=2):
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        chosen = engine.choose(position, d1, d2, rng)
        if plays:
            assert chosen in plays
        else:
            assert chosen is None

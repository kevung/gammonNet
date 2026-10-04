"""Shared plumbing of the training pipelines' smoke mode.

A smoke run proves that a pipeline goes end to end and leaves a readable
artefact. It proves nothing about strength: the labeller here is a randomly
initialised network, so every label is plausible and meaningless. Nothing that
comes out of a smoke run may be measured, published, or compared.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

INPUT_SIZE = 196
NUM_OUTPUTS = 5


def write_random_network(path: Path, hidden: list[int], seed: int) -> Path:
    """A He-initialised prob5 network in the engine's flat format."""
    from quantize_model import write_model

    rng = np.random.default_rng(seed)
    sizes = [INPUT_SIZE] + list(hidden) + [NUM_OUTPUTS]
    layers = []
    for index in range(len(sizes) - 1):
        scale = (2.0 / sizes[index]) ** 0.5
        layers.append((
            (rng.standard_normal((sizes[index + 1], sizes[index])) * scale
             ).astype(np.float32),
            np.zeros(sizes[index + 1], dtype=np.float32)))
    path.parent.mkdir(parents=True, exist_ok=True)
    write_model(path, {
        "num_hidden": len(hidden), "input_size": INPUT_SIZE,
        "activation": 0, "output_mode": 2, "hidden": list(hidden),
        "layers": layers,
    })
    return path


def walk(network, seed: int, max_plies: int = 300):
    """Endless stream of `(position, d1, d2)` from 0-ply self-play games."""
    from gammonnet.arena import BLACK, opening_roll
    from gammonnet.rules import Position
    from gammonnet.search import SearchConfig, search_plays

    rng = random.Random(seed)
    while True:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()
        for _ in range(max_plies):
            if position.is_over():
                break
            yield position, d1, d2
            plays = position.legal_plays(d1, d2)
            if plays:
                position = search_plays(network, position, d1, d2,
                                        SearchConfig(ply=0))[0].play.result
            else:
                position = position.swapped_turn()
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)

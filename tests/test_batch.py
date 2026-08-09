"""T35 — le lot d'inférence : les identités qui l'autorisent.

`gn_evaluate_batch` réordonne QUELLE position une ligne de poids multiplie
ensuite, jamais l'ordre de la somme d'une position donnée. Ce que ça promet,
et ce que ce fichier tient :

* **Invariance au découpage** : évaluer N positions en un lot ou une par une
  par le même chemin de lot rend les MÊMES bits. C'est l'invariant fort — s'il
  casse, le résultat d'une recherche dépendrait du nombre de coups frères.
* **Accord avec le scalaire** : identique au bit près sur le build par défaut
  (mêmes opérations, même ordre) ; sous `NATIVE_FP=1`, les deux chemins sont
  réassociés par le compilateur chacun à sa façon et l'écart est du bruit de
  réassociation, borné comme celui du test de régression (1e-6).

Le corpus est un vrai échantillon de parties (graine figée), pas la seule
position initiale : un noyau qui ne se trompe que sur les positions
asymétriques passerait un test trop poli.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="modèle absent")


def corpus(count: int = 192, seed: int = 20260810) -> list[Position]:
    """Des positions de vraies parties : jeux aléatoires depuis l'ouverture."""
    rng = random.Random(seed)
    positions: list[Position] = []
    position = Position.initial()
    while len(positions) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
            continue
        positions.append(position)
    return positions


@needs_model
def test_the_batch_is_invariant_to_how_it_is_chunked():
    network = Network.load(MODEL)
    positions = corpus()

    together = network.evaluate_batch(positions)
    alone = [network.evaluate_batch([p])[0] for p in positions]
    assert together == alone  # bit à bit : Evaluation est un tuple de floats

    # Un découpage qui ne tombe pas sur la taille du noyau, pour exercer les
    # restes de lot.
    ragged = []
    step = 7
    for base in range(0, len(positions), step):
        ragged.extend(network.evaluate_batch(positions[base:base + step]))
    assert ragged == together


@needs_model
def test_the_batch_agrees_with_the_scalar_path():
    network = Network.load(MODEL)
    positions = corpus()

    batched = network.evaluate_batch(positions)
    worst = 0.0
    for position, batch_eval in zip(positions, batched):
        scalar = network.evaluate(position)
        for a, b in zip(batch_eval.as_tuple(), scalar.as_tuple()):
            worst = max(worst, abs(a - b))

    # 0 attendu sur le build par défaut ; 1e-6 couvre la réassociation de
    # NATIVE_FP=1, comme dans tests/test_regression.py.
    assert worst <= 1e-6, f"max|Δ| lot-scalaire = {worst:.3e}"


@needs_model
def test_the_empty_batch_is_a_no_op():
    network = Network.load(MODEL)
    assert network.evaluate_batch([]) == []

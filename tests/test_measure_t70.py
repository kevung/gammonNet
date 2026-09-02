"""T70 — la lecture du registre : pondération, hors-corpus, bootstrap.

Ces trois mécanismes décident du chiffre que la phase 7 publiera, et aucun des
trois ne se voit échouer : une pondération inversée, un hors-corpus compté zéro
ou un bootstrap qui tire les coups au lieu des positions rendent tous un nombre
parfaitement présentable. D'où des registres écrits à la main, dont on connaît
la réponse à l'avance.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from measure_t70 import HORS_CORPUS_ALARM, weighted_bootstrap  # noqa: E402


def test_a_flat_weighting_is_the_plain_mean():
    losses = [0.010, 0.020, 0.030, 0.040]
    mean, low, high = weighted_bootstrap(losses, [1.0] * 4, 2000, 1)
    assert mean == pytest.approx(0.025)
    assert low < mean < high


def test_the_weight_is_what_undoes_the_stratification():
    """Le cas qui compte : une strate rare, sur-représentée dans le corpus.

    Deux décisions à 0,10 de perte (une classe rare, poids 0,1) et deux à 0,00
    (une classe fréquente, poids 1,9). La moyenne brute dirait 0,05 ; la
    fréquence réelle dit 0,005. Un facteur dix, invisible sans le poids.
    """
    losses = [0.10, 0.10, 0.00, 0.00]
    weights = [0.1, 0.1, 1.9, 1.9]
    mean, _low, _high = weighted_bootstrap(losses, weights, 2000, 1)
    assert mean == pytest.approx(0.005)
    naive = sum(losses) / len(losses)
    assert naive == pytest.approx(0.05)


def test_the_interval_tightens_as_decisions_accumulate():
    import random

    rng = random.Random(3)
    small = [rng.gauss(0.02, 0.01) for _ in range(50)]
    large = [rng.gauss(0.02, 0.01) for _ in range(5000)]
    _m1, lo1, hi1 = weighted_bootstrap(small, [1.0] * len(small), 2000, 7)
    _m2, lo2, hi2 = weighted_bootstrap(large, [1.0] * len(large), 2000, 7)
    assert (hi2 - lo2) < (hi1 - lo1) / 5


def test_an_empty_registry_is_zero_and_not_a_crash():
    assert weighted_bootstrap([], [], 100, 1) == (0.0, 0.0, 0.0)


def test_the_bootstrap_is_reproducible():
    losses = [0.01, 0.02, 0.03, 0.04, 0.05]
    first = weighted_bootstrap(losses, [1.0] * 5, 1000, 42)
    second = weighted_bootstrap(losses, [1.0] * 5, 1000, 42)
    assert first == second


def test_the_alarm_threshold_is_published_and_small():
    """Le seuil au-delà duquel le chiffre note le corpus plutôt que le moteur.
    Il doit rester petit : à 20 % de hors-corpus, la moyenne ne veut plus rien
    dire, et un banc qui se tairait là-dessus mentirait par omission."""
    assert 0.0 < HORS_CORPUS_ALARM <= 0.10

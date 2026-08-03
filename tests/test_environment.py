"""T00 — le socle est-il réellement fonctionnel ?

Ces tests ne mesurent aucune force. Ils vérifient qu'une chaîne existe : que le moteur
de règles C est compilé et chargeable, que le modèle de référence se charge, et qu'il
produit bien **cinq** sorties et non une équité agrégée.

Ce dernier point n'est pas cosmétique. Le match play a besoin de la distribution des cinq
probabilités, pas d'un scalaire (`BRIEF.md` §6). Un modèle qui n'en produirait qu'une
serait inutilisable ici — et le découvrir en T32 plutôt qu'en T00 coûterait cher.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "vendor" / "backgammon-ai-engine"
MODEL = REFERENCE / "best_models" / "cubeless_prob5_512_512_256_128.pt"

pytestmark = pytest.mark.skipif(
    not REFERENCE.is_dir(),
    reason="vendor/backgammon-ai-engine absent — lancer `make vendor`",
)


@pytest.fixture(scope="module")
def reference_on_path():
    """Put the pinned reference checkout on sys.path, and take it back off."""
    for path in (REFERENCE, REFERENCE / "c_engine"):
        sys.path.insert(0, str(path))
    yield
    for path in (REFERENCE, REFERENCE / "c_engine"):
        sys.path.remove(str(path))


def test_rules_engine_is_compiled():
    """`make vendor` must have produced the shared library, not just cloned the source."""
    assert (REFERENCE / "c_engine" / "libbg_engine.so").is_file(), (
        "libbg_engine.so absent — la génération de parties tomberait sur le chemin "
        "Python pur, ~20x plus lent"
    )


def test_rules_engine_loads_and_agrees_with_the_python_path(reference_on_path):
    """The C engine must load through ctypes and agree with the pure-Python generator.

    Not a substitute for T01, which cross-checks a 200-position corpus against an
    independent generator. This only catches a broken ctypes bridge — a C path that
    silently disagrees with the Python one it is supposed to replace.
    """
    import bg_fast
    import backgammon_engine
    from backgammon_engine import BoardState

    board = BoardState.initial()  # ← pas BoardState(), qui construit un plateau VIDE
    features, next_states = bg_fast.get_legal_plays_encoded(board, (3, 1))

    assert len(features) > 0, "aucun coup légal sur le jet d'ouverture 3-1"
    assert features.shape[1] == 196, f"attendu 196 caractéristiques, obtenu {features.shape[1]}"
    assert len(next_states) == len(features)

    python_plays = backgammon_engine.get_legal_plays(board, (3, 1))
    assert len(features) == len(python_plays), (
        f"le moteur C rend {len(features)} coups, le moteur Python {len(python_plays)} "
        "— le pont ctypes ne rend pas ce que le chemin de référence rend"
    )


def test_reference_model_is_present():
    assert MODEL.is_file(), f"{MODEL} absent — lancer `make vendor`"


def test_reference_model_produces_five_probabilities(reference_on_path):
    """The retained model must expose the prob5 distribution, not a money scalar."""
    import torch

    checkpoint = torch.load(MODEL, map_location="cpu", weights_only=False)

    assert checkpoint.get("model_type") == "prob5", (
        "le modèle retenu doit être un prob5 : les variantes cubeful_money sortent une "
        "équité agrégée, inutilisable en match (BRIEF.md §3.1)"
    )
    assert checkpoint.get("input_size", 196) == 196
    assert checkpoint.get("encoder_name", "perspective196") == "perspective196"

    head_weight = checkpoint["state_dict"]["head.weight"]
    assert head_weight.shape[0] == 5, (
        f"la couche de sortie a {head_weight.shape[0]} neurones, attendu 5 "
        "(gain, gain-gammon, gain-backgammon, perte-gammon, perte-backgammon)"
    )


def test_gnubg_oracle_is_installed():
    """The measurement oracle must be importable — it is an instrument, never a source."""
    pytest.importorskip("gnubg_nn", reason="gnubg-nn absent — lancer `make venv`")

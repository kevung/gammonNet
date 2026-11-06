"""T12 — l'outil qui produit le corpus ne doit jamais en changer les positions en silence.

Le corpus a été tiré une fois, par une marche aléatoire sur les coups légaux. Cette marche
choisissait un coup par son RANG dans la liste du générateur ; quand l'épingle amont est passée
de `b2750df` à `7184e2f`, les mêmes coups sont revenus dans un autre ordre et la même graine a
mené à 1 899 positions différentes sur 2 050. `--check` échouait, et `make corpus-t12` aurait
remplacé le corpus sans que rien ne le signale.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_corpus_t12 as tool  # noqa: E402
from gammonnet import Position, codec  # noqa: E402


def _walk_ids(monkeypatch, reverse: bool) -> list[str]:
    """A short walk, with the generator's list reversed or not."""
    original = Position.legal_plays

    def legal_plays(self, d1, d2):
        plays = original(self, d1, d2)
        return plays[::-1] if reverse else plays

    monkeypatch.setattr(Position, "legal_plays", legal_plays)
    monkeypatch.setattr(tool, "QUOTAS", {"contact": 30, "race": 10, "bearoff": 10, "bar": 10, "backgame": 5})
    found = tool.collect(random.Random(tool.SEED))
    return [codec.position_id(p) for category in sorted(found) for p in found[category]]


def test_the_walk_does_not_depend_on_the_generators_order(monkeypatch):
    assert _walk_ids(monkeypatch, reverse=False) == _walk_ids(monkeypatch, reverse=True)


def test_the_default_rebuild_keeps_the_committed_positions_byte_for_byte():
    """Sans `--walk`, l'outil relit les positions du fichier : le texte rendu est le fichier."""
    if not tool.MODEL.is_file():
        pytest.skip(f"{tool.MODEL} absent")
    records = tool.build(tool.frozen())
    text = "".join(tool.json.dumps(r, sort_keys=True) + "\n" for r in records)
    assert text == tool.CORPUS.read_text()

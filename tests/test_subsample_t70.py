"""T70 — le sous-échantillon à arbitrer : ce qu'il doit préserver.

Arbitrer 10 000 décisions sur 28 374 n'est légitime que si le sous-échantillon
estime sans biais ce que le corpus entier dirait. Trois propriétés le
garantissent, et chacune se perd sans bruit :

  - les **parts de classe** sont préservées, sinon la moyenne pondérée dérive ;
  - les **index d'origine** sont conservés, sinon arbitrer le reste plus tard
    créerait des collisions dans un journal qui classe par index ;
  - le tirage est **reproductible**, sinon « le corpus arbitré » n'est pas une
    chose qu'on peut nommer.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from subsample_corpus_t70 import hash_name, stratified  # noqa: E402


def corpus(counts):
    rows, index = [], 0
    for klass, n in counts.items():
        for _ in range(n):
            rows.append({"index": index, "class": klass, "weight": 1.0,
                         "context": "money", "position_id": f"P{index}",
                         "turn": 0, "dice": [3, 1]})
            index += 1
    return rows


def test_the_class_shares_are_preserved():
    """Le cas central : une strate sur-représentée dans le corpus doit l'être
    autant dans le sous-échantillon, sinon les poids d'origine — qu'on conserve
    exprès — cessent d'être les bons."""
    rows = corpus({"contact": 14000, "blitz": 3500, "backgame": 1200, "crashed": 1300})
    chosen, _ = stratified(rows, 5000, 42)
    before = collections.Counter(r["class"] for r in rows)
    after = collections.Counter(r["class"] for r in chosen)
    for klass in before:
        assert (after[klass] / len(chosen)) == pytest.approx(
            before[klass] / len(rows), abs=0.002)


def test_the_original_indices_survive():
    """Le sous-échantillon est un vrai sous-ensemble, pas une renumérotation :
    le journal d'arbitrage classe par index, et arbitrer le reste plus tard doit
    s'ajouter au même registre sans collision."""
    rows = corpus({"contact": 500, "backgame": 100})
    chosen, _ = stratified(rows, 200, 7)
    originaux = {r["index"] for r in rows}
    retenus = [r["index"] for r in chosen]
    assert set(retenus) <= originaux
    assert len(set(retenus)) == len(retenus)
    assert retenus == sorted(retenus)


def test_the_draw_is_reproducible():
    rows = corpus({"contact": 800, "blitz": 200})
    first, _ = stratified(rows, 300, 99)
    second, _ = stratified(rows, 300, 99)
    assert [r["index"] for r in first] == [r["index"] for r in second]


def test_another_seed_draws_another_sample():
    rows = corpus({"contact": 800, "blitz": 200})
    first, _ = stratified(rows, 300, 1)
    second, _ = stratified(rows, 300, 2)
    assert [r["index"] for r in first] != [r["index"] for r in second]


def test_a_class_smaller_than_its_quota_is_taken_whole():
    """Quand la cible approche la taille du corpus, le quota proportionnel d'une
    strate peut dépasser ce qu'elle contient. Elle est alors prise ENTIÈRE, et
    ce qu'elle ne consomme pas retourne aux autres — sans quoi le tirage rendrait
    moins que la cible, et la strate rare, déjà la moins bien mesurée, paierait
    l'arrondi."""
    rows = corpus({"contact": 100, "backgame": 3})
    chosen, counts = stratified(rows, 95, 5)
    assert counts["backgame"] == 3
    assert len(chosen) >= 90


def test_a_rare_class_keeps_its_share_when_the_target_is_small():
    """Le cas réel : 1 229 backgames sur 28 374, cible 10 000. La strate doit
    garder sa part, pas être sacrifiée à l'arrondi."""
    rows = corpus({"contact": 27145, "backgame": 1229})
    chosen, counts = stratified(rows, 10_000, 5)
    assert counts["backgame"] / len(chosen) == pytest.approx(1229 / 28374, abs=0.002)


def test_the_target_is_reached_and_not_overshot():
    rows = corpus({"contact": 6000, "blitz": 2000, "backgame": 2000})
    chosen, _ = stratified(rows, 4000, 11)
    assert len(chosen) == pytest.approx(4000, abs=20)
    assert len(chosen) <= len(rows)


def test_asking_for_more_than_the_corpus_returns_the_corpus():
    rows = corpus({"contact": 100, "blitz": 50})
    chosen, _ = stratified(rows, 5000, 3)
    assert len(chosen) == 150


def test_the_class_seed_offset_is_stable_across_processes():
    """`hash()` d'une chaîne varie d'un processus Python à l'autre. S'en servir
    ici rendrait le tirage irreproductible SANS que rien ne le signale — le même
    piège que `build_corpus_t70.py` nomme déjà pour les contextes."""
    assert hash_name("backgame") == hash_name("backgame")
    assert hash_name("backgame") != hash_name("contact")
    assert hash_name("contact") == 155090271

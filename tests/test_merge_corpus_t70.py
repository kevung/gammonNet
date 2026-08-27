"""T70 — la fusion des tranches : les trois façons dont un `cat` mentirait.

Chacune produit un fichier parfaitement lisible. Aucune ne se voit sans test :
un poids faux déplace une moyenne d'équité sans rien casser, des index qui se
recouvrent confondent deux décisions dans le journal d'arbitrage, et un doublon
pondère deux fois la même position — de préférence dans une classe rare, là où
il pèse le plus.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from merge_corpus_t70 import check_compatible, merge_rows, reweight  # noqa: E402


def row(index, klass, pid, dice=(3, 1), turn=0):
    return {"index": index, "context": "money", "class": klass, "weight": 1.0,
            "position_id": pid, "turn": turn, "dice": list(dice),
            "candidates": [pid]}


def test_the_indices_are_renumbered_across_slices():
    """Chaque tranche numérote à partir de zéro. L'arbitrage journalise par
    index et l'étape 0 de T71 apparie par index : deux décisions portant le
    numéro 0 se confondraient en silence."""
    a = [row(0, "contact", "A"), row(1, "contact", "B")]
    b = [row(0, "backgame", "C"), row(1, "contact", "D")]
    rows, _dupes = merge_rows([(Path("t1"), a), (Path("t2"), b)])
    assert [r["index"] for r in rows] == [0, 1, 2, 3]
    assert len({r["index"] for r in rows}) == 4


def test_a_decision_present_in_two_slices_is_kept_once():
    """Des graines différentes peuvent tomber sur la même décision. Comptée deux
    fois, elle pèserait double — et c'est dans les classes rares que la
    collision coûte le plus cher."""
    a = [row(0, "backgame", "MÊME", (5, 2))]
    b = [row(0, "backgame", "MÊME", (5, 2)), row(1, "contact", "AUTRE")]
    rows, duplicates = merge_rows([(Path("t1"), a), (Path("t2"), b)])
    assert duplicates == 1
    assert len(rows) == 2


def test_the_same_position_with_other_dice_is_another_decision():
    """L'identité d'une décision, c'est la position ET le jet : la même position
    sous 6-5 et sous 2-1 pose deux problèmes différents."""
    a = [row(0, "contact", "P", (6, 5))]
    b = [row(0, "contact", "P", (2, 1))]
    rows, duplicates = merge_rows([(Path("t1"), a), (Path("t2"), b)])
    assert duplicates == 0
    assert len(rows) == 2


def test_the_weight_is_recomputed_on_the_UNITED_corpus():
    """Le cas central. Un poids calculé sur une tranche et appliqué au corpus
    réuni déplace la moyenne d'équité sans rien casser d'apparent."""
    rows = ([row(i, "contact", f"C{i}") for i in range(9)]
            + [row(9, "backgame", "B0")])
    natural = {"contact": 0.99, "backgame": 0.01}
    counts = reweight(rows, natural)
    assert counts == {"contact": 9, "backgame": 1}
    # contact : 99 % de fréquence naturelle pour 90 % du corpus → poids 1,1
    assert rows[0]["weight"] == pytest.approx(0.99 / 0.9)
    # backgame : sur-représenté (10 % du corpus pour 1 % naturel) → poids 0,1
    assert rows[9]["weight"] == pytest.approx(0.01 / 0.1)
    # Et la somme des poids vaut le nombre de décisions : la pondération
    # redistribue, elle n'invente ni ne détruit de masse.
    assert sum(r["weight"] for r in rows) == pytest.approx(
        sum(natural.values()) * len(rows))


def test_a_class_absent_from_the_natural_distribution_weighs_zero_not_one():
    """Zéro par défaut serait un poids implicite de 1 — la classe compterait
    comme n'importe quelle autre alors qu'on ne sait rien de sa fréquence."""
    rows = [row(0, "inconnue", "X")]
    reweight(rows, {"contact": 1.0})
    assert rows[0]["weight"] == 0.0


def test_two_slices_from_different_engines_are_refused_by_name():
    base = {"version": 3, "ply": 2, "width": 6, "model": "net.bin",
            "filters": {"2": [0, 1, 5]}}
    other = dict(base, ply=3, model="autre.bin")
    with pytest.raises(SystemExit) as caught:
        check_compatible([(Path("t1"), base), (Path("t2"), other)])
    message = str(caught.value)
    assert "REFUS" in message
    assert "ply" in message and "model" in message


def test_slices_differing_only_in_harvest_settings_are_accepted():
    """Graine, cible, quotas : ce sont des réglages de RÉCOLTE. Ils doivent
    varier d'une tranche à l'autre — c'est même le but."""
    base = {"version": 3, "ply": 2, "width": 6, "model": "net.bin",
            "filters": {"2": [0, 1, 5]}, "seed": 1, "quota": {"contact": 100}}
    other = dict(base, seed=999_999, quota={"contact": 7})
    check_compatible([(Path("t1"), base), (Path("t2"), other)])

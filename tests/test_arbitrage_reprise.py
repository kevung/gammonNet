"""T70 — la reprise de l'arbitrage : ce qu'un journal doit garantir.

Une campagne d'arbitrage conséquente dure des jours. Sans reprise elle est un
pari : une coupure tardive perd tout. Avec reprise, elle devient une décision —
à condition que le journal tienne trois promesses, dont aucune ne se voit
échouer si on ne la teste pas :

  - il **refuse** de mélanger deux protocoles, au lieu de rendre un registre
    plausible fait de deux moitiés incomparables ;
  - il survit à une **ligne tronquée** par une coupure, en rejouant la décision
    plutôt qu'en la comptant à moitié ;
  - il rend un registre **trié et dédoublonné**, quel que soit l'ordre dans
    lequel les tranches sont revenues.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from arbitrate_t70 import load_journal, read_journal_records  # noqa: E402

HEADER = {"corpus": "corpus-money.jsonl", "decisions": 3, "context": "money",
          "seed": 20260827, "net": 0.004, "resolution": 0.005,
          "truncated_trials": 216, "full_trials": 648, "truncate": 11,
          "deep_truncate": 21, "audit": 0.05, "model": "reseau.bin"}


def write(path: Path, header, records):
    lines = []
    if header is not None:
        lines.append(json.dumps({"header": header}, sort_keys=True))
    lines.extend(json.dumps(r, sort_keys=True) for r in records)
    path.write_text("\n".join(lines) + "\n")


def test_an_absent_journal_is_an_empty_resume(tmp_path):
    assert load_journal(tmp_path / "rien.journal", HEADER) == set()
    assert read_journal_records(tmp_path / "rien.journal") == []


def test_the_indices_already_arbitrated_are_returned(tmp_path):
    j = tmp_path / "r.journal"
    write(j, HEADER, [{"index": 2, "equities": [1.0]}, {"index": 7, "equities": [2.0]}])
    assert load_journal(j, HEADER) == {2, 7}


def test_a_different_protocol_is_refused_and_names_what_differs(tmp_path):
    """Le cas qui compte. Deux moitiés arbitrées sous des budgets d'essais
    différents produiraient un registre parfaitement lisible et faux : rien dans
    le fichier ne dirait que ses décisions ne sont pas comparables entre elles."""
    j = tmp_path / "r.journal"
    write(j, HEADER, [{"index": 1}])
    autre = dict(HEADER, full_trials=1296, net=0.010)
    with pytest.raises(SystemExit) as caught:
        load_journal(j, autre)
    message = str(caught.value)
    assert "REFUS" in message
    assert "full_trials" in message and "net" in message


def test_a_line_cut_by_a_crash_is_skipped_not_half_counted(tmp_path):
    """Une coupure tronque la dernière ligne. Son index manque donc au journal,
    et la décision est rejouée — jamais comptée sur une ligne incomplète."""
    j = tmp_path / "r.journal"
    write(j, HEADER, [{"index": 1, "equities": [1.0]}])
    with j.open("a") as fh:
        fh.write('{"index": 2, "equit')
    assert load_journal(j, HEADER) == {1}
    assert [r["index"] for r in read_journal_records(j)] == [1]


def test_the_registry_comes_back_sorted_whatever_the_order_of_return(tmp_path):
    """Les tranches reviennent dans l'ordre où elles finissent, pas dans l'ordre
    du corpus. Le registre, lui, doit être trié : `measure_t70` et l'étape 0 de
    T71 s'apparient par index."""
    j = tmp_path / "r.journal"
    write(j, HEADER, [{"index": 9}, {"index": 2}, {"index": 5}])
    assert [r["index"] for r in read_journal_records(j)] == [2, 5, 9]


def test_a_decision_replayed_after_a_crash_is_kept_once(tmp_path):
    """Une tranche en vol au moment de la coupure est rejouée à la reprise : son
    index apparaît deux fois dans le journal. Le registre n'en garde qu'une —
    sinon la moyenne pondérerait deux fois la même décision."""
    j = tmp_path / "r.journal"
    write(j, HEADER, [{"index": 4, "pass_used": 1}, {"index": 4, "pass_used": 2}])
    records = read_journal_records(j)
    assert len(records) == 1
    assert records[0]["pass_used"] == 2


def test_a_journal_without_header_still_resumes(tmp_path):
    """Un journal d'avant l'en-tête, ou dont la première ligne a été perdue, ne
    doit pas faire perdre le travail déjà payé : on reprend, sans pouvoir
    vérifier le protocole."""
    j = tmp_path / "r.journal"
    write(j, None, [{"index": 3}])
    assert load_journal(j, HEADER) == {3}

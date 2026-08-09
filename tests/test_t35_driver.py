"""T35 — le pilote : la propriété qui autorise à éteindre la machine.

Le test central rejoue la même campagne de deux façons — d'une traite, et en
trois lots avec des nombres d'ouvriers différents — et exige que les journaux
portent **les mêmes lignes, bit à bit** (l'en-tête et l'ordre d'arrivée mis à
part : les lignes portent leur index, l'ordre n'est pas une donnée).

C'est la propriété annoncée par `bench/run_t35.py` ; si elle casse, la
segmentation produirait une mesure différente du calcul d'une traite, et tout
l'argument de la reprise s'effondre. Elle se teste au 0-ply, nous contre
nous : la propriété est celle du harnais, pas du réglage de la campagne.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="modèle absent")

DRIVER = ROOT / "bench" / "run_t35.py"
REPORT = ROOT / "bench" / "report_t35.py"


def run_driver(journal: Path, mode: str, pairs: int, workers: int,
               limit: int = 0) -> str:
    command = [sys.executable, str(DRIVER), "--mode", mode,
               "--pairs", str(pairs), "--journal", str(journal),
               "--theirs", "self", "--ours-ply", "0", "--ours-filter", "",
               "--workers", str(workers), "--seed", "20260810"]
    if limit:
        command += ["--limit", str(limit)]
    done = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr + done.stdout
    return done.stdout


def journal_rows(journal: Path) -> dict[int, dict]:
    rows = {}
    with journal.open() as lines:
        for line in lines:
            row = json.loads(line)
            if not row.get("header"):
                rows[row["i"]] = row
    return rows


@needs_model
def test_a_segmented_run_matches_a_single_run_bit_for_bit(tmp_path):
    single = tmp_path / "single.jsonl"
    run_driver(single, "money", pairs=6, workers=6)

    segmented = tmp_path / "segmented.jsonl"
    run_driver(segmented, "money", pairs=6, workers=3, limit=2)
    run_driver(segmented, "money", pairs=6, workers=2, limit=2)
    run_driver(segmented, "money", pairs=6, workers=6)

    assert journal_rows(single) == journal_rows(segmented)


@needs_model
def test_the_match_mode_is_segmentable_too(tmp_path):
    single = tmp_path / "single.jsonl"
    run_driver(single, "match", pairs=4, workers=4)

    segmented = tmp_path / "segmented.jsonl"
    run_driver(segmented, "match", pairs=4, workers=2, limit=1)
    run_driver(segmented, "match", pairs=4, workers=3)

    assert journal_rows(single) == journal_rows(segmented)
    # Les scores échantillonnés font partie du protocole : ils doivent être
    # dans le journal, pas seulement dans la mémoire du processus.
    assert all("away_a" in row for row in journal_rows(single).values())


@needs_model
def test_a_journal_refuses_another_protocol(tmp_path):
    journal = tmp_path / "campaign.jsonl"
    run_driver(journal, "money", pairs=2, workers=2)

    command = [sys.executable, str(DRIVER), "--mode", "money",
               "--pairs", "2", "--journal", str(journal),
               "--theirs", "self", "--ours-ply", "0", "--ours-filter", "",
               "--seed", "999"]  # autre graine → autre protocole
    done = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert done.returncode != 0
    assert "autre protocole" in done.stderr + done.stdout


@needs_model
def test_the_report_reads_a_partial_journal_and_says_so(tmp_path):
    journal = tmp_path / "campaign.jsonl"
    run_driver(journal, "money", pairs=5, workers=3, limit=3)

    done = subprocess.run([sys.executable, str(REPORT), "--journal",
                           str(journal)], capture_output=True, text=True,
                          timeout=120)
    assert done.returncode == 0, done.stderr
    assert "PARTIEL" in done.stdout and "2 paire(s) manquante(s)" in done.stdout

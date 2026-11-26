"""La chance d'un jet (gammonnet/luck.py) et la colonne corrigée des tête-à-tête.

Ce qui est tenu ici, et pas supposé :
- les 21 valeurs du juge sont l'équité 0-ply du meilleur coup sous chaque jet,
  dans l'ordre de `ROLLS` — la même grandeur que `roll_equity` de gn_rollout.c ;
- la chance est centrée sachant la position, exactement (au flottant près) ;
- le juge ne change pas la partie : mêmes points, mêmes tours, mêmes doubles ;
- A contre A rend une chance nette nulle, comme un résultat net nul ;
- le pilote écrit la chance, et le dépouillement l'imprime avec son identité
  comptable.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from gammonnet.cubeful import (
    GammonNetCubePlayer,
    play_cubeful_duplicate,
    play_match_duplicate,
)
from gammonnet.luck import LuckReference, roll_index
from gammonnet.rules import Position
from gammonnet.search import ROLLS, SearchConfig, search_plays

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_768_768_256_256_256.bin"
OTHER = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="modèle absent")


def _positions(n: int = 12, seed: int = 20261126) -> list[Position]:
    """Des positions de partie réelle, obtenues en jouant au 0-ply."""
    from gammonnet.infer import Network

    net = Network.load(MODEL)
    rng = random.Random(seed)
    out, pos = [], Position.initial()
    while len(out) < n:
        if pos.is_over():
            pos = Position.initial()
        out.append(pos)
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = search_plays(net, pos, d1, d2, SearchConfig(ply=0))
        pos = plays[0].result if plays else pos.swapped_turn()
    return out


@needs_model
def test_the_judge_values_each_roll_by_its_best_zero_ply_play():
    judge = LuckReference(MODEL)
    for pos in _positions(6):
        values, weights = judge.roll_values(pos)
        assert sum(weights) == pytest.approx(1.0, abs=1e-12)
        for r, (a, b, w) in enumerate(ROLLS):
            assert weights[r] == pytest.approx(w, abs=1e-12)
            plays = search_plays(judge.network, pos, a, b, SearchConfig(ply=0))
            if not plays:
                continue          # a dance: the judge scores the passed turn
            assert values[r] == pytest.approx(plays[0].equity, abs=2e-6), (a, b)
    assert roll_index(5, 2) == roll_index(2, 5)


@needs_model
def test_luck_is_centred_given_the_position():
    judge = LuckReference(MODEL)
    for pos in _positions(8):
        total = sum(w * judge.luck(pos, a, b) for a, b, w in ROLLS)
        assert total == pytest.approx(0.0, abs=1e-9)


def _players():
    a = GammonNetCubePlayer(ply=0, filter=(), cube_ply=0, prune_k=0, model=str(MODEL))
    b = GammonNetCubePlayer(ply=0, filter=(), cube_ply=0, prune_k=0, model=str(OTHER),
                            name="other")
    return a, b


@needs_model
@pytest.mark.skipif(not OTHER.exists(), reason="second modèle absent")
def test_the_judge_changes_nothing_in_the_games():
    a, b = _players()
    judge = LuckReference(MODEL)
    for index in range(6):
        plain, plain_stats = play_cubeful_duplicate(a, b, 7, index)
        judged, judged_stats = play_cubeful_duplicate(a, b, 7, index, luck=judge)
        luck = judged_stats.pop("luck")
        assert (plain, plain_stats) == (judged, judged_stats)
        assert isinstance(luck, float)
    for index in range(3):
        plain, plain_stats = play_match_duplicate(a, b, 3, 2, 7, index)
        judged, judged_stats = play_match_duplicate(a, b, 3, 2, 7, index, luck=judge)
        judged_stats.pop("luck")
        assert (plain, plain_stats) == (judged, judged_stats)


@needs_model
def test_a_against_a_nets_zero_luck():
    a, _ = _players()
    judge = LuckReference(MODEL)
    for index in range(4):
        net, stats = play_cubeful_duplicate(a, a, 11, index, luck=judge)
        assert net == 0
        assert stats["luck"] == pytest.approx(0.0, abs=1e-12)
        net, stats = play_match_duplicate(a, a, 2, 4, 11, index, luck=judge)
        assert net == 0
        assert stats["luck"] == pytest.approx(0.0, abs=1e-12)


@needs_model
@pytest.mark.skipif(not OTHER.exists(), reason="second modèle absent")
def test_the_driver_records_luck_and_the_report_prints_the_adjusted_column(tmp_path):
    journal = tmp_path / "luck.jsonl"
    command = [sys.executable, str(ROOT / "bench" / "run_t35.py"), "--mode", "money",
               "--pairs", "6", "--journal", str(journal), "--theirs", "self",
               "--ours-ply", "0", "--ours-filter", "", "--ours-prune-k", "0",
               "--theirs-model", str(OTHER), "--luck-model", str(MODEL),
               "--workers", "2", "--seed", "20261126"]
    done = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr + done.stdout
    lines = [json.loads(line) for line in journal.read_text().splitlines()]
    header, rows = lines[0], lines[1:]
    assert header["luck_reference"]["model"] == str(MODEL)
    assert header["evalcache_key"] == "position+network"
    assert len(rows) == 6 and all("luck" in r for r in rows)

    report = subprocess.run([sys.executable, str(ROOT / "bench" / "report_t35.py"),
                             "--journal", str(journal), "--bootstrap", "200"],
                            capture_output=True, text=True, timeout=600)
    assert report.returncode == 0, report.stderr
    assert "ppg corrigé" in report.stdout
    gap = float(report.stdout.split("identité comptable : brute = corrigée + chance, écart ")[1].split()[0])
    assert gap < 1e-9


def test_a_journal_from_before_the_cache_fix_is_not_extended(tmp_path):
    """Un journal à deux réseaux sans la marque `evalcache_key` a été joué avec le
    cache indexé par la seule position : le pilote refuse de le prolonger."""
    if not (MODEL.exists() and OTHER.exists()):
        pytest.skip("modèles absents")
    journal = tmp_path / "old.jsonl"
    command = [sys.executable, str(ROOT / "bench" / "run_t35.py"), "--mode", "money",
               "--pairs", "2", "--journal", str(journal), "--theirs", "self",
               "--ours-ply", "0", "--ours-filter", "", "--ours-prune-k", "0",
               "--theirs-model", str(OTHER), "--workers", "1", "--seed", "3"]
    done = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    lines = journal.read_text().splitlines()
    header = json.loads(lines[0])
    del header["evalcache_key"]
    journal.write_text("\n".join([json.dumps(header)] + lines[1:]) + "\n")
    command[command.index("--pairs") + 1] = "4"
    again = subprocess.run(command, capture_output=True, text=True, timeout=600)
    assert again.returncode != 0
    assert "evalcache_key" in again.stdout + again.stderr

"""`bench/report_policy.py` — the paired report, in match and in money."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from report_policy import paired_summary  # noqa: E402

REPORT = ROOT / "bench" / "report_policy.py"


def header(mode: str, model: str, dice_key: str | None = "a|b") -> dict:
    head = {"header": True, "task": "T35", "mode": mode, "seed": 20260810,
            "ours": {"name": "gammonnet-policy-normal", "model": model,
                     "policy_level": "normal"},
            "theirs": {"name": "gnubg-2ply-f0/1/3-cube2"}}
    if dice_key is not None:
        head["dice_key"] = dice_key
    return head


def money_rows(nets: list[int]) -> dict[int, dict]:
    return {i: {"i": i, "net": net, "stalled": False} for i, net in enumerate(nets)}


def write(path: Path, head: dict, rows: dict[int, dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in [head, *rows.values()]))
    return path


def test_money_reports_points_per_game_and_the_paired_gap():
    ours = money_rows([2, 0, -1, 4])
    ref = money_rows([0, 0, -1, 2])
    s = paired_summary(header("money", "new.bin"), ours, header("money", "old.bin"), ref,
                       bootstrap=200)
    assert s["mode"] == "money" and s["pairs"] == 4
    # One sample per duplicate pair: net / 2 points per game.
    assert s["ours"][0] == pytest.approx((1 + 0 - 0.5 + 2) / 4)
    assert s["reference"][0] == pytest.approx((0 + 0 - 0.5 + 1) / 4)
    assert s["diff"][0] == pytest.approx(s["ours"][0] - s["reference"][0])
    assert s["same"] == 2
    low, high = s["diff"][1:]
    assert low <= s["diff"][0] <= high


def test_stalled_and_missing_pairs_are_left_out_of_the_pairing():
    ours = money_rows([2, 0, 4])
    ours[1]["stalled"] = True
    ref = money_rows([0, 0])
    s = paired_summary(header("money", "n"), ours, header("money", "o"), ref, bootstrap=50)
    assert (s["pairs"], s["first"], s["last"]) == (1, 0, 0)


def test_two_modes_or_two_dice_keys_do_not_pair():
    rows = money_rows([0, 2])
    with pytest.raises(ValueError, match="modes"):
        paired_summary(header("money", "n"), rows, header("match", "o"), rows)
    with pytest.raises(ValueError, match="clés de dés"):
        paired_summary(header("money", "n"), rows, header("money", "o", "c|d"), rows)


def test_a_source_journal_pairs_through_the_key_of_its_player_names():
    from gammonnet.arena import pair_key

    source = header("money", "o", dice_key=None)
    replay = header("money", "n",
                    dice_key=pair_key(source["ours"]["name"], source["theirs"]["name"]))
    rows = money_rows([0, 2])
    assert paired_summary(replay, rows, source, rows, bootstrap=50)["pairs"] == 2


def test_match_still_refuses_another_starting_score():
    a = {0: {"i": 0, "net": 2, "away_a": 3, "away_b": 5, "post_crawford": False}}
    b = {0: {"i": 0, "net": 0, "away_a": 5, "away_b": 3, "post_crawford": False}}
    with pytest.raises(ValueError, match="situation de départ"):
        paired_summary(header("match", "n"), a, header("match", "o"), b)


def test_the_command_line_prints_ppg_for_a_money_journal(tmp_path):
    journal = write(tmp_path / "new.jsonl", header("money", "models/new.bin"),
                    money_rows([2, 0, -2, 6]))
    reference = write(tmp_path / "old.jsonl", header("money", "models/old.bin"),
                      money_rows([0, 0, -2, 2]))
    done = subprocess.run([sys.executable, str(REPORT), "--journal", str(journal),
                           "--reference", str(reference), "--bootstrap", "200"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert "+0.7500 ppg" in done.stdout          # (1 + 0 - 1 + 3) / 4
    assert "écart apparié journal − référence : +0.7500 ppg" in done.stdout
    assert "MWC" not in done.stdout

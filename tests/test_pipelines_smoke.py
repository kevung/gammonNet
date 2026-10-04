"""The two training pipelines run end to end in smoke mode and leave a readable artefact.

A smoke run labels a few hundred positions with a randomly initialised network
and trains for one epoch. It proves the plumbing - corpus, training, `.bin`
export, read-back by the engine, provenance - and nothing about strength. The
tests below therefore assert on shapes, files and reloadability, never on a
loss value.

The training tests need PyTorch; they are skipped, loudly, where it is absent
(`make setup TORCH_CPU=1`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from gammonnet.classify import in_race_zone
from gammonnet.rules import Position

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def position(points: dict[int, int], turn: int = 0, off=(0, 0), bar=(0, 0)):
    cells = [0] * 24
    for index, count in points.items():
        cells[index] = count
    return Position(tuple(cells), bar, off, turn)


def test_race_zone_excludes_contact_bearoff_and_over():
    # White moves toward index 0, black toward 23: the camps have crossed and
    # neither side is borne in, so the table does not apply.
    race = position({6: 5, 8: 5, 10: 5, 14: -5, 16: -5, 18: -5})
    # Still contact: a white checker behind a black one.
    contact = position({20: 4, 2: 1, 10: -1, 12: -4})
    # Both sides borne in: the exact table answers.
    bearoff = position({0: 3, 1: 3, 2: 3, 23: -3, 22: -3, 21: -3})
    assert in_race_zone(race)
    assert not in_race_zone(contact)
    assert not in_race_zone(bearoff)


def test_target_shape_stays_in_the_t72_window():
    import distill_t72

    shape = distill_t72.shape_for_target(80_000)
    assert distill_t72.MIN_MACS <= distill_t72.macs(shape) <= distill_t72.MAX_MACS
    assert shape == [shape[0], shape[0] // 2, shape[0] // 4]
    # The checked-in witness of the T72 preparation sweep.
    assert distill_t72.macs([256, 128, 64]) == 91_456


def test_t72_refuses_a_shape_outside_the_window(tmp_path):
    pytest.importorskip("torch")
    import distill_t72

    assert distill_t72.main(["--shape", "512,512,256,128", "--smoke",
                             "--out-dir", str(tmp_path)]) == 2


def test_t72_smoke_writes_student_and_witness_of_the_same_shape(tmp_path):
    pytest.importorskip("torch")
    import distill_t72

    assert distill_t72.main(["--smoke", "--out-dir", str(tmp_path)]) == 0
    summary = json.loads(next(tmp_path.glob("t72_*.summary.json")).read_text())
    assert summary["smoke"] is True
    shape = summary["shape"]
    for kind in ("student", "witness"):
        entry = summary["networks"][kind]
        assert Path(entry["path"]).is_file()
        assert entry["readback"]["hidden"] == shape
        assert len(entry["readback"]["opening_position"]) == 5
    assert "NONE" in summary["verdict"]


def test_race_pipeline_smoke_corpus_train_export_gauge(tmp_path):
    pytest.importorskip("torch")
    import build_race_corpus
    import gauge_race_net
    import train_race_net

    out = tmp_path / "race_net.bin"
    assert train_race_net.main(["--smoke", "--out", str(out)]) == 0
    provenance = json.loads(out.with_suffix(".provenance.json").read_text())
    assert provenance["smoke"] is True
    assert provenance["artifact"]["readback_opening_position"]
    assert provenance["hidden"] == [128, 64]

    corpus = tmp_path / "smoke-inputs" / "race.npz"
    import numpy as np
    data = np.load(corpus)
    assert data["features"].shape[1] == 196
    assert set(data["klass"].tolist()) <= {"race", "bearoff_noncontact",
                                           "bearoff_contact"}
    # Every kept row is inside the zone: rebuild it from its identifier.
    from gammonnet import codec
    for identifier in data["ids"][:20].tolist():
        raw, turn = identifier.rsplit(":", 1)
        assert in_race_zone(codec.position_from_id(raw, int(turn)))

    report_path = tmp_path / "gauge.json"
    assert gauge_race_net.main(["--smoke", "--out", str(report_path)]) == 0
    report = json.loads(report_path.read_text())
    assert report["rows"] > 1 and report["smoke"] is True
    assert set(report["overall"]) == {"candidate", "incumbent"}
    assert build_race_corpus.DEFAULT_MODEL.name.startswith("cubeless")

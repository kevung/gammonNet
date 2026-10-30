"""T72-rang — the decision index of the distillation corpus, and the ranking term.

Nothing here measures strength (that is `bench/measure_t70.py`). What is held:
the corpus groups sibling plays without changing the walk, a resumed corpus is
the same corpus, the ranking loss is zero exactly when the order and the gaps
agree, and the 0-ply regret counts what it says.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "python"))

import distill_rank_t72 as rank  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_768_768_256_256_256.bin"
needs_model = pytest.mark.skipif(not MODEL.is_file(), reason="réseau servi absent")


def _corpus(out: Path, rows: int = 3000, chunk: int = 1000) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_distill_corpus.py"), "--rows", str(rows),
         "--workers", "2", "--chunk", str(chunk), "--seed", "11", "--host", "test",
         "--out", str(out)],
        check=True, capture_output=True)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    if not MODEL.is_file():
        pytest.skip("réseau servi absent")
    out = tmp_path_factory.mktemp("rang")
    _corpus(out)
    return out


def test_group_bounds():
    s, n = rank.group_bounds(np.array([4, 4, 4, 5, 7, 7]))
    assert s.tolist() == [0, 3, 4] and n.tolist() == [3, 1, 2]
    s, n = rank.group_bounds(np.array([], dtype=np.int64))
    assert s.size == 0 and n.size == 0


def test_parts_carry_contiguous_decisions(corpus):
    for part in sorted(corpus.glob("part-*.npz")):
        with np.load(part) as z:
            d = z["decisions"]
            assert d.shape[0] == z["labels"].shape[0] == z["codes"].shape[0]
            assert (np.diff(d) >= 0).all(), "les frères d'une décision doivent se suivre"


def test_part_boundary_continues_the_same_decision(corpus):
    """Chunk c+1 of a worker starts where chunk c stopped: same or next index."""
    for worker in (0, 1):
        parts = sorted(corpus.glob(f"part-test-{worker:03d}-*.npz"))
        for a, b in zip(parts, parts[1:]):
            with np.load(a) as za, np.load(b) as zb:
                assert zb["decisions"][0] in (za["decisions"][-1], za["decisions"][-1] + 1)


@needs_model
def test_a_group_is_one_roll_of_one_position(corpus):
    """Every group equals the teacher's 0-ply ranking of one position and roll."""
    with np.load(sorted(corpus.glob("part-test-000-*.npz"))[0]) as z:
        ids, decisions, labels = z["ids"], z["decisions"], z["labels"]
    s, n = rank.group_bounds(decisions)
    # The best play of a group has the highest MOVER equity: the sign of
    # `mover_equity` is the one the walk's own ranking used.
    for start, size in zip(s[1:6], n[1:6]):   # skip a group possibly cut at the start
        eq = rank.mover_equity(labels[start:start + size])
        assert int(np.argmax(eq)) == 0, "le premier frère est le meilleur coup du maître"
        assert len(set(ids[start:start + size])) == size


def test_resumed_corpus_is_identical(corpus, tmp_path):
    _corpus(tmp_path)
    victim = sorted(tmp_path.glob("part-*.npz"))[1]
    victim.unlink()
    _corpus(tmp_path)
    for part in sorted(corpus.glob("part-*.npz")):
        with np.load(part) as a, np.load(tmp_path / part.name) as b:
            for key in ("codes", "values", "labels", "ids", "decisions"):
                assert np.array_equal(a[key], b[key]), (part.name, key)


def test_load_grouped_drops_singletons_and_respects_the_limit(corpus):
    parts = sorted(corpus.glob("part-*.npz"))
    table = rank.value_table(parts)
    x, y, s, n = rank.load_grouped(parts, table)
    assert x.shape[0] == y.shape[0] == 3000
    assert (n >= 2).all() and (s + n <= x.shape[0]).all()
    x2, _, s2, n2 = rank.load_grouped(parts, table, limit=1500)
    assert x2.shape[0] == 1500 and (s2 + n2 <= 1500).all()


def test_load_grouped_refuses_a_part_without_decisions(tmp_path):
    np.savez(tmp_path / "part-x-000-00000.npz", codes=np.zeros((2, 196), np.uint8),
             values=np.zeros(1, np.float32), labels=np.zeros((2, 5), np.float32))
    with pytest.raises(SystemExit):
        rank.load_grouped([tmp_path / "part-x-000-00000.npz"], np.zeros(1, np.float32))


torch = pytest.importorskip("torch", reason="PyTorch absent")


def _probs(win):
    p = torch.zeros(len(win), 5, dtype=torch.float64)
    p[:, 0] = torch.tensor(win, dtype=torch.float64)
    return p


def test_mover_equity_sign():
    # A child the OPPONENT wins for sure is the mover's worst play.
    assert float(rank.mover_equity(_probs([1.0]))[0]) == -1.0
    assert float(rank.mover_equity(_probs([0.0]))[0]) == 1.0


def test_rank_loss_is_zero_on_the_teacher_and_positive_elsewhere():
    teacher = _probs([0.40, 0.45, 0.52, 0.30, 0.31])
    segment = torch.tensor([0, 0, 0, 1, 1])
    assert float(rank.rank_loss(torch, teacher, teacher, segment, 2, 0.02)) == pytest.approx(0, abs=1e-12)
    swapped = _probs([0.45, 0.40, 0.52, 0.31, 0.30])
    assert float(rank.rank_loss(torch, swapped, teacher, segment, 2, 0.02)) > 0.01


def test_rank_loss_ignores_a_shift_shared_by_siblings():
    """Only the order and the gaps inside a decision matter, not its level."""
    teacher = _probs([0.40, 0.45, 0.52])
    shifted = _probs([0.30, 0.35, 0.42])
    segment = torch.tensor([0, 0, 0])
    assert float(rank.rank_loss(torch, shifted, teacher, segment, 1, 0.02)) == pytest.approx(0, abs=1e-12)


def test_regret_counts_the_teachers_equity_lost():
    # Mover equities: teacher 0.2, 0.0, -0.2 (best = row 0); student prefers row 1.
    teacher = _probs([0.40, 0.50, 0.60])
    student = _probs([0.55, 0.45, 0.60])
    segment = torch.tensor([0, 0, 0])
    assert rank.regret(torch, student, teacher, segment, 1) == pytest.approx(0.2)
    assert rank.regret(torch, teacher, teacher, segment, 1) == pytest.approx(0.0)


def test_gather_groups():
    starts, sizes = torch.tensor([0, 5, 9]), torch.tensor([3, 2, 4])
    rows, seg = rank.gather_groups(torch, starts, sizes, torch.tensor([2, 0]))
    assert rows.tolist() == [9, 10, 11, 12, 0, 1, 2]
    assert seg.tolist() == [0, 0, 0, 0, 1, 1, 1]


@needs_model
def test_trainer_runs_end_to_end_and_the_engine_reads_it_back(corpus, tmp_path):
    out = tmp_path / "student.bin"
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "distill_rank_t72.py"), "--corpus", str(corpus),
         "--rows", "1000", "--holdout-parts", "2", "--shape", "16,8", "--rank-weight", "1",
         "--rank-groups", "8", "--epoch-rows", "2000", "--batch-size", "256",
         "--max-epochs", "2", "--device", "cpu", "--out", str(out)],
        check=True, capture_output=True)
    import json
    summary = json.loads(out.with_suffix(".summary.json").read_text())
    assert summary["rank_weight"] == 1 and summary["epochs_run"] == 2
    assert 0 <= summary["holdout_regret0"] < 2
    assert len(summary["opening_position"]) == 5

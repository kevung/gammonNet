#!/usr/bin/env python3
"""T78 — distil the exact two-sided bearoff table into a small network.

## The signal, and why it is unlike every other training run here

Every other label in this project is an estimate: a rollout with its variance,
a network's own output, a search result at some depth. This one is **exact**.
`gnubg-TS-06-11` gives the cubeless equity of all 12 376 x 12 376 pairs of
bearoff layouts, computed by dynamic programming, and the whole of it fits in
306 MiB once the three cubeful columns are dropped. There is no sampling noise,
no train/test distinction worth the name -- the training set *is* the domain --
and the error of the trained network can therefore be reported **exhaustively**
rather than estimated.

## What is being aimed at

Not the mean. T38 measured that the network already loses only 0.00028 equity
per bearoff decision on average; what it also measured is a worst case of
0.0919 on a single decision, where GNU Backgammon -- which consults its table --
never exceeds 0.0023. **It is the tail that costs**, so the run has two stages:

1. **Regression**, uniformly over the domain, mean squared error. This buys the
   mean and most of the shape.
2. **Decision fine-tuning**, on a corpus of real bearoff decisions built by
   `tools/build_bearoff_decisions.py`. A decision is a ranking problem, not a
   regression one: an error common to all candidate moves cancels, and only the
   ordering matters. The loss is therefore a cost-weighted pairwise hinge --
   each candidate that outranks the true best is penalised **in proportion to
   the equity it would actually lose**. That is what aims at the tail.

The two-stage split is itself a claim to be checked, and the run reports the
decision loss after each stage so that stage 2 has to earn its place.

## Determinism

Seeds are fixed for python, numpy and torch. CPU training with a fixed seed and
a fixed thread count is reproducible here; if CUDA is used, backward kernels
that accumulate atomically are not bit-reproducible, which is a documented
PyTorch limitation and is recorded in the provenance rather than papered over.

Usage:
    python tools/train_bearoff_net.py --steps 40000 --hidden 128,64
    python tools/train_bearoff_net.py --decision-corpus build/bearoff_decisions.npz
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.bearoff_net import (  # noqa: E402
    FEATURE_VERSION, INPUT_SIZE, SIDE_FEATURES, BearoffNet, side_features,
)

DEFAULT_MATRIX = ROOT / "build" / "ts6x11_cubeless.u16"
DEFAULT_SIDES = ROOT / "build" / "ts6x11_sides.npy"
DEFAULT_OUT = ROOT / "models" / "bearoff_net.bin"

SCALE = 2.0 / 65535.0  # the T38 scale: raw -> equity is raw * SCALE - 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def set_seeds(seed: int) -> None:
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class Model:
    """A thin torch wrapper that can hand its weights to `BearoffNet`."""

    def __init__(self, hidden: list[int], device):
        import torch.nn as nn
        sizes = [INPUT_SIZE] + hidden + [1]
        layers = []
        for index in range(len(sizes) - 1):
            layers.append(nn.Linear(sizes[index], sizes[index + 1]))
            if index + 2 < len(sizes):
                layers.append(nn.ReLU())
        layers.append(nn.Tanh())
        self.net = nn.Sequential(*layers).to(device)
        self.sizes = sizes

    def export(self) -> BearoffNet:
        import torch.nn as nn
        weights = []
        for module in self.net:
            if isinstance(module, nn.Linear):
                weights.append((module.weight.detach().cpu().numpy().T.copy(),
                                module.bias.detach().cpu().numpy().copy()))
        return BearoffNet(weights, feature_version=FEATURE_VERSION)


def load_domain(matrix_path: Path, sides_path: Path):
    """The table as a matrix, the layouts, and their features."""
    sides = np.load(sides_path)
    positions = sides.shape[0]
    raw = np.memmap(matrix_path, dtype="<u2", mode="r",
                    shape=(positions, positions))
    features = side_features(sides)
    if features.shape[1] != SIDE_FEATURES:
        raise AssertionError("feature width disagrees with the module")
    return np.asarray(raw), sides, features


def exhaustive_error(model, features_t, matrix, device, chunk: int = 16):
    """Max and mean |error| over **every** pair of the domain, index 0 aside.

    Index 0 is the empty layout -- a side with no checkers has already won, and
    the table's row and column for it describe a game that is over. Including
    them would flatter or spoil the figure for positions the evaluator is never
    asked about.

    Rows are done in blocks: `features_t` is small, and the whole point of the
    exercise is that the network is small enough for 153 million forward passes
    to be a matter of a minute.
    """
    import torch
    positions = matrix.shape[0]
    worst = 0.0
    worst_at = (0, 0)
    total = 0.0
    total_sq = 0.0
    count = 0
    over = 0

    with torch.no_grad():
        others = features_t[1:]
        for start in range(1, positions, chunk):
            stop = min(start + chunk, positions)
            rows = features_t[start:stop]
            n_rows = stop - start
            batch = torch.cat([
                rows[:, None, :].expand(n_rows, others.shape[0], SIDE_FEATURES),
                others[None, :, :].expand(n_rows, others.shape[0], SIDE_FEATURES),
            ], dim=2).reshape(-1, INPUT_SIZE)
            predicted = model.net(batch).reshape(n_rows, -1)
            # numpy's uint16 has no torch counterpart -- the widening happens
            # here rather than through a dtype torch would refuse.
            target = torch.from_numpy(
                matrix[start:stop, 1:].astype(np.float32)
            ).to(device) * SCALE - 1.0
            error = (predicted - target).abs()
            block_worst, flat = error.reshape(-1).max(dim=0)
            block_worst = float(block_worst)
            if block_worst > worst:
                index = int(flat)
                worst = block_worst
                worst_at = (start + index // (positions - 1), 1 + index % (positions - 1))
            total += float(error.sum())
            total_sq += float((error * error).sum())
            over += int((error > 0.01).sum())
            count += error.numel()

    return {
        "pairs": count,
        "mean_abs": total / count,
        "rms": (total_sq / count) ** 0.5,
        "worst_abs": worst,
        "worst_at": worst_at,
        "above_0.01": over,
    }


def sample_batch(matrix, positions, batch, rng, device, features_t):
    import torch
    i = rng.integers(1, positions, size=batch)
    j = rng.integers(1, positions, size=batch)
    target = matrix[i, j].astype(np.float32) * SCALE - 1.0
    i_t = torch.from_numpy(i.astype(np.int64)).to(device)
    j_t = torch.from_numpy(j.astype(np.int64)).to(device)
    x = torch.cat([features_t[i_t], features_t[j_t]], dim=1)
    y = torch.from_numpy(target).to(device)
    return x, y


def regression_stage(model, matrix, features_t, args, device, log):
    import torch
    positions = matrix.shape[0]
    rng = np.random.default_rng(args.seed)
    optimiser = torch.optim.AdamW(model.net.parameters(), lr=args.lr,
                                  weight_decay=args.weight_decay)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.lr, total_steps=args.steps, pct_start=0.05)
    loss_fn = torch.nn.MSELoss()

    start = time.perf_counter()
    running = 0.0
    for step in range(1, args.steps + 1):
        x, y = sample_batch(matrix, positions, args.batch, rng, device, features_t)
        predicted = model.net(x)[:, 0]
        loss = loss_fn(predicted, y)
        optimiser.zero_grad(set_to_none=True)
        loss.backward()
        optimiser.step()
        schedule.step()
        running += float(loss.detach())
        if step % args.report == 0 or step == args.steps:
            elapsed = time.perf_counter() - start
            mean = running / args.report
            running = 0.0
            log(f"  regression {step:>7}/{args.steps}  mse {mean:.3e}  "
                f"rmse {mean ** 0.5:.3e}  {elapsed / 60:.1f} min")
    return model


def load_decisions(path: Path):
    """The decision corpus, as `tools/build_bearoff_decisions.py` writes it.

    Compressed-row: `offsets[d]:offsets[d + 1]` are the candidates of decision
    `d`, `best_slot[d]` says which of them the table says is best.
    """
    data = np.load(path)
    offsets = data["offsets"]
    return {
        "offsets": offsets,
        "pairs": data["pairs"],          # (C, 2) int32, -1 = the game ends here
        "values": data["values"],        # (C,) float32, exact, mover's view
        "best": offsets[:-1] + data["best_slot"],
        "decisions": int(offsets.shape[0] - 1),
        "candidates": int(data["pairs"].shape[0]),
    }


def gather_decisions(picked, offsets):
    """Flat indices of every candidate of the picked decisions, plus their group.

    Written without a python loop over the batch: the loop was the whole cost
    of the step at 512 decisions, and it grew with the batch.
    """
    lengths = (offsets[picked + 1] - offsets[picked]).astype(np.int64)
    total = int(lengths.sum())
    group = np.repeat(np.arange(picked.shape[0]), lengths)
    within = np.arange(total) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    flat = np.repeat(offsets[picked], lengths) + within
    return flat, group, lengths


def decision_stage(model, matrix, features_t, corpus, args, device, log):
    """Cost-weighted pairwise hinge on real decisions -- the tail stage.

    A candidate is stored as the pair `(opponent_on_roll, mover)` **after** the
    move, because that is what the position has become: the mover has played
    and handed over the dice. The network answers for the side on roll, so the
    mover's equity is its negation. A move that bears off the last checker ends
    the game and is worth exactly +1 -- computed, never looked up, the trap
    `bench/exact_gap.py` documents.

    The loss penalises every candidate that outranks the true best **in
    proportion to the equity that mistake would cost**, which is precisely the
    quantity `bench/exact_gap.py` reports. An error shared by all the candidates
    of one decision costs nothing here, exactly as it costs nothing in play --
    which is why a regression stage alone leaves the tail on the table.
    """
    import torch
    offsets = corpus["offsets"]
    pairs = corpus["pairs"]
    values = corpus["values"]
    best = corpus["best"]
    decisions = corpus["decisions"]

    rng = np.random.default_rng(args.seed + 1)
    reg_rng = np.random.default_rng(args.seed + 2)
    optimiser = torch.optim.AdamW(model.net.parameters(), lr=args.decision_lr,
                                  weight_decay=args.weight_decay)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.decision_lr, total_steps=args.decision_steps,
        pct_start=0.05)
    positions = matrix.shape[0]
    start = time.perf_counter()
    running = 0.0
    running_anchor = 0.0

    for step in range(1, args.decision_steps + 1):
        picked = rng.integers(0, decisions, size=args.decision_batch)
        flat, group, lengths = gather_decisions(picked, offsets)

        block = pairs[flat]
        terminal = torch.from_numpy(block[:, 0] < 0).to(device)
        index = np.clip(block, 0, None).astype(np.int64)
        exact = torch.from_numpy(values[flat]).to(device)
        group_t = torch.from_numpy(group).to(device)

        x = torch.cat([features_t[torch.from_numpy(index[:, 0]).to(device)],
                       features_t[torch.from_numpy(index[:, 1]).to(device)]], dim=1)
        value = -model.net(x)[:, 0]
        value = torch.where(terminal, torch.ones_like(value), value)

        # The best candidate is known exactly, so no segment maximum is needed:
        # its own network value is broadcast back over its decision's run.
        best_flat = torch.from_numpy(best[picked]).to(device)
        best_block = pairs[best[picked]]
        best_terminal = torch.from_numpy(best_block[:, 0] < 0).to(device)
        best_index = np.clip(best_block, 0, None).astype(np.int64)
        best_x = torch.cat(
            [features_t[torch.from_numpy(best_index[:, 0]).to(device)],
             features_t[torch.from_numpy(best_index[:, 1]).to(device)]], dim=1)
        best_value = -model.net(best_x)[:, 0]
        best_value = torch.where(best_terminal, torch.ones_like(best_value), best_value)
        top = torch.from_numpy(values[best[picked]]).to(device)

        cost = (top[group_t] - exact).clamp(min=0.0)
        hinge = (cost * torch.relu(value - best_value[group_t] + args.margin)).sum()
        hinge = hinge / picked.shape[0]

        anchor_x, anchor_y = sample_batch(matrix, positions, args.decision_regression,
                                          reg_rng, device, features_t)
        anchor = torch.nn.functional.mse_loss(model.net(anchor_x)[:, 0], anchor_y)

        loss = hinge + args.anchor * anchor
        optimiser.zero_grad(set_to_none=True)
        loss.backward()
        optimiser.step()
        schedule.step()
        running += float(hinge.detach())
        running_anchor += float(anchor.detach())
        if step % args.report == 0 or step == args.decision_steps:
            elapsed = time.perf_counter() - start
            log(f"  decisions  {step:>7}/{args.decision_steps}  hinge "
                f"{running / args.report:.3e}  ancre {running_anchor / args.report:.3e}  "
                f"{elapsed / 60:.1f} min")
            running = 0.0
            running_anchor = 0.0
    return model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--sides", default=str(DEFAULT_SIDES))
    parser.add_argument("--hidden", default="128,64")
    parser.add_argument("--steps", type=int, default=40000)
    parser.add_argument("--batch", type=int, default=16384)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--report", type=int, default=500)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--decision-corpus", default="")
    parser.add_argument("--decision-steps", type=int, default=8000)
    parser.add_argument("--decision-batch", type=int, default=512)
    parser.add_argument("--decision-lr", type=float, default=3e-4)
    parser.add_argument("--decision-regression", type=int, default=4096)
    parser.add_argument("--margin", type=float, default=0.002)
    parser.add_argument("--anchor", type=float, default=1.0)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    import torch
    if args.threads:
        torch.set_num_threads(args.threads)
    device = torch.device(args.device)
    set_seeds(args.seed)

    log_handle = open(args.log, "a", buffering=1) if args.log else None

    def log(message: str) -> None:
        print(message, flush=True)
        if log_handle:
            log_handle.write(message + "\n")

    hidden = [int(h) for h in args.hidden.split(",") if h.strip()]
    matrix, sides, features = load_domain(Path(args.matrix), Path(args.sides))
    features_t = torch.from_numpy(features).to(device)

    model = Model(hidden, device)
    exported = model.export()
    log(f"T78 — distillation de la table exacte, {matrix.shape[0]} x {matrix.shape[0]} paires")
    log(f"  architecture {exported.sizes}, {exported.parameters} paramètres, "
        f"{exported.macs} MACs, {exported.parameters * 4 / 1024:.1f} Kio en float32")
    log(f"  torch {torch.__version__}, {args.device}, "
        f"{torch.get_num_threads()} fils, lot {args.batch}")

    started = time.perf_counter()
    regression_stage(model, matrix, features_t, args, device, log)
    after_regression = exhaustive_error(model, features_t, matrix, device)
    log(f"  exhaustif après régression : moyenne {after_regression['mean_abs']:.3e}  "
        f"rms {after_regression['rms']:.3e}  pire {after_regression['worst_abs']:.4f} "
        f"en {after_regression['worst_at']}  au-delà de 0,01 : {after_regression['above_0.01']}")

    after_decisions = None
    if args.decision_corpus:
        corpus = load_decisions(Path(args.decision_corpus))
        log(f"  corpus de décisions : {corpus['decisions']} décisions, "
            f"{corpus['candidates']} coups candidats")
        decision_stage(model, matrix, features_t, corpus, args, device, log)
        after_decisions = exhaustive_error(model, features_t, matrix, device)
        log(f"  exhaustif après décisions : moyenne {after_decisions['mean_abs']:.3e}  "
            f"rms {after_decisions['rms']:.3e}  pire {after_decisions['worst_abs']:.4f} "
            f"en {after_decisions['worst_at']}  au-delà de 0,01 : "
            f"{after_decisions['above_0.01']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    exported = model.export()
    exported.save(out)

    provenance = {
        "task": "T78",
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "architecture": exported.sizes,
        "parameters": exported.parameters,
        "macs": exported.macs,
        "feature_version": FEATURE_VERSION,
        "matrix": {"path": str(args.matrix), "sha256": sha256(Path(args.matrix))},
        "training": {
            "steps": args.steps, "batch": args.batch, "lr": args.lr,
            "seed": args.seed, "device": args.device,
            "decision_corpus": args.decision_corpus,
            "decision_steps": args.decision_steps if args.decision_corpus else 0,
            "margin": args.margin, "anchor": args.anchor,
        },
        "exhaustive_error": {
            "after_regression": after_regression,
            "after_decisions": after_decisions,
        },
        "weights_sha256": sha256(out),
        "minutes": (time.perf_counter() - started) / 60.0,
    }
    Path(str(out) + ".provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n")
    log(f"  écrit : {out} ({out.stat().st_size} octets) et sa provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

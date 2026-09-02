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
never exceeds 0.0023. **It is the tail that costs**, so the run has three
stages, and only the first is ordinary:

1. **Regression**, uniformly over the domain, mean squared error. This buys the
   mean and most of the shape.
2. **Exhaustive mining.** The domain is finite, so the network's worst pairs
   are not sampled for -- all 153 million are scored, the worst million are
   kept, and training continues on them mixed with fresh uniform pairs. This is
   the stage that attacks the maximum error, and the maximum error is what
   bounds the tail: misranking two moves gives up at most **twice** the largest
   error the evaluator can make anywhere. That bound holds over the whole
   domain, which is something no sampled measurement can offer.

3. **Decision fine-tuning**, on a corpus of real bearoff decisions built by
   `tools/build_bearoff_decisions.py`. A decision is a ranking problem, not a
   regression one: an error common to all candidate moves cancels, and only the
   ordering matters. The loss is therefore a cost-weighted pairwise hinge --
   each candidate that outranks the true best is penalised **in proportion to
   the equity it would actually lose**. That is what aims at the tail.

Each stage is a claim to be checked, and the run reports the exhaustive error
after every one of them, so a stage that buys nothing says so.

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
    FEATURE_VERSION, IDENTITY, LAYOUTS, SIDE_FEATURES, TANH, BearoffNet,
    side_features,
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
    """A thin torch wrapper that can hand its weights to `BearoffNet`.

    It owns the side encoding as well as the layers: a side is addressed by its
    combinatorial rank everywhere in this script, so that the optional layout
    code is a lookup on the same index the features are.
    """

    def __init__(self, hidden: list[int], device, features, activation: int = TANH,
                 embedding: int = 0, outputs: int = 1):
        import torch
        import torch.nn as nn
        self.features = features
        self.embedding = (nn.Embedding(LAYOUTS, embedding).to(device)
                          if embedding else None)
        if self.embedding is not None:
            nn.init.normal_(self.embedding.weight, std=0.1)
        self.side_width = SIDE_FEATURES + embedding

        sizes = [2 * self.side_width] + hidden + [outputs]
        layers = []
        for index in range(len(sizes) - 1):
            layers.append(nn.Linear(sizes[index], sizes[index + 1]))
            if index + 2 < len(sizes):
                layers.append(nn.ReLU())
        if activation == TANH:
            layers.append(nn.Tanh())
        self.net = nn.Sequential(*layers).to(device)
        self.sizes = sizes
        self.activation = activation
        self.outputs = outputs

    def parameters(self):
        import itertools
        if self.embedding is None:
            return self.net.parameters()
        return itertools.chain(self.net.parameters(), self.embedding.parameters())

    def encode(self, index):
        import torch
        block = self.features[index]
        if self.embedding is None:
            return block
        return torch.cat([block, self.embedding(index)], dim=1)

    def value(self, i, j):
        """The network's equities for the side `i` on roll against `j`.

        `(N,)` for a cubeless network, `(N, 4)` for a cubeful one. The checker
        play only ever reads column 0 -- the cube columns rank nothing.
        """
        import torch
        out = self.net(torch.cat([self.encode(i), self.encode(j)], dim=1))
        return out[:, 0] if self.outputs == 1 else out

    def export(self) -> BearoffNet:
        import torch.nn as nn
        weights = []
        for module in self.net:
            if isinstance(module, nn.Linear):
                weights.append((module.weight.detach().cpu().numpy().T.copy(),
                                module.bias.detach().cpu().numpy().copy()))
        table = (None if self.embedding is None
                 else self.embedding.weight.detach().cpu().numpy().copy())
        return BearoffNet(weights, feature_version=FEATURE_VERSION,
                          activation=self.activation, embedding=table)


def load_domain(matrix_path: Path, sides_path: Path):
    """The table as a matrix, the layouts, their features, and the column count.

    One column is T78's cubeless equity; four are T80's full row -- cubeless
    then the three cubeful equities by cube ownership. The count is **deduced
    from the file's size** rather than passed in: a mismatch between the file
    and the flag would train a network on shifted labels and say nothing.
    """
    sides = np.load(sides_path)
    positions = sides.shape[0]
    entries = matrix_path.stat().st_size // 2
    columns = entries // (positions * positions)
    if columns * positions * positions * 2 != matrix_path.stat().st_size:
        raise AssertionError(f"{matrix_path} : taille incompatible avec "
                             f"{positions} positions")
    shape = ((positions, positions) if columns == 1
             else (positions, positions, columns))
    raw = np.memmap(matrix_path, dtype="<u2", mode="r", shape=shape)
    features = side_features(sides)
    if features.shape[1] != SIDE_FEATURES:
        raise AssertionError("feature width disagrees with the module")
    return np.asarray(raw), sides, features, columns


def scan_domain(model, matrix, device, chunk: int = 16, keep: int = 0):
    """Every pair of the domain, index 0 aside: the error, and the worst of it.

    Index 0 is the empty layout -- a side with no checkers has already won, and
    that row and column describe a game that is over. Including them would
    flatter or spoil a figure for positions the evaluator is never asked about.

    `keep` asks for the indices of the `keep` worst pairs, which is what the
    mining stage trains on. They are gathered chunk by chunk (the best of each
    block, then the best of those) rather than by sorting 153 million values.
    With several columns, a pair is as hard as its **worst** column.

    **Why this is worth a minute of machine.** The domain is finite and fully
    known, so `worst_abs` is not an estimate of the worst error -- it *is* the
    worst error. And it bounds what no sampled measurement can bound: if the
    evaluator misranks two moves, the equity it gives up is at most twice the
    largest error it can make anywhere.
    """
    import torch
    positions = matrix.shape[0]
    columns = model.outputs
    worst = 0.0
    worst_at = (0, 0)
    total = np.zeros(columns)
    total_sq = np.zeros(columns)
    per_column_worst = np.zeros(columns)
    count = 0
    over = 0
    pool_error: list[np.ndarray] = []
    pool_index: list[np.ndarray] = []
    per_chunk = max(1, keep // 64) if keep else 0

    with torch.no_grad():
        cols = torch.arange(1, positions, device=device)
        for start in range(1, positions, chunk):
            stop = min(start + chunk, positions)
            n_rows = stop - start
            rows = torch.arange(start, stop, device=device)
            i = rows.repeat_interleave(positions - 1)
            j = cols.repeat(n_rows)
            predicted = model.value(i, j).reshape(n_rows, positions - 1, columns)
            # numpy's uint16 has no torch counterpart -- the widening happens
            # here rather than through a dtype torch would refuse.
            block = matrix[start:stop, 1:]
            target = torch.from_numpy(
                np.ascontiguousarray(block).astype(np.float32).reshape(
                    n_rows, positions - 1, columns)
            ).to(device) * SCALE - 1.0
            error = (predicted - target).abs()

            flat_worst = error.amax(dim=2)
            block_worst, flat = flat_worst.reshape(-1).max(dim=0)
            block_worst = float(block_worst)
            if block_worst > worst:
                index = int(flat)
                worst = block_worst
                worst_at = (start + index // (positions - 1), 1 + index % (positions - 1))
            total += error.sum(dim=(0, 1)).cpu().numpy()
            total_sq += (error * error).sum(dim=(0, 1)).cpu().numpy()
            per_column_worst = np.maximum(per_column_worst,
                                          error.amax(dim=(0, 1)).cpu().numpy())
            over += int((error[:, :, 0] > 0.01).sum())
            count += n_rows * (positions - 1)

            if per_chunk:
                flattened = flat_worst.reshape(-1)
                take = min(per_chunk, flattened.numel())
                values, indices = torch.topk(flattened, take, sorted=False)
                pool_error.append(values.cpu().numpy())
                pool_index.append(
                    np.stack([start + indices.cpu().numpy() // (positions - 1),
                              1 + indices.cpu().numpy() % (positions - 1)], axis=1))

    stats = {
        "pairs": count,
        "mean_abs": float(total[0] / count),
        "rms": float((total_sq[0] / count) ** 0.5),
        "worst_abs": float(per_column_worst[0]),
        "worst_at": worst_at,
        "above_0.01": over,
        "guaranteed_decision_loss": 2.0 * float(per_column_worst[0]),
    }
    if columns > 1:
        names = ["cubeless", "owned", "centered", "opponent_owns"]
        stats["columns"] = {
            names[k]: {"mean_abs": float(total[k] / count),
                       "rms": float((total_sq[k] / count) ** 0.5),
                       "worst_abs": float(per_column_worst[k])}
            for k in range(columns)}
    if not keep:
        return stats, None

    errors = np.concatenate(pool_error)
    indices = np.concatenate(pool_index)
    take = min(keep, errors.shape[0])
    chosen = np.argpartition(-errors, take - 1)[:take]
    return stats, indices[chosen]


def exhaustive_error(model, matrix, device, chunk: int = 16):
    stats, _ = scan_domain(model, matrix, device, chunk=chunk)
    return stats


def sample_batch(model, matrix, positions, batch, rng, device):
    """A uniform batch of pairs, with the table's own value as the target."""
    import torch
    i = rng.integers(1, positions, size=batch)
    j = rng.integers(1, positions, size=batch)
    target = np.ascontiguousarray(matrix[i, j]).astype(np.float32) * SCALE - 1.0
    i_t = torch.from_numpy(i.astype(np.int64)).to(device)
    j_t = torch.from_numpy(j.astype(np.int64)).to(device)
    return i_t, j_t, torch.from_numpy(target).to(device)


def regression_stage(model, matrix, args, device, log):
    import torch
    positions = matrix.shape[0]
    rng = np.random.default_rng(args.seed)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr,
                                  weight_decay=args.weight_decay)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.lr, total_steps=args.steps, pct_start=0.05)
    loss_fn = torch.nn.MSELoss()

    start = time.perf_counter()
    running = 0.0
    for step in range(1, args.steps + 1):
        i, j, y = sample_batch(model, matrix, positions, args.batch, rng, device)
        loss = loss_fn(model.value(i, j), y)
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


def mining_stage(model, matrix, args, device, log):
    """Chase the maximum error itself, on the pairs that actually carry it.

    The domain is finite, so the hardest pairs are not guessed at: they are
    *found*, by scoring all 153 million and keeping the worst. Each round
    retrains on a mixture of those and of fresh uniform pairs -- the uniform
    half is what keeps the network from trading the bulk of the domain away for
    its tail, and the run reports both figures after every round so the trade is
    visible rather than assumed.
    """
    import torch
    positions = matrix.shape[0]
    rng = np.random.default_rng(args.seed + 3)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.mine_lr,
                                  weight_decay=args.weight_decay)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.mine_lr,
        total_steps=args.mine_rounds * args.mine_steps, pct_start=0.05)
    loss_fn = torch.nn.MSELoss()
    hard_size = max(1, int(args.batch * args.mine_mix))
    easy_size = args.batch - hard_size

    for round_index in range(1, args.mine_rounds + 1):
        started = time.perf_counter()
        stats, hard = scan_domain(model, matrix, device, keep=args.mine_keep)
        log(f"  mine {round_index}/{args.mine_rounds}  moyenne {stats['mean_abs']:.3e}  "
            f"rms {stats['rms']:.3e}  pire {stats['worst_abs']:.5f}  "
            f"borne décision {stats['guaranteed_decision_loss']:.5f}  "
            f"balayage {time.perf_counter() - started:.0f} s")

        running = 0.0
        for step in range(1, args.mine_steps + 1):
            picked = rng.integers(0, hard.shape[0], size=hard_size)
            i = np.concatenate([hard[picked, 0],
                                rng.integers(1, positions, size=easy_size)])
            j = np.concatenate([hard[picked, 1],
                                rng.integers(1, positions, size=easy_size)])
            target = np.ascontiguousarray(matrix[i, j]).astype(np.float32) * SCALE - 1.0
            i_t = torch.from_numpy(i.astype(np.int64)).to(device)
            j_t = torch.from_numpy(j.astype(np.int64)).to(device)
            y = torch.from_numpy(target).to(device)
            loss = loss_fn(model.value(i_t, j_t), y)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            optimiser.step()
            schedule.step()
            running += float(loss.detach())
            if step % args.report == 0:
                log(f"    mine {round_index} {step:>6}/{args.mine_steps}  "
                    f"mse {running / args.report:.3e}")
                running = 0.0
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


def decision_stage(model, matrix, corpus, args, device, log):
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
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.decision_lr,
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

        raw = model.value(torch.from_numpy(index[:, 0]).to(device),
                          torch.from_numpy(index[:, 1]).to(device))
        # Le classement des coups ne lit que l'équité cubeless : les colonnes
        # de videau ne trient rien.
        value = -(raw if model.outputs == 1 else raw[:, 0])
        value = torch.where(terminal, torch.ones_like(value), value)

        # The best candidate is known exactly, so no segment maximum is needed:
        # its own network value is broadcast back over its decision's run.
        best_flat = torch.from_numpy(best[picked]).to(device)
        best_block = pairs[best[picked]]
        best_terminal = torch.from_numpy(best_block[:, 0] < 0).to(device)
        best_index = np.clip(best_block, 0, None).astype(np.int64)
        best_raw = model.value(torch.from_numpy(best_index[:, 0]).to(device),
                               torch.from_numpy(best_index[:, 1]).to(device))
        best_value = -(best_raw if model.outputs == 1 else best_raw[:, 0])
        best_value = torch.where(best_terminal, torch.ones_like(best_value), best_value)
        top = torch.from_numpy(values[best[picked]]).to(device)

        cost = (top[group_t] - exact).clamp(min=0.0)
        hinge = (cost * torch.relu(value - best_value[group_t] + args.margin)).sum()
        hinge = hinge / picked.shape[0]

        anchor_i, anchor_j, anchor_y = sample_batch(
            model, matrix, positions, args.decision_regression, reg_rng, device)
        anchor = torch.nn.functional.mse_loss(model.value(anchor_i, anchor_j), anchor_y)

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


def cube_stage(model, matrix, args, device, log):
    """Le quatrième étage : viser la DÉCISION de videau, pas ses équités.

    Une décision de videau se réduit à un signe. La marge exacte

        m* = e_nd* - min(2 x e_opp*, 1)

    est positive quand il ne faut pas doubler, négative quand il faut, et sa
    valeur absolue **est** l'équité que coûterait le verdict inverse. La perte
    est donc une charnière sur le signe, pondérée par ce coût — la même forme
    que l'étage par décision de coup, et pour la même raison : une erreur
    commune aux deux branches ne change pas le verdict, seule leur différence
    le fait.

    Les deux états de possession se jugent ensemble, chacun avec sa colonne :
    « possédé » lit la colonne 1, « centré » la colonne 2, et les deux se
    comparent au même double, qui donne le videau à l'adversaire (colonne 3).
    """
    import torch
    positions = matrix.shape[0]
    rng = np.random.default_rng(args.seed + 4)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.cube_lr,
                                  weight_decay=args.weight_decay)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.cube_lr, total_steps=args.cube_steps, pct_start=0.05)
    start = time.perf_counter()
    running = 0.0
    running_anchor = 0.0

    for step in range(1, args.cube_steps + 1):
        i, j, exact = sample_batch(model, matrix, positions, args.cube_batch,
                                   rng, device)
        predicted = model.value(i, j)

        exact_double = torch.clamp(2.0 * exact[:, 3], max=1.0)
        predicted_double = torch.clamp(2.0 * predicted[:, 3], max=1.0)

        hinge = 0.0
        for column in (1, 2):
            exact_margin = exact[:, column] - exact_double
            margin = predicted[:, column] - predicted_double
            cost = exact_margin.abs()
            hinge = hinge + (cost * torch.relu(
                args.cube_margin - torch.sign(exact_margin) * margin)).mean()

        anchor = torch.nn.functional.mse_loss(predicted, exact)
        loss = hinge + args.anchor * anchor
        optimiser.zero_grad(set_to_none=True)
        loss.backward()
        optimiser.step()
        schedule.step()
        running += float(hinge.detach())
        running_anchor += float(anchor.detach())
        if step % args.report == 0 or step == args.cube_steps:
            log(f"  videau     {step:>7}/{args.cube_steps}  charnière "
                f"{running / args.report:.3e}  ancre {running_anchor / args.report:.3e}  "
                f"{(time.perf_counter() - start) / 60:.1f} min")
            running = 0.0
            running_anchor = 0.0
    return model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--sides", default=str(DEFAULT_SIDES))
    parser.add_argument("--hidden", default="128,64")
    parser.add_argument("--output", default="tanh", choices=["tanh", "linear"],
                        help="activation de sortie ; « linear » ne sature pas")
    parser.add_argument("--embedding", type=int, default=0,
                        help="largeur du code appris par disposition (0 : aucun)")
    parser.add_argument("--steps", type=int, default=40000)
    parser.add_argument("--batch", type=int, default=16384)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--report", type=int, default=500)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--mine-rounds", type=int, default=0,
                        help="tours de fouille exhaustive des pires paires")
    parser.add_argument("--mine-steps", type=int, default=4000)
    parser.add_argument("--mine-keep", type=int, default=1000000)
    parser.add_argument("--mine-mix", type=float, default=0.5,
                        help="part du lot tirée des pires paires")
    parser.add_argument("--mine-lr", type=float, default=5e-4)
    parser.add_argument("--decision-corpus", default="")
    parser.add_argument("--decision-steps", type=int, default=8000)
    parser.add_argument("--decision-batch", type=int, default=512)
    parser.add_argument("--decision-lr", type=float, default=3e-4)
    parser.add_argument("--decision-regression", type=int, default=4096)
    parser.add_argument("--margin", type=float, default=0.002)
    parser.add_argument("--anchor", type=float, default=1.0)
    parser.add_argument("--cube-steps", type=int, default=0,
                        help="étage de décision de videau (réseau à quatre sorties)")
    parser.add_argument("--cube-batch", type=int, default=8192)
    parser.add_argument("--cube-lr", type=float, default=2e-4)
    parser.add_argument("--cube-margin", type=float, default=0.002)
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
    matrix, sides, features, columns = load_domain(Path(args.matrix), Path(args.sides))
    features_t = torch.from_numpy(features).to(device)

    model = Model(hidden, device, features_t,
                  activation=TANH if args.output == "tanh" else IDENTITY,
                  embedding=args.embedding, outputs=columns)
    exported = model.export()
    log(f"Distillation de la table exacte, {matrix.shape[0]} x {matrix.shape[0]} paires, "
        f"{columns} colonne(s) : "
        f"{'équité cubeless' if columns == 1 else 'cubeless + les trois cubeful'}")
    log(f"  architecture {exported.sizes}, {exported.parameters} paramètres, "
        f"{exported.macs} MACs, {exported.parameters * 4 / 1024:.1f} Kio en float32")
    log(f"  torch {torch.__version__}, {args.device}, "
        f"{torch.get_num_threads()} fils, lot {args.batch}")

    started = time.perf_counter()
    regression_stage(model, matrix, args, device, log)
    after_regression = exhaustive_error(model, matrix, device)
    log(f"  exhaustif après régression : moyenne {after_regression['mean_abs']:.3e}  "
        f"rms {after_regression['rms']:.3e}  pire {after_regression['worst_abs']:.4f} "
        f"en {after_regression['worst_at']}  au-delà de 0,01 : {after_regression['above_0.01']}")

    after_mining = None
    if args.mine_rounds:
        mining_stage(model, matrix, args, device, log)
        after_mining = exhaustive_error(model, matrix, device)
        log(f"  exhaustif après fouille : moyenne {after_mining['mean_abs']:.3e}  "
            f"rms {after_mining['rms']:.3e}  pire {after_mining['worst_abs']:.5f}  "
            f"borne décision {after_mining['guaranteed_decision_loss']:.5f}")

    after_decisions = None
    if args.decision_corpus:
        corpus = load_decisions(Path(args.decision_corpus))
        log(f"  corpus de décisions : {corpus['decisions']} décisions, "
            f"{corpus['candidates']} coups candidats")
        decision_stage(model, matrix, corpus, args, device, log)
        after_decisions = exhaustive_error(model, matrix, device)
        log(f"  exhaustif après décisions : moyenne {after_decisions['mean_abs']:.3e}  "
            f"rms {after_decisions['rms']:.3e}  pire {after_decisions['worst_abs']:.4f} "
            f"en {after_decisions['worst_at']}  au-delà de 0,01 : "
            f"{after_decisions['above_0.01']}")

    after_cube = None
    if args.cube_steps:
        if columns != 4:
            raise SystemExit("l'étage de videau demande les quatre colonnes "
                             "(--matrix build/ts6x11_cubeful.u16)")
        cube_stage(model, matrix, args, device, log)
        after_cube = exhaustive_error(model, matrix, device)
        log(f"  exhaustif après videau : moyenne {after_cube['mean_abs']:.3e}  "
            f"rms {after_cube['rms']:.3e}  pire {after_cube['worst_abs']:.5f}")
        if "columns" in after_cube:
            for name, block in after_cube["columns"].items():
                log(f"    {name:<14} moyenne {block['mean_abs']:.3e}  "
                    f"pire {block['worst_abs']:.5f}")

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
        "outputs": columns,
        "output": args.output,
        "embedding": args.embedding,
        "matrix": {"path": str(args.matrix), "sha256": sha256(Path(args.matrix))},
        "training": {
            "steps": args.steps, "batch": args.batch, "lr": args.lr,
            "seed": args.seed, "device": args.device,
            # Le nombre de fils fait partie de la recette : sur CPU, torch n'est
            # reproductible au bit près qu'à nombre de fils constant (mesuré en
            # T78 — deux lignées à 6 et 7 fils s'écartent de 2 % sur l'erreur
            # moyenne et de 10 % sur le maximum).
            "threads": torch.get_num_threads(),
            "mine_rounds": args.mine_rounds, "mine_steps": args.mine_steps,
            "mine_keep": args.mine_keep, "mine_mix": args.mine_mix,
            "decision_corpus": args.decision_corpus,
            "decision_steps": args.decision_steps if args.decision_corpus else 0,
            "margin": args.margin, "anchor": args.anchor,
            "cube_steps": args.cube_steps, "cube_batch": args.cube_batch,
            "cube_lr": args.cube_lr, "cube_margin": args.cube_margin,
        },
        "exhaustive_error": {
            "after_regression": after_regression,
            "after_mining": after_mining,
            "after_decisions": after_decisions,
            "after_cube": after_cube,
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

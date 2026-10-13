#!/usr/bin/env python3
"""T72 — the volume -> quality curve of 0-ply distillation, from corpus parts.

## The question

T72prep (`docs/mesures/2026-09-03-T72prep-taille-et-distillation.md`): at the
teacher's OWN size, a network redistilled on 800 000 0-ply labels loses
0.00990 per contested decision against the teacher's 0.00313 -- a factor 3.2
with not one parameter removed -- while shrinking it 21x adds only 13 %. So
the obstacle to a smaller network is the distillation, not the size. This
script measures whether it is the VOLUME: same shape, same seed, same
hold-out, same budget rule, only the number of training rows varies.

## Protocol, fixed here so that runs are comparable

* Rows come from `tools/build_distill_corpus.py` parts. The hold-out is a
  fixed set of parts (`--holdout-parts`, drawn first with the seed) shared by
  every run of a curve; a run's training parts are drawn at random among the
  others -- never a prefix, because parts are written worker by worker and a
  prefix would vary the walk along with the volume.
* Features stay on the GPU as uint8 codes into one global value table and are
  decoded batch by batch (exactly: the table is the union of the parts' own
  float32 tables).
* Loss: binary cross entropy against the teacher's five probabilities, the
  witness's loss in `distill_smaller.py`. One "epoch" is `--epoch-rows`
  samples whatever the volume, so the plateau schedule and the early stop
  read the same clock across volumes.
* Export: the engine's flat format through `write_model` (ReLU, prob5), read
  back by the engine before the run is declared done.

Neither held-out loss nor anything printed here is a strength: the verdict is
`bench/measure_t70.py` on the arbitrated registry.

Usage:
    python tools/distill_volume_t72.py --corpus build/t72-distill \\
        --rows 3200000 --shape 512,512,256,256 --out models/t72v_512x_3m2.bin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

INPUT_SIZE = 196
NUM_OUTPUTS = 5
REFERENCE_MACS = 526_976 + 512 * 128  # 512-512-256-256 -> 5


def macs(shape: list[int]) -> int:
    sizes = [INPUT_SIZE] + list(shape) + [NUM_OUTPUTS]
    return sum(sizes[i] * sizes[i + 1] for i in range(len(sizes) - 1))


def select_parts(corpus: Path, rows: int, holdout_parts: int, seed: int):
    parts = sorted(corpus.glob("part-*.npz"))
    if not parts:
        raise SystemExit(f"aucune part dans {corpus}")
    rng = random.Random(seed)
    shuffled = parts[:]
    rng.shuffle(shuffled)
    hold, pool = shuffled[:holdout_parts], shuffled[holdout_parts:]
    train, total = [], 0
    for part in pool:
        if total >= rows:
            break
        train.append(part)
        with np.load(part) as z:
            total += z["labels"].shape[0]
    if total < rows:
        raise SystemExit(f"corpus trop petit : {total:,} lignes < {rows:,} demandées")
    return train, hold


def value_table(parts: list[Path]) -> np.ndarray:
    """The union of the parts' own float32 value tables."""
    tables = []
    for part in parts:
        with np.load(part) as z:
            tables.append(z["values"])
    return np.unique(np.concatenate(tables)).astype(np.float32)


def load(parts: list[Path], table: np.ndarray, limit: int | None = None):
    """Parts -> (uint8 codes into `table`, float32 labels), exactly."""
    codes, labels = [], []
    for part in parts:
        with np.load(part) as z:
            own = z["values"]
            index = np.searchsorted(table, own)
            if not np.array_equal(table[index], own):
                raise SystemExit(f"{part}: valeur absente de la table globale")
            codes.append(index.astype(np.uint8)[z["codes"]])
            labels.append(z["labels"])
    x, y = np.concatenate(codes), np.concatenate(labels)
    if limit is not None:
        x, y = x[:limit], y[:limit]
    return x, y


def build(nn, shape):
    layers, size = [], INPUT_SIZE
    for width in shape:
        layers += [nn.Linear(size, width), nn.ReLU()]
        size = width
    layers.append(nn.Linear(size, NUM_OUTPUTS))
    return nn.Sequential(*layers)


def export(model, shape, path: Path) -> None:
    from quantize_model import write_model
    linears = [m for m in model if hasattr(m, "weight")]
    layers = [(m.weight.detach().cpu().numpy().astype(np.float32),
               m.bias.detach().cpu().numpy().astype(np.float32)) for m in linears]
    path.parent.mkdir(parents=True, exist_ok=True)
    write_model(path, {"num_hidden": len(shape), "input_size": INPUT_SIZE,
                       "activation": 0, "output_mode": 2,
                       "hidden": list(shape), "layers": layers})


def read_back(path: Path, shape):
    from quantize_model import read_model
    from gammonnet.infer import Network
    from gammonnet.rules import Position
    model = read_model(path)
    if model["hidden"] != list(shape):
        raise SystemExit(f"REFUS - {path} ne relit pas la forme écrite")
    with Network.load(path) as network:
        return list(network.evaluate(Position.initial()).as_tuple())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    import torch
    from torch import nn

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--shape", required=True, help="e.g. 512,512,256,256")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--holdout-parts", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261013)
    parser.add_argument("--epoch-rows", type=int, default=4_000_000)
    parser.add_argument("--max-epochs", type=int, default=400)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--schedule", choices=("plateau", "cosine"), default="plateau",
                        help="plateau: halve on a stalled hold-out, stop after "
                             "--patience; cosine: --max-epochs epochs exactly, "
                             "lr decayed to zero, best hold-out kept")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    shape = [int(w) for w in args.shape.split(",")]
    torch.manual_seed(args.seed)
    device = torch.device(args.device)

    train_parts, hold_parts = select_parts(args.corpus, args.rows, args.holdout_parts, args.seed)
    table = value_table(train_parts + hold_parts)
    x, y = load(train_parts, table, args.rows)
    hx, hy = load(hold_parts, table)

    print(f"T72 volume : {x.shape[0]:,} lignes ({len(train_parts)} parts), validation "
          f"{hx.shape[0]:,} ({len(hold_parts)} parts), forme {shape} = {macs(shape):,} MACs",
          flush=True)

    gx = torch.from_numpy(x).to(device)
    gy = torch.from_numpy(y).to(device)
    ghx = torch.from_numpy(hx).to(device)
    ghy = torch.from_numpy(hy).to(device)
    gtable = torch.from_numpy(table).to(device)

    model = build(nn, shape).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    if args.schedule == "cosine":
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.max_epochs)
    else:
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=6)
    bce = nn.BCEWithLogitsLoss()
    gen = torch.Generator(device=device).manual_seed(args.seed)

    def held_out():
        model.eval()
        total_bce, total_abs, n = 0.0, 0.0, ghx.shape[0]
        with torch.no_grad():
            for s in range(0, n, 65536):
                feats = gtable[ghx[s:s + 65536].long()]
                logits = model(feats)
                target = ghy[s:s + 65536]
                m = target.shape[0]
                total_bce += float(bce(logits, target)) * m
                total_abs += float((torch.sigmoid(logits) - target).abs().mean()) * m
        model.train()
        return total_bce / n, total_abs / n

    best, best_state, best_epoch = float("inf"), None, 0
    history = []
    start = time.perf_counter()
    steps = max(1, args.epoch_rows // args.batch_size)
    for epoch in range(1, args.max_epochs + 1):
        for _ in range(steps):
            idx = torch.randint(0, gx.shape[0], (args.batch_size,), device=device, generator=gen)
            opt.zero_grad(set_to_none=True)
            loss = bce(model(gtable[gx[idx].long()]), gy[idx])
            loss.backward()
            opt.step()
        held, absolute = held_out()
        if args.schedule == "cosine":
            sched.step()
        else:
            sched.step(held)
        history.append((epoch, held, absolute))
        if held < best - 1e-7:
            best, best_epoch = held, epoch
            best_state = {k: t.detach().cpu().clone() for k, t in model.state_dict().items()}
        if epoch % 10 == 0 or epoch == 1:
            print(f"  époque {epoch:4d}  bce {held:.6f}  |écart| {absolute:.5f}  "
                  f"lr {opt.param_groups[0]['lr']:.1e}  {time.perf_counter() - start:.0f} s",
                  flush=True)
        if args.schedule == "plateau" and epoch - best_epoch >= args.patience:
            break
    model.load_state_dict(best_state)
    model = model.cpu().eval()
    export(model, shape, args.out)
    opening = read_back(args.out, shape)

    held = [h for h in history if h[0] == best_epoch][0]
    summary = {
        "date": date.today().isoformat(), "tool": "tools/distill_volume_t72.py",
        "teacher_labels": "0-ply, cubeless_prob5_512_512_256_256 (build_distill_corpus)",
        "rows": int(x.shape[0]), "train_parts": [p.name for p in train_parts],
        "holdout_parts": [p.name for p in hold_parts], "holdout_rows": int(hx.shape[0]),
        "shape": shape, "macs": macs(shape), "seed": args.seed,
        "epoch_rows": args.epoch_rows, "batch_size": args.batch_size, "lr": args.lr,
        "schedule": args.schedule, "max_epochs": args.max_epochs,
        "best_epoch": best_epoch, "epochs_run": history[-1][0],
        "holdout_bce": held[1], "holdout_mean_abs": held[2],
        "seconds": time.perf_counter() - start, "sha256": sha256(args.out),
        "opening_position": opening, "verdict": "AUCUN — la force se lit sur T70",
    }
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"  meilleure époque {best_epoch}, bce {held[1]:.6f}, |écart| {held[2]:.5f} "
          f"→ {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

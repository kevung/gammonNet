#!/usr/bin/env python3
"""T72 — one parameterised pipeline: a 60-100 k MAC student, and its witness.

## What it produces

For one target size, two networks of the SAME architecture, the SAME seed and
the SAME hold-out fraction, differing in one thing only, the labels:

* the **student**, trained like `train_t71.py` (2-ply labels from
  `tools/build_labels_t71.py`, five nested probabilities by binary cross
  entropy plus the auxiliary volatility head), but at the target size;
* the **witness**, the same shape redistilled the way `distill_smaller.py`
  does it (0-ply labels of the large network, `build/prune_corpus.npz`).

`docs/mesures/2026-09-03-T72prep-taille-et-distillation.md` measured that at
equal size distillation alone costs a factor 3.2, so a student judged against
the original attributes to the reduction a loss that comes from the method.
The witness is the comparison that avoids that mistake: the student is read
against it, never against the original alone.

## What it does not decide

Neither held-out cross entropy nor anything printed here is a strength. The
verdict is `bench/measure_t70.py` on the arbitrated registry (protocol in
`docs/mesures/2026-10-04-T72-pipeline-distillation.md`).

Usage:
    python tools/distill_t72.py --target-macs 80000 --labels build/t71-money
    python tools/distill_t72.py --shape 256,128,64 --mode student
    python tools/distill_t72.py --smoke          # a few hundred rows, one epoch
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

INPUT_SIZE = 196
NUM_OUTPUTS = 5
AUX_WEIGHT = 0.2

#: The size window of the T72 sheet, in multiply-accumulates.
MIN_MACS, MAX_MACS = 60_000, 100_000
DEFAULT_TARGET_MACS = 80_000
#: Reference size of the large network, for the `x ref` column.
REFERENCE_MACS = 526_976
DEFAULT_SEED = 20260902
SMOKE_ROWS = 400


def macs(shape: list[int]) -> int:
    sizes = [INPUT_SIZE] + list(shape) + [NUM_OUTPUTS]
    return sum(sizes[i] * sizes[i + 1] for i in range(len(sizes) - 1))


def shape_for_target(target: int) -> list[int]:
    """The `(w, w/2, w/4)` shape, w a multiple of 16, nearest to `target` MACs.

    The halving ladder is the shape of every network of the T72 preparation
    sweep, so that the only thing varying between sizes is the size.
    """
    best = min(range(16, 1025, 16),
               key=lambda w: abs(macs([w, w // 2, w // 4]) - target))
    return [best, best // 2, best // 4]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_student(nn, shape):
    """Trunk, five-probability head, auxiliary volatility head (not exported)."""
    class Student(nn.Module):
        def __init__(self):
            super().__init__()
            layers, size = [], INPUT_SIZE
            for width in shape:
                layers += [nn.Linear(size, width), nn.ReLU()]
                size = width
            self.trunk = nn.Sequential(*layers)
            self.head = nn.Linear(size, NUM_OUTPUTS)
            self.aux = nn.Linear(size, 1)

        def forward(self, x):
            hidden = self.trunk(x)
            return self.head(hidden), self.aux(hidden)

    return Student()


def export_student(model, shape, path: Path) -> None:
    """Trunk and head, in the engine's flat format, through `write_model`."""
    import numpy as np

    from quantize_model import write_model

    def arrays(module):
        return (module.weight.detach().cpu().numpy().astype(np.float32),
                module.bias.detach().cpu().numpy().astype(np.float32))

    layers = [arrays(m) for m in model.trunk if hasattr(m, "weight")]
    layers.append(arrays(model.head))
    path.parent.mkdir(parents=True, exist_ok=True)
    write_model(path, {"num_hidden": len(shape), "input_size": INPUT_SIZE,
                       "activation": 0, "output_mode": 2,
                       "hidden": list(shape), "layers": layers})


def split(torch, features, seed, holdout, device, *tensors):
    """Same permutation for every tensor, hold-out cut at the end."""
    cut = int(features.shape[0] * (1.0 - holdout))
    order = torch.randperm(features.shape[0],
                           generator=torch.Generator().manual_seed(seed))
    return [(t[order[:cut]].to(device), t[order[cut:]].to(device))
            for t in (features,) + tensors]


def fit_student(torch, nn, shape, data, args, device):
    (train_x, hold_x), (train_y, hold_y), (train_v, hold_v) = data
    model = build_student(nn, shape).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimiser, factor=0.5, patience=8)
    bce, mse = nn.BCEWithLogitsLoss(), nn.MSELoss()
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    best, best_state, best_epoch, epoch = float("inf"), None, 0, 0
    started = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train()
        order = torch.randperm(train_x.shape[0], generator=generator)
        for start in range(0, train_x.shape[0], args.batch_size):
            index = order[start:start + args.batch_size].to(device)
            optimiser.zero_grad()
            logits, aux = model(train_x[index])
            loss = (bce(logits, train_y[index])
                    + args.aux_weight * mse(aux, train_v[index]))
            loss.backward()
            optimiser.step()
        model.eval()
        with torch.no_grad():
            logits, _ = model(hold_x)
            held = float(bce(logits, hold_y))
            absolute = float((torch.sigmoid(logits) - hold_y).abs().mean())
        scheduler.step(held)
        if held < best - 1e-7:
            best, best_epoch = held, epoch
            best_state = {k: t.detach().cpu().clone()
                          for k, t in model.state_dict().items()}
        if epoch - best_epoch >= args.patience:
            break
    model.load_state_dict(best_state)
    return (model.eval().to("cpu"), best, absolute, best_epoch, epoch,
            time.perf_counter() - started)


def smoke_inputs(workdir: Path, rows: int, seed: int):
    """A tiny labels directory and witness corpus. Meaningless on purpose."""
    import numpy as np

    from gammonnet import codec
    from gammonnet.infer import Network
    from smoke_support import walk, write_random_network

    labeller = write_random_network(workdir / "labeller.bin", [32, 16], seed)
    labels = workdir / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    features, probs = [], []
    seen = set()
    with Network.load(labeller) as network, \
            (labels / "labels.part-00.jsonl").open("w") as out:
        for position, _d1, _d2 in walk(network, seed):
            identifier = codec.position_id(position)
            if identifier in seen:
                continue
            seen.add(identifier)
            evaluation = network.evaluate(position).as_tuple()
            volatility = abs(evaluation[0] - 0.5)
            out.write(json.dumps({"id": identifier, "probs": list(evaluation),
                                  "volatility": volatility}) + "\n")
            features.append(codec.encode(position))
            probs.append(evaluation)
            if len(features) >= rows:
                break
    (labels / "manifeste.json").write_text(json.dumps(
        {"smoke": True, "labeller": "random-init network, meaningless"}))
    corpus = workdir / "witness_corpus.npz"
    np.savez(corpus, features=np.asarray(features, dtype=np.float32),
             labels=np.asarray(probs, dtype=np.float32))
    return labels, corpus


def read_back(path: Path, shape):
    """The artefact must load in the engine and answer on the opening position."""
    from quantize_model import read_model

    from gammonnet.infer import Network
    from gammonnet.rules import Position

    model = read_model(path)
    if model["hidden"] != list(shape) or model["input_size"] != INPUT_SIZE:
        raise SystemExit(f"REFUS - {path} ne relit pas la forme écrite")
    with Network.load(path) as network:
        evaluation = network.evaluate(Position.initial())
    return {"hidden": model["hidden"],
            "opening_position": list(evaluation.as_tuple())}


def main(argv: list[str] | None = None) -> int:
    import numpy as np
    import torch
    from torch import nn

    import distill_smaller
    import train_t71

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    size = parser.add_mutually_exclusive_group()
    size.add_argument("--target-macs", type=int, default=DEFAULT_TARGET_MACS)
    size.add_argument("--shape", help="hidden widths, e.g. 256,128,64")
    parser.add_argument("--mode", choices=("both", "student", "witness"),
                        default="both")
    parser.add_argument("--labels", type=Path, default=ROOT / "build" / "t71-money",
                        help="2-ply labels directory (student)")
    parser.add_argument("--witness-corpus", type=Path,
                        default=ROOT / "build" / "prune_corpus.npz",
                        help="0-ply corpus (witness)")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--prefix", default="t72")
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--aux-weight", type=float, default=AUX_WEIGHT)
    parser.add_argument("--holdout", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0,
                        help="random subsample of N rows, both networks")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--smoke", action="store_true",
                        help="a few hundred synthetic rows, one epoch, "
                             "artefacts under --out-dir (default: a temp dir)")
    parser.add_argument("--allow-any-size", action="store_true",
                        help="accept a shape outside 60-100 k MACs")
    args = parser.parse_args(argv)

    shape = ([int(v) for v in args.shape.split(",")] if args.shape
             else shape_for_target(args.target_macs))
    count = macs(shape)
    if not MIN_MACS <= count <= MAX_MACS and not args.allow_any_size:
        print(f"REFUS - {shape} fait {count:,} MACs, hors de "
              f"{MIN_MACS:,}-{MAX_MACS:,} (--allow-any-size pour passer outre).",
              file=sys.stderr)
        return 2

    workdir = None
    if args.smoke:
        args.epochs, args.patience, args.batch_size = 1, 1, 128
        args.device = "cpu"
        if args.out_dir == ROOT / "models":
            workdir = Path(tempfile.mkdtemp(prefix="t72-smoke-"))
            args.out_dir = workdir / "out"
        else:
            workdir = args.out_dir / "smoke-inputs"
            workdir.mkdir(parents=True, exist_ok=True)
        args.labels, args.witness_corpus = smoke_inputs(
            workdir, SMOKE_ROWS, args.seed)
    for needed, mode in ((args.labels, "student"), (args.witness_corpus, "witness")):
        if args.mode in ("both", mode) and not needed.exists():
            print(f"REFUS - entrée absente pour le mode {mode} : {needed}",
                  file=sys.stderr)
            return 2

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device(args.device if torch.cuda.is_available()
                          or args.device == "cpu" else "cpu")
    print(f"T72 - {shape} = {count:,} MACs ({count / REFERENCE_MACS:.3f} x ref), "
          f"mode {args.mode}, {device}{' [FUMEE]' if args.smoke else ''}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report = {"task": "T72 - student and same-size witness",
              "date": date.today().isoformat(), "smoke": args.smoke,
              "shape": shape, "macs": count, "seed": args.seed,
              "training": {"epochs": args.epochs, "patience": args.patience,
                           "batch_size": args.batch_size, "lr": args.lr,
                           "aux_weight": args.aux_weight,
                           "holdout": args.holdout, "limit": args.limit,
                           "device": str(device), "torch": torch.__version__},
              "networks": {}}
    name = "-".join(str(v) for v in shape)

    def subsample(*arrays):
        if args.limit and args.limit < arrays[0].shape[0]:
            picked = np.random.default_rng(args.seed).choice(
                arrays[0].shape[0], size=args.limit, replace=False)
            return [a[picked] for a in arrays]
        return list(arrays)

    if args.mode in ("both", "student"):
        features, probs, volatility, manifests, duplicates = \
            train_t71.load_labels(args.labels)
        if features.shape[0] == 0:
            print(f"REFUS - aucune étiquette lisible dans {args.labels}",
                  file=sys.stderr)
            return 2
        features, probs, volatility = subsample(features, probs, volatility)
        data = split(torch, torch.from_numpy(features), args.seed, args.holdout,
                     device, torch.from_numpy(probs), torch.from_numpy(volatility))
        model, held, absolute, best_epoch, ran, seconds = fit_student(
            torch, nn, shape, data, args, device)
        path = args.out_dir / f"{args.prefix}_student_{name}.bin"
        export_student(model, shape, path)
        report["networks"]["student"] = {
            "labels": "2-ply + volatility head", "directory": str(args.labels),
            "positions": int(features.shape[0]), "duplicates_dropped": duplicates,
            "held_out_bce": held, "mean_abs_error": absolute,
            "best_epoch": best_epoch, "epochs_run": ran, "seconds": seconds,
            "path": str(path), "sha256": sha256(path),
            "readback": read_back(path, shape)}
        print(f"  student : {features.shape[0]:,} rows, bce {held:.6f}, "
              f"{seconds / 60:.2f} min -> {path}")

    if args.mode in ("both", "witness"):
        raw = np.load(args.witness_corpus)
        features, labels = subsample(raw["features"], raw["labels"])
        (train_x, hold_x), (train_y, hold_y) = split(
            torch, torch.from_numpy(features).float(), args.seed, args.holdout,
            device, torch.from_numpy(labels).float())
        witness_model, held, absolute, best_epoch, seconds = \
            distill_smaller.train_one(
                torch, nn, shape, (train_x, train_y, hold_x, hold_y), args,
                device, print)
        path = args.out_dir / f"{args.prefix}_witness_{name}.bin"
        distill_smaller.export_bin(witness_model, shape, path)
        report["networks"]["witness"] = {
            "labels": "0-ply of the large network",
            "corpus": str(args.witness_corpus),
            "positions": int(features.shape[0]), "held_out_bce": held,
            "mean_abs_error": absolute, "best_epoch": best_epoch,
            "seconds": seconds, "path": str(path), "sha256": sha256(path),
            "readback": read_back(path, shape)}
        print(f"  witness : {features.shape[0]:,} rows, bce {held:.6f}, "
              f"{seconds / 60:.2f} min -> {path}")

    report["verdict"] = ("NONE - strength is measured by bench/measure_t70.py, "
                         "never by held-out cross entropy (DS-14).")
    summary = args.out_dir / f"{args.prefix}_{name}.summary.json"
    summary.write_text(json.dumps(report, ensure_ascii=False, indent=1,
                                  sort_keys=True))
    print(f"  -> {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

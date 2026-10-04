#!/usr/bin/env python3
"""Train the race-zone network from a `build_race_corpus.py` corpus, export `.bin`.

The domain is `classify.in_race_zone`: contact-free, outside the exact bearoff
tables. The network has the engine's 196 inputs and five nested outputs, so the
`.bin` it writes is the engine's own flat format (`quantize_model.write_model`,
ReLU hidden layers, sigmoid out, `output_mode = 2`); nothing else is written.

Targets are the rollout outcome frequencies, trained with binary cross entropy
per output (the likelihood of nested probabilities, see `train_t71.py`). The
rollout noise is not removed: the corpus stores each label's standard error and
`tools/gauge_race_net.py` reports it as the floor of any measured error.

Held-out cross entropy is a training signal, never a strength. The verdict is
`tools/gauge_race_net.py` against the incumbent on a corpus built from another
seed (protocol: `docs/mesures/2026-10-04-reseau-de-course-pipeline.md`).

Usage:
    python tools/train_race_net.py --corpus build/race_train.npz \\
        --hidden 128,64 --out models/race_128_64.bin
    python tools/train_race_net.py --smoke
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

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

INPUT_SIZE = 196
NUM_OUTPUTS = 5
DEFAULT_SEED = 20261004


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def macs(hidden: list[int]) -> int:
    sizes = [INPUT_SIZE] + hidden + [NUM_OUTPUTS]
    return sum(sizes[i] * sizes[i + 1] for i in range(len(sizes) - 1))


def export_bin(model, hidden: list[int], path: Path) -> None:
    from quantize_model import write_model

    layers = [(m.weight.detach().cpu().numpy().astype(np.float32),
               m.bias.detach().cpu().numpy().astype(np.float32))
              for m in model if hasattr(m, "weight")]
    path.parent.mkdir(parents=True, exist_ok=True)
    write_model(path, {"num_hidden": len(hidden), "input_size": INPUT_SIZE,
                       "activation": 0, "output_mode": 2,
                       "hidden": list(hidden), "layers": layers})


def main(argv: list[str] | None = None) -> int:
    import torch
    from torch import nn

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, nargs="+",
                        default=[ROOT / "build" / "race_train.npz"])
    parser.add_argument("--hidden", default="128,64")
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "race_net.bin")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--holdout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--smoke", action="store_true",
                        help="build a tiny corpus, train one epoch, export")
    args = parser.parse_args(argv)

    if args.smoke:
        import build_race_corpus
        if args.out == ROOT / "models" / "race_net.bin":
            workdir = Path(tempfile.mkdtemp(prefix="race-smoke-"))
            args.out = workdir / "race_net.bin"
        else:
            workdir = args.out.parent / "smoke-inputs"
        if build_race_corpus.main(["--smoke", "--out",
                                   str(workdir / "race.npz"),
                                   "--seed", str(args.seed)]) != 0:
            return 2
        args.corpus = [workdir / "race.npz"]
        args.epochs, args.patience, args.batch_size = 1, 1, 64
        args.device = "cpu"
    missing = [c for c in args.corpus if not c.exists()]
    if missing:
        print(f"REFUS - corpus absent : {missing[0]}\n"
              f"  python tools/build_race_corpus.py", file=sys.stderr)
        return 2

    hidden = [int(v) for v in args.hidden.split(",")]
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device(args.device if torch.cuda.is_available()
                          or args.device == "cpu" else "cpu")

    parts = [np.load(c) for c in args.corpus]
    features = np.concatenate([p["features"] for p in parts])
    probs = np.concatenate([p["probs"] for p in parts])
    ids = np.concatenate([p["ids"] for p in parts])
    if len(set(ids.tolist())) != len(ids):
        print("REFUS - positions en double entre les corpus.", file=sys.stderr)
        return 2
    cut = int(len(ids) * (1.0 - args.holdout))
    order = torch.randperm(len(ids), generator=torch.Generator().manual_seed(args.seed))
    x = torch.from_numpy(features)
    y = torch.from_numpy(probs)
    train_x, hold_x = x[order[:cut]].to(device), x[order[cut:]].to(device)
    train_y, hold_y = y[order[:cut]].to(device), y[order[cut:]].to(device)

    layers, size = [], INPUT_SIZE
    for width in hidden:
        layers += [nn.Linear(size, width), nn.ReLU()]
        size = width
    layers.append(nn.Linear(size, NUM_OUTPUTS))
    model = nn.Sequential(*layers).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimiser, factor=0.5, patience=6)
    bce = nn.BCEWithLogitsLoss()
    generator = torch.Generator().manual_seed(args.seed)
    best, best_state, best_epoch, epoch = float("inf"), None, 0, 0
    absolute = 0.0
    started = time.perf_counter()
    print(f"race net {hidden} = {macs(hidden):,} MACs, {len(ids):,} rows, {device}"
          f"{' [FUMEE]' if args.smoke else ''}")
    for epoch in range(1, args.epochs + 1):
        model.train()
        shuffled = torch.randperm(train_x.shape[0], generator=generator)
        for start in range(0, train_x.shape[0], args.batch_size):
            index = shuffled[start:start + args.batch_size].to(device)
            optimiser.zero_grad()
            bce(model(train_x[index]), train_y[index]).backward()
            optimiser.step()
        model.eval()
        with torch.no_grad():
            logits = model(hold_x)
            held = float(bce(logits, hold_y))
            absolute = float((torch.sigmoid(logits) - hold_y).abs().mean())
        scheduler.step(held)
        if held < best - 1e-7:
            best, best_epoch = held, epoch
            best_state = {k: t.detach().cpu().clone()
                          for k, t in model.state_dict().items()}
        if epoch % 10 == 0 or epoch == 1:
            print(f"  epoch {epoch:4d}  held-out bce {held:.6f}  abs {absolute:.6f}")
        if epoch - best_epoch >= args.patience:
            break
    model.load_state_dict(best_state)
    model.eval().to("cpu")
    seconds = time.perf_counter() - started

    export_bin(model, hidden, args.out)
    from quantize_model import read_model

    from gammonnet.infer import Network
    from gammonnet.rules import Position
    back = read_model(args.out)
    if back["hidden"] != hidden:
        print("REFUS - le .bin relu n'a pas la forme écrite.", file=sys.stderr)
        return 2
    with Network.load(args.out) as network:
        opening = list(network.evaluate(Position.initial()).as_tuple())
    provenance = {
        "task": "race-zone network", "date": date.today().isoformat(),
        "smoke": args.smoke, "hidden": hidden, "macs": macs(hidden),
        "corpus": [{"path": str(c), "sha256": sha256(c)} for c in args.corpus],
        "rows": int(len(ids)),
        "training": {"seed": args.seed, "epochs_run": epoch,
                     "best_epoch": best_epoch, "batch_size": args.batch_size,
                     "lr": args.lr, "holdout": args.holdout,
                     "held_out_bce": best, "held_out_mean_abs": absolute,
                     "seconds": seconds, "device": str(device),
                     "torch": torch.__version__},
        "artifact": {"path": str(args.out), "sha256": sha256(args.out),
                     "readback_opening_position": opening},
        "verdict": "NONE - strength is tools/gauge_race_net.py against the "
                   "incumbent on an independent corpus.",
    }
    destination = args.out.with_suffix(".provenance.json")
    destination.write_text(json.dumps(provenance, ensure_ascii=False, indent=1,
                                      sort_keys=True))
    print(f"  held-out bce {best:.6f} (epoch {best_epoch}), {seconds / 60:.2f} min"
          f"\n  -> {args.out}\n  -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

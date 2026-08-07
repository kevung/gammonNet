#!/usr/bin/env python3
"""T3A — train the pruning network by distillation from the grand network.

## What is being trained, and from what

A 196 -> 32 -> 5 network, same conventions as the grand network (`BRIEF.md`
§6): `encoding.py`'s 196 perspective features in, five nested sigmoid
probabilities out, prob5 mode. Trained with MSE against the GRAND network's
own five outputs on `tools/build_prune_corpus.py`'s corpus — never against
gnubg, never against game outcomes. `docs/etudes/README.md` names this
network-to-network distillation explicitly (registry row 2026-08-03): the
weights of a pruning network are the product of someone's training run, not
an idea, so ours must come from our own network.

## Determinism

`torch.manual_seed`, `numpy`'s and Python's `random.seed` are all fixed. CUDA
matmul/convolution backward passes use atomic accumulation on some kernels,
which is not bit-reproducible run to run even with a fixed seed — this is a
documented PyTorch/cuDNN limitation, not a bug in this script.
`torch.use_deterministic_algorithms(True, warn_only=True)` is set so that any
non-deterministic op used is at least visible (a warning), rather than silent.
The practical effect on this network is small: it is tiny (6,469 parameters),
trained on a few hundred thousand rows, so the run-to-run MSE difference this
introduces is below the precision anyone would read off a report.

## Export path

The `.bin` is NOT written by a second, home-grown writer: it goes through
`vendor/backgammon-ai-engine/export_weights.py`, exactly as
`tools/export_model.py` does for the grand network. A second implementation
of the BGNN writer would be a second thing to keep in step with the C reader.

Usage:
    python tools/train_prune.py
    python tools/train_prune.py --corpus build/prune_corpus.npz --epochs 200
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "backgammon-ai-engine"
sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(ROOT / "python"))

DEFAULT_CORPUS = ROOT / "build" / "prune_corpus.npz"
RAW_PT = ROOT / "models" / "prune_32_raw.pt"          # gitignored (models/*.pt)
OUT_BIN = ROOT / "models" / "prune_32.bin"            # gitignored (models/*.bin)
OUT_PROVENANCE = ROOT / "models" / "prune_32.provenance.json"  # committed
GRAND_MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
GRAND_PROVENANCE = ROOT / "models" / "cubeless_prob5_512_512_256_128.provenance.json"

HIDDEN_SIZES = [32]
ACTIVATION = "relu"
INPUT_SIZE = 196

TRAIN_SEED = 20260807
HOLDOUT_FRACTION = 0.05


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def load_corpus(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    if not path.is_file():
        raise SystemExit(
            f"{path} absent — lancer `python tools/build_prune_corpus.py` d'abord"
        )
    data = np.load(path, allow_pickle=True)
    meta = {
        "seed": int(data["seed"]),
        "workers": int(data["workers"]),
        "model": str(data["model"]),
        "size": int(data["features"].shape[0]),
    }
    return data["features"], data["labels"], meta


def split(features: np.ndarray, labels: np.ndarray, seed: int, holdout_fraction: float):
    n = features.shape[0]
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    n_holdout = int(round(n * holdout_fraction))
    holdout_idx = order[:n_holdout]
    train_idx = order[n_holdout:]
    return (features[train_idx], labels[train_idx],
            features[holdout_idx], labels[holdout_idx])


def train(features: np.ndarray, labels: np.ndarray, args) -> tuple[object, dict]:
    import torch
    import torch.nn as nn
    from model import ProbNetwork  # vendor, MIT — see module docstring

    device = torch.device(args.device if torch.cuda.is_available() or "cuda" not in args.device else "cpu")
    if "cuda" in args.device and not torch.cuda.is_available():
        print("  CUDA indisponible : retombe sur CPU", file=sys.stderr)
        device = torch.device("cpu")

    x_train, y_train, x_holdout, y_holdout = split(
        features, labels, args.split_seed, HOLDOUT_FRACTION,
    )
    print(f"  train={x_train.shape[0]:,}  held-out={x_holdout.shape[0]:,}  "
          f"({HOLDOUT_FRACTION:.0%})")

    x_train_t = torch.from_numpy(x_train).to(device)
    y_train_t = torch.from_numpy(y_train).to(device)
    x_holdout_t = torch.from_numpy(x_holdout).to(device)
    y_holdout_t = torch.from_numpy(y_holdout).to(device)

    net = ProbNetwork(
        hidden_sizes=HIDDEN_SIZES, input_size=INPUT_SIZE, activation=ACTIVATION,
        encoder_name="perspective196", raw_logits=False,
    ).to(device)

    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()

    n_train = x_train_t.shape[0]
    best_holdout_mse = float("inf")
    best_state = None
    best_epoch = 0
    patience_left = args.patience
    history = []

    generator = torch.Generator(device="cpu").manual_seed(args.split_seed)

    start = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        net.train()
        perm = torch.randperm(n_train, generator=generator)
        epoch_loss = 0.0
        for start_idx in range(0, n_train, args.batch_size):
            idx = perm[start_idx:start_idx + args.batch_size].to(device)
            xb = x_train_t[idx]
            yb = y_train_t[idx]
            optimizer.zero_grad()
            pred = net(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * xb.shape[0]
        train_mse = epoch_loss / n_train

        net.eval()
        with torch.no_grad():
            holdout_pred = net(x_holdout_t)
            holdout_mse = loss_fn(holdout_pred, y_holdout_t).item()

        history.append({"epoch": epoch, "train_mse": train_mse, "holdout_mse": holdout_mse})

        improved = holdout_mse < best_holdout_mse - args.min_delta
        if improved:
            best_holdout_mse = holdout_mse
            best_epoch = epoch
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
            patience_left = args.patience
        else:
            patience_left -= 1

        if epoch == 1 or epoch % 5 == 0 or improved or patience_left == 0:
            marker = "*" if improved else " "
            print(f"  epoch {epoch:4d}  train MSE {train_mse:.6f}  "
                  f"held-out MSE {holdout_mse:.6f} {marker}")

        if patience_left <= 0:
            print(f"  arrêt anticipé : pas d'amélioration depuis {args.patience} époques "
                  f"(meilleure à l'époque {best_epoch})")
            break

    elapsed = time.perf_counter() - start
    net.load_state_dict(best_state)
    net.eval()

    return net, {
        "epochs_run": epoch,
        "best_epoch": best_epoch,
        "best_holdout_mse": best_holdout_mse,
        "train_seconds": elapsed,
        "history": history,
        "device": str(device),
    }


def export(net, args) -> None:
    """Save raw .pt, then hand off to the vendored, untouched exporter."""
    net_cpu = net.to("cpu")
    RAW_PT.parent.mkdir(parents=True, exist_ok=True)
    net_cpu.save(str(RAW_PT))

    result = subprocess.run(
        [sys.executable, "export_weights.py", str(RAW_PT.resolve()), str(OUT_BIN.resolve())],
        cwd=VENDOR, capture_output=True, text=True,
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)


def verify_c_loader() -> list[dict]:
    """Load the exported .bin through OUR C loader, evaluate 3 positions.

    Not a repeat of `export_weights.py`'s own `verify_export` (that runs the
    PyTorch model, not the C reader). This is the check the task actually
    needs: the artefact the C `nn_eval.c` reader will consume, read by the
    same `Network.load` the rest of gammonNet uses.
    """
    from gammonnet.infer import Network
    from gammonnet.rules import Position

    net = Network.load(OUT_BIN)
    checks = []
    samples = {
        "position initiale": Position.initial(),
        "position initiale, camp inverse": Position.initial().swapped_turn(),
        "course pure (contrôle d'orientation)": Position(
            points=tuple(
                [3, 3, 3, 3, 3] + [0] * 14 + [-3, -3, -3, -3, -3]
            ),
            bar=(0, 0), off=(0, 0), turn=0,
        ),
    }
    for label, position in samples.items():
        if not position.is_valid():
            raise SystemExit(f"position de contrôle invalide : {label}")
        evaluation = net.evaluate(position)
        checks.append({
            "label": label,
            "probs": list(evaluation.as_tuple()),
            "nested": evaluation.is_nested,
        })
        print(f"  {label:38s} {[round(v, 4) for v in evaluation.as_tuple()]}  "
              f"imbriqué={evaluation.is_nested}")
    net.close()
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--min-delta", type=float, default=1e-7)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=TRAIN_SEED)
    parser.add_argument("--split-seed", type=int, default=TRAIN_SEED)
    args = parser.parse_args()

    print("T3A — entraînement du réseau d'élagage par distillation")
    set_seeds(args.seed)

    features, labels, corpus_meta = load_corpus(args.corpus)
    print(f"  corpus : {corpus_meta['size']:,} positions, graine {corpus_meta['seed']}, "
          f"{corpus_meta['workers']} processus, enseignant {Path(corpus_meta['model']).name}")

    net, train_meta = train(features, labels, args)

    print("\n  export du .bin (magic BGNN, hidden [32], output_mode prob5)")
    export(net, args)

    print("\n  vérification — chargement par le lecteur C, 3 positions")
    checks = verify_c_loader()
    if not all(c["nested"] for c in checks):
        raise SystemExit("des sorties non imbriquées sur les positions de contrôle — export suspect")

    grand_provenance = json.loads(GRAND_PROVENANCE.read_text()) if GRAND_PROVENANCE.is_file() else None

    provenance = {
        "network": "prune_32",
        "architecture": {
            "input_size": INPUT_SIZE,
            "hidden_sizes": HIDDEN_SIZES,
            "activation": ACTIVATION,
            "output_mode": "prob5",
        },
        "distilled_from": {
            "network": "cubeless_prob5_512_512_256_128",
            "artifact": str(GRAND_MODEL.relative_to(ROOT)),
            "sha256": grand_provenance["sha256"] if grand_provenance else None,
        },
        "corpus": {
            "path": "build/prune_corpus.npz (gitignored — se régénère par graine)",
            "size": corpus_meta["size"],
            "seed": corpus_meta["seed"],
            "workers": corpus_meta["workers"],
            "generator": "tools/build_prune_corpus.py",
        },
        "training": {
            "optimizer": "Adam",
            "lr": args.lr,
            "batch_size": args.batch_size,
            "loss": "MSE (post-sigmoid, 5 outputs)",
            "holdout_fraction": HOLDOUT_FRACTION,
            "epochs_run": train_meta["epochs_run"],
            "best_epoch": train_meta["best_epoch"],
            "best_holdout_mse": train_meta["best_holdout_mse"],
            "train_seconds": train_meta["train_seconds"],
            "device": train_meta["device"],
            "seed": args.seed,
            "split_seed": args.split_seed,
            "deterministic_note": (
                "torch.manual_seed fixe ; les noyaux CUDA de retro-propagation "
                "restent partiellement non-déterministes (accumulation atomique) — "
                "use_deterministic_algorithms(warn_only=True) rend cela visible, "
                "sans l'éliminer. Effet négligeable sur un réseau de 6 469 "
                "paramètres."
            ),
        },
        "artifact": OUT_BIN.name,
        "sha256": sha256(OUT_BIN),
        "bytes": OUT_BIN.stat().st_size,
        "date": date.today().isoformat(),
        "verification": checks,
        "license": "MIT (poids produits par ce dépôt ; exporteur vendoré Alexander Strehl, MIT)",
    }
    OUT_PROVENANCE.write_text(json.dumps(provenance, indent=2) + "\n")

    print(f"\n  MSE held-out finale (meilleure époque {train_meta['best_epoch']}) : "
          f"{train_meta['best_holdout_mse']:.6f}")
    print(f"  {OUT_BIN} : {OUT_BIN.stat().st_size:,} octets, sha256={provenance['sha256'][:16]}...")
    print(f"  provenance : {OUT_PROVENANCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""#34 -- a SHORT measurement experiment, not a model of the project.

Question: can the strength of the 768×768 be carried into a network of the
current shape (512-512-256-256), so that it costs what the current one costs?
T72 measured a ceiling for small students trained from scratch; this asks a
different question -- a student that STARTS from the current network's own
weights and is only nudged toward the 768×768's outputs.

Training a network of our own is phase 4, which is conditional and closed
(CLAUDE.md). This script therefore trains nothing that ships: its output is a
measurement input for `bench/measure_t70.py`, named `i34-ft-*`, kept out of
`models/`, and the report says so.

Data: `tools/build_prune_corpus.py --model <768×768>` -- the candidate
positions our engine meets at 0-ply, each labelled with the 768×768's five
raw probabilities. Loss: MSE on the five sigmoids, the same objective
`tools/train_prune.py` distils with.

    python tools/finetune_wide_i34.py --corpus build/i34e4/wide_corpus_8m.npz \
        --out build/i34e4/i34-ft-512.pt --epochs 6 --lr 1e-4

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "vendor" / "backgammon-ai-engine"
sys.path.insert(0, str(REFERENCE))

from model import ProbNetwork  # noqa: E402

INIT = REFERENCE / "best_models" / "cubeless_prob5_512_512_256_256.pt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--init", type=Path, default=INIT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--holdout", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    data = np.load(args.corpus)
    x = torch.from_numpy(data["features"])
    y = torch.from_numpy(data["labels"])
    order = torch.from_numpy(np.random.default_rng(args.seed).permutation(len(x)))
    cut = int(len(x) * args.holdout)
    held, train = order[:cut], order[cut:]

    net = ProbNetwork.load(str(args.init)).to(args.device)
    xh, yh = x[held].to(args.device), y[held].to(args.device)

    def held_mse() -> float:
        net.eval()
        with torch.no_grad():
            total = 0.0
            for s in range(0, len(xh), 65536):
                total += torch.nn.functional.mse_loss(
                    net(xh[s:s + 65536]), yh[s:s + 65536], reduction="sum").item()
        net.train()
        return total / (len(xh) * 5)

    start = held_mse()
    print(f"  MSE held-out, réseau actuel avant affinage : {start:.6f}")
    optimiser = torch.optim.Adam(net.parameters(), lr=args.lr)
    best, best_state = start, {k: v.detach().clone() for k, v in net.state_dict().items()}
    for epoch in range(args.epochs):
        perm = train[torch.randperm(len(train))]
        for s in range(0, len(perm), args.batch_size):
            idx = perm[s:s + args.batch_size]
            loss = torch.nn.functional.mse_loss(net(x[idx].to(args.device)),
                                                y[idx].to(args.device))
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
        mse = held_mse()
        print(f"  époque {epoch + 1}/{args.epochs} : MSE held-out {mse:.6f}")
        if mse < best:
            best = mse
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    net.cpu().save(str(args.out), train_params={
        "experiment": "#34 finetune toward 768x768 (measurement only)",
        "init": str(args.init.name), "corpus": str(args.corpus.name),
        "lr": args.lr, "epochs": args.epochs, "seed": args.seed,
        "held_mse_before": start, "held_mse_best": best,
    })
    print(f"  → {args.out}  (MSE held-out {start:.6f} → {best:.6f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

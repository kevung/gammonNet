#!/usr/bin/env python3
"""T72 (préparation) — distiller le réseau vers des architectures plus petites.

## Ce que ce programme prépare, et ce qu'il ne prétend pas être

T72 veut un réseau de **60 000 à 100 000 MACs** dont la qualité reste
indiscernable sur l'instrument de T70, et elle le veut **distillé du réseau
issu de T71**, pas de l'actuel. Ce programme ne fait donc pas T72.

Il fait ce qui doit exister **avant** T72 : la courbe taille → qualité sur le
réseau d'aujourd'hui. Sans elle, T72 n'aurait aucun repère pour juger son propre
résultat — « 91 000 MACs coûtent tant » serait un chiffre sans comparaison. La
règle 2 du dépôt le dit autrement : le harnais de mesure se construit avant le
modèle.

## D'où viennent les étiquettes

`build/prune_corpus.npz` — les positions rencontrées par notre moteur en
self-play, chacune étiquetée par **les cinq probabilités brutes du grand
réseau**. C'est le corpus que T3A a construit pour le réseau d'élagage, et il
convient exactement : distiller, c'est apprendre la sortie du maître, et la
distribution des positions y est celle du jeu.

Rien ne vient d'un moteur extérieur, ici comme partout.

## Le warm-start, et pourquoi il est absent

DS-06 dit que partir du professeur nuit **quand on entraîne pour la
recherche** — on cherche alors un réseau qui a vu autre chose. Ici on cherche
le même réseau, en plus petit, ce qui plaiderait pour un warm-start ; mais les
formes diffèrent, il n'y a donc rien à reprendre. Les poids sont tirés au sort.

## Le critère

Ce n'est pas la perte de validation. C'est l'instrument de T70 : la perte
d'équité par décision sur le registre arbitré, contre l'étalon 0,00313. Ce
programme rend un `.bin` par architecture ; les mesurer est un autre travail,
et c'est lui qui tranche.

Usage :
    python tools/distill_smaller.py --shapes 256,128,64 192,96,48
    python tools/distill_smaller.py --sweep      # les six tailles du balayage
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

INPUT_SIZE = 196
NUM_OUTPUTS = 5

#: Le balayage : de part et d'autre de la cible 60–100 k MACs de T72, plus la
#: forme actuelle en témoin. Une seule chose change d'une ligne à l'autre —
#: la taille — parce qu'un balayage qui bougerait aussi l'activation ou la
#: profondeur ne se lirait plus.
SWEEP = ["512,512,256,128", "320,160,80", "256,128,64",
         "192,96,48", "128,64,32", "96,48,24"]


def macs(shape: list[int]) -> int:
    sizes = [INPUT_SIZE] + shape + [NUM_OUTPUTS]
    return sum(sizes[i] * sizes[i + 1] for i in range(len(sizes) - 1))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(torch, nn, shape):
    layers = []
    size = INPUT_SIZE
    for width in shape:
        layers += [nn.Linear(size, width), nn.ReLU()]
        size = width
    layers.append(nn.Linear(size, NUM_OUTPUTS))
    return nn.Sequential(*layers)


def export_bin(model, shape, path: Path) -> None:
    """Le format plat du moteur, écrit par `write_model` et pas par un second."""
    import numpy as np

    from quantize_model import write_model  # noqa: PLC0415

    linears = [m for m in model if hasattr(m, "weight")]
    layers = [(m.weight.detach().cpu().numpy().astype(np.float32),
               m.bias.detach().cpu().numpy().astype(np.float32))
              for m in linears]
    write_model(path, {
        "num_hidden": len(shape), "input_size": INPUT_SIZE,
        "activation": 0,   # ReLU
        "output_mode": 2,  # prob5, sortie sigmoïde
        "hidden": list(shape), "layers": layers,
    })


def train_one(torch, nn, shape, data, args, device, report):
    train_x, train_y, hold_x, hold_y = data
    model = build(torch, nn, shape).to(device)
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimiser, factor=0.5, patience=6)
    bce = nn.BCEWithLogitsLoss()

    best, best_state, best_epoch = float("inf"), None, 0
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    started = time.perf_counter()

    for epoch in range(1, args.epochs + 1):
        model.train()
        order = torch.randperm(train_x.shape[0], generator=generator)
        for start in range(0, train_x.shape[0], args.batch_size):
            index = order[start:start + args.batch_size].to(device)
            optimiser.zero_grad()
            loss = bce(model(train_x[index]), train_y[index])
            loss.backward()
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
        if epoch - best_epoch >= args.patience:
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval().to("cpu")
    return model, best, absolute, best_epoch, time.perf_counter() - started


def main() -> int:
    import numpy as np
    import torch
    from torch import nn

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shapes", nargs="*", default=[])
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--corpus", type=Path,
                        default=ROOT / "build" / "prune_corpus.npz")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--prefix", default="t72prep")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--holdout", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    shapes = args.shapes or (SWEEP if args.sweep else [])
    if not shapes:
        print("REFUS — donner --shapes ou --sweep.", file=sys.stderr)
        return 2
    if not args.corpus.exists():
        print(f"REFUS — corpus absent : {args.corpus}\n"
              f"  `python tools/build_prune_corpus.py`", file=sys.stderr)
        return 2

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device(args.device if torch.cuda.is_available()
                          or args.device == "cpu" else "cpu")

    raw = np.load(args.corpus)
    features = torch.from_numpy(raw["features"]).float()
    labels = torch.from_numpy(raw["labels"]).float()
    cut = int(features.shape[0] * (1.0 - args.holdout))
    order = torch.randperm(features.shape[0],
                           generator=torch.Generator().manual_seed(args.seed))
    data = (features[order[:cut]].to(device), labels[order[:cut]].to(device),
            features[order[cut:]].to(device), labels[order[cut:]].to(device))

    print(f"Distillation vers des architectures réduites — {device}")
    print(f"  corpus : {features.shape[0]:,} positions, étiquetées par le grand "
          f"réseau (T3A)")
    print(f"  {len(shapes)} architectures\n")
    print(f"  {'architecture':<22} {'MACs':>8} {'×réf':>6} "
          f"{'entropie':>10} {'écart abs':>10} {'min':>6}")

    reference = macs([512, 512, 256, 128])
    rows = []
    for text in shapes:
        shape = [int(v) for v in text.split(",")]
        model, held, absolute, epoch, elapsed = train_one(
            torch, nn, shape, data, args, device, print)
        count = macs(shape)
        name = f"{args.prefix}_{'-'.join(str(v) for v in shape)}"
        destination = args.out_dir / f"{name}.bin"
        export_bin(model, shape, destination)
        rows.append({
            "shape": shape, "macs": count, "ratio": count / reference,
            "held_out_bce": held, "mean_abs_error": absolute,
            "best_epoch": epoch, "seconds": elapsed,
            "path": str(destination), "sha256": sha256(destination),
        })
        print(f"  {text:<22} {count:>8,} {count / reference:>6.3f} "
              f"{held:>10.6f} {absolute:>10.6f} {elapsed / 60:>6.1f}")

    provenance = {
        "task": "T72 (préparation) — courbe taille → qualité",
        "date": date.today().isoformat(),
        "corpus": {"path": str(args.corpus), "positions": int(features.shape[0])},
        "training": {"seed": args.seed, "epochs": args.epochs,
                     "batch_size": args.batch_size, "lr": args.lr,
                     "patience": args.patience, "holdout": args.holdout,
                     "device": str(device), "torch": torch.__version__},
        "networks": rows,
        "verdict": "AUCUN — la qualité se mesure sur l'instrument de T70, "
                   "jamais sur l'entropie croisée retenue.",
    }
    out = ROOT / "docs" / "mesures" / "t72prep-taille-qualite.json"
    out.write_text(json.dumps(provenance, ensure_ascii=False, indent=1,
                              sort_keys=True))
    print(f"\n  → {out}")
    print("  Ces colonnes ne disent PAS la force. Mesurer chaque .bin sur le")
    print("  registre de T70, contre l'étalon 0,00313.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

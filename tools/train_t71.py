#!/usr/bin/env python3
"""T71 étape 1 — distiller notre propre 2-ply dans un réseau.

## Ce qui est appris, et à partir de quoi

Les étiquettes de `tools/build_labels_t71.py` : pour chaque position, les cinq
probabilités que notre expectiminimax rend à 2-ply, et la volatilité exacte de
la position sur les 21 jets. L'élève apprend les deux — les cinq par
entropie croisée, la volatilité par erreur quadratique, dans une **tête
auxiliaire** dont le poids de perte suit la fiche (0,15–0,3 du principal).

Aucune étiquette extérieure. La règle de licence du dépôt fait de GNU
Backgammon un instrument de mesure et jamais une source d'apprentissage.

## From scratch, et pourquoi ce n'est pas un oubli

DS-06 est explicite : pour l'entraînement **pour la recherche**, partir des
poids du professeur nuit. On ne cherche pas le même réseau exprimé autrement
(c'est le cas de la QAT de T73, qui warm-start à raison) ; on cherche un réseau
qui a vu ce que la recherche voit. Les poids sont donc tirés au sort.

## Pourquoi l'entropie croisée et non l'erreur quadratique

Les cinq sorties ne forment pas une distribution catégorielle : ce sont des
probabilités emboîtées (gagner, gagner gammon, gagner backgammon, perdre
gammon, perdre backgammon), chacune passée par une sigmoïde. L'entropie croisée
**binaire, sortie par sortie** est donc la vraisemblance de ce modèle-là ; un
softmax supposerait une exclusivité qui n'existe pas, et l'erreur quadratique
traiterait 0,001 et 0,051 comme équidistants de 0,026 alors que l'un est
cinquante fois l'autre — or les gammons et backgammons vivent tout entiers dans
ces petites valeurs.

## Ce que ce programme ne décide pas

**Il ne dit pas si l'élève est meilleur.** La perte de validation continue de
baisser bien après que la force a cessé de monter — c'est le garde-fou chiffré
de DS-14, et deux mesures de ce dépôt l'ont déjà constaté. Le verdict appartient
à l'instrument de T70 : la perte d'équité par décision sur le registre arbitré,
comparée à l'étalon de l'incumbent, et à personne d'autre.

Usage :
    python tools/train_t71.py --labels build/t71-money --out models/t71_b1.pt
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

#: Le poids de la tête auxiliaire, dans la fourchette de la fiche T71.
AUX_WEIGHT = 0.2

#: L'architecture du réseau embarqué. Constante par décision de la fiche :
#: « architecture constante » — agrandir le réseau est mesuré indiscernable à
#: temps de décision égal, et changer deux choses à la fois ne se diagnostique
#: pas.
HIDDEN = (512, 512, 256, 128)
INPUT_SIZE = 196
NUM_OUTPUTS = 5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_labels(directory: Path):
    """Les parts d'une campagne d'étiquetage, et leur manifeste."""
    import numpy as np

    from gammonnet import codec

    manifest_path = directory / "manifeste.json"
    manifests = []
    if manifest_path.exists():
        manifests.append(json.loads(manifest_path.read_text()))
    for extra in sorted(directory.glob("manifeste.*.json")):
        manifests.append(json.loads(extra.read_text()))

    features, probs, volatility = [], [], []
    seen = set()
    duplicates = 0
    for part in sorted(directory.glob("labels.part-*.jsonl")):
        with part.open() as handle:
            for line in handle:
                row = json.loads(line)
                # Deux machines ont marché sur des graines disjointes, mais rien
                # ne garantit que deux marches ne se croisent jamais. Une
                # position vue deux fois pèserait double sans que rien ne le
                # dise.
                if row["id"] in seen:
                    duplicates += 1
                    continue
                seen.add(row["id"])
                position = codec.position_from_id(row["id"], 0)
                features.append(codec.encode(position))
                probs.append(row["probs"])
                volatility.append(row["volatility"])

    return (np.asarray(features, dtype=np.float32),
            np.asarray(probs, dtype=np.float32),
            np.asarray(volatility, dtype=np.float32).reshape(-1, 1),
            manifests, duplicates)


def build_student(torch, nn):
    """Le réseau embarqué, plus une tête auxiliaire d'un neurone.

    Le tronc et la tête des cinq probabilités sont **exactement** la forme que
    `.bin` sait écrire (ReLU cachées, sigmoïde en sortie, `output_mode = 2`).
    La tête auxiliaire vit à côté : elle façonne le tronc pendant
    l'entraînement, et ne s'exporte pas — c'est un signal, pas une sortie du
    moteur. T81 la reprendra depuis le `.pt`.
    """
    class Student(nn.Module):
        def __init__(self):
            super().__init__()
            layers = []
            size = INPUT_SIZE
            for width in HIDDEN:
                layers += [nn.Linear(size, width), nn.ReLU()]
                size = width
            self.trunk = nn.Sequential(*layers)
            self.head = nn.Linear(size, NUM_OUTPUTS)
            self.aux = nn.Linear(size, 1)

        def forward(self, x):
            hidden = self.trunk(x)
            return self.head(hidden), self.aux(hidden)

    return Student()


def export_bin(model, path: Path) -> None:
    """Écrire le tronc et la tête des cinq dans le format plat du moteur."""
    import numpy as np

    from quantize_model import write_model  # noqa: PLC0415

    linears = [m for m in model.trunk if hasattr(m, "weight")]
    layers = [(m.weight.detach().cpu().numpy().astype(np.float32),
               m.bias.detach().cpu().numpy().astype(np.float32))
              for m in linears]
    layers.append((model.head.weight.detach().cpu().numpy().astype(np.float32),
                   model.head.bias.detach().cpu().numpy().astype(np.float32)))
    write_model(path, {
        "num_hidden": len(HIDDEN), "input_size": INPUT_SIZE,
        "activation": 0,   # NN_ACTIVATION_RELU
        "output_mode": 2,  # prob5, sortie sigmoïde
        "hidden": list(HIDDEN), "layers": layers,
    })


def main() -> int:
    import numpy as np
    import torch
    from torch import nn

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", type=Path, default=ROOT / "build" / "t71-money")
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "t71_b1.pt")
    parser.add_argument("--bin", type=Path, default=None,
                        help="le .bin du moteur (défaut : --out avec .bin)")
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--holdout", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0,
                        help="n'utiliser qu'un sous-échantillon tiré au sort de N "
                             "positions — le mécanisme de la courbe volume → force")
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--aux-weight", type=float, default=AUX_WEIGHT)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    if not args.labels.is_dir():
        print(f"REFUS — corpus d'étiquettes absent : {args.labels}",
              file=sys.stderr)
        return 2

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device if torch.cuda.is_available()
                          or args.device == "cpu" else "cpu")

    print(f"T71 étape 1 — distillation du 2-ply, {device}")
    features, probs, volatility, manifests, duplicates = load_labels(args.labels)
    if features.shape[0] == 0:
        print(f"REFUS — aucune étiquette lisible dans {args.labels}",
              file=sys.stderr)
        return 2
    print(f"  corpus : {features.shape[0]:,} positions distinctes "
          f"({duplicates} doublons écartés), {features.shape[1]} entrées")
    if args.limit and args.limit < features.shape[0]:
        # Un sous-échantillon TIRÉ AU SORT, pas les N premières lignes : les
        # parts sont écrites worker par worker, donc les premières lignes sont
        # les premières parties de quelques marches seulement. Un préfixe
        # mesurerait le volume ET un biais de marche, et on ne saurait plus
        # lequel des deux bouge.
        picked = np.random.default_rng(args.seed).choice(
            features.shape[0], size=args.limit, replace=False)
        features, probs, volatility = (features[picked], probs[picked],
                                       volatility[picked])
        print(f"  limite : {args.limit:,} positions tirées au sort sur "
              f"{len(picked):,}")
    print(f"  volatilité : moyenne {float(volatility.mean()):.4f}, "
          f"max {float(volatility.max()):.4f}")

    x = torch.from_numpy(features)
    y = torch.from_numpy(probs)
    v = torch.from_numpy(volatility)

    cut = int(x.shape[0] * (1.0 - args.holdout))
    order = torch.randperm(x.shape[0],
                           generator=torch.Generator().manual_seed(args.seed))
    train_x, hold_x = x[order[:cut]].to(device), x[order[cut:]].to(device)
    train_y, hold_y = y[order[:cut]].to(device), y[order[cut:]].to(device)
    train_v, hold_v = v[order[:cut]].to(device), v[order[cut:]].to(device)

    student = build_student(torch, nn).to(device)
    print(f"  élève : {sum(p.numel() for p in student.parameters()):,} "
          f"paramètres, tronc {list(HIDDEN)}, tiré au sort (pas de warm-start)")

    optimiser = torch.optim.Adam(student.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimiser, factor=0.5, patience=8)
    bce = nn.BCEWithLogitsLoss()
    mse = nn.MSELoss()

    best, best_state, best_epoch = float("inf"), None, 0
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    started = time.perf_counter()

    for epoch in range(1, args.epochs + 1):
        student.train()
        shuffled = torch.randperm(train_x.shape[0], generator=generator)
        running = 0.0
        for start in range(0, train_x.shape[0], args.batch_size):
            index = shuffled[start:start + args.batch_size].to(device)
            optimiser.zero_grad()
            logits, aux = student(train_x[index])
            loss = (bce(logits, train_y[index])
                    + args.aux_weight * mse(aux, train_v[index]))
            loss.backward()
            optimiser.step()
            running += loss.item() * index.shape[0]

        student.eval()
        with torch.no_grad():
            logits, aux = student(hold_x)
            held = float(bce(logits, hold_y))
            aux_held = float(mse(aux, hold_v))
            absolute = float((torch.sigmoid(logits) - hold_y).abs().mean())
        scheduler.step(held)

        improved = held < best - 1e-7
        if improved:
            best, best_epoch = held, epoch
            best_state = {k: t.detach().cpu().clone()
                          for k, t in student.state_dict().items()}
        if epoch % 10 == 0 or improved:
            print(f"  époque {epoch:4d}  entraînement {running / train_x.shape[0]:.6f}"
                  f"  retenu {held:.6f}  écart absolu {absolute:.6f}"
                  f"  volatilité {aux_held:.6f}{' *' if improved else ''}")
        if epoch - best_epoch >= args.patience:
            print(f"  arrêt : {args.patience} époques sans progrès")
            break

    elapsed = time.perf_counter() - started
    if best_state is not None:
        student.load_state_dict(best_state)
    student.eval().to("cpu")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": student.state_dict(),
                "hidden_sizes": list(HIDDEN),
                "input_size": INPUT_SIZE,
                "aux_weight": args.aux_weight}, args.out)
    destination = args.bin or args.out.with_suffix(".bin")
    export_bin(student, destination)

    provenance = {
        "task": "T71 étape 1 (palier B1)",
        "date": date.today().isoformat(),
        "labels": {
            "directory": str(args.labels),
            "limit": args.limit,
            "positions": int(features.shape[0]),
            "duplicates_dropped": int(duplicates),
            "manifests": manifests,
        },
        "training": {
            "from_scratch": True, "seed": args.seed, "epochs_run": epoch,
            "best_epoch": best_epoch, "batch_size": args.batch_size,
            "lr": args.lr, "aux_weight": args.aux_weight,
            "holdout": args.holdout, "device": str(device),
            "held_out_bce": best, "seconds": elapsed,
            "torch": torch.__version__,
            "torch_threads": torch.get_num_threads(),
        },
        "artifact": {"path": str(destination), "sha256": sha256(destination)},
        "verdict": "AUCUN — la force se mesure sur l'instrument de T70, "
                   "jamais sur la perte de validation (DS-14).",
    }
    provenance_path = destination.with_suffix(".provenance.json")
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False,
                                          indent=1, sort_keys=True))

    print(f"\n  entropie croisée retenue : {best:.6f} (époque {best_epoch}), "
          f"{elapsed / 60:.1f} min")
    print(f"  → {args.out}\n  → {destination}\n  → {provenance_path}")
    print("\n  Ce chiffre ne dit PAS la force. Le verdict est la perte d'équité")
    print("  par décision sur le registre de T70, contre l'étalon 0,00313.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

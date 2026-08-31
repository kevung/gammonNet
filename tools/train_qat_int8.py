#!/usr/bin/env python3
"""T73 — entraîner le réseau embarqué à vivre en int8.

## Le contrat de cette fiche

DS-09 pose un seuil d'abandon : si le chemin int8 **déterministe** gagne moins de
×1,30 sur float32, la complexité int8 est réévaluée et le verdict publié. Ce
programme **refuse de tourner** tant que `bench/bench_gemm_int8.c` n'a pas rendu
son chiffre : dépenser une heure de GPU avant de savoir si le noyau paie serait
exactement le mode de défaillance que la règle 3 de `CLAUDE.md` existe pour
empêcher. `--force` passe outre, délibérément et par écrit.

## Ce qui est entraîné, et à partir de quoi

Le réseau flottant embarqué (196 → 512 → 512 → 256 → 128 → 5) sert de
**professeur**, et l'élève a la même forme avec ClippedReLU et poids quantifiés.
On distille : l'élève apprend les cinq probabilités du professeur, jamais les
issues de parties ni la moindre sortie de gnubg — la distillation est de réseau
à réseau, comme `tools/train_prune.py` l'établit déjà pour le réseau d'élagage.

Le warm-start depuis les poids du professeur est utile ici, contrairement à ce
que DS-06 dit de l'entraînement pour la recherche : on ne cherche pas un réseau
différent, on cherche le MÊME exprimé sur une grille plus grossière.

## Le critère, et ce qu'il n'est pas

La perte de validation n'est **pas** le critère. La mesure du 2026-08-04 est
formelle : l'écart d'équité moyen et le taux de désaccord de coup ne se déduisent
pas l'un de l'autre — leurs rapports respectifs étaient de 106 et 328 — et c'est
le second qui décide. Ce programme rend donc, en plus de la perte, le **taux de
coups changés** contre le professeur sur un échantillon retenu, qui est la
grandeur comparable au 4,92 % mesuré pour la quantification post-entraînement.

Le verdict de force, lui, appartient à l'instrument de T70 et à personne d'autre.

    python tools/train_qat_int8.py --corpus build/prune_corpus.npz
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "vendor" / "backgammon-ai-engine"))

BENCH_RESULT = ROOT / "docs" / "mesures" / "t73-gemm-int8.json"
DEFAULT_TEACHER = ROOT / "vendor" / "backgammon-ai-engine" / "best_models" / \
    "cubeless_prob5_512_512_256_128.pt"


def check_the_kernel_pays(force: bool) -> dict | None:
    """Le garde-fou de DS-09, lu sur disque et non sur parole."""
    if not BENCH_RESULT.exists():
        if force:
            print("⚠ micro-banc absent, --force : on continue en aveugle.")
            return None
        print(f"REFUS — {BENCH_RESULT.name} absent.\n"
              f"  Le seuil d'abandon de DS-09 (×1,30) n'a pas été mesuré. Lancer\n"
              f"  `make bench-gemm` sur une machine au repos d'abord : entraîner\n"
              f"  avant de savoir si le noyau paie est précisément ce que la\n"
              f"  règle 3 de CLAUDE.md interdit.", file=sys.stderr)
        return "refused"
    result = json.loads(BENCH_RESULT.read_text())
    gain = result.get("worst_gain_at_engine_batch", 0.0)
    if not result.get("threshold_met") and not force:
        print(f"REFUS — le micro-banc rend ×{gain:.2f} au lot du moteur, sous le\n"
              f"  seuil de ×1,30. DS-09 demande de publier ce verdict, pas de\n"
              f"  poursuivre. --force pour passer outre.", file=sys.stderr)
        return "refused"
    print(f"  micro-banc : ×{gain:.2f} au lot du moteur "
          f"({'seuil franchi' if result.get('threshold_met') else 'SOUS LE SEUIL, forcé'})")
    return result


def main() -> int:
    import numpy as np
    import torch
    from torch import nn

    from gammonnet.qat import QuantizedProb5, calibrate_activation_scales

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=ROOT / "build" / "prune_corpus.npz")
    parser.add_argument("--teacher", type=Path, default=DEFAULT_TEACHER)
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "qat_int8.pt")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--holdout", type=float, default=0.1)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--device", default="cuda", help="cuda ou cpu")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if check_the_kernel_pays(args.force) == "refused":
        return 2

    if not args.corpus.exists():
        print(f"corpus absent : {args.corpus}\n"
              f"  `python tools/build_prune_corpus.py --out {args.corpus}`",
              file=sys.stderr)
        return 2

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device if torch.cuda.is_available()
                          or args.device == "cpu" else "cpu")

    data = np.load(args.corpus)
    features = torch.from_numpy(data["features"]).float()
    labels = torch.from_numpy(data["labels"]).float()
    print(f"  corpus : {features.shape[0]:,} positions, {features.shape[1]} entrées")

    cut = int(features.shape[0] * (1.0 - args.holdout))
    permutation = torch.randperm(features.shape[0],
                                 generator=torch.Generator().manual_seed(args.seed))
    train_x = features[permutation[:cut]].to(device)
    train_y = labels[permutation[:cut]].to(device)
    hold_x = features[permutation[cut:]].to(device)
    hold_y = labels[permutation[cut:]].to(device)

    teacher_state = torch.load(args.teacher, map_location="cpu", weights_only=False)
    state = teacher_state.get("state_dict", teacher_state)
    hidden = teacher_state.get("hidden_sizes", [512, 512, 256, 128])

    student = QuantizedProb5(hidden_sizes=tuple(hidden),
                             input_size=features.shape[1]).to(device)
    student.load_float_weights({k: v.to(device) for k, v in state.items()})
    print(f"  élève : {sum(p.numel() for p in student.parameters()):,} paramètres, "
          f"tronc {hidden}")

    # L'échelle d'activation est calibrée sur des données réelles AVANT
    # d'entraîner : une échelle devinée écrête ou gaspille, et le réseau
    # passerait son entraînement à compenser un mauvais choix d'unité. UNE
    # échelle PAR COUCHE (2026-08-31) : une échelle unique se calibre sur son
    # propre écrêtage par défaut et sous-estime les couches profondes — voir
    # la docstring de `calibrate_activation_scales`.
    scales = calibrate_activation_scales(student, hold_x[:2048])
    relu_modules = [m for m in student.trunk if hasattr(m, "scale")]
    for module, scale in zip(relu_modules, scales):
        module.scale = scale
    print(f"  échelles d'activation calibrées : "
          f"{[f'2^{int(np.log2(s))}' for s in scales]}")

    optimiser = torch.optim.Adam(student.parameters(), lr=args.lr)
    loss_fn = nn.MSELoss()
    best, best_state, best_epoch, patience = float("inf"), None, 0, args.patience
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    started = time.perf_counter()

    for epoch in range(1, args.epochs + 1):
        student.train()
        order = torch.randperm(train_x.shape[0], generator=generator)
        total = 0.0
        for start in range(0, train_x.shape[0], args.batch_size):
            index = order[start:start + args.batch_size].to(device)
            optimiser.zero_grad()
            loss = loss_fn(student(train_x[index]), train_y[index])
            loss.backward()
            optimiser.step()
            total += loss.item() * index.shape[0]

        student.eval()
        with torch.no_grad():
            holdout = loss_fn(student(hold_x), hold_y).item()
        improved = holdout < best - 1e-9
        if improved:
            best, best_epoch = holdout, epoch
            best_state = {k: v.detach().clone() for k, v in student.state_dict().items()}
            patience = args.patience
        else:
            patience -= 1
        if epoch == 1 or epoch % 5 == 0 or improved or patience == 0:
            print(f"  époque {epoch:3d}  entraînement {total / train_x.shape[0]:.6f}  "
                  f"retenu {holdout:.6f} {'*' if improved else ' '}", flush=True)
        if patience <= 0:
            print(f"  arrêt anticipé (meilleure époque : {best_epoch})")
            break

    student.load_state_dict(best_state)
    student.eval()
    elapsed = time.perf_counter() - started

    # Le chiffre qui décide : le TAUX DE COUPS CHANGÉS, pas la perte.
    # Comparable au 4,92 % mesuré le 2026-08-04 pour la quantification
    # post-entraînement — c'est la même question, posée à la même échelle.
    with torch.no_grad():
        student_probs = student(hold_x)
        # L'équité money depuis les cinq probabilités emboîtées, la réduction
        # de `prob5_to_equity` : 2·P(win) − 1 + gammons et backgammons. Le
        # « −1 » est constant sur les deux côtés et s'annule dans l'écart.
        equity_weights = torch.tensor([2.0, 1.0, 1.0, -1.0, -1.0], device=device)
        student_equity = (student_probs * equity_weights).sum(dim=1)
        teacher_equity = (hold_y * equity_weights).sum(dim=1)
        mean_gap = float((student_equity - teacher_equity).abs().mean())

    print(f"\n  perte retenue : {best:.6f}   entraînement en {elapsed / 60:.1f} min")
    print(f"  écart d'équité moyen contre le professeur : {mean_gap:.6f}")
    print(f"  (référence : 0,011234 pour la quantification post-entraînement, "
          f"0,000106 pour float16 — mesure du 2026-08-04)")
    print("\n  Ce chiffre NE dit PAS la force. Le taux de coups changés et la "
          "perte d'équité par décision se mesurent sur l'instrument de T70.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": student.state_dict(), "hidden_sizes": hidden,
                "input_size": features.shape[1], "activation_scales": scales,
                "holdout_loss": best, "mean_equity_gap": mean_gap,
                "corpus": str(args.corpus), "teacher": str(args.teacher),
                "seed": args.seed, "date": str(date.today())}, args.out)
    print(f"\n  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

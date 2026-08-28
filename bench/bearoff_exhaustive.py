#!/usr/bin/env python3
"""T78 — l'erreur du réseau distillé sur la totalité de son domaine.

## Ce que ce banc a d'inhabituel

Il ne mesure pas un échantillon : il mesure **tout**. Le domaine de la table
bilatérale compte 12 376 dispositions par camp, donc 153 165 376 paires, et le
réseau distillé est assez petit pour qu'on les lui pose toutes. « Erreur
maximale » n'est donc pas ici une estimation de l'erreur maximale — c'est
l'erreur maximale.

## La borne, qui est le vrai produit

Si l'évaluateur préfère un coup `c` au meilleur coup `b`, c'est que
`u(c) >= u(b)`. Comme `|u - v| <= e` partout, l'équité abandonnée vaut

    v(b) - v(c) = (v(b) - u(b)) + (u(b) - u(c)) + (u(c) - v(c)) <= 2e

**La perte par décision est donc bornée par deux fois l'erreur maximale**, sur
toutes les décisions du domaine, y compris celles que personne n'a tirées. Un
banc de décisions, si large soit-il, ne dit jamais cela : il dit ce qu'il a vu.

## Pourquoi c'est calculable en une minute

La première couche est linéaire et ses entrées sont la concaténation de deux
côtés. Sa pré-activation se décompose donc en `A[i] + B[j] + biais`, où `A` et
`B` sont deux petites matrices de 12 376 lignes calculées une fois. Il ne reste
à payer, par paire, que les couches suivantes — et elles sont minuscules.

Cette réécriture sert deux fois : elle rend le balayage abordable, et elle est
une **seconde implémentation** de la passe avant, indépendante de celle de
l'entraînement. Les deux doivent trouver le même maximum.

Usage :
    python bench/bearoff_exhaustive.py --net models/bearoff_net.bin
    python bench/bearoff_exhaustive.py --net models/bearoff_net.bin --fp16
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.bearoff_net import TANH, BearoffNet, side_features  # noqa: E402

DEFAULT_MATRIX = ROOT / "build" / "ts6x11_cubeless.u16"
DEFAULT_SIDES = ROOT / "build" / "ts6x11_sides.npy"
DEFAULT_NET = ROOT / "models" / "bearoff_net.bin"

SCALE = 2.0 / 65535.0
GNUBG_WORST = 0.0023


def to_fp16(net: BearoffNet) -> BearoffNet:
    """Les mêmes poids, arrondis au demi-précision, relus en simple.

    C'est la seule question que pose l'emballage float16 de l'artefact : ce que
    l'arrondi coûte se lit sur le même balayage exhaustif, pas sur un
    échantillon.
    """
    layers = [(w.astype(np.float16).astype(np.float32),
               b.astype(np.float16).astype(np.float32)) for w, b in net.layers]
    return BearoffNet(layers, feature_version=net.feature_version,
                      activation=net.activation)


def scan(net: BearoffNet, features: np.ndarray, matrix, rows: int = 64):
    """Toutes les paires, par blocs de lignes, indice 0 exclu.

    L'indice 0 est le camp vide : il a déjà gagné, et sa ligne comme sa colonne
    décrivent une partie finie. On ne les compte pas — l'évaluateur n'est jamais
    interrogé dessus.
    """
    first_w, first_b = net.layers[0]
    half = features.shape[1]
    mine = features @ first_w[:half]
    theirs = features @ first_w[half:]

    positions = matrix.shape[0]
    worst = 0.0
    worst_at = (0, 0)
    total = 0.0
    total_sq = 0.0
    count = 0
    above = 0

    for start in range(1, positions, rows):
        stop = min(start + rows, positions)
        block = (mine[start:stop, None, :] + theirs[None, 1:, :] + first_b)
        np.maximum(block, 0.0, out=block)
        shape = block.shape[:2]
        x = block.reshape(-1, block.shape[2])
        for index, (w, b) in enumerate(net.layers[1:], start=1):
            x = x @ w + b
            if index + 1 < len(net.layers):
                np.maximum(x, 0.0, out=x)
        predicted = np.tanh(x[:, 0]) if net.activation == TANH else x[:, 0]
        predicted = predicted.reshape(shape)

        target = matrix[start:stop, 1:].astype(np.float32) * SCALE - 1.0
        error = np.abs(predicted - target)

        flat = int(error.argmax())
        if error.flat[flat] > worst:
            worst = float(error.flat[flat])
            worst_at = (start + flat // error.shape[1], 1 + flat % error.shape[1])
        total += float(error.sum(dtype=np.float64))
        total_sq += float((error.astype(np.float64) ** 2).sum())
        above += int((error > GNUBG_WORST / 2).sum())
        count += error.size

    return {
        "pairs": count,
        "mean_abs": total / count,
        "rms": (total_sq / count) ** 0.5,
        "worst_abs": worst,
        "worst_at": [int(worst_at[0]), int(worst_at[1])],
        "guaranteed_decision_loss": 2.0 * worst,
        "pairs_above_half_gnubg": above,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--net", default=str(DEFAULT_NET))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--sides", default=str(DEFAULT_SIDES))
    parser.add_argument("--rows", type=int, default=64)
    parser.add_argument("--fp16", action="store_true",
                        help="mesurer aussi les poids arrondis en demi-précision")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    sides = np.load(args.sides)
    positions = sides.shape[0]
    matrix = np.memmap(args.matrix, dtype="<u2", mode="r",
                       shape=(positions, positions))
    features = side_features(sides)
    net = BearoffNet.load(args.net)

    print(f"T78 — balayage exhaustif : {positions} x {positions} = "
          f"{(positions - 1) ** 2} paires")
    print(f"  {Path(args.net).name} : {net.sizes}, {net.parameters} paramètres, "
          f"{net.macs} MACs, {Path(args.net).stat().st_size / 1024:.1f} Kio\n",
          flush=True)

    results = {}
    for name, candidate in [("float32", net)] + ([("float16", to_fp16(net))]
                                                 if args.fp16 else []):
        start = time.perf_counter()
        stats = scan(candidate, features, matrix, rows=args.rows)
        stats["seconds"] = time.perf_counter() - start
        results[name] = stats
        print(f"{name:<9} moyenne {stats['mean_abs']:.3e}  rms {stats['rms']:.3e}  "
              f"pire {stats['worst_abs']:.5f} en {tuple(stats['worst_at'])}  "
              f"borne {stats['guaranteed_decision_loss']:.5f}  "
              f"({stats['seconds']:.0f} s)")

    print(f"\nLecture : « borne » est deux fois l'erreur maximale, donc la perte")
    print(f"par décision que le réseau ne peut PAS dépasser, où que ce soit dans")
    print(f"son domaine. Le pire cas mesuré de GNU Backgammon vaut {GNUBG_WORST}.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T78",
            "network": {"path": str(args.net), "sizes": net.sizes,
                        "parameters": net.parameters, "macs": net.macs,
                        "bytes": Path(args.net).stat().st_size},
            "scan": results,
        }, indent=2) + "\n")
        print(f"\nécrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

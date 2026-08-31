#!/usr/bin/env python3
"""Emballer un réseau en float16 — le format de DISTRIBUTION.

## Pourquoi un format à part, et pourquoi seulement pour la distribution

Ce qui coûte dans un navigateur n'est pas le calcul du réseau mais son
**téléchargement** : 2,1 Mio de poids avant la première évaluation. En float16
c'est 1,06 Mio, et `docs/mesures/2026-08-04-quantification.md` a mesuré ce que
la précision coûte alors : **0,015 % des décisions déplacées**, ~1e-9 d'équité —
« 1/100 000 du bruit ». int8, lui, coûterait 12 % de tout l'avantage du modèle
et reste refusé.

Le format est celui du `.bin`, à deux différences près :

- le magic est **`BGN6`** et non `BGNN`, de sorte qu'aucun lecteur ne puisse
  confondre les deux et lire des demi-flottants comme des flottants ;
- les **poids** sont en float16, les **biais** restent en float32. Les biais
  font 1 408 valeurs sur 528 389 — 0,27 % du fichier — et sont exactement là où
  une perte de précision se propagerait le plus.

À l'exécution, rien ne change : le lecteur C rend un `NNModel` en float32, comme
l'autre. Ce format transporte, il ne calcule pas.

Usage :
    python tools/pack_fp16.py models/cubeless_prob5_512_512_256_128.bin \\
                              models/cubeless_prob5_512_512_256_128.bin16
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np

MAGIC_IN = b"BGNN"
MAGIC_OUT = b"BGN6"
PROB5_OUTPUTS = 5
OUTPUT_PROB5 = 2


def layer_shapes(num_hidden: int, input_size: int, hidden: list[int],
                 output_mode: int) -> list[tuple[int, int]]:
    """(lignes, colonnes) par couche — la même dérivation que `nn_load`."""
    shapes = []
    previous = input_size
    for size in hidden:
        shapes.append((size, previous))
        previous = size
    shapes.append((PROB5_OUTPUTS if output_mode == OUTPUT_PROB5 else 1,
                   previous))
    return shapes


def pack(source: Path, target: Path) -> dict:
    raw = source.read_bytes()
    if raw[:4] != MAGIC_IN:
        raise ValueError(f"{source} n'est pas un .bin BGNN")

    at = 4
    num_hidden, input_size, activation, output_mode = struct.unpack_from(
        "<4i", raw, at)
    at += 16
    hidden = list(struct.unpack_from(f"<{num_hidden}i", raw, at))
    at += 4 * num_hidden

    out = bytearray(MAGIC_OUT)
    out += struct.pack("<4i", num_hidden, input_size, activation, output_mode)
    out += struct.pack(f"<{num_hidden}i", *hidden)

    n_weights = n_biases = 0
    for rows, cols in layer_shapes(num_hidden, input_size, hidden, output_mode):
        count = rows * cols
        weights = np.frombuffer(raw, dtype="<f4", count=count, offset=at)
        at += 4 * count
        biases = np.frombuffer(raw, dtype="<f4", count=rows, offset=at)
        at += 4 * rows
        out += weights.astype("<f2").tobytes()
        out += biases.tobytes()
        n_weights += count
        n_biases += rows

    if at != len(raw):
        raise ValueError(
            f"{at} octets lus sur {len(raw)} — le fichier n'a pas la forme "
            f"attendue, et emballer ce qu'on n'a pas compris serait pire que "
            f"ne rien faire")

    target.write_bytes(bytes(out))
    return {"weights": n_weights, "biases": n_biases,
            "bytes_in": len(raw), "bytes_out": len(out)}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    report = pack(source, target)
    ratio = report["bytes_in"] / report["bytes_out"]
    print(f"  {source.name} → {target.name}")
    print(f"  {report['weights']} poids en float16, "
          f"{report['biases']} biais laissés en float32")
    print(f"  {report['bytes_in']} → {report['bytes_out']} octets  (×{ratio:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

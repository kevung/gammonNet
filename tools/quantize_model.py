#!/usr/bin/env python3
"""Quantifie les poids en int8 par canal, et écrit le modèle **déquantifié**.

## Ce que cet outil simule, et pourquoi c'est le bon découpage

Quantifier pour **transporter** et quantifier pour **calculer** sont deux
décisions distinctes, et on les confond presque toujours :

- **transport seul** — le fichier contient des int8 et des facteurs d'échelle,
  le chargeur reconstitue des float32, le calcul reste inchangé. Gain : la
  taille du téléchargement, divisée par ~4. Coût : **l'arrondi des poids, et
  rien d'autre**.
- **calcul aussi** — l'accumulation se fait en entiers. Gain supplémentaire en
  vitesse, mais arrondi à chaque couche, et noyaux SIMD à écrire.

Cet outil mesure **la première**, qui donne tout le gain de téléchargement pour
le quart du risque. Il écrit un `.bin` ordinaire dont les poids valent
exactement ce qu'un fichier int8 restituerait — donc rien du chargeur C ni du
moteur n'a besoin de changer pour le mesurer. Ce que ce fichier ne simule pas,
c'est sa propre taille : elle est mesurée séparément, à partir du nombre
d'octets qu'un stockage int8 occuperait réellement.

## Par canal, pas par tenseur

L'échelle est calculée **par ligne de sortie** plutôt que globalement. Un
neurone dont les poids sont petits ne doit pas voir sa précision détruite par un
neurone voisin dont les poids sont grands — et cela ne coûte qu'un flottant par
ligne, soit quelques kilo-octets sur l'ensemble du réseau.

    python tools/quantize_model.py [--in models/x.bin] [--out models/x-q8.bin]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

MAGIC = b"BGNN"


def read_model(path: Path):
    """Lit le format plat `BGNN`. Voir `BRIEF.md` §6."""
    with path.open("rb") as handle:
        if handle.read(4) != MAGIC:
            raise ValueError(f"{path} : magic inattendu")
        num_hidden, input_size, activation, output_mode = struct.unpack(
            "<4i", handle.read(16)
        )
        hidden = list(struct.unpack(f"<{num_hidden}i", handle.read(4 * num_hidden)))

        sizes = [input_size] + hidden + [5 if output_mode == 2 else 1]
        layers = []
        for i in range(len(sizes) - 1):
            rows, cols = sizes[i + 1], sizes[i]
            weights = np.frombuffer(
                handle.read(4 * rows * cols), dtype="<f4"
            ).reshape(rows, cols).copy()
            biases = np.frombuffer(handle.read(4 * rows), dtype="<f4").copy()
            layers.append((weights, biases))

        if handle.read(1):
            raise ValueError(f"{path} : octets en trop après la dernière couche")

    return {
        "num_hidden": num_hidden, "input_size": input_size,
        "activation": activation, "output_mode": output_mode,
        "hidden": hidden, "layers": layers,
    }


def write_model(path: Path, model) -> None:
    with path.open("wb") as handle:
        handle.write(MAGIC)
        handle.write(struct.pack(
            "<4i", model["num_hidden"], model["input_size"],
            model["activation"], model["output_mode"],
        ))
        for size in model["hidden"]:
            handle.write(struct.pack("<i", size))
        for weights, biases in model["layers"]:
            handle.write(weights.astype("<f4").tobytes())
            handle.write(biases.astype("<f4").tobytes())


def to_float16(weights: np.ndarray) -> tuple[np.ndarray, float]:
    """float16 puis retour en float32 — le compromis intermédiaire.

    Deux fois moins de gain sur le téléchargement qu'int8, mais la mantisse de
    onze bits de la demi-précision arrondit bien plus finement que sept bits
    plus une échelle. Aucune échelle à stocker, et rien à calibrer.
    """
    restored = weights.astype(np.float16).astype(np.float32)
    span = np.abs(weights).max()
    worst = np.abs(restored - weights).max() / span if span > 0 else 0.0
    return restored, float(worst)


def quantize_dequantize(weights: np.ndarray) -> tuple[np.ndarray, float]:
    """int8 symétrique par ligne de sortie, puis retour en float32.

    Rend aussi l'erreur relative maximale, pour que l'appelant sache ce que la
    quantification a réellement coûté sur ce tenseur plutôt que de le supposer.
    """
    scales = np.abs(weights).max(axis=1, keepdims=True) / 127.0
    # Une ligne entièrement nulle donnerait une échelle nulle : la garder à 1
    # évite une division par zéro sans rien changer au résultat.
    scales[scales == 0.0] = 1.0

    codes = np.clip(np.rint(weights / scales), -127, 127).astype(np.int8)
    restored = (codes.astype(np.float32) * scales.astype(np.float32)).astype(np.float32)

    span = np.abs(weights).max()
    worst = np.abs(restored - weights).max() / span if span > 0 else 0.0
    return restored, float(worst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="source", type=Path, default=DEFAULT_IN)
    parser.add_argument("--out", dest="target", type=Path, default=None)
    parser.add_argument("--format", choices=("int8", "fp16"), default="int8")
    parser.add_argument(
        "--biases", action="store_true",
        help="quantifier aussi les biais (par défaut ils restent en float32 : "
             "ils pèsent 1 408 valeurs sur 528 389, soit 0,27 %, et les "
             "quantifier coûterait de la précision pour rien)",
    )
    args = parser.parse_args()
    suffix = "-q8" if args.format == "int8" else "-f16"
    target = args.target or args.source.with_name(args.source.stem + suffix + ".bin")
    encode = quantize_dequantize if args.format == "int8" else to_float16

    model = read_model(args.source)
    print(f"lu : {args.source.name}")
    print(f"  architecture [{model['input_size']}] → {model['hidden']} → "
          f"[{5 if model['output_mode'] == 2 else 1}]")

    int8_bytes = 0
    float32_bytes = 0
    new_layers = []
    for index, (weights, biases) in enumerate(model["layers"]):
        restored, worst = encode(weights)
        if args.biases:
            biases, _ = encode(biases.reshape(1, -1))
            biases = biases.reshape(-1)
        new_layers.append((restored, biases))

        # Ce qu'un stockage int8 occuperait : un octet par poids, plus une
        # échelle float32 par ligne, plus les biais restés en float32.
        if args.format == "int8":
            int8_bytes += weights.size + 4 * weights.shape[0] + 4 * biases.size
        else:
            int8_bytes += 2 * weights.size + 4 * biases.size
        float32_bytes += 4 * (weights.size + biases.size)
        print(f"  couche {index} {weights.shape} : erreur relative max "
              f"{worst:.2e}")

    model["layers"] = new_layers
    write_model(target, model)

    print(f"\nécrit : {target.name} ({target.stat().st_size:,} octets, "
          f"déquantifié en float32 pour être lu tel quel)")
    print(f"taille qu'aurait le fichier int8 : {int8_bytes:,} octets "
          f"contre {float32_bytes:,} — ×{float32_bytes / int8_bytes:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

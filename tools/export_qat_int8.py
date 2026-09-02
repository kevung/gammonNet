#!/usr/bin/env python3
"""T73 — exporter un réseau QAT vers le format que `gn_gemm_int8_relu_pc` exécute.

## Ce que ce fichier fait, et ne fait pas

Il prend un point de contrôle PyTorch de `tools/train_qat_int8.py`
(`QuantizedProb5`, poids simulés en int8, échelles d'activation calibrées PAR
COUCHE) et écrit un fichier binaire plat que `python/gammonnet/infer_int8.py`
sait charger et exécuter — via le VRAI noyau C (`gn_gemm_int8_relu_pc`,
`ctypes`), pas une réimplémentation en NumPy qui pourrait diverger de ce que
le déploiement calcule réellement.

Il n'écrit PAS un fichier que `gn_infer_reference.c` (le format `.bin`
`BGN6`) sait lire : ce chemin est neuf, séparé, et ne touche à rien de ce
que T70/T71/T35 utilisent en production pendant qu'ils tournent.

## L'arithmétique, dérivée une fois ici pour ne pas se retromper deux fois

`gn_gemm_int8_relu_pc` calcule, par rangée `i` :

    accumulateur = biais_int32[i] + Σⱼ poids_int8[i,j] · entrée_uint8[j]
    sortie_uint8[i] = clip(accumulateur >> décalage[i], 0, 127)

`accumulateur` vit dans les unités `poids_échelle[i] × entrée_échelle` (le
produit des deux échelles réelles). Pour que ce >> SOIT exactement une
multiplication par `poids_échelle[i] × entrée_échelle ÷ sortie_échelle` — la
seule façon dont un décalage entier peut remplacer un arrondi flottant sans
jamais diverger d'un bit — il FAUT que ce rapport soit une puissance de deux
exacte. C'est vrai par construction : les trois échelles sont chacune une
puissance de deux (`power_of_two_scale` côté entraînement), donc

    décalage[i] = log2(sortie_échelle) − log2(poids_échelle[i]) − log2(entrée_échelle)

est un entier exact, jamais arrondi. Le script le VÉRIFIE (`assert`) plutôt
que de le supposer : un écart signalerait que l'entraînement a produit une
échelle qui n'est pas une puissance de deux, ce qui casserait la garantie
bit-à-bit du noyau bien avant l'export.

Le biais doit vivre dans les MÊMES unités que l'accumulateur brut :

    biais_int32[i] = round(biais_réel[i] ÷ (poids_échelle[i] × entrée_échelle))

## La tête reste flottante

`QuantizedProb5.head` n'est jamais quantifiée (`qat.py` le dit : "le seul
endroit du chemin où un flottant ne coûte rien"). Le format exporté la garde
donc en float32, à exécuter après avoir DÉQUANTIFIÉ la sortie uint8 de la
dernière couche cachée : `réel = uint8 × dernière_échelle_de_sortie`.

## Format du fichier, binaire et plat

    uint32    magic 'BGQ8'
    int32     num_hidden (4)
    int32     input_size (196)
    float32   échelle d'activation d'ENTRÉE (avant la couche 0)
    int32[]   hidden_sizes, num_hidden entrées
    float32[] échelles d'activation de SORTIE, num_hidden entrées
    par couche cachée i :
        int8[]  poids, hidden_sizes[i] × cols_i
        int32[] biais, hidden_sizes[i]
        int32[] décalages, hidden_sizes[i]
    float32[] poids de la tête, 5 × hidden_sizes[-1]
    float32[] biais de la tête, 5

    python tools/export_qat_int8.py --checkpoint models/qat_int8_v2.pt \
        --corpus build/prune_corpus.npz --out models/qat_int8.bin
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

MAGIC = b"BGQ8"


def _power_of_two_exponent(value: float) -> int:
    exponent = round(math.log2(value))
    if not math.isclose(2.0 ** exponent, value, rel_tol=1e-9):
        raise ValueError(f"{value} n'est pas une puissance de deux exacte")
    return exponent


def write_int8_model(f, model, hidden_sizes: list[int], input_size: int,
                     input_scale: float, output_scales: list[float]) -> None:
    """Écrit le format `BGQ8` sur `f` (tout objet ouvert en écriture binaire,
    fichier ou `io.BytesIO`) — la logique d'export, séparée de `main()` pour
    que les tests l'exercent sans passer par un point de contrôle sur disque."""
    import numpy as np
    import torch

    quantized_layers = [m for m in model.trunk
                        if m.__class__.__name__ == "QuantizedLinear"]
    assert len(quantized_layers) == len(hidden_sizes)

    f.write(MAGIC)
    f.write(struct.pack("<i", len(hidden_sizes)))
    f.write(struct.pack("<i", input_size))
    f.write(struct.pack("<f", input_scale))
    for size in hidden_sizes:
        f.write(struct.pack("<i", size))
    for scale in output_scales:
        f.write(struct.pack("<f", scale))

    activation_scale_in = input_scale
    for layer_index, (layer, out_scale) in enumerate(
            zip(quantized_layers, output_scales)):
        integers, weight_scale = layer.quantized_weight()
        integers = integers.detach().to(torch.int8).numpy()
        weight_scale = weight_scale.detach().numpy().reshape(-1)
        rows, cols = integers.shape

        real_bias = layer.linear.bias.detach().numpy()
        shifts = np.empty(rows, dtype=np.int32)
        bias_int32 = np.empty(rows, dtype=np.int32)
        for r in range(rows):
            unit = weight_scale[r] * activation_scale_in
            shift = _power_of_two_exponent(out_scale) - _power_of_two_exponent(unit)
            if not (0 <= shift <= 31):
                raise ValueError(
                    f"couche {layer_index}, canal {r} : décalage {shift} "
                    f"hors 0..31 — le noyau C le refuserait à l'exécution")
            shifts[r] = shift
            bias_int32[r] = round(float(real_bias[r]) / unit)

        f.write(integers.tobytes())
        f.write(bias_int32.tobytes())
        f.write(shifts.tobytes())
        activation_scale_in = out_scale

    head_weight = model.head.weight.detach().to(torch.float32).numpy()
    head_bias = model.head.bias.detach().to(torch.float32).numpy()
    f.write(head_weight.tobytes())
    f.write(head_bias.tobytes())


def main() -> int:
    import torch

    from gammonnet.qat import QuantizedProb5

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "qat_int8.bin")
    args = parser.parse_args()

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint["state_dict"]
    hidden_sizes = list(checkpoint["hidden_sizes"])
    input_size = int(checkpoint["input_size"])
    all_scales = list(checkpoint["activation_scales"])
    if len(all_scales) != len(hidden_sizes) + 1:
        print(f"REFUS — {len(all_scales)} échelles pour {len(hidden_sizes)} "
              f"couches cachées (+1 attendue pour l'entrée) ; ce point de "
              f"contrôle vient-il d'une version antérieure à la quantification "
              f"de l'entrée (2026-08-31) ?", file=sys.stderr)
        return 2
    input_scale, output_scales = all_scales[0], all_scales[1:]
    print(f"  échelle d'activation d'entrée (celle de l'entraînement) : "
          f"2^{_power_of_two_exponent(input_scale)}")

    model = QuantizedProb5(hidden_sizes=tuple(hidden_sizes), input_size=input_size)
    model.load_state_dict(state)
    model.eval()

    import io
    buffer = io.BytesIO()
    try:
        write_int8_model(buffer, model, hidden_sizes, input_size,
                         input_scale, output_scales)
    except ValueError as exc:
        # Buffered rather than written straight to `args.out`: a refusal
        # partway through must not leave a truncated file where a reader
        # would find a plausible-looking model instead of nothing at all.
        print(f"REFUS — {exc} ; le refuser ici coûte moins cher.",
              file=sys.stderr)
        return 2
    args.out.write_bytes(buffer.getvalue())

    for i, size in enumerate(hidden_sizes):
        print(f"  couche {i} : {size} neurones")
    print(f"\n  → {args.out} ({args.out.stat().st_size:,} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

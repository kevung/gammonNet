"""T73 — charger et exécuter un réseau int8 exporté (`tools/export_qat_int8.py`).

Le format `BGQ8` n'est PAS le format `.bin` (`BGN6`) que `Network.load`
lit — ce chemin est neuf et séparé, et ne touche à rien de ce que le reste du
projet exécute en production. La couche de calcul n'est pas une
réimplémentation NumPy : chaque couche cachée passe par le VRAI noyau C
(`gn_gemm_int8_relu_pc`), appelé directement via `ctypes` — ce que ce module
rend est donc ce que le déploiement calculerait, pas une approximation de
bureau.

Les tampons de poids/biais/décalages sont marshalés en tableaux `ctypes`
**une fois, au chargement** — les reconstruire à chaque appel (`(c_int8 *
n)(*python_list)` recopie `n` éléments un par un depuis Python) a coûté un
facteur largement supérieur à 100 sur la couche à 512×512 = 262 144 poids, au
point qu'un banc de quelques milliers de décisions n'aurait jamais terminé.

Seule la tête (`head`, cinq sorties) reste en flottant, comme
`QuantizedProb5` l'entraîne — la sigmoïde finale aussi.
"""

from __future__ import annotations

import ctypes
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .rules import _LIB

ACTIVATION_MAX = 127
MAGIC = b"BGQ8"

#: `gn_gemm_int8_relu_pc`'s own accumulator buffer is `int32_t[256]`
#: (`src/gn_gemm_int8.c`) -- a hard kernel limit, not a tuning knob. Refused
#: here rather than silently chunked: a decision with over 256 candidate
#: plays does not happen in this game, and a caller that ever saw one would
#: want to know, not have it quietly split into two calls.
MAX_BATCH = 256

_LIB.gn_gemm_int8_relu_pc.argtypes = [
    ctypes.POINTER(ctypes.c_int8),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int32),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int32),
    ctypes.POINTER(ctypes.c_uint8),
]
_LIB.gn_gemm_int8_relu_pc.restype = ctypes.c_int


@dataclass
class _Layer:
    rows: int
    cols: int
    weights: ctypes.Array  # c_int8[rows*cols], marshaled once
    bias: ctypes.Array  # c_int32[rows]
    shifts: ctypes.Array  # c_int32[rows]
    out: ctypes.Array = field(init=False)  # c_uint8[rows], reused every call

    def __post_init__(self):
        self.out = (ctypes.c_uint8 * self.rows)()


@dataclass
class Int8Network:
    input_size: int
    input_scale: float
    hidden_sizes: list[int]
    output_scales: list[float]
    layers: list[_Layer]
    head_weight: np.ndarray  # 5 x hidden_sizes[-1]
    head_bias: np.ndarray  # 5

    @classmethod
    def load(cls, path: str | Path) -> "Int8Network":
        data = Path(path).read_bytes()
        offset = 0

        def read(fmt: str):
            nonlocal offset
            size = struct.calcsize(fmt)
            values = struct.unpack_from(fmt, data, offset)
            offset += size
            return values

        (magic,) = read("<4s")
        if magic != MAGIC:
            raise ValueError(f"{path} : magic {magic!r} inattendu, {MAGIC!r} requis")
        (num_hidden,) = read("<i")
        (input_size,) = read("<i")
        (input_scale,) = read("<f")
        hidden_sizes = list(read(f"<{num_hidden}i"))
        output_scales = list(read(f"<{num_hidden}f"))

        layers = []
        cols = input_size
        for rows in hidden_sizes:
            weights = (ctypes.c_int8 * (rows * cols)).from_buffer_copy(
                data, offset)
            offset += rows * cols
            bias = (ctypes.c_int32 * rows).from_buffer_copy(data, offset)
            offset += rows * 4
            shifts = (ctypes.c_int32 * rows).from_buffer_copy(data, offset)
            offset += rows * 4
            layers.append(_Layer(rows, cols, weights, bias, shifts))
            cols = rows

        head_weight = np.frombuffer(
            data, dtype="<f4", count=5 * cols, offset=offset).reshape(5, cols).copy()
        offset += 5 * cols * 4
        head_bias = np.frombuffer(
            data, dtype="<f4", count=5, offset=offset).copy()
        offset += 5 * 4

        if offset != len(data):
            raise ValueError(
                f"{path} : {len(data) - offset} octets de trop après la lecture "
                f"attendue — le format ou la forme du réseau a divergé")

        return cls(input_size, input_scale, hidden_sizes, output_scales,
                   layers, head_weight, head_bias)

    def quantize_input(self, features) -> ctypes.Array:
        """Les 196 caractéristiques flottantes, sur la grille 0..127 de la
        couche 0 — le même arrondi-et-écrêtage que `ClippedReLU`, en Python
        parce qu'il n'y a pas encore de couche C avant la première."""
        buffer = (ctypes.c_uint8 * self.input_size)()
        for i, x in enumerate(features):
            buffer[i] = max(0, min(ACTIVATION_MAX, round(x / self.input_scale)))
        return buffer

    def forward(self, features) -> list[float]:
        """Une position, cinq probabilités — par le VRAI noyau int8, une
        couche à la fois, batch=1."""
        if len(features) != self.input_size:
            raise ValueError(
                f"{len(features)} caractéristiques, {self.input_size} attendues")

        activations = self.quantize_input(features)
        for layer in self.layers:
            status = _LIB.gn_gemm_int8_relu_pc(
                layer.weights, layer.rows, layer.cols, layer.bias,
                activations, 1, layer.shifts, layer.out)
            if status != 0:
                raise ValueError("gn_gemm_int8_relu_pc a refusé cette couche")
            activations = layer.out

        last_scale = self.output_scales[-1]
        dequantized = np.frombuffer(activations, dtype=np.uint8).astype(
            np.float64) * last_scale
        totals = self.head_bias + self.head_weight @ dequantized
        return list(1.0 / (1.0 + np.exp(-totals)))

    def forward_batch(self, features_batch) -> list[list[float]]:
        """N positions, N×5 probabilités, EN UN SEUL aller-retour C par
        couche — pas une boucle sur `forward`.

        La raison d'être de cette méthode est chiffrée, pas supposée :
        `docs/mesures/2026-08-31-T73-int8-debit-taille.md` mesure `forward`
        (une position à la fois, batch=1) à ×0,22 de float32 — le noyau
        déterministe PERD sans lot (`bench_gemm_int8.c` : ×0,79 au lot 1,
        contre ×2,13 au lot 32, le point que DS-09 a franchi). Cette méthode
        est ce qui permet à un appelant d'atteindre CE point-là.
        """
        batch = len(features_batch)
        if batch == 0:
            return []
        if batch > MAX_BATCH:
            raise ValueError(
                f"{batch} positions, au-delà du lot maximal du noyau ({MAX_BATCH})")
        for features in features_batch:
            if len(features) != self.input_size:
                raise ValueError(
                    f"{len(features)} caractéristiques, {self.input_size} attendues")

        # Feature-major, comme le noyau l'exige : input[j*batch + n].
        activations = (ctypes.c_uint8 * (self.input_size * batch))()
        for n, features in enumerate(features_batch):
            for j, x in enumerate(features):
                activations[j * batch + n] = max(
                    0, min(ACTIVATION_MAX, round(x / self.input_scale)))

        for layer in self.layers:
            out = (ctypes.c_uint8 * (layer.rows * batch))()
            status = _LIB.gn_gemm_int8_relu_pc(
                layer.weights, layer.rows, layer.cols, layer.bias,
                activations, batch, layer.shifts, out)
            if status != 0:
                raise ValueError("gn_gemm_int8_relu_pc a refusé cette couche")
            activations = out

        last_scale = self.output_scales[-1]
        width = self.hidden_sizes[-1]
        dequantized = np.frombuffer(activations, dtype=np.uint8).astype(
            np.float64).reshape(width, batch) * last_scale
        totals = self.head_bias[:, None] + self.head_weight @ dequantized  # (5, batch)
        probs = 1.0 / (1.0 + np.exp(-totals))
        return [probs[:, n].tolist() for n in range(batch)]

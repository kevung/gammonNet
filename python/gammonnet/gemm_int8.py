"""T73 — le noyau int8 déterministe, vu de Python.

Sert deux usages : les tests de non-régression (le chemin dispatché contre la
référence scalaire, bit pour bit) et le micro-banc des sept plateformes. Les
tableaux passent en `bytes`/`array`, sans copie inutile — le banc mesure le
noyau, pas la glu.
"""

from __future__ import annotations

import ctypes

from .rules import _LIB

_LIB.gn_gemm_int8_headroom.argtypes = [ctypes.c_int]
_LIB.gn_gemm_int8_headroom.restype = ctypes.c_double

_LIB.gn_gemm_int8_path.argtypes = []
_LIB.gn_gemm_int8_path.restype = ctypes.c_char_p

_RAW_ARGS = [
    ctypes.POINTER(ctypes.c_int8),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int32),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int32),
]
_LIB.gn_gemm_int8_raw.argtypes = _RAW_ARGS
_LIB.gn_gemm_int8_raw.restype = ctypes.c_int
_LIB.gn_gemm_int8_raw_reference.argtypes = _RAW_ARGS
_LIB.gn_gemm_int8_raw_reference.restype = ctypes.c_int

_LIB.gn_gemm_int8_relu.argtypes = [
    ctypes.POINTER(ctypes.c_int8),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int32),
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_uint8),
]
_LIB.gn_gemm_int8_relu.restype = ctypes.c_int

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

#: Le plafond de la ClippedReLU, répété du C. Les activations tiennent dans
#: 0..127 pour qu'un poids int8 les multiplie sans étape d'élargissement.
ACTIVATION_MAX = 127


def headroom(cols: int) -> float:
    """La marge int32 d'une couche de `cols` entrées, en facteur.

    Au-dessus de 1, aucun ordre de sommation ne peut déborder — la condition
    exacte dont dépend la garantie bit-à-bit.
    """
    return float(_LIB.gn_gemm_int8_headroom(cols))


def path() -> str:
    """Le chemin réellement compilé : scalar, simd128, sse2 ou avx2."""
    return _LIB.gn_gemm_int8_path().decode("ascii")


def _weights(values) -> ctypes.Array:
    return (ctypes.c_int8 * len(values))(*values)


def _bias(values) -> ctypes.Array | None:
    return (ctypes.c_int32 * len(values))(*values) if values is not None else None


def _input(values) -> ctypes.Array:
    return (ctypes.c_uint8 * len(values))(*values)


def raw(weights, rows: int, cols: int, bias, activations, batch: int,
        reference: bool = False) -> list[int]:
    """Les accumulateurs int32 bruts, `rows` × `batch`, feature-major.

    `reference=True` force la référence scalaire — c'est contre elle que le
    chemin dispatché est comparé, et un écart entre les deux invaliderait la
    garantie du fichier d'en-tête.
    """
    out = (ctypes.c_int32 * (rows * batch))()
    call = _LIB.gn_gemm_int8_raw_reference if reference else _LIB.gn_gemm_int8_raw
    if call(_weights(weights), rows, cols, _bias(bias), _input(activations),
            batch, out) != 0:
        raise ValueError("gn_gemm_int8_raw a refusé ces arguments")
    return list(out)


def relu(weights, rows: int, cols: int, bias, activations, batch: int,
         shift: int) -> list[int]:
    """Une couche complète : accumulation, décalage, ClippedReLU 0..127."""
    out = (ctypes.c_uint8 * (rows * batch))()
    if _LIB.gn_gemm_int8_relu(_weights(weights), rows, cols, _bias(bias),
                              _input(activations), batch, shift, out) != 0:
        raise ValueError("gn_gemm_int8_relu a refusé ces arguments")
    return list(out)


def relu_pc(weights, rows: int, cols: int, bias, activations, batch: int,
            shifts, out=None) -> list[int]:
    """Comme `relu`, mais UN DÉCALAGE PAR RANGÉE — ce que la QAT entraîne
    réellement (`QuantizedLinear.quantized_weight`, une échelle par canal de
    sortie). `shifts` a `rows` éléments."""
    buffer = out if out is not None else (ctypes.c_uint8 * (rows * batch))()
    if _LIB.gn_gemm_int8_relu_pc(
            _weights(weights), rows, cols, _bias(bias), _input(activations),
            batch, (ctypes.c_int32 * len(shifts))(*shifts), buffer) != 0:
        raise ValueError("gn_gemm_int8_relu_pc a refusé ces arguments")
    return list(buffer)

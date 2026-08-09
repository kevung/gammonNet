"""ctypes binding for `src/gn_infer.h` — the network's five probabilities.

The C library is the authority; nothing is reimplemented here. The measurement
side of the project drives exactly the code the inference library runs, which
is the only way a measurement says anything about what ships.

**The distribution is the output.** `Evaluation` carries five probabilities and
offers `money_equity` as a derived convenience. That ordering is deliberate and
it is the point of T10: a scalar equity has already discarded what the match
equity table needs. See the derivation in `src/gn_infer.h`.
"""

from __future__ import annotations

import ctypes
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .codec import NUM_FEATURES, _FeatureArray
from .rules import _LIB, Position, _CPosition

NUM_OUTPUTS = 5
NUM_EXCLUSIVE = 6

_ProbArray = ctypes.c_float * NUM_OUTPUTS
_ExclusiveArray = ctypes.c_double * NUM_EXCLUSIVE


def _f32(x: float) -> float:
    """Arrondi à la précision du moteur.

    Le réseau, `nn_eval.c` et le `.bin` sont en float32 de bout en bout. Une
    vérification menée en float64 examinerait un calcul qui n'a jamais eu lieu.
    """
    return struct.unpack("<f", struct.pack("<f", x))[0]

_LIB.gn_network_load.argtypes = [ctypes.c_char_p]
_LIB.gn_network_load.restype = ctypes.c_void_p

_LIB.gn_network_free.argtypes = [ctypes.c_void_p]
_LIB.gn_network_free.restype = None

_LIB.gn_network_input_size.argtypes = [ctypes.c_void_p]
_LIB.gn_network_input_size.restype = ctypes.c_int

_LIB.gn_evaluate.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(ctypes.c_float),
]
_LIB.gn_evaluate.restype = ctypes.c_int

_LIB.gn_evaluate_features.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_float),
]
_LIB.gn_evaluate_features.restype = ctypes.c_int

_LIB.gn_evaluate_batch.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.POINTER(_CPosition)),
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_float),
]
_LIB.gn_evaluate_batch.restype = ctypes.c_int

_LIB.gn_money_equity.argtypes = [ctypes.POINTER(ctypes.c_float)]
_LIB.gn_money_equity.restype = ctypes.c_float

_LIB.gn_probs_are_nested.argtypes = [ctypes.POINTER(ctypes.c_float)]
_LIB.gn_probs_are_nested.restype = ctypes.c_int

_LIB.gn_probs_exclusive.argtypes = [
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(ctypes.c_double),
]
_LIB.gn_probs_exclusive.restype = None


@dataclass(frozen=True)
class Evaluation:
    """Five nested probabilities, from the on-roll player's point of view.

    Nested, not exclusive: `win_gammon` counts backgammons, and `win` counts
    both. `P(win single only)` is `win - win_gammon`.
    """

    win: float
    win_gammon: float
    win_backgammon: float
    lose_gammon: float
    lose_backgammon: float

    def as_tuple(self) -> tuple[float, float, float, float, float]:
        return (
            self.win,
            self.win_gammon,
            self.win_backgammon,
            self.lose_gammon,
            self.lose_backgammon,
        )

    @property
    def lose(self) -> float:
        return 1.0 - self.win

    @property
    def money_equity(self) -> float:
        """Cubeless money equity, in points.

        A projection of the distribution: it loses what match play needs. Fine
        for money, fine for comparing against an engine that prints it, wrong
        as an input to a match equity table.
        """
        return (
            2.0 * self.win
            + self.win_gammon
            + self.win_backgammon
            - self.lose_gammon
            - self.lose_backgammon
            - 1.0
        )

    @property
    def is_nested(self) -> bool:
        """Les inégalités d'imbrication, **dans l'arithmétique du moteur**.

        En float32 — celle du réseau et de `nn_eval.c`. Les vérifier en float64
        donnerait un faux positif d'échec : quand `P(gain)` vaut 1,5e-10,
        `1.0f - P(gain)` vaut exactement `1.0f` en float32, si bien qu'un
        `P(perte-gammon)` de 1,0 satisfait l'inégalité sans écrêtage — et c'est
        correct. La marge que le float64 fait réapparaître n'existe pas dans le
        calcul qui a produit ces nombres. Pour un consommateur qui dénesterait
        en double, c'est `exclusive` qui règle le problème, pas ce test.
        """
        one = _f32(1.0)
        return (
            _f32(self.win_gammon) <= _f32(self.win)
            and _f32(self.win_backgammon) <= _f32(self.win_gammon)
            and _f32(self.lose_gammon) <= _f32(one - _f32(self.win))
            and _f32(self.lose_backgammon) <= _f32(self.lose_gammon)
        )

    @property
    def exclusive(self) -> "Outcomes":
        """Les six issues mutuellement exclusives, jamais négatives.

        La décomposition dont T32 et T34 auront besoin. Elle est calculée en C,
        en double et plancher à zéro — voir la note de `src/gn_infer.h`, qui
        explique pourquoi la soustraction naïve produit une probabilité
        négative sur des positions réelles.
        """
        buffer = _ProbArray(*self.as_tuple())
        out = _ExclusiveArray()
        _LIB.gn_probs_exclusive(buffer, out)
        return Outcomes(*out)


@dataclass(frozen=True)
class Outcomes:
    """Les six issues mutuellement exclusives d'une partie. Somme = 1."""

    win_single: float
    win_gammon: float
    win_backgammon: float
    lose_single: float
    lose_gammon: float
    lose_backgammon: float

    def as_tuple(self) -> tuple[float, ...]:
        return (
            self.win_single,
            self.win_gammon,
            self.win_backgammon,
            self.lose_single,
            self.lose_gammon,
            self.lose_backgammon,
        )

    @property
    def total(self) -> float:
        return sum(self.as_tuple())

    @property
    def money_equity(self) -> float:
        """L'équité money, recomposée depuis les issues exclusives.

        Chemin indépendant de `Evaluation.money_equity` : celui-ci part des
        probabilités imbriquées, celui-là des exclusives. Les deux doivent
        coïncider, ce qui en fait un contrôle croisé plutôt qu'une redite.
        """
        return (
            1.0 * self.win_single
            + 2.0 * self.win_gammon
            + 3.0 * self.win_backgammon
            - 1.0 * self.lose_single
            - 2.0 * self.lose_gammon
            - 3.0 * self.lose_backgammon
        )


class Network:
    """A loaded network. Refuses what it cannot evaluate.

    A model that is not prob5, or that expects a different number of inputs, is
    rejected at load time rather than run on a vector it has never seen. See
    `CLAUDE.md`, rule 2.
    """

    def __init__(self, handle: int, path: Path):
        self._handle = handle
        self.path = path

    @classmethod
    def load(cls, path: str | Path) -> "Network":
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"{path} absent — lancer `make model`")
        handle = _LIB.gn_network_load(str(path).encode())
        if not handle:
            raise ValueError(
                f"{path} refusé : fichier illisible, ou modèle que ce build ne "
                f"sait pas évaluer (mode de sortie autre que prob5, ou taille "
                f"d'entrée différente de {NUM_FEATURES})"
            )
        return cls(handle, path)

    def close(self) -> None:
        if self._handle:
            _LIB.gn_network_free(self._handle)
            self._handle = None

    def __enter__(self) -> "Network":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    @property
    def input_size(self) -> int:
        return _LIB.gn_network_input_size(self._handle)

    def evaluate(self, position: Position) -> Evaluation:
        """Evaluate a position. Raises if the position is not valid."""
        probs = _ProbArray()
        if _LIB.gn_evaluate(self._handle, ctypes.byref(position._to_c()), probs) != 0:
            raise ValueError("position refusée par l'évaluateur (structurellement invalide)")
        return Evaluation(*probs)

    def evaluate_features(self, features: Sequence[float]) -> Evaluation:
        """Evaluate an already-encoded feature vector."""
        if len(features) != NUM_FEATURES:
            raise ValueError(f"{len(features)} caractéristiques, {NUM_FEATURES} attendues")
        probs = _ProbArray()
        buffer = _FeatureArray(*features)
        if _LIB.gn_evaluate_features(self._handle, buffer, probs) != 0:
            raise ValueError("vecteur refusé par l'évaluateur")
        return Evaluation(*probs)

    def evaluate_batch(self, positions: Sequence[Position]) -> list[Evaluation]:
        """Le chemin de lot de la recherche (T35), exposé pour ce qui doit le
        VOIR : les tests d'identité, et l'empreinte de build du journal de
        campagne. Pour évaluer une position, `evaluate` suffit."""
        count = len(positions)
        if count == 0:
            return []
        boards = [position._to_c() for position in positions]
        pointers = (ctypes.POINTER(_CPosition) * count)(
            *(ctypes.pointer(board) for board in boards))
        out = (ctypes.c_float * (NUM_OUTPUTS * count))()
        if _LIB.gn_evaluate_batch(self._handle, pointers, count, out) != 0:
            raise ValueError("lot refusé par l'évaluateur")
        return [Evaluation(*out[i * NUM_OUTPUTS:(i + 1) * NUM_OUTPUTS])
                for i in range(count)]

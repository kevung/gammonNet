"""ctypes binding for `src/gn_met.h` — équité de match.

Le C fait autorité. Le réseau est *cubeless* et aveugle au score : il sort cinq
probabilités, et c'est **ici** que le score et le videau entrent. Voir
`BRIEF.md` §6.

**Ce module est la raison d'être de `Evaluation`.** Un scalaire d'équité money a
déjà perdu ce dont une équité de match a besoin : à 2-away/4-away un gammon
gagne souvent le match, alors qu'en money il vaut deux points comme un autre.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from .infer import NUM_OUTPUTS, Evaluation, _ProbArray
from .rules import _LIB

MAX_AWAY = 25


class _CMatchState(ctypes.Structure):
    _fields_ = [
        ("away_on_roll", ctypes.c_int),
        ("away_opponent", ctypes.c_int),
        ("cube", ctypes.c_int),
        ("crawford", ctypes.c_int),
    ]


_LIB.gn_met_pre.argtypes = [ctypes.c_int, ctypes.c_int]
_LIB.gn_met_pre.restype = ctypes.c_double

_LIB.gn_met_post.argtypes = [ctypes.c_int]
_LIB.gn_met_post.restype = ctypes.c_double

_LIB.gn_match_state_is_valid.argtypes = [ctypes.POINTER(_CMatchState)]
_LIB.gn_match_state_is_valid.restype = ctypes.c_int

_LIB.gn_met_after.argtypes = [ctypes.POINTER(_CMatchState), ctypes.c_int, ctypes.c_int]
_LIB.gn_met_after.restype = ctypes.c_double

for _name in ("gn_match_winning_chance", "gn_match_equity"):
    _fn = getattr(_LIB, _name)
    _fn.argtypes = [ctypes.POINTER(_CMatchState), ctypes.POINTER(ctypes.c_float)]
    _fn.restype = ctypes.c_double


@dataclass(frozen=True)
class MatchState:
    """L'état du match, du point de vue du joueur au trait.

    `away` = les points qu'il reste à marquer. 1 signifie « à la balle de
    match ». Un joueur à 0 a déjà gagné, et il n'y a plus rien à évaluer.
    """

    away_on_roll: int
    away_opponent: int
    cube: int = 1
    crawford: bool = False

    def _to_c(self) -> _CMatchState:
        return _CMatchState(
            self.away_on_roll, self.away_opponent, self.cube, int(self.crawford)
        )

    @property
    def is_valid(self) -> bool:
        return bool(_LIB.gn_match_state_is_valid(ctypes.byref(self._to_c())))

    def after(self, points: int, on_roll_wins: bool) -> float:
        """MWC du joueur au trait si la partie rapporte `points` à un camp."""
        value = _LIB.gn_met_after(
            ctypes.byref(self._to_c()), points, int(on_roll_wins)
        )
        if value < 0.0:
            raise ValueError(f"état de match non évaluable : {self}")
        return value

    def winning_chance(self, evaluation: Evaluation) -> float:
        """La conversion : cinq probabilités → chance de gagner le match."""
        buffer = _ProbArray(*evaluation.as_tuple())
        value = _LIB.gn_match_winning_chance(ctypes.byref(self._to_c()), buffer)
        if value < 0.0:
            raise ValueError(f"état de match non évaluable : {self}")
        return value

    def equity(self, evaluation: Evaluation) -> float:
        """`2 × MWC − 1` — l'échelle « équivalent money » que les moteurs affichent."""
        return 2.0 * self.winning_chance(evaluation) - 1.0


def pre_crawford(away_a: int, away_b: int) -> float:
    """MWC du joueur à `away_a` contre un adversaire à `away_b`."""
    value = _LIB.gn_met_pre(away_a, away_b)
    if value < 0.0:
        raise ValueError(f"hors table : {away_a}-away contre {away_b}-away")
    return value


def post_crawford(away_trailer: int) -> float:
    """MWC du **poursuivant**, le meneur étant à 1-away."""
    value = _LIB.gn_met_post(away_trailer)
    if value < 0.0:
        raise ValueError(f"hors table : poursuivant à {away_trailer}-away")
    return value

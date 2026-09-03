"""ctypes binding for `src/gn_cube.h` — le modèle de videau (T34).

Le C fait autorité : ce module ne recalcule rien, il empaquette des `double` et
lit ce que `gn_cube.c` répond. Voir `docs/specs/t34-videau-spec.md` pour le
modèle lui-même — Janowski, dérivé et vérifié là, pas ici.

**Ce que ce module ajoute par rapport au C** : `CubeInputs.from_evaluation`
part d'une `Evaluation` (les cinq probabilités imbriquées du réseau) plutôt que
d'un tableau `float` brut, à la façon de `MatchState.winning_chance` dans
`met.py`.
"""

from __future__ import annotations

import ctypes
import enum
from dataclasses import dataclass
from typing import Sequence

from .infer import Evaluation, _ProbArray
from .met import MatchState, _CMatchState
from .rules import _LIB


class CubeOwner(enum.IntEnum):
    """Qui peut tourner le videau — miroir de `GnCubeOwner`."""

    CENTRED = 0
    OWNED = 1
    OPPONENT = 2


class CubeAction(enum.IntEnum):
    """Le verdict — miroir de `GnCubeAction`."""

    NO_DOUBLE = 0
    DOUBLE_TAKE = 1
    DOUBLE_PASS = 2
    TOO_GOOD = 3


class _CCubeInputs(ctypes.Structure):
    _fields_ = [
        ("win", ctypes.c_double),
        ("win_points", ctypes.c_double),
        ("lose_points", ctypes.c_double),
    ]


class _CCubeDecision(ctypes.Structure):
    _fields_ = [
        ("action", ctypes.c_int),
        ("equity_no_double", ctypes.c_double),
        ("equity_double", ctypes.c_double),
        ("take_point", ctypes.c_double),
    ]


_LIB.gn_cube_inputs.argtypes = [
    ctypes.POINTER(ctypes.c_float),
    ctypes.POINTER(_CCubeInputs),
]
_LIB.gn_cube_inputs.restype = ctypes.c_int

_LIB.gn_cube_take_point.argtypes = [
    ctypes.POINTER(_CCubeInputs),
    ctypes.c_int,
    ctypes.c_double,
]
_LIB.gn_cube_take_point.restype = ctypes.c_double

_LIB.gn_cube_equity.argtypes = [
    ctypes.POINTER(_CCubeInputs),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_double,
]
_LIB.gn_cube_equity.restype = ctypes.c_double

_LIB.gn_cube_decide.argtypes = [
    ctypes.POINTER(ctypes.c_float),
    ctypes.c_int,
    ctypes.POINTER(_CMatchState),
    ctypes.c_double,
    ctypes.c_int,
    ctypes.POINTER(_CCubeDecision),
]
_LIB.gn_cube_decide.restype = ctypes.c_int

_LIB.gn_cube_value.argtypes = [
    ctypes.POINTER(ctypes.c_float),
    ctypes.c_int,
    ctypes.POINTER(_CMatchState),
    ctypes.c_double,
    ctypes.POINTER(ctypes.c_int),
]
_LIB.gn_cube_value.restype = ctypes.c_double


@dataclass(frozen=True)
class CubeInputs:
    """`p`, `W`, `L` de `docs/specs/t34-videau-spec.md` §1 — la seule chose
    dont le modèle de videau a besoin, et rien de plus.

    `win` : P(gain), toute marge. `win_points` : E[points | gain]. `lose_points`
    : E[points | perte]. Les deux derniers valent 1 dans les cas dégénérés
    (`win` exactement 0 ou 1) — voir `gn_cube_inputs` en C pour pourquoi ce
    n'est pas NaN.
    """

    win: float
    win_points: float
    lose_points: float

    def _to_c(self) -> _CCubeInputs:
        return _CCubeInputs(self.win, self.win_points, self.lose_points)

    @classmethod
    def from_evaluation(cls, evaluation: Evaluation) -> "CubeInputs":
        """Construit les entrées du videau depuis les cinq probabilités du réseau.

        Passe exclusivement par `gn_probs_exclusive`, côté C — jamais par une
        soustraction refaite ici. Voir `gn_infer.h` pour le piège que ça évite.
        """
        buffer = _ProbArray(*evaluation.as_tuple())
        out = _CCubeInputs()
        if _LIB.gn_cube_inputs(buffer, ctypes.byref(out)) != 0:
            raise ValueError("distribution refusée par gn_cube_inputs")
        return cls(out.win, out.win_points, out.lose_points)

    def take_point(self, owner: CubeOwner, efficiency: float) -> float:
        """`TP(x)` si le videau pourrait m'être doublé (`CENTRED`/`OPPONENT`),
        `CP(x)` si je le possède (`OWNED`) — voir `gn_cube_take_point` en C
        pour pourquoi ce choix dépend de `owner`."""
        value = _LIB.gn_cube_take_point(
            ctypes.byref(self._to_c()), int(owner), efficiency
        )
        if value < 0.0:
            raise ValueError(f"point de prise non calculable pour {self}")
        return value

    def equity(self, owner: CubeOwner, cube: int, efficiency: float) -> float:
        """Équité cubeful money, en points, du point de vue du joueur au trait."""
        return _LIB.gn_cube_equity(
            ctypes.byref(self._to_c()), int(owner), cube, efficiency
        )


@dataclass(frozen=True)
class CubeDecision:
    """Le verdict, et les équités des branches qui l'expliquent.

    `docs/specs/t34-videau-spec.md` §4 est explicite : une décision juste de
    0,001 et une juste de 0,5 ne sont pas la même décision, donc les équités
    voyagent toujours avec le verdict, jamais lui seul.
    """

    action: CubeAction
    equity_no_double: float
    equity_double: float
    take_point: float


def decide(
    evaluation: Evaluation,
    owner: CubeOwner,
    efficiency: float,
    state: MatchState | None = None,
    jacoby: bool = True,
) -> CubeDecision:
    """La décision de videau, money ou match selon `state`.

    `jacoby` : actif par défaut en money (`state is None`), comme le prévoit
    `docs/specs/t34-videau-spec.md` §4 — « Défaut : actif en money, sans objet
    en match ». Sans effet quand `state` est fourni : la table d'équité de
    match prend déjà les gammons en compte au score, ce que Jacoby ne fait
    qu'approcher en money.
    """
    buffer = _ProbArray(*evaluation.as_tuple())
    c_state = ctypes.byref(state._to_c()) if state is not None else None
    out = _CCubeDecision()

    result = _LIB.gn_cube_decide(
        buffer, int(owner), c_state, efficiency, int(jacoby), ctypes.byref(out)
    )
    if result != 0:
        raise ValueError(f"décision refusée : état de match non évaluable ({state})")

    return CubeDecision(
        action=CubeAction(out.action),
        equity_no_double=out.equity_no_double,
        equity_double=out.equity_double,
        take_point=out.take_point,
    )


def value(
    evaluation: Evaluation,
    owner: CubeOwner,
    efficiency: float,
    state: MatchState | None = None,
) -> float:
    """La valeur cubeful d'une distribution, sur l'échelle à négation de la
    recherche — la valuation de feuille de `docs/specs/t34-videau-spec.md` §8.

    Money (`state is None`) : points par unité de videau, §3. Match : équité
    `2·MWC − 1` par la récursion §9, au videau de `state`. Voir `gn_cube_value`
    en C pour l'antisymétrie qui rend ces valeurs propagables par
    l'expectiminimax — et `tests/test_search_cube.py`, qui la vérifie au lieu
    de la croire.
    """
    buffer = _ProbArray(*evaluation.as_tuple())
    c_state = ctypes.byref(state._to_c()) if state is not None else None
    failed = ctypes.c_int(0)
    result = _LIB.gn_cube_value(
        buffer, int(owner), c_state, efficiency, ctypes.byref(failed)
    )
    if failed.value:
        raise ValueError(f"valeur cubeful refusée ({state})")
    return result


_LIB.gn_cube_value_batch.argtypes = [
    ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(_CMatchState),
    ctypes.c_double,
    ctypes.POINTER(ctypes.c_double),
]
_LIB.gn_cube_value_batch.restype = ctypes.c_int


def value_batch(
    evaluations: Sequence[Evaluation],
    owner: CubeOwner,
    efficiency: float,
    state: MatchState | None = None,
) -> list[float]:
    """Les mêmes valeurs, pour plusieurs distributions qui partagent un état de
    videau — `gn_cube_value_batch`, la forme par lot de T85.

    Elle existe parce que les soixante bissections d'un candidat sont une chaîne
    de dépendances sérielle, et que celles de deux candidats sont indépendantes :
    les faire en pas cadencé remplit la latence de l'une avec le travail de
    l'autre. **Le résultat est celui du scalaire au bit près**, et
    `tests/test_cube_batch.py` le tient plutôt que de l'affirmer.
    """
    count = len(evaluations)
    if count == 0:
        return []
    buffers = [_ProbArray(*e.as_tuple()) for e in evaluations]
    pointers = (ctypes.POINTER(ctypes.c_float) * count)(
        *[ctypes.cast(b, ctypes.POINTER(ctypes.c_float)) for b in buffers]
    )
    out = (ctypes.c_double * count)()
    c_state = ctypes.byref(state._to_c()) if state is not None else None
    if _LIB.gn_cube_value_batch(pointers, count, int(owner), c_state,
                                efficiency, out) != 0:
        raise ValueError(f"valeur cubeful par lot refusée ({state})")
    return list(out)


_LIB.gn_cube_verdict.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double]
_LIB.gn_cube_verdict.restype = ctypes.c_int


def verdict(e_nd: float, e_dt: float, e_dp: float = 1.0) -> CubeAction:
    """La table §4 sur trois équités explicites — `gn_cube_verdict`, pas une
    réécriture.

    Pour les équités qui ne sortent pas de `decide` : la table bilatérale
    exacte, un rollout. La règle à quatre lignes vit une seule fois, en C.
    """
    return CubeAction(_LIB.gn_cube_verdict(e_nd, e_dt, e_dp))

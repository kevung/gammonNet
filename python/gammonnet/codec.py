"""ctypes binding for the codec: 196 features, Position ID, XGID.

The C library is the authority. Nothing is reimplemented here — a second
implementation in Python would be a second thing to keep in agreement with the
network, and T02 is precisely the task where a quiet disagreement is fatal.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from .rules import _LIB, BLACK, WHITE, Position, _CPosition

NUM_FEATURES = 196

SIDE_ON_ROLL = 0
SIDE_OPPONENT = 1

_POSITION_ID_LENGTH = 15
_XGID_LENGTH = 64

_FeatureArray = ctypes.c_float * NUM_FEATURES


class _CXgidFields(ctypes.Structure):
    _fields_ = [
        ("cube_power", ctypes.c_int),
        ("cube_owner", ctypes.c_int),
        ("turn", ctypes.c_int),
        ("die1", ctypes.c_int),
        ("die2", ctypes.c_int),
        ("score_upper", ctypes.c_int),
        ("score_lower", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("match_length", ctypes.c_int),
        ("max_cube", ctypes.c_int),
    ]


def _bind() -> None:
    _LIB.gn_encode.argtypes = [ctypes.POINTER(_CPosition), ctypes.POINTER(ctypes.c_float)]
    _LIB.gn_encode.restype = ctypes.c_int

    _LIB.gn_decode.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
        ctypes.POINTER(_CPosition),
    ]
    _LIB.gn_decode.restype = ctypes.c_int

    _LIB.gn_pip_count_from_features.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int]
    _LIB.gn_pip_count_from_features.restype = ctypes.c_int

    _LIB.gn_position_id.argtypes = [ctypes.POINTER(_CPosition), ctypes.c_char_p]
    _LIB.gn_position_id.restype = ctypes.c_int

    _LIB.gn_position_from_id.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.POINTER(_CPosition),
    ]
    _LIB.gn_position_from_id.restype = ctypes.c_int

    _LIB.gn_position_from_xgid.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(_CPosition),
        ctypes.POINTER(_CXgidFields),
    ]
    _LIB.gn_position_from_xgid.restype = ctypes.c_int

    _LIB.gn_xgid.argtypes = [
        ctypes.POINTER(_CPosition),
        ctypes.POINTER(_CXgidFields),
        ctypes.c_char_p,
    ]
    _LIB.gn_xgid.restype = ctypes.c_int


_bind()


@dataclass(frozen=True)
class XgidFields:
    """Everything in an XGID that is not a checker.

    gammonNet acts on none of it yet — the cube is T34, the match score is T32 —
    but it is carried through so that an identifier survives a round-trip rather
    than being silently stripped of half its meaning.
    """

    cube_power: int = 0
    cube_owner: int = 0
    turn: int = 1
    die1: int = 0
    die2: int = 0
    score_upper: int = 0
    score_lower: int = 0
    flags: int = 0
    match_length: int = 0
    max_cube: int = 10


# ── The 196 features ─────────────────────────────────────────────────


def encode(position: Position) -> list[float]:
    """The 196 network inputs for `position`, seen by the player on roll.

    Raises ValueError on an invalid position. Refused, never approximated: a
    network handed an input it has never seen returns five perfectly plausible
    probabilities and gives no sign at all.
    """
    features = _FeatureArray()
    if _LIB.gn_encode(ctypes.byref(position._to_c()), features) != 0:
        raise ValueError(f"gn_encode a refusé {position!r}")
    return list(features)


def decode(features: list[float] | _FeatureArray, turn: int) -> Position:
    """Recover a position from its features, given whose turn it is.

    The turn must be supplied: a perspective encoding is deliberately blind to
    absolute colour, which is exactly why the network needs one function and not
    two.
    """
    buffer = _FeatureArray(*features)
    c = _CPosition()
    if _LIB.gn_decode(buffer, turn, ctypes.byref(c)) != 0:
        raise ValueError("gn_decode a refusé ce vecteur de caractéristiques")
    return Position._from_c(c)


def pip_count_from_features(features: list[float] | _FeatureArray, side: int) -> int:
    """Pip count read straight out of the vector — the sentinel of `BRIEF.md` §6.

    Computed from the vector rather than from the position, so that it catches an
    encoding mistake a position-side check would happily agree with.
    """
    buffer = _FeatureArray(*features)
    result = _LIB.gn_pip_count_from_features(buffer, side)
    if result < 0:
        raise ValueError("vecteur de caractéristiques mal formé")
    return result


# ── GNU Backgammon Position ID ───────────────────────────────────────


def position_id(position: Position) -> str:
    buffer = ctypes.create_string_buffer(_POSITION_ID_LENGTH)
    if _LIB.gn_position_id(ctypes.byref(position._to_c()), buffer) != 0:
        raise ValueError(f"gn_position_id a refusé {position!r}")
    return buffer.value.decode("ascii")


def position_from_id(identifier: str, turn: int) -> Position:
    c = _CPosition()
    if _LIB.gn_position_from_id(identifier.encode("ascii"), turn, ctypes.byref(c)) != 0:
        raise ValueError(f"identifiant de position invalide : {identifier!r}")
    return Position._from_c(c)


# ── XGID ─────────────────────────────────────────────────────────────


def position_from_xgid(xgid: str) -> tuple[Position, XgidFields]:
    c = _CPosition()
    fields = _CXgidFields()
    if _LIB.gn_position_from_xgid(xgid.encode("ascii"), ctypes.byref(c), ctypes.byref(fields)) != 0:
        raise ValueError(f"XGID invalide : {xgid!r}")
    return Position._from_c(c), XgidFields(
        cube_power=fields.cube_power,
        cube_owner=fields.cube_owner,
        turn=fields.turn,
        die1=fields.die1,
        die2=fields.die2,
        score_upper=fields.score_upper,
        score_lower=fields.score_lower,
        flags=fields.flags,
        match_length=fields.match_length,
        max_cube=fields.max_cube,
    )


def xgid(position: Position, fields: XgidFields | None = None) -> str:
    buffer = ctypes.create_string_buffer(_XGID_LENGTH)
    c_fields = None
    if fields is not None:
        c_fields = ctypes.byref(_CXgidFields(*[getattr(fields, f[0]) for f in _CXgidFields._fields_]))
    if _LIB.gn_xgid(ctypes.byref(position._to_c()), c_fields, buffer) != 0:
        raise ValueError(f"gn_xgid a refusé {position!r}")
    return buffer.value.decode("ascii")

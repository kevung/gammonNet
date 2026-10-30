"""ctypes binding for `src/gn_plan.h` — une décision découpée en tâches.

Le C fait autorité : ce module ne fait que passer des octets. Un plan est un
`bytes`, une tâche un `bytes` de `TASK_BYTES` octets ; `run_task` les exécute
sur les réseaux de CE processus, `advance` recombine. Aucun état n'est gardé
entre deux appels, d'un côté comme de l'autre — c'est ce qui permet de faire
tourner les tâches ailleurs, dans n'importe quel ordre
(`docs/specs/decision-decomposee-spec.md`).
"""

from __future__ import annotations

import ctypes
import random
from dataclasses import dataclass

from .infer import NUM_OUTPUTS
from .met import _CMatchState
from .policy import Decision, _CAction, _CDecision, _handle
from .rules import _LIB, Position, _CPosition
from .search import _CCandidate, _CSearchConfig, SearchConfig

TASK_BYTES = 256
NUM_ROLLS = 21

KIND_MOVE, KIND_CUBE, KIND_POLICY, KIND_POSITION = 1, 2, 3, 4


class _CFingerprint(ctypes.Structure):
    _fields_ = [("model", ctypes.c_uint64), ("prune", ctypes.c_uint64),
                ("bearoff", ctypes.c_uint64)]


class _CPlanCube(ctypes.Structure):
    _fields_ = [("owner", ctypes.c_int), ("use_match", ctypes.c_int),
                ("state", _CMatchState), ("efficiency", ctypes.c_double),
                ("jacoby", ctypes.c_int)]


class _CPlanResult(ctypes.Structure):
    _fields_ = [("index", ctypes.c_int), ("wave_key", ctypes.c_uint64),
                ("value", ctypes.c_double),
                ("probs", ctypes.c_float * NUM_OUTPUTS),
                ("evaluations", ctypes.c_ulong)]


class _CCubeDecision(ctypes.Structure):
    _fields_ = [("action", ctypes.c_int), ("equity_no_double", ctypes.c_double),
                ("equity_double", ctypes.c_double), ("take_point", ctypes.c_double),
                # GnCubeBeaver, opaque here: room enough, never read.
                ("_beaver", ctypes.c_byte * 64)]


_BytesOut = ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))
_P = ctypes.c_void_p

_LIB.gn_plan_bytes_move.argtypes = [_P, _P, ctypes.POINTER(_CFingerprint),
                                    ctypes.POINTER(_CPosition), ctypes.c_int, ctypes.c_int,
                                    ctypes.POINTER(_CSearchConfig), _BytesOut]
_LIB.gn_plan_bytes_cube.argtypes = [_P, _P, ctypes.POINTER(_CFingerprint),
                                    ctypes.POINTER(_CPosition),
                                    ctypes.POINTER(_CSearchConfig),
                                    ctypes.POINTER(_CPlanCube), _BytesOut]
_LIB.gn_plan_bytes_position.argtypes = [_P, _P, ctypes.POINTER(_CFingerprint),
                                        ctypes.POINTER(_CPosition),
                                        ctypes.POINTER(_CSearchConfig), _BytesOut]
_LIB.gn_plan_bytes_policy.argtypes = [_P, _P, ctypes.POINTER(_CFingerprint),
                                      ctypes.c_char_p, ctypes.POINTER(_CDecision), _BytesOut]
_LIB.gn_plan_bytes_advance.argtypes = [_P, _P, ctypes.c_char_p, ctypes.c_size_t,
                                       ctypes.POINTER(_CPlanResult), ctypes.c_int, _BytesOut]
for _name in ("gn_plan_bytes_move", "gn_plan_bytes_cube", "gn_plan_bytes_position",
              "gn_plan_bytes_policy", "gn_plan_bytes_advance"):
    getattr(_LIB, _name).restype = ctypes.c_long
_LIB.gn_plan_bytes_free.argtypes = [ctypes.c_void_p]
_LIB.gn_plan_bytes_free.restype = None
_LIB.gn_plan_bytes_info.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int * 6]
_LIB.gn_plan_bytes_info.restype = ctypes.c_int
_LIB.gn_plan_bytes_tasks.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
                                     ctypes.c_int]
_LIB.gn_plan_bytes_tasks.restype = ctypes.c_int
_LIB.gn_plan_run_encoded.argtypes = [_P, _P, ctypes.POINTER(_CFingerprint),
                                     ctypes.c_char_p, ctypes.c_size_t,
                                     ctypes.POINTER(_CPlanResult)]
_LIB.gn_plan_run_encoded.restype = ctypes.c_int
_LIB.gn_plan_bytes_candidates.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                          ctypes.POINTER(_CCandidate), ctypes.c_int]
_LIB.gn_plan_bytes_candidates.restype = ctypes.c_int
_LIB.gn_plan_bytes_cube_decision.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                             ctypes.POINTER(_CCubeDecision),
                                             ctypes.c_float * NUM_OUTPUTS]
_LIB.gn_plan_bytes_cube_decision.restype = ctypes.c_int
_LIB.gn_plan_bytes_action.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                      ctypes.POINTER(_CAction)]
_LIB.gn_plan_bytes_action.restype = ctypes.c_int
_LIB.gn_plan_bytes_position_value.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                              ctypes.POINTER(ctypes.c_double),
                                              ctypes.c_float * NUM_OUTPUTS]
_LIB.gn_plan_bytes_position_value.restype = ctypes.c_int
_LIB.gn_plan_bytes_evaluations.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
_LIB.gn_plan_bytes_evaluations.restype = ctypes.c_long


@dataclass(frozen=True)
class Fingerprint:
    """Ce qu'une instance détient et dont la réponse d'une tâche dépend."""

    model: int = 1
    prune: int = 0
    bearoff: int = 0

    def _to_c(self) -> _CFingerprint:
        return _CFingerprint(self.model, self.prune, self.bearoff)


def _take(size: int, out) -> bytes:
    if size < 0:
        raise ValueError("plan refusé")
    try:
        return ctypes.string_at(out, size)
    finally:
        _LIB.gn_plan_bytes_free(out)




def plan_move(net, position: Position, d1: int, d2: int, config: SearchConfig,
              fp: Fingerprint = Fingerprint()) -> bytes:
    out = ctypes.POINTER(ctypes.c_ubyte)()
    size = _LIB.gn_plan_bytes_move(
        _handle(net), _handle(config.prune_net), ctypes.byref(fp._to_c()),
        ctypes.byref(position._to_c()), d1, d2, ctypes.byref(config._to_c()),
        ctypes.byref(out))
    return _take(size, out)


def plan_cube(net, position: Position, config: SearchConfig, *, owner: int,
              efficiency: float, jacoby: bool, match=None,
              fp: Fingerprint = Fingerprint()) -> bytes:
    cube = _CPlanCube(owner=int(owner), use_match=int(match is not None),
                      efficiency=efficiency, jacoby=int(jacoby))
    if match is not None:
        cube.state = match._to_c()
    out = ctypes.POINTER(ctypes.c_ubyte)()
    size = _LIB.gn_plan_bytes_cube(
        _handle(net), _handle(config.prune_net), ctypes.byref(fp._to_c()),
        ctypes.byref(position._to_c()), ctypes.byref(config._to_c()),
        ctypes.byref(cube), ctypes.byref(out))
    return _take(size, out)


def plan_position(net, position: Position, config: SearchConfig,
                  fp: Fingerprint = Fingerprint()) -> bytes:
    out = ctypes.POINTER(ctypes.c_ubyte)()
    size = _LIB.gn_plan_bytes_position(
        _handle(net), _handle(config.prune_net), ctypes.byref(fp._to_c()),
        ctypes.byref(position._to_c()), ctypes.byref(config._to_c()),
        ctypes.byref(out))
    return _take(size, out)


def plan_policy(net, prune_net, level: str, decision: Decision,
                fp: Fingerprint = Fingerprint()) -> bytes:
    out = ctypes.POINTER(ctypes.c_ubyte)()
    size = _LIB.gn_plan_bytes_policy(
        _handle(net), _handle(prune_net), ctypes.byref(fp._to_c()),
        level.encode("utf-8"), ctypes.byref(decision._to_c()), ctypes.byref(out))
    return _take(size, out)


@dataclass(frozen=True)
class PlanInfo:
    kind: int
    done: bool
    tasks: int
    evaluations: int
    wave: int
    policy_need: int


def info(plan: bytes) -> PlanInfo:
    values = (ctypes.c_int * 6)()
    if _LIB.gn_plan_bytes_info(plan, len(plan), values) != 0:
        raise ValueError("plan illisible")
    return PlanInfo(values[0], bool(values[1]), values[2], values[3], values[4], values[5])


def tasks(plan: bytes) -> list[bytes]:
    count = info(plan).tasks
    buffer = ctypes.create_string_buffer(max(1, count) * TASK_BYTES)
    n = _LIB.gn_plan_bytes_tasks(plan, len(plan), buffer, count)
    if n != count:
        raise ValueError("tâches illisibles")
    raw = buffer.raw
    return [raw[k * TASK_BYTES:(k + 1) * TASK_BYTES] for k in range(n)]


def run_task(net, prune_net, task: bytes, fp: Fingerprint = Fingerprint()) -> _CPlanResult:
    out = _CPlanResult()
    rc = _LIB.gn_plan_run_encoded(_handle(net), _handle(prune_net),
                                  ctypes.byref(fp._to_c()), task, len(task),
                                  ctypes.byref(out))
    if rc == -2:
        raise ValueError("tâche refusée : réseaux ou table d'une autre instance")
    if rc != 0:
        raise ValueError("tâche refusée")
    return out


def advance(net, prune_net, plan: bytes, results: list[_CPlanResult]) -> bytes:
    array = (_CPlanResult * max(1, len(results)))(*results)
    out = ctypes.POINTER(ctypes.c_ubyte)()
    size = _LIB.gn_plan_bytes_advance(_handle(net), _handle(prune_net), plan, len(plan),
                                      array, len(results), ctypes.byref(out))
    return _take(size, out)


def run_locally(net, prune_net, plan: bytes, *, rng: random.Random | None = None,
                fp: Fingerprint = Fingerprint()) -> bytes:
    """Mène le plan à son terme ici, chaque vague exécutée dans un ordre
    MÉLANGÉ si `rng` est donné — l'ordre ne doit rien changer."""
    while not info(plan).done:
        wave = tasks(plan)
        order = list(range(len(wave)))
        if rng is not None:
            rng.shuffle(order)
        results = [run_task(net, prune_net, wave[k], fp) for k in order]
        plan = advance(net, prune_net, plan, results)
    return plan


def candidates(plan: bytes, max_out: int = 3072) -> list[_CCandidate]:
    buffer = (_CCandidate * max_out)()
    n = _LIB.gn_plan_bytes_candidates(plan, len(plan), buffer, max_out)
    if n < 0:
        raise ValueError("plan non conclu")
    return [buffer[i] for i in range(n)]


def cube_decision(plan: bytes) -> tuple[_CCubeDecision, tuple[float, ...]]:
    out = _CCubeDecision()
    probs = (ctypes.c_float * NUM_OUTPUTS)()
    if _LIB.gn_plan_bytes_cube_decision(plan, len(plan), ctypes.byref(out), probs) != 0:
        raise ValueError("plan non conclu")
    return out, tuple(probs)


def action(plan: bytes) -> _CAction:
    out = _CAction()
    if _LIB.gn_plan_bytes_action(plan, len(plan), ctypes.byref(out)) != 0:
        raise ValueError("plan non conclu")
    return out


def position_value(plan: bytes) -> tuple[float, tuple[float, ...]]:
    equity = ctypes.c_double()
    probs = (ctypes.c_float * NUM_OUTPUTS)()
    if _LIB.gn_plan_bytes_position_value(plan, len(plan), ctypes.byref(equity), probs) != 0:
        raise ValueError("plan non conclu")
    return equity.value, tuple(probs)


def evaluations(plan: bytes) -> int:
    return _LIB.gn_plan_bytes_evaluations(plan, len(plan))

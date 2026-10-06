"""ctypes binding for `src/gn_policy.h` — la politique de jeu sans état.

Une décision entre, une action sort (`docs/specs/politique-spec.md`). Le C fait
autorité : rien n'est recomposé ici, et c'est tout l'objet de la fonction — la
composition (référentiel, propriétaire du videau, score vu du trait, efficacité
par état, gardes de videau mort) est écrite une fois, là où elle se mesure.

`PolicyPlayer` branche cette fonction sur la boucle cubeful de T35
(`cubeful.py`) : c'est ainsi que la mesure de la spec §9 rejoue T35 avec la
politique pour notre camp.
"""

from __future__ import annotations

import ctypes
import enum
from dataclasses import dataclass, field
from pathlib import Path

from .cube import CubeOwner
from .met import MatchState
from .rules import _LIB, Move, Play, Position, _CPlay, _CPosition
from .search import MAX_PLY, _CSearchLevel

_ROOT = Path(__file__).resolve().parent.parent.parent

MODEL = "models/cubeless_prob5_512_512_256_256.bin"
PRUNE_MODEL = "models/prune_32.bin"

#: L'horizon, en jets, de la lecture exacte de la défaite certaine (§5.5).
RESIGN_HORIZON = 2


class Pending(enum.IntEnum):
    MOVE = 0
    CUBE = 1
    TAKE = 2
    RESIGN = 3


class ActionKind(enum.IntEnum):
    MOVE = 0
    ROLL = 1
    DOUBLE = 2
    RESIGN = 3
    TAKE = 4
    PASS = 5
    ACCEPT = 6
    REJECT = 7


class _CDecision(ctypes.Structure):
    _fields_ = [
        ("position", _CPosition),
        ("pending", ctypes.c_int),
        ("d1", ctypes.c_int),
        ("d2", ctypes.c_int),
        ("cube", ctypes.c_int),
        ("cube_owner", ctypes.c_int),
        ("jacoby", ctypes.c_int),
        ("use_match", ctypes.c_int),
        ("away_on_roll", ctypes.c_int),
        ("away_opponent", ctypes.c_int),
        ("crawford", ctypes.c_int),
        ("resign_value", ctypes.c_int),
    ]


class _CAction(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_int),
        ("play", _CPlay),
        ("resign_value", ctypes.c_int),
        ("searched", ctypes.c_int),
        ("equity_a", ctypes.c_double),
        ("equity_b", ctypes.c_double),
    ]


_LIB.gn_policy_decide.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p,
    ctypes.POINTER(_CDecision), ctypes.POINTER(_CAction),
]
_LIB.gn_policy_decide.restype = ctypes.c_int
_LIB.gn_policy_decide_level.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_CSearchLevel),
    ctypes.POINTER(_CDecision), ctypes.POINTER(_CAction),
]
_LIB.gn_policy_decide_level.restype = ctypes.c_int
_LIB.gn_policy_efficiency.argtypes = [ctypes.c_int]
_LIB.gn_policy_efficiency.restype = ctypes.c_double
_LIB.gn_policy_certain_loss.argtypes = [ctypes.POINTER(_CPosition)]
_LIB.gn_policy_certain_loss.restype = ctypes.c_int


@dataclass(frozen=True)
class Decision:
    """La décision, dans le référentiel du joueur au trait (`position.turn`)."""

    position: Position
    pending: Pending
    d1: int = 0
    d2: int = 0
    cube: int = 1
    cube_owner: CubeOwner = CubeOwner.CENTRED
    jacoby: bool = False
    match: MatchState | None = None
    resign_value: int = 0

    def _to_c(self) -> _CDecision:
        c = _CDecision()
        c.position = self.position._to_c()
        c.pending = int(self.pending)
        c.d1, c.d2 = self.d1, self.d2
        c.cube = self.cube
        c.cube_owner = int(self.cube_owner)
        c.jacoby = int(self.jacoby)
        if self.match is not None:
            if self.match.cube != self.cube:
                raise ValueError("le videau du score et celui de la décision diffèrent")
            c.use_match = 1
            c.away_on_roll = self.match.away_on_roll
            c.away_opponent = self.match.away_opponent
            c.crawford = int(self.match.crawford)
        c.resign_value = self.resign_value
        return c


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    play: Play | None
    resign_value: int
    searched: bool
    equity_a: float
    equity_b: float
    #: La sortie C brute, pour qui veut la comparer octet pour octet.
    raw: bytes = field(repr=False, compare=False, default=b"")


def _handle(network) -> ctypes.c_void_p | None:
    if network is None:
        return None
    handle = getattr(network, "_handle", None)
    if not handle:
        raise ValueError("réseau non chargé")
    return ctypes.c_void_p(handle)


def _level_struct(level) -> _CSearchLevel:
    """Une forme de recherche explicite : (ply, filter, filter_extra,
    filter_threshold, prune_k) — ou un `SearchLevel`."""
    c = _CSearchLevel()
    c.name = b"custom"
    c.ply = level.ply
    for i, v in enumerate(tuple(level.filter)[: MAX_PLY + 1]):
        c.filter[i] = v
    for i, v in enumerate(tuple(getattr(level, "filter_extra", ()))[: MAX_PLY + 1]):
        c.filter_extra[i] = v
    for i, v in enumerate(tuple(getattr(level, "filter_threshold", ()))[: MAX_PLY + 1]):
        c.filter_threshold[i] = v
    c.prune_k = level.prune_k
    return c


def decide(network, prune, level, decision: Decision) -> Action:
    """`gn_policy_decide`. `level` est un nom canonique, ou une forme
    explicite (un objet portant `ply`, `filter`, … `prune_k`) pour la mesure.
    Lève `ValueError` sur un refus — jamais une action devinée."""
    c_decision = decision._to_c()
    out = _CAction()
    if isinstance(level, str):
        rc = _LIB.gn_policy_decide(_handle(network), _handle(prune),
                                   level.encode("utf-8"), ctypes.byref(c_decision),
                                   ctypes.byref(out))
    else:
        shape = _level_struct(level)
        rc = _LIB.gn_policy_decide_level(_handle(network), _handle(prune),
                                         ctypes.byref(shape), ctypes.byref(c_decision),
                                         ctypes.byref(out))
    if rc != 0:
        raise ValueError(f"décision refusée : {decision!r}")
    play = None
    kind = ActionKind(out.kind)
    if kind == ActionKind.MOVE:
        moves = tuple(Move(out.play.moves[m].from_, out.play.moves[m].to)
                      for m in range(out.play.num_moves))
        play = Play(moves=moves, result=Position._from_c(out.play.result))
    return Action(kind=kind, play=play, resign_value=out.resign_value,
                  searched=bool(out.searched), equity_a=out.equity_a,
                  equity_b=out.equity_b, raw=bytes(out))


def efficiency(owner: CubeOwner) -> float:
    return _LIB.gn_policy_efficiency(int(owner))


def certain_loss(position: Position) -> int:
    """La valeur certaine de la défaite du joueur au trait (1, 2, 3), ou 0."""
    return _LIB.gn_policy_certain_loss(ctypes.byref(position._to_c()))


@dataclass(frozen=True)
class Shape:
    """Une forme de recherche explicite — pour rejouer un réglage qui n'est pas
    un niveau canonique (celui de T35)."""

    ply: int
    filter: tuple[int, ...] = ()
    filter_extra: tuple[int, ...] = ()
    filter_threshold: tuple[float, ...] = ()
    prune_k: int = 0


def search_level_shape(name: str) -> Shape:
    """La forme d'un niveau canonique, lue dans `gn_search_level`."""
    from .search import search_level

    lv = search_level(name)
    return Shape(ply=lv.ply, filter=lv.filter, filter_extra=lv.filter_extra,
                 filter_threshold=lv.filter_threshold, prune_k=lv.prune_k)


@dataclass
class PolicyPlayer:
    """La politique, branchée sur la boucle cubeful (`cubeful.CubefulPlayer`).

    La boucle ne connaît pas l'abandon : un `RESIGN` rendu avant de lancer y
    est lu comme « pas de double », ce qui est la seule réponse cohérente d'un
    joueur qui a perdu à coup sûr. NON CHARGÉ À LA CONSTRUCTION — même règle de
    sérialisation que les autres joueurs.
    """

    level: object = "normal"
    model: str = MODEL
    prune_model: str = PRUNE_MODEL
    jacoby: bool = True
    name: str = field(default="")
    _network: object = field(default=None, repr=False, compare=False)
    _prune: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.name:
            tag = self.level if isinstance(self.level, str) else (
                f"{self.level.ply}ply-f" + "/".join(map(str, self.level.filter))
                + f"-p{self.level.prune_k}")
            self.name = f"gammonnet-policy-{tag}"

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_network"] = None
        state["_prune"] = None
        return state

    def _load(self):
        if self._network is None:
            from .infer import Network

            def path(p):
                p = Path(p)
                return p if p.is_absolute() else _ROOT / p

            self._network = Network.load(path(self.model))
            self._prune = Network.load(path(self.prune_model))
        return self._network

    def decide(self, decision: Decision) -> Action:
        return decide(self._load(), self._prune, self.level, decision)

    def choose(self, position, d1, d2, rng, match=None):
        cube = match.cube if match is not None else 1
        owner = CubeOwner.CENTRED if cube == 1 else CubeOwner.OWNED
        action = self.decide(Decision(position, Pending.MOVE, d1, d2, cube=cube,
                                      cube_owner=owner, match=match))
        return action.play if action.play.moves else None

    def wants_double(self, position, cube, owner, match=None):
        action = self.decide(Decision(position, Pending.CUBE, cube=cube,
                                      cube_owner=owner, jacoby=self.jacoby,
                                      match=match))
        return action.kind == ActionKind.DOUBLE

    def accepts_double(self, position, cube, owner, match=None):
        action = self.decide(Decision(position, Pending.TAKE, cube=cube,
                                      cube_owner=owner, jacoby=self.jacoby,
                                      match=match))
        return action.kind == ActionKind.TAKE


# ── Le corpus de référence (spec §8) ─────────────────────────────────

import struct  # noqa: E402

CORPUS_MAGIC = b"GNPL"
CORPUS_VERSION = 1
RECORD_SIZE = 160
LEVELS = ("instant", "normal", "thorough")

_HEADER = struct.Struct("<4sIII")
_INPUT = struct.Struct("<24b4BB3x12i")
_OUTPUT_HEAD = struct.Struct("<5i8b")
_POSITION = struct.Struct("<24b4BB")
_OUTPUT_TAIL = struct.Struct("<3x2d4x")
assert _INPUT.size == 80
assert _OUTPUT_HEAD.size + _POSITION.size + _OUTPUT_TAIL.size == 80


def _position_fields(position: Position) -> tuple:
    return (*position.points, *position.bar, *position.off, position.turn)


def _decision_fields(decision: Decision) -> tuple:
    c = decision._to_c()
    return (c.pending, c.d1, c.d2, c.cube, c.cube_owner, c.jacoby, c.use_match,
            c.away_on_roll, c.away_opponent, c.crawford, c.resign_value)


def pack_record(level: str, decision: Decision, action: Action | None) -> bytes:
    """Un enregistrement de 160 octets ; `action is None` pour un refus."""
    head = _INPUT.pack(*_position_fields(decision.position), LEVELS.index(level),
                       *_decision_fields(decision))
    if action is None:
        return head + struct.pack("<i", -1) + bytes(76)
    moves = [0] * 8
    result = bytes(_POSITION.size)
    num = 0
    if action.kind == ActionKind.MOVE:
        num = len(action.play.moves)
        for i, m in enumerate(action.play.moves):
            moves[2 * i], moves[2 * i + 1] = m.from_, m.to
        result = _POSITION.pack(*_position_fields(action.play.result))
    out = (_OUTPUT_HEAD.pack(0, int(action.kind), action.resign_value,
                             int(action.searched), num, *moves)
           + result + _OUTPUT_TAIL.pack(action.equity_a, action.equity_b))
    return head + out


def unpack_decision(record: bytes) -> tuple[str, Decision]:
    f = _INPUT.unpack_from(record, 0)
    position = Position(points=tuple(f[0:24]), bar=(f[24], f[25]),
                        off=(f[26], f[27]), turn=f[28])
    (level, pending, d1, d2, cube, owner, jacoby, use_match, away_on_roll,
     away_opponent, crawford, resign_value) = f[29:41]
    match = (MatchState(away_on_roll, away_opponent, cube=cube, crawford=bool(crawford))
             if use_match else None)
    decision = Decision(position, Pending(pending), d1, d2, cube=cube,
                        cube_owner=CubeOwner(owner), jacoby=bool(jacoby),
                        match=match, resign_value=resign_value)
    return LEVELS[level], decision


def write_corpus(path: Path, records: list[bytes]) -> None:
    with open(path, "wb") as out:
        out.write(_HEADER.pack(CORPUS_MAGIC, CORPUS_VERSION, len(records), RECORD_SIZE))
        for r in records:
            assert len(r) == RECORD_SIZE
            out.write(r)


def read_corpus(path: Path) -> list[bytes]:
    data = Path(path).read_bytes()
    magic, version, count, size = _HEADER.unpack_from(data, 0)
    if magic != CORPUS_MAGIC or version != CORPUS_VERSION or size != RECORD_SIZE:
        raise ValueError(f"corpus illisible : {path}")
    if len(data) != _HEADER.size + count * size:
        raise ValueError(f"corpus tronqué : {path}")
    return [data[_HEADER.size + i * size: _HEADER.size + (i + 1) * size]
            for i in range(count)]


def answer(network, prune, level: str, decision: Decision) -> bytes:
    """La réponse de la référence C, encodée comme dans le corpus."""
    try:
        action = decide(network, prune, level, decision)
    except ValueError:
        action = None
    return pack_record(level, decision, action)


#: Ce que le corpus doit couvrir (spec §8) : chaque verdict de videau en money
#: et en match, chaque réponse, chaque valeur de défaite certaine, et les
#: régimes. `tests/test_policy.py` échoue si une catégorie manque.
REQUIRED_CATEGORIES = frozenset({
    *(f"{verdict}/{mode}" for verdict in ("pas-de-double", "double-prise",
                                          "double-passe", "trop-bon")
      for mode in ("argent", "match")),
    "double-optionnel/argent", "double-optionnel/match",
    "videau-indisponible", "prise", "passe", "abandon-accepte", "abandon-refuse",
    "defaite-1", "defaite-2", "defaite-3", "coup", "coup-impossible", "coup-force",
    "argent", "match", "crawford", "jacoby", "refus",
})


def categories(record: bytes) -> set[str]:
    """Les catégories qu'un enregistrement du corpus illustre.

    Le verdict de videau se relit dans la sortie, sans rien recalculer :
    `equity_b` (doubler) vaut l'encaissement exactement sur un double/passe,
    `equity_a` (ne pas doubler) le dépasse sur un trop-bon, et les deux
    l'égalent sur un double optionnel (spec §5.2)."""
    level, d = unpack_decision(record)
    rc, kind, value, searched, num = struct.unpack_from("<5i", record, 80)
    a, b = struct.unpack_from("<2d", record, 140)
    mode = "match" if d.match is not None else "argent"
    out = {mode}
    if d.match is not None and d.match.crawford:
        out.add("crawford")
    if d.match is None and d.jacoby:
        out.add("jacoby")
    if rc == -1:
        return out | {"refus"}
    kind = ActionKind(kind)
    if d.pending == Pending.MOVE:
        out.add("coup" if searched else ("coup-impossible" if num == 0 else "coup-force"))
    elif d.pending == Pending.CUBE:
        if kind == ActionKind.RESIGN:
            out.add(f"defaite-{value}")
        elif not searched:
            out.add("videau-indisponible")
        else:
            cash = 1.0 if d.match is None else d.match.after(d.cube, True)
            if kind == ActionKind.DOUBLE:
                verdict = "double-passe" if b == cash else "double-prise"
            elif a == b == cash:
                verdict = "double-optionnel"
            elif a > cash:
                verdict = "trop-bon"
            else:
                verdict = "pas-de-double"
            out.add(f"{verdict}/{mode}")
    elif d.pending == Pending.TAKE:
        out.add("prise" if kind == ActionKind.TAKE else "passe")
    else:
        out.add("abandon-accepte" if kind == ActionKind.ACCEPT else "abandon-refuse")
    return out

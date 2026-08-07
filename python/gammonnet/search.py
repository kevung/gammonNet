"""ctypes binding for `src/gn_search.h` — expectiminimax over dice.

Le C fait autorité. Rien n'est réimplémenté ici : une seconde recherche en
Python serait une seconde chose à tenir en accord avec celle qui tourne, et les
deux se tromperaient différemment.

**Le piège de perspective**, répété ici parce qu'il ne provoque aucun plantage :
`gn_evaluate` répond du point de vue du joueur au trait, et une position
résultante a déjà rendu la main. L'équité d'un coup, pour celui qui l'a joué,
est donc l'**opposée** de ce que le réseau dit de son résultat. `Candidate.equity`
porte déjà cette négation.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from .infer import NUM_OUTPUTS, Evaluation, Network
from .met import MatchState, _CMatchState
from .rules import _LIB, Move, Play, Position, _CPlay, _CPosition

MAX_PLY = 3
NUM_ROLLS = 21

#: Les 21 jets distincts, avec leur probabilité. (1,2) et (2,1) sont le même
#: jet compté deux fois, pas deux jets.
ROLLS = tuple(
    (a, b, (1 if a == b else 2) / 36.0)
    for a in range(1, 7)
    for b in range(a, 7)
)


class _CSearchConfig(ctypes.Structure):
    _fields_ = [
        ("ply", ctypes.c_int),
        ("filter", ctypes.c_int * (MAX_PLY + 1)),
        ("use_match", ctypes.c_int),
        ("match", _CMatchState),
        ("use_cube", ctypes.c_int),
        ("cube_owner", ctypes.c_int),
        ("cube_x", ctypes.c_double),
    ]


class _CCandidate(ctypes.Structure):
    _fields_ = [
        ("play", _CPlay),
        ("probs", ctypes.c_float * NUM_OUTPUTS),
        ("equity", ctypes.c_double),
    ]


_LIB.gn_search_plays.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(_CSearchConfig),
    ctypes.POINTER(_CCandidate),
    ctypes.c_int,
]
_LIB.gn_search_plays.restype = ctypes.c_int

_LIB.gn_search_equity.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(_CSearchConfig),
]
_LIB.gn_search_equity.restype = ctypes.c_double

_LIB.gn_search_probs.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(_CSearchConfig),
    ctypes.c_float * NUM_OUTPUTS,
]
_LIB.gn_search_probs.restype = ctypes.c_int

_LIB.gn_terminal_equity.argtypes = [ctypes.POINTER(_CPosition)]
_LIB.gn_terminal_equity.restype = ctypes.c_double

_LIB.gn_search_evaluations.argtypes = []
_LIB.gn_search_evaluations.restype = ctypes.c_ulong

_LIB.gn_search_reset_evaluations.argtypes = []
_LIB.gn_search_reset_evaluations.restype = None

_MAX_CANDIDATES = 2048
_CandidateArray = _CCandidate * _MAX_CANDIDATES


@dataclass(frozen=True)
class Candidate:
    """Un coup et son équité, **du point de vue de celui qui le joue**."""

    play: Play
    equity: float
    evaluation: Evaluation | None

    @property
    def result(self) -> Position:
        return self.play.result


@dataclass(frozen=True)
class SearchConfig:
    """Profondeur, filtrage, et éventuellement le score du match.

    `filter[d]` est le nombre de candidats qui survivent à la profondeur `d` ;
    0 signifie aucun filtrage. C'est le mécanisme de T31, et ce qu'il coûte en
    qualité doit être **mesuré** — un filtre qui « ne change rien » n'a pas été
    mesuré.

    `use_match` fait valuer chaque nœud par la table d'équité de match plutôt
    qu'en money cubeless. Le score porté par `match` est celui du joueur au
    trait **à la racine** ; la recherche le bascule en descendant.

    `use_cube` (t34-videau-spec §8, étape 2) fait valuer les **feuilles** par
    le modèle de videau à l'efficacité `cube_x` — money §3, ou la récursion
    §9 si `use_match` est aussi actif. `cube_owner` est l'état du videau vu
    par le joueur au trait **à la racine** ; la recherche le met en miroir en
    descendant, comme elle bascule le score. Dans le domaine de la table
    bilatérale, les feuilles money sont **exactes** (lues, pas modélisées).
    """

    ply: int = 0
    filter: tuple[int, ...] = ()
    use_match: bool = False
    match: MatchState | None = None
    use_cube: bool = False
    cube_owner: int = 0
    cube_x: float = 0.0

    def _to_c(self) -> _CSearchConfig:
        c = _CSearchConfig()
        c.ply = self.ply
        for depth, keep in enumerate(self.filter[: MAX_PLY + 1]):
            c.filter[depth] = keep
        if self.use_match:
            if self.match is None:
                raise ValueError("use_match sans score de match")
            c.use_match = 1
            c.match = self.match._to_c()
        if self.use_cube:
            c.use_cube = 1
            c.cube_owner = int(self.cube_owner)
            c.cube_x = self.cube_x
        return c


def match_config(ply: int, state: MatchState) -> SearchConfig:
    """Une configuration valuée par la table, ou **refusée**.

    Si le score n'est pas représentable — au-delà de 25 points, un videau qui
    n'est pas une puissance de deux — la configuration rendue a `use_match`
    faux et `ply` remis à zéro. Une recherche qui serait tranquillement
    retombée en money à un score qu'elle ne sait pas représenter serait fausse
    en match, et muette.
    """
    if not state.is_valid:
        return SearchConfig(ply=0)
    return SearchConfig(ply=ply, use_match=True, match=state)


def evaluations() -> int:
    """Nombre d'évaluations réseau consommées depuis la dernière remise à zéro.

    L'unité que T21 chronomètre. Avec ce compteur, un coût par décision devient
    une mesure au lieu d'une supposition.
    """
    return _LIB.gn_search_evaluations()


def reset_evaluations() -> None:
    _LIB.gn_search_reset_evaluations()


def terminal_equity(position: Position) -> float:
    """Équité exacte d'une partie finie, du point de vue de `position.turn`.

    Toujours négative : à une position terminale, `turn` désigne le perdant.
    """
    return _LIB.gn_terminal_equity(ctypes.byref(position._to_c()))


def search_plays(
    network: Network, position: Position, d1: int, d2: int,
    config: SearchConfig | None = None,
) -> list[Candidate]:
    """Les coups légaux classés, meilleur d'abord.

    Une liste vide n'est pas une erreur : c'est une position sans coup légal, et
    le trait passe simplement.
    """
    config = config or SearchConfig()
    buffer = _CandidateArray()
    count = _LIB.gn_search_plays(
        network._handle, ctypes.byref(position._to_c()), d1, d2,
        ctypes.byref(config._to_c()), buffer, _MAX_CANDIDATES,
    )
    if count < 0:
        raise ValueError("recherche refusée")

    out: list[Candidate] = []
    for i in range(count):
        c = buffer[i]
        moves = tuple(
            Move(c.play.moves[m].from_, c.play.moves[m].to)
            for m in range(c.play.num_moves)
        )
        play = Play(moves=moves, result=Position._from_c(c.play.result))
        # Les cinq probabilités ne décrivent le coup que si la recherche s'est
        # arrêtée au réseau. Plus profond, elles sont un vestige du classement
        # peu profond — les exposer comme la sortie du coup serait faux.
        evaluation = Evaluation(*c.probs) if config.ply == 0 else None
        out.append(Candidate(play=play, equity=c.equity, evaluation=evaluation))
    return out


def best_play(
    network: Network, position: Position, d1: int, d2: int,
    config: SearchConfig | None = None,
) -> Candidate | None:
    """Le meilleur coup, ou `None` s'il n'y en a aucun de légal."""
    candidates = search_plays(network, position, d1, d2, config)
    return candidates[0] if candidates else None


def position_equity(
    network: Network, position: Position, config: SearchConfig | None = None,
) -> float:
    """Équité d'une position **avant le jet**, du point de vue de `position.turn`.

    Ce dont une décision de videau aura besoin (T34) : la valeur de la position
    avant le dé, pas après un dé particulier.
    """
    config = config or SearchConfig()
    return _LIB.gn_search_equity(
        network._handle, ctypes.byref(position._to_c()), ctypes.byref(config._to_c())
    )


def position_probs(
    network: Network, position: Position, config: SearchConfig | None = None,
) -> Evaluation:
    """La distribution d'une position **avant le jet**, à la profondeur de
    `config` — le pendant §8 de `position_equity` (t34-videau-spec).

    Au 0-ply, identique à `Network.evaluate` (mêmes trois sources : table
    exacte, cache, réseau). Plus profond, la moyenne pondérée sur les 21 jets
    de la distribution du meilleur coup — choisi par la même valuation que la
    recherche scalaire. C'est ce qu'une décision de videau à profondeur
    consomme, à la place de l'évaluation statique de la racine.
    """
    config = config or SearchConfig()
    buffer = (ctypes.c_float * NUM_OUTPUTS)()
    result = _LIB.gn_search_probs(
        network._handle, ctypes.byref(position._to_c()),
        ctypes.byref(config._to_c()), buffer,
    )
    if result != 0:
        raise ValueError("distribution non calculable pour cette position")
    return Evaluation(*buffer)

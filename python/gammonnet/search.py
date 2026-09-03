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

MAX_PLY = 4
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
        ("prune_net", ctypes.c_void_p),
        ("prune_k", ctypes.c_int),
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

NUM_ROLLS = 21
_RollProbArray = (ctypes.c_float * NUM_OUTPUTS) * NUM_ROLLS
_RollWeightArray = ctypes.c_double * NUM_ROLLS
_LIB.gn_search_probs_by_roll.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(_CSearchConfig),
    _RollProbArray,
    _RollWeightArray,
]
_LIB.gn_search_probs_by_roll.restype = ctypes.c_int

_LIB.gn_terminal_equity.argtypes = [ctypes.POINTER(_CPosition)]
_LIB.gn_terminal_equity.restype = ctypes.c_double

_LIB.gn_search_evaluations.argtypes = []
_LIB.gn_search_evaluations.restype = ctypes.c_ulong

_LIB.gn_search_reset_evaluations.argtypes = []
_LIB.gn_search_reset_evaluations.restype = None

_LIB.gn_search_prune_evaluations.argtypes = []
_LIB.gn_search_prune_evaluations.restype = ctypes.c_ulong


class _CSearchLevel(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("ply", ctypes.c_int),
        ("filter", ctypes.c_int * (MAX_PLY + 1)),
        ("prune_k", ctypes.c_int),
        ("prune_equity_loss", ctypes.c_double),
        ("prune_equity_loss_ci_low", ctypes.c_double),
        ("prune_equity_loss_ci_high", ctypes.c_double),
    ]


_LIB.gn_search_level.argtypes = [ctypes.c_char_p]
_LIB.gn_search_level.restype = ctypes.POINTER(_CSearchLevel)

_LIB.gn_search_level_count.argtypes = []
_LIB.gn_search_level_count.restype = ctypes.c_int

_LIB.gn_search_level_name.argtypes = [ctypes.c_int]
_LIB.gn_search_level_name.restype = ctypes.c_char_p

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

    `prune_net` / `prune_k` (T3A) branchent le **réseau d'élagage** : le petit
    réseau classe tous les coups légaux, et seuls les `prune_k` meilleurs sont
    montrés au grand. `prune_k = 0` ou `prune_net = None` laisse la recherche
    **exactement** comme avant, bit pour bit — le défaut, parce que ce
    mécanisme change ce que le moteur joue et doit donc être choisi, puis
    mesuré contre la recherche non élaguée.

    **Ce que la recherche rend alors** : au plus `prune_k` candidats, pas tous
    les coups légaux. Les recalés portent les probabilités du **petit** réseau,
    et cinq nombres plausibles venus du mauvais réseau sont exactement le mode
    de défaillance de la règle 2 de `CLAUDE.md` : ils ne sortent pas.
    """

    ply: int = 0
    filter: tuple[int, ...] = ()
    use_match: bool = False
    match: MatchState | None = None
    use_cube: bool = False
    cube_owner: int = 0
    cube_x: float = 0.0
    prune_net: object | None = None
    prune_k: int = 0

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
        if self.prune_net is not None and self.prune_k > 0:
            handle = getattr(self.prune_net, "_handle", None)
            if not handle:
                raise ValueError("prune_net n'est pas un Network chargé")
            c.prune_net = ctypes.c_void_p(handle)
            c.prune_k = int(self.prune_k)
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


def prune_evaluations() -> int:
    """Évaluations du **petit** réseau depuis la dernière remise à zéro.

    Compteur séparé exprès : tous les coûts publiés par ce projet sont en
    évaluations du grand réseau, et confondre deux unités distantes d'un
    facteur 92,5 les rendrait toutes incomparables.
    """
    return _LIB.gn_search_prune_evaluations()


def reset_evaluations() -> None:
    """Remet à zéro les deux compteurs, le grand réseau et l'élagage."""
    _LIB.gn_search_reset_evaluations()


@dataclass(frozen=True)
class SearchLevel:
    """Une forme canonique de recherche, nommée, coût de qualité attaché.

    Verticale 5 (issue #25) : `ply = 2`, `filter = (0,1,3)` et `prune_k = 12`
    étaient recopiés à la main jusqu'à cinq fois à travers ce dépôt, blunderDB
    et gammonGo. `gn_search_level` (`src/gn_search.c`, la table `LEVELS`) est
    désormais l'unique endroit qui les définit ; cette classe et
    `search_level()` en sont la lecture Python — rien n'est réinventé ici.

    `prune_equity_loss` et son intervalle à 95 % sont MESURÉS
    (`docs/mesures/2026-08-26-T3A-regroupement.md`), toujours 0 quand
    `prune_k == 0` : il n'y a rien à perdre.
    """

    name: str
    ply: int
    filter: tuple[int, ...]
    prune_k: int
    prune_equity_loss: float
    prune_equity_loss_ci_low: float
    prune_equity_loss_ci_high: float

    def to_config(self) -> SearchConfig:
        """La `SearchConfig` correspondante — sans réseau d'élagage : c'est à
        l'appelant de charger celui qu'il veut brancher (`SearchConfig.prune_net`)."""
        return SearchConfig(ply=self.ply, filter=self.filter)


def search_level(name: str) -> SearchLevel:
    """La forme canonique nommée (`"instant"`, `"normal"`, `"thorough"`).

    Lève `ValueError` si `name` n'est pas connu — jamais un défaut deviné ; le
    message nomme les niveaux qui existent réellement, plutôt que de forcer
    l'appelant à les retrouver dans ce fichier.
    """
    ptr = _LIB.gn_search_level(name.encode("utf-8"))
    if not ptr:
        known = ", ".join(search_level_names())
        raise ValueError(f"niveau inconnu : {name!r}. Connus : {known}")
    c = ptr.contents
    return SearchLevel(
        name=c.name.decode("utf-8"),
        ply=c.ply,
        filter=tuple(c.filter[: MAX_PLY + 1]),
        prune_k=c.prune_k,
        prune_equity_loss=c.prune_equity_loss,
        prune_equity_loss_ci_low=c.prune_equity_loss_ci_low,
        prune_equity_loss_ci_high=c.prune_equity_loss_ci_high,
    )


def search_level_names() -> tuple[str, ...]:
    """Les noms des niveaux canoniques, dans l'ordre de la table C."""
    count = _LIB.gn_search_level_count()
    return tuple(
        _LIB.gn_search_level_name(i).decode("utf-8") for i in range(count)
    )


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


def probs_by_roll(
    network: Network, position: Position, config: SearchConfig | None = None,
) -> tuple[list[Evaluation], list[float]]:
    """Les 21 distributions du backup, une par jet, et leurs poids.

    `position_probs` en est exactement la moyenne pondérée — c'est la même
    boucle, prise avant la somme. Ce que la moyenne jette est la **dispersion**
    de la position sur les jets, la grandeur que la tête auxiliaire de T71
    apprend ; la reprendre ici ne coûte rien, la redemander par 21 recherches
    séparées coûterait tout le backup une seconde fois.

    Exige `config.ply >= 1` et une position non terminée : en dessous il n'y a
    aucun jet à énumérer, et rendre des zéros serait la réponse plausible et
    fausse que ce dépôt refuse.
    """
    config = config or SearchConfig()
    if config.ply < 1:
        raise ValueError("probs_by_roll exige au moins un ply : sans jet énuméré, "
                         "il n'y a pas de dispersion à lire")
    buffer = _RollProbArray()
    weights = _RollWeightArray()
    result = _LIB.gn_search_probs_by_roll(
        network._handle, ctypes.byref(position._to_c()),
        ctypes.byref(config._to_c()), buffer, weights,
    )
    if result != 0:
        raise ValueError("dispersion non calculable pour cette position")
    return ([Evaluation(*buffer[r]) for r in range(NUM_ROLLS)],
            [weights[r] for r in range(NUM_ROLLS)])


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

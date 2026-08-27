"""Liaison ctypes vers `src/gn_rollout.h` — l'arbitre indépendant (T39).

Le C fait autorité. Rien n'est réimplémenté ici : une seconde façon de tirer les
dés serait une seconde chose à tenir en accord avec celle qui tourne, et le
mécanisme des **dés communs** ne survivrait pas à la divergence.

**La réserve voyage avec chaque résultat.** Un rollout conduit par notre réseau
nous favorise : il note l'avenir avec l'approximation même qui a choisi le coup.
Un rollout gnubg les favorise. `PLAN.md` en fait un critère de T39 — aucune
colonne n'est présentée seule.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from .infer import NUM_OUTPUTS, Network
from .met import MatchState, _CMatchState
from .rules import _LIB, Position, _CPosition
from .search import MAX_PLY, SearchConfig, _CSearchConfig


class _CRolloutConfig(ctypes.Structure):
    _fields_ = [
        ("trials", ctypes.c_ulong),
        ("truncate", ctypes.c_uint),
        ("policy", _CSearchConfig),
        ("seed", ctypes.c_ulong),
        ("use_cube", ctypes.c_int),
        ("cube_owner", ctypes.c_int),
        ("cube_x", ctypes.c_double * 3),
        ("jacoby", ctypes.c_int),
        ("cube_defer_first", ctypes.c_int),
        ("variance_reduction", ctypes.c_int),
        ("target_se", ctypes.c_double),
        ("min_trials", ctypes.c_ulong),
        ("use_match", ctypes.c_int),
        ("match", _CMatchState),
    ]


class _CRolloutResult(ctypes.Structure):
    _fields_ = [
        ("equity", ctypes.c_double),
        ("standard_error", ctypes.c_double),
        ("frequencies", ctypes.c_double * NUM_OUTPUTS),
        ("trials", ctypes.c_ulong),
        ("stalled", ctypes.c_ulong),
        ("cashed", ctypes.c_ulong),
        ("average_cube", ctypes.c_double),
        ("average_luck", ctypes.c_double),
    ]


_LIB.gn_rollout.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(_CRolloutConfig),
    ctypes.POINTER(_CRolloutResult),
]
_LIB.gn_rollout.restype = ctypes.c_int

_LIB.gn_rollout_candidates.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.c_int,
    ctypes.POINTER(_CRolloutConfig),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
_LIB.gn_rollout_candidates.restype = ctypes.c_int

_LIB.gn_rollout_candidates_paired.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.c_int,
    ctypes.POINTER(_CRolloutConfig),
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_ulong),
]
_LIB.gn_rollout_candidates_paired.restype = ctypes.c_int

_LIB.gn_rollout_difference.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(_CPosition),
    ctypes.POINTER(_CRolloutConfig),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
_LIB.gn_rollout_difference.restype = ctypes.c_int


@dataclass(frozen=True)
class RolloutConfig:
    """Combien de parties, jusqu'où, jouées comment, et avec quels dés.

    `seed` est le mécanisme des dés communs : deux variantes comparées **doivent**
    le partager. Les dés sont une fonction pure de `(seed, essai, ply)`, donc
    deux rollouts lancés depuis des positions différentes, dans des processus
    différents, rencontrent les mêmes dés aux mêmes rangs.

    `truncate` n'est pas une approximation d'un rollout complet qui coûterait
    moins cher : c'est un **estimateur différent**, à variance plus faible et à
    biais non nul. Lequel vaut mieux dépend de la précision du réseau à
    l'horizon, ce qui se mesure.

    `use_cube` (T39 × T34) : chaque essai porte un videau **vivant** — la
    décision est EXACTE dans le domaine de la table bilatérale, celle du
    modèle ajusté ailleurs ; un passe encaisse l'enjeu courant, une prise le
    double et transfère le videau. `cube_owner` est vu par le joueur au trait
    de la position confiée ; `cube_x` est indexé par état (centré, possédé,
    adverse) — les trois valeurs mesurées de t34-efficacite.json, jamais une
    seule recyclée. Les équités restent en unités du videau INITIAL.
    """

    trials: int = 1296
    truncate: int = 11
    seed: int = 0
    policy: SearchConfig = SearchConfig(ply=0)
    use_cube: bool = False
    cube_owner: int = 0
    cube_x: tuple[float, float, float] = (0.0, 0.0, 0.0)
    jacoby: bool = False
    #: L'option de double du tour courant est déjà passée — voir gn_rollout.h
    #: pour la sonde qui a fixé ce que la table bilatérale entend par là.
    #: Actif pour arbitrer une décision de videau ; inactif pour une position
    #: d'après-coup, dont l'adversaire entame son tour avec son option.
    cube_defer_first: bool = False
    #: Réduction de variance par la chance : à chaque pli, la chance du jet
    #: tiré (équité 0-ply du meilleur jeu sous ce jet, moins la moyenne
    #: pondérée des 21 jets) est soustraite de l'essai. Espérance nulle par
    #: construction — aucun biais possible, seulement moins de dés dans le
    #: résultat. Le prix (≈ une recherche 1-ply par coup joué) et le gain se
    #: mesurent : bench/vr_gain.py.
    variance_reduction: bool = False
    #: Arrêt sur l'intervalle : dès que le se atteint `target_se` (contrôlé
    #: toutes les 36 parties, jamais avant `min_trials`), le rollout s'arrête ;
    #: `trials` reste le plafond. Zéro conserve le comptage fixe. Pour une
    #: différence, c'est `rollout_difference` qui porte le bon critère —
    #: l'erreur SUR la différence.
    target_se: float = 0.0
    min_trials: int = 0
    #: Essais de MATCH : chaque partie finie (ou encaissée) devient des points,
    #: les points un score, le score une chance de gain de match par la MET —
    #: une partie par essai, la table valorisant toutes les suivantes. Le
    #: résultat est en équité de match (2·MWC − 1). `match` est l'état vu par
    #: le joueur au trait de la position confiée, `match.cube` le videau
    #: COURANT. `use_cube` garde son sens (consultation vivante), mais la
    #: décision passe par la récursion §9, jamais par le modèle money ni par
    #: la table exacte (money par nature). Un état invalide est refusé.
    match: MatchState | None = None

    def _to_c(self) -> _CRolloutConfig:
        c = _CRolloutConfig()
        c.trials = self.trials
        c.truncate = self.truncate
        c.seed = self.seed
        c.policy = self.policy._to_c()
        if self.use_cube:
            c.use_cube = 1
            c.cube_owner = int(self.cube_owner)
            c.cube_x = (ctypes.c_double * 3)(*self.cube_x)
            c.jacoby = int(self.jacoby)
            c.cube_defer_first = int(self.cube_defer_first)
        c.variance_reduction = int(self.variance_reduction)
        c.target_se = float(self.target_se)
        c.min_trials = int(self.min_trials)
        if self.match is not None:
            c.use_match = 1
            c.match = self.match._to_c()
        return c


@dataclass(frozen=True)
class RolloutResult:
    equity: float
    standard_error: float
    trials: int
    stalled: int
    frequencies: tuple[float, ...]
    #: Essais cubeful terminés par un passe, et videau final moyen — zéro
    #: l'un et l'autre pour un rollout cubeless.
    cashed: int = 0
    average_cube: float = 0.0
    #: Chance moyenne par essai — zéro sans réduction de variance. Son
    #: espérance est nulle par construction : loin de zéro à plusieurs se,
    #: c'est la correction elle-même qui est cassée. La moyenne non corrigée
    #: se retrouve par `equity + average_luck`.
    average_luck: float = 0.0

    def __str__(self) -> str:
        return (f"{self.equity:+.5f} ± {self.standard_error:.5f} "
                f"({self.trials} essais)")


def rollout(network: Network, position: Position,
            config: RolloutConfig | None = None) -> RolloutResult:
    """L'équité de `position`, du point de vue de `position.turn`."""
    config = config or RolloutConfig()
    result = _CRolloutResult()
    if _LIB.gn_rollout(network._handle, ctypes.byref(position._to_c()),
                       ctypes.byref(config._to_c()), ctypes.byref(result)) != 0:
        raise RuntimeError("rollout refusé")
    return RolloutResult(
        equity=result.equity,
        standard_error=result.standard_error,
        trials=result.trials,
        stalled=result.stalled,
        frequencies=tuple(result.frequencies),
        cashed=result.cashed,
        average_cube=result.average_cube,
        average_luck=result.average_luck,
    )


def rollout_candidates(network: Network, results: list[Position],
                       config: RolloutConfig | None = None
                       ) -> tuple[list[float], list[float]]:
    """L'équité de chaque coup candidat, **du point de vue de celui qui l'a joué**.

    Les positions passées sont les **résultats** des coups — elles ont déjà rendu
    le trait. La négation est faite dans le C, une fois, délibérément.
    """
    config = config or RolloutConfig()
    count = len(results)
    array = (_CPosition * count)(*(p._to_c() for p in results))
    equities = (ctypes.c_double * count)()
    errors = (ctypes.c_double * count)()
    if _LIB.gn_rollout_candidates(network._handle, array, count,
                                  ctypes.byref(config._to_c()),
                                  equities, errors) != 0:
        raise RuntimeError("rollout des candidats refusé")
    return list(equities), list(errors)


def rollout_difference(network: Network, a: Position, b: Position,
                       config: RolloutConfig | None = None) -> tuple[float, float]:
    """`a - b`, et l'erreur **sur la différence**, calculée sur les essais appariés.

    L'erreur rendue ici n'est pas celle qu'on obtiendrait en composant les deux
    marges : les dés étant partagés, la différence est bien mieux déterminée que
    chacun des deux termes. C'est tout l'intérêt du dispositif, et c'est la seule
    erreur qui a un sens quand on arbitre un désaccord.
    """
    config = config or RolloutConfig()
    difference = ctypes.c_double()
    error = ctypes.c_double()
    if _LIB.gn_rollout_difference(network._handle,
                                  ctypes.byref(a._to_c()), ctypes.byref(b._to_c()),
                                  ctypes.byref(config._to_c()),
                                  ctypes.byref(difference), ctypes.byref(error)) != 0:
        raise RuntimeError("rollout de différence refusé")
    return difference.value, error.value


#: La borne du C (`GN_ROLLOUT_MAX_CANDIDATES`). Répétée ici pour refuser côté
#: Python plutôt que de lire un -1 sans cause lisible.
MAX_CANDIDATES = 8


def rollout_candidates_paired(network: Network, results: list[Position],
                              config: RolloutConfig | None = None,
                              pivot: int = 0
                              ) -> tuple[list[float], list[float], list[float], int]:
    """L'arbitrage de T70 : chaque candidat, sa différence au pivot, et
    l'erreur **sur cette différence**.

    Rend `(équités, différences, erreurs, essais)`. C'est ce qui permet de payer
    un arbitrage **une fois** et d'y lire ensuite le coût de n'importe quel coup
    plausible : un moteur candidat qui joue autrement se note sur le même
    registre, sans nouveau rollout.

    Les erreurs marginales de `rollout_candidates` ne conviennent pas ici — les
    dés étant partagés, la différence est bien mieux déterminée que chacun des
    deux termes, et c'est la différence qu'on arbitre.
    """
    config = config or RolloutConfig()
    count = len(results)
    if not 0 < count <= MAX_CANDIDATES:
        raise ValueError(f"de 1 à {MAX_CANDIDATES} candidats, {count} demandés")
    if not 0 <= pivot < count:
        raise ValueError(f"pivot {pivot} hors des {count} candidats")

    array = (_CPosition * count)(*(p._to_c() for p in results))
    equities = (ctypes.c_double * count)()
    differences = (ctypes.c_double * count)()
    errors = (ctypes.c_double * count)()
    trials = ctypes.c_ulong()
    if _LIB.gn_rollout_candidates_paired(network._handle, array, count,
                                         ctypes.byref(config._to_c()), pivot,
                                         equities, differences, errors,
                                         ctypes.byref(trials)) != 0:
        raise RuntimeError("rollout apparié des candidats refusé")
    return (list(equities), list(differences), list(errors), int(trials.value))

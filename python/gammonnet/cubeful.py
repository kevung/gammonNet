"""T35 — parties **cubeful**, money et match : la boucle qui manquait à l'arène.

`arena.py` l'annonce depuis T04 : *« nothing pretends to double »*. Depuis,
T34 a donné le modèle de videau, T38 la table exacte, T32 l'équité de match —
cette boucle les branche pour faire jouer deux moteurs l'un contre l'autre,
videau compris. Elle n'altère rien de ce qu'`arena.py` mesure en cubeless :
mêmes dés dupliqués, mêmes graines dérivées de `(base, clé de paire, index)`,
même contrôle nul **exact** (A contre A totalise zéro, pas zéro-dans-l'IC).

## Qui répond à quoi

Chaque camp répond avec SON modèle, jamais avec celui d'en face :

* **Doubler ?** — le joueur au trait, avant de lancer. Son propre verdict §4
  (ou §9 au score) : il double si sa décision est DOUBLE_TAKE ou DOUBLE_PASS.
* **Prendre ?** — le joueur doublé, avec sa propre lecture de la même
  position (le trait reste au doubleur) : il prend si, selon lui, la branche
  prise coûte moins que la branche passée — `e_dt < e_dp`, vues du doubleur.

Un moteur qui déciderait sa prise avec le modèle du doubleur ne serait pas un
joueur, mais un écho.

## Le protocole est nommé, pas sous-entendu

* **Jacoby actif en money, des deux côtés** — décisions ET décompte final :
  une partie dont le videau n'a jamais tourné vaut un point, gammon ou pas.
  C'est la convention money par défaut de gnubg (sondée en T34, voir
  `bench/compare_cube.py`) et l'hypothèse du fit d'efficacité qu'on applique.
* **Pas de beaver** — ni notre modèle ni la question posée à gnubg n'en
  parlent.
* **Videau plafonné à 64 en money.** En match, pas de plafond : la règle du
  videau mort (Crawford, ou videau ≥ les deux scores restants) borne avant,
  la même garde que `gn_rollout.c`.
* **Nos décisions** : table bilatérale exacte dans son domaine (money
  uniquement — ses équités stockées sont des équités money), modèle §4/§9 à
  l'efficacité mesurée de T34 ailleurs. Le même chemin que `cube_action` dans
  `gn_rollout.c`.
* **Les leurs** : `cfevaluate` à profondeur nommée ; verdict de double par la
  classification sondée en T34, prise par comparaison numérique des équités
  take/drop que `cfevaluate` rend déjà.

## Ce que la segmentation d'une campagne exige d'ici

Rien de plus que ce que l'arène garantit déjà : une paire dupliquée est une
fonction pure de `(graine de base, clé, index)`. Un pilote peut donc jouer les
index dans n'importe quel ordre, s'arrêter, reprendre — l'union des résultats
est identique bit à bit à un calcul d'une traite. C'est une propriété testée
(`tests/test_cubeful.py`), pas une intention.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from . import gnubg_board as gb
from .arena import MAX_TURNS, derive_seed, game_value, opening_roll, pair_key
from .cube import CubeAction, CubeInputs, CubeOwner, decide, verdict
from .cube import value as cube_value
from .gnubg_engine import GnubgEngine, classify_gnubg_verdict, gnubg_state
from .met import MatchState
from .rules import BLACK, WHITE, Play, Position

_ROOT = Path(__file__).resolve().parent.parent.parent

MODEL = "models/cubeless_prob5_512_512_256_128.bin"
DATABASE = "gnu_bearoff_database/gnubg_ts6x11.bd"
EFFICIENCY_FILE = "docs/mesures/t34-efficacite.json"

#: Le plafond money habituel du videau physique. Nommé, comme chaque règle ici.
CUBE_CAP = 64

#: Les deux verdicts §4 qui signifient « je double ».
_DOUBLES = (CubeAction.DOUBLE_TAKE, CubeAction.DOUBLE_PASS)


def measured_efficiency(path: str | Path = EFFICIENCY_FILE) -> tuple[float, float, float]:
    """Le fit de T34, indexé comme `GnRolloutConfig.cube_x` : (centré,
    possédé, adverse). Lu depuis la mesure, jamais codé en dur."""
    p = Path(path)
    if not p.is_absolute():
        p = _ROOT / p
    results = json.loads(p.read_text())["results"]
    return (results["centered"]["x"], results["owned"]["x"], results["opponent"]["x"])


class CubefulPlayer(Protocol):
    """Ce que la boucle cubeful attend d'un moteur. Rien d'autre.

    Pour les deux questions de videau, `position.turn` est le DOUBLEUR
    potentiel ; `match` est l'état vu du doubleur, portant le videau COURANT.
    """

    name: str

    def choose(self, position: Position, d1: int, d2: int, rng: random.Random,
               match: MatchState | None = None) -> Play | None: ...

    def wants_double(self, position: Position, cube: int, owner: CubeOwner,
                     match: MatchState | None = None) -> bool: ...

    def accepts_double(self, position: Position, cube: int, owner: CubeOwner,
                       match: MatchState | None = None) -> bool: ...


# ── Notre joueur ─────────────────────────────────────────────────────


@dataclass
class GammonNetCubePlayer:
    """gammonNet complet : recherche filtrée pour les pions, T34 pour le videau.

    `ply`/`filter` — le joueur de pions : équité money cubeless, ou table de
    match au score (les identités mesurées par T36 et T31/T37). `cube_ply` —
    la profondeur des décisions de videau : distribution §8 par
    `position_probs`, puis `decide`.

    NON CHARGÉ À LA CONSTRUCTION — même règle de sérialisation que les autres
    moteurs : le harnais expédie les joueurs vers ses processus ouvriers, et
    un handle ctypes ne voyage pas.
    """

    ply: int = 0
    filter: tuple[int, ...] = ()
    cube_ply: int = 0
    model: str = MODEL
    database: str | None = DATABASE
    efficiency: tuple[float, float, float] | None = None
    jacoby: bool = True
    name: str = field(default="")
    _network: object = field(default=None, repr=False, compare=False)
    _exact: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if not self.name:
            suffix = "-f" + "/".join(str(k) for k in self.filter) if self.filter else ""
            self.name = f"gammonnet-{self.ply}ply{suffix}-cube{self.cube_ply}"

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_network"] = None
        state["_exact"] = None
        return state

    def _load(self):
        if self._network is None:
            from . import bearoff
            from .infer import Network

            path = Path(self.model)
            if not path.is_absolute():
                path = _ROOT / path
            self._network = Network.load(path)

            if self.database is not None:
                db = Path(self.database)
                if not db.is_absolute():
                    db = _ROOT / db
                if bearoff._shared is not None:
                    # Another player in this process already wired the shared
                    # table; a second mapping would waste a file descriptor
                    # and silently unhook theirs.
                    self._exact = bearoff._shared
                elif db.exists():
                    self._exact = bearoff.use_shared(db)

            if self.efficiency is None:
                self.efficiency = measured_efficiency()
        return self._network

    # ── Les pions ────────────────────────────────────────────────────

    def choose(self, position, d1, d2, rng, match=None):
        from .search import SearchConfig, best_play

        network = self._load()
        if match is None:
            config = SearchConfig(ply=self.ply, filter=self.filter)
        else:
            if not match.is_valid:
                raise ValueError(f"état de match non évaluable : {match}")
            config = SearchConfig(ply=self.ply, filter=self.filter,
                                  use_match=True, match=match)
        candidate = best_play(network, position, d1, d2, config)
        return candidate.play if candidate is not None else None

    # ── Le videau ────────────────────────────────────────────────────

    def _distribution(self, position, match):
        from .search import SearchConfig, position_probs

        config = SearchConfig(ply=self.cube_ply, filter=self.filter,
                              use_match=match is not None, match=match)
        return position_probs(self._load(), position, config)

    def wants_double(self, position, cube, owner, match=None):
        self._load()
        if match is None and self._exact is not None and self._exact.contains(position):
            exact = self._exact.equities(position)
            e_nd = exact.centered if owner == CubeOwner.CENTRED else exact.owned
            return verdict(e_nd, 2.0 * exact.opponent_owns, 1.0) in _DOUBLES
        decision = decide(self._distribution(position, match), owner,
                          self.efficiency[int(owner)], state=match,
                          jacoby=self.jacoby)
        return decision.action in _DOUBLES

    def accepts_double(self, position, cube, owner, match=None):
        self._load()
        x_taken = self.efficiency[int(CubeOwner.OPPONENT)]
        if match is None and self._exact is not None and self._exact.contains(position):
            # Exact e_dt, per current-cube unit, doubler's view; e_dp = 1.
            return 2.0 * self._exact.equities(position).opponent_owns < 1.0
        evaluation = self._distribution(position, match)
        if match is None:
            e_dt = 2.0 * CubeInputs.from_evaluation(evaluation).equity(
                CubeOwner.OPPONENT, 1, x_taken)
            return e_dt < 1.0
        doubled = MatchState(match.away_on_roll, match.away_opponent,
                             cube=2 * cube, crawford=match.crawford)
        e_dt = cube_value(evaluation, CubeOwner.OPPONENT, x_taken, doubled)
        e_dp = 2.0 * match.after(cube, True) - 1.0
        return e_dt < e_dp


# ── Le leur ──────────────────────────────────────────────────────────


@dataclass
class GnubgCubePlayer(GnubgEngine):
    """GNU Backgammon, videau compris — les questions de `cfevaluate`.

    Le jeu de pions est celui de `GnubgEngine` (convention composée, vérifiée
    en T36). **Au score il n'est pas encore sondé : demandé, il refuse** —
    jamais approximé en silence (CLAUDE.md, règle 2).
    """

    cube_ply: int = 0

    def __post_init__(self):
        auto = not self.name
        super().__post_init__()
        if auto:
            self.name = f"{self.name}-cube{self.cube_ply}"

    def choose(self, position, d1, d2, rng, match=None):
        if match is not None:
            raise NotImplementedError(
                "le jeu de pions de gnubg au score n'est pas sondé — "
                "refusé plutôt qu'approximé")
        return super().choose(position, d1, d2, rng)

    def _cube_answer(self, position, cube, owner, match):
        state = gnubg_state(owner, match, jacoby=match is None, cube=cube)
        values = self._connect().cubeful(
            [gb.to_gnubg(position)], plies=self.cube_ply,
            prune=self.prune, state=state)
        return values[0]

    def wants_double(self, position, cube, owner, match=None):
        # `cfevaluate` returns (optimal, nodouble, take, drop, code, text);
        # only the probed recommendation string is interpreted.
        answer = self._cube_answer(position, cube, owner, match)
        return classify_gnubg_verdict(str(answer[5])) in _DOUBLES

    def accepts_double(self, position, cube, owner, match=None):
        _optimal, _no_double, take, drop, _code, _text = self._cube_answer(
            position, cube, owner, match)
        # The taker minimises the doubler's equity: take when the taken
        # branch is worth less to the doubler than the passed one.
        return float(take) < float(drop)


# ── Une partie ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class CubefulResult:
    """Une partie cubeful, du point de vue de WHITE. `points` inclut le videau."""

    points: int
    turns: int
    cube: int
    doubles: int
    cashed: bool
    stalled: bool = False


def _mover_view(match, mover, cube):
    """L'état de match vu du joueur au trait, videau courant compris."""
    if match is None:
        return None
    away_white, away_black, crawford = match
    mine, theirs = ((away_white, away_black) if mover == WHITE
                    else (away_black, away_white))
    return MatchState(mine, theirs, cube=cube, crawford=crawford)


def play_cubeful_game(white, black, dice, white_rng, black_rng,
                      jacoby: bool = True, cap: int = CUBE_CAP,
                      match: tuple[int, int, bool] | None = None,
                      start: Position | None = None) -> CubefulResult:
    """Une partie avec videau vivant. `match` : None (money) ou
    `(away_white, away_black, crawford)`.

    La fenêtre de double est la fenêtre standard : le joueur au trait peut
    doubler avant de lancer, à partir du deuxième tour — le jet d'ouverture
    arrive déjà lancé. Un pass paie le videau d'AVANT le double refusé.

    `start` court-circuite le jet d'ouverture et fait démarrer la partie sur
    une position arbitraire, trait compris, fenêtre de double ouverte — ce
    dont les tests du protocole ont besoin pour placer une situation connue.
    """
    if start is None:
        first, d1, d2 = opening_roll(dice)
        position = Position.initial()
        if first == BLACK:
            position = position.swapped_turn()
        pending: tuple[int, int] | None = (d1, d2)
    else:
        position = start
        pending = None

    engines = {WHITE: white, BLACK: black}
    rngs = {WHITE: white_rng, BLACK: black_rng}

    cube, cube_owner, doubles = 1, None, 0
    turns = 0

    while turns < MAX_TURNS:
        mover = position.turn
        other = BLACK if mover == WHITE else WHITE

        if pending is None:
            may = cube_owner in (None, mover)
            if match is None:
                may = may and cube < cap
            else:
                away_white, away_black, crawford = match
                # The dead-cube guard of `gn_rollout.c::match_cube_is_dead`:
                # nobody is consulted during Crawford, or once the cube
                # covers both remaining scores.
                may = may and not crawford
                may = may and not (cube >= away_white and cube >= away_black)
            if may:
                state = _mover_view(match, mover, cube)
                owner = CubeOwner.CENTRED if cube_owner is None else CubeOwner.OWNED
                if engines[mover].wants_double(position, cube, owner, state):
                    doubles += 1
                    if engines[other].accepts_double(position, cube, owner, state):
                        cube *= 2
                        cube_owner = other
                    else:
                        points = cube if mover == WHITE else -cube
                        return CubefulResult(points, turns, cube, doubles,
                                             cashed=True)
            pending = (dice.randint(1, 6), dice.randint(1, 6))

        d1, d2 = pending
        pending = None

        play = engines[mover].choose(position, d1, d2, rngs[mover],
                                     match=_mover_view(match, mover, cube))
        position = play.result if play is not None else position.swapped_turn()
        turns += 1

        if position.is_over():
            winner = position.winner()
            value_won = game_value(position, winner)
            if match is None and jacoby and cube_owner is None:
                # Jacoby: an unturned cube caps the game at a single point.
                value_won = 1
            points = value_won * cube
            return CubefulResult(points if winner == WHITE else -points,
                                 turns, cube, doubles, cashed=False)

    return CubefulResult(0, turns, cube, doubles, cashed=False, stalled=True)


# ── Un match ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MatchResult:
    """Un match, du point de vue de WHITE : `won` vaut +1 ou -1."""

    won: int
    games: int
    turns: int
    biggest_cube: int
    doubles: int
    stalled: bool = False


def play_match(white, black, away_white: int, away_black: int, dice,
               white_rng, black_rng, crawford_done: bool = False) -> MatchResult:
    """Un match depuis un score arbitraire, joué jusqu'à son terme.

    La partie de Crawford est la première où exactement un joueur est à
    1-away ; `crawford_done` dit qu'elle est déjà derrière nous — ce que
    signifie échantillonner un score de départ post-Crawford.
    """
    games = turns = doubles = 0
    biggest = 1

    while away_white > 0 and away_black > 0:
        crawford_now = (not crawford_done) and ((away_white == 1) != (away_black == 1))
        result = play_cubeful_game(white, black, dice, white_rng, black_rng,
                                   match=(away_white, away_black, crawford_now))
        if crawford_now:
            crawford_done = True
        games += 1
        turns += result.turns
        doubles += result.doubles
        biggest = max(biggest, result.cube)
        if result.stalled:
            return MatchResult(0, games, turns, biggest, doubles, stalled=True)
        if result.points > 0:
            away_white = max(0, away_white - result.points)
        else:
            away_black = max(0, away_black - (-result.points))

    won = 1 if away_white <= 0 else -1
    return MatchResult(won, games, turns, biggest, doubles)


# ── Les paires dupliquées ────────────────────────────────────────────


def play_cubeful_duplicate(a, b, base_seed: int, index: int,
                           jacoby: bool = True, cap: int = CUBE_CAP,
                           dice_key: str | None = None) -> tuple[int, dict]:
    """`arena.play_duplicate`, videau vivant. Rend (points nets de A, stats).

    Mêmes clés, mêmes graines, même bascule de sièges — donc même contrôle
    nul exact, et même pureté par index qui rend une campagne segmentable.
    """
    key = dice_key if dice_key is not None else pair_key(a.name, b.name)
    seed = derive_seed(base_seed, key, index)

    total = 0
    stats = {"stalled": False, "cashed": 0, "doubles": 0, "biggest_cube": 1,
             "turns": 0}
    for swapped in (False, True):
        dice = random.Random(seed)
        white_rng = random.Random(seed ^ 0x5741_4954)
        black_rng = random.Random(seed ^ 0x424C_4143)

        white, black = (b, a) if swapped else (a, b)
        result = play_cubeful_game(white, black, dice, white_rng, black_rng,
                                   jacoby=jacoby, cap=cap)

        total += -result.points if swapped else result.points
        stats["stalled"] = stats["stalled"] or result.stalled
        stats["cashed"] += int(result.cashed)
        stats["doubles"] += result.doubles
        stats["biggest_cube"] = max(stats["biggest_cube"], result.cube)
        stats["turns"] += result.turns

    return total, stats


def play_match_duplicate(a, b, away_a: int, away_b: int, base_seed: int,
                         index: int, crawford_done: bool = False,
                         dice_key: str | None = None) -> tuple[int, dict]:
    """Une paire dupliquée de MATCHS sur la même situation de départ.

    Le score reste **collé au siège**, parce que les dés le sont : le siège
    WHITE part à `away_a`-away dans les deux manches et reçoit les mêmes
    jets ; seuls les moteurs échangent leurs places. Les deux manches ne
    diffèrent donc que par l'occupant de chaque situation — ce que la paire
    mesure — et A contre A totalise **exactement** zéro, à n'importe quel
    score. (Faire basculer les scores avec les sièges avait été essayé et
    casse cette propriété : le joueur à `away_a` recevrait les jets de
    l'autre rôle, et les deux manches seraient deux parties différentes.)

    La paire couvre d'elle-même les deux orientations : manche 1, A joue
    `away_a` contre B à `away_b` ; manche 2, B joue `away_a` contre A à
    `away_b`. Rend (victoires nettes de A ∈ {-2, 0, +2}, stats).
    """
    key = dice_key if dice_key is not None else pair_key(a.name, b.name)
    seed = derive_seed(base_seed, key, index)

    total = 0
    stats = {"stalled": False, "games": 0, "doubles": 0, "biggest_cube": 1,
             "turns": 0}
    for swapped in (False, True):
        dice = random.Random(seed)
        white_rng = random.Random(seed ^ 0x5741_4954)
        black_rng = random.Random(seed ^ 0x424C_4143)

        white, black = (b, a) if swapped else (a, b)
        result = play_match(white, black, away_a, away_b, dice,
                            white_rng, black_rng, crawford_done=crawford_done)

        total += -result.won if swapped else result.won
        stats["stalled"] = stats["stalled"] or result.stalled
        stats["games"] += result.games
        stats["doubles"] += result.doubles
        stats["biggest_cube"] = max(stats["biggest_cube"], result.biggest_cube)
        stats["turns"] += result.turns

    return total, stats

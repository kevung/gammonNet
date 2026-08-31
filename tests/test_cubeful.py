"""T35 — la boucle cubeful : contrôles nuls exacts, règles du protocole,
déterminisme.

Deux familles de tests, et la séparation est le point :

* **Les règles de la boucle** (Jacoby, cash, plafond, videau mort, Crawford)
  se testent avec des joueurs-stubs dont le comportement est écrit dans le
  test — la règle est isolée du modèle, et un stub qui LÈVE quand on le
  consulte prouve qu'on ne l'a pas consulté.
* **Les contrôles nuls et le déterminisme** se testent avec le vrai joueur :
  ce sont des propriétés du harnais entier, modèle compris.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.cubeful import (  # noqa: E402
    CUBE_CAP,
    GammonNetCubePlayer,
    play_cubeful_duplicate,
    play_cubeful_game,
    play_match,
    play_match_duplicate,
)
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"


@pytest.fixture(autouse=True, scope="module")
def _unhook_shared_bearoff():
    """`GammonNetCubePlayer` branche la table bilatérale PARTAGÉE — un état de
    processus. La débrancher en sortant, ou les tests suivants de la même
    session pytest évalueraient avec un autre évaluateur que seuls : le test
    de rollout à 3σ l'a détecté (échec en suite, succès isolé)."""
    yield
    from gammonnet.bearoff import disable_shared

    disable_shared()

needs_model = pytest.mark.skipif(not MODEL.exists(), reason="modèle absent")
needs_db = pytest.mark.skipif(not DATABASE.exists(),
                              reason="base bilatérale absente")


# ── Les stubs ────────────────────────────────────────────────────────


@dataclass
class Stub:
    """Un joueur dont le videau est scripté par le test.

    `double=None` signifie « ne doit jamais être consulté » : la question
    lève, et le test qui l'observe prouve que la boucle a bien appliqué sa
    garde (Crawford, videau mort) sans demander l'avis de personne.
    """

    double: bool | None = False
    take: bool | None = True
    name: str = "stub"

    def choose(self, position, d1, d2, rng, match=None):
        plays = position.legal_plays(d1, d2)
        return plays[0] if plays else None

    def wants_double(self, position, cube, owner, match=None):
        if self.double is None:
            raise AssertionError("wants_double consulté malgré la garde")
        return self.double

    def accepts_double(self, position, cube, owner, match=None):
        if self.take is None:
            raise AssertionError("accepts_double consulté malgré la garde")
        return self.take


def streams(seed: int):
    return (random.Random(seed), random.Random(seed ^ 1), random.Random(seed ^ 2))


def gammon_certain_for_white() -> Position:
    """WHITE porte ses deux derniers pions, BLACK n'a rien sorti : gammon au
    prochain jet, quel qu'il soit."""
    points = [0] * NUM_POINTS
    points[0] = 2
    points[18] = points[19] = points[20] = -5
    off = [0, 0]
    off[WHITE] = 13
    return Position(points=tuple(points), bar=(0, 0), off=tuple(off), turn=WHITE)


def hopeless_race_for_black() -> Position:
    """Course finie des deux côtés, WHITE gagne presque toujours — et dans le
    domaine de la table bilatérale (2 pions contre 2)."""
    points = [0] * NUM_POINTS
    points[0] = points[1] = 1
    points[22] = points[23] = -1
    off = [0, 0]
    off[WHITE] = 13
    off[BLACK] = 13
    return Position(points=tuple(points), bar=(0, 0), off=tuple(off), turn=WHITE)


# ── Les règles de la boucle, par stubs ───────────────────────────────


def test_jacoby_caps_an_unturned_cube_gammon_at_one_point():
    quiet = Stub(double=False)
    dice, wr, br = streams(1)
    result = play_cubeful_game(quiet, quiet, dice, wr, br, jacoby=True,
                               start=gammon_certain_for_white())
    assert result.points == 1
    assert result.cube == 1 and result.doubles == 0 and not result.cashed


def test_without_jacoby_the_same_gammon_pays_two():
    quiet = Stub(double=False)
    dice, wr, br = streams(1)
    result = play_cubeful_game(quiet, quiet, dice, wr, br, jacoby=False,
                               start=gammon_certain_for_white())
    assert result.points == 2


def test_a_pass_pays_the_cube_from_before_the_double():
    doubler = Stub(double=True)
    passer = Stub(double=False, take=False)
    dice, wr, br = streams(2)
    result = play_cubeful_game(doubler, passer, dice, wr, br,
                               start=gammon_certain_for_white())
    assert result.points == 1  # le videau montrait 1 quand BLACK a passé
    assert result.cashed and result.doubles == 1 and result.turns == 0


def test_the_money_cap_stops_the_doubling_war():
    warrior = Stub(double=True, take=True)
    dice, wr, br = streams(3)
    result = play_cubeful_game(warrior, warrior, dice, wr, br)
    assert result.cube == CUBE_CAP
    # Six doubles mènent de 1 à 64 ; au-delà, plus personne n'est consulté.
    assert result.doubles == 6
    assert result.points % CUBE_CAP == 0 and result.points != 0


def test_crawford_asks_nobody():
    muzzled = Stub(double=None, take=None)
    dice, wr, br = streams(4)
    result = play_cubeful_game(muzzled, muzzled, dice, wr, br,
                               match=(3, 1, True))
    assert result.cube == 1 and result.doubles == 0


def test_a_dead_cube_asks_nobody():
    muzzled = Stub(double=None, take=None)
    dice, wr, br = streams(5)
    result = play_cubeful_game(muzzled, muzzled, dice, wr, br,
                               match=(1, 1, False))
    assert result.cube == 1 and result.doubles == 0


def test_a_cube_dead_for_the_mover_alone_asks_nobody():
    """T35 residual (2026-08-26): `away_mover <= cube < away_opponent`.

    WHITE is on roll with cube=1 and away_white=1: winning this game
    already clinches the match for WHITE regardless of stake, so
    doubling has no upside for WHITE and only raises BLACK's gain if
    WHITE loses. The rate of doubling here should be exactly zero — the
    model measured 3.1% on sampled positions
    (docs/mesures/2026-08-26-T35-verdict.md). WHITE stays dead-for-itself
    for the whole game (its away can't grow), so it must never be asked;
    BLACK's own away (4) is untouched by the guard and gets a real
    (declining) policy so the game can proceed past its own turns.
    """
    muzzled_white = Stub(double=None, take=None)
    declining_black = Stub(double=False, take=True)
    dice, wr, br = streams(5)
    result = play_cubeful_game(muzzled_white, declining_black, dice, wr, br,
                               match=(1, 4, False),
                               start=Position.initial())
    assert result.cube == 1 and result.doubles == 0


def test_a_match_ends_and_names_its_winner():
    eager = Stub(double=True, take=True)
    dice, wr, br = streams(6)
    result = play_match(eager, eager, 5, 3, dice, wr, br)
    assert result.won in (+1, -1)
    assert result.games >= 1 and not result.stalled


# ── Le harnais entier, avec le vrai joueur ───────────────────────────


@needs_model
def test_money_null_control_is_exactly_zero():
    player = GammonNetCubePlayer(ply=0)
    for index in range(3):
        total, stats = play_cubeful_duplicate(player, player, 20260809, index)
        assert total == 0, f"paire {index} : {total} ≠ 0"
        assert not stats["stalled"]


@needs_model
def test_match_null_control_is_exactly_zero_even_at_an_asymmetric_score():
    player = GammonNetCubePlayer(ply=0)
    total, stats = play_match_duplicate(player, player, 5, 3, 20260809, 0)
    assert total == 0
    assert not stats["stalled"]


@needs_model
def test_a_duplicate_pair_is_a_pure_function_of_its_index():
    player = GammonNetCubePlayer(ply=0)
    first = play_cubeful_duplicate(player, player, 20260809, 7)
    again = play_cubeful_duplicate(player, player, 20260809, 7)
    assert first == again


# ── Nos décisions de videau, sur la table exacte ─────────────────────


@needs_model
@needs_db
def test_our_player_doubles_a_hopeless_race_and_refuses_to_take_it():
    player = GammonNetCubePlayer(ply=0)
    player._load()
    position = hopeless_race_for_black()
    assert player._exact is not None and player._exact.contains(position)

    assert player.wants_double(position, 1, CubeOwner.CENTRED)
    assert not player.accepts_double(position, 1, CubeOwner.CENTRED)


@needs_model
@pytest.mark.skipif(__import__("shutil").which(
    __import__("os").environ.get("GNUBG", "gnubg")) is None,
    reason="gnubg absent")
def test_a_cubeful_pair_against_gnubg_completes():
    """Fumée : gnubg répond aux deux questions de videau dans une vraie
    partie, et la paire se termine. Aucune affirmation de force ici — une
    paire n'est pas une mesure."""
    from gammonnet.cubeful import GnubgCubePlayer

    ours = GammonNetCubePlayer(ply=0)
    theirs = GnubgCubePlayer(ply=0, cube_ply=0)
    total, stats = play_cubeful_duplicate(ours, theirs, 20260809, 0)
    assert isinstance(total, int)
    assert stats["turns"] > 0 and not stats["stalled"]


@needs_model
@pytest.mark.skipif(__import__("shutil").which(
    __import__("os").environ.get("GNUBG", "gnubg")) is None,
    reason="gnubg absent")
def test_gnubg_score_evaluation_still_speaks_emg():
    """L'ancrage de la sonde du 2026-08-09, tenu contre toute dérive : une
    perte simple certaine vaut exactement −1,0 à tous les scores — la
    signature de l'échelle EMG sur laquelle repose le jeu de gnubg au score.
    Si gnubg change d'échelle un jour, ce test le dira avant la campagne."""
    from gammonnet import gnubg_board as gb
    from gammonnet.gnubg_engine import GnubgSession, gnubg_state
    from gammonnet.met import MatchState

    points = [0] * NUM_POINTS
    points[0] = 2
    points[18] = points[19] = points[20] = -2
    off = [0, 0]
    off[WHITE] = 13
    off[BLACK] = 9
    certain_loss = Position(points=tuple(points), bar=(0, 0),
                            off=tuple(off), turn=BLACK)

    with GnubgSession() as session:
        board = gb.to_gnubg(certain_loss)
        for match in (MatchState(2, 2), MatchState(2, 4), MatchState(1, 1)):
            state = gnubg_state(CubeOwner.CENTRED, match, jacoby=False)
            values = session.evaluate([board], plies=0, state=state)
            assert float(values[0][5]) == pytest.approx(-1.0, abs=1e-6), match


@needs_model
@pytest.mark.skipif(__import__("shutil").which(
    __import__("os").environ.get("GNUBG", "gnubg")) is None,
    reason="gnubg absent")
def test_a_match_pair_against_gnubg_completes_at_dmp():
    """Fumée : gnubg joue ses pions AU SCORE (chemin EMG) dans un vrai match.
    DMP, pour que la paire reste courte et ne consulte pas le videau."""
    from gammonnet.cubeful import GnubgCubePlayer

    ours = GammonNetCubePlayer(ply=0)
    theirs = GnubgCubePlayer(ply=0, cube_ply=0)
    total, stats = play_match_duplicate(ours, theirs, 1, 1, 20260809, 0)
    assert total in (-2, 0, 2)
    assert stats["doubles"] == 0 and stats["biggest_cube"] == 1
    assert not stats["stalled"]


@needs_model
@needs_db
def test_the_exact_and_model_take_answers_agree_here():
    """La même question, par les deux chemins : la table exacte, et le modèle
    §4 privé de table. Sur une course sans espoir ils doivent tomber d'accord
    — un désaccord signalerait un branchement cassé, pas une nuance."""
    with_table = GammonNetCubePlayer(ply=0)
    without = GammonNetCubePlayer(ply=0, database=None,
                                  name="gammonnet-0ply-no-table")
    position = hopeless_race_for_black()
    assert with_table.accepts_double(position, 1, CubeOwner.CENTRED) is False
    assert without.accepts_double(position, 1, CubeOwner.CENTRED) is False

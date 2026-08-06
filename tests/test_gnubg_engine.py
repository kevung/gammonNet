"""GNU Backgammon lui-même comme oracle — la plomberie, vérifiée.

Le contrôle central est le **croisement au 0-ply contre `gnubg-nn`**. C'est le
seul endroit où les deux oracles sont censés dire la même chose : même moteur à
l'origine, aucune table d'équité consultée en money, et `gnubg-nn` y est sain
— c'est au-delà du 0-ply qu'il plante.

Si le nouveau chemin — conversion de plateau, protocole JSON, convention de
profondeur, signe de l'équité — se trompait quelque part, ce croisement le
dirait. Qu'il passe n'établit pas que le 2-ply est juste ; il établit que la
plomberie l'est.
"""

from __future__ import annotations

import random

import pytest

from gammonnet import BLACK, Position
from gammonnet import gnubg_board as gb
from gammonnet.arena import opening_roll

gnubg_engine = pytest.importorskip("gammonnet.gnubg_engine")

GnubgEngine = gnubg_engine.GnubgEngine
GnubgSession = gnubg_engine.GnubgSession


@pytest.fixture(scope="module")
def session():
    with GnubgSession() as live:
        yield live


def random_positions(count: int, seed: int) -> list[tuple[Position, int, int]]:
    """Des positions atteintes par jeu aléatoire, avec leur jet.

    Le jeu aléatoire produit des positions bien plus variées que la partie
    d'ouverture — barre, fermetures, courses, bearoffs — et `BRIEF.md` §6
    insiste : une position symétrique ne détecte pas une inversion de
    perspective.
    """
    from gammonnet.arena import RandomEngine

    rng = random.Random(seed)
    engine = RandomEngine()
    out = []

    position = Position.initial()
    first, d1, d2 = opening_roll(rng)
    if first == BLACK:
        position = position.swapped_turn()

    while len(out) < count:
        if len(position.legal_plays(d1, d2)) >= 2:
            out.append((position, d1, d2))
        play = engine.choose(position, d1, d2, rng)
        position = play.result if play is not None else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
            first, d1, d2 = opening_roll(rng)
            if first == BLACK:
                position = position.swapped_turn()
            continue
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)

    return out


def test_session_starts_and_reports_its_python(session):
    assert session.python.startswith("3.")


def test_evaluation_is_a_distribution_plus_an_equity(session):
    board = gb.to_gnubg(Position.initial())
    (value,) = session.evaluate([board], plies=0)
    assert len(value) == 6
    win, wg, wbg, lg, lbg, equity = value
    # Événements imbriqués : gagner un backgammon, c'est gagner un gammon,
    # c'est gagner. Le même contrôle que T10 impose à notre propre réseau.
    assert 0.0 <= wbg <= wg <= win <= 1.0
    assert 0.0 <= lbg <= lg <= 1.0
    assert -3.0 <= equity <= 3.0


def test_batch_matches_one_at_a_time(session):
    """Le lot est une optimisation ; il ne doit rien changer au résultat."""
    cases = random_positions(12, seed=4)
    boards = [gb.to_gnubg(p) for p, _, _ in cases]

    together = session.evaluate(boards, plies=0)
    apart = [session.evaluate([b], plies=0)[0] for b in boards]

    assert together == apart


def test_evaluation_is_deterministic(session):
    board = gb.to_gnubg(random_positions(1, seed=7)[0][0])
    assert session.evaluate([board], plies=1) == session.evaluate([board], plies=1)


def test_depth_changes_the_answer(session):
    """Une profondeur qui ne change jamais rien signale une recherche fausse.

    Le contrôle que `PLAN.md` désigne comme le plus révélateur de la chaîne,
    appliqué ici à l'oracle plutôt qu'à nous.
    """
    boards = [gb.to_gnubg(p) for p, _, _ in random_positions(20, seed=8)]
    shallow = session.evaluate(boards, plies=0)
    deeper = session.evaluate(boards, plies=1)
    assert shallow != deeper


def test_agrees_with_gnubg_nn_at_zero_ply():
    """LE contrôle. Deux chemins vers le même moteur doivent choisir pareil.

    `gnubg-nn` est le binding en processus, croisé de longue date par T03 ; le
    nouveau chemin passe par le mode Python de GNU Backgammon et compose le
    choix lui-même. Ils n'ont en commun que le moteur.

    Un désaccord ici dénoncerait la conversion de plateau, le signe de
    l'équité, ou la convention de profondeur — et aucune de ces trois erreurs
    ne fait planter quoi que ce soit.
    """
    oracle_nn = pytest.importorskip("gammonnet.oracle")

    cases = random_positions(150, seed=20260806)
    ours = GnubgEngine(ply=0)
    theirs = oracle_nn.Oracle(ply=0)

    agree = 0
    for position, d1, d2 in cases:
        mine = ours.choose(position, d1, d2, random.Random(0))
        yours = theirs.best_play(position, d1, d2)
        if gb.key(mine.result) == gb.key(yours.result):
            agree += 1

    rate = agree / len(cases)
    # Pas 100 % attendu : deux coups d'équité identique au bit près se
    # départagent par l'ordre d'énumération, qui n'est pas le même des deux
    # côtés. Un accord élevé établit la plomberie ; un accord parfait serait
    # une coïncidence sur laquelle il ne faut pas s'appuyer.
    assert rate >= 0.95, f"accord au 0-ply : {rate:.1%} sur {len(cases)} décisions"


def test_terminal_positions_are_computed_not_evaluated():
    """Une partie finie ne se donne pas à un réseau.

    Le moteur doit choisir le coup gagnant sans jamais soumettre la position
    terminale à l'oracle. Le contrôle est indirect mais suffisant : le coup
    retenu termine la partie.
    """
    # Blanc a un pion sur l'as, tout le reste sorti ; un 1 le sort.
    points = [0] * 24
    points[0] = 1
    points[23] = -2
    position = Position(points=tuple(points), bar=(0, 0), off=(14, 13), turn=1)

    engine = GnubgEngine(ply=0)
    play = engine.choose(position, 1, 3, random.Random(0))
    assert play is not None
    assert play.result.is_over()

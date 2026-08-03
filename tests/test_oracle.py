"""T03 — l'oracle GNU Backgammon.

Ces tests ne mesurent aucune force. Ils établissent que l'instrument **répond**,
qu'il répond de façon cohérente, et surtout que **les positions qu'on lui envoie
sont bien celles qu'on croit** : le contrôle croisé du compte de pips valide du
même coup la traduction de position de T02.
"""

from __future__ import annotations

import random

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet import gnubg_board as gb

gnubg_nn = pytest.importorskip("gnubg_nn", reason="gnubg-nn absent — lancer `make venv`")

from gammonnet.oracle import Evaluation, Oracle, match_score  # noqa: E402

SEED = 20260803
CORPUS_SIZE = 1200


def build_corpus(size: int, seed: int = SEED) -> list[Position]:
    rng = random.Random(seed)
    positions: list[Position] = []

    while len(positions) < size:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()

        for _ in range(400):
            if position.is_over() or len(positions) >= size:
                break
            positions.append(position)
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()

    return positions


CORPUS = build_corpus(CORPUS_SIZE)


# ── L'oracle répond ──────────────────────────────────────────────────


def test_oracle_answers_on_the_whole_corpus():
    """T03 exige ≥ 1 000 positions rendues sans erreur."""
    assert len(CORPUS) >= 1000

    oracle = Oracle(ply=0)
    for position in CORPUS:
        evaluation = oracle.evaluate(position)
        assert isinstance(evaluation, Evaluation)
        for value in evaluation.as_tuple():
            assert 0.0 <= value <= 1.0, f"{position!r} : probabilité hors [0, 1]"


def test_nested_events_hold_everywhere():
    """Un gammon est un gain, un backgammon est un gammon.

    Une distribution qui viole l'imbrication n'est pas une distribution, et
    toute équité qu'on en tirerait serait plausible et dépourvue de sens.
    """
    oracle = Oracle(ply=0)
    for position in CORPUS:
        evaluation = oracle.evaluate(position)
        assert evaluation.nested_events_hold(), f"{position!r} : {evaluation}"


# ── Le contrôle croisé qui valide T02 ────────────────────────────────


def test_positions_sent_to_the_oracle_are_the_ones_we_mean():
    """La sentinelle du compte de pips, sur le chemin vers l'oracle.

    C'est le contrôle explicitement demandé par T03 : il valide la traduction de
    position autant que l'oracle. Une inversion de perspective ne planterait pas
    — elle ferait évaluer une autre position, sans aucun signe.
    """
    for position in CORPUS:
        board = gb.to_gnubg(position)
        opponent = BLACK if position.turn == WHITE else WHITE

        assert gb._gnubg_pip_count(board[1]) == position.pip_count(position.turn)
        assert gb._gnubg_pip_count(board[0]) == position.pip_count(opponent)

        # Et la position reconstruite depuis le plateau gnubg est la même.
        back = gb.from_gnubg(board, on_roll=position.turn)
        assert back.points == position.points
        assert back.bar == position.bar
        assert back.off == position.off


def test_a_won_position_evaluates_as_won_from_both_sides():
    """Contrôle d'orientation sur une position dont la réponse est connue.

    Une position d'ouverture ne détecterait rien : elle est son propre miroir.
    """
    points = [0] * 24
    points[0] = 1        # un pion blanc sur l'as
    points[23] = -15     # tout Noir encore au départ
    winning = Position(tuple(points), (0, 0), (14, 0), WHITE)
    losing = Position(tuple(points), (0, 0), (14, 0), BLACK)

    oracle = Oracle(ply=0)
    assert oracle.evaluate(winning).win == pytest.approx(1.0)
    assert oracle.evaluate(losing).win == pytest.approx(0.0)
    assert oracle.evaluate(winning).equity > 0.9
    assert oracle.evaluate(losing).equity < -0.9


# ── Le choix du coup ─────────────────────────────────────────────────


def test_best_opening_play_for_three_one():
    """8/5 6/5 est le meilleur coup d'ouverture sur 3-1, et fait consensus."""
    oracle = Oracle(ply=0)
    play = oracle.best_play(Position.initial(), 3, 1)

    # 8/5 6/5 : depuis les index 7 et 5 vers l'index 4, qui porte alors 2 pions.
    assert play is not None
    assert play.result.points[4] == 2, f"coup retenu : {play}"
    assert play.result.points[7] == 2
    assert play.result.points[5] == 4


def test_ranked_plays_cover_exactly_our_legal_plays():
    """L'oracle et nous devons voir le même ensemble de coups, pas seulement autant."""
    oracle = Oracle(ply=0)
    rng = random.Random(11)

    for position in CORPUS[:300]:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        ours = position.legal_plays(d1, d2)
        ranked = oracle.ranked_plays(position, d1, d2)

        assert len(ranked) == len(ours)
        assert {gb.key(r.play.result) for r in ranked} == {gb.key(p.result) for p in ours}


def test_ranked_plays_are_ordered_best_first():
    oracle = Oracle(ply=0)
    rng = random.Random(12)

    for position in CORPUS[:300]:
        ranked = oracle.ranked_plays(position, rng.randint(1, 6), rng.randint(1, 6))
        equities = [r.equity for r in ranked]
        assert equities == sorted(equities, reverse=True), "candidats non triés"


def test_no_legal_play_yields_no_candidate():
    """Zéro coup légal est un résultat, pas une erreur."""
    points = [0] * 24
    points[12], points[11], points[10] = 5, 5, 3   # 13 pions blancs, plus 2 sur la barre
    for i in range(18, 24):
        points[i] = -2                             # Noir ferme le jan d'entrée de Blanc
    points[0] = -3
    blocked = Position(tuple(points), (2, 0), (0, 0), WHITE)

    assert blocked.is_valid()
    assert blocked.legal_plays(3, 1) == []
    assert Oracle(ply=0).ranked_plays(blocked, 3, 1) == []
    assert Oracle(ply=0).best_play(blocked, 3, 1) is None


# ── La profondeur ────────────────────────────────────────────────────


def test_depth_changes_the_answer():
    """Une profondeur qui ne change rien signalerait un paramètre ignoré.

    C'est le contrôle le moins cher qui distingue « 2-ply » de « 0-ply appelé
    2-ply » — le même piège que T30 traitera comme bloquant.
    """
    initial = Position.initial()
    answers = [Oracle(ply=p).evaluate(initial).as_tuple() for p in (0, 1, 2)]

    assert answers[0] != answers[1], "0-ply et 1-ply rendent la même chose"
    assert answers[1] != answers[2], "1-ply et 2-ply rendent la même chose"


def test_evaluation_is_deterministic():
    """Deux appels identiques rendent la même chose, au bit près."""
    oracle = Oracle(ply=1)
    for position in CORPUS[:200]:
        assert oracle.evaluate(position).as_tuple() == oracle.evaluate(position).as_tuple()


# ── Équité de match et videau ────────────────────────────────────────


def test_match_equity_is_antisymmetric():
    """`value(i, j) == -value(j, i)`, et zéro sur la diagonale.

    La tolérance n'est pas cosmétique : la table est stockée en **float32**, et
    l'antisymétrie ne tient donc qu'à ~1e-7, pas au bit près. C'est mesuré, pas
    supposé — et c'est à savoir avant T32, dont le critère porte sur une table
    d'équité de match que nous embarquerons nous-mêmes.
    """
    worst = 0.0

    for i in range(1, 16):
        assert Oracle.match_equity(i, i) == pytest.approx(0.0, abs=1e-6), f"diagonale {i}"
        for j in range(1, 16):
            residual = abs(Oracle.match_equity(i, j) + Oracle.match_equity(j, i))
            worst = max(worst, residual)
            assert residual < 1e-6, f"({i}, {j}) : résidu {residual}"

    assert worst > 0.0, "antisymétrie exacte : la table n'est peut-être pas en float32"
    print(f"\nrésidu d'antisymétrie maximal : {worst:.3e} (float32)")


def test_match_score_context_restores_the_money_game():
    """Le score vit dans un global : un score oublié colorerait tout ce qui suit."""
    initial = Position.initial()
    oracle = Oracle(ply=0)

    before = oracle.evaluate(initial).as_tuple()
    with match_score(3, 5):
        pass
    assert oracle.evaluate(initial).as_tuple() == before


def test_cube_decision_is_exposed_but_not_interpreted():
    """Le videau répond ; sa sémantique n'est pas établie et rien ne s'en sert.

    Le test vérifie exactement cela — que l'appel aboutit sous un score de match
    et échoue en money — et surtout pas ce que les valeurs signifient.
    """
    oracle = Oracle(ply=0)
    initial = Position.initial()

    with match_score(3, 5):
        verdict = oracle.raw_cube_decision(initial)
        assert isinstance(verdict, tuple) and len(verdict) == 6

    with pytest.raises(RuntimeError):
        oracle.raw_cube_decision(initial)

"""T92 — le pont vers le moteur tiers, et l'instrument qui s'en sert.

Aucune force n'est mesurée ici. Ce qui est vérifié, ce sont les **propriétés**
du pont : une conversion qui perd l'orientation ne lève rien, elle produit une
position plausible qui n'est pas celle qu'on voulait, et toute mesure prise
ensuite est fausse sans jamais en avoir l'air (`CLAUDE.md` règle 2).

Le banc `bench/probe_sage_bridge.py` fait le contrôle au volume — 200 000
positions. Ce fichier tient les invariants qu'une suite doit rejouer en
secondes, et les deux conventions que T92 a établies plutôt que supposées :
l'absence de coup légal, et la numérotation des niveaux.
"""

from __future__ import annotations

import random

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet.sage_board import from_sage, to_sage

bgsage = pytest.importorskip("bgsage", reason="l'oracle de la phase 9 n'est pas installé")


def played_positions(seed: int, count: int) -> list[tuple[Position, int, int]]:
    """Positions atteintes par des coups au hasard, avec le jet qui suit.

    Le hasard est délibéré : il atteint la barre, les sorties et les plateaux
    déséquilibrés qu'une bonne politique évite — exactement là où une erreur
    d'orientation se verrait.
    """
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []
    while len(out) < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(120):
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
            out.append((position, d1, d2))
            if len(out) >= count:
                break
            plays = position.legal_plays(d1, d2)
            if not plays:
                position = position.swapped_turn()
                continue
            position = rng.choice(plays).result
            if position.is_over():
                break
    return out[:count]


def test_the_starting_position_is_the_one_they_ship():
    """Le plateau de départ des deux côtés est le même objet.

    C'est le seul contrôle que la position d'ouverture autorise : elle est
    symétrique, donc muette sur l'orientation. Il attrape une erreur de
    numérotation, pas une inversion de camp — d'où tout ce qui suit.
    """
    assert to_sage(Position.initial()) == bgsage.STARTING_BOARD


def test_the_conversion_survives_a_round_trip_from_either_side():
    for position, _, _ in played_positions(20260907, 400):
        board = to_sage(position)
        assert from_sage(board, on_roll=position.turn) == position


def test_black_and_white_produce_the_same_board_from_the_mover_s_seat():
    """Le plateau ne dépend que de **qui joue**, pas de la couleur qu'on a nommée.

    Une position et son miroir, vues chacune par le camp au trait, donnent des
    plateaux identiques. C'est ce qui rend l'orientation vérifiable sans avoir à
    croire un commentaire.
    """
    for position, _, _ in played_positions(20260908, 200):
        mirrored = Position(
            points=tuple(-n for n in reversed(position.points)),
            bar=(position.bar[BLACK], position.bar[WHITE]),
            off=(position.off[BLACK], position.off[WHITE]),
            turn=BLACK if position.turn == WHITE else WHITE,
        )
        assert to_sage(position) == to_sage(mirrored)


def test_the_legal_play_sets_agree():
    """Deux générateurs de coups indépendants, le même ensemble de positions.

    Contrôle bien plus fort que le compte de pips : celui-ci ne voit pas une
    erreur de génération de coups, celui-là ne voit pas une erreur d'orientation.
    """
    for position, d1, d2 in played_positions(20260909, 400):
        mover = position.turn
        ours = {tuple(to_sage(p.result, on_roll=mover)) for p in position.legal_plays(d1, d2)}
        board = to_sage(position)
        theirs = {tuple(b) for b in bgsage.possible_moves(board, d1, d2)}
        if not ours:
            # Convention différente, même sens : nous rendons une liste vide, il
            # rend le plateau inchangé. Établi par mesure, pas par son docstring,
            # qui annonce une liste vide.
            assert theirs == {tuple(board)}
            continue
        assert ours == theirs


def test_a_wrong_orientation_is_refused_rather_than_evaluated():
    """La sentinelle du compte de pips doit **lever**, pas corriger.

    Un plateau dont un camp a plus de quinze pions n'est pas une position ; le
    laisser passer produirait cinq probabilités parfaitement plausibles.
    """
    board = to_sage(Position.initial())
    board[10] += 3
    with pytest.raises(ValueError):
        from_sage(board, on_roll=WHITE)


def test_the_level_labels_are_offset_by_one():
    """Leur `3ply` est notre 2-ply — vérifié, jamais supposé.

    Ils numérotent depuis l'évaluation statique. Comparer notre 2-ply à leur
    `2ply` comparerait deux profondeurs différentes, dans le sens qui nous
    arrange. `SageEngine` porte la profondeur réelle dans son nom pour que la
    confusion n'ait pas de place où se loger.
    """
    from gammonnet.arena import SageEngine

    assert SageEngine(level="1ply").real_ply == 0
    assert SageEngine(level="3ply").real_ply == 2
    assert SageEngine(level="3ply").name == "sage-2ply"
    assert SageEngine(level="truncated1").real_ply is None
    with pytest.raises(ValueError):
        SageEngine(level="2-ply")


def test_the_third_engine_only_ever_returns_one_of_our_legal_plays():
    """L'instrument traduit, puis vérifie — il ne joue jamais un coup à nous inconnu."""
    from gammonnet.arena import SageEngine

    engine = SageEngine(level="1ply")
    rng = random.Random(0)
    for position, d1, d2 in played_positions(20260910, 120):
        play = engine.choose(position, d1, d2, rng)
        legal = position.legal_plays(d1, d2)
        if not legal:
            assert play is None
        else:
            assert play in legal

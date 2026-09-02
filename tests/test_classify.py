"""Le classificateur de T70/T77 : chaque classe est atteinte par une position
construite à la main, et la priorité entre classes est vérifiée là où deux
définitions se recouvrent.

Un classificateur qui se trompe ne plante pas : il déplace silencieusement une
strate entière du corpus. D'où des positions écrites en clair plutôt qu'un
échantillon aléatoire dont on lirait les proportions.

`build` **refuse** une position invalide. Le premier jet de ce fichier en
contenait six : le point `n` d'un joueur est le point `25 - n` de l'autre, et
les deux camps ne peuvent pas l'occuper ensemble. L'erreur ne se voyait pas —
elle rendait juste des classes plausibles et fausses.
"""

import pytest

from gammonnet.classify import CLASSES, classify
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position


def build(white: dict[int, int], black: dict[int, int],
          turn: int = WHITE, bar=(0, 0), off=(0, 0)) -> Position:
    """Une position depuis les points de CHAQUE joueur, dans son propre repère.

    `white[3] = 2` : deux pions blancs sur le point 3 de Blanc. `black[3] = 2` :
    deux pions noirs sur le point 3 de Noir — l'indice 21 du tableau. Écrire les
    deux camps dans leur repère est ce qui rend les cas lisibles.
    """
    collisions = {n for n in white if (25 - n) in black}
    assert not collisions, (
        f"points occupés par les deux camps : {sorted(collisions)} pour Blanc, "
        f"soit {sorted(25 - n for n in collisions)} pour Noir")
    points = [0] * NUM_POINTS
    for point, count in white.items():
        points[point - 1] += count
    for point, count in black.items():
        points[NUM_POINTS - point] -= count
    position = Position(tuple(points), bar, off, turn)
    assert position.is_valid(), f"position invalide : {position!r}"
    return position


def test_initial_position_is_contact():
    assert classify(Position.initial()) == "contact"


def test_bearoff_without_contact():
    position = build({1: 3, 2: 3, 3: 2}, {1: 3, 2: 3, 3: 2}, off=(7, 7))
    assert classify(position) == "bearoff_noncontact"


def test_bearoff_with_contact_is_not_the_same_strate():
    """Mêmes pions rentrés, mais un arriéré adverse derrière : la question
    posée change complètement, la strate aussi."""
    position = build({2: 3, 3: 3, 4: 2}, {1: 5, 2: 5, 24: 2}, off=(7, 3))
    assert classify(position) == "bearoff_contact"


def test_pure_race():
    position = build({7: 5, 8: 5, 9: 5}, {7: 5, 8: 5, 9: 5})
    assert classify(position) == "race"


def test_residual_contact_is_its_own_strate():
    """Un seul arriéré, à quelques pips de la course pure — ni course ni
    contact, c'est le cas que DS-13 vise."""
    position = build({6: 4, 8: 2, 14: 1}, {6: 4, 8: 2, 13: 2}, off=(8, 7))
    assert classify(position) == "race_contact"


def test_backgame_takes_priority_over_holding():
    """Trois ancrages dans le jan adverse : c'est un backgame, même si
    l'ancrage à 20 et un déficit de course en feraient aussi un holding."""
    position = build({20: 2, 22: 2, 23: 2, 13: 5, 8: 4},
                     {6: 5, 8: 3, 13: 5, 24: 2})
    assert classify(position) == "backgame"


def test_prime_against_prime():
    """Deux murs de quatre, et chacun un arriéré à faire passer."""
    position = build({4: 2, 5: 2, 6: 2, 7: 2, 9: 2, 13: 3, 22: 2},
                     {4: 2, 5: 2, 6: 2, 7: 2, 10: 2, 14: 3, 23: 2})
    assert classify(position) == "prime_vs_prime"


def test_blitz_needs_the_opponent_on_the_bar():
    """Trois points du jan tenus **et** un pion adverse à rentrer."""
    home = {1: 2, 2: 2, 3: 2, 8: 4, 13: 5}
    away = {6: 5, 8: 3, 13: 4, 20: 2}
    assert classify(build(home, away, bar=(0, 1))) == "blitz"
    # Sans le pion sur la barre, la même structure n'est pas un blitz.
    assert classify(build(home, {**away, 6: 6})) != "blitz"


def test_crashed_counts_checkers_outside_the_home_board():
    """Deux pions hors du jan : le jeu est en ruine, quelle que soit la suite."""
    position = build({1: 4, 2: 4, 3: 5, 13: 2}, {6: 5, 8: 4, 13: 4, 20: 2})
    assert classify(position) == "crashed"


def test_holding_needs_both_the_anchor_and_the_deficit():
    """L'ancrage seul ne suffit pas : sans déficit de course, on n'est pas en
    train de tenir, on est devant."""
    white = {4: 2, 6: 3, 8: 3, 13: 5, 20: 2}
    behind = {4: 4, 6: 5, 8: 4, 24: 2}
    position = build(white, behind)
    assert position.pip_count(WHITE) - position.pip_count(BLACK) >= 10
    assert classify(position) == "holding"


def test_point_of_view_matters():
    """Une position rend deux classes, une par camp — c'est la règle, et c'est
    ce qui permet à T77 de lire la décision de celui qui joue."""
    position = build({1: 2, 2: 2, 3: 2, 8: 4, 13: 5},
                     {6: 5, 8: 3, 13: 4, 20: 2}, bar=(0, 1))
    assert classify(position, WHITE) == "blitz"
    assert classify(position, BLACK) != "blitz"


def test_default_point_of_view_is_the_player_to_move():
    position = build({1: 2, 2: 2, 3: 2, 8: 4, 13: 5},
                     {6: 5, 8: 3, 13: 4, 20: 2}, turn=BLACK, bar=(0, 1))
    assert classify(position) == classify(position, BLACK)


def test_finished_game_is_over():
    position = build({}, {6: 5, 8: 3, 13: 5, 24: 2}, off=(15, 0))
    assert classify(position) == "over"


def test_every_class_of_the_published_list_is_reached_here():
    """La liste publiée n'a pas de classe morte : chacune est produite par un
    cas de ce fichier."""
    reached = {
        "over", "bearoff_noncontact", "bearoff_contact", "race",
        "race_contact", "backgame", "prime_vs_prime", "blitz", "crashed",
        "holding", "contact",
    }
    assert reached == set(CLASSES)


@pytest.mark.parametrize("point", range(1, 25))
def test_the_two_frames_are_mirror_images(point):
    """Le repère de chaque joueur : le point `n` de l'un est le `25 - n` de
    l'autre. La sentinelle la moins chère du projet, appliquée ici."""
    position = build({point: 2}, {}, off=(13, 15))
    mirror = build({}, {25 - point: 2}, off=(15, 13))
    assert position.points[point - 1] == 2
    assert mirror.points[point - 1] == -2

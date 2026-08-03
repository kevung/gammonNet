"""T04 — le harnais de round-robin.

Aucune force n'est mesurée ici. On vérifie que **l'instrument est droit** : qu'il
est antisymétrique, qu'il rend zéro quand il doit rendre zéro, qu'il redonne le
même résultat à graine égale, et qu'il n'affiche jamais un chiffre nu.

Un instrument faux ne se voit pas dans ses résultats — il donne des ppg
parfaitement plausibles. D'où des contrôles qui portent sur ses **propriétés**,
et non sur ses valeurs.
"""

from __future__ import annotations

import random

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet.arena import (
    BACKGAMMON,
    GAMMON,
    NORMAL,
    FirstPlayEngine,
    OracleEngine,
    RandomEngine,
    bootstrap_ci,
    derive_seed,
    game_value,
    opening_roll,
    pair_key,
    play_duplicate,
    play_pair,
    round_robin,
)

SEED = 20260803


# ── Le compte des points ─────────────────────────────────────────────


def _finished(white_off: int, black_off: int, black_points=(), black_bar=0) -> Position:
    points = [0] * 24
    for i in black_points:
        points[i] = -1
    remaining = 15 - black_off - len(black_points) - black_bar
    if remaining:
        points[12] = -remaining
    return Position(tuple(points), (0, black_bar), (white_off, black_off), BLACK)


def test_a_plain_win_is_one_point():
    assert game_value(_finished(15, 3), WHITE) == NORMAL


def test_a_gammon_is_two_points():
    """Le perdant n'a rien sorti, et n'est ni sur la barre ni dans le jan gagnant."""
    assert game_value(_finished(15, 0, black_points=(12, 13)), WHITE) == GAMMON


def test_a_backgammon_is_three_points_from_the_bar():
    assert game_value(_finished(15, 0, black_bar=1), WHITE) == BACKGAMMON


def test_a_backgammon_is_three_points_from_the_winners_home():
    """Un pion du perdant dans le jan intérieur du GAGNANT — indices 0-5 pour Blanc."""
    assert game_value(_finished(15, 0, black_points=(3,)), WHITE) == BACKGAMMON
    # Le même pion ailleurs n'est qu'un gammon.
    assert game_value(_finished(15, 0, black_points=(9,)), WHITE) == GAMMON


def test_backgammon_home_board_is_the_winners_not_a_fixed_end():
    """Pour Noir gagnant, le jan qui compte est 18-23, pas 0-5.

    Une constante figée passerait le test précédent et serait fausse d'un côté.
    """
    points = [0] * 24
    points[20] = 1      # un pion blanc dans le jan intérieur de Noir
    points[12] = 14
    won_by_black = Position(tuple(points), (0, 0), (0, 15), WHITE)

    assert game_value(won_by_black, BLACK) == BACKGAMMON

    points = [0] * 24
    points[10] = 1      # le même pion hors du jan de Noir
    points[12] = 14
    gammon = Position(tuple(points), (0, 0), (0, 15), WHITE)
    assert game_value(gammon, BLACK) == GAMMON


# ── Le jet d'ouverture ───────────────────────────────────────────────


def test_opening_roll_never_returns_doubles_and_the_higher_die_starts():
    for seed in range(200):
        first, d1, d2 = opening_roll(random.Random(seed))
        assert d1 != d2, "un double a été rendu comme jet d'ouverture"
        assert first == (WHITE if d1 > d2 else BLACK)


# ── Le contrôle nul ──────────────────────────────────────────────────


def test_an_engine_against_itself_scores_exactly_zero():
    """Le test le plus révélateur du harnais.

    Avec des dés dupliqués et un hasard attaché au SIÈGE et non au moteur, les
    deux parties d'une paire sont la même partie jouée deux fois, sièges
    échangés. Le total doit être **exactement** zéro, pas zéro à l'intervalle
    de confiance près. Un écart signale un harnais faux, pas de la variance.
    """
    engine = RandomEngine(name="random")

    for index in range(200):
        points, stalled = play_duplicate(engine, engine, SEED, index)
        assert points == 0, f"paire {index} : {points} points au lieu de 0"
        assert not stalled


def test_the_null_control_survives_the_full_pair_summary():
    engine = RandomEngine(name="random")
    result = play_pair(engine, engine, pairs=300, base_seed=SEED, bootstrap=2000)

    assert result.ppg == 0.0
    low, high = result.ci
    assert low <= 0.0 <= high, f"zéro hors de l'intervalle {result.ci}"
    assert result.stalled == 0


# ── L'antisymétrie ───────────────────────────────────────────────────


def test_pair_key_is_order_independent():
    assert pair_key("a", "b") == pair_key("b", "a")
    assert derive_seed(1, pair_key("a", "b"), 7) == derive_seed(1, pair_key("b", "a"), 7)


def test_two_behaviourally_identical_engines_cancel_exactly():
    """Deux `RandomEngine` de noms différents ne sont pas deux joueurs différents.

    Les dés dupliqués et le hasard attaché au siège les annulent **exactement**.
    C'est une propriété du schéma, pas un accident — et elle rend visible qu'un
    « écart » entre deux moteurs identiques ne serait que du bruit mal maîtrisé.
    """
    result = play_pair(
        RandomEngine(name="alpha"), RandomEngine(name="beta"),
        pairs=200, base_seed=SEED, bootstrap=500,
    )
    assert result.ppg == 0.0
    assert result.ci == (0.0, 0.0)


def test_antisymmetry_between_two_different_engines():
    """`ppg[A][B] == -ppg[B][A]`, les deux sens étant réellement joués.

    Aucune cellule n'est obtenue en niant l'autre : le test vérifie que
    l'appariement et la graine sont symétriques, pas une identité arithmétique
    qu'on se serait imposée.
    """
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    forward = play_pair(a, b, pairs=200, base_seed=SEED, bootstrap=500)
    backward = play_pair(b, a, pairs=200, base_seed=SEED, bootstrap=500)

    assert forward.ppg == pytest.approx(-backward.ppg, abs=1e-12), (
        f"{forward.ppg} vs {backward.ppg}"
    )
    assert forward.win_rate == pytest.approx(1.0 - backward.win_rate, abs=1e-12)


# ── La reproductibilité ──────────────────────────────────────────────


def test_two_runs_with_the_same_seed_are_identical():
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    first = play_pair(a, b, pairs=150, base_seed=SEED, bootstrap=500)
    second = play_pair(a, b, pairs=150, base_seed=SEED, bootstrap=500)

    assert first == second, "deux exécutions à graine identique diffèrent"


def test_a_different_seed_gives_a_different_result():
    """Sinon la graine serait ignorée, et la reproductibilité serait vide de sens."""
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    assert (
        play_pair(a, b, pairs=150, base_seed=1, bootstrap=500).ppg
        != play_pair(a, b, pairs=150, base_seed=2, bootstrap=500).ppg
    )


def test_parallel_workers_change_nothing():
    """Le résultat ne doit pas dépendre de l'ordonnancement.

    La bibliothèque de l'oracle a un état global : la parallélisation se fait par
    **processus**. Ce test vérifie qu'elle ne déplace rien.
    """
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    serial = play_pair(a, b, pairs=120, base_seed=SEED, workers=1, bootstrap=500)
    parallel = play_pair(a, b, pairs=120, base_seed=SEED, workers=4, bootstrap=500)

    assert serial == parallel
    # Sans cela le test comparerait 0 à 0 : deux moteurs identiques s'annulent,
    # et l'ordonnancement n'aurait rien à déplacer.
    assert serial.ppg != 0.0


# ── L'intervalle de confiance ────────────────────────────────────────


def test_confidence_interval_is_deterministic_and_brackets_the_mean():
    samples = [random.Random(i).gauss(0.05, 1.0) for i in range(500)]

    first = bootstrap_ci(samples, resamples=2000, seed=SEED)
    second = bootstrap_ci(samples, resamples=2000, seed=SEED)

    assert first == second
    mean = sum(samples) / len(samples)
    assert first[0] <= mean <= first[1]


def test_more_games_tighten_the_interval():
    """Un intervalle qui ne se resserre pas avec le volume ne mesure rien."""
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    small = play_pair(a, b, pairs=60, base_seed=SEED, bootstrap=2000)
    large = play_pair(a, b, pairs=600, base_seed=SEED, bootstrap=2000)

    def width(result):
        return result.ci[1] - result.ci[0]

    assert width(large) < width(small), (
        f"600 paires : {width(large):.4f} ; 60 paires : {width(small):.4f}"
    )


def test_a_result_never_prints_a_bare_number():
    """`BRIEF.md` §5 : l'intervalle fait partie du chiffre, pas de la décoration."""
    a = FirstPlayEngine(name="first-play")
    b = RandomEngine(name="random")

    rendered = str(play_pair(a, b, pairs=50, base_seed=SEED, bootstrap=500))
    assert "ppg" in rendered and "[" in rendered and ";" in rendered


# ── La matrice ───────────────────────────────────────────────────────


def test_round_robin_matrix_is_antisymmetric_everywhere():
    engines = [RandomEngine(name="random"), FirstPlayEngine(name="first-play"),
               RandomEngine(name="chaos")]
    matrix = round_robin(engines, pairs=80, base_seed=SEED, bootstrap=500)

    for a in matrix.names:
        assert matrix.ppg(a, a) == 0.0
        for b in matrix.names:
            assert matrix.ppg(a, b) == pytest.approx(-matrix.ppg(b, a), abs=1e-12)

    assert "ppg" in matrix.report()


# ── L'oracle comme adversaire ────────────────────────────────────────


@pytest.mark.parametrize("ply", [0])
def test_the_oracle_crushes_a_random_player(ply):
    """Un contrôle de bon sens : si ce signe s'inversait, tout serait faux.

    Ce n'est pas une mesure de force — c'est la vérification que le harnais sait
    reconnaître un vainqueur, sur le seul écart si grand qu'aucun volume n'est
    nécessaire pour le voir.
    """
    pytest.importorskip("gnubg_nn")

    oracle = OracleEngine(ply=ply)
    chaos = RandomEngine(name="random")

    result = play_pair(oracle, chaos, pairs=25, base_seed=SEED, bootstrap=500)

    assert result.ppg > 1.0, f"l'oracle ne domine pas le hasard : {result}"
    assert result.ci[0] > 0.0, f"intervalle non concluant : {result.ci}"

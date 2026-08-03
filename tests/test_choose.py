"""Le sélecteur de coup 0-ply en C, et le contrôle qui le rend digne de confiance.

`gn_best_play_0ply` existe parce que T05 a mesuré la liaison Python à un facteur
dix. Une version rapide n'a d'intérêt que si elle choisit **exactement** les mêmes
coups que la version lisible : d'où un test qui les confronte, position par
position, plutôt qu'un profilage qui dirait seulement qu'elle va vite.

Le signe est le piège du fichier. `play.result` a déjà passé le trait, donc les
cinq probabilités décrivent l'ADVERSAIRE : le coup à garder **minimise**
l'évaluation de son propre résultat. Inversé, on obtient un moteur qui joue mal
exprès et n'en dit rien — un round-robin afficherait simplement un grand nombre
négatif, qui ressemble à un modèle faible et non à un bug.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet.arena import NetworkEngine, RandomEngine, game_value, play_pair

MODEL = Path(__file__).resolve().parent.parent / "models" / "cubeless_prob5_512_512_256_128.bin"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(), reason=f"{MODEL.name} absent — lancer `make model`"
)

SEED = 20260803


@pytest.fixture(scope="module")
def engine() -> NetworkEngine:
    return NetworkEngine()


def walk(count: int, seed: int = SEED) -> list[tuple[Position, int, int]]:
    """Positions et jets tirés d'une marche aléatoire, à graine fixe."""
    rng = random.Random(seed)
    out = []
    position = Position.initial()
    while len(out) < count:
        if position.is_over():
            position = Position.initial()
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        out.append((position, d1, d2))
        plays = position.legal_plays(d1, d2)
        position = rng.choice(plays).result if plays else position.swapped_turn()
    return out


def test_the_c_chooser_agrees_with_the_readable_one(engine):
    """Sur 800 décisions, le chemin C et le chemin Python retiennent le même coup."""
    rng = random.Random(1)
    checked = 0

    for position, d1, d2 in walk(800):
        fast = engine.choose(position, d1, d2, rng)
        slow = engine.choose_via_python(position, d1, d2, rng)

        if slow is None:
            assert fast is None
            continue

        assert fast is not None
        assert fast.result.points == slow.result.points, (
            f"{position!r} dés {d1}-{d2} : le chemin C retient un autre coup"
        )
        assert fast.result.bar == slow.result.bar
        assert fast.result.off == slow.result.off
        checked += 1

    assert checked > 500, f"seulement {checked} décisions réelles — le test ne teste rien"


def test_the_chooser_prefers_a_winning_play_when_one_exists(engine):
    """Un coup qui gagne doit être joué. Le contrôle de signe le plus direct.

    Blanc a un seul pion, sur son as, et quatorze déjà sortis : tout dé le sort
    et gagne. Un sélecteur au signe inversé choisirait l'autre coup.
    """
    points = [0] * 24
    points[0] = 1
    points[23] = -15
    position = Position(tuple(points), (0, 0), (14, 0), WHITE)
    assert position.is_valid()

    rng = random.Random(0)
    play = engine.choose(position, 6, 5, rng)

    assert play is not None
    assert play.result.is_over(), f"le coup gagnant n'a pas été joué : {play}"
    assert play.result.winner() == WHITE


def test_the_chooser_beats_a_random_player_by_a_wide_margin(engine):
    """Si ce signe s'inversait, tout le reste serait faux — et silencieusement."""
    result = play_pair(engine, RandomEngine(name="random"), pairs=40,
                       base_seed=SEED, bootstrap=500)

    assert result.ppg > 1.5, f"le réseau ne domine pas le hasard : {result}"
    assert result.ci[0] > 0.0


def test_the_chooser_is_deterministic(engine):
    """Aucun hasard n'entre dans un choix 0-ply : deux appels donnent le même coup."""
    rng = random.Random(0)
    for position, d1, d2 in walk(200, seed=7):
        first = engine.choose(position, d1, d2, rng)
        second = engine.choose(position, d1, d2, rng)
        if first is None:
            assert second is None
        else:
            assert first.result.points == second.result.points


def test_a_finished_position_is_scored_and_not_evaluated(engine):
    """Une position terminée n'a pas de suite à estimer : elle vaut son enjeu.

    Le sélecteur C attribue exactement 1, 2 ou 3 points plutôt que d'interroger
    le réseau sur une position qu'il n'a jamais eu à juger.
    """
    # Blanc sort son dernier pion ; Noir n'a rien sorti et n'est pas backgammoné.
    points = [0] * 24
    points[0] = 1
    points[12] = -15
    position = Position(tuple(points), (0, 0), (14, 0), WHITE)

    rng = random.Random(0)
    play = engine.choose(position, 1, 2, rng)

    assert play is not None and play.result.is_over()
    assert game_value(play.result, WHITE) == 2, "gammon attendu"


def test_no_legal_play_is_reported_and_not_invented(engine):
    points = [0] * 24
    points[12], points[11], points[10] = 5, 5, 3
    for i in range(18, 24):
        points[i] = -2
    points[0] = -3
    blocked = Position(tuple(points), (2, 0), (0, 0), WHITE)

    assert blocked.is_valid()
    assert engine.choose(blocked, 3, 1, random.Random(0)) is None

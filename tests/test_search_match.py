"""La recherche valuée par la table d'équité de match.

`PLAN.md` avertit, à propos de T30 : au niveau intermédiaire d'une recherche
2-ply, **l'adversaire maximise son équité de match**, pas son équité cubeless.
À 4-away/2-away un coup gammonesque ne vaut pas ce qu'il vaut en money, et un
moteur qui l'ignore joue le mauvais coup avec une confiance intacte.

> **Aucun test money ne le dira jamais.** C'est pourquoi ce fichier existe
> séparément, et pourquoi son test central n'est pas « la valeur change » mais
> **« le coup change »** — la même leçon que T30 a apprise à ses dépens.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from gammonnet import BLACK, NUM_POINTS, WHITE, Position
from gammonnet.infer import Network
from gammonnet.met import MatchState
from gammonnet.search import ROLLS, SearchConfig, best_play, position_equity

ROOT = Path(__file__).resolve().parent.parent
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
SEED = 20260803


@pytest.fixture(scope="module")
def network() -> Network:
    if not MODEL_BIN.is_file():
        pytest.skip(f"{MODEL_BIN} absent — lancer `make model`")
    with Network.load(MODEL_BIN) as net:
        yield net


def build_corpus(size: int) -> list[Position]:
    rng = random.Random(SEED)
    positions: list[Position] = []
    while len(positions) < size:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(60):
            if position.is_over() or len(positions) >= size:
                break
            positions.append(position)
            plays = position.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            position = rng.choice(plays).result if plays else position.swapped_turn()
    return positions


CORPUS = build_corpus(40)


def mirror(position: Position) -> Position:
    return Position(
        points=tuple(-position.points[NUM_POINTS - 1 - j] for j in range(NUM_POINTS)),
        bar=(position.bar[BLACK], position.bar[WHITE]),
        off=(position.off[BLACK], position.off[WHITE]),
        turn=BLACK if position.turn == WHITE else WHITE,
    )


# ── LE test : la table doit changer des décisions ────────────────────


def test_the_match_score_changes_the_chosen_move(network):
    """À 2-away/2-away, la recherche doit choisir autrement qu'en money.

    C'est le contrôle décisif. Une recherche qui brancherait la table sans
    l'écouter rendrait exactement les mêmes coups qu'en money — plus lentement,
    et avec la certitude tranquille d'avoir tenu compte du score.

    2-away/2-away est le score où les gammons pèsent le plus : un gain simple
    ramène à 1-away, un gammon **emporte le match**.
    """
    money = SearchConfig(ply=0)
    gammon_score = SearchConfig(
        ply=0, use_match=True, match=MatchState(away_on_roll=2, away_opponent=2)
    )

    differences = 0
    decisions = 0
    for position in CORPUS:
        for d1, d2, _ in ROLLS:
            a = best_play(network, position, d1, d2, money)
            b = best_play(network, position, d1, d2, gammon_score)
            if a is None or b is None:
                continue
            decisions += 1
            if a.result != b.result:
                differences += 1

    assert decisions > 200
    assert differences > 0, (
        f"le score n'a changé aucun coup sur {decisions} décisions : la table "
        f"est branchée mais pas écoutée"
    )
    print(f"\n2-away/2-away contre money : {differences}/{decisions} coups "
          f"diffèrent ({100 * differences / decisions:.1f} %)")


def test_far_from_match_point_the_match_agrees_with_money(network):
    """Le contrôle inverse : loin du but, l'équité de match imite le money.

    Sans lui, le test précédent serait satisfait par une table de nombres au
    hasard — elle changerait des coups, elle aussi.
    """
    money = SearchConfig(ply=0)
    far = SearchConfig(
        ply=0, use_match=True, match=MatchState(away_on_roll=25, away_opponent=25)
    )

    differences = 0
    decisions = 0
    for position in CORPUS:
        for d1, d2, _ in ROLLS:
            a = best_play(network, position, d1, d2, money)
            b = best_play(network, position, d1, d2, far)
            if a is None or b is None:
                continue
            decisions += 1
            if a.result != b.result:
                differences += 1

    rate = differences / decisions
    assert rate < 0.05, (
        f"{rate * 100:.1f} % de désaccord à 25-away/25-away : l'équité de match "
        f"devrait y être quasi proportionnelle au money"
    )
    print(f"\n25-away/25-away contre money : {differences}/{decisions} "
          f"({100 * rate:.1f} %)")


# ── La bascule de l'état, qui est le piège silencieux ────────────────


def test_the_match_state_follows_the_player_not_the_colour(network):
    """Miroiter la position, **à score inchangé**, doit rendre la même valeur.

    `mirror` échange les couleurs et retourne le plateau : le joueur au trait y
    affronte exactement la même situation. Son score est donc **le même**, et
    l'équité aussi. C'est le test de miroir de T30, étendu à l'état de match :
    il vérifie que le score voyage avec le **joueur au trait** et non avec une
    couleur.

    Écrit d'abord avec le score inversé, il a échoué en rendant
    `+0,4573` contre `−0,4448` — presque exactement opposés. C'était la
    signature de l'erreur : le score inversé décrit le point de vue de
    l'adversaire, pas la même situation.
    """
    state = MatchState(away_on_roll=3, away_opponent=6)
    for ply in (0, 1):
        config = SearchConfig(ply=ply, use_match=True, match=state)
        for position in CORPUS[:10]:
            direct = position_equity(network, position, config)
            mirrored = position_equity(network, mirror(position), config)
            assert direct == pytest.approx(mirrored, abs=1e-9), (
                f"ply {ply} : {direct} contre {mirrored} — le score suit la couleur"
            )


def test_reversing_the_score_reverses_who_is_favoured(network):
    """Être plus près de l'arrivée vaut mieux, à position identique.

    Le contrôle qui manquait au test précédent : il vérifie que le score entre
    réellement dans le calcul, là où l'invariance par miroir vérifie qu'il y
    entre du bon côté.
    """
    ahead = SearchConfig(ply=0, use_match=True,
                         match=MatchState(away_on_roll=3, away_opponent=6))
    behind = SearchConfig(ply=0, use_match=True,
                          match=MatchState(away_on_roll=6, away_opponent=3))
    for position in CORPUS[:15]:
        assert position_equity(network, position, ahead) > \
               position_equity(network, position, behind), (
            f"mener 6-3 ne vaudrait pas mieux que le contraire sur {position}"
        )


def test_a_deeper_match_search_still_moves_the_equity(network):
    """La recherche cherche toujours quand elle est valuée par la table.

    Le contrôle de T30, rejoué en mode match : une équité figée d'un ply à
    l'autre signalerait que le branchement a cassé la récursion.
    """
    state = MatchState(away_on_roll=4, away_opponent=2)
    unchanged = 0
    for position in CORPUS[:10]:
        e0 = position_equity(network, position,
                             SearchConfig(ply=0, use_match=True, match=state))
        e1 = position_equity(network, position,
                             SearchConfig(ply=1, use_match=True, match=state))
        if abs(e1 - e0) < 1e-9:
            unchanged += 1
    assert unchanged == 0, f"{unchanged}/10 équités figées entre 0-ply et 1-ply"


# ── Bornes et refus ──────────────────────────────────────────────────


def test_match_equity_stays_in_range(network):
    """`2·MWC − 1` vit dans [−1, +1], à tout score et à toute profondeur."""
    for away_a, away_b in [(1, 1), (2, 5), (7, 3), (25, 25), (1, 25)]:
        config = SearchConfig(ply=0, use_match=True,
                              match=MatchState(away_a, away_b))
        for position in CORPUS[:15]:
            value = position_equity(network, position, config)
            assert -1.0 <= value <= 1.0, (
                f"{value} à {away_a}-away/{away_b}-away"
            )


def test_an_unrepresentable_score_is_refused_not_downgraded(network):
    """Au-delà de la table, la recherche ne retombe pas silencieusement en money.

    `gn_search_config_match` rend une configuration à `use_match` nul et `ply`
    remis à zéro. Une recherche qui aurait tranquillement basculé en money à un
    score qu'elle ne sait pas représenter serait fausse en match, et muette.
    """
    from gammonnet.search import match_config

    config = match_config(2, MatchState(away_on_roll=26, away_opponent=5))
    assert config.use_match is False
    assert config.ply == 0

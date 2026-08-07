"""T34 phase 2, étape 1 — la distribution propagée par la recherche (§8).

Les deux contrôles sont ceux que `docs/specs/t34-videau-spec.md` §8 prescrit,
à la lettre : au 0-ply la distribution est identique à l'existant ; à 1-ply,
la moyenne pondérée **à la main** sur les 21 jets d'une position figée
coïncide. S'y ajoute l'identité qui fonde tout l'édifice : les valuations
money et match étant linéaires dans la distribution, l'équité scalaire de la
recherche DOIT être la valuation de la distribution propagée, à toute
profondeur — sinon les deux marches ont divergé quelque part.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from gammonnet import Position
from gammonnet.infer import Evaluation, Network
from gammonnet.met import MatchState
from gammonnet.search import (
    ROLLS,
    SearchConfig,
    match_config,
    position_equity,
    position_probs,
)

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
    """Positions de contact, non terminales, à graine fixe — la même recette
    que `test_search.py`, la même graine, donc les mêmes positions."""
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


CORPUS = build_corpus(12)


def invert(evaluation: Evaluation) -> Evaluation:
    """La même distribution, vue de l'autre côté de la table — le miroir de
    `invert_probs` en C, réécrit ici plutôt qu'appelé : le contrôle « à la
    main » perdrait son indépendance s'il empruntait la brique qu'il teste."""
    return Evaluation(
        win=1.0 - evaluation.win,
        win_gammon=evaluation.lose_gammon,
        win_backgammon=evaluation.lose_backgammon,
        lose_gammon=evaluation.win_gammon,
        lose_backgammon=evaluation.win_backgammon,
    )


# ── Contrôle §8-1 : au 0-ply, identique à l'existant ──────────────────


def test_zero_ply_probs_are_the_evaluation(network):
    """`position_probs` au 0-ply passe par la même porte que la recherche
    (mêmes trois sources) ; sur des positions de contact hors table exacte,
    c'est exactement `Network.evaluate` — au bit près."""
    for position in CORPUS[:6]:
        direct = network.evaluate(position)
        searched = position_probs(network, position, SearchConfig(ply=0))
        assert searched == direct, position


# ── Contrôle §8-1 : à 1-ply, la moyenne à la main coïncide ────────────


def hand_average_at_one_ply(network: Network, position: Position) -> list[float]:
    """La récursion de §8 refaite en Python pur : pour chacun des 21 jets, le
    meilleur coup au 0-ply (par équité money négée, la même valuation que la
    recherche), puis la distribution de son résultat, inversée, pondérée par
    le poids du jet."""
    total = [0.0] * 5
    for d1, d2, weight in ROLLS:
        plays = position.legal_plays(d1, d2)
        if plays:
            evaluations = [network.evaluate(play.result) for play in plays]
            best = max(range(len(plays)),
                       key=lambda i: -evaluations[i].money_equity)
            mine = invert(evaluations[best])
        else:
            passed = position.swapped_turn()
            mine = invert(network.evaluate(passed))
        for i, component in enumerate(mine.as_tuple()):
            total[i] += weight * component
    return total


def test_one_ply_probs_match_the_hand_average(network):
    """Le contrôle prescrit par §8, sur deux positions figées du corpus."""
    for position in (CORPUS[0], CORPUS[7]):
        hand = hand_average_at_one_ply(network, position)
        searched = position_probs(network, position, SearchConfig(ply=1))
        for ours, theirs in zip(searched.as_tuple(), hand):
            assert ours == pytest.approx(theirs, abs=1e-5), (
                f"{position}: {searched.as_tuple()} vs {hand}"
            )


# ── L'identité valuation(distribution) == équité scalaire ─────────────


def test_money_equity_is_the_valuation_of_the_probs(network):
    """`gn_search_equity` et la valuation de `gn_search_probs` remontent le
    même arbre par deux marches ; la linéarité de l'équité money dans la
    distribution les force à coïncider, à 1-ply comme à 2-ply."""
    for ply, positions in ((1, CORPUS[:4]), (2, CORPUS[:2])):
        config = SearchConfig(ply=ply)
        for position in positions:
            equity = position_equity(network, position, config)
            probs = position_probs(network, position, config)
            assert probs.money_equity == pytest.approx(equity, abs=1e-5), (
                f"ply={ply}, {position}"
            )


def test_match_equity_is_the_valuation_of_the_probs(network):
    """La même identité, valuée par la table d'équité de match — le chemin
    qu'une décision de videau à profondeur empruntera réellement."""
    state = MatchState(away_on_roll=4, away_opponent=3, cube=1)
    config = match_config(1, state)
    assert config.use_match
    for position in CORPUS[:4]:
        equity = position_equity(network, position, config)
        probs = position_probs(network, position, config)
        assert state.equity(probs) == pytest.approx(equity, abs=1e-5), position

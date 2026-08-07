"""T34 phase 2, étape 2 — la valuation cubeful aux feuilles (§8).

Trois choses portent tout le montage, et chacune a ici le test qui la
démentirait :

* **l'antisymétrie** de `gn_cube_value` — sans elle, les négations de
  l'expectiminimax valueraient un pli sur deux avec le mauvais possesseur ;
* **l'exactitude des feuilles** dans le domaine de la table bilatérale — §8
  la revendique comme le levier de validation propre à ce dépôt ;
* **l'effet attendu n° 1 de §8** : le choix de coup devient sensible à la
  possession du videau. S'il ne l'était pas, `use_cube` vaudrait son coût en
  complexité pour rien, et le test le dirait.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest

from gammonnet import Position
from gammonnet.bearoff import TwoSidedBearoff, disable_shared, use_shared
from gammonnet.cube import CubeOwner, value as cube_value
from gammonnet.infer import Evaluation, Network
from gammonnet.met import MatchState
from gammonnet.rules import BLACK, NUM_POINTS, WHITE
from gammonnet.search import SearchConfig, best_play, position_equity

ROOT = Path(__file__).resolve().parent.parent
DATABASE = Path(os.environ.get(
    "GNUBG_TS_DATABASE",
    ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd",
))
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

SEED = 20260803

# Les efficacités mesurées (docs/mesures/t34-efficacite.json) ; les propriétés
# testées ici doivent tenir pour toute valeur dans (0, 1).
X = 0.6


@pytest.fixture(scope="module")
def network() -> Network:
    if not MODEL_BIN.is_file():
        pytest.skip(f"{MODEL_BIN} absent — lancer `make model`")
    with Network.load(MODEL_BIN) as net:
        yield net


def build_corpus(size: int) -> list[Position]:
    """La même recette et la même graine que `test_search.py`."""
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
    """Le miroir de perspective, réécrit ici — voir `test_search_probs.py`."""
    return Evaluation(
        win=1.0 - evaluation.win,
        win_gammon=evaluation.lose_gammon,
        win_backgammon=evaluation.lose_backgammon,
        lose_gammon=evaluation.win_gammon,
        lose_backgammon=evaluation.win_backgammon,
    )


MIRROR = {
    CubeOwner.CENTRED: CubeOwner.CENTRED,
    CubeOwner.OWNED: CubeOwner.OPPONENT,
    CubeOwner.OPPONENT: CubeOwner.OWNED,
}


# ── L'antisymétrie, money et match ────────────────────────────────────


DISTRIBUTIONS = [
    Evaluation(0.5, 0.0, 0.0, 0.0, 0.0),
    Evaluation(0.65, 0.25, 0.05, 0.08, 0.01),
    Evaluation(0.3, 0.1, 0.0, 0.3, 0.05),
    Evaluation(0.85, 0.55, 0.2, 0.02, 0.0),
]


def test_cube_value_is_antisymmetric_in_money():
    """`v(q, o) == -v(miroir(q), miroir(o))` — la propriété que gn_cube.h
    promet à la recherche, vérifiée sur les trois possesseurs et des
    distributions à gammons dissymétriques."""
    for q in DISTRIBUTIONS:
        for owner in CubeOwner:
            for x in (0.0, X, 1.0):
                mine = cube_value(q, owner, x)
                theirs = cube_value(invert(q), MIRROR[owner], x)
                assert mine == pytest.approx(-theirs, abs=1e-6), (
                    f"{q}, {owner}, x={x}: {mine} vs {-theirs}"
                )


def test_cube_value_is_antisymmetric_in_match():
    """La même, sur l'échelle 2·MWC − 1, l'état de match échangé avec la
    perspective — y compris à un score dissymétrique où le §9 fait vivre des
    chaînes de niveaux différentes des deux côtés."""
    for away_a, away_b in ((3, 5), (2, 4), (2, 2), (7, 2)):
        state = MatchState(away_on_roll=away_a, away_opponent=away_b, cube=1)
        swapped = MatchState(away_on_roll=away_b, away_opponent=away_a, cube=1)
        for q in DISTRIBUTIONS:
            for owner in CubeOwner:
                mine = cube_value(q, owner, X, state=state)
                theirs = cube_value(invert(q), MIRROR[owner], X, state=swapped)
                assert mine == pytest.approx(-theirs, abs=1e-6), (
                    f"{away_a}/{away_b}, {q}, {owner}: {mine} vs {-theirs}"
                )


# ── Les feuilles exactes dans le domaine de la table (money) ──────────


def random_bearoff(rng: random.Random, table: TwoSidedBearoff) -> Position:
    """Le tirage de `bench/exact_gap.py`, même philosophie : uniforme sur le
    nombre de pions, pas sur les positions."""
    while True:
        points = [0] * NUM_POINTS
        for player in (WHITE, BLACK):
            count = rng.randint(1, table.chequers)
            for _ in range(count):
                point = rng.randrange(table.points)
                if player == WHITE:
                    points[point] += 1
                else:
                    points[NUM_POINTS - 1 - point] -= 1
        white = sum(n for n in points if n > 0)
        black = -sum(n for n in points if n < 0)
        position = Position(points=tuple(points), bar=(0, 0),
                            off=(15 - white, 15 - black), turn=WHITE)
        if table.contains(position):
            return position


@pytest.mark.skipif(not DATABASE.exists(),
                    reason=f"base bilatérale absente : {DATABASE}")
def test_money_leaves_are_exact_in_the_table_domain(network):
    """Au 0-ply, `use_cube` sur une position du domaine rend EXACTEMENT
    l'équité cubeful stockée — lue, pas modélisée, pour chacun des trois
    possesseurs. C'est le levier de validation que §8 revendique."""
    rng = random.Random(SEED)
    table = TwoSidedBearoff(DATABASE)
    native = use_shared(DATABASE)
    try:
        for _ in range(20):
            position = random_bearoff(rng, table)
            exact = native.equities(position)
            expected = {CubeOwner.OWNED: exact.owned,
                        CubeOwner.CENTRED: exact.centered,
                        CubeOwner.OPPONENT: exact.opponent_owns}
            for owner, reference in expected.items():
                config = SearchConfig(ply=0, use_cube=True,
                                      cube_owner=int(owner), cube_x=X)
                searched = position_equity(network, position, config)
                assert searched == reference, (
                    f"{position}, {owner}: {searched} vs {reference}"
                )
    finally:
        disable_shared()
        table.close()


# ── Les propriétés d'ordre, à profondeur ──────────────────────────────


def test_owning_the_cube_is_worth_something_at_depth(network):
    """Possédé ≥ centré ≥ adverse, au 0-ply ET au 1-ply — le miroir de
    possession à chaque pli préserve l'ordre, ce qui casserait immédiatement
    si un pli sur deux valuait avec le mauvais possesseur."""
    for ply, positions in ((0, CORPUS[:4]), (1, CORPUS[:2])):
        for position in positions:
            values = {
                owner: position_equity(
                    network, position,
                    SearchConfig(ply=ply, use_cube=True,
                                 cube_owner=int(owner), cube_x=X))
                for owner in CubeOwner
            }
            assert values[CubeOwner.OWNED] >= values[CubeOwner.CENTRED] - 1e-9, (
                f"ply={ply}, {position}"
            )
            assert values[CubeOwner.CENTRED] >= values[CubeOwner.OPPONENT] - 1e-9, (
                f"ply={ply}, {position}"
            )


# ── L'effet n° 1 de §8 : le choix de coup sent le videau ─────────────


@pytest.mark.skipif(not DATABASE.exists(),
                    reason=f"base bilatérale absente : {DATABASE}")
def test_cube_ownership_changes_move_choices_where_leaves_are_exact(network):
    """Il existe des (position, jet) où le meilleur coup diffère entre « je
    possède » et « l'adversaire possède » — l'effet attendu n° 1 de §8,
    constaté dans le domaine de la table bilatérale, où les feuilles sont
    exactes et où les points de cash/prise saturent réellement les courbes.

    Pourquoi PAS sur des positions de contact au 0-ply : dans la région
    linéaire médiane, les courbes possédé et adverse du modèle §3 diffèrent
    d'une CONSTANTE (½ par unité de videau — se lit dans les formes du §2),
    donc l'ordre des coups n'y bouge jamais. Constaté sur 245 décisions de
    contact avant d'écrire ce test : zéro différence, par construction du
    modèle, pas par défaut du branchement. L'effet vit là où les rampes
    saturent — près du cash, près de la prise, et dans la table exacte. Le
    corpus versionné de l'étape 3 se construira là."""
    rng = random.Random(SEED)
    table = TwoSidedBearoff(DATABASE)
    use_shared(DATABASE)
    try:
        owned = SearchConfig(ply=0, use_cube=True,
                             cube_owner=int(CubeOwner.OWNED), cube_x=X)
        opponent = SearchConfig(ply=0, use_cube=True,
                                cube_owner=int(CubeOwner.OPPONENT), cube_x=X)
        differences = 0
        for _ in range(30):
            position = random_bearoff(rng, table)
            for d1 in range(1, 7):
                for d2 in range(d1, 7):
                    bold = best_play(network, position, d1, d2, owned)
                    safe = best_play(network, position, d1, d2, opponent)
                    if bold is None or safe is None:
                        continue
                    if bold.play.result != safe.play.result:
                        differences += 1
        assert differences > 0, (
            "la possession du videau n'a changé aucun choix de coup dans le "
            "domaine exact — l'effet attendu n° 1 de §8 est absent"
        )
    finally:
        disable_shared()
        table.close()


@pytest.mark.skipif(not DATABASE.exists(),
                    reason=f"base bilatérale absente : {DATABASE}")
def test_bold_safe_corpus_still_holds(network):
    """§8-3c : le corpus versionné (tools/build_bold_safe_corpus.py) rejoué —
    chaque entrée doit produire aujourd'hui les mêmes deux coups divergents
    qu'à sa génération. Un changement de poids, de modèle de videau ou de
    recherche qui ferait disparaître l'effet bold/safe échouerait ICI,
    visiblement, plutôt qu'en silence."""
    from gammonnet import codec
    from gammonnet.rules import WHITE

    corpus_file = ROOT / "tests" / "data" / "t34-bold-safe.json"
    payload = json.loads(corpus_file.read_text())
    entries = payload["entries"]
    assert entries, "corpus bold/safe vide — régénérer et comprendre pourquoi"

    use_shared(DATABASE)
    try:
        x = payload["cube_x"]
        owned = SearchConfig(ply=0, use_cube=True,
                             cube_owner=int(CubeOwner.OWNED), cube_x=x)
        opponent = SearchConfig(ply=0, use_cube=True,
                                cube_owner=int(CubeOwner.OPPONENT), cube_x=x)
        for entry in entries:
            position = codec.position_from_id(entry["position"], WHITE)
            bold = best_play(network, position, entry["d1"], entry["d2"], owned)
            safe = best_play(network, position, entry["d1"], entry["d2"], opponent)
            assert codec.position_id(bold.play.result) == entry["owned_result"], entry
            assert codec.position_id(safe.play.result) == entry["opponent_result"], entry
    finally:
        disable_shared()

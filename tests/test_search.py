"""T30 — la recherche expectiminimax, et les contrôles qui la démentiraient.

Le test le plus révélateur de toute la chaîne est ici, et `PLAN.md` le dit :
**une équité qui ne bouge pas quand on ajoute un ply signale une recherche
fausse.** Une recherche cassée ne plante pas — elle rend l'équité 0-ply, avec
vingt fois le temps de calcul et une confiance intacte.

Le second contrôle est plus rare et plus fort : notre 0-ply est confronté au
sélecteur `gn_best_play_0ply` de T04, écrit indépendamment sur l'autre machine.
Deux lectures de la même règle de signe, sur deux pistes, doivent coïncider.
"""

from __future__ import annotations

import ctypes
import random
from pathlib import Path

import pytest

from gammonnet import BLACK, NUM_POINTS, WHITE, Position
from gammonnet.infer import Network
from gammonnet.rules import _LIB, _CPlay, _CPosition
from gammonnet.search import (
    ROLLS,
    SearchConfig,
    best_play,
    evaluations,
    position_equity,
    reset_evaluations,
    search_plays,
    terminal_equity,
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


def mirror(position: Position) -> Position:
    """Échange les couleurs et retourne le plateau. Même définition qu'en T02."""
    return Position(
        points=tuple(-position.points[NUM_POINTS - 1 - j] for j in range(NUM_POINTS)),
        bar=(position.bar[BLACK], position.bar[WHITE]),
        off=(position.off[BLACK], position.off[WHITE]),
        turn=BLACK if position.turn == WHITE else WHITE,
    )


def build_corpus(size: int) -> list[Position]:
    """Positions de contact, non terminales, à graine fixe."""
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


CORPUS = build_corpus(60)


# ── La pondération des dés ───────────────────────────────────────────


def test_dice_weights_sum_to_exactly_one():
    """6 × 1/36 + 15 × 2/36 = 1, sans tolérance.

    Critère de `PLAN.md`. Une pondération fausse ne fait rien planter : elle
    biaise silencieusement chaque équité de la recherche.
    """
    assert len(ROLLS) == 21
    doubles = [r for r in ROLLS if r[0] == r[1]]
    assert len(doubles) == 6

    from fractions import Fraction

    exact = sum(
        Fraction(1, 36) if a == b else Fraction(2, 36) for a, b, _ in ROLLS
    )
    assert exact == 1, f"la somme des poids vaut {exact}, pas 1"
    assert sum(w for _, _, w in ROLLS) == pytest.approx(1.0, abs=1e-12)


def test_rolls_are_the_distinct_ones():
    """21 jets distincts, pas 36 ordonnés : (1,2) et (2,1) sont le même jet."""
    assert len({(min(a, b), max(a, b)) for a, b, _ in ROLLS} ) == 21


# ── Le contrôle croisé avec le sélecteur indépendant de T04 ──────────


def test_zero_ply_agrees_with_the_independent_chooser(network):
    """Notre 0-ply choisit ce que `gn_best_play_0ply` choisit.

    Ce sélecteur vient de T04, écrit sur l'autre machine sans connaissance de
    cette recherche. Les deux appliquent la même règle de signe — l'équité d'un
    coup est l'**opposée** de l'évaluation de son résultat — et s'ils
    divergeaient, l'un des deux jouerait le meilleur coup de son adversaire avec
    aplomb, sans rien signaler.
    """
    _LIB.gn_best_play_0ply.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_CPosition),
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CPlay),
    ]
    _LIB.gn_best_play_0ply.restype = ctypes.c_int

    compared = 0
    for position in CORPUS:
        for d1, d2, _ in ROLLS:
            ours = best_play(network, position, d1, d2, SearchConfig(ply=0))

            reference = _CPlay()
            status = _LIB.gn_best_play_0ply(
                network._handle, ctypes.byref(position._to_c()), d1, d2,
                ctypes.byref(reference),
            )

            if status == 0:
                assert ours is None, "un coup trouvé là où le sélecteur n'en voit aucun"
                continue

            assert status == 1, f"sélecteur en erreur sur {position}"
            assert ours is not None, "aucun coup là où le sélecteur en trouve un"
            assert ours.result == Position._from_c(reference.result), (
                f"désaccord 0-ply sur {position} avec {d1}{d2}"
            )
            compared += 1

    assert compared > 1000, f"seulement {compared} comparaisons — corpus trop maigre"


# ── LE contrôle : l'équité doit bouger avec la profondeur ────────────


def test_equity_moves_when_a_ply_is_added(network):
    """Une équité figée d'un ply à l'autre signale une recherche fausse.

    Le contrôle le moins cher et le plus révélateur de toute la chaîne, et
    `PLAN.md` demande de le traiter comme bloquant. Une recherche cassée ne
    plante pas : elle rend patiemment l'équité 0-ply, vingt fois plus lentement.
    """
    unchanged = 0
    total = 0
    biggest = 0.0

    for position in CORPUS[:20]:
        e0 = position_equity(network, position, SearchConfig(ply=0))
        e1 = position_equity(network, position, SearchConfig(ply=1))
        total += 1
        delta = abs(e1 - e0)
        biggest = max(biggest, delta)
        if delta < 1e-9:
            unchanged += 1

    assert unchanged == 0, (
        f"{unchanged}/{total} positions ont la même équité en 0-ply et en 1-ply : "
        f"la recherche ne cherche pas"
    )
    print(f"\nécart 0-ply → 1-ply : jusqu'à {biggest:.4f} d'équité")


def test_deeper_search_changes_the_chosen_move_sometimes(network):
    """Ajouter un ply doit parfois changer le coup, pas seulement son équité.

    Une recherche qui déplacerait l'équité sans jamais changer un choix serait
    un thermomètre coûteux : elle ne ferait pas jouer mieux.
    """
    disagreements = 0
    decisions = 0

    for position in CORPUS[:15]:
        for d1, d2, _ in ROLLS[:8]:
            shallow = best_play(network, position, d1, d2, SearchConfig(ply=0))
            deep = best_play(network, position, d1, d2, SearchConfig(ply=1))
            if shallow is None or deep is None:
                continue
            decisions += 1
            if shallow.result != deep.result:
                disagreements += 1

    assert decisions > 50
    assert disagreements > 0, (
        "le 1-ply n'a jamais changé un choix du 0-ply sur "
        f"{decisions} décisions : la recherche n'influe pas sur le jeu"
    )
    print(f"\n1-ply change le coup sur {disagreements}/{decisions} décisions "
          f"({100 * disagreements / decisions:.1f} %)")


# ── La perspective, qui est le mode de défaillance silencieux ────────


def test_equity_is_invariant_under_mirroring(network):
    """`equity(p)` == `equity(miroir(p))`, à toute profondeur.

    L'encodage est en perspective : miroiter le plateau et échanger le trait
    décrit exactement la même situation pour le joueur au trait. Une inversion
    de perspective quelque part dans la recherche casse cette égalité — et ne
    casse rien d'autre de visible.
    """
    for ply in (0, 1):
        config = SearchConfig(ply=ply)
        for position in CORPUS[:12]:
            direct = position_equity(network, position, config)
            mirrored = position_equity(network, mirror(position), config)
            assert direct == pytest.approx(mirrored, abs=1e-6), (
                f"ply {ply} : {direct} vs {mirrored} sur {position}"
            )


def test_a_won_position_is_worth_more_than_a_lost_one(network):
    """Contrôle de signe grossier, qu'une inversion de perspective ferait tomber.

    Une position où l'on a sorti quatorze pions contre zéro vaut beaucoup ; la
    même vue de l'autre côté vaut son opposé. Aucune subtilité ici — c'est
    précisément l'intérêt : le test ne dépend d'aucun jugement de jeu.
    """
    winning = Position(
        points=tuple([1] + [0] * 22 + [-15]),
        bar=(0, 0), off=(14, 0), turn=WHITE,
    )
    assert winning.is_valid()

    equity = position_equity(network, winning, SearchConfig(ply=0))
    assert equity > 0.5, f"une position quasi gagnée vaut {equity}"

    flipped = position_equity(network, mirror(winning), SearchConfig(ply=0))
    assert flipped == pytest.approx(equity, abs=1e-6)


# ── Les positions terminales sont calculées, jamais évaluées ─────────


def test_terminal_equity_is_exact_and_signed_from_the_loser(network):
    """À une position terminale, `turn` désigne le perdant : l'équité est négative."""
    plain = Position(
        points=tuple([0] * 23 + [-1]), bar=(0, 0), off=(15, 14), turn=BLACK,
    )
    assert plain.is_over()
    assert terminal_equity(plain) == pytest.approx(-1.0)

    gammon = Position(
        points=tuple([0] * 18 + [-15]), bar=(0, 0), off=(15, 0), turn=BLACK,
    )
    assert gammon.is_over()
    assert terminal_equity(gammon) == pytest.approx(-2.0)

    backgammon = Position(
        points=tuple([-15] + [0] * 23), bar=(0, 0), off=(15, 0), turn=BLACK,
    )
    assert backgammon.is_over()
    assert terminal_equity(backgammon) == pytest.approx(-3.0), (
        "un pion du perdant dans le jan intérieur du gagnant vaut backgammon"
    )


def test_a_finished_game_is_never_handed_to_the_network(network):
    """Une partie finie est comptée, pas estimée.

    Le réseau n'a jamais vu de position terminale à l'entraînement : il
    répondrait, et il répondrait n'importe quoi de plausible. Le compteur
    d'évaluations le vérifie — il ne doit pas bouger.
    """
    finished = Position(
        points=tuple([0] * 23 + [-1]), bar=(0, 0), off=(15, 14), turn=BLACK,
    )
    reset_evaluations()
    value = position_equity(network, finished, SearchConfig(ply=2))
    assert evaluations() == 0, "le réseau a été interrogé sur une partie finie"
    assert value == pytest.approx(-1.0)


# ── Le coût, en évaluations — l'unité que T21 chronomètre ────────────


def test_evaluation_count_grows_with_depth(network):
    """Le compte d'évaluations par décision, mesuré et non supposé.

    C'est ce compte qui transforme la projection de T21 en mesure : le coût
    d'une décision est ce nombre multiplié par le coût d'une évaluation.
    """
    position = CORPUS[0]
    counts = {}
    for ply in (0, 1):
        reset_evaluations()
        best_play(network, position, 3, 1, SearchConfig(ply=ply))
        counts[ply] = evaluations()

    assert counts[0] > 0
    assert counts[1] > counts[0] * 5, (
        f"1-ply n'a coûté que {counts[1]} évaluations contre {counts[0]} en "
        f"0-ply : la recherche n'explore pas les 21 jets"
    )
    print(f"\névaluations par décision : 0-ply {counts[0]}, 1-ply {counts[1]}")


# ── Le filtre de coups (T31) ─────────────────────────────────────────


def test_filtering_reduces_cost(network):
    """Le filtre coûte moins cher. Son prix en qualité est mesuré ailleurs."""
    position = CORPUS[0]

    reset_evaluations()
    best_play(network, position, 3, 1, SearchConfig(ply=1))
    unfiltered = evaluations()

    reset_evaluations()
    best_play(network, position, 3, 1, SearchConfig(ply=1, filter=(0, 4)))
    filtered = evaluations()

    assert filtered < unfiltered, (
        f"le filtre n'a rien économisé : {filtered} contre {unfiltered}"
    )
    print(f"\nfiltre à 4 : {filtered} évaluations contre {unfiltered} "
          f"(×{unfiltered / filtered:.2f})")

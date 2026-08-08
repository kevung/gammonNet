"""T39 — l'arbitre, et le contrôle sans lequel il n'arbitre rien.

> *« Un arbitre qu'on n'a pas vérifié n'arbitre rien. »* — `PLAN.md`, T39

Le contrôle central est le **croisement contre la table exacte** : sur des
positions de bearoff, la table bilatérale donne l'équité sans rien estimer. Le
rollout doit la retrouver **dans son intervalle**. C'est la seule façon de savoir
qu'il est non biaisé, parce que partout ailleurs il n'y a rien à quoi le
comparer — c'est précisément pourquoi on l'écrit.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from gammonnet.infer import Network
from gammonnet.rollout import (
    RolloutConfig,
    rollout,
    rollout_candidates,
    rollout_difference,
)
from gammonnet.rules import BLACK, NUM_POINTS, WHITE, Position
from gammonnet.search import SearchConfig

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DATABASE = Path(os.environ.get(
    "GNUBG_TS_DATABASE", ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"))


@pytest.fixture(scope="module")
def network():
    return Network.load(MODEL)


def race(white_points, black_points, turn=WHITE):
    points = [0] * NUM_POINTS
    for i, n in enumerate(white_points):
        points[i] = n
    for j, n in enumerate(black_points):
        points[NUM_POINTS - 1 - j] = -n
    return Position(points=tuple(points), bar=(0, 0),
                    off=(15 - sum(white_points), 15 - sum(black_points)), turn=turn)


# ── Les dés communs, qui sont tout le mécanisme ──────────────────────


def test_the_same_seed_gives_the_same_answer(network):
    """Reproductible au bit près, sinon rien de ce qui suit ne tient."""
    position = race([2, 2, 1], [2, 1, 2])
    config = RolloutConfig(trials=200, truncate=6, seed=7)
    first = rollout(network, position, config)
    second = rollout(network, position, config)
    assert first.equity == second.equity
    assert first.standard_error == second.standard_error


def test_a_different_seed_gives_a_different_answer(network):
    """Sinon la graine ne sert à rien et l'intervalle est une décoration."""
    position = race([2, 2, 1], [2, 1, 2])
    a = rollout(network, position, RolloutConfig(trials=200, truncate=6, seed=1))
    b = rollout(network, position, RolloutConfig(trials=200, truncate=6, seed=2))
    assert a.equity != b.equity


def test_shared_dice_sharpen_the_difference(network):
    """LE contrôle du dispositif : la différence appariée est mieux déterminée.

    On compare l'erreur sur la différence, calculée sur les essais appariés, à
    celle qu'on obtiendrait en composant les deux marges. Si les dés partagés ne
    servaient à rien, les deux seraient égales.
    """
    position = race([3, 2, 1], [2, 2, 2])
    plays = position.legal_plays(3, 1)
    assert len(plays) >= 2

    config = RolloutConfig(trials=400, truncate=8, seed=99)
    a, b = plays[0].result, plays[1].result

    _, paired_error = rollout_difference(network, a, b, config)
    _, errors = rollout_candidates(network, [a, b], config)
    naive_error = (errors[0] ** 2 + errors[1] ** 2) ** 0.5

    assert paired_error < naive_error, (
        f"apparié {paired_error:.5f} contre naïf {naive_error:.5f} — "
        "les dés communs n'ont rien apporté"
    )


# ── Le contrôle de non-biais ────────────────────────────────────────


@pytest.mark.skipif(not DATABASE.exists(),
                    reason=f"base bilatérale absente : {DATABASE}")
def test_finds_the_exact_answer_within_its_interval(network):
    """Sur des positions où la table sait, le rollout doit tomber juste.

    Le rollout est **non tronqué** ici : il joue les parties jusqu'au bout, donc
    il n'y a aucun biais d'horizon à excuser. S'il s'écartait de la table, ce
    serait le rollout qui aurait tort, et tout ce qu'il arbitrerait ensuite avec
    lui.
    """
    from gammonnet.bearoff import TwoSidedBearoff

    rng = random.Random(20260806)
    config = RolloutConfig(trials=2000, truncate=0, seed=4242,
                           policy=SearchConfig(ply=0))

    outside = 0
    examined = 0
    worst = 0.0

    with TwoSidedBearoff(DATABASE) as table:
        while examined < 8:
            white = [rng.randrange(3) for _ in range(4)]
            black = [rng.randrange(3) for _ in range(4)]
            if not sum(white) or not sum(black):
                continue
            position = race(white, black)
            if not table.contains(position):
                continue
            examined += 1

            exact = table.equity(position).cubeless
            result = rollout(network, position, config)
            assert result.stalled == 0

            # Trois écarts-types : à ce seuil, une position sur trois cents
            # sort par hasard, donc en sortir plusieurs fois sur huit dénonce
            # un biais et non la malchance.
            spread = abs(result.equity - exact)
            worst = max(worst, spread / max(result.standard_error, 1e-9))
            if spread > 3.0 * result.standard_error:
                outside += 1

    assert outside <= 1, (
        f"{outside}/8 positions hors de 3 écarts-types — le pire à "
        f"{worst:.1f} sigma. L'arbitre est biaisé."
    )


# ── Ce que le rollout refuse de faire ───────────────────────────────


def test_an_untruncated_rollout_reports_outcome_frequencies(network):
    position = race([1, 1], [1, 1])
    result = rollout(network, position,
                     RolloutConfig(trials=300, truncate=0, seed=5))
    win = result.frequencies[0]
    assert 0.0 <= win <= 1.0
    # Événements imbriqués, comme partout ailleurs dans ce dépôt.
    assert result.frequencies[1] <= win
    assert result.frequencies[2] <= result.frequencies[1]


def test_a_truncated_rollout_reports_no_frequencies(network):
    """Un rollout tronqué finit sur une évaluation, pas sur un résultat.

    Remplir les fréquences avec la fraction des essais qui ont fini quand même
    donnerait un objet qui ressemble à une distribution sans en être une.
    """
    position = race([3, 3, 2], [3, 2, 3])
    result = rollout(network, position,
                     RolloutConfig(trials=200, truncate=4, seed=5))
    assert all(value == 0.0 for value in result.frequencies)


def test_candidate_equities_are_seen_by_the_mover(network):
    """Le signe, encore — l'erreur qui transforme un moteur en son adversaire.

    Une position gagnée d'avance doit valoir POSITIF pour celui qui vient d'y
    entrer, alors que le rollout, lui, répond pour l'adversaire.
    """
    # Blanc a un pion sur l'as et joue ; Noir en a cinq à sortir.
    position = race([2], [5, 5, 5], turn=WHITE)
    plays = position.legal_plays(1, 2)
    assert plays

    equities, _ = rollout_candidates(
        network, [p.result for p in plays],
        RolloutConfig(trials=300, truncate=0, seed=3))
    assert max(equities) > 0.0, "un coup gagnant vaut positif pour celui qui le joue"


# ── Le videau vivant (T39 × T34) ─────────────────────────────────────

# Les trois efficacités mesurées (t34-efficacite.json), indexées par état :
# centré, possédé, adverse. Sans effet dans le domaine de la table — les
# décisions y sont exactes — mais le rollout les exige pour le hors-domaine.
X3 = (0.688, 0.566, 0.687)


def cubeful_config(owner: int, trials: int = 2000, seed: int = 4243,
                   truncate: int = 0) -> RolloutConfig:
    # `cube_defer_first` : la cible du contrôle est l'équité STOCKÉE, dont la
    # convention exclut l'option de double du tour courant — établi par sonde,
    # voir gn_rollout.h. Sans lui, un meneur encaisse au ply 0 et le rollout
    # vise une autre question que la table.
    policy = SearchConfig(ply=0, use_cube=True, cube_owner=owner, cube_x=0.6)
    return RolloutConfig(trials=trials, truncate=truncate, seed=seed,
                         policy=policy, use_cube=True, cube_owner=owner,
                         cube_x=X3, cube_defer_first=True)


def test_cubeful_same_seed_gives_the_same_answer(network):
    position = race([2, 2, 1], [2, 1, 2])
    first = rollout(network, position, cubeful_config(0, trials=200, seed=7))
    second = rollout(network, position, cubeful_config(0, trials=200, seed=7))
    assert first.equity == second.equity
    assert first.cashed == second.cashed
    assert first.average_cube == second.average_cube


def test_cubeless_rollout_reports_no_cube_stats(network):
    position = race([2, 2, 1], [2, 1, 2])
    result = rollout(network, position,
                     RolloutConfig(trials=100, truncate=6, seed=3))
    assert result.cashed == 0
    assert result.average_cube == 0.0


@pytest.mark.skipif(not DATABASE.exists(),
                    reason=f"base bilatérale absente : {DATABASE}")
def test_cubeful_rollout_matches_the_exact_cubeful_equity(network):
    """LE contrôle de non-biais cubeful : dans le domaine de la table, les
    verdicts de videau ET le jeu de pions du rollout sont exacts (table
    partagée installée), les parties vont au bout — le rollout doit donc
    retrouver l'équité cubeful STOCKÉE, pour chacun des trois états, dans son
    intervalle. C'est aussi le juge de la convention : si le verdict dérivé
    des équités stockées avait le mauvais timing de double, l'équité visée
    serait ratée ici, visiblement, et rien de cubeful ne serait arbitrable.
    """
    from gammonnet.bearoff import NativeBearoff, disable_shared, use_shared

    rng = random.Random(20260806)
    native = NativeBearoff(DATABASE)
    use_shared(DATABASE)
    try:
        outside = 0
        checks = 0
        cashed_total = 0
        worst = 0.0
        positions = []
        while len(positions) < 6:
            white = [rng.randrange(3) for _ in range(4)]
            black = [rng.randrange(3) for _ in range(4)]
            if not sum(white) or not sum(black):
                continue
            position = race(white, black)
            if native.contains(position):
                positions.append(position)

        for position in positions:
            exact = native.equities(position)
            reference = {0: exact.centered, 1: exact.owned,
                         2: exact.opponent_owns}
            for owner, target in reference.items():
                result = rollout(network, position,
                                 cubeful_config(owner, trials=2000, seed=4243))
                assert result.stalled == 0
                cashed_total += result.cashed
                spread = abs(result.equity - target)
                error = max(result.standard_error, 1e-9)
                worst = max(worst, spread / error)
                checks += 1
                if spread > 3.0 * error:
                    outside += 1

        assert cashed_total > 0, (
            "aucun essai encaissé sur un passe : le videau n'a pas vécu"
        )
        assert outside <= 1, (
            f"{outside}/{checks} contrôles hors de 3 écarts-types — le pire "
            f"à {worst:.1f} sigma. L'arbitre cubeful est biaisé, ou la "
            f"convention de la table n'est pas celle du verdict dérivé."
        )
    finally:
        disable_shared()
        native.close()

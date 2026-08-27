"""T70 — `rollout_candidates_paired` : l'arbitrage de k candidats d'un coup.

Le pari de la fiche T70 est qu'un arbitrage payé **une fois** peut noter tout
moteur futur. Cela ne tient que si l'appariement de k candidats donne exactement
ce que l'appariement de deux donnait — et que l'erreur rendue est bien celle de
la différence, pas une erreur marginale déguisée.

Le contrôle central est donc un **croisement contre `rollout_difference`** : à
graine et essais égaux, les deux routines lisent les mêmes dés et doivent rendre
le même nombre. Un écart, ici, signifierait que la généralisation a cassé la
corrélation qui fait tout l'intérêt du dispositif — et rien ne planterait.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gammonnet.infer import Network
from gammonnet.rollout import (
    MAX_CANDIDATES,
    RolloutConfig,
    rollout_candidates,
    rollout_candidates_paired,
    rollout_difference,
)
from gammonnet.rules import Position
from gammonnet.search import SearchConfig, search_plays

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"


@pytest.fixture(scope="module")
def network():
    return Network.load(MODEL)


@pytest.fixture(scope="module")
def candidates(network):
    """Quatre suites plausibles d'une même décision d'ouverture."""
    ranked = search_plays(network, Position.initial(), 3, 1, SearchConfig(ply=0))
    return [entry.play.result for entry in ranked[:4]]


def config(**kwargs):
    base = dict(trials=216, truncate=7, seed=4242, policy=SearchConfig(ply=0))
    base.update(kwargs)
    return RolloutConfig(**base)


def test_it_agrees_with_rollout_difference(network, candidates):
    """Le croisement qui fait foi : mêmes dés, mêmes essais, même différence.

    La tolérance est celle du flottant, pas une marge statistique — les deux
    routines parcourent la MÊME suite de dés et somment les mêmes termes.
    """
    settings = config()
    _eq, differences, _err, trials = rollout_candidates_paired(
        network, candidates, settings, pivot=0)
    for index in range(1, len(candidates)):
        expected, _se = rollout_difference(network, candidates[index],
                                           candidates[0], settings)
        assert differences[index] == pytest.approx(expected, abs=1e-9), (
            f"candidat {index} : apparié {differences[index]} "
            f"contre différence {expected}")
    assert trials == 216


def test_the_error_is_the_one_on_the_difference(network, candidates):
    """L'erreur rendue est celle de la différence — le croisement le prouve."""
    settings = config()
    _eq, _diff, errors, _n = rollout_candidates_paired(network, candidates,
                                                       settings, pivot=0)
    for index in range(1, len(candidates)):
        _d, paired_se = rollout_difference(network, candidates[index],
                                           candidates[0], settings)
        assert errors[index] == pytest.approx(paired_se, abs=1e-9)


def test_pairing_never_costs_more_than_independence(network, candidates):
    """Ce que les dés communs garantissent, et ce qu'ils ne garantissent pas.

    `Var(A−B) = Var(A) + Var(B) − 2·Cov(A, B)`. Les dés partagés ne peuvent
    qu'induire une covariance positive, donc l'erreur appariée reste sous
    `√2 × max(erreurs marginales)` : l'appariement ne nuit jamais.

    Il ne **gagne** pas toujours pour autant, et c'est mesuré ici plutôt
    qu'affirmé. Sur cette décision d'ouverture, les quatre suites divergent
    assez pour que la covariance soit faible et le gain nul — l'en-tête du C
    promet « far better determined », ce qui vaut pour deux coups voisins, pas
    pour quatre positions qui s'écartent. T70 doit donc chiffrer son gain
    d'appariement par classe de position, jamais le supposer.
    """
    settings = config()
    _eq, _diff, errors, _n = rollout_candidates_paired(network, candidates,
                                                       settings, pivot=0)
    _marginal_eq, marginal = rollout_candidates(network, candidates, settings)
    ceiling = 2 ** 0.5 * max(marginal)
    assert max(errors[1:]) <= ceiling, (
        "l'appariement a fait pire que l'indépendance — covariance négative, "
        "donc les dés ne sont pas réellement partagés")


def test_the_pivot_difference_is_identically_zero(network, candidates):
    _eq, differences, errors, _n = rollout_candidates_paired(
        network, candidates, config(), pivot=2)
    assert differences[2] == 0.0
    assert errors[2] == 0.0


def test_the_pivot_only_shifts_the_origin(network, candidates):
    """Changer de pivot translate les différences, il n'en change aucune.

    Ce que le registre de T70 enregistre est un classement, et un classement ne
    peut pas dépendre du candidat qu'on a mis en premier.
    """
    settings = config()
    _e0, from_zero, _r0, _n0 = rollout_candidates_paired(network, candidates,
                                                         settings, pivot=0)
    _e2, from_two, _r2, _n2 = rollout_candidates_paired(network, candidates,
                                                        settings, pivot=2)
    shift = from_zero[2] - from_two[2]
    for index in range(len(candidates)):
        assert from_zero[index] - from_two[index] == pytest.approx(shift, abs=1e-9)


def test_equities_match_the_unpaired_call(network, candidates):
    """Les équités elles-mêmes ne changent pas : c'est le même rollout."""
    settings = config()
    paired, _diff, _err, _n = rollout_candidates_paired(network, candidates,
                                                        settings, pivot=0)
    plain, _marginal = rollout_candidates(network, candidates, settings)
    for index in range(len(candidates)):
        assert paired[index] == pytest.approx(plain[index], abs=1e-9)


def test_variance_reduction_narrows_without_moving_the_answer(network, candidates):
    """La correction par la chance a une espérance nulle : elle resserre
    l'intervalle, elle ne déplace pas la réponse hors de cet intervalle."""
    plain = config(trials=648)
    reduced = config(trials=648, variance_reduction=True)
    _e1, d1, r1, _n1 = rollout_candidates_paired(network, candidates, plain, 0)
    _e2, d2, r2, _n2 = rollout_candidates_paired(network, candidates, reduced, 0)
    for index in range(1, len(candidates)):
        assert r2[index] < r1[index], "la réduction de variance devrait resserrer"
        spread = 1.96 * (r1[index] ** 2 + r2[index] ** 2) ** 0.5
        assert abs(d1[index] - d2[index]) <= spread, (
            f"candidat {index} : la correction a déplacé la réponse")


def test_target_se_stops_early_and_says_how_early(network, candidates):
    settings = config(trials=4096, target_se=0.05, min_trials=72)
    _eq, _diff, errors, trials = rollout_candidates_paired(network, candidates,
                                                           settings, 0)
    assert trials < 4096, "l'arrêt sur intervalle n'a pas eu lieu"
    assert trials % 36 == 0, "le contrôle d'intervalle se fait tous les 36 essais"
    assert max(errors[1:]) <= 0.05


def test_target_se_ignores_the_pivots_own_zero(network, candidates):
    """Le piège : le se du pivot vaut zéro dès le premier essai. S'il comptait,
    tout rollout à intervalle s'arrêterait aussitôt et rendrait du bruit."""
    settings = config(trials=4096, target_se=1e-9, min_trials=72)
    _eq, _diff, _errors, trials = rollout_candidates_paired(network, candidates,
                                                            settings, 0)
    assert trials == 4096, "l'arrêt s'est déclenché sur le zéro du pivot"


def test_too_many_candidates_is_refused(network, candidates):
    with pytest.raises(ValueError):
        rollout_candidates_paired(network, candidates * 3, config(), 0)


def test_a_pivot_outside_the_candidates_is_refused(network, candidates):
    with pytest.raises(ValueError):
        rollout_candidates_paired(network, candidates, config(),
                                  pivot=len(candidates))


def test_the_published_bound_matches_the_c_side(network, candidates):
    """`MAX_CANDIDATES` répète une constante du C : si elle divergeait, Python
    laisserait passer un appel que le C refuserait sans cause lisible."""
    header = (ROOT / "src" / "gn_rollout.h").read_text()
    assert f"#define GN_ROLLOUT_MAX_CANDIDATES {MAX_CANDIDATES}" in header

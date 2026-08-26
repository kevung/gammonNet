"""T3A branché — le réseau d'élagage dans la recherche, et ce qui doit rester vrai.

Le petit réseau (196→32→5, distillé du grand) classe tous les coups légaux ;
seuls les `prune_k` meilleurs sont montrés au grand. Ce fichier ne mesure pas
ce que ça rapporte — c'est le travail d'un banc, pas d'un test — il tient les
quatre propriétés sans lesquelles la mesure ne voudrait rien dire :

1. **Éteint par défaut.** Sans `prune_k`, la recherche rend exactement ce
   qu'elle rendait, bit pour bit. C'est ce qui permet de comparer.
2. **Un `k` assez large n'élague rien.** Si le petit réseau laisse passer plus
   de coups qu'il n'y en a de légaux, le résultat doit être identique à la
   recherche non élaguée — sinon le petit réseau ne fait pas que trier, il
   change autre chose, et il faut savoir quoi.
3. **Le cache n'est jamais pollué.** Une distribution du petit réseau écrite
   dans le cache d'évaluation serait servie comme celle du grand pour le reste
   du processus, à toutes les recherches suivantes, sans un signe. C'est le
   test le plus important du fichier.
4. **Le filtre reste respecté.** Élaguer en dessous de `filter[depth]`
   chercherait moins de candidats que l'appelant n'en a demandé, sans que rien
   ne le dise.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import evalcache  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    evaluations,
    prune_evaluations,
    reset_evaluations,
    search_plays,
)

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
needs_models = pytest.mark.skipif(
    not (MODEL.exists() and PRUNE.exists()), reason="modèles absents"
)


def corpus(count: int = 40, seed: int = 20260826) -> list[Position]:
    """Des positions de vraies parties, jamais la seule position initiale."""
    rng = random.Random(seed)
    positions: list[Position] = []
    position = Position.initial()
    while len(positions) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
            continue
        positions.append(position)
    return positions


def rolls(seed: int = 20260826, count: int = 40) -> list[tuple[int, int]]:
    rng = random.Random(seed ^ 0xD1CE)
    return [(rng.randint(1, 6), rng.randint(1, 6)) for _ in range(count)]


@pytest.fixture(scope="module")
def nets():
    return Network.load(MODEL), Network.load(PRUNE)


@needs_models
def test_off_by_default_is_bit_for_bit_the_old_search(nets):
    """Sans `prune_k`, rien ne bouge — ni les coups, ni les bits."""
    net, small = nets
    plain = SearchConfig(ply=0)
    # `prune_net` fourni mais `prune_k` nul : le mécanisme reste éteint.
    armed = SearchConfig(ply=0, prune_net=small, prune_k=0)

    for position, (d1, d2) in zip(corpus(), rolls()):
        a = search_plays(net, position, d1, d2, plain)
        b = search_plays(net, position, d1, d2, armed)
        assert len(a) == len(b)
        for x, y in zip(a, b):
            assert x.play.result == y.play.result
            assert x.equity == y.equity          # bit à bit, pas approx
            assert x.evaluation == y.evaluation


@needs_models
def test_a_k_wider_than_the_move_list_prunes_nothing(nets):
    """`k` au-delà du nombre de coups légaux : le petit réseau ne peut rien
    retrancher, donc le résultat doit être celui de la recherche nue."""
    net, small = nets
    plain = SearchConfig(ply=0)
    wide = SearchConfig(ply=0, prune_net=small, prune_k=4096)

    seen_wide = False
    for position, (d1, d2) in zip(corpus(), rolls()):
        a = search_plays(net, position, d1, d2, plain)
        b = search_plays(net, position, d1, d2, wide)
        if len(a) > 1:
            seen_wide = True
        assert [c.play.result for c in a] == [c.play.result for c in b]
        assert [c.equity for c in a] == [c.equity for c in b]
    assert seen_wide, "corpus trop pauvre pour que le test prouve quoi que ce soit"


@needs_models
def test_pruning_returns_at_most_k_candidates(nets):
    """Le contrat annoncé par `gn_search.h` : les survivants, et rien d'autre."""
    net, small = nets
    k = 3
    config = SearchConfig(ply=0, prune_net=small, prune_k=k)
    saw_truncation = False
    for position, (d1, d2) in zip(corpus(), rolls()):
        got = search_plays(net, position, d1, d2, config)
        plain = search_plays(net, position, d1, d2, SearchConfig(ply=0))
        assert len(got) <= max(k, 1)
        if len(plain) > k:
            saw_truncation = True
            assert len(got) == k
    assert saw_truncation


@needs_models
def test_the_small_network_never_enters_the_evaluation_cache(nets):
    """Le test qui compte.

    Une recherche élaguée voit des dizaines de positions avec le PETIT réseau.
    Si l'une d'elles finissait dans le cache, une recherche ultérieure la
    lirait comme une réponse du GRAND — définitivement, et sans un signe.
    On vérifie donc que tout ce que le cache rend après une recherche élaguée
    est exactement ce que le grand réseau répond lui-même.
    """
    net, small = nets
    was_on = evalcache.is_enabled()
    evalcache.enable(16)
    try:
        evalcache.clear(16)
        config = SearchConfig(ply=0, prune_net=small, prune_k=2)
        positions = corpus()
        for position, (d1, d2) in zip(positions, rolls()):
            search_plays(net, position, d1, d2, config)

        # Tout ce que le cache peut désormais servir doit être la réponse du
        # grand réseau. On interroge par le chemin de recherche non élagué,
        # qui lit le cache, et on compare au réseau appelé en direct.
        plain = SearchConfig(ply=0)
        checked = 0
        for position, (d1, d2) in zip(positions, rolls()):
            for candidate in search_plays(net, position, d1, d2, plain):
                if candidate.play.result.is_over():
                    continue
                direct = net.evaluate(candidate.play.result)
                assert candidate.evaluation == direct, (
                    "le cache a servi une distribution qui n'est pas celle du "
                    "grand réseau — le petit y a écrit"
                )
                checked += 1
        assert checked > 100
    finally:
        evalcache.disable()
        if was_on:
            evalcache.enable()


@needs_models
def test_pruning_never_searches_fewer_candidates_than_the_filter(nets):
    """`prune_k` sous le filtre est relevé au filtre, pas obéi."""
    net, small = nets
    # filtre 5 à la profondeur 1, élagage demandé à 2 : la recherche doit
    # quand même présenter 5 candidats au grand réseau.
    config = SearchConfig(ply=1, filter=(0, 5), prune_net=small, prune_k=2)
    saw = False
    for position, (d1, d2) in zip(corpus(12), rolls(count=12)):
        got = search_plays(net, position, d1, d2, config)
        plain = search_plays(net, position, d1, d2, SearchConfig(ply=1, filter=(0, 5)))
        if len(plain) >= 5:
            saw = True
            assert len(got) == 5
    assert saw


@needs_models
def test_the_two_counters_stay_separate(nets):
    """Un coût publié est en évaluations du GRAND réseau : les deux unités ne
    se mélangent pas, et l'élagage doit faire baisser la première."""
    net, small = nets
    position, (d1, d2) = corpus(1)[0], rolls(count=1)[0]
    was_on = evalcache.is_enabled()
    evalcache.disable()
    try:
        reset_evaluations()
        search_plays(net, position, d1, d2, SearchConfig(ply=1, filter=(0, 5)))
        big_plain, small_plain = evaluations(), prune_evaluations()
        assert small_plain == 0

        reset_evaluations()
        search_plays(net, position, d1, d2,
                     SearchConfig(ply=1, filter=(0, 5), prune_net=small, prune_k=5))
        big_pruned, small_pruned = evaluations(), prune_evaluations()

        assert small_pruned > 0
        assert big_pruned < big_plain
    finally:
        if was_on:
            evalcache.enable()

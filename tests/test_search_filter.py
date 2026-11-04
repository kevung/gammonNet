"""Le filtre de coups en triplet (accepte, extra, seuil) — ce qui doit rester vrai.

Ce fichier ne mesure pas ce que coûte un réglage : c'est le travail d'un banc
(`bench/measure_t70.py`), pas d'un test. Il tient les propriétés sans
lesquelles une mesure ne voudrait rien dire :

1. **Extra nul, seuil inopérant.** Avec `extra = 0`, le filtre est le simple
   compte d'avant le triplet, bit pour bit, quel que soit le seuil écrit. C'est
   ce qui garantit que le réglage par défaut n'a pas bougé.
2. **Les gardiens d'or.** Des équités figées en hexadécimal, produites par la
   recherche AVANT l'introduction du triplet, aux formes par compte qu'avaient
   alors les niveaux canoniques : le code actuel doit les rendre au bit près
   quand on lui redonne ces formes (mode de compatibilité, `extra = 0`). Le
   niveau `normal` porte désormais un triplet ; ce qu'il rend sur les mêmes
   positions est figé à part, et ce qui y diffère du compte est dit.
3. **La sémantique exacte.** À 1-ply, un candidat approfondi a une équité qui
   n'est plus celle de 0-ply ; le nombre de candidats approfondis doit être
   exactement `accepte` plus ceux des `extra` suivants qui restent à moins du
   seuil du meilleur, la première sortie de bande arrêtant la marche.
4. **Le réseau d'élagage ne passe pas sous le filtre.** Il laisse passer au
   moins `accepte + extra` candidats.
5. **Un triplet incohérent est refusé**, jamais rabattu.
"""

from __future__ import annotations

import ctypes
import random
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import _LIB, Position  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    _CSearchConfig,
    search_level,
    search_plays,
)

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
needs_models = pytest.mark.skipif(
    not (MODEL.exists() and PRUNE.exists()), reason="modèles absents"
)

_LIB.gn_search_set_filter.argtypes = [
    ctypes.POINTER(_CSearchConfig), ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_double,
]
_LIB.gn_search_set_filter.restype = ctypes.c_int


def corpus(count: int = 30, seed: int = 20261004) -> list[Position]:
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


def rolls(count: int = 30, seed: int = 20261004) -> list[tuple[int, int]]:
    rng = random.Random(seed + 1)
    return [(rng.randint(1, 6), rng.randint(1, 6)) for _ in range(count)]


@pytest.fixture(scope="module")
def nets():
    return Network.load(MODEL), Network.load(PRUNE)


def ranking(net, position, dice, config):
    return [(codec.position_id(c.play.result), c.equity)
            for c in search_plays(net, position, *dice, config)]


@needs_models
def test_extra_zero_never_reads_the_threshold(nets):
    net, prune = nets
    for position, dice in zip(corpus(12), rolls(12)):
        for base in (SearchConfig(ply=2, filter=(0, 1, 3)),
                     SearchConfig(ply=2, filter=(0, 1, 3), prune_net=prune, prune_k=12)):
            plain = ranking(net, position, dice, base)
            for threshold in (0.0, 0.05, 1e9):
                tripled = SearchConfig(
                    ply=base.ply, filter=base.filter, filter_extra=(0, 0, 0),
                    filter_threshold=(threshold,) * 3, prune_net=base.prune_net,
                    prune_k=base.prune_k)
                assert ranking(net, position, dice, tripled) == plain


#: The count-filter shapes the canonical levels had when GOLD was produced:
#: (filter, prune_k). Spelled out here rather than read from `search_level`,
#: so that retuning a level cannot silently re-target this gold.
COUNT_SHAPES = {
    'thorough': ((0, 1, 3), 0),
    'normal': ((0, 1, 3), 12),
}

#: First produced by the search code from BEFORE the triplet existed (count-only
#: filter); the current code at `extra = 0` was shown to return it bit for bit,
#: and it has since been re-recorded by that code when the weights moved
#: (upstream `c373141`). With MODEL and PRUNE, at the COUNT_SHAPES above: (position id,
#: turn, dice, shape) -> best play id and the bits of the first three equities. If one of these moves, the count
#: filter -- the triplet's `extra = 0` case -- changed what the engine plays.
GOLD = [
    ('ABJLVzOAowlqOg', 1, (3, 1), 'thorough',
     'EKMFajoAgqXTbA', ['9b1f16292c26b13f', '45cac0333946aa3f', 'ed25b4d750d9a63f']),
    ('ABJLVzOAowlqOg', 1, (3, 1), 'normal',
     'EKMFajoAgqXTbA', ['3bdd9abfe8aaaf3f', '56555595a906ad3f', '8445cac02cf98b3f']),
    ('d18AAgz9ExgBYA', 0, (6, 5), 'thorough',
     '/RMYgQJ3XwACDA', ['8b94814b3daae2bf']),
    ('d18AAgz9ExgBYA', 0, (6, 5), 'normal',
     '/RMYgQJ3XwACDA', ['8b94814b3daae2bf']),
    ('GQsQ42HXuQ8AAA', 0, (2, 2), 'thorough',
     '58cHAICMBYjxMA', ['c9c0d37cb7edf83f', 'fcb0486b1430f83f', '5f427b2b1292f63f']),
    ('GQsQ42HXuQ8AAA', 0, (2, 2), 'normal',
     '58cHAICMBYjxMA', ['ec25b4caabedf83f', '58a40c1e1330f83f', '46cac0990392f63f']),
    ('ShdFigO/BwAAAA', 0, (5, 3), 'thorough',
     'vwEAAJQuihQHAA', ['412c520200000040']),
    ('ShdFigO/BwAAAA', 0, (5, 3), 'normal',
     'vwEAAJQuihQHAA', ['412c520200000040']),
    ('++4AAEBvB4dAAA', 0, (6, 4), 'thorough',
     'vV0yAAH77gAAAA', ['2fa1bd34bf43f0bf', 'b7e687d5b246f0bf', '746b7e2e8249f0bf']),
    ('++4AAEBvB4dAAA', 0, (6, 4), 'normal',
     'vV0yAAH77gAAAA', ['f0746bb6cd43f0bf', '427b09ed1247f0bf', '746b7e2e8249f0bf']),
    ('JmfwCSDC5+AFCA', 1, (4, 4), 'thorough',
     'Zp7EAwgmZ/ABUA', ['45cac061f5bde23f', '5555552102aade3f', 'd7fcb0ace9e2d83f']),
    ('JmfwCSDC5+AFCA', 1, (4, 4), 'normal',
     'Zp7EAwgmZ/ABUA', ['4eb7e68704bde23f', '5555552102aade3f', 'b14819c042f3d83f']),
    ('sGfhCQI5HuEAMg', 1, (2, 1), 'thorough',
     'Mx3hADKwZ+EJQA', ['8ce338ee1126cebf', '9032f0e43aa7debf', 'a0bd84c2d307e0bf']),
    ('sGfhCQI5HuEAMg', 1, (2, 1), 'normal',
     'Mx3hADKwZ+EJQA', ['8ce338ee1126cebf', 'fdffffa767a7debf', 'a0bd84c2d307e0bf']),
    ('1xIEGxjzexUAAA', 1, (6, 6), 'thorough',
     '53cAAOBagmADAw', ['53069e1229aafb3f']),
    ('1xIEGxjzexUAAA', 1, (6, 6), 'normal',
     '53cAAOBagmADAw', ['402c520244b1fb3f']),
    ('3hDygQTtgSKMMA', 0, (5, 1), 'thorough',
     '7cEEjDDeEPKBBA', ['2265e0813ce6cfbf', '0c3cdd0eac3cd3bf', '7e58a4180935d7bf']),
    ('3hDygQTtgSKMMA', 0, (5, 1), 'normal',
     '7cEEjDDeEPKBBA', ['2265e0813ce6cfbf', '0c3cdd0eac3cd3bf', '7e58a4180935d7bf']),
    ('76cWAABbf4EgAA', 0, (4, 3), 'thorough',
     'W38hAQDvpxYAAA', ['2265e021c150e8bf', '80a75b074a6ce8bf', '6ecd0f3f1a39e9bf']),
    ('76cWAABbf4EgAA', 0, (4, 3), 'normal',
     'W38hAQDvpxYAAA', ['60913238d550e8bf', '2fa1bde8856ce8bf', '6ecd0f3f1a39e9bf']),
]


@needs_models
@pytest.mark.parametrize("entry", GOLD, ids=lambda e: f"{e[0]}-{e[2]}-{e[3]}")
def test_count_filter_reproduces_the_pre_triplet_gold(nets, entry):
    net, prune = nets
    position_id, turn, dice, shape, best, equities_hex = entry
    count, prune_k = COUNT_SHAPES[shape]
    config = SearchConfig(ply=2, filter=count, filter_extra=(0, 0, 0),
                          filter_threshold=(0.0, 0.0, 0.0),
                          prune_net=prune if prune_k else None, prune_k=prune_k)
    ranked = search_plays(net, codec.position_from_id(position_id, turn),
                          *dice, config)
    assert codec.position_id(ranked[0].play.result) == best
    got = [struct.pack("<d", c.equity).hex() for c in ranked[: len(equities_hex)]]
    assert got == equities_hex


#: The canonical "normal" level WITH its triplet (accept 1, extra 2,
#: threshold 0.04 at the root), on GOLD's positions: (position id, turn, dice)
#: -> best play id and the bits of the first three equities, with MODEL and
#: PRUNE. Against the count gold above, the best play and its equity are the
#: same on all ten; on four positions (ABJLVzOAowlqOg 3-1, GQsQ42HXuQ8AAA 2-2,
#: JmfwCSDC5+AFCA 4-4, sGfhCQI5HuEAMg 2-1) the 2nd/3rd candidates lie outside
#: the 0.04 band, are no longer deepened, and keep their shallow equity.
NORMAL_TRIPLET_GOLD = [
    ('ABJLVzOAowlqOg', 1, (3, 1), 'EKMFajoAgqXTbA',
     ['3bdd9abfe8aaaf3f', '56555595a906ad3f', '00000000c09a7e3f']),
    ('d18AAgz9ExgBYA', 0, (6, 5), '/RMYgQJ3XwACDA',
     ['8b94814b3daae2bf']),
    ('GQsQ42HXuQ8AAA', 0, (2, 2), '58cHAICMBYjxMA',
     ['ec25b4caabedf83f', '000000c0dce4f83f', '00000000a6b9f63f']),
    ('ShdFigO/BwAAAA', 0, (5, 3), 'vwEAAJQuihQHAA',
     ['412c520200000040']),
    ('++4AAEBvB4dAAA', 0, (6, 4), 'vV0yAAH77gAAAA',
     ['f0746bb6cd43f0bf', '427b09ed1247f0bf', '746b7e2e8249f0bf']),
    ('JmfwCSDC5+AFCA', 1, (4, 4), 'Zp7EAwgmZ/ABUA',
     ['4eb7e68704bde23f', '00000080c2f1de3f', '00000080439cd93f']),
    ('sGfhCQI5HuEAMg', 1, (2, 1), 'Mx3hADKwZ+EJQA',
     ['8ce338ee1126cebf', '000000806930debf', '000000405c19e0bf']),
    ('1xIEGxjzexUAAA', 1, (6, 6), '53cAAOBagmADAw',
     ['402c520244b1fb3f']),
    ('3hDygQTtgSKMMA', 0, (5, 1), '7cEEjDDeEPKBBA',
     ['2265e0813ce6cfbf', '0c3cdd0eac3cd3bf', '7e58a4180935d7bf']),
    ('76cWAABbf4EgAA', 0, (4, 3), 'W38hAQDvpxYAAA',
     ['60913238d550e8bf', '2fa1bde8856ce8bf', '6ecd0f3f1a39e9bf']),
]


@needs_models
@pytest.mark.parametrize("entry", NORMAL_TRIPLET_GOLD,
                         ids=lambda e: f"{e[0]}-{e[2]}")
def test_normal_level_reproduces_its_triplet_gold(nets, entry):
    net, prune = nets
    position_id, turn, dice, best, equities_hex = entry
    level = search_level("normal")
    base = level.to_config()
    config = SearchConfig(ply=base.ply, filter=base.filter,
                          filter_extra=base.filter_extra,
                          filter_threshold=base.filter_threshold,
                          prune_net=prune, prune_k=level.prune_k)
    ranked = search_plays(net, codec.position_from_id(position_id, turn),
                          *dice, config)
    assert codec.position_id(ranked[0].play.result) == best
    got = [struct.pack("<d", c.equity).hex() for c in ranked[: len(equities_hex)]]
    assert got == equities_hex


def expected_survivors(shallow: list[float], accept: int, extra: int,
                       threshold: float) -> int:
    n = len(shallow)
    if accept == 0 and extra == 0:
        return n
    keep = min(accept, n)
    limit = min(accept + extra, n)
    while keep < limit and shallow[keep] >= shallow[0] - threshold:
        keep += 1
    return keep


@needs_models
@pytest.mark.parametrize("accept,extra,threshold", [
    (0, 0, 0.0), (3, 0, 0.0), (1, 4, 0.0), (1, 4, 0.02), (1, 4, 0.08),
    (2, 6, 0.04), (0, 5, 0.03), (0, 8, 1e9),
])
def test_one_ply_deepens_exactly_the_triplet(nets, accept, extra, threshold):
    net, _ = nets
    checked = 0
    for position, dice in zip(corpus(), rolls()):
        shallow = search_plays(net, position, *dice, SearchConfig(ply=0))
        if len(shallow) < 3:
            continue
        zero = {codec.position_id(c.play.result): c.equity for c in shallow}
        config = SearchConfig(ply=1, filter=(0, accept), filter_extra=(0, extra),
                              filter_threshold=(0.0, threshold))
        deep = search_plays(net, position, *dice, config)
        deepened = sum(1 for c in deep
                       if c.equity != zero[codec.position_id(c.play.result)]
                       or c.play.result.is_over())
        want = expected_survivors([c.equity for c in shallow], accept, extra,
                                  threshold)
        assert deepened == want, (accept, extra, threshold, dice)
        checked += 1
    assert checked >= 10


@needs_models
def test_pruning_lets_through_at_least_accept_plus_extra(nets):
    net, prune = nets
    for position, dice in zip(corpus(15), rolls(15)):
        unpruned = search_plays(net, position, *dice, SearchConfig(ply=0))
        config = SearchConfig(ply=1, filter=(0, 1), filter_extra=(0, 5),
                              filter_threshold=(0.0, 1e9), prune_net=prune,
                              prune_k=2)
        got = search_plays(net, position, *dice, config)
        assert len(got) == min(6, len(unpruned))


@pytest.mark.parametrize("depth,accept,extra,threshold", [
    (-1, 1, 0, 0.0), (5, 1, 0, 0.0), (1, -1, 0, 0.0), (1, 1, -1, 0.0),
    (1, 1, 2, -0.01), (1, 1, 2, float("nan")), (1, 1, 2, float("inf")),
])
def test_an_incoherent_triplet_is_refused(depth, accept, extra, threshold):
    c = _CSearchConfig()
    c.filter[1] = 7
    assert _LIB.gn_search_set_filter(ctypes.byref(c), depth, accept, extra,
                                     threshold) == -1
    assert c.filter[1] == 7 and c.filter_extra[1] == 0


def test_a_coherent_triplet_is_written():
    c = _CSearchConfig()
    assert _LIB.gn_search_set_filter(ctypes.byref(c), 2, 1, 4, 0.06) == 0
    assert (c.filter[2], c.filter_extra[2], c.filter_threshold[2]) == (1, 4, 0.06)

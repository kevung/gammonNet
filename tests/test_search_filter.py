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

#: Produced by the search BEFORE the triplet existed (count-only filter), at
#: the COUNT_SHAPES above: (position id, turn, dice, shape) -> best play id
#: and the bits of the first three equities. If one of these moves, the count
#: filter -- the triplet's `extra = 0` case -- changed what the engine plays.
GOLD = [
    ('ABJLVzOAowlqOg', 1, (3, 1), 'thorough',
     'EKMFajoAgqXTbA', ['162903e76461c43f', 'cd0f8b9c6135c03f', '8745ca107d66bf3f']),
    ('ABJLVzOAowlqOg', 1, (3, 1), 'normal',
     'EKMFajoAgqXTbA', ['9132f0f411e8c33f', '9481a70b92dfbe3f', '08ed25e44317bc3f']),
    ('d18AAgz9ExgBYA', 0, (6, 5), 'thorough',
     '/RMYgQJ3XwACDA', ['0aed25300d67e2bf']),
    ('d18AAgz9ExgBYA', 0, (6, 5), 'normal',
     '/RMYgQJ3XwACDA', ['0aed25300d67e2bf']),
    ('GQsQ42HXuQ8AAA', 0, (2, 2), 'thorough',
     '58cHAICMBYjxMA', ['353f2cd80e8ef93f', '8ce338939d39f93f', '1f1629e6d5e3f63f']),
    ('GQsQ42HXuQ8AAA', 0, (2, 2), 'normal',
     '58cHAICMBYjxMA', ['52069e6c308cf93f', '9032f0af0939f93f', '3bdd9af0d1e3f63f']),
    ('ShdFigO/BwAAAA', 0, (5, 3), 'thorough',
     'vwEAAJQuihQHAA', ['5e427bbffaffff3f']),
    ('ShdFigO/BwAAAA', 0, (5, 3), 'normal',
     'vwEAAJQuihQHAA', ['000000d4faffff3f']),
    ('++4AAEBvB4dAAA', 0, (6, 4), 'thorough',
     'vV0yAAH77gAAAA', ['6291324c2843f0bf', '6fcd0f8ba443f0bf', '98d05ed4a44ef0bf']),
    ('++4AAEBvB4dAAA', 0, (6, 4), 'normal',
     'vV0yAAH77gAAAA', ['756b7ee43e43f0bf', 'a9aaaa7e1144f0bf', '98d05ed4a44ef0bf']),
    ('JmfwCSDC5+AFCA', 1, (4, 4), 'thorough',
     'Zp7EAwgmZ/ABUA', ['ed25b43fa4cbe23f', '7e58a428850edf3f', '47cac0d77e49d93f']),
    ('JmfwCSDC5+AFCA', 1, (4, 4), 'normal',
     'Zp7EAwgmZ/ABUA', ['ed25b43fa4cbe23f', '7e58a428850edf3f', '491978ee6d5ed93f']),
    ('sGfhCQI5HuEAMg', 1, (2, 1), 'thorough',
     'Mx3hADKwZ+EJQA', ['aaaaaab279ceccbf', 'f961914a3061debf', '491978a6c8a6dfbf']),
    ('sGfhCQI5HuEAMg', 1, (2, 1), 'normal',
     'Mx3hADKwZ+EJQA', ['aaaaaab279ceccbf', '756b7e405461debf', '491978a6c8a6dfbf']),
    ('1xIEGxjzexUAAA', 1, (6, 6), 'thorough',
     '53cAAOBagmADAw', ['5655554701e5fb3f']),
    ('1xIEGxjzexUAAA', 1, (6, 6), 'normal',
     '53cAAOBagmADAw', ['59a40c10fae2fb3f']),
    ('3hDygQTtgSKMMA', 0, (5, 1), 'thorough',
     '7UEDjDDeEPKBBA', ['6ecd0fa7ed03d0bf', '711cc7d5ae4ad2bf', 'c0d3ad292859d4bf']),
    ('3hDygQTtgSKMMA', 0, (5, 1), 'normal',
     '7UEDjDDeEPKBBA', ['6ecd0fa7ed03d0bf', '3e2c5242b24dd2bf', 'c0d3ad292859d4bf']),
    ('76cWAABbf4EgAA', 0, (4, 3), 'thorough',
     'W38hAQDvpxYAAA', ['d94b6897cf05e8bf', 'e0e9d6ecd427e8bf', '4db7e67bc8a7e8bf']),
    ('76cWAABbf4EgAA', 0, (4, 3), 'normal',
     'W38hAQDvpxYAAA', ['a1bd84b2e905e8bf', '77ba35171728e8bf', 'b6e68731d0a7e8bf']),
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
#: -> best play id and the bits of the first three equities. Frozen when the
#: triplet became the default. Against the count gold above, the best play and
#: its equity are the same on all ten; on three positions (GQsQ42HXuQ8AAA 2-2,
#: JmfwCSDC5+AFCA 4-4, sGfhCQI5HuEAMg 2-1) the 2nd/3rd candidates lie outside
#: the 0.04 band, are no longer deepened, and keep their shallow equity.
NORMAL_TRIPLET_GOLD = [
    ('ABJLVzOAowlqOg', 1, (3, 1), 'EKMFajoAgqXTbA',
     ['9132f0f411e8c33f', '9481a70b92dfbe3f', '08ed25e44317bc3f']),
    ('d18AAgz9ExgBYA', 0, (6, 5), '/RMYgQJ3XwACDA', ['0aed25300d67e2bf']),
    ('GQsQ42HXuQ8AAA', 0, (2, 2), '58cHAICMBYjxMA',
     ['52069e6c308cf93f', '9032f0af0939f93f', '000000c030fdf73f']),
    ('ShdFigO/BwAAAA', 0, (5, 3), 'vwEAAJQuihQHAA', ['000000d4faffff3f']),
    ('++4AAEBvB4dAAA', 0, (6, 4), 'vV0yAAH77gAAAA',
     ['756b7ee43e43f0bf', 'a9aaaa7e1144f0bf', '98d05ed4a44ef0bf']),
    ('JmfwCSDC5+AFCA', 1, (4, 4), 'Zp7EAwgmZ/ABUA',
     ['ed25b43fa4cbe23f', '00000080fadcdf3f', '000000c0c7ebda3f']),
    ('sGfhCQI5HuEAMg', 1, (2, 1), 'Mx3hADKwZ+EJQA',
     ['aaaaaab279ceccbf', '000000003b53ddbf', '0000000065eadfbf']),
    ('1xIEGxjzexUAAA', 1, (6, 6), '53cAAOBagmADAw', ['59a40c10fae2fb3f']),
    ('3hDygQTtgSKMMA', 0, (5, 1), '7UEDjDDeEPKBBA',
     ['6ecd0fa7ed03d0bf', '3e2c5242b24dd2bf', 'c0d3ad292859d4bf']),
    ('76cWAABbf4EgAA', 0, (4, 3), 'W38hAQDvpxYAAA',
     ['a1bd84b2e905e8bf', '77ba35171728e8bf', 'b6e68731d0a7e8bf']),
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

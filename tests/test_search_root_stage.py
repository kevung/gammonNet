"""La racine étagée (filtre-de-coups-spec §8) — ce qui doit rester vrai.

Ce fichier ne mesure pas ce qu'elle rapporte : c'est `bench/deep_root.py`. Il
tient les propriétés sans lesquelles cette mesure ne voudrait rien dire :

1. **Éteinte, rien ne bouge.** `root_stage_ply = 0`, ou un étage qui n'est pas
   strictement moins profond que la décision, rend la recherche sans étage au
   bit près — les ors de `test_search_filter.py` tiennent le reste.
2. **La composition exacte.** Une décision étagée est, au bit près, ce qu'on
   obtient à la main : classement 0-ply, triplet d'étage, survivants notés à
   la profondeur de l'étage, triés, `filter[ply]` sur ce classement, survivants
   notés à `ply`, triés. Vérifié à 2 plis avec un étage à 1 pli : le même
   chemin de code que 3 et 4 plis, pour une fraction du coût.
3. **Seule la racine d'une décision de coup est étagée** : l'équité avant le
   jet (`position_equity`) n'en dépend pas.
4. **Un étage incohérent est refusé**, jamais rabattu.
5. **Les niveaux `ply3` et `ply4`** portent la forme publiée.
"""

from __future__ import annotations

import ctypes
import random
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
    position_equity,
    search_level,
    search_plays,
)

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
needs_models = pytest.mark.skipif(
    not (MODEL.exists() and PRUNE.exists()), reason="modèles absents"
)


def corpus(count: int, seed: int = 20261011) -> list[tuple[Position, tuple[int, int]]]:
    """Des positions de vraies parties avec un jet, aux décisions non forcées."""
    rng = random.Random(seed)
    out = []
    position = Position.initial()
    while len(out) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if len(plays) >= 4 and rng.random() < 0.5:
            out.append((position, (d1, d2)))
        position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
    return out


@pytest.fixture(scope="module")
def nets():
    return Network.load(MODEL), Network.load(PRUNE)


def ranking(net, position, dice, config):
    return [(codec.position_id(c.play.result), c.equity.hex())
            for c in search_plays(net, position, *dice, config)]


def band(equities: list[float], accept: int, extra: int, threshold: float) -> int:
    """Le triplet de filtre, réécrit d'après la spec §2 pour le test."""
    n = len(equities)
    if accept == 0 and extra == 0:
        return n
    keep = min(accept, n)
    limit = min(accept + extra, n)
    while keep < limit and equities[keep] >= equities[0] - threshold:
        keep += 1
    return keep


@needs_models
def test_un_etage_eteint_ou_trop_profond_ne_change_rien(nets):
    net, prune = nets
    base = dict(ply=2, filter=(0, 1, 1), filter_extra=(0, 0, 2),
                filter_threshold=(0.0, 0.0, 0.04), prune_net=prune, prune_k=12)
    for position, dice in corpus(6):
        plain = ranking(net, position, dice, SearchConfig(**base))
        for stage_ply in (0, 2, 3):
            staged = SearchConfig(**base, root_stage_ply=stage_ply,
                                  root_stage_filter=(0, 8, 0.16))
            assert ranking(net, position, dice, staged) == plain


@needs_models
def test_la_racine_etagee_est_la_composition_ecrite_dans_la_spec(nets):
    net, prune = nets
    stage = (0, 4, 0.2)
    final = (0, 2, 0.04)
    config = SearchConfig(ply=2, filter=(0, 1, final[0]),
                          filter_extra=(0, 0, final[1]),
                          filter_threshold=(0.0, 0.0, final[2]),
                          prune_net=prune, prune_k=12, root_stage_ply=1,
                          root_stage_filter=stage)
    at = {d: SearchConfig(ply=d, filter=(0, 1, 0), prune_net=prune, prune_k=12)
          for d in (0, 1, 2)}

    def value(play, depth, shallow_equity):
        # A finished game is exact already: the search keeps its shallow
        # equity, which is the computed one, and never deepens it.
        if play.result.is_over():
            return shallow_equity
        return -position_equity(net, play.result, at[depth])

    differed = 0
    for position, dice in corpus(8):
        shallow = search_plays(net, position, *dice, at[0])
        plays = [c.play for c in shallow]
        eq = [c.equity for c in shallow]

        staged = band(eq, *stage)
        mid = sorted(((value(p, 1, e), p) for p, e in zip(plays[:staged], eq)),
                     key=lambda pair: -pair[0])
        deep = band([v for v, _ in mid], *final)
        top = sorted(((value(p, 2, v), p) for v, p in mid[:deep]),
                     key=lambda pair: -pair[0])
        expected = ([(codec.position_id(p.result), v.hex()) for v, p in top]
                    + [(codec.position_id(p.result), v.hex()) for v, p in mid[deep:]]
                    + [(codec.position_id(p.result), v.hex())
                       for v, p in zip(eq[staged:], plays[staged:])])

        got = ranking(net, position, dice, config)
        assert got == expected
        if staged > deep:
            differed += 1
    # Le test ne prouverait rien si l'étage ne coupait jamais.
    assert differed > 0


@needs_models
def test_l_equite_avant_le_jet_ignore_l_etage(nets):
    net, prune = nets
    plain = SearchConfig(ply=2, filter=(0, 1, 2), prune_net=prune, prune_k=12)
    staged = SearchConfig(ply=2, filter=(0, 1, 2), prune_net=prune, prune_k=12,
                          root_stage_ply=1, root_stage_filter=(0, 8, 0.16))
    for position, _ in corpus(3):
        assert (position_equity(net, position, staged).hex()
                == position_equity(net, position, plain).hex())


_LIB.gn_search_set_root_stage.argtypes = [
    ctypes.POINTER(_CSearchConfig), ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_double,
]
_LIB.gn_search_set_root_stage.restype = ctypes.c_int


@pytest.mark.parametrize("ply, accept, extra, threshold", [
    (-1, 0, 8, 0.16), (4, 0, 8, 0.16), (2, -1, 8, 0.16), (2, 0, -1, 0.16),
    (2, 0, 8, -0.01), (2, 0, 8, float("nan")), (2, 0, 8, float("inf")),
])
def test_un_etage_incoherent_est_refuse_et_la_config_intacte(ply, accept, extra,
                                                             threshold):
    c = _CSearchConfig()
    assert _LIB.gn_search_set_root_stage(ctypes.byref(c), 2, 0, 8, 0.16) == 0
    assert _LIB.gn_search_set_root_stage(ctypes.byref(c), ply, accept, extra,
                                         threshold) == -1
    assert (c.root_stage_ply, c.root_stage_filter, c.root_stage_filter_extra,
            c.root_stage_filter_threshold) == (2, 0, 8, 0.16)
    with pytest.raises(ValueError, match="étage de racine refusé"):
        SearchConfig(ply=3, root_stage_ply=ply,
                     root_stage_filter=(accept, extra, threshold))._to_c()


def test_eteindre_l_etage_remet_ses_champs_a_zero():
    c = _CSearchConfig()
    assert _LIB.gn_search_set_root_stage(ctypes.byref(c), 2, 0, 8, 0.16) == 0
    assert _LIB.gn_search_set_root_stage(ctypes.byref(c), 0, 3, 3, 0.5) == 0
    assert (c.root_stage_ply, c.root_stage_filter, c.root_stage_filter_extra,
            c.root_stage_filter_threshold) == (0, 0, 0, 0.0)


def test_les_niveaux_profonds_portent_la_forme_publiee():
    """Mesure : docs/mesures/2026-10-11-filtres-3-4-plis.md."""
    for name, ply in (("ply3", 3), ("ply4", 4)):
        level = search_level(name)
        assert level.ply == ply
        inner = (0,) + (1,) * (ply - 1)
        assert level.filter[:ply] == inner
        assert level.filter_extra[:ply] == (0,) * ply
        assert (level.filter[ply], level.filter_extra[ply],
                level.filter_threshold[ply]) == (0, 2, 0.04)
        assert level.root_stage_ply == 2
        assert level.root_stage_filter == (0, 8, 0.16)
        assert level.prune_k == 12
        config = level.to_config()
        assert (config.root_stage_ply, config.root_stage_filter) == (2, (0, 8, 0.16))
    # Le coût de l'élagage, mesuré à la forme même contre elle non élaguée.
    assert (search_level("ply3").prune_equity_loss,
            search_level("ply3").prune_equity_loss_ci_high) == pytest.approx(
                (0.000043, 0.000125))
    assert (search_level("ply4").prune_equity_loss,
            search_level("ply4").prune_equity_loss_ci_high) == pytest.approx(
                (0.000478, 0.001435))
    for name in ("instant", "normal", "thorough"):
        level = search_level(name)
        assert (level.root_stage_ply, level.root_stage_filter) == (0, (0, 0, 0.0))

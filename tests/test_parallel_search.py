"""La recherche sur plusieurs fils (`src/gn_parallel.h`) — le même résultat, au bit près.

Ce fichier ne mesure pas ce que les fils rapportent : c'est
`build/bench_decision --threads=n`. Il tient la seule propriété qui autorise à
s'en servir : **un nombre de fils ne change rien à ce que la recherche rend**.
Ni le classement, ni une seule équité, ni une probabilité, ni le compte
d'évaluations — sur chaque chemin de code que les fils traversent :

1. le nœud de hasard **groupé** (élagage actif — `normal`, `ply3`) ;
2. le nœud de hasard **non groupé** (sans élagage — `thorough`) ;
3. les candidats d'une **racine étagée** (`ply3`) ;
4. les deux **backups de distribution** (`position_probs`, `probs_by_roll`) ;
5. le **score de match** et le **videau** aux feuilles ;
6. le **cache partagé** activé (le compte d'évaluations peut alors bouger —
   qui remplit le cache en premier dépend des fils —, les valeurs non).

Le premier défaut que ce test aurait trouvé a été trouvé par son ancêtre, une
empreinte du banc : un tampon `static` local du noyau (`packed_in`), partagé
entre les fils, déplaçait 31 évaluations sur 68 260 et changeait des coups —
sans rien casser d'autre.
"""

from __future__ import annotations

import dataclasses
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import evalcache  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import Position  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    evaluations,
    position_equity,
    position_probs,
    probs_by_roll,
    reset_evaluations,
    search_level,
    search_plays,
    set_threads,
    threads,
)

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
needs_models = pytest.mark.skipif(
    not (MODEL.exists() and PRUNE.exists()), reason="modèles absents"
)

THREADS = 6


def corpus(count: int, seed: int = 20261013) -> list[tuple[Position, tuple[int, int]]]:
    """Des positions de vraies parties avec un jet, aux décisions non forcées."""
    rng = random.Random(seed)
    out = []
    position = Position.initial()
    while len(out) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if len(plays) >= 4 and rng.random() < 0.4:
            out.append((position, (d1, d2)))
        if not plays or position.is_over():
            position = Position.initial() if position.is_over() else position.swapped_turn()
            continue
        position = rng.choice(plays).result
        if position.is_over():
            position = Position.initial()
    return out


@pytest.fixture(scope="module")
def nets():
    with Network.load(MODEL) as net, Network.load(PRUNE) as prune:
        yield net, prune


@pytest.fixture(autouse=True)
def serial_after():
    yield
    set_threads(1)
    evalcache.disable()


def ranking(net, position, dice, config):
    """Le classement complet, au bit : (résultat, équité) dans l'ordre rendu."""
    return [(c.play.result, c.equity) for c in search_plays(net, position, *dice, config)]


def level_config(name: str, prune) -> SearchConfig:
    level = search_level(name)
    config = level.to_config()
    if level.prune_k:
        config = dataclasses.replace(config, prune_net=prune,
                                     prune_k=level.prune_k)
    return config


def both(fn):
    """`fn()` à un fil puis à THREADS fils, avec le compte d'évaluations."""
    out = []
    for n in (1, THREADS):
        set_threads(n)
        reset_evaluations()
        value = fn()
        out.append((value, evaluations()))
    set_threads(1)
    return out


@needs_models
@pytest.mark.parametrize("level", ["normal", "thorough"])
def test_levels_rank_identically(nets, level):
    net, prune = nets
    config = level_config(level, prune)
    for position, dice in corpus(4):
        (serial, e1), (threaded, en) = both(lambda: ranking(net, position, dice, config))
        assert threaded == serial
        assert en == e1


@needs_models
def test_staged_root_ranks_identically(nets):
    """`ply3` : racine étagée, élagage, nœuds groupés emboîtés sur trois plis."""
    net, prune = nets
    config = level_config("ply3", prune)
    position, dice = corpus(1, seed=7)[0]
    (serial, e1), (threaded, en) = both(lambda: ranking(net, position, dice, config))
    assert threaded == serial
    assert en == e1


@needs_models
def test_distribution_backups_identical(nets):
    net, prune = nets
    config = SearchConfig(ply=2, filter=(0, 1, 3))
    for position, _ in corpus(2, seed=11):
        (p1, e1), (pn, en) = both(lambda: position_probs(net, position, config).as_tuple())
        assert pn == p1 and en == e1
        (r1, f1), (rn, fn) = both(lambda: probs_by_roll(net, position, config))
        assert rn == r1 and fn == f1


@needs_models
def test_match_and_cube_identical(nets):
    net, prune = nets
    state = MatchState(away_on_roll=5, away_opponent=3)
    config = SearchConfig(ply=2, filter=(0, 1, 3), use_match=True, match=state,
                          use_cube=True, cube_owner=0, cube_x=0.68,
                          prune_net=prune, prune_k=12)
    for position, dice in corpus(2, seed=13):
        (serial, e1), (threaded, en) = both(lambda: ranking(net, position, dice, config))
        assert threaded == serial and en == e1
        (q1, _), (qn, _) = both(lambda: position_equity(net, position, config))
        assert qn == q1


@needs_models
def test_shared_cache_changes_counts_not_values(nets):
    net, prune = nets
    config = level_config("normal", prune)
    cases = corpus(3, seed=17)
    reference = [ranking(net, p, d, config) for p, d in cases]
    evalcache.enable()
    set_threads(THREADS)
    for (position, dice), expected in zip(cases, reference):
        assert ranking(net, position, dice, config) == expected
    # Twice: the second pass reads what concurrent threads wrote.
    for (position, dice), expected in zip(cases, reference):
        assert ranking(net, position, dice, config) == expected


def test_thread_count_is_refused_not_clamped():
    for bad in (0, -1, 257):
        with pytest.raises(ValueError):
            set_threads(bad)
    assert threads() == 1
    assert set_threads(3) == 3 and threads() == 3
    assert set_threads(1) == 1 and threads() == 1

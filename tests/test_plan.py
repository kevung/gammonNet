"""La décision découpée en tâches, au bit près (issue #36,
`docs/specs/decision-decomposee-spec.md`).

Chaque décision est prise deux fois : en un bloc (`search_plays`,
`position_equity`/`position_probs`, `gn_cube_decide`, `gn_policy_decide`), et
par un plan dont les tâches sont exécutées depuis leurs OCTETS, dans un ordre
mélangé. Les deux doivent être égales au dernier bit — `struct.pack` des
doubles et des floats, aucune tolérance.

Couvre ce que le module WebAssembly ne voit pas (`wasm/decision_parity.mjs`) :
la racine étagée de `ply3`, la table exacte bilatérale, les feuilles cubeful
en match.
"""

from __future__ import annotations

import ctypes
import random
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from gammonnet import plan, search
from gammonnet.cube import CubeOwner
from gammonnet.infer import Network
from gammonnet.met import MatchState
from gammonnet.policy import Decision, Pending, _CAction, _LIB as _POLICY_LIB
from gammonnet.rules import Position
from gammonnet.search import SearchConfig, match_config

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_256.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
TABLE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
CORPUS = ROOT / "data" / "policy_reference.bin"

pytestmark = pytest.mark.skipif(not MODEL.exists() or not PRUNE.exists(),
                                reason="poids absents")


def _positions(count: int, seed: int) -> list[Position]:
    data = CORPUS.read_bytes()
    n = struct.unpack_from("<I", data, 8)[0]
    out = []
    for r in range(n):
        o = 16 + r * 160
        out.append(Position(points=struct.unpack_from("<24b", data, o),
                            bar=(data[o + 24], data[o + 25]),
                            off=(data[o + 26], data[o + 27]), turn=data[o + 28]))
    out = [p for p in out if not p.is_over()]
    return random.Random(seed).sample(out, count)


@pytest.fixture(scope="module")
def nets():
    net = Network.load(MODEL)
    prune = Network.load(PRUNE)
    yield net, prune
    net.close()
    prune.close()


def _bits_d(x: float) -> bytes:
    return struct.pack("<d", x)


def _bits_f(xs) -> bytes:
    return struct.pack("<5f", *xs)


def _configs(prune) -> dict[str, SearchConfig]:
    ply3 = search.search_level("ply3")
    st = MatchState(away_on_roll=3, away_opponent=5, cube=1, crawford=False)
    return {
        "1ply": SearchConfig(ply=1),
        "normal": SearchConfig(ply=2, filter=(0, 1, 1), filter_extra=(0, 0, 2),
                               filter_threshold=(0.0, 0.0, 0.04), prune_net=prune, prune_k=12),
        "thorough": SearchConfig(ply=2, filter=(0, 1, 3)),
        "match-cubeful": replace(match_config(2, st), filter=(0, 1, 1), filter_extra=(0, 0, 2),
                                 filter_threshold=(0.0, 0.0, 0.04), prune_net=prune,
                                 prune_k=12, use_cube=True, cube_owner=int(CubeOwner.CENTRED),
                                 cube_x=0.688),
        "ply3": replace(ply3.to_config(), prune_net=prune, prune_k=ply3.prune_k),
    }


def _run(net, prune, blob: bytes, seed: int) -> tuple[bytes, list[int]]:
    rng = random.Random(seed)
    waves = []
    while not plan.info(blob).done:
        tasks = plan.tasks(blob)
        waves.append(len(tasks))
        order = list(range(len(tasks)))
        rng.shuffle(order)
        results = [plan.run_task(net, prune, tasks[k]) for k in order]
        rng.shuffle(results)
        blob = plan.advance(net, prune, blob, results)
    return blob, waves


def _action_fields(a: _CAction) -> tuple:
    """Every field, doubles as bits -- never the raw struct: its padding is
    whatever the allocator left, on both paths."""
    play = a.play
    moves = tuple((play.moves[m].from_, play.moves[m].to) for m in range(play.num_moves))
    return (a.kind, a.resign_value, a.searched, _bits_d(a.equity_a), _bits_d(a.equity_b),
            play.num_moves, moves, Position._from_c(play.result))


def _same_candidates(got, want) -> bool:
    if len(got) != len(want):
        return False
    for g, w in zip(got, want):
        if _bits_d(g.equity) != _bits_d(w.equity):
            return False
        if Position._from_c(g.play.result) != w.play.result:
            return False
    return True


@pytest.mark.parametrize("name", ["1ply", "normal", "thorough", "match-cubeful", "ply3"])
def test_move_and_position_bit_for_bit(nets, name):
    net, prune = nets
    config = _configs(prune)[name]
    count = 2 if name == "ply3" else 6
    rng = random.Random(36)
    for i, pos in enumerate(_positions(count, seed=100 + len(name))):
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        want = search.search_plays(net, pos, d1, d2, config)
        blob, _ = _run(net, prune, plan.plan_move(net, pos, d1, d2, config), seed=i)
        assert _same_candidates(plan.candidates(blob), want), (name, i)

        if name == "ply3":
            continue  # a 3-ply pre-roll search costs minutes; the root is what ply3 adds
        blob, waves = _run(net, prune, plan.plan_position(net, pos, config), seed=i + 50)
        equity, probs = plan.position_value(blob)
        assert _bits_d(equity) == _bits_d(search.position_equity(net, pos, config))
        e = search.position_probs(net, pos, config)
        assert _bits_f(probs) == _bits_f((e.win, e.win_gammon, e.win_backgammon,
                                          e.lose_gammon, e.lose_backgammon))
        assert waves == [2 * plan.NUM_ROLLS] if config.ply >= 1 else waves == []


def test_cube_bit_for_bit(nets):
    net, prune = nets
    config = _configs(prune)["normal"]
    for i, pos in enumerate(_positions(5, seed=7)):
        blob, waves = _run(net, prune, plan.plan_cube(net, pos, config, owner=0, efficiency=0.688,
                                                      jacoby=True), seed=i)
        decision, probs = plan.cube_decision(blob)
        e = search.position_probs(net, pos, config)
        assert _bits_f(probs) == _bits_f((e.win, e.win_gammon, e.win_backgammon,
                                          e.lose_gammon, e.lose_backgammon))
        assert waves == [plan.NUM_ROLLS]
        assert decision.action in (0, 1, 2, 3)


@pytest.mark.parametrize("level", ["instant", "normal", "thorough"])
def test_policy_bit_for_bit(nets, level):
    net, prune = nets
    for i, pos in enumerate(_positions(4, seed=11)):
        for decision in (Decision(position=pos, pending=Pending.MOVE, d1=5, d2=2),
                         Decision(position=pos, pending=Pending.CUBE),
                         Decision(position=pos, pending=Pending.TAKE)):
            want = _CAction()
            rc = _POLICY_LIB.gn_policy_decide(net._handle, prune._handle, level.encode(),
                                              ctypes.byref(decision._to_c()), ctypes.byref(want))
            try:
                blob = plan.plan_policy(net, prune, level, decision)
            except ValueError:
                assert rc != 0
                continue
            assert rc == 0
            blob, _ = _run(net, prune, blob, seed=i)
            got = plan.action(blob)
            assert _action_fields(got) == _action_fields(want), (level, i, decision.pending)


def test_with_the_exact_table(nets):
    if not TABLE.exists():
        pytest.skip("table bilatérale absente")
    from gammonnet import bearoff
    net, prune = nets
    config = _configs(prune)["normal"]
    bearoff.use_shared(str(TABLE))
    try:
        fp = plan.Fingerprint(model=1, prune=1, bearoff=1)
        for i, pos in enumerate(_positions(4, seed=3)):
            want = search.search_plays(net, pos, 6, 3, config)
            blob = plan.plan_move(net, pos, 6, 3, config, fp=fp)
            rng = random.Random(i)
            while not plan.info(blob).done:
                tasks = plan.tasks(blob)
                rng.shuffle(tasks)
                blob = plan.advance(net, prune, blob,
                                    [plan.run_task(net, prune, t, fp) for t in tasks])
            assert _same_candidates(plan.candidates(blob), want)
    finally:
        bearoff.disable_shared()


def test_refusals(nets):
    net, prune = nets
    config = _configs(prune)["normal"]
    pos = Position.initial()
    fp = plan.Fingerprint(model=11, prune=22, bearoff=0)
    blob = plan.plan_move(net, pos, 3, 1, config, fp=fp)
    tasks = plan.tasks(blob)
    assert len(tasks) == plan.NUM_ROLLS

    # Another instance -- another table here -- refuses the task.
    with pytest.raises(ValueError, match="autre instance"):
        plan.run_task(net, prune, tasks[0], plan.Fingerprint(model=11, prune=22, bearoff=33))
    # A pruning plan on an instance that cannot prune.
    with pytest.raises(ValueError):
        plan.run_task(net, None, tasks[0], fp)

    results = [plan.run_task(net, prune, t, fp) for t in tasks]
    with pytest.raises(ValueError):                       # one missing
        plan.advance(net, prune, blob, results[:-1])
    with pytest.raises(ValueError):                       # one twice
        plan.advance(net, prune, blob, [results[0]] + results[1:-1] + [results[0]])
    other = plan.plan_move(net, pos, 6, 4, config, fp=fp)
    foreign = [plan.run_task(net, prune, t, fp) for t in plan.tasks(other)]
    with pytest.raises(ValueError):                       # another plan's wave
        plan.advance(net, prune, blob, foreign[:len(results)])
    done = plan.advance(net, prune, blob, results)
    assert plan.info(done).done
    with pytest.raises(ValueError):                       # a plan already settled
        plan.advance(net, prune, done, results)


def test_no_legal_play_and_zero_ply(nets):
    net, prune = nets
    # Black closed out its home board, a White checker on the bar: no entry on 6-6.
    points = [0] * 24
    for i in range(18, 24):
        points[i] = -2
    points[0] = 14
    pos = Position(points=tuple(points), bar=(1, 0), off=(0, 3), turn=0)
    blob = plan.plan_move(net, pos, 6, 6, _configs(prune)["normal"])
    assert plan.info(blob).done and plan.candidates(blob) == []
    assert search.search_plays(net, pos, 6, 6, _configs(prune)["normal"]) == []

    # 0-ply: nothing to cut, the plan is settled at once.
    blob = plan.plan_position(net, Position.initial(), SearchConfig(ply=0))
    assert plan.info(blob).done and plan.info(blob).tasks == 0
    equity, _ = plan.position_value(blob)
    assert _bits_d(equity) == _bits_d(search.position_equity(net, Position.initial(),
                                                             SearchConfig(ply=0)))

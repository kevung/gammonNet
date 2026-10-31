"""#37 — `/v1/cube` at depth: the pre-roll distribution comes from the search.

The real server, on a real socket, against the library called in-process with
the same pinned weights, pruning network and `k`. What is held:

  * without `ply` the route answers exactly as before (no `ply` key either —
    `tests/test_serve_cube_compat.py` replays the recorded bytes);
  * at ply 1 and 2 the reported distribution is `position_probs` at that
    depth, BIT FOR BIT, and the cube equities are `decide()` on that vector;
  * in a match, the search is valued by the match table (`match_config`),
    not by money — the two give different distributions, so a server that
    searched in money would fail here;
  * a decider not on roll reads the MIRROR of the roller's searched
    distribution, and the negated equity;
  * the ceiling: asking past `--max-ply` comes back reporting the depth
    actually applied.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_serve import (  # noqa: E402
    PIN,
    ROOT,
    SERVE,
    _free_port,
    _pinned_weights_missing,
    _post,
    _wait_healthy,
)

NO_DICE_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:00:0:0:0:0:10"
GAMMONISH_XGID = "XGID=-cABCaCBA---aaaA--af-B--a-:0:0:1:00:0:0:0:0:10"

MAX_PLY = 2  # the fixture's ceiling: 2-ply pruned is a fraction of a second here


@pytest.fixture(scope="module")
def server():
    manque = _pinned_weights_missing()
    if manque:
        pytest.skip(manque)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVE), "--host", "127.0.0.1", "--port", str(port),
         "--max-ply", str(MAX_PLY)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(base_url, proc)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def library():
    """The pinned network, pruning network and `k`, and T34's efficiencies,
    loaded the way any caller of the library would."""
    from gammonnet.cube import CubeOwner
    from gammonnet.infer import Network

    manque = _pinned_weights_missing()
    if manque:
        pytest.skip(manque)
    pin = json.loads(PIN.read_text())
    network = Network.load(PIN.parent / pin["network_fp16"]["filename"])
    prune = Network.load(PIN.parent / pin["prune_fp16"]["filename"])
    measured = json.loads((ROOT / "docs" / "mesures" / "t34-efficacite.json").read_text())["results"]
    efficiency = {
        CubeOwner.CENTRED: measured["centered"]["x"],
        CubeOwner.OWNED: measured["owned"]["x"],
        CubeOwner.OPPONENT: measured["opponent"]["x"],
    }
    yield network, prune, pin.get("prune_k", 12), efficiency
    network.close()
    prune.close()


def _searched(library, xgid: str, ply: int, state=None):
    from gammonnet import codec
    from gammonnet.search import SearchConfig, match_config, position_probs

    network, prune, k, _eff = library
    position, _fields = codec.position_from_xgid(xgid)
    config = match_config(ply, state) if state is not None else SearchConfig(ply=ply)
    assert config.ply == ply
    return position_probs(network, position, replace(config, prune_net=prune, prune_k=k))


def _cube(server: str, **fields) -> dict:
    status, body = _post(server, "/v1/cube", fields)
    assert status == 200, body
    return body


def _probs(body: dict) -> tuple[float, ...]:
    p = body["probs"]
    return (p["win"], p["win_g"], p["win_bg"], p["lose_g"], p["lose_bg"])


def test_without_ply_no_ply_key_comes_back(server):
    body = _cube(server, xgid=NO_DICE_XGID, kind="double")
    assert "ply" not in body
    assert _cube(server, xgid=NO_DICE_XGID, kind="double", ply=0) == {**body, "ply": 0}


@pytest.mark.parametrize("ply", [1, 2])
def test_money_distribution_is_the_search_bit_for_bit(server, library, ply):
    from gammonnet.cube import CubeOwner, decide

    _net, _prune, _k, efficiency = library
    body = _cube(server, xgid=GAMMONISH_XGID, kind="double", ply=ply)
    assert body["ply"] == ply
    searched = _searched(library, GAMMONISH_XGID, ply)
    assert _probs(body) == searched.as_tuple()
    # And the cube model read exactly that vector.
    decision = decide(searched, CubeOwner.CENTRED, efficiency[CubeOwner.CENTRED], None, jacoby=True)
    assert body["no_double"] == decision.equity_no_double


def test_depth_actually_moves_the_answer(server):
    static = _cube(server, xgid=GAMMONISH_XGID, kind="double", ply=0)
    deep = _cube(server, xgid=GAMMONISH_XGID, kind="double", ply=1)
    assert _probs(static) != _probs(deep)


def _state(away_on_roll: int, away_opponent: int):
    from gammonnet.met import MatchState
    return MatchState(away_on_roll=away_on_roll, away_opponent=away_opponent, cube=1, crawford=False)


def test_match_search_is_valued_by_the_table(server, library):
    state = _state(3, 5)
    body = _cube(server, xgid=GAMMONISH_XGID, kind="double", decider_away=3, opponent_away=5, ply=2)
    assert _probs(body) == _searched(library, GAMMONISH_XGID, 2, state).as_tuple()
    # Not the money search: the table changes which play is best somewhere.
    assert _probs(body) != _searched(library, GAMMONISH_XGID, 2).as_tuple()


def test_decider_not_on_roll_reads_the_mirror_and_the_negation(server, library):
    common = dict(xgid=NO_DICE_XGID, kind="equity", decider_away=5, opponent_away=3, cube=1, ply=1)
    roller = _cube(server, **common, decider_on_roll=True)
    decider = _cube(server, **common | {"decider_away": 3, "opponent_away": 5}, decider_on_roll=False)
    assert decider["equity"] == -roller["equity"]
    assert _probs(decider) == _searched(library, NO_DICE_XGID, 1, _state(5, 3)).mirrored().as_tuple()


def test_take_at_depth_is_the_negation_of_double_at_depth(server):
    common = dict(xgid=NO_DICE_XGID, cube=1, ply=2)
    double = _cube(server, **common, kind="double", decider_away=2, opponent_away=7, decider_on_roll=True)
    take = _cube(server, **common, kind="take", decider_away=7, opponent_away=2, decider_on_roll=False)
    assert take["take"] == -double["double_take"]
    assert take["pass"] == -double["double_pass"]


def test_ply_is_clamped_to_the_ceiling_and_reported(server):
    body = _cube(server, xgid=NO_DICE_XGID, kind="double", ply=99)
    assert body["ply"] == MAX_PLY
    assert body == _cube(server, xgid=NO_DICE_XGID, kind="double", ply=MAX_PLY)


@pytest.mark.parametrize("bad", [-1, True, 1.5, "2"])
def test_a_malformed_ply_is_a_400(server, bad):
    status, body = _post(server, "/v1/cube", {"xgid": NO_DICE_XGID, "kind": "double", "ply": bad})
    assert status == 400
    assert "ply" in body["error"]


def test_server_names_contract_4(server):
    import urllib.request
    with urllib.request.urlopen(f"{server}/healthz", timeout=5) as resp:
        assert resp.headers["Server"].startswith("gammonNet-serve/4")

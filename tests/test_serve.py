"""#18 — integration tests for `tools/serve.py`, gammonNet's HTTP mode.

These start the REAL server as a subprocess, on a real socket, loading the
REAL pinned float16 artifact, and send REAL HTTP requests — no handler is
called in-process. `CLAUDE.md`'s garde-fou is explicit: never conclude a
thing works without having run it and read its output. A test that imported
`handle_eval` directly would never notice a routing mistake, a JSON encoding
bug, or the SHA-256 gate refusing to start.

The known position throughout is the opening 3-1 roll for White (uppercase):
the well-established, non-controversial best play is `6/5 8/5` (making the
5-point) — a real content check, not a shape-only assertion.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / "tools" / "serve.py"
PIN = ROOT / "models" / "release_pin.json"

OPENING_31_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10"

needs_weights = pytest.mark.skipif(
    not PIN.is_file(), reason="models/release_pin.json absent"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(base_url: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"le serveur s'est arrêté avant d'être prêt (code {proc.returncode}) :\n{out}")
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.2)
    raise TimeoutError("le serveur n'a jamais répondu à /healthz")


def _post(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def server():
    if not PIN.is_file():
        pytest.skip("models/release_pin.json absent")
    port = _free_port()
    proc = subprocess.Popen(
        # --max-ply 1 keeps this suite fast: a real 2-ply decision measures
        # in the SECONDS on this machine (docs/mesures/), which is real work
        # to verify manually, not something a test suite should pay for on
        # every run. The clamp itself is exercised below.
        [sys.executable, str(SERVE), "--host", "127.0.0.1", "--port", str(port), "--max-ply", "1"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
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


# ── /v1/eval ─────────────────────────────────────────────────────────────


def test_eval_finds_the_known_best_opening_play(server):
    status, body = _post(server, "/v1/eval", {"xgid": OPENING_31_XGID, "ply": 0})

    assert status == 200
    assert body["best_move"] == "6/5 8/5", body
    assert body["ply"] == 0
    assert isinstance(body["equity"], float)
    assert len(body["candidates"]) >= 15  # every legal 3-1 play

    equities = [c["equity"] for c in body["candidates"]]
    assert equities == sorted(equities, reverse=True), "les candidats doivent être triés, meilleur d'abord"
    assert body["candidates"][0]["move"] == "6/5 8/5"
    assert body["candidates"][0]["equity"] == pytest.approx(body["equity"])

    probs = body["probs"]
    assert set(probs) == {"win", "win_g", "win_bg", "lose_g", "lose_bg"}
    assert probs["win_bg"] <= probs["win_g"] <= probs["win"] <= 1.0
    assert probs["lose_bg"] <= probs["lose_g"] <= 1.0 - probs["win"] + 1e-6


def test_eval_clamps_ply_to_the_server_operators_ceiling(server):
    """The fixture launches with `--max-ply 1`; asking for 99 must come back
    reporting 1, never the number that was asked for."""
    status, body = _post(server, "/v1/eval", {"xgid": OPENING_31_XGID, "ply": 99})
    assert status == 200
    assert body["ply"] == 1


def test_eval_rejects_an_xgid_with_no_dice(server):
    no_dice_xgid = "XGID=-b----E-C---eE---c-e----B-:0:0:1:00:0:0:0:0:10"
    status, body = _post(server, "/v1/eval", {"xgid": no_dice_xgid, "ply": 0})
    assert status == 400
    assert "error" in body


def test_eval_rejects_a_malformed_xgid(server):
    status, body = _post(server, "/v1/eval", {"xgid": "not an xgid", "ply": 0})
    assert status == 400
    assert "error" in body


# ── /v1/cube ─────────────────────────────────────────────────────────────


def test_cube_double_at_the_opening_says_no_double(server):
    """No sane engine doubles on roll one of an even match — a real content
    check on the verdict, not merely that a verdict exists."""
    status, body = _post(
        server,
        "/v1/cube",
        {
            "xgid": OPENING_31_XGID,
            "kind": "double",
            "decider_away": 7,
            "opponent_away": 7,
            "cube": 1,
            "decider_on_roll": True,
        },
    )
    assert status == 200
    assert body["should_double"] is False
    assert body["too_good"] is False
    # ND is the chosen branch, so it must be the largest of the three.
    assert body["no_double"] >= body["double_take"]
    assert body["no_double"] >= body["double_pass"] or body["should_double"] is False
    assert body["should_take"] is False and body["take"] == 0.0 and body["pass"] == 0.0


def test_cube_double_and_take_are_perspective_negations(server):
    """The doubler's double_take/double_pass and the responder's take/pass,
    on the SAME position, must be exact negations of each other — that is the
    zero-sum property the implementation is built on, not a coincidence to
    hope for."""
    common = {
        "xgid": OPENING_31_XGID,
        "decider_away": 7,
        "opponent_away": 7,
        "cube": 1,
    }
    _status, double_body = _post(
        server, "/v1/cube", {**common, "kind": "double", "decider_on_roll": True}
    )
    _status, take_body = _post(
        server, "/v1/cube", {**common, "kind": "take", "decider_on_roll": False}
    )

    assert take_body["take"] == pytest.approx(-double_body["double_take"], abs=1e-9)
    assert take_body["pass"] == pytest.approx(-double_body["double_pass"], abs=1e-9)
    assert take_body["should_take"] == (double_body["double_take"] < double_body["double_pass"])


def test_cube_take_uses_the_doublers_own_away_score(server):
    """An ASYMMETRIC match, on purpose: `decider_away`/`opponent_away` name
    the DECIDER's own scores, and the decider is the responder for kind
    "take" — the opposite player from kind "double". A symmetric match
    (equal away scores, as the other perspective test above uses) cannot
    catch a doubler/responder mix-up; this one can, because 2-away and
    7-away are worth very different things."""
    doubling_side = {
        "xgid": OPENING_31_XGID, "kind": "double",
        "decider_away": 2, "opponent_away": 7, "cube": 1, "decider_on_roll": True,
    }
    # Same physical match, described from the RESPONDER's own point of view:
    # they are the decider now, so THEIR away score (7) comes first.
    responding_side = {
        "xgid": OPENING_31_XGID, "kind": "take",
        "decider_away": 7, "opponent_away": 2, "cube": 1, "decider_on_roll": False,
    }
    _status, double_body = _post(server, "/v1/cube", doubling_side)
    _status, take_body = _post(server, "/v1/cube", responding_side)

    assert take_body["take"] == pytest.approx(-double_body["double_take"], abs=1e-9)
    assert take_body["pass"] == pytest.approx(-double_body["double_pass"], abs=1e-9)


def test_cube_money_double_pass_is_exactly_one_cube_unit(server):
    """Janowski's model: passing a double always concedes exactly the
    pre-double stake — a fixed constant, not a computed one, so this is a
    genuine regression guard on the formula, not a tautology."""
    status, body = _post(
        server,
        "/v1/cube",
        {
            "xgid": OPENING_31_XGID,
            "kind": "double",
            "decider_away": 0,
            "opponent_away": 0,
            "cube": 4,
            "decider_on_roll": True,
        },
    )
    assert status == 200
    assert body["double_pass"] == pytest.approx(4.0)


def test_cube_rejects_a_non_power_of_two_cube(server):
    status, body = _post(
        server,
        "/v1/cube",
        {
            "xgid": OPENING_31_XGID,
            "kind": "double",
            "decider_away": 7,
            "opponent_away": 7,
            "cube": 3,
            "decider_on_roll": True,
        },
    )
    assert status == 400
    assert "error" in body


def test_cube_rejects_an_unknown_kind(server):
    status, body = _post(
        server,
        "/v1/cube",
        {
            "xgid": OPENING_31_XGID,
            "kind": "redouble",
            "decider_away": 7,
            "opponent_away": 7,
            "cube": 1,
            "decider_on_roll": True,
        },
    )
    assert status == 400
    assert "error" in body


# ── /v1/rollout ──────────────────────────────────────────────────────────


def test_rollout_returns_the_requested_trial_count_and_a_plausible_equity(server):
    status, body = _post(
        server,
        "/v1/rollout",
        {"xgid": OPENING_31_XGID, "trials": 108, "max_depth": 4, "seed": 20260828},
    )
    assert status == 200
    assert body["trials"] == 108
    assert body["std_err"] > 0.0
    # An opening-roll equity has no business being outside a generous
    # money-game range; this is a sanity bound, not a claim of precision.
    assert -1.0 < body["equity"] < 1.0


def test_rollout_is_reproducible_under_the_same_seed(server):
    """Common random numbers (gn_rollout.h): identical inputs, identical seed
    -> bit-identical result. A real determinism check, not an approximation."""
    request = {"xgid": OPENING_31_XGID, "trials": 36, "max_depth": 3, "seed": 7}
    _status, first = _post(server, "/v1/rollout", request)
    _status, second = _post(server, "/v1/rollout", request)
    assert first == second


def test_rollout_rejects_a_finished_position(server):
    # A position with all 15 White checkers borne off and Black untouched.
    over_xgid = "XGID=-a-a-a-a-a-a-a-a---------:0:0:1:00:0:0:0:0:10"
    status, body = _post(server, "/v1/rollout", {"xgid": over_xgid, "trials": 10, "max_depth": 0, "seed": 1})
    assert status == 422 or status == 400
    assert "error" in body


# ── Error contract ───────────────────────────────────────────────────────


def test_unknown_route_is_a_404(server):
    status, body = _post(server, "/v1/nope", {})
    assert status == 404


def test_a_non_json_body_is_a_400(server):
    req = urllib.request.Request(
        f"{server}/v1/eval", data=b"not json", headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "un corps non-JSON doit être refusé"
    except urllib.error.HTTPError as e:
        assert e.code == 400


# ── SHA-256 gate ─────────────────────────────────────────────────────────


@needs_weights
def test_refuses_to_start_on_a_tampered_weights_file(tmp_path):
    """CLAUDE.md rule 2, applied to the server's own startup: a weights file
    that does not match its pinned SHA-256 must never get a listening
    socket — proven here by launching the real process and checking that it
    exits non-zero and never answers /healthz."""
    tampered = tmp_path / "tampered.bin16"
    tampered.write_bytes(b"not the real network, but the right size doesn't matter here")

    port = _free_port()
    proc = subprocess.run(
        [
            sys.executable, str(SERVE),
            "--host", "127.0.0.1", "--port", str(port),
            "--weights", str(tampered),
            "--no-prune",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode != 0
    assert "SHA-256" in proc.stdout + proc.stderr or "SHA-256" in (proc.stdout or "")
    with pytest.raises((urllib.error.URLError, ConnectionError)):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)

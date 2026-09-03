"""#20 — two concurrent clients hammering `/v1/eval` must never corrupt each
other's response.

Found during gammonGo#1021's recette: two `go test` runs in flight against the
same `gammonnet serve` produced a structurally malformed/mixed HTTP response —
not merely a wrong number. Suspect (per the issue): `ThreadingServer` dispatches
each request onto its own thread, but the native inference library's forward
pass writes into scratch buffers OWNED BY THE MODEL (`NNModel.buf_a`/`buf_b` in
`vendor/backgammon-ai-engine/c_inference/nn_eval.c`, allocated once at load
time and reused — never per-call). `ctypes.CDLL` releases the GIL for the
duration of a call, so two threads inside `nn_forward_prob5` at the same time
race on those same buffers.

**The oracle**: `gn_evaluate` is a pure function of (weights, position) — the
existing suite already relies on this (`test_rollout_is_reproducible_under_the_
same_seed`). So a single-threaded reference response for a FIXED xgid must be
exactly reproduced every time that same xgid is requested, however much
unrelated concurrent traffic (a DIFFERENT xgid, hammered in a tight loop on
another thread) is happening at the same time. A deviation — wrong best_move,
wrong equity, or a body that doesn't even parse as JSON — is the corruption
the issue describes, caught without needing to know its exact shape.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from test_serve import (OPENING_31_XGID, SERVE, _free_port, _post,
                        _pinned_weights_missing, _wait_healthy)

import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent

# Same opening board, a different roll (6-5 instead of 3-1) -- a different
# xgid with a clearly different best play and equity, so a mix-up between the
# two threads' responses is unmistakable rather than a subtle rounding drift.
OPENING_65_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:65:0:0:0:0:10"

# Iterations per thread. Tuned to reliably reproduce the race on this machine
# (2+ threads, tight loop) while keeping the test itself fast; this is a
# concurrency reproduction, not a load test -- see test_serve_throughput.py
# for the measured req/s figure #1028 needs.
ITERATIONS = 400


@pytest.fixture(scope="module")
def concurrency_server():
    manque = _pinned_weights_missing()
    if manque:
        pytest.skip(manque)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVE), "--host", "127.0.0.1", "--port", str(port), "--max-ply", "0"],
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


def _hammer(base_url: str, xgid: str, iterations: int, errors: list) -> None:
    payload = json.dumps({"xgid": xgid, "ply": 0}).encode()
    for _ in range(iterations):
        req = urllib.request.Request(
            f"{base_url}/v1/eval", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
        try:
            body = json.loads(raw)
        except ValueError as exc:
            errors.append(f"réponse JSON mal formée pour {xgid!r} : {exc!r} -- corps brut : {raw!r}")
            continue
        yield body


def test_two_concurrent_clients_never_corrupt_each_others_response(concurrency_server):
    # Single-threaded reference, taken BEFORE any concurrent traffic starts --
    # the ground truth every concurrent response for the same xgid must match.
    ref_status_a, ref_a = _post(concurrency_server, "/v1/eval", {"xgid": OPENING_31_XGID, "ply": 0})
    ref_status_b, ref_b = _post(concurrency_server, "/v1/eval", {"xgid": OPENING_65_XGID, "ply": 0})
    assert ref_status_a == 200 and ref_status_b == 200
    assert ref_a["best_move"] != ref_b["best_move"], "les deux xgid doivent produire des coups différents"

    errors_a: list[str] = []
    errors_b: list[str] = []
    mismatches: list[str] = []

    def run(xgid: str, reference: dict, errors: list[str]) -> None:
        for body in _hammer(concurrency_server, xgid, ITERATIONS, errors):
            if body.get("best_move") != reference["best_move"] or body.get("equity") != reference["equity"]:
                mismatches.append(
                    f"xgid={xgid!r} attendu best_move={reference['best_move']!r} equity={reference['equity']!r} "
                    f"obtenu {body!r}"
                )

    t1 = threading.Thread(target=run, args=(OPENING_31_XGID, ref_a, errors_a))
    t2 = threading.Thread(target=run, args=(OPENING_65_XGID, ref_b, errors_b))
    start = time.monotonic()
    t1.start()
    t2.start()
    t1.join(timeout=120)
    t2.join(timeout=120)
    elapsed = time.monotonic() - start

    assert not t1.is_alive() and not t2.is_alive(), "les deux threads n'ont pas terminé à temps"

    total = 2 * ITERATIONS
    print(
        f"\n{total} requêtes /v1/eval, deux clients concurrents, en {elapsed:.2f}s "
        f"({total / elapsed:.1f} req/s) -- {len(errors_a) + len(errors_b)} JSON malformés, "
        f"{len(mismatches)} réponses mélangées/corrompues"
    )

    assert not errors_a, errors_a[:5]
    assert not errors_b, errors_b[:5]
    assert not mismatches, mismatches[:5]

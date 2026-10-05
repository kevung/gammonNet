"""#26 — `/v1/cube` answers a request without the new fields EXACTLY as before.

The contract of `/v1/cube` grew four fields (Jacoby, cube ownership, Crawford,
and the `equity` kind). The promise that came with them is the strictest one
a contract can make: a request that sends none of them receives the SAME
BYTES as before. Not "the same numbers within a tolerance" — the same bytes,
because a caller may have recorded a response, hashed it, or diffed it.

## How this is proved, and why it is not circular

`tests/data/serve_cube_gold.jsonl` was RECORDED against the server as it
stood before any of those fields existed (its first line names the commit and
the pinned artifact). This test replays every recorded request against the
CURRENT server and compares the raw response body, byte for byte, and the
HTTP status. One recorded body is allowed to differ, and only to the exact
text written in `DELIBERATE_CHANGES`: the error that lists the accepted
`kind` values, which would otherwise keep listing two of three. A server that recomputed the gold with its own new code would
prove nothing; this one is held to what an older process answered.

The matrix is deliberately wide where a regression would hide: money and
match, symmetric and asymmetric away scores, a player at 1-away on either
side, cube values 1/2/4, both kinds, both `decider_on_roll`, a position where
Jacoby changes the verdict, and XGIDs whose own cube-owner and Crawford fields
are set — those fields were ignored before and must stay ignored when the
request does not ask otherwise. Refused requests are replayed too: a status
that changed from 400 to 422 is a contract change like any other.

## Tolerance

None by default. A `NATIVE_FP=1` build moves outputs by ~6e-07
(`tests/test_regression.py`), which no byte comparison survives: set
`GN_REGRESSION_TOLERANCE` (as for the regression corpus) and the bodies are
then compared as parsed JSON, numbers within that tolerance, keys and every
non-numeric value still exact.

## Recording

    python tests/test_serve_cube_compat.py --record

is how the gold was made, and the only legitimate reason to run it again is a
change of pinned weights — which moves every number and must be visible as a
regenerated file in its own commit, never folded into a contract change.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_serve import (  # noqa: E402
    OPENING_31_XGID, PIN, ROOT, SERVE, _free_port, _pinned_weights_missing,
    _wait_healthy,
)

GOLD = ROOT / "tests" / "data" / "serve_cube_gold.jsonl"

# A contact position where the on-roll side wins 83 % with 61 % gammons: the
# Jacoby rule flips its money verdict (too good without it, double/pass with
# it). Chosen from the T12 corpus for exactly that property.
GAMMONISH_XGID = "XGID=-cABCaCBA---aaaA--af-B--a-:0:0:1:00:0:0:0:0:10"
# The same board, its XGID claiming a cube at 2 owned by the uppercase player,
# then by the lowercase one, then a Crawford game of a 5-point match. The
# request fields, not the XGID's, have always decided the cube state here.
GAMMONISH_OWNER_UPPER = "XGID=-cABCaCBA---aaaA--af-B--a-:1:1:1:00:0:0:0:0:10"
GAMMONISH_OWNER_LOWER = "XGID=-cABCaCBA---aaaA--af-B--a-:1:-1:1:00:0:0:0:0:10"
GAMMONISH_CRAWFORD = "XGID=-cABCaCBA---aaaA--af-B--a-:0:0:1:00:4:2:1:5:10"
RACE_XGID = "XGID=-AGB-B----C--b-a---aaadcb-:0:0:1:00:0:0:0:0:10"
BACKGAME_XGID = "XGID=-b--babA-B-Ab--ababA-DDAA-:0:0:1:00:0:0:0:0:10"

POSITIONS = (
    OPENING_31_XGID, GAMMONISH_XGID, GAMMONISH_OWNER_UPPER,
    GAMMONISH_OWNER_LOWER, GAMMONISH_CRAWFORD, RACE_XGID, BACKGAME_XGID,
)
SCORES = ((0, 0), (7, 7), (2, 7), (7, 2), (2, 2), (1, 5), (5, 1), (3, 4), (0, 5))
CUBES = (1, 2, 4)


def request_matrix() -> list[dict]:
    requests: list[dict] = []
    for xgid in POSITIONS:
        # Nothing but the two mandatory fields: every default at once.
        for kind in ("double", "take"):
            requests.append({"xgid": xgid, "kind": kind})
        for decider_away, opponent_away in SCORES:
            for cube in CUBES:
                for kind in ("double", "take"):
                    for on_roll in (True, False):
                        requests.append({
                            "xgid": xgid, "kind": kind,
                            "decider_away": decider_away,
                            "opponent_away": opponent_away,
                            "cube": cube, "decider_on_roll": on_roll,
                        })
    # What was refused must stay refused, with the same status and message.
    base = {"xgid": OPENING_31_XGID, "kind": "double", "decider_away": 7,
            "opponent_away": 7, "cube": 1, "decider_on_roll": True}
    requests += [
        {**base, "cube": 3},
        {**base, "cube": 0},
        {**base, "cube": "2"},
        {**base, "kind": "redouble"},
        {**base, "decider_away": 26},
        {**base, "decider_away": 7.0},
        {**base, "xgid": "not an xgid"},
        {**base, "xgid": ""},
        {"kind": "double"},
        {**base, "xgid": "XGID=-a-a-a-a-a-a-a-a---------:0:0:1:00:0:0:0:0:10"},
    ]
    return requests


#: The ONLY recorded answers allowed to differ, each with its new body and
#: its reason. An error message that ENUMERATES the accepted values must
#: change when a value is added, or it states something false; the status
#: stays the same. Any other difference fails, and so does this one if its
#: new body is not exactly the one written here.
DELIBERATE_CHANGES = {
    json.dumps({"xgid": OPENING_31_XGID, "kind": "redouble", "decider_away": 7,
                "opponent_away": 7, "cube": 1, "decider_on_roll": True}): (
        '{"error": "kind doit \\u00eatre \'double\', \'take\' ou \'equity\'"}',
        "#26 : le message énumère les kinds admis, et 'equity' en est un",
    ),
}


def post_raw(base_url: str, payload: dict) -> tuple[int, str]:
    """The status and the body AS SENT — not re-serialised from a parse,
    which would normalise away exactly the differences this test exists to
    see (key order, float formatting)."""
    req = urllib.request.Request(
        f"{base_url}/v1/cube", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def start_server() -> tuple[subprocess.Popen, str]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVE), "--host", "127.0.0.1", "--port", str(port),
         "--max-ply", "1"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    _wait_healthy(base_url, proc)
    return proc, base_url


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def load_gold() -> tuple[dict, list[dict]]:
    lines = GOLD.read_text(encoding="utf-8").splitlines()
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


def _close(a, b, tolerance: float, path: str = "$") -> list[str]:
    """Structural comparison for a `NATIVE_FP=1` build: numbers within
    `tolerance`, everything else — keys, booleans, strings — exact."""
    if isinstance(a, bool) or isinstance(b, bool) or not (
        isinstance(a, (int, float)) and isinstance(b, (int, float))
    ):
        if isinstance(a, dict) and isinstance(b, dict):
            if list(a) != list(b):
                return [f"{path}: clés {list(a)} != {list(b)}"]
            out: list[str] = []
            for key in a:
                out += _close(a[key], b[key], tolerance, f"{path}.{key}")
            return out
        return [] if a == b and type(a) is type(b) else [f"{path}: {a!r} != {b!r}"]
    return [] if math.isclose(a, b, rel_tol=0.0, abs_tol=tolerance) else [
        f"{path}: {a!r} != {b!r}"
    ]


@pytest.fixture(scope="module")
def current_server():
    manque = _pinned_weights_missing()
    if manque:
        pytest.skip(manque)
    proc, base_url = start_server()
    try:
        yield base_url
    finally:
        stop_server(proc)


def test_the_gold_was_recorded_against_the_pinned_artifact_in_use():
    """A gold recorded on other weights would fail for a reason that has
    nothing to do with the contract — say so instead of failing obscurely."""
    header, entries = load_gold()
    pin = json.loads(PIN.read_text())
    assert header["pin_version"] == pin["version"], (
        f"repère enregistré sous {header['pin_version']}, épingle courante "
        f"{pin['version']} : un changement de poids se régénère dans son propre commit"
    )
    assert header["network_sha256"] == pin["network_fp16"]["sha256"]
    assert len(entries) == len(request_matrix())


def test_a_request_without_the_new_fields_gets_the_recorded_bytes(current_server):
    _header, entries = load_gold()
    assert [e["request"] for e in entries] == request_matrix(), (
        "la matrice de requêtes a changé depuis l'enregistrement"
    )
    tolerance = float(os.environ.get("GN_REGRESSION_TOLERANCE", "0"))

    differences = []
    deliberate_seen = set()
    for entry in entries:
        status, body = post_raw(current_server, entry["request"])
        if status != entry["status"]:
            differences.append(f"{entry['request']}: statut {status} != {entry['status']}")
            continue
        key = json.dumps(entry["request"])
        if key in DELIBERATE_CHANGES:
            deliberate_seen.add(key)
            expected, _reason = DELIBERATE_CHANGES[key]
            if body != expected:
                differences.append(f"{entry['request']}: changement délibéré attendu {expected}, obtenu {body}")
            continue
        if tolerance == 0.0:
            if body != entry["body"]:
                differences.append(f"{entry['request']}:\n  avant {entry['body']}\n  après {body}")
        else:
            for line in _close(json.loads(entry["body"]), json.loads(body), tolerance):
                differences.append(f"{entry['request']}: {line}")

    assert deliberate_seen == set(DELIBERATE_CHANGES), "un changement délibéré ne figure plus dans le repère"
    assert not differences, (
        f"{len(differences)} réponse(s) sur {len(entries)} ont changé :\n"
        + "\n".join(differences[:10])
    )


def record() -> None:
    manque = _pinned_weights_missing()
    if manque:
        raise SystemExit(manque)
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--", "tools/serve.py", "python", "src"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty:
        raise SystemExit(f"le serveur ou la bibliothèque a des modifications non commitées :\n{dirty}")
    pin = json.loads(PIN.read_text())

    proc, base_url = start_server()
    try:
        lines = [json.dumps({
            "recorded_at_commit": commit,
            "pin_version": pin["version"],
            "network_sha256": pin["network_fp16"]["sha256"],
        })]
        for request in request_matrix():
            status, body = post_raw(base_url, request)
            lines.append(json.dumps({"request": request, "status": status, "body": body}))
    finally:
        stop_server(proc)
    GOLD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines) - 1} réponses enregistrées dans {GOLD.relative_to(ROOT)} @ {commit[:7]}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--record"]:
        record()
    else:
        raise SystemExit("usage : python tests/test_serve_cube_compat.py --record")

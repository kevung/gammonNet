#!/usr/bin/env python3
"""`gammonNet serve` — an HTTP wrapper around the evaluator (#18).

This is the `blunderdb serve` shape applied here: a generic engine process
that speaks HTTP, so any consumer (gammonGo today, Desktop/blunderDB per
kevung/blunderDB#119 tomorrow) can point at it instead of embedding this
repository. The wrapper lives here, per the issue's own framing — not in the
consumer.

## Why Python, not a new C binary

`CLAUDE.md` names two languages: C for inference, Python for tooling and
measurement. An HTTP server is neither, strictly — but `python/gammonnet`
already IS a complete, tested surface over every C entry point this server
needs (rules, inference, search, the cube model, the match equity table,
rollouts, XGID). Writing this in C would mean re-deriving that surface a
second time against the raw header, with nothing gained: no consumer of this
process cares what language answers an HTTP request, and a second copy of
"how to call gn_cube_decide" is a second thing to keep in agreement with the
first. `tools/gnubg_server.py` is the precedent already in this repository —
a thin Python protocol wrapper standing in front of an engine, over
stdin/stdout rather than HTTP. This keeps its shape and changes only the
transport, using nothing beyond the standard library's `http.server` — no new
dependency, exotic or otherwise.

## What this refuses, on principle

`CLAUDE.md` rule 2: *"A model this build cannot evaluate is refused, not
approximated."* Applied here: the pinned float16 artifact's SHA-256 is
checked BEFORE the socket opens. A mismatch exits non-zero with nothing
listening — never a server that started anyway on the wrong weights.

## The three endpoints, and what each one does NOT try to be

  * `/v1/eval`    — XGID (checkers AND dice) + ply -> ranked candidate plays,
                    at 0-ply by default. The XGID's own cube/score fields are
                    IGNORED here: this is deliberately a plain cubeless money
                    search. A caller wanting a cube-aware or match-aware
                    decision uses /v1/cube, which takes the score explicitly.
  * `/v1/cube`    — a cube decision, "double" or "take", given explicit away
                    scores (0 on either side means money, not "match not
                    started"). Static (0-ply) always. Crawford is not carried
                    by this contract and defaults to false — a known,
                    documented limitation, not a silent guess.
  * `/v1/rollout` — Monte-Carlo estimate of a position (the XGID's dice, if
                    any, are ignored: a rollout answers for the position
                    BEFORE a roll, same convention as `gn_rollout`).
                    `max_depth == 0` plays every trial to the end, which is
                    the only case `win_prob` is a real observed frequency
                    rather than the honest zero a truncated rollout reports.

See `README.md` for the wire format and `tests/test_serve.py` for a live
round-trip against each endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import socketserver
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.cube import CubeAction, CubeOwner, decide as cube_decide  # noqa: E402
from gammonnet.cube import value as cube_value  # noqa: E402
from gammonnet.infer import Evaluation, Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout as run_rollout  # noqa: E402
from gammonnet.rules import BAR, OFF, WHITE  # noqa: E402
from gammonnet.search import Candidate, SearchConfig, search_plays  # noqa: E402

DEFAULT_PIN = ROOT / "models" / "release_pin.json"
DEFAULT_EFFICIENCY_FILE = ROOT / "docs" / "mesures" / "t34-efficacite.json"

MAX_SEARCH_PLY = 4  # GN_MAX_PLY — the hard ceiling the C search enforces.


# ── Startup: the SHA-256 gate ───────────────────────────────────────────


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pinned(path: Path, expected_sha256: str, label: str) -> None:
    """Refuse to start rather than serve an artifact that does not match its pin.

    This is CLAUDE.md rule 2 applied to weight loading: an evaluator handed an
    input — here, a FILE — it was not told to expect returns nothing plausible
    at all. It never gets the chance to run.
    """
    if not path.is_file():
        raise SystemExit(
            f"REFUS DE DÉMARRER : {label} absent ({path}).\n"
            f"  lancer : python tools/fetch_release.py"
        )
    actual = sha256_of(path)
    if actual.lower() != expected_sha256.lower():
        raise SystemExit(
            f"REFUS DE DÉMARRER : {label} ne correspond pas au SHA-256 épinglé.\n"
            f"  fichier  : {path}\n"
            f"  attendu  : {expected_sha256}\n"
            f"  obtenu   : {actual}\n"
            f"Un poids qui ne correspond pas à son épingle n'est jamais chargé,"
            f" jamais approximé (CLAUDE.md, règle 2)."
        )


# ── Move notation ────────────────────────────────────────────────────────
#
# `Move.__repr__` in rules.py prints raw 0-23 array indices — a debugging
# aid, not backgammon notation. The real thing needs each point renumbered
# from the MOVER'S own perspective: gn_rules.h states the mapping directly —
# "index i denotes point (i+1) for WHITE and point (24-i) for BLACK" — and
# that formula, read for whichever colour is actually on roll, already IS
# each player's own 1-24 numbering (ace point nearest to bearing off is
# always 1, the far point is always 24). No second convention to invent.


def _point_number(index: int, mover: int) -> str:
    if index == BAR:
        return "bar"
    if index == OFF:
        return "off"
    return str(index + 1) if mover == WHITE else str(24 - index)


def format_play(candidate: Candidate, mover: int) -> str:
    """Standard notation, e.g. `24/18 13/11(2)` — repeated submoves collapsed."""
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for move in candidate.play.moves:
        pair = (_point_number(move.from_, mover), _point_number(move.to, mover))
        if pair not in counts:
            order.append(pair)
        counts[pair] = counts.get(pair, 0) + 1
    if not order:
        return ""
    parts = []
    for src, dst in order:
        n = counts[(src, dst)]
        parts.append(f"{src}/{dst}" + (f"({n})" if n > 1 else ""))
    return " ".join(parts)


def _probs_json(evaluation: Evaluation) -> dict:
    return {
        "win": evaluation.win,
        "win_g": evaluation.win_gammon,
        "win_bg": evaluation.win_backgammon,
        "lose_g": evaluation.lose_gammon,
        "lose_bg": evaluation.lose_backgammon,
    }


# ── Errors ────────────────────────────────────────────────────────────────


class ApiError(Exception):
    """Carries the HTTP status a handler wants — never 200 with a disguised
    error body. gammonGo's client treats any non-200 as a transport failure
    and degrades gracefully; a 200 with an error payload it doesn't parse
    would instead be silently misread as a real result."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ApiError(400, message)


def is_int(value: object) -> bool:
    """`bool` is technically an `int` subclass in Python; a JSON `true` must
    never silently pass a numeric field check as `1`."""
    return isinstance(value, int) and not isinstance(value, bool)


# ── The engine, loaded once ─────────────────────────────────────────────


@dataclass
class Engine:
    network: Network
    prune_network: Network | None
    prune_k: int
    efficiency: dict[CubeOwner, float]
    #: Operator-set ceiling, `<= MAX_SEARCH_PLY`. `BRIEF.md` measured a
    #: 2-ply decision at ~14s on this machine with the k=12 pruning network
    #: (unpruned 3-ply: 70s) — real costs, not a guess. Defaulting this to
    #: `MAX_SEARCH_PLY` keeps the issue's "2-ply on demand" promise; an
    #: operator who wants a stricter bound on a shared or latency-sensitive
    #: deployment sets `--max-ply` down, never by editing this file.
    max_ply: int = MAX_SEARCH_PLY


def load_efficiency(path: Path) -> dict[CubeOwner, float]:
    """T34's own measured cube efficiencies (`docs/mesures/t34-efficacite.json`),
    indexed by cube ownership — never a borrowed or guessed constant."""
    data = json.loads(path.read_text())["results"]
    return {
        CubeOwner.OWNED: data["owned"]["x"],
        CubeOwner.CENTRED: data["centered"]["x"],
        CubeOwner.OPPONENT: data["opponent"]["x"],
    }


# ── /v1/eval ─────────────────────────────────────────────────────────────


def handle_eval(engine: Engine, body: dict) -> dict:
    xgid = body.get("xgid")
    require(isinstance(xgid, str) and xgid, "xgid manquant ou invalide")
    requested_ply = body.get("ply", 0)
    require(is_int(requested_ply) and requested_ply >= 0, "ply doit être un entier >= 0")

    try:
        position, fields = codec.position_from_xgid(xgid)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    require(not position.is_over(), "position déjà terminée : rien à décider")

    require(
        fields.die1 in range(1, 7) and fields.die2 in range(1, 7),
        "xgid sans dés : rien à rechercher (une position à décider n'a pas encore de coup)",
    )

    applied_ply = min(requested_ply, engine.max_ply, MAX_SEARCH_PLY)
    config = SearchConfig(ply=applied_ply)
    if applied_ply >= 1 and engine.prune_network is not None:
        config = replace(config, prune_net=engine.prune_network, prune_k=engine.prune_k)

    candidates = search_plays(engine.network, position, fields.die1, fields.die2, config)

    if not candidates:
        # No legal play: the position is unchanged, only the turn passes.
        # The mover's own equity is then the negation of the OPPONENT's own
        # static evaluation of that same, unmoved board — exactly what
        # `gn_choose`'s own sign convention says a resulting position means.
        opponent_view = engine.network.evaluate(position.swapped_turn())
        return {
            "best_move": "",
            "equity": -opponent_view.money_equity,
            "candidates": [],
            "ply": applied_ply,
        }

    best = candidates[0]
    out_candidates = []
    for c in candidates:
        entry: dict[str, Any] = {
            "move": format_play(c, position.turn),
            "equity": c.equity,
        }
        # `GnCandidate.probs` describes the RESULTING position, so the
        # opponent, while `equity` on the same candidate is already the
        # mover's. Handing both out unmirrored puts two opposite points of
        # view side by side in one object, and a mirrored nested distribution
        # is still perfectly nested — nothing downstream can notice. Both
        # fields leave here as the mover's.
        entry["probs"] = (
            _probs_json(c.evaluation.mirrored()) if c.evaluation is not None else None
        )
        out_candidates.append(entry)

    result: dict[str, Any] = {
        "best_move": format_play(best, position.turn),
        "equity": best.equity,
        "candidates": out_candidates,
        "ply": applied_ply,
    }
    if best.evaluation is not None:
        result["probs"] = _probs_json(best.evaluation.mirrored())
    return result


# ── /v1/rollout ──────────────────────────────────────────────────────────


def handle_rollout(engine: Engine, body: dict) -> dict:
    xgid = body.get("xgid")
    require(isinstance(xgid, str) and xgid, "xgid manquant ou invalide")
    trials = body.get("trials", 1296)
    max_depth = body.get("max_depth", 0)
    seed = body.get("seed", 0)
    require(is_int(trials) and 1 <= trials <= 200_000, "trials doit être un entier entre 1 et 200000")
    require(is_int(max_depth) and max_depth >= 0, "max_depth doit être un entier >= 0")
    require(is_int(seed) and seed >= 0, "seed doit être un entier >= 0")

    try:
        position, _fields = codec.position_from_xgid(xgid)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    require(not position.is_over(), "position déjà terminée : rien à jouer")

    config = RolloutConfig(trials=trials, truncate=max_depth, seed=seed)
    try:
        result = run_rollout(engine.network, position, config)
    except RuntimeError as exc:
        raise ApiError(422, str(exc)) from exc

    return {
        "trials": result.trials,
        "equity": result.equity,
        "std_err": result.standard_error,
        # Meaningful only when max_depth == 0 (untruncated) — see gn_rollout.h:
        # a truncated trial ends on an evaluation, not an outcome, and the
        # frequency is then genuinely zero, not an approximation of one.
        "win_prob": result.frequencies[0],
    }


# ── /v1/cube ─────────────────────────────────────────────────────────────

_JACOBY_DEFAULT = True  # Not carried by this contract; documented assumption.


def _cube_owner(cube: int) -> CubeOwner:
    # A centred cube is always at value 1; anything higher means whoever is
    # weighing the double already owns it (the opponent could not have
    # doubled them to that value and left them still holding the option).
    return CubeOwner.CENTRED if cube <= 1 else CubeOwner.OWNED


def _match_state(decider_away: int, opponent_away: int, cube: int) -> MatchState | None:
    if decider_away <= 0 or opponent_away <= 0:
        return None  # money game: 0 is the "no match" sentinel, not "match won"
    state = MatchState(away_on_roll=decider_away, away_opponent=opponent_away, cube=cube, crawford=False)
    if not state.is_valid:
        raise ApiError(422, f"état de match non évaluable : {state}")
    return state


def _cube_triple(
    engine: Engine, evaluation: Evaluation, owner: CubeOwner, cube: int, state: MatchState | None
) -> tuple[CubeAction, float, float, float]:
    """(action, no_double, double_take, double_pass), all from the DOUBLER's
    own point of view, on ONE consistent scale: real points in money, `2*MWC-1`
    match equity in match play.

    `decide()` alone only reports `min(double_take, double_pass)` — exactly
    right for a verdict, not enough to report BOTH branches (Task 2.2 wants
    the XG-style ND/DT/DP triple). The two missing pieces are computed with
    the SAME public, tested functions `decide()` itself uses internally:

      * `double_pass` is the value of collecting the CURRENT stake outright —
        `1.0` per unit of cube in money (Janowski's constant, no computation
        needed); `state.after(cube, on_roll_wins=True)` in match, the exact
        call `gn_cube_decide` makes for its own `e_dp`.
      * `double_take` is `gn_cube_value` at cube OWNERSHIP OPPONENT — the
        doubler's own equity once the opponent holds the (now doubled) cube.
        Money: `gn_cube_value` returns the PER-UNIT-of-the-new-cube value, so
        ×2 restates it per unit of the ORIGINAL cube, matching `equity_no_double`'s
        own scale — exactly the ×2 `gn_cube_decide` applies internally.
        Match: `gn_cube_value` already returns `2*MWC-1` for the STATE IT IS
        GIVEN — passing a state whose `cube` is doubled makes that state's own
        level 0 equal the original state's level 1, which is exactly the
        doubled-stake node `gn_cube_decide` resolves for `e_dt`. No further
        scaling: the result is already the number this function reports.
    """
    decision = cube_decide(evaluation, owner, engine.efficiency[owner], state, jacoby=_JACOBY_DEFAULT)
    opp_efficiency = engine.efficiency[CubeOwner.OPPONENT]

    if state is None:
        no_double = decision.equity_no_double * cube
        double_take = 2.0 * cube_value(evaluation, CubeOwner.OPPONENT, opp_efficiency, None) * cube
        double_pass = 1.0 * cube
    else:
        doubled_state = replace(state, cube=state.cube * 2)
        no_double = 2.0 * decision.equity_no_double - 1.0
        double_take = cube_value(evaluation, CubeOwner.OPPONENT, opp_efficiency, doubled_state)
        double_pass = 2.0 * state.after(state.cube, on_roll_wins=True) - 1.0

    return decision.action, no_double, double_take, double_pass


def handle_cube(engine: Engine, body: dict) -> dict:
    xgid = body.get("xgid")
    kind = body.get("kind")
    require(isinstance(xgid, str) and xgid, "xgid manquant ou invalide")
    require(kind in ("double", "take"), "kind doit être 'double' ou 'take'")

    decider_away = body.get("decider_away", 0)
    opponent_away = body.get("opponent_away", 0)
    cube = body.get("cube", 1)
    decider_on_roll = bool(body.get("decider_on_roll", True))
    require(is_int(decider_away) and is_int(opponent_away), "decider_away/opponent_away doivent être des entiers")
    require(is_int(cube) and cube >= 1 and (cube & (cube - 1)) == 0, "cube doit être une puissance de deux >= 1")

    try:
        position, _fields = codec.position_from_xgid(xgid)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    require(not position.is_over(), "position déjà terminée : rien à décider")

    # `decider_away`/`opponent_away` name the AWAY SCORES OF THE DECIDER — the
    # responder for kind="take", not the doubler. Every cube computation below
    # is anchored on the DOUBLER's own perspective (gn_cube.h — the formulas
    # need only the doubler's own state), so for a "take" request the two
    # scores must be swapped back to the doubler's own view before building
    # the MatchState. Getting this backwards does not crash: it silently
    # scores the decision at the WRONG player's away score, and a symmetric
    # match (equal away scores) would never reveal it — see
    # `test_cube_take_uses_the_doublers_own_away_score` for the asymmetric
    # case that catches exactly this mistake.
    doubler_away, doubler_opponent_away = (
        (decider_away, opponent_away) if kind == "double" else (opponent_away, decider_away)
    )
    state = _match_state(doubler_away, doubler_opponent_away, cube)

    # Cube math is always taken from the DOUBLER's (on-roll) own perspective —
    # gn_cube.h: the formulas need only the doubler's own (W, L), the
    # opponent's side folds in by symmetry. `decider_on_roll` never enters
    # this call; it only decides whose distribution gets REPORTED below.
    doubler_eval = engine.network.evaluate(position)
    owner = _cube_owner(cube)
    action, no_double, double_take, double_pass = _cube_triple(engine, doubler_eval, owner, cube, state)

    decider_eval = doubler_eval if decider_on_roll else engine.network.evaluate(position.swapped_turn())

    result: dict[str, Any] = {
        "should_double": False,
        "too_good": False,
        "should_take": False,
        "no_double": 0.0,
        "double_take": 0.0,
        "double_pass": 0.0,
        "probs": _probs_json(decider_eval),
        "take": 0.0,
        "pass": 0.0,
    }

    if kind == "double":
        result["should_double"] = action in (CubeAction.DOUBLE_TAKE, CubeAction.DOUBLE_PASS)
        result["too_good"] = action == CubeAction.TOO_GOOD
        result["no_double"] = no_double
        result["double_take"] = double_take
        result["double_pass"] = double_pass
    else:  # "take" — the RESPONDER's own equities, the negation of the doubler's.
        result["should_take"] = double_take < double_pass
        result["take"] = -double_take
        result["pass"] = -double_pass

    return result


# ── HTTP plumbing ────────────────────────────────────────────────────────

ROUTES = {
    "/v1/eval": handle_eval,
    "/v1/rollout": handle_rollout,
    "/v1/cube": handle_cube,
}


#: #20 -- serializes every call into `engine` across the ThreadingServer's
#: worker threads.
#:
#: Root cause: `Network.evaluate`/`evaluate_batch`, `search_plays`, and
#: `run_rollout` are each, underneath, ONE `ctypes` call into the native
#: library (`gn_search_plays`, `gn_rollout`, ...). `ctypes.CDLL` releases the
#: GIL for the duration of such a call, and the C side reuses per-model
#: scratch buffers across calls (`NNModel.buf_a`/`buf_b` in
#: `vendor/backgammon-ai-engine/c_inference/nn_eval.c`, allocated once at load
#: time) rather than allocating fresh ones each time. A search or rollout
#: loops over `gn_evaluate` many times INSIDE that one C call, entirely
#: without returning to Python -- so a lock around only the Python-level
#: `Network.evaluate` wrapper would not protect that internal fanout. Two
#: threads inside the native code at once race on the same buffers and
#: corrupt each other's forward pass; `tests/test_serve_concurrency.py`
#: measured this at 682/800 (85%) responses corrupted with no lock.
#:
#: Serializing here, at the single seam every route already funnels through
#: (`handler(self.engine, body)`), covers every native entry point without
#: having to enumerate or keep up with each one individually. The cost is
#: real but small: 0-ply is ~86 us/eval (`docs/mesures/`), and
#: `tests/test_serve_concurrency.py` measures the actual throughput this
#: leaves under concurrent load -- a number, not an assumption.
_ENGINE_LOCK = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    engine: Engine  # set on the class by `main()` before serving
    #: Bumped to /2 when `/v1/eval` stopped handing out the opponent's
    #: distribution under the mover's equity. The ROUTE stays `/v1` — the old
    #: numbers were wrong, not a different contract someone could still want —
    #: but a client that cached a response, or a gold file recorded against
    #: the old server, is stale, and this header is what tells it apart.
    server_version = "gammonNet-serve/2"

    def log_message(self, fmt: str, *args) -> None:  # quieter, structured-ish
        sys.stderr.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {self.address_string()} {fmt % args}\n")

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        handler = ROUTES.get(self.path)
        if handler is None:
            self._write_json(404, {"error": f"route inconnue : {self.path}"})
            return

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > 1 << 20:
            self._write_json(400, {"error": "corps de requête manquant ou trop volumineux"})
            return
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("le corps doit être un objet JSON")
        except ValueError as exc:
            self._write_json(400, {"error": f"JSON invalide : {exc}"})
            return

        try:
            with _ENGINE_LOCK:
                result = handler(self.engine, body)
        except ApiError as exc:
            self._write_json(exc.status, {"error": exc.message})
            return
        except Exception as exc:  # noqa: BLE001 — never a silent 500 (CLAUDE.md)
            sys.stderr.write(f"erreur serveur non anticipée sur {self.path} : {exc!r}\n")
            self._write_json(500, {"error": "erreur interne"})
            return

        self._write_json(200, result)


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


# ── Entry point ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--pin", type=Path, default=DEFAULT_PIN, help="fichier d'épingle {version, sha256}")
    parser.add_argument("--weights", type=Path, default=None, help="surcharge le chemin du grand réseau")
    parser.add_argument("--prune", type=Path, default=None, help="surcharge le chemin du réseau d'élagage")
    parser.add_argument("--no-prune", action="store_true", help="désactive l'élagage même si le réseau est présent")
    parser.add_argument("--prune-k", type=int, default=None, help="candidats survivants à l'élagage (défaut : celui de l'épingle)")
    parser.add_argument(
        "--max-ply", type=int, default=MAX_SEARCH_PLY,
        help=f"plafond de profondeur pour /v1/eval, <= {MAX_SEARCH_PLY} (défaut : {MAX_SEARCH_PLY})",
    )
    parser.add_argument("--efficiency-file", type=Path, default=DEFAULT_EFFICIENCY_FILE)
    args = parser.parse_args(argv)

    pin = json.loads(args.pin.read_text())
    weights_path = args.weights or (args.pin.parent / pin["network_fp16"]["filename"])
    prune_path = args.prune or (args.pin.parent / pin["prune_fp16"]["filename"])
    prune_k = args.prune_k if args.prune_k is not None else pin.get("prune_k", 12)

    verify_pinned(weights_path, pin["network_fp16"]["sha256"], "réseau principal (network_fp16)")
    print(f"==> réseau principal conforme à l'épingle {pin['version']} : {weights_path}")

    prune_network: Network | None = None
    if not args.no_prune:
        try:
            verify_pinned(prune_path, pin["prune_fp16"]["sha256"], "réseau d'élagage (prune_fp16)")
            prune_network = Network.load(prune_path)
            print(f"==> réseau d'élagage conforme à l'épingle {pin['version']} : {prune_path}")
        except SystemExit as exc:
            print(f"    élagage désactivé : {exc}")

    network = Network.load(weights_path)
    efficiency = load_efficiency(args.efficiency_file)

    max_ply = max(0, min(args.max_ply, MAX_SEARCH_PLY))
    engine = Engine(
        network=network, prune_network=prune_network, prune_k=prune_k,
        efficiency=efficiency, max_ply=max_ply,
    )
    Handler.engine = engine

    httpd = ThreadingServer((args.host, args.port), Handler)
    print(f"==> gammonNet serve : http://{args.host}:{args.port}  (0-ply par défaut, {max_ply}-ply au plus)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        network.close()
        if prune_network is not None:
            prune_network.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

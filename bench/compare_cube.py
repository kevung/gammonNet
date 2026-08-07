#!/usr/bin/env python3
"""T34 §6.3 — our cube decisions against GNU Backgammon's, at money and at
four match scores.

## Step 0 — the semantics of `gnubg.cfevaluate`, established by probe

`tools/gnubg_server.py:op_cfeval` returns whatever `gnubg.cfevaluate` renders,
**uninterpreted** (see its docstring: "T34 en fixera le sens"). Before any
measurement, that meaning was pinned down here, by probe and by the only two
sources `CLAUDE.md` allows for this ("le manuel de GNU Backgammon" and the
tool's own public `help()` output) — never by reading gnubg's source.

**`help(gnubg.cubeinfo)`, `help(gnubg.cfevaluate)`** (run once, transcribed in
`docs/mesures/2026-08-07-T34-comparaison-gnubg.md`, not re-derived here) gave
the actual signatures — and caught a real bug: `tools/gnubg_server.py`'s
`make_cubeinfo` was calling `gnubg.cubeinfo()` with **nine** positional
arguments where the tool takes **seven** (`jacoby`/`beavers` are not
positional args — they live in the dictionary `cubeinfo()` *returns*, which is
directly the `cube-info` structure `cfevaluate` consumes). Nine args where
seven are expected does not raise a Python exception: the whole gnubg process
dies wordlessly, which `GnubgSession._read` can only report as "closed its
output without answering" — indistinguishable, from here, from any other
crash. Nothing had exercised `state=` before T34, so nobody had hit it. Fixed
in `tools/gnubg_server.py` (`make_cubeinfo`), and covered here rather than
re-explained: see that function's docstring for the fix itself.

**What the probe then established, empirically, on constructed positions**:

* `cubeinfo(cube, cube_owner, move, match_to, score, crawford, bgv)` — 7
  positional args. `cube_owner`: `-1` centred, matches `move` = I own it,
  differs from `move` = opponent owns it. `move` fixed at `1` throughout this
  module (arbitrary but consistent) — a symmetric starting position confirmed
  `move` alone changes nothing when the cube is centred, as expected.
* `score` is `(points scored by player 0, points scored by player 1)`, i.e.
  `score[move]` is the **mover's own** score. Confirmed with the post-Crawford
  systematic double: mover 2-away, opponent 1-away, `crawford=0` — only the
  score assignment `score = (match_to - away_opponent, match_to - away_mover)`
  (with `move=1`) reproduces gnubg recommending "Double" at every `p` tested;
  the flipped assignment gave "Never double (dead cube)" everywhere, which is
  not the systematic-double signature and would have been silently wrong.
* `matchto=0` defaults `jacoby=1` in the dictionary `cubeinfo()` returns; any
  `matchto>0` defaults it to `0`. That is gnubg's *own* convention for "Jacoby
  applies to money, not to match play" — the same rule `docs/specs/t34-videau-
  spec.md` §4 states for our model, found here without reading either side's
  source.
* A gammon-certain position (found by searching our own network's `corpus()`
  output for the highest `win_gammon`) flips gnubg's recommendation from "Too
  good to double, pass" (no Jacoby) to "Double, pass" (Jacoby on) for a
  centred cube — the mechanism `test_cube.py::
  test_jacoby_removes_gammon_value_from_the_no_double_branch` checks on our
  side, seen independently on theirs.

**`cfevaluate` return tuple**, per `help()`: `(optimal, nodouble, take, drop,
recommendation: int, recommendationtext: str)`. Only the string is used here —
the int code is gnubg-internal and undocumented beyond the string it prints;
mapping the string is what `help()` explicitly hands us ("recommendationtext")
and what the task calls "probablement suffisant". Distinct `(code, text)`
pairs actually observed during the probe (4000+ calls across bearoff
positions spanning `p` from ~0 to ~1, both Jacoby settings, all three cube
owners, plus Crawford and post-Crawford scores):

    0  'Double, take'
    1  'Double, pass'
    2  'No double, take'
    4  'Too good to double, pass'
    7  'Redouble, take'
    8  'Redouble, pass'
    9  'No redouble, take'
    11 'Too good to redouble, pass'
    13 'Never double, take (dead cube)'
    15 'Cube not available'

`classify_gnubg_verdict` below maps every one of these (and any future string
built from the same vocabulary) to our four-verdict `CubeAction`, and raises
loudly — never silently defaults — on a string it does not recognise, per
`CLAUDE.md` rule 2.

## The corpus, and what "compare" means here

2000 contact positions (`bench/decision_loss.corpus`, seed 20260807) + 1000
bearoff positions (`bench/exact_gap.random_bearoff`, seed 20260808), reused
verbatim — not regenerated. For each position, two cube states with a real
decision to compare: **centred** and **owned by the player on roll**. A third
state, **opponent owns the cube**, has no decision to compare (nobody can
double) — both engines are checked to agree that no double is possible, on a
small separate sample, never folded into the confusion matrix.

Five contexts per owner state: **money** (Jacoby active both sides) and the
four match scores the spec names: 2-away/2-away, 4-away/2-away, 2-away/4-away,
and post-Crawford (mover 2-away, opponent 1-away, `crawford=False` — the
Crawford game itself is not one of the four; it is covered separately by
`tests/test_cube.py::test_crawford_never_doubles`, which is a pure property of
our own model and needs no external oracle). Cube value fixed at 1 throughout
— this bench does not exercise redoubles to higher cube values; a named scope
limitation, not an oversight.

**Efficiency `x`**: read from `docs/mesures/t34-efficacite.json`, never
hard-coded — `owned` for the OWNED state, `centered` for CENTRED, matching
which column of the bilateral table each state's decision was fit against.

## What "agreement" does and does not mean

Per `docs/specs/t34-videau-spec.md` §6.3 and `CLAUDE.md` rule 2: this measures
**resemblance**, not superiority. No rollout-based arbiter exists yet that
could say which engine is *right* on a disagreement (cubeful rollouts are
future work, named in the report, not attempted here). The global agreement
rate is inflated by the trivial NO_DOUBLE/NO_DOUBLE positions that dominate
any corpus; the number that matters is the rate on the **contested subset**
(at least one engine says something other than NO_DOUBLE) — reported
separately, always.

Usage:
    python bench/compare_cube.py --pilot 8
    python bench/compare_cube.py --contact 2000 --bearoff 1000 --workers 26 \\
        --out docs/mesures/t34-comparaison.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.cube import CubeAction, CubeOwner, decide  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

from decision_loss import corpus as contact_corpus  # noqa: E402
from exact_gap import random_bearoff  # noqa: E402

PROGRESS = Path(os.environ.get("T34CMP_PROGRESS", "/tmp/t34cmp-progress.log"))
MODEL = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")
EFFICIENCY_FILE = ROOT / "docs" / "mesures" / "t34-efficacite.json"
DATABASE = str(ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd")

CONTACT_SEED = 20260807
BEAROFF_SEED = 20260808

#: (name, MatchState-or-None). `None` means money. Crawford itself is not
#: here -- see the module docstring for why.
CONTEXTS: tuple[tuple[str, MatchState | None], ...] = (
    ("money", None),
    ("match_2a2a", MatchState(away_on_roll=2, away_opponent=2, cube=1, crawford=False)),
    ("match_4a2a", MatchState(away_on_roll=4, away_opponent=2, cube=1, crawford=False)),
    ("match_2a4a", MatchState(away_on_roll=2, away_opponent=4, cube=1, crawford=False)),
    ("match_postcrawford",
     MatchState(away_on_roll=2, away_opponent=1, cube=1, crawford=False)),
)

OWNERS_COMPARED = (CubeOwner.OWNED, CubeOwner.CENTRED)

_GNUBG_OWNER_OF = {CubeOwner.CENTRED: -1, CubeOwner.OWNED: 1, CubeOwner.OPPONENT: 0}


# ── Step 0 — the verdict-string mapping the probe established ─────────

#: Every (code, text) pair actually seen during the probe -- kept as a
#: constant for `tests/` and for anyone auditing this file, NOT consulted by
#: the classifier itself (which matches on substrings of the text, so it also
#: covers any variant built from the same vocabulary this module hasn't seen
#: yet, e.g. beaver-suffixed texts, without needing to be re-probed --
#: provided the vocabulary itself does not change).
OBSERVED_GNUBG_VERDICTS: frozenset[tuple[int, str]] = frozenset({
    (0, "Double, take"),
    (1, "Double, pass"),
    (2, "No double, take"),
    (4, "Too good to double, pass"),
    (7, "Redouble, take"),
    (8, "Redouble, pass"),
    (9, "No redouble, take"),
    (11, "Too good to redouble, pass"),
    (13, "Never double, take (dead cube)"),
    (15, "Cube not available"),
})


def classify_gnubg_verdict(text: str) -> CubeAction:
    """Map gnubg's `recommendationtext` to our four-verdict `CubeAction`.

    Order matters: "too good" must be checked before the generic
    double/pass-or-take rule, since "Too good to double, pass" would
    otherwise match the DOUBLE_PASS rule. Everything not recognised raises --
    per `CLAUDE.md` rule 2, an unmapped string is refused, never guessed at.
    """
    lowered = text.lower()
    if "too good" in lowered:
        return CubeAction.TOO_GOOD
    if "cube not available" in lowered:
        return CubeAction.NO_DOUBLE
    if "never double" in lowered:
        return CubeAction.NO_DOUBLE
    if lowered.startswith("no double") or lowered.startswith("no redouble"):
        return CubeAction.NO_DOUBLE
    has_double_word = "double" in lowered or "redouble" in lowered
    if has_double_word and "pass" in lowered:
        return CubeAction.DOUBLE_PASS
    if has_double_word and "take" in lowered:
        return CubeAction.DOUBLE_TAKE
    raise ValueError(
        f"gnubg verdict string not in the mapping established by the T34 "
        f"probe: {text!r}. Refused rather than guessed -- see the module "
        f"docstring for the probe and extend the classifier deliberately."
    )


def gnubg_state(owner: CubeOwner, match: MatchState | None, jacoby: bool) -> dict:
    """Build the `state` dict `GnubgSession.cubeful` forwards to `cubeinfo`.

    `move` is fixed at 1 (established by probe: arbitrary but must be
    consistent with the score assignment below). For a match state,
    `score[move]` must be the mover's own score -- also established by probe,
    against the post-Crawford systematic-double signature.
    """
    state = {"cube": 1, "cube_owner": _GNUBG_OWNER_OF[owner], "move": 1}
    if match is None:
        state.update(match_to=0, score=(0, 0), crawford=0, jacoby=int(jacoby))
    else:
        match_to = max(match.away_on_roll, match.away_opponent)
        state.update(
            match_to=match_to,
            score=(match_to - match.away_opponent, match_to - match.away_on_roll),
            crawford=int(match.crawford),
        )
    return state


def load_efficiency() -> dict[CubeOwner, float]:
    """`x` by cube state, read from the T34 fit -- never hard-coded here."""
    payload = json.loads(EFFICIENCY_FILE.read_text())
    results = payload["results"]
    return {
        CubeOwner.OWNED: results["owned"]["x"],
        CubeOwner.CENTRED: results["centered"]["x"],
    }


def build_corpus(contact_count: int, bearoff_count: int) -> list[tuple[Position, str]]:
    """The 3000-position corpus: contact positions, then bearoff positions.

    Both generators are reused verbatim from their own tasks (T36, T38) --
    see the module docstring for why (a corpus is versioned once, reused, not
    quietly rebuilt with a slightly different recipe every time it's needed).
    """
    network = Network.load(MODEL)
    contact = [(position, "contact")
               for position, _d1, _d2 in contact_corpus(contact_count, CONTACT_SEED, network)]

    from gammonnet.bearoff import TwoSidedBearoff

    rng = random.Random(BEAROFF_SEED)
    table = TwoSidedBearoff(DATABASE)
    bearoff = [(random_bearoff(rng, table), "bearoff") for _ in range(bearoff_count)]
    table.close()

    return contact + bearoff


# ── The measurement, per worker ────────────────────────────────────────


def measure(payload):
    (model, efficiency, positions, progress) = payload

    from gammonnet.gnubg_engine import GnubgSession

    network = Network.load(model)
    session = GnubgSession()

    boards = [gb.to_gnubg(position) for position, _origin in positions]
    evaluations = [network.evaluate(position) for position, _origin in positions]
    position_ids = [codec.position_id(position) for position, _origin in positions]

    rows = []
    for context_name, match in CONTEXTS:
        jacoby = match is None
        for owner in OWNERS_COMPARED:
            state = gnubg_state(owner, match, jacoby)
            gnubg_results = session.cubeful(boards, plies=0, state=state)

            for i, (position, origin) in enumerate(positions):
                our = decide(evaluations[i], owner, efficiency[owner],
                             state=match, jacoby=jacoby)
                g_optimal, g_nodouble, g_take, g_drop, _g_code, g_text = gnubg_results[i]

                gnubg_action = classify_gnubg_verdict(g_text)
                gnubg_margin = g_nodouble - min(g_take, g_drop)
                our_margin = our.equity_no_double - our.equity_double

                rows.append({
                    "position_id": position_ids[i],
                    "turn": position.turn,
                    "origin": origin,
                    "context": context_name,
                    "owner": owner.name,
                    "our_action": our.action.name,
                    "our_margin": our_margin,
                    "our_equity_no_double": our.equity_no_double,
                    "our_equity_double": our.equity_double,
                    "gnubg_action": gnubg_action.name,
                    "gnubg_margin": gnubg_margin,
                    "gnubg_optimal": g_optimal,
                    "gnubg_nodouble": g_nodouble,
                    "gnubg_take": g_take,
                    "gnubg_drop": g_drop,
                    "gnubg_text": g_text,
                    "agree": our.action == gnubg_action,
                })

                if progress:
                    with open(progress, "a") as fh:
                        fh.write("x\n")

    session.close()
    return rows


def opponent_sanity_check(positions: list[tuple[Position, str]], efficiency) -> dict:
    """A small sample where NOBODY can double -- both engines must agree that
    no double is possible. Never folded into the confusion matrix: there is
    no real decision here, only a structural check.
    """
    from gammonnet.gnubg_engine import GnubgSession

    network = Network.load(MODEL)
    session = GnubgSession()

    boards = [gb.to_gnubg(position) for position, _origin in positions]
    evaluations = [network.evaluate(position) for position, _origin in positions]

    checked = 0
    agreed = 0
    contexts_checked = []
    for context_name, match in CONTEXTS[:2]:  # money + one match score suffices
        jacoby = match is None
        state = gnubg_state(CubeOwner.OPPONENT, match, jacoby)
        gnubg_results = session.cubeful(boards, plies=0, state=state)
        for i, (position, _origin) in enumerate(positions):
            our = decide(evaluations[i], CubeOwner.OPPONENT,
                         efficiency[CubeOwner.CENTRED], state=match, jacoby=jacoby)
            gnubg_action = classify_gnubg_verdict(gnubg_results[i][5])
            checked += 1
            if our.action == CubeAction.NO_DOUBLE and gnubg_action == CubeAction.NO_DOUBLE:
                agreed += 1
        contexts_checked.append(context_name)

    session.close()
    return {"checked": checked, "agreed": agreed, "contexts": contexts_checked}


# ── Statistics ───────────────────────────────────────────────────────


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval -- honest where the normal approximation is not, on a
    rate near 0 or 1 with a modest sample. Reused verbatim from
    `bench/analyse_filter.py`.
    """
    if total == 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def confusion_matrix(rows: list[dict]) -> dict[str, dict[str, int]]:
    actions = [a.name for a in CubeAction]
    matrix = {a: {b: 0 for b in actions} for a in actions}
    for row in rows:
        matrix[row["our_action"]][row["gnubg_action"]] += 1
    return matrix


def agreement_stats(rows: list[dict]) -> dict:
    n = len(rows)
    agreed = sum(1 for r in rows if r["agree"])
    low, high = wilson(agreed, n)
    return {"n": n, "agreed": agreed, "rate": agreed / n if n else float("nan"),
            "ci95": [low, high]}


# ── Driver ──────────────────────────────────────────────────────────


def run(positions: list[tuple[Position, str]], efficiency, workers: int,
        progress: Path | None) -> tuple[list[dict], float]:
    from concurrent.futures import ProcessPoolExecutor

    workers = max(1, min(workers, len(positions)))
    chunks = [positions[i::workers] for i in range(workers)]
    payloads = [(MODEL, efficiency, chunk, progress) for chunk in chunks if chunk]

    start = time.perf_counter()
    if len(payloads) == 1:
        gathered = [measure(payloads[0])]
    else:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            gathered = list(pool.map(measure, payloads))
    elapsed = time.perf_counter() - start

    rows = [row for part in gathered for row in part]
    return rows, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contact", type=int, default=2000)
    parser.add_argument("--bearoff", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--pilot", type=int, default=8,
                        help="positions used for the plumbing/throughput pilot; 0 skips it")
    parser.add_argument("--sanity-sample", type=int, default=60,
                        help="sample size for the opponent-owns-the-cube sanity check")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    print("T34 §6.3 — cube decisions against GNU Backgammon")
    print(f"  corpus: {args.contact} contact (seed {CONTACT_SEED}) + "
          f"{args.bearoff} bearoff (seed {BEAROFF_SEED})")
    print(f"  contexts: {', '.join(name for name, _ in CONTEXTS)}")
    print(f"  progress: {PROGRESS}\n", flush=True)

    efficiency = load_efficiency()
    print(f"  efficiency x: owned={efficiency[CubeOwner.OWNED]:.3f} "
          f"centred={efficiency[CubeOwner.CENTRED]:.3f}\n", flush=True)

    build_start = time.perf_counter()
    positions = build_corpus(args.contact, args.bearoff)
    print(f"  corpus built in {time.perf_counter() - build_start:.0f} s "
          f"({len(positions)} positions)\n", flush=True)

    if PROGRESS.exists():
        PROGRESS.unlink()

    if args.pilot:
        pilot_positions = positions[:args.pilot]
        pilot_rows, pilot_elapsed = run(pilot_positions, efficiency, workers=1, progress=None)
        per_position = pilot_elapsed / len(pilot_positions)
        projected = per_position * len(positions) / max(1, args.workers)
        print(f"pilot: {len(pilot_positions)} positions, {len(pilot_rows)} decisions, "
              f"{pilot_elapsed:.1f} s serial -> {per_position:.3f} s/position")
        print(f"projection for {len(positions)} positions on {args.workers} workers: "
              f"~{projected / 60:.1f} min (MEASURED pilot, extrapolated volume -- "
              f"see CLAUDE.md rule 3)\n", flush=True)

    print("running the full corpus...", flush=True)
    rows, elapsed = run(positions, efficiency, workers=args.workers, progress=PROGRESS)
    print(f"{len(rows)} decisions in {elapsed / 60:.1f} min on {args.workers} workers "
          f"(MEASURED, not extrapolated)\n")

    print("opponent-owns-the-cube sanity check...", flush=True)
    sanity_positions = positions[:args.sanity_sample]
    sanity = opponent_sanity_check(sanity_positions, efficiency)
    print(f"  {sanity['agreed']}/{sanity['checked']} agree that no double is possible "
          f"({sanity['contexts']})\n")

    global_stats = agreement_stats(rows)
    contested_rows = [r for r in rows
                      if r["our_action"] != "NO_DOUBLE" or r["gnubg_action"] != "NO_DOUBLE"]
    contested_stats = agreement_stats(contested_rows)
    matrix = confusion_matrix(rows)

    print(f"global agreement:    {global_stats['agreed']}/{global_stats['n']} = "
          f"{global_stats['rate']*100:.1f}% [{global_stats['ci95'][0]*100:.1f} ; "
          f"{global_stats['ci95'][1]*100:.1f}]")
    print(f"contested agreement: {contested_stats['agreed']}/{contested_stats['n']} = "
          f"{contested_stats['rate']*100:.1f}% [{contested_stats['ci95'][0]*100:.1f} ; "
          f"{contested_stats['ci95'][1]*100:.1f}]  "
          f"({contested_stats['n']}/{global_stats['n']} decisions are contested)\n")

    print("confusion matrix (rows = ours, cols = gnubg):")
    actions = [a.name for a in CubeAction]
    print(f"{'':16}" + "".join(f"{a:>14}" for a in actions))
    for a in actions:
        print(f"{a:16}" + "".join(f"{matrix[a][b]:>14}" for b in actions))
    print()

    per_context = []
    for context_name, _match in CONTEXTS:
        for owner in OWNERS_COMPARED:
            subset = [r for r in rows if r["context"] == context_name
                     and r["owner"] == owner.name]
            stats = agreement_stats(subset)
            sub_contested = [r for r in subset
                             if r["our_action"] != "NO_DOUBLE"
                             or r["gnubg_action"] != "NO_DOUBLE"]
            contested = agreement_stats(sub_contested)
            per_context.append({
                "context": context_name, "owner": owner.name,
                "global": stats, "contested": contested,
            })
            print(f"  {context_name:20} {owner.name:8} global "
                  f"{stats['rate']*100:5.1f}%  contested {contested['rate']*100:5.1f}% "
                  f"(n_contested={contested['n']})")

    worst = sorted((r for r in rows if not r["agree"]),
                   key=lambda r: abs(r["gnubg_margin"]), reverse=True)[:20]
    print("\nworst 20 disagreements by |gnubg margin|:")
    for r in worst:
        print(f"  {r['position_id']:16} {r['context']:20} {r['owner']:8} "
              f"ours={r['our_action']:12}({r['our_margin']:+.4f})  "
              f"gnubg={r['gnubg_action']:12}({r['gnubg_margin']:+.4f}) "
              f"[{r['gnubg_text']}]")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "T34-6.3",
            "seed_contact": CONTACT_SEED,
            "seed_bearoff": BEAROFF_SEED,
            "positions": {"contact": args.contact, "bearoff": args.bearoff,
                         "total": len(positions)},
            "efficiency": {"owned": efficiency[CubeOwner.OWNED],
                          "centered": efficiency[CubeOwner.CENTRED]},
            "contexts": [name for name, _ in CONTEXTS],
            "elapsed_seconds": elapsed,
            "workers": args.workers,
            "opponent_sanity": sanity,
            "global_agreement": global_stats,
            "contested_agreement": contested_stats,
            "confusion_matrix": matrix,
            "per_context": per_context,
            "worst_disagreements": worst,
            "observed_gnubg_verdicts": sorted(list(OBSERVED_GNUBG_VERDICTS)),
        }, indent=2) + "\n")
        print(f"\nwritten to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

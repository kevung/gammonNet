#!/usr/bin/env python3
"""T35 — is GNU Backgammon being driven correctly at score? Its API path
against its own command line.

## Why this probe exists

The T35 campaign measures two halves against the same opponent at the same
setting. They disagree, and the disagreement is large:

    money, 50 000 pairs, complete   -0.0119 ppg  [-0.0310 ; +0.0074]
    match, 23 988 pairs, partial     56.42 % MWC [56.01 ; 56.84]

Even in money, six points of match-winning chance in match play. Split by
starting score, the match edge is concentrated exactly where the cube lives:

    DMP (1-away/1-away), dead cube      50.94 %   <- chequer play alone: even
    cube alive                          56.34 %
    post-Crawford                       60.25 %

Chequer play is bare, which agrees with the money half. So the whole match
edge comes from cube decisions AT SCORE -- either because our cube handling
(exact MET, 2-ply cube) really is better there, or because the opponent we
drive through `cfevaluate` is not the opponent GNU Backgammon actually is at
score. Publishing "stronger than gnubg" on the second reading would be the
silent-error mode `CLAUDE.md` rule 2 exists to prevent.

Only a measurement separates them, and this is it.

## What is compared

For each position, cube state and score, the SAME question is put to gnubg
twice, and the two answers are compared:

* **`api`** -- the campaign's own path, verbatim: `GnubgCubePlayer._cube_answer`,
  i.e. `cfevaluate` under a `cubeinfo` built by `gnubg_engine.gnubg_state`.
  That helper compresses the match: it tells gnubg `match_to = max(away)` and
  a score derived from it, because a match equity table is indexed by away
  scores. Whether that compression is really free is one of the things
  measured here, not assumed.
* **`cli_true`** -- gnubg's own command-line interface, with the campaign's
  real match set up: `new match 7`, the real score, the real Crawford flag,
  the cube value and owner placed on the board, then `hint`.
* **`cli_compressed`** -- the same command line, but with the match length
  compressed the way the API path describes it. `cli_true` vs
  `cli_compressed` isolates the compression; `api` vs `cli_true` isolates
  everything else (the `cubeinfo` conventions, the score orientation, the
  cube owner mapping, the verdict string).

In money -- the control half, where the campaign measures no anomaly -- the
two CLI variants are `cli_nobeaver` and `cli_beaver` instead: `cubeinfo()`
picks its own default for beavers when `matchto = 0` and the campaign never
overrides it, so rather than guess which one it is, both are run and the
agreement says.

## What agreement does and does not mean

This measures whether *we are asking gnubg the right question*, not who is
right about the cube. A disagreement is a defect in the harness. Perfect
agreement does NOT prove the +6 MWC edge is real -- it removes the harness as
its explanation, which is what T35 needs before it can publish a verdict.

The corpus is the one T34 used for the same kind of comparison
(`bench/decision_loss.corpus`, seed 20260807, plus `exact_gap.random_bearoff`,
seed 20260808), reused verbatim rather than rebuilt. It is NOT the campaign's
own position distribution -- a named limitation: it spans the equity range
where cube decisions are contested, which is what the question needs, but the
weight of each cell is not the campaign's.

Usage:
    python bench/probe_gnubg_at_score.py --pilot
    python bench/probe_gnubg_at_score.py --contact 100 --bearoff 40 --workers 2 \\
        --out docs/mesures/t35-sonde-videau-au-score.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.gnubg_engine import (  # noqa: E402
    GnubgSession,
    classify_gnubg_verdict,
    gnubg_state,
)
from gammonnet.gnubg_cli import Gnubg  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

MODEL = str(ROOT / "models" / "cubeless_prob5_512_512_256_128.bin")
DATABASE = str(ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd")
CONTACT_SEED = 20260807
BEAROFF_SEED = 20260808

#: The campaign's opponent setting, named rather than implied (PLAN.md T35):
#: gnubg cube decisions at 2 ply with its pruning nets -- the same numbers
#: `bench/run_t35.py --gnubg-ply 2` gives `GnubgCubePlayer`.
CUBE_PLY = 2
PRUNE = 1
#: The campaign's match length.
MATCH_LENGTH = 7

#: The cube value probed for each ownership state. A centred cube at 1 is the
#: opening double; an owned cube at 2 is the redouble -- the case the campaign
#: reaches constantly (its biggest cube in match play is 8) and the one that
#: exercises gnubg's dead-cube logic at score.
CUBE_OF = {CubeOwner.CENTRED: 1, CubeOwner.OWNED: 2}
#: `gnubg_state` puts the mover on `move = 1`; the command line must therefore
#: put the mover on player 1, and the cube owner mapping follows.
CLI_OWNER = {CubeOwner.CENTRED: None, CubeOwner.OWNED: 1, CubeOwner.OPPONENT: 0}
CLI_MOVER = 1
OWNERS = (CubeOwner.CENTRED, CubeOwner.OWNED)


@dataclass(frozen=True)
class Context:
    """A score to put the same question at. `away_mover is None` means money."""

    name: str
    away_mover: int | None = None
    away_opponent: int | None = None
    crawford: bool = False

    @property
    def money(self) -> bool:
        return self.away_mover is None

    def match_state(self, cube: int) -> MatchState | None:
        if self.money:
            return None
        return MatchState(away_on_roll=self.away_mover,
                          away_opponent=self.away_opponent,
                          cube=cube, crawford=self.crawford)


#: Money is the control. The cube-alive cells are where the campaign's edge
#: sits; the post-Crawford cells are where it peaks; the last three are
#: structural -- nobody can double, and both paths must say so.
CONTEXTS: tuple[Context, ...] = (
    Context("money"),
    Context("2a2a", 2, 2),
    Context("3a5a", 3, 5),
    Context("5a3a", 5, 3),
    Context("4a4a", 4, 4),
    Context("7a7a", 7, 7),
    Context("postcrawford_2a1a", 2, 1),
    Context("postcrawford_4a1a", 4, 1),
    Context("postcrawford_6a1a", 6, 1),
    Context("postcrawford_leader_1a3a", 1, 3),
    Context("crawford_2a1a", 2, 1, crawford=True),
    Context("crawford_leader_1a2a", 1, 2, crawford=True),
)


def build_corpus(contact_count: int, bearoff_count: int) -> list[tuple[Position, str]]:
    """The T34 corpus, reused verbatim -- see the module docstring."""
    from decision_loss import corpus as contact_corpus
    from exact_gap import random_bearoff
    from gammonnet.bearoff import TwoSidedBearoff

    positions: list[tuple[Position, str]] = []
    if contact_count:
        network = Network.load(MODEL)
        positions += [(position, "contact") for position, _d1, _d2
                      in contact_corpus(contact_count, CONTACT_SEED, network)]
    if bearoff_count:
        rng = random.Random(BEAROFF_SEED)
        table = TwoSidedBearoff(DATABASE)
        positions += [(random_bearoff(rng, table), "bearoff")
                      for _ in range(bearoff_count)]
        table.close()
    return positions


# ── The command-line side ──────────────────────────────────────────────


def cli_variants(context: Context):
    """The command-line setups to compare against the API path, by context."""

    def match_setup(length: int):
        def setup(cli: Gnubg) -> None:
            cli.new_match(length)
            # `score` is what each player HAS scored; player 1 is the mover,
            # exactly as `gnubg_state` describes it to `cubeinfo`.
            cli.set_score(length - context.away_opponent,
                          length - context.away_mover, length)
            if (context.away_mover == 1) != (context.away_opponent == 1):
                cli.set_crawford(context.crawford)
            cli.set_turn(CLI_MOVER)
        return setup

    def money_setup(beavers: bool):
        def setup(cli: Gnubg) -> None:
            cli.new_money_session(jacoby=True, beavers=beavers)
            cli.set_turn(CLI_MOVER)
        return setup

    if context.money:
        return (("cli_nobeaver", money_setup(False)),
                ("cli_beaver", money_setup(True)))
    compressed = max(context.away_mover, context.away_opponent)
    variants = [("cli_true", match_setup(MATCH_LENGTH))]
    if compressed != MATCH_LENGTH:
        variants.append(("cli_compressed", match_setup(compressed)))
    return tuple(variants)


def takes_from_text(action: str) -> bool | None:
    """The take/pass half of gnubg's verdict, as the string carries it."""
    lowered = action.lower()
    if "take" in lowered:
        return True
    if "pass" in lowered:
        return False
    return None


# ── The measurement, per worker ────────────────────────────────────────


def measure(payload):
    index, positions = payload
    boards = [gb.to_gnubg(position) for position, _origin in positions]
    ids = [codec.position_id(position) for position, _origin in positions]

    session = GnubgSession()
    cli = Gnubg(manual=True, cube_ply=CUBE_PLY, cube_prune=bool(PRUNE))

    rows: list[dict] = []
    for context in CONTEXTS:
        cells: dict[tuple[int, str], dict] = {}

        # The API path: one call per (owner, context) for the whole chunk --
        # this is the campaign's own question, asked the campaign's own way.
        for owner in OWNERS:
            cube = CUBE_OF[owner]
            match = context.match_state(cube)
            state = gnubg_state(owner, match, jacoby=match is None, cube=cube)
            values = session.cubeful(boards, plies=CUBE_PLY, prune=PRUNE,
                                     state=state)
            for i, value in enumerate(values):
                _optimal, no_double, take, drop, _code, text = value
                cells[(i, owner.name)] = {
                    "position_id": ids[i],
                    "origin": positions[i][1],
                    "context": context.name,
                    "owner": owner.name,
                    "cube": cube,
                    "api_action": str(text),
                    "api_verdict": classify_gnubg_verdict(str(text)).name,
                    "api_no_double": float(no_double),
                    "api_take": float(take),
                    "api_drop": float(drop),
                    # The campaign's own take rule, verbatim from
                    # `GnubgCubePlayer.accepts_double`.
                    "api_takes": float(take) < float(drop),
                    "api_state": state,
                }

        # The command-line side: the match is set up once per variant, the
        # cube and the board per position.
        for variant, setup in cli_variants(context):
            setup(cli)
            for owner in OWNERS:
                for i, (position, _origin) in enumerate(positions):
                    hint = cli.cube_hint(position, cube=CUBE_OF[owner],
                                         owner=CLI_OWNER[owner])
                    cell = cells[(i, owner.name)]
                    cell[f"{variant}_action"] = hint.action
                    cell[f"{variant}_verdict"] = (
                        classify_gnubg_verdict(hint.action).name
                        if hint.available else "NO_DOUBLE")
                    cell[f"{variant}_available"] = hint.available
                    cell[f"{variant}_no_double"] = hint.no_double
                    cell[f"{variant}_take"] = hint.double_take
                    cell[f"{variant}_drop"] = hint.double_pass
                    cell[f"{variant}_takes"] = (takes_from_text(hint.action)
                                                if hint.available else None)

        rows.extend(cells.values())
        print(f"  [worker {index}] {context.name} done", file=sys.stderr,
              flush=True)

    cli.close()
    session.close()
    return rows


# ── The report ─────────────────────────────────────────────────────────


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / total
                           + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def compare(rows: list[dict], reference: str) -> dict:
    """API against one command-line variant, per context."""
    out: dict[str, dict] = {}
    for row in rows:
        key = f"{reference}_verdict"
        if key not in row:
            continue
        cell = out.setdefault(row["context"], {
            "positions": 0, "verdict_agree": 0, "take_agree": 0,
            "take_comparable": 0, "max_equity_gap": 0.0, "disagreements": [],
        })
        cell["positions"] += 1
        agree = row["api_verdict"] == row[key]
        cell["verdict_agree"] += int(agree)

        api_takes, cli_takes = row["api_takes"], row[f"{reference}_takes"]
        if cli_takes is not None and row[f"{reference}_available"]:
            cell["take_comparable"] += 1
            cell["take_agree"] += int(api_takes == cli_takes)

        for ours, theirs in (("api_no_double", f"{reference}_no_double"),
                             ("api_take", f"{reference}_take"),
                             ("api_drop", f"{reference}_drop")):
            if row.get(theirs) is not None:
                gap = abs(row[ours] - row[theirs])
                cell["max_equity_gap"] = max(cell["max_equity_gap"], gap)

        if not agree and len(cell["disagreements"]) < 12:
            cell["disagreements"].append({
                "position_id": row["position_id"], "owner": row["owner"],
                "cube": row["cube"], "api": row["api_action"],
                reference: row[f"{reference}_action"],
                "api_equities": [row["api_no_double"], row["api_take"],
                                 row["api_drop"]],
                "cli_equities": [row.get(f"{reference}_no_double"),
                                 row.get(f"{reference}_take"),
                                 row.get(f"{reference}_drop")],
            })
    return out


def print_table(title: str, table: dict) -> None:
    print(f"\n── {title} ──")
    print(f"  {'contexte':26s} {'n':>6s} {'verdicts':>16s} "
          f"{'take/pass':>16s} {'écart équité':>13s}")
    for context, cell in table.items():
        low, high = wilson(cell["verdict_agree"], cell["positions"])
        rate = cell["verdict_agree"] / cell["positions"] * 100
        takes = (f"{cell['take_agree']}/{cell['take_comparable']}"
                 if cell["take_comparable"] else "—")
        print(f"  {context:26s} {cell['positions']:6d} "
              f"{rate:7.2f}% [{low*100:5.1f};{high*100:5.1f}] "
              f"{takes:>16s} {cell['max_equity_gap']:13.6f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", type=int, default=100)
    parser.add_argument("--bearoff", type=int, default=40)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--pilot", action="store_true",
                        help="6 positions, 1 worker -- the wiring, not the measure")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    contact, bearoff, workers = args.contact, args.bearoff, args.workers
    if args.pilot:
        contact, bearoff, workers = 4, 2, 1

    print(f"T35 — sonde : le videau au score, chemin API contre ligne de "
          f"commande gnubg", flush=True)
    print(f"  corpus : {contact} contact (graine {CONTACT_SEED}) + "
          f"{bearoff} fin de partie (graine {BEAROFF_SEED})", flush=True)
    print(f"  réglage adversaire : videau {CUBE_PLY}-ply, prune={PRUNE}, "
          f"match de {MATCH_LENGTH} points", flush=True)
    print(f"  contextes : {len(CONTEXTS)} — {workers} ouvrier(s)\n", flush=True)

    start = time.perf_counter()
    positions = build_corpus(contact, bearoff)
    print(f"  corpus construit en {time.perf_counter() - start:.0f} s "
          f"({len(positions)} positions)\n", flush=True)

    chunks = [positions[i::workers] for i in range(workers)]
    chunks = [chunk for chunk in chunks if chunk]

    start = time.perf_counter()
    if len(chunks) == 1:
        results = [measure((0, chunks[0]))]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=len(chunks)) as pool:
            results = list(pool.map(measure, list(enumerate(chunks))))
    rows = [row for result in results for row in result]
    elapsed = time.perf_counter() - start
    print(f"\n  {len(rows)} décisions comparées en {elapsed:.0f} s", flush=True)

    tables = {}
    for reference in ("cli_true", "cli_compressed", "cli_nobeaver", "cli_beaver"):
        table = compare(rows, reference)
        if table:
            tables[reference] = table
            print_table(f"API contre {reference}", table)

    # The compression, isolated: the two command-line variants against each
    # other, both of them gnubg's own interface.
    compression = {}
    for row in rows:
        if "cli_compressed_verdict" not in row:
            continue
        cell = compression.setdefault(row["context"],
                                      {"positions": 0, "verdict_agree": 0})
        cell["positions"] += 1
        cell["verdict_agree"] += int(row["cli_true_verdict"]
                                     == row["cli_compressed_verdict"])
    if compression:
        print("\n── cli_true contre cli_compressed (la compression, isolée) ──")
        for context, cell in compression.items():
            print(f"  {context:26s} {cell['verdict_agree']}/{cell['positions']}")

    worst = [row for row in rows
             if "cli_true_verdict" in row
             and row["api_verdict"] != row["cli_true_verdict"]]
    print(f"\n  désaccords API/cli_true : {len(worst)} sur "
          f"{sum(1 for r in rows if 'cli_true_verdict' in r)}")
    for row in worst[:10]:
        print(f"    {row['context']:24s} {row['owner']:8s} cube {row['cube']} "
              f"{row['position_id']:16s} API={row['api_action']!r} "
              f"CLI={row['cli_true_action']!r}")

    if args.out:
        payload = {
            "task": "T35",
            "probe": "cube decisions at score: API path vs gnubg's own CLI",
            "corpus": {"contact": contact, "bearoff": bearoff,
                       "contact_seed": CONTACT_SEED, "bearoff_seed": BEAROFF_SEED},
            "setting": {"cube_ply": CUBE_PLY, "prune": PRUNE,
                        "match_length": MATCH_LENGTH,
                        "cube_by_owner": {k.name: v for k, v in CUBE_OF.items()}},
            "contexts": [c.name for c in CONTEXTS],
            "elapsed_s": elapsed,
            "summary": tables,
            "compression": compression,
            "rows": rows,
        }
        args.out.write_text(json.dumps(payload, indent=1, default=str))
        print(f"\n  écrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

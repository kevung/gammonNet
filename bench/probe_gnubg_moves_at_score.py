#!/usr/bin/env python3
"""T35 — the second half of the same question: gnubg's CHEQUER play at score,
API path against its own command line.

`bench/probe_gnubg_at_score.py` settled the cube. It left a named gap: the
campaign also drives gnubg's chequer play at score, through a different
mechanism -- `GnubgEngine._evaluate_at` evaluates the resulting positions
under a match `cubeinfo` and ranks them by `-eval[5]`, relying on the EMG
convention probed on 2026-08-09 (affine in the mover's MWC, positive slope).
The DMP cell of the campaign (50.94 %) and the money half say that convention
is not grossly wrong; neither measures it at an arbitrary score.

## What is compared

For every position, roll and score:

* **`api`** -- the campaign's own evaluation path: every legal play's result
  evaluated at 2 ply, `prune=1`, cubeless, under the state the campaign
  builds (`gnubg_state(CENTRED, swapped_match, jacoby=False)`, the swap being
  the campaign's own -- `play.result` has already turned the move over to the
  opponent). Best equity wins. The campaign's root filter is NOT applied: it
  is a deliberate, separately measured handicap (T31), not part of the
  question here.
* **`cli`** -- gnubg's own interface with the real match posed, its 2-ply
  move filter opened wide so that it too ranks every legal play, and the cube
  handed to the opponent so that `play` can only be a chequer move. The move
  it plays is matched to ours by resulting position ID.

**Money is the control.** The campaign's money half is measured clean, so the
money agreement rate is what "the harness is faithful" looks like here. If the
score path were broken, agreement at score would fall away from it. The
absolute rate is not expected to be 100 %: two engines ranking the same moves
by nearly equal equities will part company on near-ties, and a near-tie costs
nothing. Every disagreement is therefore also reported with the equity the
API path puts between the two moves -- that gap, not the rate, says whether a
disagreement matters.

Usage:
    python bench/probe_gnubg_moves_at_score.py --pilot
    python bench/probe_gnubg_moves_at_score.py --contact 600 --bearoff 300 \\
        --workers 26 --out docs/mesures/t35-sonde-coups-au-score.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.gnubg_cli import CLI_MOVER, Gnubg  # noqa: E402
from gammonnet.gnubg_engine import GnubgSession, gnubg_state  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

from probe_gnubg_at_score import Context, build_corpus  # noqa: E402

PLY = 2
PRUNE = 1
MATCH_LENGTH = 7
DICE_SEED = 20260821

#: Eight contexts, money first -- the control.
CONTEXTS: tuple[Context, ...] = (
    Context("money"),
    Context("2a2a", 2, 2),
    Context("3a5a", 3, 5),
    Context("5a3a", 5, 3),
    Context("4a4a", 4, 4),
    Context("7a7a", 7, 7),
    Context("postcrawford_2a1a", 2, 1),
    Context("postcrawford_4a1a", 4, 1),
)


def roll_for(index: int) -> tuple[int, int]:
    rng = random.Random((DICE_SEED, index).__hash__())
    return rng.randint(1, 6), rng.randint(1, 6)


def usable(position: Position, d1: int, d2: int) -> bool:
    """A position is usable when the comparison can mean something.

    More than one legal play (agreement on a forced move says nothing), and no
    play that ends the game -- gnubg's board readback after a finished game is
    another state to handle, and skipping is honest and cheap.
    """
    plays = position.legal_plays(d1, d2)
    return len(plays) > 1 and not any(play.result.is_over() for play in plays)


def setup_cli(cli: Gnubg, context: Context) -> None:
    if context.money:
        cli.new_money_session(jacoby=True, beavers=False)
    else:
        cli.new_match(MATCH_LENGTH)
        cli.set_score(MATCH_LENGTH - context.away_opponent,
                      MATCH_LENGTH - context.away_mover, MATCH_LENGTH)
        if (context.away_mover == 1) != (context.away_opponent == 1):
            cli.set_crawford(context.crawford)
    # The session opens with two humans -- otherwise gnubg plays the whole
    # game by itself the moment it is created, cube included, and the pilot
    # met a finished game before its first question. The mover is turned into
    # a gnu player only once the match is posed: `play` then plays exactly one
    # chequer move and stops, because the opponent is a human who never moves.
    cli._send(f"set player {CLI_MOVER} gnubg")
    cli.set_turn(CLI_MOVER)
    # Wide open at 2 ply, both levels: gnubg ranks every legal play, as the
    # API path does. `-1` is gnubg's "skip pruning" -- established by probe,
    # read back from `show player`.
    for player in (0, 1):
        cli._send(f"set player {player} movefilter 2 0 -1 0 0.0",
                  f"set player {player} movefilter 2 1 -1 0 0.0")


def measure(payload):
    index, items = payload

    session = GnubgSession()
    cli = Gnubg(ply=PLY, cubeful=False, manual=True)

    rows = []
    for context in CONTEXTS:
        setup_cli(cli, context)
        for position, origin, d1, d2 in items:
            plays = position.legal_plays(d1, d2)

            # The campaign's own state: it describes the OPPONENT, because
            # `play.result` has already turned the move over.
            match = context.match_state(1)
            if match is None:
                state = gnubg_state(CubeOwner.CENTRED, None, jacoby=False, cube=1)
            else:
                swapped = MatchState(match.away_opponent, match.away_on_roll,
                                     cube=match.cube, crawford=match.crawford)
                state = gnubg_state(CubeOwner.CENTRED, swapped, jacoby=False,
                                    cube=match.cube)
            values = session.evaluate([gb.to_gnubg(play.result) for play in plays],
                                      plies=PLY, prune=PRUNE, state=state)
            equities = [-float(value[5]) for value in values]
            best = max(range(len(plays)), key=lambda i: equities[i])

            chosen = cli.best_play_at_score(position, d1, d2)
            if chosen is None:
                # gnubg a abandonné plutôt que de jouer : la position est trop
                # perdue pour que le choix de coup y veuille dire quelque
                # chose. Comptée à part, jamais devinée.
                rows.append({
                    "position_id": codec.position_id(position),
                    "origin": origin, "context": context.name,
                    "dice": [d1, d2], "plays": len(plays),
                    "agree": None, "equity_gap": None, "resigned": True,
                })
                continue
            chosen_id = codec.position_id(chosen.result)
            by_id = {codec.position_id(play.result): i
                     for i, play in enumerate(plays)}
            theirs = by_id[chosen_id]

            rows.append({
                "position_id": codec.position_id(position),
                "origin": origin, "context": context.name,
                "dice": [d1, d2], "plays": len(plays),
                "agree": theirs == best,
                # What the API path says the disagreement costs, in its own
                # equity scale. A near-tie is not a defect.
                "equity_gap": equities[best] - equities[theirs],
            })
        print(f"  [worker {index}] {context.name} done", file=sys.stderr, flush=True)

    cli.close()
    session.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", type=int, default=600)
    parser.add_argument("--bearoff", type=int, default=300)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    contact, bearoff, workers = args.contact, args.bearoff, args.workers
    if args.pilot:
        contact, bearoff, workers = 8, 4, 1

    print("T35 — sonde : le JEU DE PIONS au score, chemin API contre ligne de "
          "commande gnubg", flush=True)
    corpus = build_corpus(contact, bearoff)
    items = []
    for i, (position, origin) in enumerate(corpus):
        d1, d2 = roll_for(i)
        if usable(position, d1, d2):
            items.append((position, origin, d1, d2))
    print(f"  {len(items)} positions utilisables sur {len(corpus)} "
          f"(jets de graine {DICE_SEED} ; coups forcés et positions "
          f"terminales écartés)", flush=True)
    print(f"  {len(CONTEXTS)} contextes, {PLY}-ply prune={PRUNE} des deux "
          f"côtés, sans filtre de racine\n", flush=True)

    chunks = [items[i::workers] for i in range(workers)]
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

    print(f"\n  {len(rows)} décisions comparées en {elapsed:.0f} s\n")
    print(f"  {'contexte':22s} {'n':>6s} {'même coup':>10s} "
          f"{'écart médian':>13s} {'écart max':>11s} {'> 0,01':>8s} "
          f"{'abandons':>9s}")
    summary = {}
    for context in CONTEXTS:
        cell = [row for row in rows if row["context"] == context.name]
        if not cell:
            continue
        resigned = sum(1 for row in cell if row.get("resigned"))
        cell = [row for row in cell if not row.get("resigned")]
        if not cell:
            continue
        agree = sum(row["agree"] for row in cell)
        gaps = sorted(row["equity_gap"] for row in cell if not row["agree"])
        median = gaps[len(gaps) // 2] if gaps else 0.0
        heavy = sum(1 for gap in gaps if gap > 0.01)
        summary[context.name] = {
            "n": len(cell), "agree": agree, "rate": agree / len(cell),
            "median_gap": median, "max_gap": gaps[-1] if gaps else 0.0,
            "gaps_over_0.01": heavy, "resigned": resigned,
        }
        print(f"  {context.name:22s} {len(cell):6d} {agree/len(cell)*100:9.2f}% "
              f"{median:13.5f} {(gaps[-1] if gaps else 0.0):11.5f} "
              f"{heavy:8d} {resigned:9d}")

    if args.out:
        args.out.write_text(json.dumps({
            "task": "T35",
            "probe": "chequer play at score: API path vs gnubg's own CLI",
            "setting": {"ply": PLY, "prune": PRUNE, "cubeful": False,
                        "match_length": MATCH_LENGTH, "dice_seed": DICE_SEED,
                        "root_filter": None},
            "corpus": {"contact": contact, "bearoff": bearoff,
                       "usable": len(items)},
            "elapsed_s": elapsed,
            "summary": summary,
            "disagreements": sorted(
                ({k: row[k] for k in ("context", "position_id", "dice",
                                      "plays", "equity_gap", "origin")}
                 for row in rows if row["agree"] is False),
                key=lambda row: -row["equity_gap"])[:60],
        }, indent=1, default=str))
        print(f"\n  écrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

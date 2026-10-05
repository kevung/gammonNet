#!/usr/bin/env python3
"""Scan reachable positions for legal-play disagreements with GNU Backgammon.

`tests/test_rules.py` already crosses our generator against gnubg, but on a
hand-built corpus of 204 positions — 4 284 (position, roll) pairs. The upstream
rules engine we compile in has a defect whose announced incidence is at most
1/3700 decisions (alexstrehl/backgammon-ai-engine, commit 5c9aa87: a shorter
play shadows the maximal one in the dedup table, producing a false forced pass).
A fixed corpus of that size can miss it, and ours does.

This scans positions reached by random play instead: many more pairs, drawn
from the distribution a game actually visits. GNU Backgammon is the independent
generator, exactly as in T01 — an instrument, never a source.

It reports what it finds, including nothing. A run with zero disagreements over
a stated number of pairs is a measurement, not a failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from gammonnet import Position  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402

try:
    import gnubg_nn
except ImportError:  # pragma: no cover - the scan is meaningless without it
    sys.exit("gnubg-nn absent — lancer `make venv`")

ALL_ROLLS = [(d1, d2) for d1 in range(1, 7) for d2 in range(d1, 7)]


def play_signature(play) -> str:
    """The sub-moves themselves, not just where they land.

    Two plays can reach the same board with a different number of dice; the
    defect this scan hunts for is exactly that, so the signature has to carry
    the moves.
    """
    return "|".join(f"{m.from_}/{m.to}" for m in play.moves)


def compare(position: Position, d1: int, d2: int, ours=None) -> dict | None:
    """Return a record of the disagreement, or None when the two agree."""
    if ours is None:
        ours = position.legal_plays(d1, d2)
    our_keys = {gb.key(play.result, on_roll=position.turn) for play in ours}
    their_keys = set(gnubg_nn.moves(gb.to_gnubg(position), d1, d2, 0))

    collapsed = len(our_keys) != len(ours)
    if our_keys == their_keys and not collapsed:
        return None

    return {
        "points": list(position.points),
        "bar": list(position.bar),
        "off": list(position.off),
        "turn": position.turn,
        "dice": [d1, d2],
        "ours": len(ours),
        "ours_distinct": len(our_keys),
        "theirs": len(their_keys),
        "missing_from_ours": sorted(their_keys - our_keys),
        "extra_in_ours": sorted(our_keys - their_keys),
        "duplicate_states": collapsed,
    }


def walk(rng: random.Random, max_plies: int):
    """Yield positions along one random game, starting from the opening."""
    position = Position.initial()
    for _ in range(max_plies):
        if position.is_over():
            return
        yield position
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        if not plays:
            position = position.swapped_turn()
            continue
        # Sorted by the board reached, never by the order the generator
        # returned them: the walk must visit the same positions across two
        # builds even if their orderings differ, or the digests below would
        # disagree for a reason that is not a rules disagreement.
        ordered = sorted(plays, key=lambda p: gb.key(p.result, on_roll=position.turn))
        position = ordered[rng.randrange(len(ordered))].result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=20000,
                        help="nombre de positions visitées (21 jets chacune)")
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--max-plies", type=int, default=120)
    parser.add_argument("--out", type=Path, default=None,
                        help="fichier JSON où écrire le relevé")
    parser.add_argument("--against-gnubg", action="store_true", default=True,
                        help="croiser avec GNU Backgammon (défaut)")
    parser.add_argument("--no-gnubg", dest="against_gnubg", action="store_false",
                        help="n'exécuter que les contrôles internes et l'empreinte")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    seen_positions = 0
    pairs = 0
    plays_total = 0
    ragged = 0
    findings: list[dict] = []
    digest = hashlib.sha256()

    while seen_positions < args.positions:
        for position in walk(rng, args.max_plies):
            if seen_positions >= args.positions:
                break
            seen_positions += 1
            for d1, d2 in ALL_ROLLS:
                pairs += 1
                plays = position.legal_plays(d1, d2)
                plays_total += len(plays)

                # The maximal-use rule makes every legal play spend the same
                # number of dice. A list that mixes lengths means a shorter
                # play was kept where a longer one existed.
                lengths = {len(play.moves) for play in plays}
                if len(lengths) > 1:
                    ragged += 1

                signatures = sorted(play_signature(play) for play in plays)
                digest.update(f"{position!r}{d1}{d2}{signatures}".encode())

                if args.against_gnubg:
                    record = compare(position, d1, d2, ours=plays)
                    if record is not None:
                        findings.append(record)
            if seen_positions % 2000 == 0:
                print(f"  {seen_positions} positions · {pairs} couples · "
                      f"{len(findings)} désaccords", flush=True)

    report = {
        "seed": args.seed,
        "positions": seen_positions,
        "pairs": pairs,
        "plays": plays_total,
        "ragged_lists": ragged,
        "digest": digest.hexdigest(),
        "against_gnubg": args.against_gnubg,
        "disagreements": len(findings),
        "incidence_per_pair": len(findings) / pairs if pairs else 0.0,
        "findings": findings[:200],
    }

    print(f"\n{seen_positions} positions · {pairs} couples (position, jet) · "
          f"{plays_total} coups engendrés")
    print(f"listes à longueurs mêlées : {ragged}")
    print(f"empreinte des sous-coups : {digest.hexdigest()}")
    if findings:
        print(f"DÉSACCORDS : {len(findings)} — un couple sur "
              f"{pairs // len(findings)}")
        for record in findings[:5]:
            print(f"  dés {record['dice']} : nous {record['ours_distinct']}, "
                  f"gnubg {record['theirs']}"
                  + (" (doublon interne)" if record["duplicate_states"] else ""))
    else:
        print("Aucun désaccord. C'est une mesure, pas une preuve d'absence : "
              f"l'incidence annoncée en amont (≤1/3700) rendrait ~{pairs // 3700} "
              "désaccords attendus à ce volume.")

    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\n→ {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

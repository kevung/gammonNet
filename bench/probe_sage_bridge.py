#!/usr/bin/env python3
"""T92 étape 1 — le pont vers le moteur tiers, vérifié avant de servir à mesurer.

Ce banc ne mesure aucune force. Il répond à une seule question : **la position
que nous croyons envoyer est-elle celle que l'autre moteur reçoit ?** Tant qu'elle
n'a pas de réponse, tout chiffre produit plus loin est dépourvu de sens — et
n'en aurait pas l'air, ce qui est le mode de défaillance que `CLAUDE.md` règle 2
vise.

Trois contrôles, du moins au plus exigeant :

1. **Aller-retour** — `to_sage` puis `from_sage` rend la position de départ, et
   le compte de pips survit dans les deux sens (sentinelle de `BRIEF.md` §6).
2. **Ensembles de coups légaux** — pour chaque position et chaque jet, les
   positions atteignables énumérées ici et là-bas sont **le même ensemble**.
   C'est le contrôle fort : deux générateurs de coups indépendants qui
   s'accordent sur des milliers de positions ne partagent pas une erreur
   d'orientation.
3. **Positions asymétriques et jets asymétriques** — la position d'ouverture est
   symétrique, donc muette sur l'orientation. Le corpus est tiré de parties
   jouées, barre et sorties comprises.

Usage :
    python bench/probe_sage_bridge.py --positions 2000 --workers 26
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.rules import BLACK, WHITE, Position  # noqa: E402
from gammonnet.sage_board import from_sage, to_sage  # noqa: E402

SEED = 20260907


def sample_positions(seed: int, count: int) -> list[tuple[Position, int, int]]:
    """Positions reached by random play, with the roll that follows each.

    Random play is deliberate here: it reaches the bar, the borne-off states and
    the lopsided boards that a strong policy avoids, and those are exactly where
    an orientation error would show.
    """
    rng = random.Random(seed)
    out: list[tuple[Position, int, int]] = []
    while len(out) < count:
        position = Position.initial()
        if rng.random() < 0.5:
            position = position.swapped_turn()
        for _ in range(200):
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
            out.append((position, d1, d2))
            if len(out) >= count:
                break
            plays = position.legal_plays(d1, d2)
            if not plays:
                position = position.swapped_turn()
                continue
            position = rng.choice(plays).result
            if position.is_over():
                break
    return out[:count]


def check_one(item: tuple[Position, int, int]) -> dict:
    """Run the three controls on one (position, roll). Returns a failure record."""
    import bgsage

    position, d1, d2 = item
    mover = position.turn
    board = to_sage(position)

    back = from_sage(board, on_roll=mover)
    if back != position:
        return {"kind": "aller-retour", "position": repr(position), "board": board}

    ours = {
        tuple(to_sage(play.result, on_roll=mover)) for play in position.legal_plays(d1, d2)
    }
    theirs = {tuple(b) for b in bgsage.possible_moves(board, d1, d2)}

    # « Aucun coup légal » ne s'écrit pas pareil des deux côtés : nous rendons
    # une liste vide, l'autre moteur rend le plateau inchangé — malgré ce que
    # dit son propre docstring. Les deux disent la même chose. La différence est
    # normalisée ici, une fois, plutôt que devinée à chaque appel : un moteur qui
    # « joue » le plateau inchangé sans que personne l'ait remarqué produirait un
    # tour perdu et une mesure fausse.
    if not ours and theirs == {tuple(board)}:
        return {}

    if ours != theirs:
        missing = ours - theirs
        extra = theirs - ours
        kind = (
            "coup-manquant" if missing and not extra
            else "coup-en-trop" if extra and not missing
            else "coups-differents"
        )
        return {
            "kind": kind,
            "position": repr(position),
            "position_id": _position_id(position),
            "dice": [d1, d2],
            "only_ours": sorted(missing)[:3],
            "only_theirs": sorted(extra)[:3],
            "n_ours": len(ours),
            "n_theirs": len(theirs),
            "bearoff": bool(position.off[mover]),
        }
    return {}


def _position_id(position: Position) -> str:
    """The gnubg position key, so a divergence can be replayed elsewhere."""
    from gammonnet import gnubg_board as gb

    try:
        return gb.key(position)
    except Exception:  # noqa: BLE001 — un identifiant absent ne doit rien casser
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    items = sample_positions(args.seed, args.positions)

    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(check_one, items, chunksize=16):
            if record:
                failures.append(record)

    with_bar = sum(1 for p, _, _ in items if p.bar[WHITE] or p.bar[BLACK])
    with_off = sum(1 for p, _, _ in items if p.off[WHITE] or p.off[BLACK])
    black_to_act = sum(1 for p, _, _ in items if p.turn == BLACK)

    kinds: dict[str, int] = {}
    for record in failures:
        kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1

    report = {
        "positions": len(items),
        "seed": args.seed,
        "with_bar": with_bar,
        "with_off": with_off,
        "black_to_act": black_to_act,
        "failures": len(failures),
        "by_kind": kinds,
        "in_bearoff": sum(1 for r in failures if r.get("bearoff")),
        "first_failures": failures[:8],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if failures:
        print(f"\nREFUS — {len(failures)} position(s) sur {len(items)} ne traversent pas le pont.")
        return 1
    print(
        f"\nLe pont tient sur {len(items)} positions "
        f"({with_bar} avec barre, {with_off} avec sorties, {black_to_act} à BLACK de jouer)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

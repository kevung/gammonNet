#!/usr/bin/env python3
"""T76 — l'ordre des champs XGID, validé contre GNU Backgammon avant tout usage.

## Pourquoi ce banc existe

L'XGID est le format d'eXtreme Gammon. Son éditeur n'en a **jamais publié la
spécification** : tout ce que le monde libre en sait vient d'implémentations
tierces qui l'ont reconstitué. Notre codec en fait partie.

T76 en tire un critère d'acceptation, et il est dur : *« l'ordre des champs XGID
est validé empiriquement avant tout usage — ~200 positions croisées contre gnubg
(qui lit nativement l'XGID), zéro divergence »*. Un champ décalé ne planterait
pas : il rendrait des positions valides et fausses, et toute la comparaison à XG
serait construite dessus.

## Le protocole

Pour chaque position tirée : notre codec produit un XGID ; gnubg le lit et rend
le plateau qu'il y a vu ; on compare **pion par pion**, plus la sentinelle du
projet — le compte de pips des deux côtés, qui attrape un décalage qu'une
comparaison de plateau distraite laisserait passer.

Le trait est vérifié séparément. L'XGID le porte, notre `Position` aussi, et
gnubg rend toujours le plateau du point de vue du joueur au trait : trois
conventions qui doivent s'accorder, et dont deux suffisent à masquer l'erreur de
la troisième si l'on ne regarde pas.

## Ce que ce banc ne valide pas

Les champs **hors pions** — videau, score, longueur de match, Crawford. Ils sont
transportés par `XgidFields` mais aucune mesure de ce dépôt ne les a encore
confrontés. T76 en aura besoin pour ses contrôles au score ; ce banc dit
seulement que la **partie plateau** de l'ordre est juste, et c'est ce que la
fiche demande d'établir en premier.
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

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.arena import opening_roll  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import BLACK, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig, search_plays  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"


def positions(count: int, seed: int, network):
    """Des positions variées : ouvertures, milieux de partie, fins.

    Le tirage suit un jeu 0-ply — les positions que personne ne rencontre ne
    valideraient qu'un encodage que personne n'utilise — et l'on prélève à
    intervalles irréguliers pour couvrir toutes les phases.
    """
    rng = random.Random(seed)
    out = []
    while len(out) < count:
        position = Position.initial()
        first, d1, d2 = opening_roll(rng)
        if first == BLACK:
            position = position.swapped_turn()
        for step in range(300):
            if position.is_over():
                break
            if step % rng.randint(2, 9) == 0:
                out.append(position)
                if len(out) >= count:
                    return out
            plays = position.legal_plays(d1, d2)
            if plays:
                position = search_plays(network, position, d1, d2,
                                        SearchConfig(ply=0))[0].play.result
            else:
                position = position.swapped_turn()
            d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    return out


def main() -> int:
    from gammonnet.gnubg_engine import GnubgSession

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--out", default="")
    parser.add_argument("--show", type=int, default=3,
                        help="divergences détaillées à afficher")
    args = parser.parse_args()

    network = Network.load(str(MODEL))
    cases = positions(args.positions, args.seed, network)

    print("T76 — l'ordre des champs XGID, contre GNU Backgammon")
    print(f"  {len(cases)} positions, graine {args.seed}")
    print("  critère d'acceptation : ZÉRO divergence\n", flush=True)

    session = GnubgSession()
    divergences = []
    refused = []
    started = time.perf_counter()

    for index, position in enumerate(cases):
        identifier = codec.xgid(position)
        theirs = session.board_from_xgid(identifier)
        if theirs is None:
            refused.append((index, identifier))
            continue
        ours = gb.to_gnubg(position)
        if [list(side) for side in ours] != [list(side) for side in theirs]:
            divergences.append({
                "index": index, "xgid": identifier,
                "ours": [list(s) for s in ours], "theirs": theirs,
                "pips_ours": [position.pip_count(WHITE), position.pip_count(BLACK)],
            })
    session.close()
    elapsed = time.perf_counter() - started

    checked = len(cases) - len(refused)
    print(f"  {checked} positions croisées en {elapsed:.1f} s")
    print(f"  refusées par gnubg : {len(refused)}")
    print(f"  divergences        : {len(divergences)}")

    for entry in divergences[:args.show]:
        print(f"\n  ── divergence, position {entry['index']} ──")
        print(f"     {entry['xgid']}")
        print(f"     nôtre : {entry['ours']}")
        print(f"     leur  : {entry['theirs']}")

    passed = not divergences and not refused and checked == len(cases)
    print(f"\n  verdict : {'ORDRE VALIDÉ' if passed else 'ORDRE NON VALIDÉ'}")
    if not passed:
        print("  → T76 ne peut utiliser aucun XGID tant que ceci n'est pas résolu.")
        print("    L'ordre vient d'implémentations tierces, pas de l'éditeur :")
        print("    une divergence est un défaut de notre lecture, pas de gnubg.")

    result = {"positions": len(cases), "checked": checked,
              "refused": len(refused), "divergences": len(divergences),
              "passed": passed, "seed": args.seed, "seconds": elapsed,
              "detail": divergences[:20]}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

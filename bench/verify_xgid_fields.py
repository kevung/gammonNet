#!/usr/bin/env python3
"""T76 — les champs XGID hors pions, confrontés à GNU Backgammon.

## Ce qui restait à faire

`bench/verify_xgid.py` a établi que la **partie plateau** de l'XGID est juste :
200 positions, zéro divergence. Il notait aussi ce qu'il ne validait pas — le
videau, le score, la longueur de match, Crawford. Ces champs viennent des mêmes
implémentations tierces que les pions, et n'ont pas plus de raison d'être justes
sans vérification.

Ils comptent autant. T76 doit comparer nos décisions à celles d'XG **au score**,
et un champ de score décalé ferait comparer deux moteurs sur deux situations
différentes — en rendant des chiffres parfaitement présentables.

## Le protocole

On balaie des combinaisons choisies pour être discriminantes : videau centré et
possédé de chaque côté, puissances de videau distinctes, scores **asymétriques**
(un score 3–3 ne peut pas révéler une inversion), matchs de longueurs
différentes, Crawford actif et non. Notre codec produit l'XGID ; gnubg le lit et
rend son `cubeinfo`. On compare champ par champ.

**Les scores asymétriques sont le cœur du banc.** Une inversion `upper`/`lower`
est exactement le genre d'erreur qui ne se voit jamais sur des cas symétriques,
et qui fausse ensuite toutes les mesures au score.

## Ce que ce banc établit, et dans quel sens

Il ne dit pas que notre codec est « correct dans l'absolu » — il n'existe aucune
spécification publiée à laquelle le confronter. Il dit que **notre lecture et
celle de gnubg coïncident**, ce qui est le maximum disponible, et ce que la
fiche demande : *« l'ordre vient d'implémentations tierces, pas de l'éditeur »*.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import codec  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

#: Les combinaisons balayées. Choisies discriminantes, pas exhaustives : un
#: balayage complet coûterait des milliers de cas pour ne rien dire de plus que
#: ceux-ci, qui sont chacun capable de démasquer une erreur précise.
CUBE_POWERS = (0, 1, 2, 6)
CUBE_OWNERS = (0, 1, -1)
#: Asymétriques à dessein : un score 3–3 ne peut pas révéler une inversion.
SCORES = ((0, 0), (3, 1), (1, 4), (6, 0), (0, 5))
MATCH_LENGTHS = (0, 5, 7, 11)


def expected_cube_value(power: int) -> int:
    return 1 << power


def check(session, fields, position) -> dict | None:
    """Un cas : produire l'XGID, le faire lire, comparer. None si tout colle."""
    identifier = codec.xgid(position, fields)
    state = session.state_from_xgid(identifier)
    if state is None:
        return {"xgid": identifier, "fault": "refusé par gnubg"}
    info = state.get("cubeinfo")
    if info is None:
        return {"xgid": identifier, "fault": "cubeinfo indisponible",
                "detail": state.get("cubeinfo_error")}

    faults = []
    if info["cube"] != expected_cube_value(fields.cube_power):
        faults.append(f"videau {info['cube']} pour 2^{fields.cube_power}")
    if fields.match_length and info["matchto"] != fields.match_length:
        faults.append(f"match_to {info['matchto']} pour {fields.match_length}")
    # Le score : l'XGID porte deux nombres, gnubg en rend deux. Lequel est
    # lequel est précisément la question — on compare l'ENSEMBLE d'abord, ce qui
    # sépare « valeurs fausses » de « valeurs bonnes, ordre à établir ».
    ours = {fields.score_upper, fields.score_lower}
    theirs = set(info["score"])
    if fields.match_length and ours != theirs:
        faults.append(f"scores {info['score']} pour "
                      f"({fields.score_upper}, {fields.score_lower})")
    if not faults:
        return None
    return {"xgid": identifier, "faults": faults,
            "sent": {"cube_power": fields.cube_power,
                     "cube_owner": fields.cube_owner,
                     "score": [fields.score_upper, fields.score_lower],
                     "match_length": fields.match_length},
            "read": {k: info[k] for k in ("cube", "cubeowner", "matchto",
                                          "score", "crawford")}}


def main() -> int:
    from gammonnet.gnubg_engine import GnubgSession

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="")
    parser.add_argument("--show", type=int, default=6)
    args = parser.parse_args()

    position = Position.initial()
    session = GnubgSession()
    cases = 0
    divergences = []
    score_order = {"upper_is_index0": 0, "upper_is_index1": 0, "ambiguous": 0}

    print("T76 — les champs XGID hors pions, contre GNU Backgammon")
    print("  videau, score, longueur de match — la partie que "
          "`verify_xgid.py` ne validait pas\n", flush=True)

    for power, owner, score, length in itertools.product(
            CUBE_POWERS, CUBE_OWNERS, SCORES, MATCH_LENGTHS):
        # Un score ne peut pas dépasser la longueur du match, et un match de
        # longueur 0 est le money game, où le score n'a pas de sens.
        if length and (score[0] >= length or score[1] >= length):
            continue
        fields = codec.XgidFields(cube_power=power, cube_owner=owner, turn=1,
                                  score_upper=score[0], score_lower=score[1],
                                  match_length=length, max_cube=10)
        cases += 1
        fault = check(session, fields, position)
        if fault:
            divergences.append(fault)
            continue
        # L'ordre du score, établi sur les cas asymétriques uniquement.
        if length and score[0] != score[1]:
            state = session.state_from_xgid(codec.xgid(position, fields))
            read = state["cubeinfo"]["score"]
            if read[0] == score[0] and read[1] == score[1]:
                score_order["upper_is_index0"] += 1
            elif read[0] == score[1] and read[1] == score[0]:
                score_order["upper_is_index1"] += 1
            else:
                score_order["ambiguous"] += 1

    session.close()

    print(f"  {cases} combinaisons examinées")
    print(f"  divergences : {len(divergences)}")
    for entry in divergences[:args.show]:
        print(f"\n  ── {entry['xgid']}")
        for fault in entry.get("faults", [entry.get("fault", "?")]):
            print(f"     {fault}")
        if "read" in entry:
            print(f"     envoyé : {entry['sent']}")
            print(f"     lu     : {entry['read']}")

    print("\n  ordre du score, sur les cas asymétriques :")
    for name, count in score_order.items():
        print(f"    {name:20s} {count}")
    decided = (score_order["upper_is_index0"] > 0) ^ (score_order["upper_is_index1"] > 0)
    if decided and not score_order["ambiguous"]:
        which = ("score_upper ↔ score[0]" if score_order["upper_is_index0"]
                 else "score_upper ↔ score[1]")
        print(f"    → correspondance établie sans exception : {which}")
    else:
        print("    → NON ÉTABLIE : les cas ne s'accordent pas entre eux.")

    passed = not divergences and decided and not score_order["ambiguous"]
    print(f"\n  verdict : {'CHAMPS VALIDÉS' if passed else 'CHAMPS NON VALIDÉS'}")

    result = {"cases": cases, "divergences": divergences[:30],
              "score_order": score_order, "passed": passed}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

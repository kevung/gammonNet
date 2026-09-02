"""Le repère du CODEC, produit par le C natif, pour la parité WebAssembly.

`tools/dump_reference.py` fige ce que le RÉSEAU répond ; celui-ci fige ce que le
CODEC répond. Les deux ont la même raison d'être : le module WebAssembly doit
être vérifié contre le C, pas contre l'écriture JavaScript qu'il remplace.

Ce que ce repère contient, par position du corpus T12 :

    position_id   l'identifiant tel que le corpus le porte
    turn          le joueur au trait qui va avec
    board         les 29 entiers de la frontière (24 points signés, bar, off, turn)
    pips          les deux comptes de pips
    xgid          le XGID de la même position, champs par défaut

Le corpus T12 porte des identifiants, pas des plateaux : le plateau est obtenu
en DÉCODANT par le C, ce qui fait de ce fichier un test d'aller-retour autant
qu'un repère — si `gn_position_from_id` puis `gn_position_id` ne redonnaient pas
l'identifiant de départ, la génération échouerait ici, avant toute comparaison.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import BLACK, WHITE, codec  # noqa: E402

CORPUS = ROOT / "tests" / "data" / "corpus_t12.jsonl"
OUT = ROOT / "build" / "codec_reference.json"


def board_ints(position) -> list[int]:
    """Les 29 entiers de la frontière WebAssembly, dans l'ordre de `gn_wasm.c`."""
    return (
        list(position.points)
        + [position.bar[WHITE], position.bar[BLACK]]
        + [position.off[WHITE], position.off[BLACK]]
        + [position.turn]
    )


def main() -> int:
    if not CORPUS.is_file():
        print(f"corpus absent : {CORPUS}", file=sys.stderr)
        return 1

    entries = []
    with CORPUS.open() as handle:
        for line in handle:
            record = json.loads(line)
            identifier = record["position_id"]
            turn = record["turn"]
            position = codec.position_from_id(identifier, turn)

            # L'aller-retour, contrôlé ICI plutôt que promis : un repère bâti
            # sur un décodage faux serait un repère faux, et la parité passerait
            # au vert en comparant deux erreurs.
            again = codec.position_id(position)
            if again != identifier:
                print(f"aller-retour rompu sur {record['id']} : "
                      f"{identifier} → {again}", file=sys.stderr)
                return 1

            entries.append({
                "id": record["id"],
                "position_id": identifier,
                "turn": turn,
                "board": board_ints(position),
                "pips": [position.pip_count(WHITE), position.pip_count(BLACK)],
                "xgid": codec.xgid(position),
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries), encoding="utf-8")
    print(f"→ {OUT} : {len(entries)} positions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Génère l'export canonique `data/search_levels.json` (issue #25).

`ply = 2`, `filter = (0,1,3)` et `prune_k = 12` étaient recopiés à la main
jusqu'à cinq fois à travers ce dépôt et ses cibles, et le coût en qualité de ce
réglage ne voyageait avec AUCUNE de ces copies -- ce qui a un jour laissé un
`prune_k = 3` "rapide" s'installer sans mesure amont.

## Une seule source, un seul export

`gn_search_level` (`src/gn_search.c`, la table `LEVELS`) est la source qui
fait foi -- ADR-0003 : une forme partagée entre les cibles se décide et se
mesure ici. Ce script ne fait que la
lire par le lien Python (`gammonnet.search.search_level`, qui appelle
`gn_search_level` par `ctypes`, rien n'est réinventé) et l'écrire en JSON :

- `data/search_levels.json` -- l'export canonique, à lire au lieu de
  retranscrire les nombres à la main, sur le modèle de
  `data/met_kazaross_xg2.json` (issue #24) ;
- `data/search_levels.sha256` -- l'empreinte SHA-256 de l'export, sur le
  même modèle : un appelant qui embarque une copie peut vérifier qu'elle n'a
  pas divergé sans reparser chaque champ.

    python tools/extract_search_levels.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.search import search_level, search_level_names  # noqa: E402


def build_export() -> dict:
    levels = {}
    for name in search_level_names():
        level = search_level(name)
        levels[name] = {
            "ply": level.ply,
            # Seuls les indices que la forme publiée fixe réellement voyagent
            # -- (0,1,3), jamais les zéros de remplissage jusqu'à GN_MAX_PLY
            # que le C garde pour dimensionner GnSearchConfig.filter.
            "filter": list(level.filter[: level.ply + 1]),
            "prune_k": level.prune_k,
            "prune_equity_loss": level.prune_equity_loss,
            "prune_equity_loss_ci": [
                level.prune_equity_loss_ci_low,
                level.prune_equity_loss_ci_high,
            ],
        }
    return {
        "_comment": (
            "Formes canoniques de recherche (issue #25), generated from "
            "gn_search_level() (src/gn_search.c), the single canonical "
            "source -- read this instead of retyping ply/filter/prune_k. "
            "prune_equity_loss and its 95% CI are measured "
            "(docs/mesures/2026-08-26-T3A-regroupement.md, 450 decisions "
            "at 2-ply filter (0,1,3), pruned vs the same search unpruned); "
            "0 wherever prune_k is 0 -- nothing to lose. Regenerate with "
            "tools/extract_search_levels.py; do not hand-edit."
        ),
        "source": "gammonNet gn_search_level (src/gn_search.c)",
        "levels": levels,
    }


def main() -> int:
    export = build_export()
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    export_path = data_dir / "search_levels.json"
    export_path.write_text(
        json.dumps(export, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(export_path.read_bytes()).hexdigest()
    (data_dir / "search_levels.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"écrit : {export_path}")
    print(f"écrit : {data_dir / 'search_levels.sha256'} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

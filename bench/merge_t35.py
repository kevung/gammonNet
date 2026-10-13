#!/usr/bin/env python3
"""Réunir des journaux T35 d'une même campagne jouée en plusieurs morceaux.

Chaque morceau (`run_t35.py --indices A:B`, une autre machine…) a son propre
journal au même en-tête. La fusion ajoute au journal cible les paires des
autres qu'il n'a pas encore ; le pilote, relancé sur la cible, les saute.

Refus, sans rien écrire :
* un en-tête diffère (hors `pairs_target`, comme `check_header`) ;
* un index est présent dans deux journaux avec des contenus différents — une
  paire est une fonction pure de son index, un écart veut dire un autre build ;
* un processus a encore l'un des journaux ouvert : un pilote en cours écrit
  en ajout dans sa cible, et ne relirait de toute façon pas les lignes
  ajoutées (sa liste d'index est figée au lancement).

La cible est réécrite d'un bloc (fichier temporaire puis `os.replace`) : une
coupure pendant la fusion laisse l'ancienne cible intacte.

    python bench/merge_t35.py --into docs/mesures/adoption-256-t35-match.jsonl \\
        docs/mesures/adoption-256-t35-match-distant.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from run_t35 import read_journal  # noqa: E402


def open_by(path: Path) -> list[int]:
    """Les PID qui ont `path` ouvert (Linux, /proc ; les processus d'autres
    utilisateurs, illisibles, ne peuvent pas écrire nos journaux)."""
    target = path.resolve()
    pids = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc / "fd").iterdir():
                try:
                    if Path(os.readlink(fd)) == target:
                        pids.append(int(proc.name))
                        break
                except OSError:
                    continue
        except OSError:
            continue
    return pids


def same_protocol(a: dict, b: dict) -> list[str]:
    keys = (set(a) | set(b)) - {"pairs_target"}
    return sorted(k for k in keys if a.get(k) != b.get(k))


def merge(into: Path, sources: list[Path]) -> tuple[dict[int, dict], int]:
    """Les lignes à ajouter et le nombre de doublons identiques ignorés."""
    header, rows = read_journal(into)
    if header is None:
        raise SystemExit(f"{into} : pas d'en-tête")
    added: dict[int, dict] = {}
    duplicates = 0
    for source in sources:
        other_header, other_rows = read_journal(source)
        if other_header is None:
            raise SystemExit(f"{source} : pas d'en-tête")
        differing = same_protocol(header, other_header)
        if differing:
            raise SystemExit(f"{source} : en-tête différent ({', '.join(differing)})")
        for i, row in other_rows.items():
            known = rows.get(i, added.get(i))
            if known is None:
                added[i] = row
            elif known == row:
                duplicates += 1
            else:
                raise SystemExit(f"index {i} : contenus différents entre {into} "
                                 f"et {source} — refus")
    return added, duplicates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--into", type=Path, required=True)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in (args.into, *args.sources):
        busy = open_by(path)
        if busy:
            raise SystemExit(f"{path} est ouvert par le(s) PID {busy} : arrêtez "
                             f"le pilote avant de fusionner")
    added, duplicates = merge(args.into, args.sources)
    _, rows = read_journal(args.into)
    total = len(rows) + len(added)
    print(f"{args.into} : {len(rows)} paire(s), + {len(added)} ajoutée(s), "
          f"{duplicates} doublon(s) identique(s) ignoré(s) → {total}")
    if args.dry_run or not added:
        return 0
    text = args.into.read_text()
    if text and not text.endswith("\n"):
        # A line cut by a crash: read_journal ignored it, drop it here too.
        text = text[:text.rfind("\n") + 1]
    tmp = args.into.with_suffix(args.into.suffix + ".fusion")
    with tmp.open("w") as out:
        out.write(text)
        for i in sorted(added):
            out.write(json.dumps(added[i], ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, args.into)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

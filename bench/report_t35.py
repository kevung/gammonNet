#!/usr/bin/env python3
"""T35 — le dépouillement : du journal aux chiffres, protocole compris.

Lit un journal produit par `bench/run_t35.py` et imprime la mesure avec ce
que `BRIEF.md` §5 exige d'une mesure : le protocole (l'en-tête du journal,
verbatim), le volume, la graine, et l'intervalle de confiance — bootstrap sur
les paires dupliquées, jamais sur les parties, parce que les deux manches
d'une paire partagent leurs dés et ne sont pas indépendantes.

Il ne joue rien : relancer le dépouillement est gratuit, à n'importe quel
stade de la campagne. Sur un journal incomplet il dit combien de paires
manquent et donne le chiffre PARTIEL, clairement marqué comme tel.

    python bench/report_t35.py --journal docs/mesures/t35-money.jsonl
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from run_t35 import read_journal  # noqa: E402

from gammonnet.arena import bootstrap_ci  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    args = parser.parse_args()

    header, rows = read_journal(args.journal)
    if header is None:
        raise SystemExit(f"{args.journal} : pas d'en-tête — pas un journal T35")
    if not rows:
        raise SystemExit(f"{args.journal} : aucune paire jouée")

    target = header.get("pairs_target", 0)
    present = sorted(rows)
    missing = target - len(present)

    print("── Protocole (en-tête du journal, verbatim) ──")
    for key, value in header.items():
        if key != "header":
            print(f"  {key}: {value}")
    print()

    label = "MESURE COMPLÈTE" if missing == 0 else (
        f"CHIFFRE PARTIEL — {missing} paire(s) manquante(s) sur {target}")
    print(f"── {label} ──")
    print(f"  paires jouées : {len(present)} (2 {'matchs' if header['mode'] == 'match' else 'parties'} chacune), graine {header['seed']}")

    nets = [rows[i]["net"] for i in present]
    samples = [n / 2.0 for n in nets]
    low, high = bootstrap_ci(samples, args.bootstrap, seed=header["seed"])

    if header["mode"] == "money":
        ppg = sum(nets) / (2.0 * len(nets))
        print(f"  ppg cubeful ({header['ours']['name']} vs "
              f"{header['theirs']['name']}) : {ppg:+.4f} "
              f"[{low:+.4f} ; {high:+.4f}] (IC 95 %, bootstrap sur les paires)")
    else:
        mean_wins = sum(nets) / (2.0 * len(nets))
        rate = (mean_wins + 1.0) / 2.0
        print(f"  MWC aux scores échantillonnés : {rate * 100:.2f} % "
              f"[{(low + 1) / 2 * 100:.2f} ; {(high + 1) / 2 * 100:.2f}] "
              f"(IC 95 %, bootstrap sur les paires)")
        print(f"  (victoires nettes par paire : {mean_wins:+.4f} "
              f"[{low:+.4f} ; {high:+.4f}])")

        cells: dict[tuple, list] = defaultdict(list)
        for i in present:
            row = rows[i]
            cells[(row["away_a"], row["away_b"], row["post_crawford"])].append(row["net"])
        print("\n  par score de départ (away_a, away_b, post-Crawford) :")
        for cell in sorted(cells):
            cell_nets = cells[cell]
            mean = sum(cell_nets) / (2.0 * len(cell_nets))
            print(f"    {cell}: {len(cell_nets):5d} paires, "
                  f"victoires nettes {mean:+.3f}")

    stalled = sum(1 for i in present if rows[i]["stalled"])
    doubles = sum(rows[i]["doubles"] for i in present)
    biggest = max(rows[i]["biggest_cube"] for i in present)
    turns = sum(rows[i]["turns"] for i in present)
    print(f"\n  videau : {doubles} double(s) au total "
          f"({doubles / len(present):.2f}/paire), plus gros videau {biggest}")
    if header["mode"] == "money":
        cashed = sum(rows[i]["cashed"] for i in present)
        print(f"  parties encaissées sur pass : {cashed} "
              f"({cashed / (2 * len(present)) * 100:.1f} %)")
    print(f"  tours joués : {turns}")
    if stalled:
        print(f"  ⚠ {stalled} paire(s) avec partie abandonnée à la limite de "
              f"tours — comptées 0, à examiner")
    if missing:
        print(f"\n  Reprise : relancer bench/run_t35.py avec le même journal "
              f"({missing} paire(s) restantes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

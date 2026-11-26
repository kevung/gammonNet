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

Plusieurs `--journal` se lisent EN COMMUN : des lots indépendants de la même
confrontation, joués sous des graines différentes (deux machines, par
exemple). Les paires de graines différentes ne partagent aucun dé, donc la
réunion est un échantillon plus grand de la même quantité. Refus si les
joueurs, le mode ou le réglage diffèrent, ou si deux journaux ont la même
graine — leurs paires de même index seraient les mêmes parties, comptées
deux fois. Les empreintes numériques peuvent différer (deux builds) : elles
sont imprimées, pas exigées égales.

    python bench/report_t35.py --journal a.jsonl --journal b.jsonl
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


# Fields that may differ between pooled journals: the dice (seed), the build
# (fingerprints) and how far each pilot was first aimed (pairs_target).
POOLABLE = {"seed", "eval_fingerprint", "pairs_target"}


def comparable(header: dict) -> dict:
    out = {k: v for k, v in header.items() if k not in POOLABLE}
    if isinstance(out.get("theirs"), dict):
        out["theirs"] = {k: v for k, v in out["theirs"].items()
                         if k != "eval_fingerprint"}
    return out


def print_luck_adjusted(header: dict, rows: list[dict], raw: list[float],
                        bootstrap: int) -> None:
    """La colonne corrigée de la chance : `(net − luck)` par paire, même unité
    que la brute. La chance a une espérance nulle par construction ; sa moyenne
    est imprimée avec son z, parce qu'un z loin de zéro dirait que la
    correction est cassée — c'est le garde-fou de T39, `average_luck`."""
    if any("luck" not in r for r in rows):
        raise SystemExit("en-tête avec juge de la chance, mais des paires sans "
                         "chance : journal mêlé — refus")
    luck = [r["luck"] / 2.0 for r in rows]
    adjusted = [a - b for a, b in zip(raw, luck)]
    n = len(adjusted)

    def var(xs):
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / (len(xs) - 1) if len(xs) > 1 else 0.0

    mean_adj = sum(adjusted) / n
    low, high = bootstrap_ci(adjusted, bootstrap, seed=header["seed"])
    v_raw, v_adj, v_luck = var(raw), var(adjusted), var(luck)
    mean_luck = sum(luck) / n
    z_luck = mean_luck / (v_luck / n) ** 0.5 if v_luck > 0 else 0.0
    ref = header["luck_reference"]
    print(f"\n── Colonne corrigée de la chance (juge {ref['model']}, "
          f"empreinte {ref['eval_fingerprint']}) ──")
    if header["mode"] == "money":
        print(f"  ppg corrigé : {mean_adj:+.4f} [{low:+.4f} ; {high:+.4f}] "
              f"(IC 95 %, bootstrap sur les paires)")
    else:
        print(f"  MWC corrigée : {(mean_adj + 1) / 2 * 100:.2f} % "
              f"[{(low + 1) / 2 * 100:.2f} ; {(high + 1) / 2 * 100:.2f}] "
              f"(victoires nettes {mean_adj:+.4f} [{low:+.4f} ; {high:+.4f}])")
    ratio = v_raw / v_adj if v_adj > 0 else float("inf")
    print(f"  variance par paire : brute {v_raw:.5f}, corrigée {v_adj:.5f} "
          f"— divisée par {ratio:.2f}")
    print(f"  chance moyenne : {mean_luck:+.5f} (z = {z_luck:+.2f} ; "
          f"centrée par construction, |z| > 3 dirait une correction cassée)")
    print(f"  identité comptable : brute = corrigée + chance, écart "
          f"{abs(sum(raw) / n - mean_adj - mean_luck):.1e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True, action="append",
                        help="répétable : plusieurs lots se lisent en commun")
    parser.add_argument("--bootstrap", type=int, default=10_000)
    args = parser.parse_args()

    journals = []
    for path in args.journal:
        header, rows = read_journal(path)
        if header is None:
            raise SystemExit(f"{path} : pas d'en-tête — pas un journal T35")
        if not rows:
            raise SystemExit(f"{path} : aucune paire jouée")
        journals.append((path, header, rows))

    header = journals[0][1]
    seeds = [h["seed"] for _, h, _ in journals]
    if len(set(seeds)) != len(seeds):
        raise SystemExit(f"graines répétées {seeds} : mêmes dés, paires comptées "
                         f"deux fois — refus (bench/merge_t35.py réunit les "
                         f"morceaux d'une même graine)")
    for path, other, _ in journals[1:]:
        a, b = comparable(header), comparable(other)
        if a != b:
            keys = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            raise SystemExit(f"{path} : autre confrontation que {journals[0][0]} "
                             f"(champs {keys}) — refus")

    print("── Protocole (en-tête du journal, verbatim) ──")
    for key, value in header.items():
        if key != "header":
            print(f"  {key}: {value}")
    print()

    missing = 0
    for path, own, rows in journals:
        # A pilot resumed with a larger --pairs keeps its first target in the
        # header: more pairs than that is not a negative shortfall.
        missing += max(0, own.get("pairs_target", 0) - len(rows))
    if len(journals) > 1:
        print(f"── {len(journals)} journaux lus en commun ──")
        for path, own, rows in journals:
            theirs_fp = own["theirs"].get("eval_fingerprint") if isinstance(
                own.get("theirs"), dict) else None
            print(f"  {path} : {len(rows)} paires, graine {own['seed']}, "
                  f"empreinte {own['eval_fingerprint']}"
                  + (f" / {theirs_fp}" if theirs_fp else ""))
        print()

    present = [(j, i) for j, (_, _, rows) in enumerate(journals) for i in sorted(rows)]
    rows = {(j, i): journals[j][2][i] for j, i in present}
    target = sum(own.get("pairs_target", 0) for _, own, _ in journals)

    label = "MESURE COMPLÈTE" if missing == 0 else (
        f"CHIFFRE PARTIEL — {missing} paire(s) manquante(s) sur {target}")
    print(f"── {label} ──")
    print(f"  paires jouées : {len(present)} (2 {'matchs' if header['mode'] == 'match' else 'parties'} chacune), "
          f"graine{'s' if len(seeds) > 1 else ''} {', '.join(map(str, seeds))}")

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

    if "luck_reference" in header:
        print_luck_adjusted(header, [rows[i] for i in present], samples,
                            args.bootstrap)

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

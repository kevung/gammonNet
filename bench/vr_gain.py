"""T39 — le gain de la réduction de variance par la chance, chiffré.

Deux mesures, parce que la fiche exige les deux :

1. **Le gain.** Sur des positions de natures différentes (contact, course hors
   domaine, bearoff en domaine, contact cubeful), le même rollout avec et sans
   correction, mêmes essais, même graine : rapport des variances et rapport des
   temps. Le chiffre qui compte est le rapport d'EFFICACITÉ — variance gagnée
   par seconde dépensée — car la correction coûte environ une recherche 1-ply
   par coup joué et un gain de variance qui coûterait plus qu'il ne rapporte
   serait une perte déguisée.

2. **Le non-biais.** La correction a une espérance nulle par construction,
   mais la construction, c'est le code, et le code se vérifie : sur la position
   de contact, six graines corrigées contre une vérité indépendante (six
   tranches brutes de 2 592 essais). L'écart doit être compatible avec zéro et
   la dispersion inter-graines conforme au se annoncé.

Usage : python bench/vr_gain.py [--trials 216] [--workers 12]
Sortie : docs/mesures/t39-vr-gain.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import stdev

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.rules import NUM_POINTS, WHITE, Position  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"

X3 = (0.688, 0.566, 0.687)  # t34-efficacite.json — mesurées, jamais recyclées


def build(white, black, turn=WHITE, bar=(0, 0)):
    points = [0] * NUM_POINTS
    for point, count in white:
        points[point] = count
    for point, count in black:
        points[point] = -count
    off_w = 15 - sum(c for _, c in white) - bar[0]
    off_b = 15 - sum(c for _, c in black) - bar[1]
    return Position(points=tuple(points), bar=bar, off=(off_w, off_b), turn=turn)


POSITIONS = {
    # Position initiale : plein contact, l'arbitrage type de bench/arbitrate_cube.
    "contact-initial": build(
        [(23, 2), (12, 5), (7, 3), (5, 5)],
        [(0, 2), (11, 5), (16, 3), (18, 5)]),
    # Course longue, HORS du domaine de la table : là où l'arbitre n'a que lui.
    "course-hors-domaine": build(
        [(23, 2), (12, 4), (9, 3), (5, 6)],
        [(0, 2), (13, 4), (15, 3), (19, 6)]),
    # Bearoff EN domaine : la vérité exacte existe, le gain s'y mesure aussi.
    "bearoff-en-domaine": build(
        [(0, 2), (1, 2), (2, 2)],
        [(23, 2), (22, 2), (21, 1)]),
}


def gain_job(args):
    name, vr, trials, seed, cubeful = args
    from gammonnet import evalcache
    from gammonnet.bearoff import disable_shared, use_shared
    from gammonnet.infer import Network
    from gammonnet.rollout import RolloutConfig, rollout

    evalcache.enable()
    if DATABASE.exists():
        use_shared(DATABASE)
    try:
        network = Network.load(MODEL)
        kwargs = {}
        if cubeful:
            kwargs = dict(use_cube=True, cube_owner=0, cube_x=X3,
                          jacoby=True, cube_defer_first=True)
        config = RolloutConfig(trials=trials, truncate=11, seed=seed,
                               variance_reduction=vr, **kwargs)
        started = time.time()
        result = rollout(network, POSITIONS[name], config)
        elapsed = time.time() - started
        return {"position": name, "cubeful": cubeful, "vr": vr,
                "trials": result.trials, "equity": result.equity,
                "se": result.standard_error, "luck": result.average_luck,
                "seconds": elapsed}
    finally:
        if DATABASE.exists():
            disable_shared()


def bias_job(args):
    seed, trials, vr = args
    out = gain_job(("contact-initial", vr, trials, seed, False))
    return out | {"seed": seed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=216)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "mesures" / "t39-vr-gain.json")
    args = parser.parse_args()

    seed = 20260808
    gain_jobs = []
    for name in POSITIONS:
        for vr in (False, True):
            gain_jobs.append((name, vr, args.trials, seed, False))
    # Le videau vivant, sur le contact seulement : c'est la colonne de
    # l'arbitrage, celle dont la puissance manquait.
    for vr in (False, True):
        gain_jobs.append(("contact-initial", vr, args.trials, seed, True))

    bias_jobs = [(1000 + i, 2592, False) for i in range(6)]
    bias_jobs += [(2000 + i, 108, True) for i in range(6)]

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        gains = list(pool.map(gain_job, gain_jobs))
        bias = list(pool.map(bias_job, bias_jobs))

    # ── Le gain, par position ────────────────────────────────────────
    table = []
    for name in POSITIONS:
        for cubeful in (False, True):
            pair = [g for g in gains
                    if g["position"] == name and g["cubeful"] == cubeful]
            if len(pair) != 2:
                continue
            plain = next(g for g in pair if not g["vr"])
            corrected = next(g for g in pair if g["vr"])
            variance_ratio = (plain["se"] / corrected["se"]) ** 2
            time_ratio = corrected["seconds"] / plain["seconds"]
            table.append({
                "position": name, "cubeful": cubeful,
                "se_plain": plain["se"], "se_vr": corrected["se"],
                "seconds_plain": plain["seconds"],
                "seconds_vr": corrected["seconds"],
                "variance_ratio": variance_ratio,
                "time_ratio": time_ratio,
                "efficiency": variance_ratio / time_ratio,
            })
            print(f"{name}{' (cubeful)' if cubeful else '':12s} : "
                  f"se {plain['se']:.4f} → {corrected['se']:.4f} "
                  f"(variance ÷{variance_ratio:.0f}), "
                  f"temps ×{time_ratio:.1f}, efficacité ×{variance_ratio / time_ratio:.1f}",
                  flush=True)

    # ── Le non-biais ─────────────────────────────────────────────────
    plain_rows = [b for b in bias if not b["vr"]]
    vr_rows = [b for b in bias if b["vr"]]
    n_truth = sum(b["trials"] for b in plain_rows)
    truth = sum(b["equity"] * b["trials"] for b in plain_rows) / n_truth
    truth_se = (sum((b["se"] * b["trials"]) ** 2
                    for b in plain_rows) ** 0.5) / n_truth
    vr_mean = sum(b["equity"] for b in vr_rows) / len(vr_rows)
    vr_se = (sum(b["se"] ** 2 for b in vr_rows) ** 0.5) / len(vr_rows)
    gap = vr_mean - truth
    gap_se = (truth_se ** 2 + vr_se ** 2) ** 0.5
    dispersion = stdev(b["equity"] for b in vr_rows)
    print(f"\nnon-biais : vérité {truth:+.4f}±{truth_se:.4f} "
          f"({n_truth} essais bruts), corrigé {vr_mean:+.4f}±{vr_se:.4f} "
          f"(6×{vr_rows[0]['trials']}), écart {gap:+.4f}±{gap_se:.4f} ; "
          f"dispersion inter-graines {dispersion:.4f}")

    report = {
        "task": "T39-vr-gain",
        "trials": args.trials,
        "seed": seed,
        "truncate": 11,
        "gains": table,
        "bias_check": {
            "position": "contact-initial",
            "truth": truth, "truth_se": truth_se, "truth_trials": n_truth,
            "vr_mean": vr_mean, "vr_se": vr_se,
            "vr_runs": len(vr_rows), "vr_trials_each": vr_rows[0]["trials"],
            "gap": gap, "gap_se": gap_se,
            "seed_dispersion": dispersion,
            "rows": bias,
        },
    }
    args.out.write_text(json.dumps(report, indent=1))
    print(f"écrit dans {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

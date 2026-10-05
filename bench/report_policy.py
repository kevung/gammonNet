"""Dépouiller la mesure de la politique sans état contre une référence appariée — spec §9.2.

Le journal de la politique est joué avec la clé de dés de la référence
(`run_t35.py --dice-key-from`) : sa paire i rejoue la situation de la paire i de
la référence — même score échantillonné (match), mêmes jets. D'où trois chiffres :

* le résultat du journal, IC 95 % bootstrap sur les paires (comme `report_t35`) ;
* le résultat de la référence **sur les mêmes indices** ;
* l'écart apparié (journal − référence) par paire, IC 95 % bootstrap : c'est lui
  qui dit si le journal « retrouve la référence dans son intervalle ».

En match, le résultat est la MWC ; en money, les points par partie (ppg
cubeful). Les deux journaux doivent être du même mode et tirés de la même clé
de dés, sinon l'appariement ne veut rien dire et le rapport refuse.

    python bench/report_policy.py --journal docs/mesures/politique-t35-match.jsonl \\
        --reference docs/mesures/t35-match-v2.jsonl
    python bench/report_policy.py --journal docs/mesures/adoption-256-t35-money-candidat.jsonl \\
        --reference docs/mesures/adoption-256-t35-money-incumbent.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "python"))

from run_t35 import read_journal  # noqa: E402

from gammonnet.arena import bootstrap_ci, pair_key  # noqa: E402


def dice_key(header: dict) -> str:
    """La clé dont dérivent les dés d'un journal : la sienne si elle a été
    reprise d'un autre, sinon celle des noms de ses deux joueurs."""
    return header.get("dice_key") or pair_key(header["ours"]["name"],
                                             header["theirs"]["name"])


def paired_summary(header: dict, rows: dict[int, dict], ref_header: dict,
                   ref_rows: dict[int, dict], bootstrap: int = 10_000) -> dict:
    """Les trois chiffres, sur les paires communes et non bloquées.

    Un échantillon par paire : `net / 2`, soit des victoires nettes par match
    (match) ou des points par partie (money) — les deux parties d'une paire
    dupliquée ne sont jamais rééchantillonnées séparément.
    """
    mode = header["mode"]
    if ref_header["mode"] != mode:
        raise ValueError(f"modes différents : {mode} contre {ref_header['mode']}")
    if dice_key(header) != dice_key(ref_header):
        raise ValueError("clés de dés différentes : les paires ne s'apparient pas")
    common = sorted(i for i in rows if i in ref_rows
                    and not rows[i].get("stalled") and not ref_rows[i].get("stalled"))
    if not common:
        raise ValueError("aucune paire commune")
    if mode == "match":
        for i in common:
            a, b = rows[i], ref_rows[i]
            if (a["away_a"], a["away_b"], a["post_crawford"]) != (
                    b["away_a"], b["away_b"], b["post_crawford"]):
                raise ValueError(f"paire {i} : pas la même situation de départ")

    ours = [rows[i]["net"] / 2.0 for i in common]
    ref = [ref_rows[i]["net"] / 2.0 for i in common]
    diff = [a - b for a, b in zip(ours, ref)]
    seed = header["seed"]
    return {
        "mode": mode,
        "pairs": len(common),
        "first": common[0],
        "last": common[-1],
        "ours": (sum(ours) / len(ours), *bootstrap_ci(ours, bootstrap, seed=seed)),
        "reference": (sum(ref) / len(ref), *bootstrap_ci(ref, bootstrap, seed=seed)),
        "diff": (sum(diff) / len(diff), *bootstrap_ci(diff, bootstrap, seed=seed)),
        "same": sum(1 for a, b in zip(ours, ref) if a == b),
    }


def mwc(net_wins: float) -> float:
    return (net_wins + 1.0) / 2.0 * 100.0


def describe(header: dict) -> str:
    ours = header["ours"]
    model = Path(ours["model"]).name if ours.get("model") else "?"
    return f"{ours.get('policy_level') or ours['name']}, {model}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=10_000)
    args = parser.parse_args()

    header, rows = read_journal(args.journal)
    ref_header, ref_rows = read_journal(args.reference)
    if header is None or ref_header is None:
        raise SystemExit("journal sans en-tête")
    try:
        s = paired_summary(header, rows, ref_header, ref_rows, args.bootstrap)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print(f"paires communes : {s['pairs']} (indices {s['first']}..{s['last']})")
    mean, lo, hi = s["ours"]
    rmean, rlo, rhi = s["reference"]
    dmean, dlo, dhi = s["diff"]
    if s["mode"] == "money":
        print(f"journal ({describe(header)}) : {mean:+.4f} ppg [{lo:+.4f} ; {hi:+.4f}]")
        print(f"référence ({describe(ref_header)}), mêmes indices : "
              f"{rmean:+.4f} ppg [{rlo:+.4f} ; {rhi:+.4f}]")
        print(f"écart apparié journal − référence : {dmean:+.4f} ppg "
              f"[{dlo:+.4f} ; {dhi:+.4f}]")
    else:
        print(f"journal ({describe(header)}) : MWC {mwc(mean):.2f} % "
              f"[{mwc(lo):.2f} ; {mwc(hi):.2f}]")
        # The full-journal figure of a reference has ONE source, its published
        # verdict; only the same-index figure is computed here.
        print(f"référence ({describe(ref_header)}), mêmes indices : MWC {mwc(rmean):.2f} % "
              f"[{mwc(rlo):.2f} ; {mwc(rhi):.2f}]")
        print(f"écart apparié journal − référence : {dmean / 2 * 100:+.2f} points de MWC "
              f"[{dlo / 2 * 100:+.2f} ; {dhi / 2 * 100:+.2f}]")
    print(f"paires au même résultat net : {s['same']}/{s['pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

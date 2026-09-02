#!/usr/bin/env python3
"""T84 — le balayage de largeur, en round-robin.

Neuf binaires : trois largeurs (8, 16, 32) × trois noyaux (auto-vectorisé sur la
cible x86-64 de base, auto-vectorisé en AVX2, intrinsèques en AVX2). Chacun est
compilé avec sa largeur en **constante**, ce que ni `bench_batch.c` (largeur en
variable d'exécution) ni le balayage d'entrée du 2026-09-02 (un seul relevé par
largeur, machine en dérive) ne faisaient.

Le round-robin est le point : lancer les neuf binaires l'un après l'autre, P
fois, plutôt que P fois chacun à la suite. La machine dérive de ±20 % sur une
séance ; en bloc, cette dérive entre directement dans la comparaison, et c'est
exactement ce qui avait rendu le balayage d'entrée non concluant.

    python bench/width_sweep.py [--passes 3] [--reps 5] [--decisions 10]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
PRUNE = ROOT / "models" / "prune_32.bin"

WIDTHS = [8, 16, 32]

#: Le natif a TROIS noyaux et le WebAssembly deux, et ce n'est pas une
#: simplification : `-march=native` sépare « écrit à la main » de « jeu
#: d'instructions plus large », que le premier chiffre venu confondrait. En
#: WebAssembly il n'y a pas ce choix — SIMD128 est SIMD128, quatre voies, et
#: `-msimd128` est passé aux deux.
TARGETS = {
    "native": {
        "kernels": ["auto", "auto-avx2", "intrin"],
        "labels": {
            "auto": "auto-vectorisé (base x86-64, SSE)",
            "auto-avx2": "auto-vectorisé (-march=native, AVX2)",
            "intrin": "intrinsèques (AVX2, écrites à la main)",
        },
        "baseline": (32, "auto"),
    },
    "wasm": {
        "kernels": ["auto", "intrin"],
        "labels": {
            "auto": "auto-vectorisé (SIMD128)",
            "intrin": "intrinsèques (SIMD128, écrites à la main)",
        },
        "baseline": (32, "auto"),
    },
}

RATE = re.compile(r"débit du noyau[^:]*:\s*([0-9.]+) éval/s")
DECISION = re.compile(r"décision 2-ply[^:]*:\s*([0-9.]+) s\s*\(min ([0-9.]+)")
EXACT = re.compile(r"max\|Δ\| = ([0-9.e+-]+)")
KERNEL = re.compile(r"noyau (.+)$", re.MULTILINE)


def run(target: str, width: int, kernel: str, reps: int, decisions: int) -> dict:
    if target == "wasm":
        # Le `.data` des fichiers préchargés doit être à côté du `.js`, et les
        # chemins de modèle sont ceux du système de fichiers VIRTUEL.
        directory = ROOT / "build" / "wasm"
        binary = directory / f"bench_kernel_{kernel}_{width}.js"
        command = ["node", binary.name,
                   "models/cubeless_prob5_512_512_256_128.bin",
                   "models/prune_32.bin", str(reps), str(decisions)]
        hint = "make bench-width-wasm"
    else:
        directory = ROOT
        binary = ROOT / "build" / "kernel" / f"bench_{kernel}_{width}"
        command = [str(binary), str(MODEL), str(PRUNE), str(reps), str(decisions)]
        hint = "make bench-width"
    if not binary.exists():
        sys.exit(f"manquant : {binary} — lancer `{hint}` d'abord")
    done = subprocess.run(command, capture_output=True, text=True, cwd=directory)
    if done.returncode != 0:
        sys.exit(done.stdout + done.stderr)
    text = done.stdout
    decision = DECISION.search(text)
    return {
        "rate": float(RATE.search(text).group(1)),
        "decision": float(decision.group(1)),
        "decision_min": float(decision.group(2)),
        "exact": float(EXACT.search(text).group(1)),
        "kernel": KERNEL.search(text).group(1).strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), default="native")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--decisions", type=int, default=10)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    spec = TARGETS[args.target]
    kernels, label, baseline_key = spec["kernels"], spec["labels"], spec["baseline"]

    results: dict[tuple[int, str], list[dict]] = {}
    for p in range(args.passes):
        for width in WIDTHS:
            for kernel in kernels:
                got = run(args.target, width, kernel, args.reps, args.decisions)
                results.setdefault((width, kernel), []).append(got)
                print(f"passe {p + 1}/{args.passes}  largeur {width:2d}  "
                      f"{kernel:10s}  {got['rate']:9.1f} éval/s  "
                      f"{got['decision']:.4f} s", flush=True)

    print()
    print(f"── T84 — {args.target} : débit du noyau et décision,"
          " par largeur et par noyau ──")
    print(f"{'largeur':>7} {'noyau':<40} {'éval/s':>10} {'gain':>7} "
          f"{'s/décision':>11} {'gain':>7} {'max|Δ|':>9}")

    baseline_rate = statistics.median(r["rate"] for r in results[baseline_key])
    baseline_dec = statistics.median(r["decision"] for r in results[baseline_key])

    table = []
    for width in WIDTHS:
        for kernel in kernels:
            runs = results[(width, kernel)]
            rate = statistics.median(r["rate"] for r in runs)
            dec = statistics.median(r["decision"] for r in runs)
            worst = max(r["exact"] for r in runs)
            print(f"{width:>7} {label[kernel]:<40} {rate:>10.1f} "
                  f"{rate / baseline_rate:>6.2f}x {dec:>11.4f} "
                  f"{baseline_dec / dec:>6.2f}x {worst:>9.1e}")
            table.append({
                "target": args.target,
                "width": width, "kernel": kernel, "label": label[kernel],
                "kernel_built": runs[0]["kernel"],
                "rate": rate, "rate_gain": rate / baseline_rate,
                "decision": dec, "decision_gain": baseline_dec / dec,
                "decision_min": min(r["decision_min"] for r in runs),
                "max_delta": worst,
                "samples": [{"rate": r["rate"], "decision": r["decision"]} for r in runs],
            })

    print()
    print(f"référence des colonnes « gain » : largeur {baseline_key[0]},"
          f" {label[baseline_key[1]]} — ce qui est livré aujourd'hui.")
    non_exact = [t for t in table if t["max_delta"] != 0.0]
    if non_exact:
        print("ATTENTION — le bit à bit est rompu sur :",
              ", ".join(f"{t['width']}/{t['kernel']}" for t in non_exact))
    else:
        print("bit à bit tenu à TOUTES les largeurs et sur les trois noyaux"
              " (max|Δ| = 0).")

    if args.json:
        args.json.write_text(json.dumps(table, indent=2, ensure_ascii=False))
        print(f"→ {args.json}")


if __name__ == "__main__":
    main()

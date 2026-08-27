#!/usr/bin/env python3
"""T70 — où en est la campagne, en une commande.

    python tools/etat_t70.py

Une campagne de deux jours répartie sur 26 processus muets pose une question
simple à laquelle rien ne répondait : **est-ce que ça avance, ou est-ce que ça
patine ?** Les deux se ressemblent vues de `uptime` — une machine à 26 de charge
peut aussi bien récolter que tourner en rond dans une partie qui ne finit pas.

Ce banc lit trois sources et ne devine rien :

- le **journal de campagne**, qui dit quelle étape est en cours ;
- le **fichier de suivi de la récolte**, un relevé par processus, dont on garde
  le dernier de chacun ;
- le **journal d'arbitrage**, dont chaque ligne est une décision payée.

Ce qu'il refuse de faire : présenter une estimation de temps restant comme une
mesure. Les débits affichés sont observés ; les « reste ~ » en découlent par
règle de trois, et le disent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = Path(os.environ.get("T70_CORPUS_PROGRESS", "/tmp/t70-corpus-progress.log"))
LOGS = Path(os.environ.get("LOGS", "/home/kunger/dev/gammonNet-logs"))


def running(pattern: str) -> list[str]:
    """Les processus RÉELS : un shell qui cite un nom n'est pas un calcul."""
    try:
        out = subprocess.run(["pgrep", "-af", pattern], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in out.splitlines() if "shell-snapshots" not in line]



def harvest_target() -> int | None:
    """La cible de la récolte en cours, lue sur la ligne de commande du parent.

    Elle n'est écrite nulle part ailleurs : le fichier de suivi ne porte que le
    budget d'examen. La deviner serait pire que de ne rien dire.
    """
    for line in running("python.*build_corpus_t70[.]py"):
        parts = line.split()
        if "--target" in parts:
            try:
                return int(parts[parts.index("--target") + 1])
            except (ValueError, IndexError):
                return None
    return None


def harvest_state():
    """Le dernier relevé de chaque processus de récolte."""
    if not PROGRESS.exists():
        return None
    latest = {}
    for line in PROGRESS.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        latest[row["worker"]] = row
    if not latest:
        return None
    rows = list(latest.values())
    return {
        "workers": len(rows),
        "kept": sum(r["kept"] for r in rows),
        "examined": sum(r["examined"] for r in rows),
        "budget": sum(r["budget"] for r in rows),
        "seconds": max(r["seconds"] for r in rows),
        "age": time.time() - PROGRESS.stat().st_mtime,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--context", default="money")
    parser.add_argument("--tail", type=int, default=6)
    args = parser.parse_args()

    print(f"T70 — état au {time.strftime('%Y-%m-%d %H:%M:%S')}")

    orchestrator = running("bash .*campagne_t70_tranches[.]sh")
    print(f"  orchestrateur : "
          f"{'vivant, PID ' + orchestrator[0].split()[0] if orchestrator else '⚠ ABSENT'}")
    print(f"  charge : {Path('/proc/loadavg').read_text().split()[0]}"
          f"   récolte {len(running('python.*build_corpus_t70[.]py'))} proc."
          f"   arbitrage {len(running('python.*arbitrate_t70[.]py'))} proc.")

    # ── les tranches ───────────────────────────────────────────────────────
    tranches = sorted((ROOT / "docs/corpus/t70/tranches").glob("tranche-*"))
    if tranches:
        print("\n  tranches récoltées :")
        total = 0
        for path in tranches:
            corpus = path / f"corpus-{args.context}.jsonl"
            if corpus.exists() and corpus.stat().st_size:
                n = sum(1 for _ in corpus.open())
                total += n
                print(f"    {path.name}  ✓ {n:6d} décisions")
            else:
                print(f"    {path.name}  … en cours ou à faire")
        print(f"    {'total':22s}  {total:6d}")

    # ── la récolte en cours ────────────────────────────────────────────────
    state = harvest_state()
    if state:
        share = state["examined"] / state["budget"] if state["budget"] else 0.0
        rate = state["examined"] / state["seconds"] if state["seconds"] else 0.0
        stale = state["age"] > 600
        print(f"\n  récolte en cours — {state['workers']} processus ont parlé")
        print(f"    {state['examined']}/{state['budget']} positions examinées "
              f"({100 * share:.1f} %), {state['kept']} décisions gardées")
        print(f"    {rate * 60:.0f} positions/min observées")

        # Ce qui arrête une récolte, ce n'est PAS l'épuisement du budget
        # d'examen : c'est le remplissage des quotas, qui arrive bien avant.
        # Extrapoler vers le budget donnait « reste ~5 h » là où les deux
        # premières tranches ont mis 2 h 30 — une estimation deux fois trop
        # longue, annoncée avec le même aplomb qu'une bonne. On extrapole donc
        # sur les décisions GARDÉES vers la cible, et le budget redevient ce
        # qu'il est : un plafond, pas un objectif.
        target = harvest_target()
        if target and state["kept"]:
            kept_rate = state["kept"] / state["seconds"] if state["seconds"] else 0.0
            left = (target - state["kept"]) / kept_rate if kept_rate else 0.0
            print(f"    {state['kept']}/{target} décisions gardées → "
                  f"reste ~{left / 3600:.1f} h (règle de trois sur les décisions "
                  f"gardées, pas une mesure)")
            if rate:
                ceiling = (state["budget"] - state["examined"]) / rate
                print(f"    le budget d'examen, lui, ne serait épuisé qu'après "
                      f"~{ceiling / 3600:.1f} h — c'est un plafond, pas un objectif")
        print(f"    dernier relevé il y a {state['age']:.0f} s"
              f"{'   ⚠ PLUS DE DIX MINUTES — vérifier' if stale else ''}")

    # ── l'arbitrage ────────────────────────────────────────────────────────
    journal = ROOT / f"docs/corpus/t70/registre-{args.context}.jsonl.journal"
    if journal.exists():
        done = sum(1 for _ in journal.open()) - 1  # l'en-tête
        corpus = ROOT / f"docs/corpus/t70/corpus-{args.context}.jsonl"
        target = sum(1 for _ in corpus.open()) if corpus.exists() else 0
        age = time.time() - journal.stat().st_mtime
        print(f"\n  arbitrage : {done}/{target} décisions au journal")
        print(f"    dernière écriture il y a {age:.0f} s"
              f"{'   ⚠ PLUS DE DIX MINUTES — vérifier' if age > 600 else ''}")
        print("    (une coupure ici ne coûte que les tranches en vol : "
              "relancer la campagne reprend au journal)")

    # ── le journal de campagne ─────────────────────────────────────────────
    log = LOGS / "t70-campagne.log"
    if log.exists():
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        print(f"\n  {log} — {args.tail} dernières lignes :")
        for line in lines[-args.tail:]:
            print(f"    {line[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

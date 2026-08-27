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
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = Path(os.environ.get("T70_CORPUS_PROGRESS", "/tmp/t70-corpus-progress.log"))
#: La v2 lance plusieurs récoltes de front, chacune avec son propre fichier de
#: suivi : un seul fichier partagé mélangerait deux tranches, et l'état
#: additionnerait des budgets qui n'ont rien à voir.
PROGRESS_GLOB = "t70-progress-*.log"
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
    """L'état de CHAQUE récolte en cours, séparément.

    La v2 lance plusieurs récoltes de front, chacune avec son fichier de suivi.
    Les additionner produirait un non-sens : les budgets de deux tranches n'ont
    rien à voir, et le total des décisions gardées dépasserait la cible d'une
    seule — c'est ce que l'état affichait, avec un temps restant négatif.

    Les fichiers dont plus rien ne bouge depuis STALE secondes appartiennent à
    des récoltes terminées : ils sont écartés, sinon une tranche finie il y a
    trois heures continuerait de peser sur l'état.
    """
    #: Un fichier de suivi qu'aucun processus n'a touché depuis ce délai
    #: appartient à une récolte finie. 20 min laisse de la marge au relevé le
    #: plus espacé (~90 s) sans traîner une tranche terminée pendant une heure.
    STALE = 1200
    now = time.time()
    files = sorted(Path("/tmp").glob(PROGRESS_GLOB))
    if PROGRESS.exists():
        files.append(PROGRESS)
    out = []
    for path in files:
        age = now - path.stat().st_mtime
        if age > STALE:
            continue
        latest = {}
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest[row["worker"]] = row
        if not latest:
            continue
        rows = list(latest.values())
        name = re.sub(r"^t70-progress-|\.log$", "", path.name)
        out.append({
            "name": name if name != "t70-corpus-progress" else "(v1)",
            "workers": len(rows),
            "idle": sum(1 for r in rows
                        if max(x["seconds"] for x in rows) - r["seconds"] > 600),
            "kept": sum(r["kept"] for r in rows),
            "examined": sum(r["examined"] for r in rows),
            "budget": sum(r["budget"] for r in rows),
            "seconds": max(r["seconds"] for r in rows),
            "age": age,
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--context", default="money")
    parser.add_argument("--tail", type=int, default=6)
    args = parser.parse_args()

    print(f"T70 — état au {time.strftime('%Y-%m-%d %H:%M:%S')}")

    orchestrator = running("bash .*campagne_t70_(tranches|v2)[.]sh")
    print(f"  orchestrateur : "
          f"{'vivant, PID ' + orchestrator[0].split()[0] if orchestrator else '⚠ ABSENT'}")
    print(f"  charge : {Path('/proc/loadavg').read_text().split()[0]}"
          f"   récolte {len(running('python.*build_corpus_t70[.]py'))} proc."
          f"   arbitrage {len(running('python.*arbitrate_t70[.]py'))} proc.")

    # ── les tranches ───────────────────────────────────────────────────────
    root = ROOT / "docs/corpus/t70/tranches"
    tranches = sorted(list(root.glob("tranche-*")) + list(root.glob("*-[0-9][0-9]")))
    tranches = sorted(set(tranches))
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
    states = harvest_state()
    if states:
        target = harvest_target()
        print(f"\n  récoltes en cours : {len(states)}")
        for st in states:
            share = st["kept"] / target if target else 0.0
            rate = st["kept"] / st["seconds"] if st["seconds"] else 0.0
            left = (target - st["kept"]) / rate if (rate and target) else 0.0
            # Une récolte qui a atteint sa cible et se tait est TERMINÉE, pas
            # bloquée. Confondre les deux fait crier l'alarme à chaque fin de
            # tranche — et un garde-fou qui crie pour rien est celui qu'on
            # apprend à ignorer. L'alarme ne vaut que pour une récolte qui se
            # tait AVANT d'avoir fini.
            done = target and st["kept"] >= target
            stale = st["age"] > 600 and not done
            if done:
                mark = "   ✓ terminée"
                reste = ""
            else:
                mark = ("   ⚠ MUETTE DEPUIS "
                        + str(int(st["age"] / 60)) + " MIN" if stale else "")
                reste = f"   reste ~{left / 3600:.1f} h"
            print(f"    {st['name']:14s} {st['kept']:5d}"
                  f"{'/' + str(target) if target else ''} gardées "
                  f"({100 * share:5.1f} %)  {st['workers'] - st['idle']}/"
                  f"{st['workers']} processus actifs{reste}{mark}")
        vivantes = [st for st in states
                    if not (target and st["kept"] >= target)]
        idle = sum(st["idle"] for st in vivantes)
        busy = sum(st["workers"] - st["idle"] for st in vivantes)
        if busy + idle:
            print(f"    → {busy} processus au travail, {idle} en attente "
                  f"({100 * idle / (busy + idle):.0f} % de traîne)")

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

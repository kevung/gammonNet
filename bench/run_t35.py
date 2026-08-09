#!/usr/bin/env python3
"""T35 — le pilote de campagne : segmentable, journalisé, reprenable.

## Pourquoi la reprise est exacte, et pas approximative

Une paire dupliquée est une fonction pure de `(graine de base, clé de paire,
index)` — c'est la construction d'`arena.py`, que `cubeful.py` reprend. Le
pilote peut donc jouer les index dans n'importe quel ordre, s'arrêter au
milieu, reprendre le lendemain : l'union des lignes du journal est identique
bit à bit à ce qu'un calcul d'une traite aurait produit. Cette propriété est
testée (`tests/test_t35_driver.py`), pas affirmée.

## Le journal

Un fichier JSONL, append-only : une ligne d'en-tête qui fige le protocole
(moteurs, graine, mode, règles, échantillonnage des scores), puis une ligne
par paire jouée, portant son index. À la reprise, l'en-tête est confronté à
l'invocation — **un désaccord refuse**, parce qu'un journal qui mélange deux
protocoles n'est plus une mesure. Les index déjà présents sont sautés.

Chaque ligne est écrite et poussée sur disque dès que sa paire se termine :
éteindre la machine au milieu d'un lot ne coûte au pire que les paires en vol.
Une dernière ligne tronquée par une coupure est ignorée à la relecture — son
index manque donc au journal, et la paire est simplement rejouée.

## S'arrêter, reprendre

    # premier lot : 4 heures, puis arrêt propre
    python bench/run_t35.py --mode money --pairs 50000 --minutes 240 ...

    # le lendemain : la même commande reprend où le journal s'arrête
    python bench/run_t35.py --mode money --pairs 50000 --minutes 240 ...

Ctrl-C draine les paires en vol puis sort proprement. `--limit` borne un lot
en nombre de paires plutôt qu'en minutes. Sans l'un ni l'autre, le pilote
joue jusqu'au bout de `--pairs`.

## Le mode match

Les scores de départ sont échantillonnés (PLAN.md, amendement du 2026-08-06),
uniformément sur les couples `(away_a, away_b)` de 1 à `--match-length` ;
quand exactement un joueur est à 1-away, une pièce décide si la partie de
Crawford est encore à jouer ou déjà derrière. L'échantillonnage est dérivé de
`(graine, "scores", index)` — même pureté que les dés. Le score est collé au
siège, les moteurs échangent leurs places entre les deux manches — voir
`play_match_duplicate` pour pourquoi c'est la construction qui rend le
contrôle nul exact.

Le jeu de pions de gnubg au score passe par l'EMG sondée le 2026-08-09
(`docs/mesures/2026-08-09-t35-sonde-emg.md`) : `evaluate` sous un `cubeinfo`
de match, même convention composée qu'en money.

Ce pilote produit un journal, pas une conclusion : le dépouillement (ppg,
MWC, intervalles bootstrap) est `bench/report_t35.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.arena import derive_seed  # noqa: E402
from gammonnet.cubeful import (  # noqa: E402
    CUBE_CAP,
    GammonNetCubePlayer,
    GnubgCubePlayer,
    play_cubeful_duplicate,
    play_match_duplicate,
)


def parse_filter(text: str) -> tuple[int, ...]:
    return tuple(int(k) for k in text.split(",")) if text else ()


def eval_fingerprint(model: str) -> str:
    """L'empreinte numérique du build : les cinq flottants de la position
    initiale, hachés bit à bit.

    Le build fait partie du protocole — `NATIVE_FP=1` change la réassociation
    flottante, donc potentiellement des choix de coups. Deux lots d'une même
    campagne doivent évaluer EXACTEMENT pareil ; l'empreinte dans l'en-tête
    du journal refuse toute reprise sous un build numériquement différent.
    """
    import hashlib
    import struct

    from gammonnet.infer import Network
    from gammonnet.rules import Position

    network = Network.load(ROOT / model if not Path(model).is_absolute() else model)
    values = network.evaluate(Position.initial()).as_tuple()
    return hashlib.blake2b(struct.pack("<5f", *values), digest_size=8).hexdigest()


def sampled_score(seed: int, index: int, length: int) -> tuple[int, int, bool]:
    """Le score de départ de la paire `index` : pur, publié, rejouable."""
    rng = random.Random(derive_seed(seed, "scores", index))
    away_a = rng.randint(1, length)
    away_b = rng.randint(1, length)
    crawford_done = False
    if (away_a == 1) != (away_b == 1):
        crawford_done = rng.random() < 0.5
    return away_a, away_b, crawford_done


# ── Les ouvriers ─────────────────────────────────────────────────────
#
# Les moteurs sont installés une fois par processus (initializer), pas
# re-sérialisés à chaque paire : le réseau ne se recharge pas, et surtout la
# session gnubg — un sous-processus à la seconde de démarrage — survit d'une
# paire à la suivante.

_A = None
_B = None


def _install(a, b, evalcache_log2):
    global _A, _B
    _A, _B = a, b
    if evalcache_log2:
        # ×3,41 mesuré sur une paire identique (2026-08-09), résultats
        # vérifiés bit à bit : le cache rejoue les mêmes évaluations, il n'en
        # invente aucune. La question de videau 2-ply et le coup qui la suit
        # partagent l'essentiel de leurs sous-arbres.
        from gammonnet import evalcache

        evalcache.enable(evalcache_log2)


def _play(payload):
    mode, seed, index, length = payload
    if mode == "money":
        net, stats = play_cubeful_duplicate(_A, _B, seed, index)
        return {"i": index, "net": net, **stats}
    away_a, away_b, crawford_done = sampled_score(seed, index, length)
    net, stats = play_match_duplicate(_A, _B, away_a, away_b, seed, index,
                                      crawford_done=crawford_done)
    return {"i": index, "net": net, "away_a": away_a, "away_b": away_b,
            "post_crawford": crawford_done, **stats}


# ── Le journal ───────────────────────────────────────────────────────


def read_journal(path: Path) -> tuple[dict | None, dict[int, dict]]:
    """L'en-tête et les paires déjà jouées. Une ligne inanalysable est
    signalée et ignorée — son index manquant fera rejouer la paire."""
    if not path.exists():
        return None, {}
    header = None
    rows: dict[int, dict] = {}
    with path.open() as lines:
        for number, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"⚠ ligne {number} inanalysable (coupure ?) — ignorée, "
                      f"la paire sera rejouée", file=sys.stderr)
                continue
            if row.get("header"):
                header = row
            else:
                previous = rows.get(row["i"])
                if previous is not None and previous != row:
                    raise SystemExit(
                        f"index {row['i']} présent deux fois avec des contenus "
                        f"différents — le journal n'est pas fiable, refus")
                rows[row["i"]] = row
    return header, rows


def check_header(existing: dict, wanted: dict, path: Path) -> None:
    """Tout doit coïncider, sauf la cible de volume (une campagne s'étend)."""
    for key, value in wanted.items():
        if key == "pairs_target":
            continue
        if existing.get(key) != value:
            raise SystemExit(
                f"le journal {path} a été ouvert avec un autre protocole :\n"
                f"  {key} = {existing.get(key)!r}, demandé {value!r}\n"
                f"Un journal, un protocole. Changez de fichier de journal.")


# ── Le pilote ────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("money", "match"), required=True)
    parser.add_argument("--pairs", type=int, required=True,
                        help="cible totale de paires dupliquées (2 parties ou "
                             "2 matchs chacune)")
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--workers", type=int, default=11,
                        help="11 = le pic de débit agrégé mesuré sur le "
                             "bureau (x4,4 ; 14 ouvriers RETOMBENT à x3,0 — "
                             "l'inférence est bornée par la bande passante "
                             "mémoire, pas par les cœurs)")
    parser.add_argument("--evalcache-log2", type=int, default=21,
                        help="taille du cache d'évaluation par ouvrier "
                             "(2^n entrées ; 0 = désactivé)")
    parser.add_argument("--limit", type=int, default=0,
                        help="taille du lot en paires (0 = jusqu'au bout)")
    parser.add_argument("--minutes", type=float, default=0.0,
                        help="budget de temps du lot (0 = sans limite)")
    parser.add_argument("--ours-ply", type=int, default=2)
    parser.add_argument("--ours-filter", default="0,1,1")
    parser.add_argument("--ours-cube-ply", type=int, default=None,
                        help="défaut : la profondeur de jeu")
    parser.add_argument("--theirs", choices=("gnubg", "self"), default="gnubg",
                        help="self = notre joueur des deux côtés (essais, "
                             "contrôles) ; l'adversaire de la mesure est gnubg")
    parser.add_argument("--gnubg-ply", type=int, default=2)
    parser.add_argument("--gnubg-filter", default="0,1,1")
    parser.add_argument("--gnubg-cube-ply", type=int, default=None)
    parser.add_argument("--match-length", type=int, default=7)
    args = parser.parse_args()

    ours_cube = args.ours_cube_ply if args.ours_cube_ply is not None else args.ours_ply
    ours = GammonNetCubePlayer(ply=args.ours_ply,
                               filter=parse_filter(args.ours_filter),
                               cube_ply=ours_cube)
    if args.theirs == "self":
        theirs = GammonNetCubePlayer(ply=args.ours_ply,
                                     filter=parse_filter(args.ours_filter),
                                     cube_ply=ours_cube,
                                     name=ours.name + "-bis")
    else:
        gnubg_cube = (args.gnubg_cube_ply if args.gnubg_cube_ply is not None
                      else args.gnubg_ply)
        theirs = GnubgCubePlayer(ply=args.gnubg_ply,
                                 filter=parse_filter(args.gnubg_filter),
                                 cube_ply=gnubg_cube)

    wanted_header = {
        "header": True,
        "task": "T35",
        "mode": args.mode,
        "seed": args.seed,
        "jacoby": True,
        "cube_cap": CUBE_CAP,
        "ours": {"name": ours.name, "model": ours.model, "ply": ours.ply,
                 "filter": list(ours.filter), "cube_ply": ours.cube_ply},
        "eval_fingerprint": eval_fingerprint(ours.model),
        "theirs": ({"name": theirs.name, "ply": theirs.ply,
                    "filter": list(theirs.filter),
                    "cube_ply": getattr(theirs, "cube_ply", None),
                    "prune": getattr(theirs, "prune", None)}),
        "match_length": args.match_length if args.mode == "match" else None,
        "score_sampling": ("uniforme sur (1..L)² ; Crawford joué/derrière à "
                           "pile ou face quand un seul joueur est à 1-away ; "
                           "dérivé de (seed, 'scores', index)"
                           if args.mode == "match" else None),
        "pairs_target": args.pairs,
    }

    header, rows = read_journal(args.journal)
    if header is not None:
        check_header(header, wanted_header, args.journal)
    done = set(rows)
    todo = [i for i in range(args.pairs) if i not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f"Journal : {args.journal} — {len(done)} paire(s) déjà jouée(s), "
          f"cible {args.pairs}, ce lot : {len(todo)}")
    if not todo:
        print("Rien à jouer — la cible est atteinte. Dépouillement : "
              "bench/report_t35.py")
        return 0

    deadline = time.monotonic() + args.minutes * 60 if args.minutes else None
    played = 0
    started = time.perf_counter()

    args.journal.parent.mkdir(parents=True, exist_ok=True)
    with args.journal.open("a") as out:
        if header is None:
            out.write(json.dumps(wanted_header, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())

        queue = iter(todo)
        pending = {}

        def refill(pool):
            while len(pending) < 2 * args.workers:
                if deadline is not None and time.monotonic() > deadline:
                    return
                index = next(queue, None)
                if index is None:
                    return
                payload = (args.mode, args.seed, index, args.match_length)
                pending[pool.submit(_play, payload)] = index

        with ProcessPoolExecutor(args.workers, initializer=_install,
                                 initargs=(ours, theirs,
                                           args.evalcache_log2)) as pool:
            try:
                refill(pool)
                while pending:
                    finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        del pending[future]
                        row = future.result()
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        played += 1
                    out.flush()
                    os.fsync(out.fileno())
                    refill(pool)
                    if played % 20 < len(finished):
                        rate = played / (time.perf_counter() - started)
                        remaining = args.pairs - len(done) - played
                        eta = remaining / rate if rate > 0 else float("inf")
                        print(f"  {len(done) + played}/{args.pairs} paires — "
                              f"{rate:.2f} paire/s — reste ~{eta / 3600:.1f} h "
                              f"au total", flush=True)
            except KeyboardInterrupt:
                print("\nArrêt demandé — les paires en vol sont abandonnées, "
                      "le journal garde tout le reste.", file=sys.stderr)
                for future in pending:
                    future.cancel()

    total_done = len(done) + played
    print(f"Lot terminé : {played} paire(s) jouée(s) en "
          f"{(time.perf_counter() - started) / 60:.1f} min — journal à "
          f"{total_done}/{args.pairs}.")
    if total_done < args.pairs:
        print("Relancez la même commande pour reprendre ; la machine peut "
              "être éteinte entre deux lots.")
    else:
        print("Cible atteinte. Dépouillement : bench/report_t35.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

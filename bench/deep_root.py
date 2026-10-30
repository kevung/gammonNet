#!/usr/bin/env python3
"""Issue #31 — les filtres de coups à 3 et 4 plis, et la racine étagée.

## La question

Le filtre de coups n'est publié que jusqu'à 2 plis. Au-delà, deux choix
restent ouverts, et ce banc les mesure :

1. **Le filtre intérieur.** Combien de répliques un nœud intérieur approfondit
   à 3 et 4 plis : l'ancien « 5 coups » ou la seule meilleure, `(1, 0, 0)`.
2. **La racine.** Choisir les candidats payés à `k` plis directement depuis le
   classement 0-ply (`filter[k]`), ou passer d'abord par un classement 2-ply
   (`SearchConfig.root_stage_ply`, filtre-de-coups-spec §8).

## La mesure

Les décisions de coup d'un vrai match (`test.sgf`, lu par GNU Backgammon via
le Python embarqué de gnubg : ce dépôt ne lit pas un `.sgf`), au score réel,
cubeless, élaguées à `k = 12` comme le niveau `normal`. Pour chaque
configuration : les évaluations du grand réseau (cache coupé, donc un compte et
non un temps), le temps, et le coup choisi.

**La perte** d'une configuration est celle de son coup sous une **référence**
plus large : `REF(meilleur) − REF(coup choisi)`, où `REF(coup)` est la valeur
`k` plis de la position résultante sous les filtres intérieurs de la référence
— le même calcul que la passe profonde, appelé par `position_equity`. La
référence porte une racine large `(0, 8, 0,16)` ; à 3 plis son intérieur est
l'ancien (le plus large), à 4 plis c'est `(1, 0, 0)`, l'ancien y étant hors de
portée. C'est une mesure de **nous contre nous** : la référence n'est pas un
arbitre de force, elle dit seulement ce qu'un filtre plus large aurait choisi.

    python bench/deep_root.py extract                    # une fois : le corpus
    python bench/deep_root.py measure --ply 3 --workers 14 --every 7 \
        --only old direct staged_canonical staged_wide ref_inner1 ref_unpruned
    python bench/deep_root.py measure --ply 4 --workers 14 --every 20

Résultats et lecture : `docs/mesures/2026-10-11-filtres-3-4-plis.md`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from gammonnet.codec import position_from_id  # noqa: E402
from gammonnet.codec import position_id as codec_id  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rules import WHITE  # noqa: E402
from gammonnet.search import (  # noqa: E402
    SearchConfig,
    evaluations,
    position_equity,
    reset_evaluations,
    search_plays,
    terminal_equity,
)

MODEL = ROOT / "models" / "cubeless_prob5_768_768_256_256_256.bin"
PRUNE = ROOT / "models" / "prune_32.bin"
CORPUS = ROOT / "docs" / "mesures" / "deep-root-test-sgf.jsonl"
PRUNE_K = 12

# Triplets (accepte, extra, seuil).
NORMAL_ROOT = (1, 2, 0.04)      # la racine publiée du niveau `normal`
ONE = (1, 0, 0.0)               # une seule réplique
FIVE = (5, 0, 0.0)              # l'ancien « 5 coups »
WIDE = (0, 8, 0.16)             # la racine large
FINAL = (0, 2, 0.04)            # la racine finale après l'étage


def shape(ply: int, root: tuple, inner: dict[int, tuple],
          stage: tuple | None = None, prune: bool = True) -> dict:
    """Une forme : le triplet de racine à `ply`, ceux des nœuds intérieurs par
    profondeur, l'étage éventuel `(ply, triplet)`, et l'élagage à k = 12."""
    triplets = {d: ONE for d in range(1, ply)}
    triplets.update(inner)
    triplets[ply] = root
    return {"ply": ply, "triplets": triplets, "stage": stage, "prune": prune}


def configs(ply: int) -> dict[str, dict]:
    """Les formes comparées, et la référence, à `ply` plis."""
    if ply == 3:
        old_inner = {2: NORMAL_ROOT}          # l'ancien : normal + 5 à 3 plis
        return {
            "old": shape(3, FIVE, old_inner),
            "direct": shape(3, NORMAL_ROOT, {}),
            "staged_canonical": shape(3, FINAL, {}, (2, NORMAL_ROOT)),
            "staged_wide": shape(3, FINAL, {}, (2, WIDE)),
            "ref": shape(3, WIDE, old_inner),
            "ref_inner1": shape(3, WIDE, {}),
            # Le coût de l'élagage, à la forme retenue : la même sans élagage.
            "ref_unpruned": shape(3, FINAL, {}, (2, WIDE), prune=False),
        }
    if ply == 4:
        return {
            "direct": shape(4, NORMAL_ROOT, {}),
            "staged_canonical": shape(4, FINAL, {}, (2, NORMAL_ROOT)),
            "staged_wide": shape(4, FINAL, {}, (2, WIDE)),
            "ref": shape(4, WIDE, {}),
            "ref_unpruned": shape(4, FINAL, {}, (2, WIDE), prune=False),
        }
    raise SystemExit("--ply vaut 3 ou 4")


def to_config(s: dict, match: MatchState, prune: Network) -> SearchConfig:
    width = 5
    filt = [0] * width
    extra = [0] * width
    thr = [0.0] * width
    for d, (a, e, t) in s["triplets"].items():
        filt[d], extra[d], thr[d] = a, e, t
    stage_ply, stage = (s["stage"] or (0, (0, 0, 0.0)))
    return SearchConfig(ply=s["ply"], filter=tuple(filt),
                        filter_extra=tuple(extra), filter_threshold=tuple(thr),
                        use_match=True, match=match,
                        prune_net=prune if s["prune"] else None,
                        prune_k=PRUNE_K if s["prune"] else 0,
                        root_stage_ply=stage_ply,
                        root_stage_filter=stage)


def swapped(m: MatchState) -> MatchState:
    return MatchState(away_on_roll=m.away_opponent, away_opponent=m.away_on_roll,
                      cube=m.cube, crawford=m.crawford)


# ── Le corpus ─────────────────────────────────────────────────────────


# Lu par le Python embarqué de gnubg (`gnubg -t -p`) : `gnubg.match()` rend
# chaque coup avec la position avant lui, vue du joueur au trait. La marche
# en ligne de commande (`analyse_match.MatchWalker`) ne convient pas ici : un
# match chargé dont la dernière partie finit sur un abandon laisse gnubg sans
# partie en cours, et `first game` n'y revient pas.
_GNUBG_DUMP = r"""
import gnubg, json, os
gnubg.command("load match " + os.environ["DEEP_ROOT_MATCH"])
m = gnubg.match(analysis=0, boards=1, statistics=0, verbose=0)
length = m["match-info"]["match-length"]
states, crawford_done = [], False
for game in m["games"]:
    info = game["info"]
    score = {"X": info["score-X"], "O": info["score-O"]}
    crawford = (not crawford_done and length > 0
                and max(score.values()) == length - 1)
    crawford_done = crawford_done or crawford
    cube = 1
    for action in game["game"]:
        if action["action"] == "take":
            cube *= 2
        if action["action"] != "move" or not action.get("dice"):
            continue
        me = action["player"]
        them = "O" if me == "X" else "X"
        states.append({"id": action["board"], "dice": list(action["dice"]),
                       "away": [length - score[me], length - score[them]],
                       "cube": cube, "crawford": crawford})
print("DEEP_ROOT_JSON " + json.dumps(states))
"""


def extract(match_path: str, out: Path) -> int:
    import os
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as script:
        script.write(_GNUBG_DUMP)
    try:
        done = subprocess.run(
            ["gnubg", "-t", "-q", "-p", script.name], capture_output=True,
            text=True, timeout=300,
            env={**os.environ, "DEEP_ROOT_MATCH": str(Path(match_path).resolve())})
    finally:
        os.unlink(script.name)
    line = next((x for x in done.stdout.splitlines()
                 if x.startswith("DEEP_ROOT_JSON ")), None)
    if line is None:
        raise SystemExit(f"gnubg n'a rien rendu : {done.stdout[-300:]}{done.stderr[-300:]}")
    states, seen = [], set()
    for state in json.loads(line.split(" ", 1)[1]):
        key = (state["id"], tuple(state["dice"]), tuple(state["away"]))
        if key not in seen:
            seen.add(key)
            states.append(state)

    rows = []
    for state in states:
        position = position_from_id(state["id"], WHITE)
        d1, d2 = state["dice"]
        if len(position.legal_plays(d1, d2)) < 2:
            continue
        rows.append({
            "id": state["id"], "dice": [d1, d2], "away": state["away"],
            "cube": state["cube"], "crawford": state["crawford"],
        })
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{len(rows)} décisions non forcées → {out}")
    return 0


# ── La mesure ─────────────────────────────────────────────────────────

_NET = None
_PRUNE = None


def _init() -> None:
    global _NET, _PRUNE
    _NET = Network.load(MODEL)
    _PRUNE = Network.load(PRUNE)


def ref_value(play_result, s: dict, match: MatchState) -> float:
    """La valeur `ply` plis d'un coup sous la forme `s`, pour qui l'a joué."""
    if play_result.is_over():
        return -terminal_equity(play_result)
    config = to_config(s, swapped(match), _PRUNE)
    return -position_equity(_NET, play_result, config)


def measure_one(args: tuple) -> dict:
    row, ply, names = args
    shapes = configs(ply)
    position = position_from_id(row["id"], WHITE)
    match = MatchState(away_on_roll=row["away"][0], away_opponent=row["away"][1],
                       cube=row["cube"], crawford=row["crawford"])
    d1, d2 = row["dice"]
    out = {"id": row["id"], "dice": row["dice"], "away": row["away"],
           "runs": {}}
    for name in names:
        config = to_config(shapes[name], match, _PRUNE)
        reset_evaluations()
        started = time.perf_counter()
        ranked = search_plays(_NET, position, d1, d2, config)
        seconds = time.perf_counter() - started
        out["runs"][name] = {
            "evals": evaluations(), "seconds": seconds,
            "choice": codec_id(ranked[0].play.result),
            "equity": ranked[0].equity,
            "_play": ranked[0].play,
        }

    # Les pertes, sous chaque référence présente.
    for ref in (n for n in names if n.startswith("ref")):
        best = out["runs"][ref]["equity"]
        values = {}
        for name in names:
            run = out["runs"][name]
            key = run["choice"]
            if key not in values:
                values[key] = ref_value(run["_play"].result, shapes[ref], match)
            run[f"loss_{ref}"] = best - values[key]
        # Contrôle : la valeur de référence du coup de la référence est son
        # équité rendue par la recherche, au bit près.
        out[f"check_{ref}"] = values[out["runs"][ref]["choice"]] - best
    for run in out["runs"].values():
        del run["_play"]
    return out


def measure(ply: int, workers: int, limit: int | None, every: int,
            out_path: Path, names: list[str] | None) -> int:
    rows = [json.loads(line) for line in CORPUS.read_text().splitlines()]
    rows = rows[::every]
    if limit:
        rows = rows[:limit]
    names = names or list(configs(ply))
    jobs = [(row, ply, names) for row in rows]
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        for i, res in enumerate(pool.map(measure_one, jobs), 1):
            results.append(res)
            print(f"\r{i}/{len(jobs)}", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    out_path.write_text("".join(json.dumps(r) + "\n" for r in results))
    report(results, names)
    return 0


def bootstrap(values: list[float], resamples: int = 10_000,
              seed: int = 20261011) -> tuple[float, float]:
    """L'intervalle à 95 % de la moyenne, par rééchantillonnage des décisions."""
    import random
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n
                   for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def report(results: list[dict], names: list[str]) -> None:
    refs = [n for n in names if n.startswith("ref")]
    for ref in refs:
        checks = [abs(r[f"check_{ref}"]) for r in results]
        print(f"contrôle {ref} : max |REF(choix de la réf.) − équité rendue| = "
              f"{max(checks):.3e}")
    print(f"{len(results)} décisions")
    header = f"{'forme':<18}{'évals moy.':>12}{'s moy.':>9}"
    for ref in refs:
        header += f"{'perte ' + ref:>22}{'IC 95 %':>22}{'max':>9}{'≠':>5}"
    print(header)
    for name in names:
        runs = [r["runs"][name] for r in results]
        line = (f"{name:<18}{statistics.mean(x['evals'] for x in runs):>12.0f}"
                f"{statistics.mean(x['seconds'] for x in runs):>9.2f}")
        for ref in refs:
            losses = [x[f"loss_{ref}"] for x in runs]
            differ = sum(1 for r in results
                         if r["runs"][name]["choice"] != r["runs"][ref]["choice"])
            low, high = bootstrap(losses)
            line += (f"{statistics.mean(losses):>22.6f}"
                     f"{f'[{low:.6f} ; {high:.6f}]':>22}{max(losses):>9.5f}"
                     f"{differ:>5}")
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--match", default=str(ROOT / "test.sgf"))
    m = sub.add_parser("measure")
    m.add_argument("--ply", type=int, required=True)
    m.add_argument("--workers", type=int, default=8)
    m.add_argument("--limit", type=int)
    m.add_argument("--every", type=int, default=1,
                   help="une décision sur N, réparties sur tout le match")
    m.add_argument("--only", nargs="*")
    m.add_argument("--out", type=Path)
    r = sub.add_parser("report")
    r.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.cmd == "extract":
        return extract(args.match, CORPUS)
    if args.cmd == "report":
        results = [json.loads(x) for x in args.path.read_text().splitlines()]
        report(results, list(results[0]["runs"]))
        return 0
    out = args.out or ROOT / "docs" / "mesures" / f"deep-root-{args.ply}ply.jsonl"
    return measure(args.ply, args.workers, args.limit, args.every, out, args.only)


if __name__ == "__main__":
    raise SystemExit(main())

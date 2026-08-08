#!/usr/bin/env python3
"""T39 — la campagne d'arbitrage : qui a raison sur les désaccords de videau money.

## Ce que ce banc arbitre, et avec quoi

Les désaccords de décision de videau **money** (états centré et possédé) entre
notre modèle (0-ply, `x` mesurés, Jacoby actif — le protocole de §6.3) et
GNU Backgammon (`cfevaluate`, mêmes conditions), sur le corpus de §6.3
rejoué. Trois arbitres, du plus fort au plus faible :

1. **La table bilatérale**, pour les désaccords dans son domaine : la
   décision exacte s'y lit, sans variance et sans réserve (mécanique §4 sur
   les trois équités stockées — convention « option du tour courant exclue »,
   la même que la branche « ne double pas »).
2. **Notre rollout cubeful** (`gn_rollout`, T39) : les deux branches de la
   décision — « ne double pas » (état courant, `cube_defer_first`) et
   « double, pris » (2 × l'état adverse) — jouées jusqu'au bout, dés communs
   par décision, décisions de videau internes exactes en domaine et modèle
   ailleurs.
3. **Le rollout de gnubg lui-même** (CLI `rollout`, cubeful, 0-ply, graine
   fixée, sous pseudo-terminal — la table finale ne s'imprime pas dans un
   tube, sonde du 2026-08-08) : les mêmes deux branches, `set cube` à l'état
   voulu. Le CF rendu est **par unité de videau courant** (établi par sonde :
   CF −0,134 sous videau 2 adverse là où le cubeless vaut +0,054 — une valeur
   absolue aurait le double), donc la branche prise vaut 2 × CF.

**Asymétrie assumée entre les colonnes, nommée** : le rollout de gnubg joue
au bout avec sa réduction de variance par la chance (144 parties leur
donnent déjà une se de ~0,035) ; le nôtre n'a pas de réduction de variance
et un videau vivant non tronqué produit un écart-type PAR ESSAI de ~4 (les
videaux à 4-8 font des queues à ±8) — inutilisable pour arbitrer des marges
de quelques centièmes. Notre colonne roule donc TRONQUÉE à 11 plis, valuée
cubeful à l'horizon : la variance s'effondre, au prix d'un biais d'horizon
qui vient de notre propre modèle — partiellement annulé entre les deux
branches par les dés communs, et de toute façon couvert par la réserve
structurelle ci-dessus. Chaque colonne est l'estimateur honnête de son
moteur ; aucune n'est présentée seule.

**La réserve de T39, qui voyage avec chaque ligne** : notre rollout nous
favorise (il joue et évalue avec notre réseau), celui de gnubg les favorise.
C'est précisément pourquoi les DEUX colonnes existent et qu'aucune n'est
présentée seule. Leur accord est ce qui fait un verdict ; leur désaccord est
une ligne « non tranchée », jamais une occasion de choisir sa colonne.

## La résolution

Un verdict de rollout est « résolu » si la décision §4 est STABLE quand on
perturbe E_nd et E_dt de ±1,96 erreur-type chacun (les quatre coins). Sinon
la ligne est « non résolue » — rapportée, jamais comptée pour un camp.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from compare_cube import build_corpus, classify_gnubg_verdict, gnubg_state  # noqa: E402

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet import evalcache  # noqa: E402
from gammonnet.bearoff import NativeBearoff, disable_shared, use_shared  # noqa: E402
from gammonnet.cube import CubeAction, CubeOwner, decide  # noqa: E402
from gammonnet.gnubg_engine import GnubgSession  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
MODEL_BIN = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
EFFICIENCY_FILE = ROOT / "docs" / "mesures" / "t34-efficacite.json"
GNUBG = "/usr/local/bin/gnubg"

ROLLOUT_SEED = 20260811

_FINAL = re.compile(
    r"Rollout done\. Printing final results\.\s*\n\s*\nCurrent Position:\s*\n"
    r"\s*([-+0-9. ]+)CL\s*([-+0-9.]+)\s*CF\s*([-+0-9.]+)\s*\n"
    r"\s*\[([-0-9. ]+)CL\s*([0-9.]+)\s*CF\s*([0-9.]+)\]")


def verdict(e_nd: float, e_dt: float, e_dp: float = 1.0) -> CubeAction:
    """La table §4 — les mêmes quatre lignes que `gn_cube_verdict`."""
    e_double = min(e_dt, e_dp)
    if e_nd > e_dp and e_nd >= e_double:
        return CubeAction.TOO_GOOD
    if e_dt >= e_dp:
        return CubeAction.DOUBLE_PASS
    if e_double > e_nd:
        return CubeAction.DOUBLE_TAKE
    return CubeAction.NO_DOUBLE


def resolved_verdict(e_nd: float, se_nd: float, e_dt: float, se_dt: float
                     ) -> tuple[str, bool]:
    """Le verdict §4, et sa stabilité aux quatre coins ±1,96 erreur-type."""
    centre = verdict(e_nd, e_dt)
    corners = {
        verdict(e_nd + s1 * 1.96 * se_nd, e_dt + s2 * 1.96 * se_dt)
        for s1 in (-1.0, 1.0) for s2 in (-1.0, 1.0)
    }
    return centre.name, corners == {centre}


# ── Colonne 3 : le rollout de gnubg, par script sous pseudo-terminal ──


def gnubg_rollout_branches(position_id: str, owner: CubeOwner, trials: int,
                           seed: int) -> dict:
    """Les CF des deux branches, par un seul processus gnubg.

    Branche nd : videau 1, centré ou possédé par le joueur au trait — nommé
    `arbiter` plutôt que le nom de login que gnubg donne au joueur 1, et
    `set turn` purge aussi les dés que `new game` a lancés. Branche dt : videau 2 possédé par l'adversaire (`gnubg`). Même
    graine : leurs dés quasi aléatoires s'apparient entre les branches.
    """
    nd_cube = ("set cube centre" if owner == CubeOwner.CENTRED
               else "set cube owner arbiter")
    script = "\n".join([
        "set player 0 human",
        "set player 1 human",
        "set player 1 name arbiter",
        "new game",
        f"set rollout trials {trials}",
        "set rollout truncation enable off",
        "set rollout cubeful on",
        "set rollout chequerplay plies 0",
        "set rollout cubedecision plies 0",
        f"set rollout seed {seed}",
        f"set board {position_id}",
        "set turn arbiter",
        "set cube value 1",
        nd_cube,
        "rollout",
        f"set board {position_id}",
        "set turn arbiter",
        "set cube value 2",
        "set cube owner gnubg",
        "rollout",
        "quit",
        "y",
    ]) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False) as handle:
        handle.write(script)
        commands = handle.name
    try:
        output = subprocess.run(
            ["script", "-qec", f"{GNUBG} --tty --quiet --no-rc < {commands}",
             "/dev/null"],
            capture_output=True, text=True, timeout=1200).stdout
    finally:
        Path(commands).unlink(missing_ok=True)

    finals = _FINAL.findall(output)
    if len(finals) != 2:
        raise RuntimeError(
            f"{len(finals)} tables finales au lieu de 2 pour {position_id} — "
            f"la sortie de gnubg n'a pas la forme sondée")
    (nd, dt) = finals
    return {
        "e_nd": float(nd[2]),   # groupes : probs, CL, CF, probs_se, CL_se, CF_se
        "se_nd": float(nd[5]),
        "e_dt": 2.0 * float(dt[2]),        # CF par unité → branche à videau 2
        "se_dt": 2.0 * float(dt[5]),
    }


# ── Phase 1 : la collecte des désaccords ─────────────────────────────


def collect(payload):
    positions, x_of = payload
    use_shared(DATABASE)
    network = Network.load(MODEL_BIN)
    session = GnubgSession()

    rows = []
    for position, origin in positions:
        board = gb.to_gnubg(position)
        evaluation = network.evaluate(position)
        for owner in (CubeOwner.CENTRED, CubeOwner.OWNED):
            ours = decide(evaluation, owner, x_of[owner], jacoby=True)
            raw = session.cubeful([board], plies=0,
                                  state=gnubg_state(owner, None, True))[0]
            theirs = classify_gnubg_verdict(raw[5])
            if ours.action != theirs:
                rows.append({
                    "id": codec.position_id(position),
                    "origin": origin,
                    "owner": owner.name,
                    "ours": ours.action.name,
                    "ours_margin": ours.equity_no_double - ours.equity_double,
                    "theirs": theirs.name,
                    "theirs_margin": raw[1] - min(raw[2], raw[3]),
                })
    session.close()
    disable_shared()
    return rows


# ── Phases 2 et 3 : l'arbitrage d'une décision ───────────────────────


def arbitrate(payload):
    rows, x3, trials = payload
    use_shared(DATABASE)
    evalcache.enable()
    native = NativeBearoff(DATABASE)
    network = Network.load(MODEL_BIN)

    out = []
    for index, row in rows:
        position = codec.position_from_id(row["id"], 0)
        owner = CubeOwner[row["owner"]]

        exact = native.equities(position)
        if exact is not None:
            e_nd = exact.owned if owner == CubeOwner.OWNED else exact.centered
            row["arbiter"] = "exact"
            row["exact"] = {
                "verdict": verdict(e_nd, 2.0 * exact.opponent_owns).name,
                "e_nd": e_nd, "e_dt": 2.0 * exact.opponent_owns,
            }
            out.append(row)
            continue

        row["arbiter"] = "rollouts"
        seed = ROLLOUT_SEED + index

        # Notre colonne. Branche nd : l'état courant, l'option du tour
        # courant déjà rendue (defer) ; branche dt : 2 × l'état adverse.
        ours = {}
        for branch, branch_owner, scale in (("nd", owner, 1.0),
                                            ("dt", CubeOwner.OPPONENT, 2.0)):
            policy = SearchConfig(ply=0, use_cube=True,
                                  cube_owner=int(branch_owner), cube_x=0.6)
            config = RolloutConfig(
                trials=trials, truncate=11, seed=seed, policy=policy,
                use_cube=True, cube_owner=int(branch_owner), cube_x=x3,
                jacoby=True, cube_defer_first=True)
            result = rollout(network, position, config)
            ours[f"e_{branch}"] = scale * result.equity
            ours[f"se_{branch}"] = scale * result.standard_error
            ours[f"stalled_{branch}"] = result.stalled
        ours["verdict"], ours["resolved"] = resolved_verdict(
            ours["e_nd"], ours["se_nd"], ours["e_dt"], ours["se_dt"])
        row["our_column"] = ours

        # Leur colonne : le rollout de gnubg, mêmes deux branches.
        theirs = gnubg_rollout_branches(row["id"], owner, trials, seed)
        theirs["verdict"], theirs["resolved"] = resolved_verdict(
            theirs["e_nd"], theirs["se_nd"], theirs["e_dt"], theirs["se_dt"])
        row["gnubg_column"] = theirs

        out.append(row)

    native.close()
    disable_shared()
    return out


def support(row: dict, column: str) -> str:
    """Qui la colonne soutient : nous, eux, aucun (autre verdict), non résolu."""
    block = row[column]
    if not block.get("resolved", True):
        return "unresolved"
    if block["verdict"] == row["ours"]:
        return "ours"
    if block["verdict"] == row["theirs"]:
        return "theirs"
    return "neither"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact", type=int, default=2000)
    parser.add_argument("--bearoff", type=int, default=1000)
    parser.add_argument("--trials", type=int, default=1296)
    parser.add_argument("--workers", type=int, default=15)
    parser.add_argument("--limit", type=int, default=0,
                        help="arbitrer au plus N désaccords (0 = tous)")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    payload = json.loads(EFFICIENCY_FILE.read_text())["results"]
    x_of = {CubeOwner.OWNED: payload["owned"]["x"],
            CubeOwner.CENTRED: payload["centered"]["x"]}
    x3 = (payload["centered"]["x"], payload["owned"]["x"],
          payload["opponent"]["x"])

    corpus = build_corpus(args.contact, args.bearoff)
    chunk = (len(corpus) + args.workers - 1) // args.workers
    with Pool(args.workers) as pool:
        batches = pool.map(collect, [(corpus[i:i + chunk], x_of)
                                     for i in range(0, len(corpus), chunk)])
    disagreements = [r for batch in batches for r in batch]
    print(f"{len(disagreements)} désaccords money collectés", flush=True)

    if args.limit:
        disagreements = disagreements[:args.limit]

    indexed = list(enumerate(disagreements))
    # Tourniquet, pas tranches : les désaccords du domaine exact (gratuits)
    # et de contact (coûteux) arrivent groupés, et des tranches contiguës
    # laisseraient des workers oisifs.
    with Pool(args.workers) as pool:
        batches = pool.map(
            arbitrate,
            [(indexed[i::args.workers], x3, args.trials)
             for i in range(args.workers)])
    rows = [r for batch in batches for r in batch]

    report = {
        "task": "T39-arbitrage-money", "trials": args.trials,
        "rollout_seed": ROLLOUT_SEED, "jacoby": True,
        "corpus": {"contact": args.contact, "bearoff": args.bearoff},
        "n_disagreements": len(rows),
        "exact": {}, "columns": {}, "rows": rows,
    }

    exact_rows = [r for r in rows if r["arbiter"] == "exact"]
    report["exact"] = {
        "n": len(exact_rows),
        "ours": sum(1 for r in exact_rows
                    if r["exact"]["verdict"] == r["ours"]),
        "theirs": sum(1 for r in exact_rows
                      if r["exact"]["verdict"] == r["theirs"]),
        "neither": sum(1 for r in exact_rows
                       if r["exact"]["verdict"] not in (r["ours"], r["theirs"])),
    }

    rolled = [r for r in rows if r["arbiter"] == "rollouts"]
    for column in ("our_column", "gnubg_column"):
        counts = {"ours": 0, "theirs": 0, "neither": 0, "unresolved": 0}
        for r in rolled:
            counts[support(r, column)] += 1
        report["columns"][column] = {"n": len(rolled)} | counts
    both = [r for r in rolled
            if support(r, "our_column") != "unresolved"
            and support(r, "gnubg_column") != "unresolved"]
    report["columns"]["agreement_between_columns"] = {
        "n_both_resolved": len(both),
        "same_support": sum(1 for r in both
                            if support(r, "our_column")
                            == support(r, "gnubg_column")),
    }

    summary = {k: v for k, v in report.items() if k != "rows"}
    print(json.dumps(summary, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"écrit dans {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

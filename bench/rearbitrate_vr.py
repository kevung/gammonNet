"""T39 — la colonne corrigée reprend les lignes que l'ancienne ne résolvait pas.

L'arbitrage money (t39-arbitrage-money.json) a laissé 210 décisions non
résolues par NOTRE colonne : des fenêtres DOUBLE_TAKE / NO_DOUBLE où l'écart
médian |e_ND − e_DT| (0,042) était trop proche du se atteignable sans
réduction de variance (0,025 au médian, 3 888 essais). C'était une limite de
l'instrument, nommée dans le rapport. La réduction de variance existe
maintenant ; ce banc mesure ce qu'elle lève.

Même protocole que la colonne d'origine — mêmes branches (nd différée, dt à
2× l'état adverse), mêmes graines par décision — mais corrigé par la chance
et arrêté sur l'intervalle (cible de se par branche, plafond d'essais). La
doctrine ne change pas : la nouvelle colonne ne « choisit » rien contre celle
de gnubg ; on compte ce qu'elle résout, et avec qui elle tombe d'accord.

Usage : python bench/rearbitrate_vr.py [--target-se 0.008] [--cap 1296]
        [--workers 15] [--source docs/mesures/t39-arbitrage-money.json]
Sortie : docs/mesures/t39-rearbitrage-vr.json
"""

from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "bench"))

from arbitrate_cube import (  # noqa: E402
    DATABASE,
    MODEL_BIN,
    ROLLOUT_SEED,
    resolved_verdict,
)
from gammonnet import codec, evalcache  # noqa: E402
from gammonnet.bearoff import disable_shared, use_shared  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

X3 = (0.688, 0.566, 0.687)  # t34-efficacite.json


def rearbitrate(payload):
    rows, target_se, cap = payload
    use_shared(DATABASE)
    evalcache.enable()
    network = Network.load(MODEL_BIN)

    out = []
    for index, row in rows:
        position = codec.position_from_id(row["id"], 0)
        owner = CubeOwner[row["owner"]]
        seed = ROLLOUT_SEED + index

        column = {}
        for branch, branch_owner, scale in (("nd", owner, 1.0),
                                            ("dt", CubeOwner.OPPONENT, 2.0)):
            policy = SearchConfig(ply=0, use_cube=True,
                                  cube_owner=int(branch_owner), cube_x=0.6)
            config = RolloutConfig(
                trials=cap, truncate=11, seed=seed, policy=policy,
                use_cube=True, cube_owner=int(branch_owner), cube_x=X3,
                jacoby=True, cube_defer_first=True,
                variance_reduction=True,
                # La cible vaut pour l'équité RENDUE : la branche dt est
                # rendue à l'échelle 2×, sa cible interne est donc moitié.
                target_se=target_se / scale, min_trials=216)
            result = rollout(network, position, config)
            column[f"e_{branch}"] = scale * result.equity
            column[f"se_{branch}"] = scale * result.standard_error
            column[f"trials_{branch}"] = result.trials
            column[f"stalled_{branch}"] = result.stalled
        column["verdict"], column["resolved"] = resolved_verdict(
            column["e_nd"], column["se_nd"], column["e_dt"], column["se_dt"])
        out.append({**row, "vr_column": column})
    disable_shared()
    return out


def support(row: dict, column: str) -> str:
    block = row[column]
    if not block.get("resolved", True):
        return "unresolved"
    if block["verdict"] == row["ours"]:
        return "ours"
    if block["verdict"] == row["theirs"]:
        return "theirs"
    return "neither"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path,
                        default=ROOT / "docs" / "mesures" / "t39-arbitrage-money.json")
    parser.add_argument("--target-se", type=float, default=0.008)
    parser.add_argument("--cap", type=int, default=1296)
    parser.add_argument("--workers", type=int, default=15)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs" / "mesures" / "t39-rearbitrage-vr.json")
    args = parser.parse_args()

    source = json.loads(args.source.read_text())
    targets = [(i, row) for i, row in enumerate(source["rows"])
               if row["arbiter"] == "rollouts"
               and not row["our_column"]["resolved"]]
    print(f"{len(targets)} lignes non résolues par l'ancienne colonne",
          flush=True)

    chunks = [targets[i::args.workers] for i in range(args.workers)]
    with Pool(args.workers) as pool:
        parts = pool.map(rearbitrate,
                         [(c, args.target_se, args.cap) for c in chunks if c])
    rows = [row for part in parts for row in part]

    resolved = [r for r in rows if r["vr_column"]["resolved"]]
    tally = {"ours": 0, "theirs": 0, "neither": 0}
    agree_with_gnubg = both = 0
    for row in resolved:
        tally[support(row, "vr_column")] += 1
        if row["gnubg_column"].get("resolved"):
            both += 1
            if row["vr_column"]["verdict"] == row["gnubg_column"]["verdict"]:
                agree_with_gnubg += 1

    report = {
        "task": "T39-rearbitrage-vr",
        "source": args.source.name,
        "target_se": args.target_se,
        "cap": args.cap,
        "rollout_seed": ROLLOUT_SEED,
        "n_unresolved_before": len(targets),
        "n_resolved_now": len(resolved),
        "support": tally,
        "vs_gnubg_column": {"both_resolved": both,
                            "same_verdict": agree_with_gnubg},
        "rows": rows,
    }
    args.out.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                     indent=1), flush=True)
    print(f"écrit dans {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Le corpus de référence de la politique sans état — `docs/specs/politique-spec.md` §8.

Écrit `data/policy_reference.bin` (format de la spec) et `data/policy_reference.json`
(empreintes des poids, conditions de génération, décompte). Ce que la référence C
répond pour chaque décision, figé : un portage se vérifie contre lui au lieu de
contre lui-même.

D'où viennent les décisions :

* des **parties jouées** par la politique elle-même au niveau `instant`, money
  (Jacoby actif et inactif) et match (scores tirés, Crawford et après-Crawford
  compris) — chaque question que la boucle cubeful pose est enregistrée ;
* des **offres d'abandon** posées sur une part de ces positions, valeurs 1, 2, 3 ;
* des **cas de bord** écrits à la main : défaite certaine à chaque valeur, valeur
  incertaine, videau indisponible, coup forcé ou impossible, et des refus.

Chaque décision est répondue au niveau `instant` ; un sous-ensemble tiré aux
niveaux `normal` et `thorough`. Tout est déterministe : la même commande sur le
même build réécrit les mêmes octets, et `tests/test_policy.py` l'exige.

Conditions : build natif par défaut (pas `NATIVE_FP`), AUCUNE table bilatérale
installée — la politique suit alors le modèle partout.

    python tools/policy_corpus.py
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet import bearoff  # noqa: E402
from gammonnet.cube import CubeOwner  # noqa: E402
from gammonnet.cubeful import play_cubeful_game  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.policy import (LEVELS, REQUIRED_CATEGORIES, Decision, Pending,  # noqa: E402
                              PolicyPlayer, answer, categories, unpack_decision,
                              write_corpus)
from gammonnet.rules import WHITE, Position  # noqa: E402

OUT = ROOT / "data" / "policy_reference.bin"
META = ROOT / "data" / "policy_reference.json"
SEED = 20261005

#: Combien de décisions de chaque niveau. `instant` les prend toutes.
NORMAL = 90
THOROUGH = 30


class Recorder(PolicyPlayer):
    """La politique au niveau `instant`, qui note chaque question posée."""

    def __init__(self, log, **kw):
        super().__init__(level="instant", **kw)
        self.log = log

    def decide(self, decision):
        self.log.append(decision)
        return super().decide(decision)


def board(white, black, turn=WHITE):
    points = [0] * 24
    for i, n in white.items():
        points[i] += n
    for i, n in black.items():
        points[i] -= n
    return Position(points=tuple(points), bar=(0, 0),
                    off=(15 - sum(white.values()), 15 - sum(black.values())), turn=turn)


def played_decisions() -> list[Decision]:
    log: list[Decision] = []
    rng = random.Random(SEED)
    for game in range(6):
        jacoby = game % 2 == 0
        white, black = Recorder(log, jacoby=jacoby), Recorder(log, jacoby=jacoby)
        dice = random.Random(rng.getrandbits(32))
        play_cubeful_game(white, black, dice, random.Random(1), random.Random(2),
                          jacoby=jacoby)
    for game in range(10):
        away_w, away_b = rng.randint(1, 7), rng.randint(1, 7)
        crawford = (away_w == 1) != (away_b == 1) and game % 2 == 0
        white, black = Recorder(log), Recorder(log)
        dice = random.Random(rng.getrandbits(32))
        play_cubeful_game(white, black, dice, random.Random(1), random.Random(2),
                          match=(away_w, away_b, crawford))
    return log


def resign_offers(decisions: list[Decision]) -> list[Decision]:
    out = []
    pre_roll = [d for d in decisions if d.pending == Pending.CUBE]
    for i, d in enumerate(pre_roll[::7]):
        out.append(Decision(d.position, Pending.RESIGN, cube=d.cube,
                            cube_owner=d.cube_owner, jacoby=d.jacoby, match=d.match,
                            resign_value=1 + i % 3))
    return out


def edge_cases() -> list[Decision]:
    lost = {
        "gammon": board({12: 15}, {23: 2}),
        "backgammon": board({12: 9, 22: 6}, {23: 1}),
        "single": board({12: 14}, {23: 2}),
        "two-rolls": board({12: 15}, {23: 3}),
        "uncertain-value": board({12: 14, 22: 1}, {23: 2}),
        "not-certain": board({12: 15}, {23: 5}),
    }
    cases = []
    for pos in lost.values():
        cases += [
            Decision(pos, Pending.CUBE),
            Decision(pos, Pending.CUBE, jacoby=True),
            Decision(pos, Pending.CUBE, jacoby=True, cube=2, cube_owner=CubeOwner.OWNED),
            Decision(pos, Pending.CUBE, match=MatchState(3, 2, 1, False)),
            Decision(pos, Pending.CUBE, cube=2, cube_owner=CubeOwner.OPPONENT,
                     match=MatchState(4, 4, 2, False)),
        ]
    start = Position.initial()
    closed = Position(points=tuple([0] * 18 + [-2] * 6), bar=(1, 0), off=(14, 3),
                      turn=WHITE)
    cases += [
        Decision(closed, Pending.MOVE, 6, 6),                         # aucun coup
        Decision(board({0: 1}, {23: 1}), Pending.MOVE, 1, 2),          # un seul coup
        Decision(start, Pending.CUBE, cube=2, cube_owner=CubeOwner.OPPONENT),
        Decision(start, Pending.CUBE, match=MatchState(1, 4, 1, True)),
        Decision(start, Pending.CUBE, match=MatchState(4, 1, 1, True)),
        Decision(start, Pending.CUBE, match=MatchState(1, 4, 1, False)),
        Decision(start, Pending.CUBE, match=MatchState(4, 1, 1, False)),   # double du mené
        Decision(start, Pending.CUBE, cube=2, cube_owner=CubeOwner.OWNED,
                 match=MatchState(2, 5, 2, False)),
        Decision(start, Pending.CUBE, match=MatchState(2, 2, 1, False)),
        Decision(start, Pending.TAKE, match=MatchState(2, 2, 1, False)),
        Decision(start, Pending.TAKE, cube=4, cube_owner=CubeOwner.OWNED),
        Decision(start, Pending.RESIGN, resign_value=3),
        Decision(start, Pending.RESIGN, resign_value=1, jacoby=True),
        Decision(start, Pending.RESIGN, resign_value=2, match=MatchState(1, 1, 1, False)),
        # Refus.
        Decision(start, Pending.MOVE, 0, 3),
        Decision(start, Pending.CUBE, cube=2, cube_owner=CubeOwner.CENTRED),
        Decision(start, Pending.CUBE, match=MatchState(3, 3, 1, True)),
        Decision(start, Pending.CUBE, match=MatchState(26, 3, 1, False)),
        Decision(start, Pending.TAKE, cube=2, cube_owner=CubeOwner.OPPONENT),
        Decision(start, Pending.TAKE, match=MatchState(1, 3, 1, True)),
        Decision(start, Pending.RESIGN, resign_value=4),
    ]
    return cases


def optional_doubles() -> list[Decision]:
    """Le double optionnel (spec §5.2) : un bearoff gagné à coup sûr, où
    doubler vaut exactement ne pas doubler. Il n'existe qu'à partir d'un ply
    — à 0-ply le réseau ne rend jamais P(gain) = 1 exactement —, d'où sa place
    au niveau `normal`. Le premier est la position que la fiche du 2026-10-05
    (§2) a trouvée contre le joueur de T35."""
    won = Position(points=(1,) + (0,) * 17 + (-6, -2, -2, -1, 0, -2), bar=(0, 0),
                   off=(14, 2), turn=WHITE)
    return [
        Decision(won, Pending.CUBE, cube=2, cube_owner=CubeOwner.OWNED, jacoby=True,
                 match=MatchState(3, 4, 2, False)),
        Decision(won, Pending.CUBE, cube=2, cube_owner=CubeOwner.OWNED),
    ]


#: Les états de videau sous lesquels on cherche les verdicts manquants.
SCAN_STATES = (
    dict(),
    dict(jacoby=True),
    dict(cube=2, cube_owner=CubeOwner.OWNED),
    dict(match=MatchState(3, 5, 1, False)),
    dict(match=MatchState(2, 4, 1, False)),
    dict(match=MatchState(5, 2, 1, False)),
    dict(cube=2, cube_owner=CubeOwner.OWNED, match=MatchState(4, 4, 2, False)),
)


def targeted(network, prune, have: set[str]) -> list[tuple[str, Decision]]:
    """Des décisions avant le jet tirées de parties au hasard (graine fixe), au
    niveau `instant`, retenues seulement si elles illustrent une catégorie que
    le corpus n'a pas encore — deux exemples au plus par catégorie."""
    rng = random.Random(SEED + 2)
    wanted = {c: 2 for c in REQUIRED_CATEGORIES if c not in have}
    picked = []
    for _ in range(400):
        if not wanted:
            break
        pos = Position.initial()
        while not pos.is_over() and wanted:
            for state in SCAN_STATES:
                d = Decision(pos, Pending.CUBE, **state)
                record = answer(network, prune, "instant", d)
                hit = [c for c in categories(record) if c in wanted]
                if hit and any(c.split("/")[0] in ("trop-bon", "double-passe",
                                                   "double-prise", "pas-de-double")
                               for c in hit):
                    picked.append(("instant", d))
                    for c in categories(record):
                        if c in wanted:
                            wanted[c] -= 1
                            if wanted[c] == 0:
                                del wanted[c]
            plays = pos.legal_plays(rng.randint(1, 6), rng.randint(1, 6))
            pos = rng.choice(plays).result if plays else pos.swapped_turn()
    return picked


def sha256(path: Path) -> str:
    return hashlib.sha256(path.resolve().read_bytes()).hexdigest()


def main() -> int:
    if bearoff._shared is not None:
        raise SystemExit("une table bilatérale est installée : le corpus se génère sans")
    played = played_decisions()
    decisions = played + resign_offers(played) + edge_cases()

    player = PolicyPlayer(level="instant")
    network = player._load()
    prune = player._prune

    rng = random.Random(SEED + 1)
    sample = played + resign_offers(played)
    # Les niveaux qui cherchent coûtent : un sous-ensemble tiré, mais qui
    # couvre chaque cas en attente.
    by_kind: dict[Pending, list[Decision]] = {}
    for d in sample:
        by_kind.setdefault(d.pending, []).append(d)

    def draw(n: int) -> list[Decision]:
        picked = []
        kinds = sorted(by_kind)
        for i in range(n):
            pool = by_kind[kinds[i % len(kinds)]]
            picked.append(pool[rng.randrange(len(pool))])
        return picked

    jobs = ([("instant", d) for d in decisions]
            + [("normal", d) for d in draw(NORMAL)]
            + [("thorough", d) for d in draw(THOROUGH)])

    jobs += [("normal", d) for d in optional_doubles()]
    have = set()
    for level, d in jobs:
        if level == "instant" or d in optional_doubles():
            have |= categories(answer(network, prune, level, d))
    jobs += targeted(network, prune, have)

    records = []
    for i, (level, d) in enumerate(jobs):
        records.append(answer(network, prune, level, d))
        if i % 100 == 0:
            print(f"  {i}/{len(jobs)}", flush=True)
    write_corpus(OUT, records)

    counts = Counter()
    for r in records:
        level, d = unpack_decision(r)
        refused = r[80:84] == b"\xff\xff\xff\xff"
        counts[f"{level}/{d.pending.name}{'/refus' if refused else ''}"] += 1
    META.write_text(json.dumps({
        "_comment": ("Corpus de référence de la politique sans état "
                     "(docs/specs/politique-spec.md §8). Généré par "
                     "tools/policy_corpus.py ; ne pas éditer à la main."),
        "format": "GNPL v1, enregistrements de 160 octets, petit-boutiste",
        "seed": SEED,
        "count": len(records),
        "levels": list(LEVELS),
        "by_level_and_pending": dict(sorted(counts.items())),
        "models": {
            "network": {"path": player.model, "sha256": sha256(ROOT / player.model)},
            "prune": {"path": player.prune_model,
                      "sha256": sha256(ROOT / player.prune_model)},
        },
        "conditions": ("build natif par défaut (pas NATIVE_FP) ; aucune table "
                       "bilatérale installée ; cache d'évaluation indifférent"),
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"→ {OUT} : {len(records)} décisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

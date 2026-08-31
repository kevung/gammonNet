#!/usr/bin/env python3
"""T73 — le QAT jugé sur le jeu, contre la référence flottante.

## Pourquoi ce script existe, et pas `measure_quantization.py`

`measure_quantization.py` compare deux modèles chargés par `Network.load` —
le format `.bin` (`BGN6`) que `gn_infer_reference.c` lit. Un réseau QAT
exporté (`tools/export_qat_int8.py`, format `BGQ8`) n'entre pas dans ce
chemin : il s'exécute par `gammonnet.infer_int8.Int8Network`, qui appelle le
VRAI noyau C (`gn_gemm_int8_relu_pc`) couche par couche, pas la même API.

C'est la même MÉTRIQUE que `measure_quantization.py` — taux de désaccord de
coup et équité perdue quand il y a désaccord, jugés par le modèle flottant de
référence — la seule qui compte (`PLAN.md`/T31 : « une erreur qui décale
TOUS les coups candidats de la même quantité ne change aucun classement et
ne coûte rien »). Ce qui change est le modèle mis à l'épreuve.

**C'est la première comparaison de ce type que ce dépôt ait produite pour la
QAT.** Le nombre que `train_qat_int8.py` imprime (l'écart d'équité moyen
contre le professeur, sur des positions isolées) n'a jamais été comparable
au 0,011234 de la quantification post-entraînement — ce dernier EST déjà
cette métrique-ci, mesurée le 2026-08-04 ; celui-là est une régression brute,
sans classement de coups, sur un corpus et un protocole différents. Ce
script referme cet écart.

    python tools/measure_qat_decision_loss.py --model models/qat_int8.bin \
        [--positions 300]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from gammonnet import codec  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.infer_int8 import Int8Network  # noqa: E402
from gammonnet.search import ROLLS  # noqa: E402
from measure_quantization import build_corpus  # noqa: E402

REFERENCE = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"


def int8_money_equity(probs: list[float]) -> float:
    """La même formule que `Evaluation.money_equity` (`gn_infer.h`), sur les
    cinq sorties brutes d'`Int8Network.forward` — un chemin indépendant, pas
    un raccourci vers la même fonction."""
    win, win_g, win_bg, lose_g, lose_bg = probs
    return 2.0 * win + win_g + win_bg - lose_g - lose_bg - 1.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=300)
    parser.add_argument("--model", required=True, help="le .bin BGQ8 à éprouver")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.is_file():
        print(f"{model_path} absent — `python tools/export_qat_int8.py`",
              file=sys.stderr)
        return 1

    corpus = build_corpus(args.positions)
    tested = Int8Network.load(model_path)

    print(f"éprouvé : {model_path.name}")
    with Network.load(REFERENCE) as truth:
        equity_gaps: list[float] = []
        losses: list[float] = []
        decisions = 0
        disagreements = 0

        for position in corpus:
            a = truth.evaluate(position)
            b_probs = tested.forward(codec.encode(position))
            equity_gaps.append(abs(a.money_equity - int8_money_equity(b_probs)))

            for d1, d2, _ in ROLLS:
                plays = position.legal_plays(d1, d2)
                if len(plays) < 2:
                    continue
                decisions += 1

                truth_equities = {
                    play.result: truth.evaluate(play.result).money_equity
                    for play in plays
                }
                best_result = min(truth_equities, key=truth_equities.get)
                # Le résultat vu ici est celui de l'ADVERSAIRE (le trait a
                # basculé) : la MEILLEURE équité pour qui vient de jouer est
                # la PIRE pour l'adversaire — même convention que
                # `bench/decision_loss.py` et `measure_quantization.py`.

                int8_equities = {
                    play.result: int8_money_equity(
                        tested.forward(codec.encode(play.result)))
                    for play in plays
                }
                chosen_result = min(int8_equities, key=int8_equities.get)

                if chosen_result == best_result:
                    continue
                disagreements += 1
                losses.append(truth_equities[chosen_result] - truth_equities[best_result])

    print(f"corpus                          {len(corpus)} positions, "
          f"{decisions:,} décisions")
    print()
    print("── L'écart d'évaluation (la mauvaise métrique, pour mémoire) ──")
    print(f"  écart d'équité moyen          {statistics.fmean(equity_gaps):.6f}")
    print(f"  écart d'équité médian         {statistics.median(equity_gaps):.6f}")
    print(f"  écart d'équité maximal        {max(equity_gaps):.6f}")
    print()
    print("── Ce qui compte : le jeu ──")
    rate = disagreements / decisions if decisions else 0.0
    print(f"  taux de désaccord de coup     {rate * 100:.3f} %  "
          f"({disagreements:,} / {decisions:,})")
    if losses:
        print(f"  équité perdue, moyenne        {statistics.fmean(losses):.6f}")
        print(f"  équité perdue, médiane        {statistics.median(losses):.6f}")
        print(f"  équité perdue, maximale       {max(losses):.6f}")
        print()
        print(f"  ➜ équité perdue par décision  {rate * statistics.fmean(losses):.6f}")
        print()
        print("  référence (2026-08-04, même métrique et même protocole) :")
        print("    quantification post-entraînement (fausse, jamais exécutée)  0.011234")
        print("    float16                                                     0.000106")
    else:
        print("  aucun désaccord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

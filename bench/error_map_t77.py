#!/usr/bin/env python3
"""T77 — la carte d'erreur par classe de position, et la décision qu'elle porte.

## Ce que personne n'a publié

Où l'erreur d'un réseau unique se concentre, catégorie par catégorie. DS-12
l'appelle le « Test C » : sans cette carte, tout choix de spécialisation est
aveugle ; avec elle, il devient une décision d'une ligne.

Ce banc ne mesure rien de neuf — il **lit** le registre de T70 sous l'angle des
classes. Ce qui coûte cher (l'arbitrage) est déjà payé ; ce qui reste est une
ventilation et deux colonnes qu'on ne trouve nulle part ensemble :

- **l'erreur par catégorie**, avec son intervalle ;
- **le poids de la catégorie dans les décisions réelles**, mesuré par la passe 1
  du constructeur de corpus et transporté dans le manifeste.

La seconde colonne est celle qu'on oublie, et c'est elle qui décide. Une classe
où l'on se trompe trois fois plus que la moyenne mais qui pèse un demi pour cent
des décisions ne vaut aucune tête dédiée : elle ne peut pas déplacer le total.

## Le seuil, écrit avant de regarder

DS-12 le fixe : une catégorie qui concentre **plus de 2× l'erreur moyenne** ET
**pèse dans les décisions réelles** ouvre une fiche « tête dédiée sur tronc
partagé ». Sinon, aucun découpage — l'aiguillage dur par classe est mesuré
neutre (Whittington), et on ne spécialise pas par principe.

Le second membre du ET demande un chiffre. Ce banc prend **5 % des décisions**,
et le dit : en dessous, même une erreur double ne déplace le total que de 5 % de
son écart, ce qui rentre dans le bruit de l'instrument.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT))

from gammonnet.classify import CLASSES  # noqa: E402

#: Le seuil de DS-12 : l'erreur d'une classe rapportée à l'erreur moyenne.
ERROR_RATIO = 2.0
#: Le second membre du ET, qui manquait à DS-12 : le poids minimal dans les
#: décisions réelles pour qu'une classe puisse déplacer le total.
WEIGHT_FLOOR = 0.05


def main() -> int:
    sys.path.insert(0, str(ROOT / "bench"))
    from measure_t70 import weighted_bootstrap  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scores", required=True,
                        help="la sortie --out de bench/measure_t70.py")
    parser.add_argument("--manifest", required=True,
                        help="le manifeste du corpus, pour les fréquences naturelles")
    parser.add_argument("--detail", default="",
                        help="le registre, si l'on veut recalculer les intervalles")
    parser.add_argument("--bootstrap", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    scores = json.loads(Path(args.scores).read_text())
    manifest = json.loads(Path(args.manifest).read_text())
    natural = manifest["natural"]

    overall = scores["loss"]
    by_class = scores["by_class"]

    print(f"T77 — carte d'erreur : {scores['label']} sur {scores['registry']}")
    print(f"  erreur moyenne pondérée : {overall:.5f} par décision")
    print(f"  seuil DS-12 : erreur > {ERROR_RATIO}× la moyenne "
          f"ET poids > {100 * WEIGHT_FLOOR:.0f} % des décisions réelles\n")

    print(f"  {'classe':22s} {'n':>6s} {'erreur':>10s} {'× moyenne':>10s} "
          f"{'poids réel':>11s}   décision")
    rows = []
    triggers = []
    for name in CLASSES:
        entry = by_class.get(name)
        if not entry or not entry["n"]:
            continue
        loss = entry["loss"]
        ratio = loss / overall if overall else 0.0
        weight = natural.get(name, 0.0)
        hot = ratio > ERROR_RATIO and weight > WEIGHT_FLOOR
        # Une classe qui concentre l'erreur mais ne pèse rien est nommée
        # autrement : ce n'est pas un déclencheur, et la confondre avec un
        # déclencheur ferait ouvrir une fiche pour un gain que l'arithmétique
        # interdit.
        verdict = ("TÊTE DÉDIÉE" if hot else
                   "concentrée mais légère" if ratio > ERROR_RATIO else
                   "—")
        if hot:
            triggers.append(name)
        print(f"  {name:22s} {entry['n']:6d} {loss:10.5f} {ratio:9.2f}× "
              f"{100 * weight:10.2f} %   {verdict}")
        rows.append({"class": name, "n": entry["n"], "loss": loss,
                     "ratio": ratio, "natural_weight": weight, "trigger": hot})

    print()
    if triggers:
        print(f"  → {len(triggers)} classe(s) franchissent les DEUX seuils : "
              f"{', '.join(triggers)}")
        print("    DS-12 ouvre une fiche « tête dédiée sur tronc partagé ». "
              "Ce banc la déclenche ; il ne la conçoit pas.")
    else:
        print("  → aucune classe ne franchit les deux seuils.")
        print("    DS-12 conclut : AUCUN découpage. L'aiguillage dur par classe "
              "est mesuré neutre, et on ne spécialise pas par principe.")

    # Ce que la carte ne dit pas, dit explicitement.
    covered = sum(natural.get(r["class"], 0.0) for r in rows)
    if covered < 0.95:
        print(f"\n  ⚠ les classes mesurées ne couvrent que {100 * covered:.1f} % "
              f"des décisions réelles — le reste n'est pas dans le corpus, et la "
              f"carte est muette dessus. Elle ne dit pas « pas d'erreur » : elle "
              f"ne dit rien.")

    result = {"label": scores["label"], "overall": overall,
              "error_ratio_threshold": ERROR_RATIO,
              "weight_floor": WEIGHT_FLOOR,
              "classes": rows, "triggers": triggers,
              "coverage_of_real_decisions": covered}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\n  → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

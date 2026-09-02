#!/usr/bin/env python3
"""T70 — les tranches déjà récoltées sont-elles cohérentes ?

    python tools/coherence_t70.py docs/corpus/t70/tranches/tranche-*

Une campagne de deux jours ne doit pas rendre son premier verdict au bout de
deux jours. Chaque tranche est tirée d'une graine indépendante : deux tranches
sont donc une **réplication**, et une réplication se lit avant la fin.

Ce banc pose trois questions, dans l'ordre de ce qu'elles coûteraient si la
réponse était mauvaise.

## 1. Les invariants — une ligne du corpus peut-elle être fausse ?

Une décision n'est retenue que si notre coup diffère de celui de gnubg. L'index
`gnubg` ne peut donc **jamais** valoir `ours`. S'il le valait, le corpus
contiendrait des décisions non disputées, l'arbitrage les paierait, et la perte
d'équité qu'on en tirerait serait diluée par des positions où les deux moteurs
sont d'accord — un chiffre plus flatteur, et faux.

## 2. La réplication — les tranches racontent-elles la même histoire ?

Le taux de désaccord, la distribution naturelle des classes, le remplissage des
strates. Deux tranches qui diffèrent au-delà de leur erreur d'échantillonnage
signalent que la graine ne fait pas ce qu'on croit, ou que le générateur dérive.
Le banc compare donc **écart observé contre erreur attendue**, jamais l'écart
seul : deux chiffres différents ne sont pas une anomalie, deux chiffres
différents *au-delà de leur bruit* en sont une.

## 3. Le recouvrement — les tranches se répètent-elles ?

Les graines sont espacées d'un million pour qu'elles ne récoltent jamais les
mêmes positions. C'est une intention ; ceci la mesure. Un recouvrement notable
voudrait dire que la fusion jette du travail payé, et que la taille annoncée du
corpus n'est pas celle qu'on obtient.

Ce banc ne conclut jamais « c'est bon ». Il dit ce qui est vérifié, ce qui
s'écarte, et de combien.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from gammonnet.classify import CLASSES  # noqa: E402

#: Un écart de plus de trois erreurs-types entre deux tranches n'est plus du
#: bruit d'échantillonnage. Le seuil est celui de la fiche T71 pour son z, et
#: il est écrit ici pour se lire, pas pour se régler.
SIGMA_ALARM = 3.0

#: L'EFFET DE GRAPPE de la distribution naturelle, mesuré le 2026-08-27.
#:
#: `natural_distribution` compte les classes le long d'une partie jouée contre
#: elle-même. Des positions consécutives ne sont donc PAS des tirages
#: indépendants — un backgame dure vingt coups, et toutes ses positions sont
#: comptées « backgame ». Le modèle binomial, qui suppose l'indépendance,
#: sous-estime l'erreur d'autant que la classe persiste.
#:
#: Ces facteurs sont l'écart-type OBSERVÉ sur six tirages indépendants de 5 000
#: positions, divisé par l'écart-type binomial correspondant. Sans eux, l'audit
#: signalait blitz et backgame comme incohérentes entre tranches alors que leur
#: écart tient dans leur vrai bruit — un garde-fou qui crie pour rien est un
#: garde-fou qu'on apprend à ignorer.
#:
#: `crashed` mesure 0,7× : un facteur sous 1 n'a pas de sens physique, c'est le
#: bruit de l'écart-type lui-même, estimé sur six tirages seulement. On ne
#: descend donc jamais sous 1 — corriger à la baisse une erreur reviendrait à
#: se déclarer plus sûr que le modèle le plus simple.
DESIGN_EFFECT = {
    "contact": 1.3, "holding": 2.4, "blitz": 2.2, "race_contact": 1.4,
    "bearoff_contact": 1.8, "prime_vs_prime": 1.2, "crashed": 1.0,
    "backgame": 3.4,
}
DESIGN_EFFECT_DEFAULT = 1.5

#: À partir de ce nombre de tranches, l'écart-type OBSERVÉ entre elles remplace
#: le binomial corrigé : quatre réplications indépendantes valent mieux qu'un
#: modèle d'erreur, et n'en supposent aucun.
EMPIRICAL_MIN = 4


def binomial_se(rate: float, n: int) -> float:
    return math.sqrt(rate * (1 - rate) / n) if n > 0 else 0.0


def check_invariants(name: str, rows: list) -> list[str]:
    """Ce qu'une ligne ne peut pas être. Rend la liste des manquements."""
    faults = []
    not_disputed = [r["index"] for r in rows
                    if r.get("gnubg") == r.get("ours", 0)]
    if not_disputed:
        faults.append(
            f"{len(not_disputed)} décision(s) où gnubg joue le coup que nous "
            f"jouons — le corpus n'est plus celui des décisions disputées "
            f"(index {not_disputed[:5]}…)")

    out_of_range = [r["index"] for r in rows
                    if not 0 <= r.get("gnubg", -1) < len(r.get("candidates", []))]
    if out_of_range:
        faults.append(f"{len(out_of_range)} index gnubg hors de la liste des "
                      f"candidats (index {out_of_range[:5]}…)")

    duplicated = [r["index"] for r in rows
                  if len(set(r["candidates"])) != len(r["candidates"])]
    if duplicated:
        faults.append(f"{len(duplicated)} décision(s) dont la liste de candidats "
                      f"contient un doublon — `ids.index()` rendrait le premier, "
                      f"donc peut-être pas celui de gnubg (index {duplicated[:5]}…)")

    thin = [r["index"] for r in rows if len(r.get("candidates", [])) < 2]
    if thin:
        faults.append(f"{len(thin)} décision(s) à moins de deux candidats : "
                      f"il n'y a rien à arbitrer (index {thin[:5]}…)")

    unknown = sorted({r["class"] for r in rows} - set(CLASSES))
    if unknown:
        faults.append(f"classe(s) inconnue(s) : {', '.join(unknown)}")

    indices = [r["index"] for r in rows]
    if len(set(indices)) != len(indices):
        faults.append("des index se répètent DANS la tranche")
    if indices and sorted(indices) != list(range(len(indices))):
        faults.append("les index ne forment pas 0..n-1")

    weights = [r.get("weight", 0.0) for r in rows]
    if any(w <= 0 for w in weights):
        faults.append(f"{sum(1 for w in weights if w <= 0)} poids nul ou négatif "
                      f"— ces décisions ne compteraient pas dans la moyenne")
    return faults


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slices", nargs="+", type=Path)
    parser.add_argument("--context", default="money")
    args = parser.parse_args()

    loaded = []
    for path in sorted(set(args.slices)):
        corpus = path / f"corpus-{args.context}.jsonl"
        manifest = path / "manifeste.json"
        if not (corpus.exists() and corpus.stat().st_size and manifest.exists()):
            print(f"  {path.name} : incomplète, ignorée")
            continue
        rows = [json.loads(l) for l in corpus.read_text().splitlines() if l.strip()]
        loaded.append((path, json.loads(manifest.read_text()), rows))

    if not loaded:
        print("aucune tranche complète", file=sys.stderr)
        return 2

    print(f"T70 — cohérence de {len(loaded)} tranche(s), contexte {args.context}\n")
    problems = 0

    # ── 1. les invariants ──────────────────────────────────────────────────
    print("── invariants de structure ────────────────────────────────────")
    for path, _manifest, rows in loaded:
        faults = check_invariants(path.name, rows)
        if faults:
            problems += len(faults)
            print(f"  {path.name}  ✗ {len(rows)} décisions")
            for fault in faults:
                print(f"      ✗ {fault}")
        else:
            print(f"  {path.name}  ✓ {len(rows)} décisions — "
                  "toutes disputées, candidats distincts, index contigus, poids > 0")

    # ── 2. la réplication ──────────────────────────────────────────────────
    print("\n── taux de désaccord, tranche par tranche ─────────────────────")
    print("   (T36 avait mesuré 9,5 % par un chemin indépendant ; "
          "la calibration du 2026-08-27, 11,0 %)")
    rates = []
    for path, manifest, rows in loaded:
        stats = manifest["contexts"][args.context]
        compared = stats["compared"]
        rate = stats["disagreement_rate"]
        se = binomial_se(rate, compared)
        rates.append((path.name, rate, se, compared))
        print(f"  {path.name}  {100 * rate:5.2f} % ± {100 * se:.2f} "
              f"(sur {compared} comparées)")
    if len(rates) >= 2:
        worst = 0.0
        for i in range(len(rates)):
            for j in range(i + 1, len(rates)):
                _, r1, s1, _ = rates[i]
                _, r2, s2, _ = rates[j]
                spread = math.sqrt(s1 ** 2 + s2 ** 2)
                sigma = abs(r1 - r2) / spread if spread else 0.0
                worst = max(worst, sigma)
        verdict = "compatibles" if worst < SIGMA_ALARM else "INCOMPATIBLES"
        print(f"  → écart maximal entre tranches : {worst:.2f} σ — {verdict} "
              f"(seuil {SIGMA_ALARM:g} σ)")
        if worst >= SIGMA_ALARM:
            problems += 1

    # ── la distribution naturelle, mesurée indépendamment par chaque tranche
    print("\n── distribution naturelle des classes, mesurée par tranche ────")
    samples = [(path.name, m["natural"], m["natural_sample"]) for path, m, _ in loaded]
    classes = sorted({k for _, n, _ in samples for k in n if n[k] > 0},
                     key=lambda k: -samples[0][1].get(k, 0.0))
    if len(samples) >= EMPIRICAL_MIN:
        print(f"   ({len(samples)} réplications indépendantes : la colonne « σ observé » EST")
        print("    l'erreur, mesurée entre tranches, et aucun modèle n'est supposé)")
    else:
        print("   (l'écart est rapporté au bruit CORRIGÉ de l'effet de grappe : des")
        print("    positions consécutives d'une même partie ne sont pas indépendantes)")
    header = "  " + f"{'classe':22s}" + "".join(f"{n:>12s}" for n, _, _ in samples)
    label = "σ observé" if len(samples) >= EMPIRICAL_MIN else "grappe"
    print(header + f"{label:>9s}{'écart max':>11s}")
    for klass in classes:
        values = [(n.get(klass, 0.0), s) for _, n, s in samples]
        cells = "".join(f"{100 * v:11.2f}%" for v, _ in values)
        # AVEC ASSEZ DE RÉPLICATIONS, ON NE MODÉLISE PLUS : ON MESURE.
        #
        # Chaque tranche estime la distribution naturelle sur son propre
        # échantillon, tiré d'une graine indépendante. Dès qu'il y en a assez,
        # leur écart-type EST l'erreur — plus besoin d'un binomial corrigé d'un
        # facteur de grappe estimé ailleurs. C'était annoncé le 2026-08-27 :
        # « les six tranches donneront six estimations à 20 000 échantillons, et
        # la dispersion se lira alors directement ».
        #
        # Le facteur tabulé ne sert plus que de repli sous quatre tranches, où
        # un écart-type sur trois points ne vaut pas grand-chose.
        if len(values) >= EMPIRICAL_MIN:
            observed = statistics.stdev(v for v, _ in values)
            deff = None
        else:
            observed = None
            deff = max(1.0, DESIGN_EFFECT.get(klass, DESIGN_EFFECT_DEFAULT))
        worst = 0.0
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                (v1, n1), (v2, n2) = values[i], values[j]
                if observed is not None:
                    spread = observed * math.sqrt(2)
                else:
                    spread = deff * math.sqrt(binomial_se(v1, n1) ** 2
                                              + binomial_se(v2, n2) ** 2)
                worst = max(worst, abs(v1 - v2) / spread if spread else 0.0)
        flag = "  ✗" if worst >= SIGMA_ALARM else ""
        if worst >= SIGMA_ALARM:
            problems += 1
        shown = (f"{100 * observed:7.3f}%" if observed is not None
                 else f"{deff:7.1f}×")
        print(f"  {klass:22s}{cells}{shown}{worst:10.2f}σ{flag}")

    # ── le remplissage des strates ─────────────────────────────────────────
    print("\n── remplissage des strates (le facteur d'examen fait-il son office ?)")
    for path, manifest, rows in loaded:
        counts = collections.Counter(r["class"] for r in rows)
        quota = manifest.get("quota", {})
        starved = [(k, counts.get(k, 0), quota[k]) for k in quota
                   if quota[k] and counts.get(k, 0) / quota[k] < 0.8]
        # Le facteur d'examen n'est pas consigné au manifeste — un manque de
        # provenance pour un corpus qui se veut « figé et versionné ». À
        # corriger dans le générateur, mais PAS au milieu d'une campagne : les
        # tranches déjà récoltées ne l'auraient pas, et une provenance
        # inconsistante est pire qu'une provenance incomplète.
        factor = manifest.get("examine_factor", "non consigné")
        if starved:
            print(f"  {path.name} (facteur {factor}) — {len(starved)} sous-remplie(s) :")
            for name, got, want in sorted(starved, key=lambda t: t[1] / t[2]):
                print(f"      {name:22s} {got:5d}/{want:5d} ({100 * got / want:5.1f} %)")
            print("      → leur intervalle sera large ; T77 lit ces strates.")
        else:
            print(f"  {path.name} (facteur {factor})  ✓ toutes les strates à 80 % ou plus")

    # ── 3. le recouvrement ─────────────────────────────────────────────────
    if len(loaded) >= 2:
        print("\n── recouvrement entre tranches ────────────────────────────────")
        print("   (les graines sont espacées d'un million pour qu'il soit nul ;")
        print("    ceci le mesure au lieu de le supposer)")
        keys = []
        for path, _m, rows in loaded:
            keys.append((path.name, {(r["turn"], r["position_id"], tuple(r["dice"]))
                                     for r in rows}))
        total_overlap = 0
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                (n1, k1), (n2, k2) = keys[i], keys[j]
                shared = len(k1 & k2)
                total_overlap += shared
                if shared:
                    print(f"  {n1} ∩ {n2} : {shared} décision(s) commune(s) "
                          f"({100 * shared / min(len(k1), len(k2)):.3f} %)")
        if total_overlap == 0:
            print("  ✓ aucune décision commune : la fusion ne jettera rien")
        else:
            print(f"  {total_overlap} recouvrement(s) au total — la fusion les "
                  f"écartera, le corpus final sera d'autant plus petit")

    print(f"\n═══ {problems} anomalie(s) relevée(s) ═══")
    if not problems:
        print("  Aucun manquement aux invariants, et les tranches se répètent")
        print("  dans leur bruit d'échantillonnage. Ce n'est pas une preuve que")
        print("  le corpus est BON — c'est la preuve qu'il n'est pas incohérent.")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""T70 — l'arbitre escaladé : le registre d'équité du corpus figé.

## Le principe

Le corpus (`tools/build_corpus_t70.py`) dit **quelles** décisions sont
disputées et **quels coups** y sont plausibles. Ce banc dit ce que chaque coup
vaut. Le résultat est un registre : une ligne par décision, l'équité de chaque
candidat, l'erreur sur son écart au pivot, et la passe qui l'a tranchée.

Le registre est ce qui rend un point de comparaison rapide. Une fois payé, noter
un moteur candidat ne demande plus aucun rollout : il joue, on lit.

## L'escalade, et pourquoi elle a trois marches

Un rollout complet à IC 95 % < 0,005 sur toutes les décisions coûterait des
jours. Or la plupart des décisions ne le méritent pas : quand un coup domine
franchement, un instrument grossier le voit aussi bien qu'un instrument fin.

| passe | instrument | quand |
|---|---|---|
| **0** | table bilatérale exacte | tous les candidats dans son domaine |
| **1** | gnubg 3-ply | l'écart meilleur/second dépasse `--net` |
| **2** | rollout tronqué, variance réduite, dés communs | sinon |
| **3** | rollout complet, dés communs | ce que la passe 2 n'a pas tranché |

La passe 0 est sans variance ni réserve. La passe 1 est **biaisée en faveur de
gnubg** — c'est son instrument qui parle — et ce biais n'est pas supposé petit :
il est mesuré, par `--audit`, qui rejoue en passe 2 un échantillon de ce que la
passe 1 a tranché. L'écart est publié avec chaque usage du registre. Un arbitre
qu'on n'a pas vérifié n'arbitre rien (règle T39).

## Ce que ce banc ne fait pas

Il ne rend aucun verdict de force. Il produit l'échelle ; la lecture est dans
`bench/measure_t70.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
# `tools/` aussi : les contextes de score sont définis là où le corpus est
# construit, et une seconde définition serait un second joueur.
sys.path.insert(0, str(ROOT))

from gammonnet import codec  # noqa: E402
from gammonnet import gnubg_board as gb  # noqa: E402
from gammonnet.bearoff import TwoSidedBearoff  # noqa: E402
from gammonnet.infer import Network  # noqa: E402
from gammonnet.met import MatchState  # noqa: E402
from gammonnet.rollout import RolloutConfig, rollout_candidates_paired  # noqa: E402
from gammonnet.rules import BLACK, WHITE, Position  # noqa: E402
from gammonnet.search import SearchConfig  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
DATABASE = ROOT / "gnu_bearoff_database" / "gnubg_ts6x11.bd"
PROGRESS = Path(os.environ.get("T70_PROGRESS", "/tmp/t70-arbitrage-progress.log"))

#: La profondeur de la passe 1. Supérieure à celle des moteurs comparés (2-ply),
#: sans quoi elle arbitrerait avec le regard de l'un des deux plaideurs.
ARBITER_PLY = 3

#: L'écart au meilleur, selon gnubg 3-ply, au-delà duquel un candidat est tenu
#: pour DOMINÉ sans qu'aucun rollout ne le vérifie.
#:
#: Mesuré sur le corpus, et le chiffre a renversé la conception : l'écart
#: meilleur/second y a une médiane de **0,0016**, si bien qu'un critère « l'écart
#: est net » à 0,020 ne trancherait **aucune** décision. C'était prévisible après
#: coup — le corpus ne retient que les décisions DISPUTÉES, et deux moteurs
#: divergent précisément là où les coups sont proches. Le corpus sélectionne donc
#: les positions où rien ne domine.
#:
#: L'étendue, elle, a une médiane de 0,048 : les candidats lointains sont
#: franchement mauvais, seuls ceux de tête sont serrés. C'est ce qui rend
#: l'escalade praticable — on écarte les mauvais à la passe 1, et le rollout ne
#: paie que le groupe de tête.
#:
#: La valeur est CHOISIE SUR MESURE (25 décisions, 98 candidats) :
#:
#:   seuil   tête moyenne   décisions closes   trajectoires
#:   0,010       2,68            52 %               35
#:   0,020       2,84            44 %               43
#:   0,030       3,16            28 %               60
#:   0,050       3,44            20 %               71
#:   sans tri    3,92             0 %               98
#:
#: 0,010 économise le plus, mais c'est GNUBG qui décide qui entre dans le groupe
#: de tête : un seuil trop serré exclurait un bon coup dès que gnubg se trompe
#: de dix millièmes sur lui, et ce biais est justement l'inconnue que `--audit`
#: mesure. 0,020 garde une marge du double pour un coût à peine supérieur —
#: ×2,3 de trajectoires en moins contre ×2,8, et 44 % de décisions closes.
DOMINANCE_MARGIN = 0.020

#: La résolution par décision, et le raisonnement qui la fixe.
#:
#: La fiche écrit « rollout complet (IC 95 % < 0,005) ». Ce serait la bonne
#: exigence s'il fallait trancher CHAQUE décision individuellement. Ce n'est pas
#: la métrique de T70 : la métrique est une MOYENNE de pertes sur 10⁴–10⁵
#: décisions, et l'erreur d'un arbitrage non biaisé se divise par la racine du
#: nombre de décisions.
#:
#: Le calcul, sur ce qui doit être visible — l'intervalle 2-ply par décision de
#: T36, [-0,00005 ; +0,00019], que T71 doit faire passer au-dessus de zéro :
#:
#:  - deux moteurs proches diffèrent sur ~10 % des décisions, soit ~1 000 sur
#:    10 000 ; le registre étant FIGÉ, ils lisent les mêmes valeurs partout où
#:    ils jouent le même coup, et ces décisions contribuent exactement zéro ;
#:  - un effet de 0,0002 sur l'ensemble vaut donc ~0,002 sur les décisions de
#:    désaccord ;
#:  - avec un se de `s` par décision, le se de leur moyenne vaut s/racine(1000),
#:    soit s/32. Pour rester sous le tiers de l'effet, il faut s <= 0,02.
#:
#: On retient 0,010, la moitié de ce que le calcul autorise : la marge paie
#: l'incertitude du raisonnement lui-meme. Par rapport au 0,00255 qu'imposait la
#: lecture littérale de la fiche, le nombre d'essais est divisé par ~15.
#:
#: Ce que cela suppose, et qui se vérifie ailleurs : que l'erreur d'arbitrage
#: soit NON BIAISÉE. Un biais, lui, ne se divise par rien — d'où
#: `bench/arbiter_bias_t70.py`, qui doit passer avant toute campagne.
FULL_TARGET_SE = 0.010 / 1.96

#: Le se visé par la passe 2. Plus lâche que la passe 3 : son rôle est de
#: trancher ce qui se tranche vite, pas de tout résoudre.
TRUNCATED_TARGET_SE = 0.012


def context_state(context: str) -> MatchState | None:
    from tools.build_corpus_t70 import CONTEXTS  # noqa: PLC0415
    return CONTEXTS[context]


def resolution_of(differences, errors, pivot: int, margin: float) -> list[str]:
    """L'état de chaque candidat : `resolved`, `dominated`, ou `open`.

    Exiger que les six candidats soient connus à ±`margin` rendrait l'arbitrage
    prohibitif — l'estimation de coût donnait des dizaines d'heures là où la
    fiche exige « des heures ». Or ce n'est pas nécessaire : un coup dont on
    sait **avec certitude** qu'il est pire que le pivot d'au moins `margin` est
    tranché, quelle que soit l'imprécision qui reste sur sa valeur exacte.

    Ce que le registre perd, il le dit : un candidat `dominated` porte une
    estimation dont l'intervalle est large, et `bench/measure_t70.py` compte à
    part les décisions où le moteur noté a justement joué un tel coup. Un bon
    moteur ne joue presque jamais un coup manifestement dominé, donc
    l'imprécision se concentre là où elle ne coûte rien — mais elle n'est
    jamais passée sous silence.
    """
    states = []
    for index, (difference, error) in enumerate(zip(differences, errors)):
        if index == pivot:
            states.append("resolved")
        elif 1.96 * error <= margin:
            states.append("resolved")
        elif difference + 1.96 * error < -margin:
            states.append("dominated")
        else:
            states.append("open")
    return states


def decided(differences, errors, pivot: int, margin: float) -> bool:
    """Plus aucun candidat n'est `open` : la décision est tranchée."""
    return "open" not in resolution_of(differences, errors, pivot, margin)


def arbitrate_batch(payload):
    """Une tranche du corpus, arbitrée de bout en bout par un processus."""
    (rows, context, model, seed, net_margin, truncated_trials, full_trials,
     truncate, deep_truncate, margin, audit_indices) = payload

    from gammonnet.gnubg_engine import GnubgSession, gnubg_state

    network = Network.load(model)
    session = GnubgSession()
    table = TwoSidedBearoff(str(DATABASE)) if DATABASE.exists() else None
    state = context_state(context)
    request_state = None
    if state is not None:
        request_state = gnubg_state(0, MatchState(state.away_opponent,
                                                  state.away_on_roll,
                                                  state.cube, state.crawford),
                                    jacoby=False)  # pas de `beavers` : ce
        # paramètre n'existe dans aucune signature de `gnubg_state`, et cette
        # ligne levait donc un TypeError. Elle ne s'exécute que pour un contexte
        # de SCORE — money passe `state = None` et saute la branche entière —
        # d'où un chemin jamais exercé jusqu'au 2026-08-28, où les huit tranches
        # des quatre contextes ont échoué en quelques secondes.

    out = []
    for row in rows:
        turn = row["turn"]
        mover = turn
        opponent = BLACK if mover == WHITE else WHITE
        # Les candidats sont des positions APRÈS coup : le trait est passé.
        results = [codec.position_from_id(pid, opponent) for pid in row["candidates"]]
        record = dict(row)
        started = time.perf_counter()

        # ── Passe 0 : la table exacte ───────────────────────────────
        if (table is not None and state is None
                and all(table.contains(r) for r in results)):
            # `.cubeless` et non une équité agrégée : le corpus money est
            # cubeless, et lire ici une des trois colonnes cubeful mêlerait
            # deux échelles. `equity` répond pour le joueur au trait de la
            # position confiée, soit l'adversaire de celui qui a joué : d'où la
            # négation, la même qui court dans tout ce dépôt.
            equities = [-table.equity(r).cubeless for r in results]
            # Zéro est ici la VRAIE valeur : une table de fin de partie rend
            # l'équité exacte, pas une estimation. C'est le seul endroit du
            # fichier où un intervalle nul se justifie.
            record.update(pass_used=0, equities=equities,
                          errors=[0.0] * len(results),
                          resolution=["resolved"] * len(results),
                          trials=0, seconds=time.perf_counter() - started)
            out.append(record)
            _tick()
            continue

        # ── Passe 1 : gnubg 3-ply ───────────────────────────────────
        values = session.evaluate([gb.to_gnubg(r) for r in results],
                                  plies=ARBITER_PLY, prune=1, state=request_state)
        gnubg_equities = [-float(v[5]) for v in values]
        best_equity = max(gnubg_equities)
        # Le GROUPE DE TÊTE : les candidats que gnubg 3-ply ne condamne pas
        # franchement. Eux seuls iront au rollout ; les autres sont dominés, et
        # leur valeur exacte n'a aucune importance parce qu'aucun moteur
        # raisonnable ne les jouera. Ce tri est ce qui divise le coût du rollout
        # par le rapport entre le nombre de candidats et la taille du groupe.
        head = [i for i, equity in enumerate(gnubg_equities)
                if best_equity - equity <= net_margin]
        spread = best_equity - min(gnubg_equities[i] for i in head)
        audit = row["index"] in audit_indices

        if (len(head) <= 1 or spread < margin) and not audit:
            # Tranché sans rollout — non pas parce qu'on sait QUI gagne, mais
            # parce que l'enjeu entre les prétendants est sous la résolution :
            # la perte de n'importe lequel d'entre eux est alors connue à
            # `margin` près, ce que le registre doit précisément garantir.
            states = ["resolved" if i in head else "dominated"
                      for i in range(len(results))]
            # gnubg 3-ply est DÉTERMINISTE : rejouer rend le même nombre, donc
            # l'erreur d'échantillonnage est nulle. Elle n'est pas exacte pour
            # autant — le biais de cette passe est une autre question, celle
            # que l'audit `--audit` sert à chiffrer. `errors` mesure la
            # dispersion, jamais la justesse, et le registre porte
            # `pass_used` pour qu'on ne confonde pas les deux.
            record.update(pass_used=1, equities=gnubg_equities,
                          errors=[0.0] * len(results), spread=spread,
                          head=len(head), resolution=states,
                          trials=0, seconds=time.perf_counter() - started)
            out.append(record)
            _tick()
            continue

        # ── Passe 2 : rollout tronqué, variance réduite ─────────────
        # Sur le groupe de tête SEUL. Les dominés gardent leur équité gnubg et
        # leur étiquette : ils sont pires, on sait de combien à peu près, et
        # c'est tout ce dont le registre a besoin d'eux.
        rolled = [results[i] for i in head]
        pivot_in_head = max(range(len(head)),
                            key=lambda j: gnubg_equities[head[j]])
        pivot = head[pivot_in_head]
        config = RolloutConfig(trials=truncated_trials, truncate=truncate,
                               seed=seed + 7919 * row["index"], policy=SearchConfig(ply=0),
                               variance_reduction=True,
                               target_se=TRUNCATED_TARGET_SE, min_trials=72,
                               match=state, use_cube=False)
        head_equities, differences, errors, trials = rollout_candidates_paired(
            network, rolled, config, pivot_in_head)
        used, total_trials = 2, trials

        if not decided(differences, errors, pivot_in_head, margin):
            # ── Passe 3 : rollout long ──────────────────────────────
            # Tronqué à `deep_truncate` et non complet. Un rollout non tronqué
            # avec réduction de variance joue cinq fois plus de plis, chacun
            # payant une recherche 1-ply : l'estimation à partir de T39 donne
            # ~6 h par décision, et deux décisions arbitrées l'ont confirmé.
            config = RolloutConfig(trials=full_trials, truncate=deep_truncate,
                                   seed=seed + 7919 * row["index"],
                                   policy=SearchConfig(ply=0),
                                   variance_reduction=True,
                                   target_se=FULL_TARGET_SE, min_trials=108,
                                   match=state, use_cube=False)
            head_equities, differences, errors, trials = rollout_candidates_paired(
                network, rolled, config, pivot_in_head)
            used, total_trials = 3, trials

        # Recomposer le registre complet : le groupe de tête porte les équités
        # du rollout, les dominés gardent celles de gnubg, recalées sur le pivot
        # pour que les deux moitiés vivent sur la MÊME échelle. Sans ce recalage,
        # une perte se lirait tantôt en unités de rollout tantôt en unités de
        # gnubg, et la moyenne mélangerait deux règles graduées différemment.
        offset = head_equities[pivot_in_head] - gnubg_equities[pivot]
        equities = [gnubg_equities[i] + offset for i in range(len(results))]
        states = ["dominated"] * len(results)
        head_states = resolution_of(differences, errors, pivot_in_head, margin)
        for j, i in enumerate(head):
            equities[i] = head_equities[j]
            states[i] = head_states[j]

        # L'INTERVALLE, et non un zéro. Le rollout calcule une erreur-type par
        # candidat de tête, `resolution_of` s'en sert juste au-dessus pour
        # décider si un candidat est résolu ou resté ouvert — et le registre
        # les jetait pour écrire des zéros. Un registre dont chaque intervalle
        # vaut 0,000 se lit comme un arbitrage parfaitement résolu : c'est le
        # « zéro par défaut » que la règle 2 de CLAUDE.md nomme, et la fiche
        # T70 exige au contraire que « chaque décision porte sa passe
        # d'arbitrage ET SON INTERVALLE ».
        #
        # `None` pour les candidats hors du groupe de tête, jamais zéro : leur
        # valeur vient de gnubg recalé sur le pivot, aucun rollout ne les a
        # prix, et leur intervalle n'est donc pas mesuré. Ne pas mesurer et
        # mesurer zéro sont deux choses différentes ; `resolution` dit déjà
        # « dominated » pour ceux-là.
        candidate_errors = [None] * len(results)
        for j, i in enumerate(head):
            candidate_errors[i] = errors[j]
        record.update(pass_used=used, equities=equities, head=len(head),
                      errors=candidate_errors, pivot=pivot,
                      trials=total_trials, resolution=states,
                      seconds=time.perf_counter() - started)
        if audit:
            # L'audit garde les DEUX lectures de la même décision : c'est
            # l'écart entre elles qui chiffre le biais de la passe 1.
            #
            # `spread` et non `gap` : `gap` n'existait nulle part dans ce
            # fichier, et cette ligne levait donc un NameError dès la première
            # décision auditée qui montait en passe 2 — c'est-à-dire au bout de
            # quelques secondes d'une vraie campagne, `--audit` valant 0,05 par
            # défaut. Le chemin n'avait jamais été exécuté : les tests couvrent
            # l'escalade, pas l'audit de l'escalade.
            #
            # `spread` est l'écart, SELON LA PASSE 1, à l'intérieur du groupe de
            # tête. C'est la grandeur qui a décidé de l'escalade, donc celle
            # qu'un audit de cette décision doit consigner à côté des deux
            # lectures.
            record["audit_pass1"] = gnubg_equities
            record["audit_gap"] = spread
        out.append(record)
        _tick()

    session.close()
    if table is not None:
        table.close()
    return out



def protocol_header(args, corpus: Path, count: int, context: str) -> dict:
    """Ce qui doit être identique pour que deux lots vivent dans le même journal.

    Un journal qui mélangerait deux protocoles n'est plus une mesure : les
    décisions arbitrées avec un budget d'essais ou une marge de dominance
    différents ne sont pas comparables entre elles, et rien dans le fichier ne
    le dirait. La reprise CONFRONTE donc l'en-tête à l'invocation, et refuse au
    moindre désaccord — la règle de `run_t35.py`, pour la même raison.

    Le nombre de processus n'y figure pas, et c'est le point : depuis que la
    graine d'une décision vaut `seed + 7919 * index`, le découpage n'influe
    plus sur le résultat. Reprendre à 26 processus ce qui a commencé à 8 rend
    le même registre.
    """
    return {
        "corpus": corpus.name, "decisions": count, "context": context,
        "seed": args.seed, "net": args.net, "resolution": args.resolution,
        "truncated_trials": args.truncated_trials,
        "full_trials": args.full_trials, "truncate": args.truncate,
        "deep_truncate": args.deep_truncate, "audit": args.audit,
        "model": MODEL.name,
    }


def load_journal(journal: Path, header: dict) -> set:
    """Les index déjà arbitrés, l'en-tête vérifié. Refuse si le protocole diffère."""
    if not journal.exists():
        return set()
    done, seen_header = set(), None
    for line in journal.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # Dernière ligne tronquée par une coupure : son index manque donc au
            # journal, et la décision sera simplement rejouée.
            continue
        if "header" in row and len(row) == 1:
            seen_header = row["header"]
            continue
        if "index" in row:
            done.add(row["index"])
    if seen_header is not None and seen_header != header:
        differences = sorted(
            k for k in set(seen_header) | set(header)
            if seen_header.get(k) != header.get(k))
        raise SystemExit(
            f"REFUS — le journal {journal.name} a été écrit sous un autre "
            f"protocole ; désaccord sur : {', '.join(differences)}.\n"
            "Un journal qui mélange deux protocoles n'est plus une mesure. "
            "Reprendre avec les mêmes réglages, ou écrire ailleurs.")
    return done


def read_journal_records(journal: Path) -> list:
    """Le registre, reconstitué depuis le journal : trié, dédoublonné par index."""
    if not journal.exists():
        return []
    best = {}
    for line in journal.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "index" in row and not ("header" in row and len(row) == 1):
            best[row["index"]] = row
    return [best[k] for k in sorted(best)]


def _tick():
    try:
        with open(PROGRESS, "a") as fh:
            fh.write("x\n")
    except OSError:
        pass


def main() -> int:
    from concurrent.futures import ProcessPoolExecutor, as_completed

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, help="le .jsonl à arbitrer")
    parser.add_argument("--out", default="", help="registre de sortie (.jsonl)")
    parser.add_argument("--workers", type=int, default=26)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--net", type=float, default=DOMINANCE_MARGIN,
                        help="écart au meilleur au-delà duquel un candidat est dominé")
    parser.add_argument("--deep-truncate", type=int, default=25,
                        help="troncature de la passe 3 ; 0 serait un rollout complet, "
                             "impraticable avec réduction de variance")
    parser.add_argument("--resolution", type=float, default=0.010,
                        help="largeur d'IC 95 %% en deçà de laquelle on s'arrête")
    # Les plafonds sont des BUDGETS, pas des limites théoriques. Sur une
    # décision où l'erreur ne converge pas — et il en existe —, `target_se` ne
    # déclenche jamais et l'on paie le plafond en entier. Avec 1 296 essais à
    # variance réduite sur trois candidats tronqués à 17 plis, cela vaut des
    # HEURES pour une seule décision : la plomberie s'y est arrêtée deux fois,
    # bloquée à 7 décisions sur 25 pendant vingt minutes.
    #
    # Le plafond borne donc le coût, et ce qui n'est pas résolu dans ce budget
    # est marqué « ouvert » et rapporté. C'est le bon compromis : une décision
    # pathologique coûte un budget fixe au lieu de manger la campagne, et le
    # registre dit lesquelles n'ont pas abouti au lieu de le taire.
    parser.add_argument("--truncated-trials", type=int, default=324,
                        help="budget de la passe 2 ; atteint = candidat « ouvert »")
    parser.add_argument("--full-trials", type=int, default=648,
                        help="budget de la passe 3 ; atteint = candidat « ouvert »")
    parser.add_argument("--truncate", type=int, default=11)
    parser.add_argument("--audit", type=float, default=0.05,
                        help="part des décisions tranchées en passe 1 rejouées en passe 2")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chunk", type=int, default=4,
                        help="taille maximale d'une tranche rendue au parent ; "
                             "borne ce qu'une coupure fait perdre. 4 et non 64 : "
                             "une décision coûte ~16,7 min·cœur (mesuré le "
                             "2026-08-28), donc 64 ferait 17,8 h sans une seule "
                             "écriture au journal — la reprise ne protégerait "
                             "plus rien pendant presque une journée.")
    parser.add_argument("--offset", type=int, default=0,
                        help="ne traiter que les décisions d'index >= OFFSET — "
                             "le découpage entre MACHINES, pas entre processus")
    parser.add_argument("--journal-only", action="store_true",
                        help="ne rien arbitrer : reconstruire le registre depuis "
                             "le journal d'une campagne interrompue")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    rows = [json.loads(line) for line in corpus.read_text().splitlines() if line.strip()]
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print("corpus vide", file=sys.stderr)
        return 2
    context = rows[0]["context"]

    rng = random.Random(args.seed)
    audit_indices = {row["index"] for row in rows if rng.random() < args.audit}

    out = Path(args.out) if args.out else corpus.with_name(
        corpus.name.replace("corpus-", "registre-"))
    PROGRESS.unlink(missing_ok=True)

    print("T70 — arbitrage escaladé du corpus figé")
    print(f"  {len(rows)} décisions, contexte {context}, {args.workers} processus")
    print(f"  dominé au-delà de {args.net}, résolution visée {args.resolution}")
    print(f"  audit de la passe 1 : {len(audit_indices)} décisions rejouées")
    print(f"  suivi : {PROGRESS}", flush=True)

    journal = Path(str(out) + ".journal")
    header = protocol_header(args, corpus, len(rows), context)

    if args.journal_only:
        # Une campagne coupée laisse un journal complet et pas de registre. Cette
        # porte le reconstruit sans rien recalculer : ce qui a été payé une fois
        # ne doit pas l'être deux.
        records = read_journal_records(journal)
        if not records:
            print(f"journal vide ou absent : {journal}", file=sys.stderr)
            return 2
        with open(out, "w") as fh:
            for record in records:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        print(f"  registre reconstruit depuis le journal : {len(records)} décisions")
        print(f"  → {out}")
        return 0

    done = load_journal(journal, header)
    if done:
        print(f"  reprise : {len(done)} décisions déjà arbitrées dans {journal.name}")
    todo = [row for row in rows if row["index"] not in done]
    if args.offset:
        # Le découpage entre machines se fait ICI, et pas plus haut, pour trois
        # raisons qui sont toutes des façons de ne pas fabriquer deux mesures
        # incomparables : l'en-tête de protocole est calculé sur le corpus
        # ENTIER (donc les deux journaux se reconnaissent), l'échantillon
        # d'audit aussi (donc les deux machines auditent les mêmes décisions),
        # et la graine d'une décision vaut `seed + 7919 * index` — l'index
        # ABSOLU, jamais un rang dans une tranche. Deux journaux produits sur
        # deux machines à des offsets disjoints se recollent alors par simple
        # concaténation, et une décision faite deux fois rend deux fois la
        # même ligne.
        before = len(todo)
        todo = [row for row in todo if row["index"] >= args.offset]
        print(f"  tranche : index >= {args.offset}, "
              f"{len(todo)} décisions sur {before}")
    if not todo:
        print("  rien à arbitrer : le journal est complet.")

    workers = max(1, min(args.workers, max(len(todo), 1)))
    # Des tranches COURTES, et non une par processus. Une tranche par processus
    # ne rend rien avant sa fin : sur une campagne de plusieurs jours, une
    # coupure perdrait tout le travail en vol. Ici chaque tranche revient en
    # quelques minutes, est écrite et poussée sur disque, et la reprise ne coûte
    # au pire que les tranches en cours. C'est la construction de `run_t35.py`,
    # portée à l'arbitrage.
    span = max(1, min(args.chunk, max(len(todo) // (workers * 4), 1)))
    chunks = [todo[i:i + span] for i in range(0, len(todo), span)]
    payloads = [(chunk, context, str(MODEL), args.seed, args.net,
                 args.truncated_trials, args.full_trials, args.truncate,
                 args.deep_truncate, args.resolution, audit_indices)
                for chunk in chunks if chunk]

    started = time.perf_counter()
    written = 0
    with journal.open("a") as fh:
        if not done:
            fh.write(json.dumps({"header": header}, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

        def note(part):
            nonlocal written
            for record in part:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
                written += 1
            # Poussé sur disque à chaque tranche, pas à la fin : éteindre la
            # machine au milieu ne coûte que les tranches en vol.
            fh.flush()
            os.fsync(fh.fileno())
            spent = time.perf_counter() - started
            rate = written / spent if spent > 0 else 0.0
            left = (len(todo) - written) / rate if rate > 0 else 0.0
            print(f"    {written}/{len(todo)} arbitrées  {rate * 3600:.0f}/h  "
                  f"reste ~{left / 3600:.1f} h", flush=True)

        if len(payloads) == 1:
            note(arbitrate_batch(payloads[0]))
        elif payloads:
            # `as_completed` et non `map` : `map` rend les résultats dans
            # l'ordre de soumission, donc une tranche lente retiendrait en
            # mémoire toutes celles finies après elle — et le journal, censé
            # borner ce qu'une coupure fait perdre, ne serait plus écrit au fil
            # de l'eau. On prend ce qui arrive, quand ça arrive.
            with ProcessPoolExecutor(max_workers=min(workers, len(payloads))) as pool:
                futures = [pool.submit(arbitrate_batch, load) for load in payloads]
                for future in as_completed(futures):
                    note(future.result())
    elapsed = time.perf_counter() - started

    records = read_journal_records(journal)
    with open(out, "w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    by_pass = {}
    for record in records:
        by_pass.setdefault(record["pass_used"], []).append(record)
    print(f"\n  arbitré en {elapsed / 60:.1f} min "
          f"({elapsed * args.workers / max(len(records), 1):.1f} s·cœur par décision)")
    for used in sorted(by_pass):
        part = by_pass[used]
        seconds = sum(r["seconds"] for r in part) / len(part)
        print(f"    passe {used} : {len(part):6d} décisions "
              f"({100 * len(part) / len(records):5.1f} %)  {seconds:7.2f} s·cœur en moyenne")
    states = [state for record in records for state in record.get("resolution", [])]
    if states:
        dominated = states.count("dominated")
        still_open = states.count("open")
        print(f"    candidats seulement bornés (dominés) : {dominated}/{len(states)} "
              f"({100 * dominated / len(states):.1f} %) — leur valeur exacte n'a pas "
              f"été achetée, on sait seulement qu'ils sont pires.")
        print(f"    candidats restés OUVERTS : {still_open}/{len(states)} "
              f"({100 * still_open / len(states):.1f} %) — le plafond d'essais a été "
              f"atteint avant la résolution.")
        if still_open:
            print("      Le plafond est un choix : il borne le coût d'une décision "
                  "pathologique au lieu de laisser un rollout courir des heures. "
                  "Ces candidats portent une valeur, mais son intervalle dépasse la "
                  "résolution visée — et le registre le dit plutôt que de le taire.")
    print(f"\n  registre : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

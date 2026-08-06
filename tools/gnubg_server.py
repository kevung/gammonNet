"""Un serveur d'évaluation, exécuté **dans** GNU Backgammon.

    gnubg --tty --quiet --no-rc -p tools/gnubg_server.py

GNU Backgammon embarque un interpréteur Python 3, et son mode `-p` y exécute ce
fichier. On y a le moteur réel : ses réseaux, ses **bases de fin de partie**, sa
table d'équité de match, et son évaluation **cubeful**. Le script boucle sur son
entrée standard et répond en JSON, de sorte qu'un processus serve des milliers
de requêtes au lieu de payer un démarrage par question.

## Pourquoi ce détour plutôt que `gnubg-nn`

`gnubg-nn` est un binding rapide et en processus, et il reste le bon outil pour
les gros volumes en money au 0-ply. Mais :

* **Il plante à partir du 1-ply sur les positions de bearoff.** Trouvé en T36 :
  segfault reproductible, base de fin de partie unilatérale désactivée ou non.
  Il n'est donc pas utilisable pour une mesure en profondeur.
* **Sa table d'équité de match n'est pas la nôtre** — T32 a mesuré
  `max|Δ| = 2,679e-02` contre Kazaross-XG2, quand une décision de videau se joue
  sur des marges bien inférieures.
* Il n'expose pas d'évaluation cubeful interprétable.

GNU Backgammon lui-même n'a aucun de ces trois défauts, et `PLAN.md` le désigne
déjà comme la référence des mesures qui engagent une conclusion en match ou sur
le videau.

## Ce que ce fichier est, et n'est pas

C'est un **instrument de mesure**, au sens de `CLAUDE.md`. On lit les sorties de
GNU Backgammon ; on ne copie ni son code ni ses poids, et on n'apprend rien de
lui. La FSF est explicite sur le fait que la sortie d'un programme n'est pas, en
général, couverte par le droit d'auteur sur son code.

## Le protocole

Une requête JSON par ligne sur l'entrée ; une réponse par ligne sur la sortie,
**préfixée de `@@`**. Le préfixe n'est pas décoratif : gnubg écrit sa bannière,
ses tableaux de plateau et ses messages sur la même sortie standard, et un
client qui lirait la première ligne venue lirait du copyright.

Le plateau est la convention de gnubg, celle que `gammonnet.gnubg_board` produit
déjà : deux tableaux de 25 entiers positifs, `board[1]` au joueur au trait,
indice 24 la barre.
"""

import json
import sys

import gnubg

_OUT = sys.stdout


def reply(payload):
    _OUT.write("@@" + json.dumps(payload) + "\n")
    _OUT.flush()


def as_board(raw):
    """La conversion en tuples est obligatoire, pas cosmétique.

    L'extension attend des séquences immuables ; une liste de listes venue de
    `json.loads` la fait échouer de façon peu bavarde.
    """
    return (tuple(int(n) for n in raw[0]), tuple(int(n) for n in raw[1]))


def make_cubeinfo(state):
    """Le contexte de videau et de score.

    Sans `state`, la partie d'argent que gnubg tient par défaut. Avec, un score
    de match explicite — c'est ce dont T34 et T35 ont besoin, et c'est la seule
    façon d'obtenir de gnubg une équité de match plutôt qu'une équité money.
    """
    if not state:
        return gnubg.cubeinfo()
    return gnubg.cubeinfo(
        int(state.get("cube", 1)),
        int(state.get("cube_owner", -1)),
        int(state.get("move", 1)),
        int(state.get("match_to", 0)),
        tuple(state.get("score", (0, 0))),
        int(state.get("crawford", 0)),
        int(state.get("jacoby", 0)),
        int(state.get("beavers", 0)),
        int(state.get("bgv", 0)),
    )


def make_context(request):
    """`evalcontext(cubeful, plies, deterministic, prune, noise)`.

    `deterministic=1` toujours : une mesure qui dépendrait d'un bruit interne ne
    serait pas reproductible, et la reproductibilité est un critère de T04.

    `prune` est le réseau d'élagage de gnubg. Il est **désactivé par défaut
    ici** : il change ce que la profondeur signifie, et une comparaison de
    profondeur doit comparer des profondeurs. Le client le demande
    explicitement quand il veut mesurer gnubg tel qu'il joue vraiment.
    """
    return gnubg.evalcontext(
        int(request.get("cubeful", 0)),
        int(request.get("plies", 0)),
        1,
        int(request.get("prune", 0)),
        0.0,
    )


def op_eval(request):
    """Les cinq probabilités et l'équité, pour un plateau ou pour plusieurs.

    Le lot est la raison d'être de cette opération. Une décision de coup pose la
    même question sur une vingtaine de positions résultantes ; un aller-retour
    par position paierait vingt fois la latence du tube pour un seul choix.
    """
    context = make_context(request)
    cubeinfo = make_cubeinfo(request.get("state"))
    boards = request["boards"] if "boards" in request else [request["board"]]
    return {"values": [gnubg.evaluate(as_board(b), cubeinfo, context) for b in boards]}


def op_cfeval(request):
    """L'évaluation **cubeful** et le verdict de videau, tels que gnubg les rend.

    La sortie est renvoyée **non interprétée**. T34 en fixera la sémantique
    contre un corpus de décisions connues ; lui donner un sens ici, à partir
    d'une lecture, serait exactement le genre de supposition que ce dépôt
    refuse.
    """
    context = make_context({**request, "cubeful": 1})
    cubeinfo = make_cubeinfo(request.get("state"))
    boards = request["boards"] if "boards" in request else [request["board"]]
    return {"values": [gnubg.cfevaluate(as_board(b), cubeinfo, context) for b in boards]}


def op_met(request):
    """La table d'équité de match que gnubg tient — le repère de T32."""
    return {"met": gnubg.met(int(request.get("match_to", 25)))}


def op_classify(request):
    """La classe de position de gnubg : over, bearoff, race, crashed, contact.

    `BRIEF.md` §9 avertit qu'un corpus riche en fins de partie flatte un moteur
    qui a des tables exactes et punit celui qui n'en a pas. Une mesure de force
    doit pouvoir dire sur quoi elle a été prise.
    """
    boards = request["boards"] if "boards" in request else [request["board"]]
    return {"classes": [gnubg.classifypos(as_board(b)) for b in boards]}


OPS = {
    "eval": op_eval,
    "cfeval": op_cfeval,
    "met": op_met,
    "classify": op_classify,
}


def main():
    # `new game` amorce l'état interne : sans partie en cours, `cubeinfo()` lève
    # « error in SetCubeInfo » et rien ne fonctionne.
    gnubg.command("new game")
    reply({"ready": True, "python": sys.version.split()[0]})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception as exc:
            reply({"error": f"json illisible : {exc}"})
            continue

        op = request.get("op")
        if op == "quit":
            reply({"bye": True})
            return

        handler = OPS.get(op)
        if handler is None:
            reply({"error": f"opération inconnue : {op!r}"})
            continue

        try:
            reply(handler(request))
        except Exception as exc:
            # Une erreur est rendue au client, jamais avalée : un oracle qui
            # répondrait n'importe quoi plutôt que de dire qu'il a échoué est
            # précisément le mode de défaillance silencieux que ce projet
            # traque.
            reply({"error": f"{type(exc).__name__}: {exc}"})


main()

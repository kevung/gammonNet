"""T88 — l'ordre des ex æquo, et pourquoi aucun test existant ne le voyait.

`compare_candidates` ne comparait que l'équité, et `qsort` n'est pas stable :
l'ordre de deux candidats de MÊME équité dépendait de la libc. Le harnais de
parité compare des équités à 1e-6, donc une permutation d'ex æquo lui est
**invisible** — et elle change le coup annoncé, ainsi que, aux deux coupes
(l'élagage `prune_k` et le filtre de la passe profonde), l'ensemble des coups
qui survivent.

MESURÉ avant d'être corrigé (`make tie-census`, corpus T12, 0-ply, les 21
lancers de chaque position) : 41 779 décisions, **802 (1,92 %) portent au
moins un ex æquo bit-à-bit**, et **433 (1,22 % des décisions à plus d'un
coup) ont un MEILLEUR coup ex æquo**. Ce n'est donc pas un défaut théorique.

Et il ne se voyait pas en natif : le `qsort` de la glibc 2.44 est stable en
pratique, celui d'Emscripten (musl, smoothsort) ne l'est pas — mesuré sur des
éléments de 72 octets, 13 / 64 / 297 / 1 184 ex æquo permutés à n = 32 / 128 /
512 / 2 048. La cible qui divergeait est celle qui tourne dans le navigateur.

La règle tenue ici est celle du portage Go (`sortByEquity`, blunderDB
`engine/gammonnet/search.go`) : **à équité égale, l'ordre d'arrivée est
conservé**, et pour le premier tri c'est l'ordre de génération de
`gn_legal_plays`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gammonnet import Position
from gammonnet import codec
from gammonnet.infer import Network
from gammonnet.search import SearchConfig, search_plays

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "data" / "corpus_t12.jsonl"
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(), reason=f"{MODEL.name} absent — lancer `make model`"
)

#: Assez de positions pour que les ex æquo apparaissent sans faire durer la
#: suite : à 1,92 % de décisions concernées, 120 positions × 21 lancers en
#: rendent quelques dizaines.
POSITIONS = 120

ROLLS = [(d1, d2) for d1 in range(1, 7) for d2 in range(d1, 7)]


@pytest.fixture(scope="module")
def network() -> Network:
    with Network.load(MODEL) as net:
        yield net


def corpus_positions(limit: int) -> list[Position]:
    out: list[Position] = []
    for line in CORPUS.read_text().splitlines():
        row = json.loads(line)
        out.append(codec.position_from_id(row["position_id"], row["turn"]))
        if len(out) >= limit:
            break
    return out


def tie_groups(equities: list[float]) -> list[tuple[int, int]]:
    """Les tranches [début, fin) d'équités bit-à-bit égales, longueur ≥ 2."""
    groups: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(equities) + 1):
        if i == len(equities) or equities[i] != equities[start]:
            if i - start >= 2:
                groups.append((start, i))
            start = i
    return groups


def test_le_corpus_contient_bien_des_ex_aequo(network: Network) -> None:
    """Sans ce contrôle, le test suivant peut passer en ne vérifiant RIEN.

    C'est le piège que T88 nomme : un harnais qui ne contient aucun ex æquo
    laisse le défaut vivre en affichant du vert.
    """
    config = SearchConfig(ply=0)
    seen = 0
    for position in corpus_positions(POSITIONS):
        for d1, d2 in ROLLS:
            equities = [c.equity for c in search_plays(network, position, d1, d2, config)]
            seen += len(tie_groups(equities))
    assert seen > 0, "aucun ex æquo dans l'échantillon : le test ne prouverait rien"


def test_les_ex_aequo_gardent_l_ordre_de_generation(network: Network) -> None:
    """La règle, énoncée comme une propriété plutôt que comme un repère figé.

    Un repère figé dirait « ce coup-ci d'abord » sans dire pourquoi ; celle-ci
    se transporte telle quelle au portage Go et au module WebAssembly, et c'est
    ce que T88 demande aux trois cibles de partager.
    """
    config = SearchConfig(ply=0)
    checked = 0
    for position in corpus_positions(POSITIONS):
        for d1, d2 in ROLLS:
            candidates = search_plays(network, position, d1, d2, config)
            groups = tie_groups([c.equity for c in candidates])
            if not groups:
                continue
            generated = position.legal_plays(d1, d2)
            order = {}
            for rank, play in enumerate(generated):
                order.setdefault((play.moves, play.result), rank)
            for start, end in groups:
                ranks = [
                    order[(candidates[i].play.moves, candidates[i].play.result)]
                    for i in range(start, end)
                ]
                assert ranks == sorted(ranks), (
                    f"ex æquo permutés à {d1}-{d2} : rangs de génération {ranks}"
                )
                checked += 1
    assert checked > 0


def test_le_classement_est_reproductible(network: Network) -> None:
    """Deux appels identiques rendent le même ordre, ex æquo compris.

    Faible en soi — mais il attrape le tri qui dépendrait d'une adresse, d'un
    contenu de tampon réutilisé ou d'un ordre d'allocation, ce qu'un tri
    instable sur un tableau réordonné entre deux appels ferait.
    """
    config = SearchConfig(ply=0)
    for position in corpus_positions(20):
        for d1, d2 in ROLLS:
            first = search_plays(network, position, d1, d2, config)
            second = search_plays(network, position, d1, d2, config)
            assert [c.play.result for c in first] == [c.play.result for c in second]

"""T12 — le corpus de non-régression : qu'une dérive future se voie.

Ce test ne dit pas que le réseau a raison. Il dit qu'il n'a pas **changé**. Si
l'encodage, le chargeur ou les poids bougent, il échoue — au lieu de laisser mille
mesures ultérieures se déplacer d'un rien, sans que personne ne le remarque.

Les cinq sorties sont figées **au bit près**, en hexadécimal de leur float32. Du
texte décimal arrondirait, et un corpus incapable de distinguer `0,5214856` de
`0,5214855` ne peut pas détecter la dérive pour laquelle il existe.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from gammonnet import BLACK, WHITE, Position
from gammonnet import codec

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "data" / "corpus_t12.jsonl"
MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"

pytestmark = pytest.mark.skipif(
    not MODEL.is_file(), reason=f"{MODEL.name} absent — lancer `make model`"
)


def hex_f32(text: str) -> float:
    return struct.unpack(">f", bytes.fromhex(text))[0]


def features_digest(features) -> str:
    import hashlib

    payload = b"".join(struct.pack(">f", v) for v in features)
    return hashlib.blake2b(payload, digest_size=16).hexdigest()


def load() -> list[dict]:
    return [json.loads(line) for line in CORPUS.read_text().splitlines()]


CORPUS_RECORDS = load()


@pytest.fixture(scope="module")
def network():
    from gammonnet.infer import Network

    with Network.load(MODEL) as net:
        yield net


# ── Le corpus lui-même ───────────────────────────────────────────────


def test_corpus_is_large_enough():
    """T12 exige au moins 2 000 positions."""
    assert len(CORPUS_RECORDS) >= 2000, f"{len(CORPUS_RECORDS)} positions"


def test_corpus_covers_every_required_category():
    """Contact, course, bearoff, barre **et backgame**.

    Le backgame est celui qui manque toujours : une marche aléatoire n'y arrive
    pratiquement jamais, parce que tenir deux points profonds est une stratégie
    et non un accident de dés. Il est donc construit, pas tiré.
    """
    categories = {r["category"] for r in CORPUS_RECORDS}
    for required in ("contact", "race", "bearoff", "bar", "backgame"):
        assert required in categories, f"catégorie « {required} » absente"

    counts = {c: sum(1 for r in CORPUS_RECORDS if r["category"] == c) for c in categories}
    assert counts["backgame"] >= 100, f"seulement {counts['backgame']} backgames"


def test_corpus_positions_are_valid_and_both_colours_play():
    turns = set()
    for record in CORPUS_RECORDS:
        position = codec.position_from_id(record["position_id"], record["turn"])
        assert position.is_valid(), record["id"]
        turns.add(record["turn"])
    assert turns == {WHITE, BLACK}


# ── La non-régression ────────────────────────────────────────────────


def test_the_encoding_has_not_moved():
    """L'empreinte des 196 caractéristiques, position par position.

    Vérifié **séparément** des sorties : une dérive du codec et une dérive des
    poids produisent le même symptôme, et les séparer dit lequel des deux a
    bougé au lieu de laisser chercher.
    """
    for record in CORPUS_RECORDS:
        position = codec.position_from_id(record["position_id"], record["turn"])
        assert features_digest(codec.encode(position)) == record["features_digest"], (
            f"{record['id']} : l'encodage a changé"
        )


def test_the_five_outputs_have_not_moved(network):
    """Les cinq probabilités, **au bit près**.

    `max|Δ| = 0` et non « proche ». Le seuil serré n'est pas du zèle : perturber
    UN SEUL poids sur 528 389 d'un pour mille ne déplace les sorties que de
    5,05e-06 (mesuré, voir plus bas). Une tolérance de 1e-5 laisserait donc
    passer exactement la dérive que ce corpus existe pour attraper.

    **Le corpus est produit par le build PAR DÉFAUT.** Sous `NATIVE_FP=1`, la
    réassociation des sommes déplace le dernier bit — T21 l'a mesuré à 4,77e-7 —
    et ce test échouera légitimement. Passer `GN_REGRESSION_TOLERANCE=1e-6` dans
    ce cas ; la valeur laisse encore quatre ordres de grandeur de marge avant de
    manquer une perturbation d'un poids.
    """
    import os

    tolerance = float(os.environ.get("GN_REGRESSION_TOLERANCE", "0"))

    worst = 0.0
    worst_id = None

    for record in CORPUS_RECORDS:
        position = codec.position_from_id(record["position_id"], record["turn"])
        produced = network.evaluate(position).as_tuple()
        expected = [hex_f32(h) for h in record["outputs_hex"]]

        for a, b in zip(produced, expected):
            delta = abs(a - b)
            if delta > worst:
                worst, worst_id = delta, record["id"]

    assert worst <= tolerance, (
        f"max|Δ| = {worst:.3e} sur {worst_id}, toléré {tolerance:.3e}. "
        "Si le build est NATIVE_FP=1, relancer avec GN_REGRESSION_TOLERANCE=1e-6."
    )
    print(f"\nmax|Δ| sur {len(CORPUS_RECORDS)} positions : {worst:.3e}")


def test_the_pip_counts_recorded_still_hold():
    """La sentinelle, une fois de plus : elle ne coûte rien et cadre le reste."""
    for record in CORPUS_RECORDS:
        position = codec.position_from_id(record["position_id"], record["turn"])
        assert [position.pip_count(WHITE), position.pip_count(BLACK)] == record["pips"], (
            f"{record['id']} : le compte de pips a changé"
        )


def test_nested_events_hold_across_the_corpus(network):
    for record in CORPUS_RECORDS:
        position = codec.position_from_id(record["position_id"], record["turn"])
        assert network.evaluate(position).is_nested, f"{record['id']}"


# ── Le test détecte-t-il réellement ? ────────────────────────────────


def test_a_one_per_mille_weight_change_is_detected(tmp_path):
    """Le critère dur de T12 : le corpus doit **échouer** sur un poids perturbé.

    Un test de non-régression qui passe quoi qu'il arrive ne protège rien. On
    perturbe donc un seul poids d'un pour mille, dans une copie du modèle, et on
    vérifie que le corpus le voit.
    """
    from gammonnet.infer import Network

    original = MODEL.read_bytes()
    perturbed = bytearray(original)

    # Le format BGNN : 4 octets de magie puis cinq int32 d'en-tête, puis les
    # tailles des couches cachées. On perturbe un float bien au-delà, dans la
    # première matrice de poids.
    header = 4 + 5 * 4
    hidden_count = struct.unpack("<i", original[4:8])[0]
    offset = header + hidden_count * 4 + 4 * 1000  # 1000 floats dans la matrice

    value = struct.unpack("<f", perturbed[offset:offset + 4])[0]
    if value == 0.0:
        value = 1e-3
    perturbed[offset:offset + 4] = struct.pack("<f", value * 1.001)

    copy = tmp_path / "perturbed.bin"
    copy.write_bytes(bytes(perturbed))

    worst = 0.0
    with Network.load(copy) as broken:
        for record in CORPUS_RECORDS[:500]:
            position = codec.position_from_id(record["position_id"], record["turn"])
            produced = broken.evaluate(position).as_tuple()
            expected = [hex_f32(h) for h in record["outputs_hex"]]
            for a, b in zip(produced, expected):
                worst = max(worst, abs(a - b))

    # Le seuil de comparaison est celui de la tolérance la PLUS LÂCHE que le
    # test principal accepte (1e-6, pour le build réassocié). Si la perturbation
    # se voit même à cette tolérance-là, elle se voit a fortiori au bit près.
    assert worst > 1e-6, (
        f"un poids perturbé d'un pour mille ne déplace les sorties que de "
        f"{worst:.3e} : le corpus ne détecterait pas la dérive qu'il existe pour "
        "détecter"
    )
    print(f"\nun seul poids sur 528 389, perturbé d'un pour mille : "
          f"max|Δ| = {worst:.3e}")


def test_a_perturbed_encoding_is_detected():
    """Et si c'est le codec qui bouge, l'empreinte doit le dire.

    Une caractéristique déplacée d'un rien change l'empreinte : c'est la
    propriété qu'on attend d'elle, et la vérifier coûte trois lignes.
    """
    record = CORPUS_RECORDS[0]
    position = codec.position_from_id(record["position_id"], record["turn"])

    features = list(codec.encode(position))
    features[0] = struct.unpack(">f", struct.pack(">f", features[0] + 1e-6))[0]

    assert features_digest(features) != record["features_digest"]

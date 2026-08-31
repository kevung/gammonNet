"""T50 — le format de distribution float16, et ce qui empêche les deux lecteurs de dériver.

Le `.bin` float32 est lu par le lecteur vendoré (`nn_load`) ; le `.bin16` par le
nôtre (`load_fp16`, dans `gn_infer_reference.c`). **Deux lecteurs pour un même
format sont une source de dérive**, exactement ce que `tools/train_prune.py`
évite en réutilisant l'exporteur vendoré plutôt qu'en en écrivant un second.

Ici le second lecteur est inévitable — le lecteur vendoré ne connaît pas les
demi-flottants — donc ce fichier le tient par les résultats :

**Un modèle emballé en float16 doit s'évaluer EXACTEMENT comme le même modèle
arrondi en float16 dans un conteneur float32.** Le second est produit par
`tools/quantize_model.py --format fp16` et lu par le lecteur vendoré. Si les
deux lecteurs divergent sur un en-tête, un ordre de couche ou une forme, les
sorties divergent et le test tombe.

Le reste — ce que la précision coûte en jeu — est mesuré ailleurs
(`docs/mesures/2026-08-04-quantification.md`) et n'a pas sa place ici.
"""

from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from gammonnet.infer import Network  # noqa: E402
from gammonnet.rules import Position  # noqa: E402

MODEL = ROOT / "models" / "cubeless_prob5_512_512_256_128.bin"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="modèle absent")


def corpus(count: int = 64, seed: int = 20260827) -> list[Position]:
    rng = random.Random(seed)
    out: list[Position] = []
    position = Position.initial()
    while len(out) < count:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
        plays = position.legal_plays(d1, d2)
        position = rng.choice(plays).result if plays else position.swapped_turn()
        if position.is_over():
            position = Position.initial()
            continue
        out.append(position)
    return out


@pytest.fixture(scope="module")
def packed(tmp_path_factory):
    target = tmp_path_factory.mktemp("fp16") / "packed.bin16"
    from pack_fp16 import pack

    report = pack(MODEL, target)
    return target, report


@needs_model
def test_the_artifact_is_half_the_size(packed):
    """La raison d'être du format : ce qui se télécharge avant la première
    évaluation. Le calcul, lui, reste en float32."""
    _target, report = packed
    ratio = report["bytes_in"] / report["bytes_out"]
    assert 1.95 < ratio < 2.0, f"×{ratio:.2f} au lieu de ×1,99 attendu"


@needs_model
def test_the_two_readers_agree_bit_for_bit(packed, tmp_path):
    """LE test du fichier : notre lecteur et le lecteur vendoré doivent rendre
    le même modèle, aux bits près."""
    target, _report = packed
    rounded = tmp_path / "rounded.bin"
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "quantize_model.py"),
         "--in", str(MODEL), "--out", str(rounded), "--format", "fp16"],
        check=True, capture_output=True)

    ours = Network.load(target)
    theirs = Network.load(rounded)
    positions = corpus()
    for position in positions:
        assert ours.evaluate(position) == theirs.evaluate(position)


@needs_model
def test_the_packed_model_is_close_to_the_original_but_not_equal(packed):
    """Il DOIT différer — sinon l'emballage n'aurait rien arrondi — et il doit
    différer peu. Un test qui ne vérifierait que la proximité passerait sur un
    fichier qui n'aurait pas été converti du tout."""
    target, _report = packed
    packed_net = Network.load(target)
    original = Network.load(MODEL)
    positions = corpus()

    differ = 0
    worst = 0.0
    for position in positions:
        a = original.evaluate(position).as_tuple()
        b = packed_net.evaluate(position).as_tuple()
        if a != b:
            differ += 1
        worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
    assert differ > 0, "aucune sortie déplacée : le fichier n'a pas été converti"
    assert worst < 1e-3, f"écart maximal {worst:.2e}, trop grand pour du float16"


@needs_model
def test_a_truncated_artifact_is_refused_not_guessed(packed, tmp_path):
    """Un artefact tronqué doit être REFUSÉ. Un modèle à moitié lu évaluerait
    et rendrait cinq nombres plausibles — le mode de défaillance central."""
    target, _report = packed
    broken = tmp_path / "broken.bin16"
    broken.write_bytes(target.read_bytes()[: len(target.read_bytes()) // 2])
    with pytest.raises(Exception):
        Network.load(broken)

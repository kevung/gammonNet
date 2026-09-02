"""T73 — l'export QAT et l'inférence int8 réelle : le format, et sa fidélité
à ce que la QAT a entraîné.

Un réseau minuscule (pas le réseau embarqué : 196→8→4→5 ici), quantifié,
exporté, chargé, exécuté par le VRAI noyau C (`Int8Network.forward`, via
`gn_gemm_int8_relu_pc`). Le test décisif n'est pas que ça tourne : c'est que
la sortie colle à ce que la simulation PyTorch de la QAT elle-même prédit —
sinon l'export ment sur ce que le déploiement calcule.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from gammonnet.infer_int8 import Int8Network  # noqa: E402
from gammonnet.qat import QuantizedProb5, calibrate_activation_scales  # noqa: E402
from export_qat_int8 import write_int8_model  # noqa: E402

needs_lib = pytest.mark.skipif(
    not (ROOT / "build" / "libgammonnet.so").exists(),
    reason="bibliothèque native absente — `make build`")


def _tiny_model_and_scales(seed: int = 0):
    torch.manual_seed(seed)
    model = QuantizedProb5(hidden_sizes=(8, 4), input_size=16)
    model.eval()
    samples = torch.rand(64, 16) * 3.0
    scales = calibrate_activation_scales(model, samples)
    model.input_quant.scale = scales[0]
    for module, scale in zip([m for m in model.trunk if hasattr(m, "scale")],
                             scales[1:]):
        module.scale = scale
    return model, scales


@needs_lib
def test_the_exported_format_round_trips():
    model, scales = _tiny_model_and_scales()
    buffer = io.BytesIO()
    write_int8_model(buffer, model, hidden_sizes=[8, 4], input_size=16,
                     input_scale=scales[0], output_scales=scales[1:])

    path = ROOT / "build" / "test_infer_int8_tmp.bin"
    path.write_bytes(buffer.getvalue())
    try:
        net = Int8Network.load(path)
    finally:
        path.unlink(missing_ok=True)

    assert net.input_size == 16
    assert net.hidden_sizes == [8, 4]
    assert net.input_scale == scales[0]
    assert net.output_scales == scales[1:]
    assert len(net.layers) == 2
    assert net.layers[0].rows == 8 and net.layers[0].cols == 16
    assert net.layers[1].rows == 4 and net.layers[1].cols == 8
    assert net.head_weight.shape == (5, 4)


@needs_lib
def test_a_wrong_magic_is_refused():
    path = ROOT / "build" / "test_infer_int8_bad_magic.bin"
    path.write_bytes(b"XXXX" + b"\x00" * 60)
    try:
        with pytest.raises(ValueError, match="magic"):
            Int8Network.load(path)
    finally:
        path.unlink(missing_ok=True)


@needs_lib
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_the_c_kernel_matches_the_qat_simulation(seed):
    """The test that matters: `Int8Network.forward` (the real C kernel,
    `gn_gemm_int8_relu_pc`) against `QuantizedProb5.forward` (what training
    optimised for) on the SAME inputs. A wide gap here would mean the export
    -- or the kernel, or the training simulation -- computes something other
    than what the other two agree on; that mismatch, closed on 2026-08-31 by
    matching `floor_ste` to the kernel's `>> shift`, is exactly what this
    guards against regressing.
    """
    model, scales = _tiny_model_and_scales(seed=seed)
    buffer = io.BytesIO()
    write_int8_model(buffer, model, hidden_sizes=[8, 4], input_size=16,
                     input_scale=scales[0], output_scales=scales[1:])
    path = ROOT / "build" / f"test_infer_int8_tmp_{seed}.bin"
    path.write_bytes(buffer.getvalue())
    try:
        net = Int8Network.load(path)
    finally:
        path.unlink(missing_ok=True)

    rng = torch.Generator().manual_seed(seed + 100)
    features = torch.rand(20, 16, generator=rng) * 3.0
    with torch.no_grad():
        torch_out = model(features).numpy()

    for i in range(len(features)):
        c_out = np.array(net.forward(features[i].tolist()))
        # Loose bound: this is int8 on an 8/4-wide toy network (little
        # headroom to average noise away), not the embedded network's
        # 512-wide layers. The regression this guards against was ~0.06 max
        # / 0.017 mean on the REAL network before the floor fix -- an order
        # of magnitude looser bound here still catches that class of bug.
        assert np.abs(c_out - torch_out[i]).max() < 0.15


@needs_lib
def test_forward_refuses_the_wrong_feature_count():
    model, scales = _tiny_model_and_scales()
    buffer = io.BytesIO()
    write_int8_model(buffer, model, hidden_sizes=[8, 4], input_size=16,
                     input_scale=scales[0], output_scales=scales[1:])
    path = ROOT / "build" / "test_infer_int8_tmp_refuse.bin"
    path.write_bytes(buffer.getvalue())
    try:
        net = Int8Network.load(path)
    finally:
        path.unlink(missing_ok=True)

    with pytest.raises(ValueError):
        net.forward([0.0] * 10)


def _load_tmp_net(model, scales, name: str) -> Int8Network:
    buffer = io.BytesIO()
    write_int8_model(buffer, model, hidden_sizes=[8, 4], input_size=16,
                     input_scale=scales[0], output_scales=scales[1:])
    path = ROOT / "build" / f"test_infer_int8_{name}.bin"
    path.write_bytes(buffer.getvalue())
    try:
        return Int8Network.load(path)
    finally:
        path.unlink(missing_ok=True)


@needs_lib
def test_forward_batch_matches_forward_bit_for_bit():
    """The whole point of `forward_batch`
    (`docs/mesures/2026-08-31-T73-int8-debit-taille.md`: `forward` loses to
    float32 at batch=1, ×0,22 measured) is speed, not a different answer —
    it must render EXACTLY what N calls to `forward` would, not merely
    something close."""
    model, scales = _tiny_model_and_scales()
    net = _load_tmp_net(model, scales, "batch_match")

    rng = torch.Generator().manual_seed(7)
    features = (torch.rand(15, 16, generator=rng) * 3.0).tolist()

    individually = [net.forward(f) for f in features]
    batched = net.forward_batch(features)

    assert len(batched) == len(individually)
    for single, together in zip(individually, batched):
        assert single == together


@needs_lib
def test_forward_batch_handles_a_single_candidate_and_an_empty_batch():
    model, scales = _tiny_model_and_scales()
    net = _load_tmp_net(model, scales, "batch_edges")

    assert net.forward_batch([]) == []

    features = torch.rand(16).tolist()
    assert net.forward_batch([features]) == [net.forward(features)]


@needs_lib
def test_forward_batch_refuses_more_than_the_kernels_accumulator_holds():
    from gammonnet.infer_int8 import MAX_BATCH

    model, scales = _tiny_model_and_scales()
    net = _load_tmp_net(model, scales, "batch_overflow")

    features = torch.rand(16).tolist()
    with pytest.raises(ValueError):
        net.forward_batch([features] * (MAX_BATCH + 1))

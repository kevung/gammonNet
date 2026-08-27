"""T73 — la QAT : le gradient passe, la grille tient, l'architecture est refusée.

Trois propriétés, et chacune échoue en silence si elle cède :

- le **straight-through estimator** doit laisser passer un gradient. S'il ne le
  fait pas, l'entraînement tourne sans rien apprendre et rend un réseau plausible
  qui n'a pas bougé.
- les poids vus par le produit matriciel doivent être des **entiers sur une
  grille de puissance de deux**. Sinon la QAT simule une quantification qui n'est
  pas celle que le noyau C exécutera, et le réseau apprend à survivre au mauvais
  arrondi.
- une couche que le noyau refuserait doit être refusée **ici**, pas après des
  heures de GPU.
"""

from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")

from gammonnet.qat import (  # noqa: E402
    ClippedReLU,
    QuantizedLinear,
    QuantizedProb5,
    calibrate_activation_scale,
    power_of_two_scale,
    round_ste,
)
from gammonnet.quantization import ACTIVATION_MAX, WEIGHT_MAX  # noqa: E402


def test_the_ste_rounds_forward():
    x = torch.tensor([0.4, 0.6, -1.2, 2.5])
    assert torch.equal(round_ste(x), torch.round(x))


def test_the_ste_passes_the_gradient_through_unchanged():
    """`round` a une dérivée nulle presque partout : sans le STE, le gradient
    serait nul et l'entraînement ne bougerait pas d'un poids."""
    x = torch.tensor([0.4, 1.6, -2.3], requires_grad=True)
    round_ste(x).sum().backward()
    assert torch.equal(x.grad, torch.ones_like(x))


def test_a_plain_round_would_have_killed_the_gradient():
    """Le contre-exemple, pour que la raison d'être du STE soit dans le test."""
    x = torch.tensor([0.4, 1.6, -2.3], requires_grad=True)
    torch.round(x).sum().backward()
    assert torch.equal(x.grad, torch.zeros_like(x))


def test_the_weights_seen_by_the_matmul_live_on_a_power_of_two_grid():
    layer = QuantizedLinear(16, 4)
    integers, scale = layer.quantized_weight()
    assert torch.equal(integers, torch.round(integers))
    assert integers.abs().max() <= WEIGHT_MAX
    for value in scale.flatten().tolist():
        assert math.log2(value) == int(math.log2(value))


def test_the_scale_is_per_channel():
    """Deux lignes d'amplitudes très différentes doivent recevoir deux échelles."""
    layer = QuantizedLinear(8, 2)
    with torch.no_grad():
        layer.linear.weight[0].fill_(0.001)
        layer.linear.weight[1].fill_(10.0)
    _integers, scale = layer.quantized_weight()
    assert scale[0].item() != scale[1].item()


def test_a_layer_the_c_kernel_would_refuse_is_refused_here():
    with pytest.raises(ValueError, match="déborderait"):
        QuantizedLinear(200_000, 4)


def test_the_clipped_relu_clips_and_snaps_to_its_grid():
    activation = ClippedReLU(scale=1.0 / 64.0)
    x = torch.tensor([-3.0, 0.0, 0.5, 1000.0])
    y = activation(x)
    assert y[0].item() == 0.0
    assert y[1].item() == 0.0
    assert y[3].item() == pytest.approx(ACTIVATION_MAX / 64.0)
    # Chaque sortie est un multiple entier de l'échelle.
    for value in y.tolist():
        assert (value * 64.0) == pytest.approx(round(value * 64.0))


def test_the_network_produces_five_probabilities():
    net = QuantizedProb5()
    y = net(torch.rand(4, 196))
    assert y.shape == (4, 5)
    assert bool((y >= 0).all() and (y <= 1).all())


def test_the_network_actually_trains():
    """Une descente sur quelques pas doit faire baisser la perte. Un réseau
    quantifié dont le gradient serait coupé passerait tous les tests de forme
    et n'apprendrait rien."""
    torch.manual_seed(0)
    net = QuantizedProb5(hidden_sizes=(32, 16))
    x = torch.rand(64, 196)
    target = torch.rand(64, 5)
    optimiser = torch.optim.Adam(net.parameters(), lr=1e-2)
    first = last = None
    for step in range(30):
        optimiser.zero_grad()
        loss = torch.nn.functional.mse_loss(net(x), target)
        loss.backward()
        optimiser.step()
        if step == 0:
            first = loss.item()
        last = loss.item()
    assert last < first, f"la perte n'a pas baissé : {first} → {last}"


def test_float_weights_load_into_the_quantized_shape():
    from torch import nn

    float_net = nn.Module()
    float_net.trunk = nn.Sequential(nn.Linear(196, 32), nn.ReLU(),
                                    nn.Linear(32, 16), nn.ReLU())
    float_net.head = nn.Linear(16, 5)
    state = float_net.state_dict()

    net = QuantizedProb5(hidden_sizes=(32, 16))
    net.load_float_weights(state)
    assert torch.equal(net.trunk[0].linear.weight, state["trunk.0.weight"])
    assert torch.equal(net.head.bias, state["head.bias"])


def test_a_mismatched_architecture_is_refused():
    from torch import nn

    float_net = nn.Module()
    float_net.trunk = nn.Sequential(nn.Linear(196, 32), nn.ReLU())
    float_net.head = nn.Linear(32, 5)
    net = QuantizedProb5(hidden_sizes=(32, 16))
    with pytest.raises(ValueError, match="ne correspondent pas"):
        net.load_float_weights(float_net.state_dict())


def test_the_calibrated_activation_scale_is_a_power_of_two():
    net = QuantizedProb5(hidden_sizes=(32, 16))
    scale = calibrate_activation_scale(net, torch.rand(64, 196))
    assert math.log2(scale) == int(math.log2(scale))


def test_the_scale_helper_never_saturates():
    maximum = torch.tensor([[0.003], [1.7], [96.0]])
    scale = power_of_two_scale(maximum, WEIGHT_MAX)
    assert bool((maximum / scale <= WEIGHT_MAX + 1e-6).all())

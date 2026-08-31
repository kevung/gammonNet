"""T73 — l'entraînement conscient de la quantification, en PyTorch.

## Pourquoi QAT et non PTQ

La mesure du 2026-08-04 a tranché la question : quantifier les poids **après**
l'entraînement (PTQ) change 4,92 % des coups et coûte ~12 % de tout l'avantage
du modèle. Ce n'est pas une imprécision négligeable, c'est deux fois la largeur
de l'intervalle de confiance d'un round-robin d'un million de parties.

La QAT retourne le problème : l'arrondi est présent **pendant** l'apprentissage,
donc le réseau apprend des poids qui survivent à l'arrondi, au lieu de subir
l'arrondi de poids qui n'y étaient pas préparés.

## Le straight-through estimator, et ce qu'il cache

`round()` a une dérivée nulle presque partout : rétropropager à travers lui
donnerait un gradient nul et aucun apprentissage. Le STE remplace cette dérivée
par l'identité — on quantifie à l'aller, on passe le gradient tel quel au
retour. C'est un mensonge assumé sur la dérivée, et c'est la technique standard ;
ce qu'il faut en retenir est que le gradient qui arrive aux poids n'est pas
celui de la fonction réellement calculée, ce qui rend la QAT plus lente à
converger qu'un entraînement flottant, et sensible au taux d'apprentissage.

## Ce que ce module ne décide pas

Il ne décide pas si int8 vaut la peine — c'est `bench/bench_gemm_int8.c` qui le
dit, avec le seuil d'abandon de DS-09, et il doit avoir parlé AVANT qu'on
dépense une heure de GPU ici.
"""

from __future__ import annotations

import math

import torch
from torch import nn

from .quantization import ACTIVATION_MAX, WEIGHT_MAX, accumulator_headroom


class _RoundStraightThrough(torch.autograd.Function):
    """`round` à l'aller, identité au retour."""

    @staticmethod
    def forward(ctx, x):
        return torch.round(x)

    @staticmethod
    def backward(ctx, grad):
        return grad


def round_ste(x: torch.Tensor) -> torch.Tensor:
    return _RoundStraightThrough.apply(x)


class _FloorStraightThrough(torch.autograd.Function):
    """`floor` à l'aller, identité au retour.

    `gn_gemm_int8_relu[_pc]` requantifie par un décalage arithmétique pur
    (`accumulateur >> shift`), délibérément SANS terme d'arrondi — le
    commentaire du noyau C le dit : « a rounding multiply here would be the
    one place the two targets could disagree ; a shift cannot ». Un décalage
    arithmétique est un PLANCHER, pas un arrondi au plus proche. Simuler
    l'activation avec `round_ste` pendant l'entraînement — ce que faisait ce
    module jusqu'au 2026-08-31 — apprend donc des poids optimisés pour une
    quantification que le noyau ne fait pas : un biais systématique vers le
    bas, qui s'accumule couche après couche (mesuré : diff moyenne 0,015 à la
    couche 0, 0,62 à la couche 3, sur un réseau à quatre couches cachées).
    """

    @staticmethod
    def forward(ctx, x):
        return torch.floor(x)

    @staticmethod
    def backward(ctx, grad):
        return grad


def floor_ste(x: torch.Tensor) -> torch.Tensor:
    return _FloorStraightThrough.apply(x)


def power_of_two_scale(maximum: torch.Tensor, levels: int) -> torch.Tensor:
    """L'échelle `2^k` la plus fine qui ne sature pas, par canal.

    Calculée en tenseur pour rester sur le GPU et différentiable-compatible :
    l'échelle elle-même est détachée du graphe — elle est une propriété du
    tenseur, pas un paramètre qu'on apprend. L'apprendre reviendrait à laisser
    le réseau choisir de saturer.
    """
    safe = torch.clamp(maximum, min=1e-12)
    exponent = torch.ceil(torch.log2(safe / levels))
    return torch.pow(2.0, exponent).detach()


class QuantizedLinear(nn.Module):
    """Une couche linéaire dont les poids sont arrondis en int8 par canal.

    Les poids restent des flottants dans l'optimiseur — c'est ce qui permet aux
    petites mises à jour de s'accumuler jusqu'à faire basculer un arrondi. Seule
    la valeur VUE par le produit matriciel est quantifiée.
    """

    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        if accumulator_headroom(in_features) < 1.0:
            # Refusé ici plutôt qu'à l'exportation : découvrir après des heures
            # de GPU que le noyau C refuse l'architecture serait une perte
            # entièrement évitable.
            raise ValueError(
                f"{in_features} entrées : l'accumulateur int32 déborderait "
                f"(marge {accumulator_headroom(in_features):.3f} < 1). "
                f"Le noyau C refuserait cette couche.")
        self.linear = nn.Linear(in_features, out_features)

    def quantized_weight(self) -> tuple[torch.Tensor, torch.Tensor]:
        weight = self.linear.weight
        maximum = weight.abs().amax(dim=1, keepdim=True)
        scale = power_of_two_scale(maximum, WEIGHT_MAX)
        integers = torch.clamp(round_ste(weight / scale), -WEIGHT_MAX, WEIGHT_MAX)
        return integers, scale

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        integers, scale = self.quantized_weight()
        return nn.functional.linear(x, integers * scale, self.linear.bias)


class ClippedReLU(nn.Module):
    """`min(max(x, 0), ceiling)`, avec l'arrondi de l'activation.

    Le plafond n'est pas cosmétique : il change ce que le réseau peut
    représenter, donc un réseau entraîné en ReLU puis plafonné n'est PAS le même
    réseau. C'est toute la raison d'être de ce module.

    `ceiling` est en unités de l'activation quantifiée. À l'exécution les
    activations sont des entiers de 0 à 127 ; ici on simule leur grille sans
    quitter le flottant, pour que le gradient continue de circuler.

    `floor_ste`, pas `round_ste` : le noyau C requantifie par un décalage
    arithmétique pur (`>> shift`), un PLANCHER, jamais un arrondi au plus
    proche — voir la docstring de `_FloorStraightThrough`. Simuler l'autre
    arrondi ici entraînerait des poids optimisés pour une arithmétique que le
    déploiement n'exécute pas.
    """

    def __init__(self, levels: int = ACTIVATION_MAX, scale: float = 1.0 / 64.0):
        super().__init__()
        self.levels = levels
        self.scale = scale

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        clamped = torch.clamp(x, min=0.0, max=self.levels * self.scale)
        return floor_ste(clamped / self.scale) * self.scale

    def extra_repr(self) -> str:
        return f"levels={self.levels}, scale={self.scale}"


class QuantizedProb5(nn.Module):
    """L'architecture du réseau embarqué, en version quantifiée.

    Même forme que `ProbNetwork` du dépôt de référence (196 → … → 5, cinq
    sigmoïdes emboîtées), ReLU remplacée par ClippedReLU, chaque linéaire
    quantifiée. La tête reste en flottant : cinq valeurs par position, c'est le
    seul endroit du chemin où un flottant ne coûte rien, et les probabilités
    demandent une dynamique que 8 bits ne donnent pas.
    """

    def __init__(self, hidden_sizes=(512, 512, 256, 128), input_size: int = 196,
                 activation_scale: float = 1.0 / 64.0):
        super().__init__()
        # The deployed C kernel (`gn_gemm_int8_relu_pc`) takes uint8 input --
        # there is no float entry point. Simulating that grid on the RAW
        # features here, not just between hidden layers, is what makes
        # `forward()` a faithful rehearsal of what deployment will compute;
        # omitting it trains a network for an input precision the kernel
        # never gets to use (found 2026-08-31, comparing an export against
        # the real kernel: a mean gap of ~0.016 on the five probabilities
        # that this one line removes).
        self.input_quant = ClippedReLU(scale=activation_scale)
        layers = []
        previous = input_size
        for size in hidden_sizes:
            layers.append(QuantizedLinear(previous, size))
            layers.append(ClippedReLU(scale=activation_scale))
            previous = size
        self.trunk = nn.Sequential(*layers)
        self.head = nn.Linear(previous, 5)
        self.hidden_sizes = list(hidden_sizes)
        self.input_size = input_size
        self.activation_scale = activation_scale

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.head(self.trunk(self.input_quant(x))))

    def load_float_weights(self, state: dict) -> None:
        """Amorce depuis le réseau flottant : les poids, tels quels.

        Le warm-start est utile ICI, contrairement à ce que DS-06 dit de
        l'entraînement pour la recherche : on ne cherche pas un réseau
        différent, on cherche le MÊME réseau exprimé sur une grille plus
        grossière. Partir de ses poids est le meilleur point de départ connu.
        """
        quantized = [m for m in self.trunk if isinstance(m, QuantizedLinear)]
        floats = [key for key in state if key.startswith("trunk.") and key.endswith(".weight")]
        floats.sort(key=lambda key: int(key.split(".")[1]))
        biases = [key.replace(".weight", ".bias") for key in floats]
        if len(floats) != len(quantized):
            raise ValueError(
                f"{len(floats)} couches flottantes contre {len(quantized)} "
                f"quantifiées — les architectures ne correspondent pas.")
        for layer, weight_key, bias_key in zip(quantized, floats, biases):
            layer.linear.weight.data.copy_(state[weight_key])
            layer.linear.bias.data.copy_(state[bias_key])
        self.head.weight.data.copy_(state["head.weight"])
        self.head.bias.data.copy_(state["head.bias"])


def calibrate_activation_scales(model: nn.Module, samples: torch.Tensor,
                                levels: int = ACTIVATION_MAX) -> list[float]:
    """Une échelle `2^-k` PAR COUCHE, calibrée séquentiellement.

    Une échelle UNIQUE calibrée en un seul aller — la première version de
    cette fonction — se contamine elle-même : chaque `ClippedReLU` du tronc
    porte encore l'échelle par défaut du CONSTRUCTEUR (1/64, plafond ≈ 2,0)
    tant que l'appelant ne l'a pas remplacée, donc la couche 2 est mesurée sur
    une sortie de couche 1 déjà écrêtée à un plafond arbitraire — et l'échelle
    unique qui en sort sous-estime toute couche plus profonde que celle qui a
    fixé le maximum. Mesuré (2026-08-31, `docs/mesures/2026-08-31-T73-qat-echelle-diagnostic.md`) :
    sur le réseau embarqué, la dernière couche cachée atteint 52,75 avant
    quantification quand l'échelle unique alors choisie (2^-3) ne couvre que
    127 × 2^-3 ≈ 15,9 — un facteur ~3,3 de saturation, dans la couche la plus
    proche de la sortie.

    Ici chaque couche est calibrée sur la sortie RÉELLEMENT vue par la
    suivante : son propre maximum devient son échelle, appliquée (écrêtage ET
    arrondi comme à l'exécution) avant de mesurer la couche d'après. C'est la
    même chaîne que `ClippedReLU.forward`, rejouée à l'avance.

    `scales[0]` est l'échelle de `model.input_quant` (les caractéristiques
    BRUTES, avant toute couche) ; `scales[1:]` sont celles des couches
    cachées, une par `ClippedReLU` du tronc, dans l'ordre.
    """
    model.eval()
    scales: list[float] = []
    with torch.no_grad():
        maximum = float(samples.clamp(min=0).max())
        input_scale = (1.0 / 64.0 if maximum <= 0.0
                       else 2.0 ** math.ceil(math.log2(maximum / levels)))
        scales.append(input_scale)
        model.input_quant.scale = input_scale
        activations = model.input_quant(samples)

        for module in model.trunk:
            if isinstance(module, QuantizedLinear):
                integers, weight_scale = module.quantized_weight()
                activations = nn.functional.linear(
                    activations, integers * weight_scale, module.linear.bias)
                maximum = float(activations.clamp(min=0).max())
                scale = (1.0 / 64.0 if maximum <= 0.0
                         else 2.0 ** math.ceil(math.log2(maximum / levels)))
                scales.append(scale)
            else:
                module.scale = scales[-1]
                activations = module(activations)
    return scales

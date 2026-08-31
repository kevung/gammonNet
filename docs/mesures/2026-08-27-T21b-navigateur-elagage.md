# T21b — l'élagage dans le navigateur : ×3,65, et un match en 74 secondes

**Date** : 2026-08-27 · **Machine de mesure** : `melbaa`, 28 cœurs, charge 1,5 · **Navigateur** :
Firefox 154.0, headless, build SIMD

> **La question, posée le matin même.** Tous les gains de vitesse d'août viennent du remplissage
> des lots. Le lot rend **×2,21** dans un navigateur contre **×8,5** en natif — le gain devait donc
> y être plus faible, et de combien, personne ne le savait. La fiche du matin refusait de le
> calculer : *« ce serait exactement l'extrapolation que la règle 3 interdit »*.
>
> **La réponse : ×3,65, contre ×3,9 en natif.** Le gain se transporte presque en entier. La
> prudence était justifiée, la crainte non.

## Le protocole, et pourquoi il a fallu deux machines

La mesure a d'abord été faite sur la machine de calcul — pendant qu'un calcul de PR y occupait
26 cœurs. Les **rapports** y étaient déjà bons (×3,39), mais les **temps absolus ne valaient
rien**. Elle a donc été refaite sur `melbaa`, libre, à charge 1,5.

**La parité d'abord, comme toujours.** Aucun chiffre de vitesse n'est retenu avant que le module
WebAssembly ait été vérifié contre le repère natif de 2 000 positions :

| build | max\|Δ\| |
|---|---|
| scalaire | **0,000e+0** — exact |
| SIMD | 6,407e-7 — sous la tolérance de 1e-6 |

Et chaque configuration chronométrée est contrôlée avant d'être mesurée : **même coup, même compte
d'évaluations, même équité à 3e-7 près** que le natif. Un débit mesuré sur un moteur qui répond
faux ne vaut rien.

## Le coût d'une décision, mesuré

Position `4HPwATDgc/ABMA`, jet 3-1. Médiane, un tour à blanc écarté.

| configuration | ms | évaluations | ms/éval |
|---|---|---|---|
| 0-ply | **6** | 16 | 0,375 |
| 1-ply | 2 289 | 7 475 | 0,306 |
| 2-ply `1/1` | 3 629 | 12 951 | 0,280 |
| 2-ply `(0,1,3)`, sans élagage | **9 813** | 38 721 | 0,253 |
| **2-ply `(0,1,3)`, élagage `k=12`** | **2 689** | 15 142 | **0,178** |

**L'élagage rend ×3,65** (9 813 → 2 689 ms). En natif il rend ×3,9. L'écart entre les deux est
plus faible que ce que le rapport des gains de lot laissait craindre.

**Le coût par évaluation baisse avec la taille du travail** — 0,375 ms au 0-ply, 0,178 ms au 2-ply
élagué. C'est le lot qui se remplit : plus la fratrie est grande, moins les voies mortes coûtent.

## Le parallélisme, et le budget qui en découle

`workers.html`, mêmes positions, débit d'évaluation :

| workers | éval/s | accélération |
|---|---|---|
| 1 | 4 301 | ×1 |
| 2 | 7 463 | ×1,74 |
| 4 | 13 333 | ×3,1 |
| **8** | **26 667** | **×6,2** |

L'annulation est honorée et le pool reste utilisable après (`cancellationHonoured`,
`usableAfterCancel`) — un détail d'interface, mais celui qui décide si un utilisateur peut changer
d'avis pendant une analyse.

**Le budget d'un match de 7 points (~130 décisions), au réglage `k=12`** :

| | |
|---|---|
| mono-fil | **350 s** — 5,8 min |
| 8 workers | **74 s** |

## Ce que cela règle, et ce que cela ne règle pas

**Réglé** : le préréglage « Approfondi » de la proposition d'interface tient — un match en une
minute et quart sur un desktop, avec le réglage dont la perte de qualité est dans le bruit
(`docs/mesures/2026-08-27-T3D-elagage-par-defaut.md`). **Le 2-ply reste praticable dans le
navigateur**, ce qui était la question qui pouvait invalider la cible du projet.

**Non réglé, et nommé** :

- **Le mobile.** T21 avait mesuré une pénalité de ×2,12 à ×2,83 sur deux appareils. Appliquée à
  74 s, elle donnerait 2,6 à 3,5 min par match — **projection, pas mesure**. Il faut un appareil.
- **La pénalité WebAssembly elle-même n'est PAS remesurée ici.** Le natif de comparaison tourne
  sur une autre machine que ce navigateur ; comparer les deux mesurerait la différence de
  processeurs autant que celle des cibles. T21 l'avait mesurée à ×1,18–1,29 sur un même poste, et
  ce chiffre n'est pas contredit — il n'est simplement pas rejoué.
- **Chromium.** Firefox seul ici. T21 avait mesuré les deux et Chromium était le plus rapide.

## Reproduire

```bash
make wasm && make wasm-parity
node wasm/harness.mjs --browser firefox --page /wasm/decision.html --build simd
node wasm/harness.mjs --browser firefox --page /wasm/workers.html  --build simd
```

Sorties : [`t21b-navigateur-decision.json`](t21b-navigateur-decision.json),
[`t21b-navigateur-workers.json`](t21b-navigateur-workers.json).

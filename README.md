# gammonNet — banc mobile

Page de mesure publiée pour **T21**, dont le volet mobile ne peut pas être mesuré depuis la
machine de développement : elle n'a pas de réseau local, et il n'y a pas de câble pour brancher
un téléphone. Le téléphone n'a donc pas besoin d'atteindre la machine — il atteint internet.

Ouvrir la page sur l'appareil, appuyer sur **Lancer la mesure**, lire le résultat.

Cette branche ne contient **que** des artefacts construits. Les sources vivent sur `main`.
La mesure et son protocole sont dans `docs/mesures/2026-08-03-T21-debit-navigateur.md`.

## Ce qui est servi

| Fichier | Rôle |
|---|---|
| `index.html` | La page de mesure |
| `evaluator.mjs` | L'enveloppe JavaScript de l'évaluateur |
| `gammonnet-simd.mjs` / `.wasm` | Le module WebAssembly, build SIMD |
| `model.bin` | Les poids `cubeless_prob5_512_512_256_128` (2,0 Mio) |
| `reference.bin` | 400 positions et leurs sorties, produites par le build natif |

La page mesure deux choses : le **débit d'évaluation** du réseau, et le **coût d'une décision
2-ply complète** — recherche comprise. Elle vérifie l'accord avec le build natif avant de
chronométrer, et refuse de conclure si l'horloge n'a pas avancé.

## Licences

Réseau et moteur d'inférence : `backgammon-ai-engine`, Copyright (c) 2026 alexstrehl, **MIT**.
gammonNet : Copyright (c) 2026 Kévin Unger, **MIT**. Voir `LICENSE` et `THIRD-PARTY.md`.

**Aucun réseau HedgeHog** (clause non commerciale) **ni poids GNU Backgammon** (GPL-3) n'entre
dans cet artefact.

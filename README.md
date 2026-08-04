# gammonNet

Un évaluateur de positions de backgammon, pour le navigateur et pour le natif.

Un réseau de neurones, une recherche expectiminimax, une table d'équité de match et des tables de
fin de partie. Deux cibles : WebAssembly (2-ply sur l'appareil) et natif (profondeurs supérieures
et rollouts).

Tout ce qui est distribué est sous licence permissive, sans clause d'usage. Un module WebAssembly
servi à un navigateur est une distribution, ce qui exclut les briques sous copyleft fort ou sous
clause non commerciale.

## Ce qui est réutilisé, ce qui est écrit ici

Les poids du réseau viennent de
[`alexstrehl/backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine) (MIT),
entraîné en self-play.

| Brique | Origine | Statut |
|---|---|---|
| Poids du réseau, moteur de règles, lecteur `.bin` | Strehl, MIT | réutilisés, isolés derrière une interface |
| Table d'équité de match Kazaross-XG2 | Neil Kazaross | réutilisée, vérifiée contre le rendu de GNU Backgammon |
| Codec position ↔ 196 caractéristiques | — | écrit ici |
| Recherche expectiminimax 0→3 ply, filtrage de coups | idée documentée par le manuel de GNU Backgammon ; aucun code repris | écrit ici |
| Équité de match dans la recherche | architecture de GNU Backgammon : réseau cubeless, conversion après | écrit ici |
| Portage WebAssembly, pool de Web Workers | — | écrit ici |
| ×9 de débit sur la passe avant, exact au bit près | — | écrit ici |

Le codec permet d'évaluer une position fournie de l'extérieur (XGID, Position ID) ; sans lui, le
modèle ne traite que les positions de son propre moteur de self-play. La recherche fait passer du
0-ply à des profondeurs supérieures : le 1-ply change le coup choisi dans 7,6 % des décisions
mesurées. L'équité de match est nécessaire pour jouer ailleurs qu'en money, le réseau étant
cubeless et aveugle au score.

### Annoncé et mesuré

| | annoncé | mesuré ici |
|---|---|---|
| Force du modèle contre GNU Backgammon, 0-ply money | +0,0578 ppg (auteur) | +0,0400 [+0,0377 ; +0,0425], 10⁶ parties |
| Pénalité WebAssembly | ×1,5 à ×2,5 (hypothèse) | ×1,18 à ×1,29 |
| Coût d'une décision 2-ply | 245 ms (extrapolé) | 1 394 ms, filtre 1/1 |
| Match de 7 points dans le navigateur | 30 à 60 s | ~2 min, 3,3 workers |
| PR du modèle, 0-ply → 2-ply | 1,06 → 0,22 (auteur) | non vérifié — objet de T35 |

Le +0,0578 n'a pas été reproduit. Le harnais du dépôt de référence, exécuté inchangé ici, donne
+0,0351, soit le même résultat que le nôtre. L'hypothèse d'un oracle différent a été testée et
réfutée. La base de comparaison de ce dépôt est donc +0,0400 dans cet environnement.

La force de la configuration complète — recherche, équité de match, tables de fin de partie —
n'est pas mesurée. C'est l'objet de T35.

## Coût dans le navigateur

Position d'ouverture, Chromium :

| Profondeur | Évaluations réseau | Coût d'une décision |
|---|---|---|
| 0-ply | 16 | 1,7 ms |
| 1-ply | 7 475 | 797 ms |
| 2-ply, filtre 1/1 | 12 951 | 1 394 ms |

Un match de 7 points représente environ deux minutes de calcul sur 3,3 workers. Mesuré sur sept
plateformes : Chromium, Firefox, deux Android, deux iPhone
([détail](docs/mesures/2026-08-04-decision-navigateur.md)).

Sur ces sept plateformes, l'écart au repère natif vaut `4,77e-07` dans tous les cas. Une analyse
produite sur téléphone donne le même résultat que sur ordinateur.

## État

Phases 0, 1 et 2 terminées. Phase 3 en cours.

| | Tâches | État |
|---|---|---|
| 0 — Socle & instrument | T00 · T01 · T02 · T03 · T04 · T05 | ✅ |
| 1 — Reproduire | T10 · T11 · T12 | ✅ |
| 2 — Navigateur | T20 · T21 · T22 · T23 | ✅ |
| 3 — Profondeur & exactitude | T30 · T31 · T32 ✅ · T33 ⏳ · T34 · T35 | en cours |
| 4 — Modèle propre au projet | — | fermée |
| 5 — Publication | T50 | à venir |

Chaque tâche porte un rapport dans [`docs/mesures/`](docs/mesures/), qui distingue le mesuré de
l'estimé.

La phase 4 devait s'ouvrir si la phase 1 échouait à confirmer la force annoncée. Le critère est
atteint à la lettre, puisque le chiffre publié n'a pas été reproduit. Elle reste fermée : le
critère visait le cas où le modèle serait insuffisant, ce qui n'est pas le cas. Condition de
réouverture : T35.

## Démarrer

```bash
make setup     # environnement Python, sources tierces épinglées, moteur C compilé
make build     # bibliothèque native
make wasm      # module WebAssembly
make test
```

Python ≥ 3.10 et un compilateur C. Emscripten pour la cible navigateur.

## Documents

| | |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Règles de travail — frontière, contraintes, conventions |
| [`BRIEF.md`](BRIEF.md) | Contexte — sources, licences, chaîne technique, protocole |
| [`PLAN.md`](PLAN.md) | Plan d'exécution — 5 phases, 21 fiches |
| [`THIRD-PARTY.md`](THIRD-PARTY.md) | Inventaire des briques et de leurs licences |
| [`docs/adr/`](docs/adr/) | Décisions d'architecture |

Objectif : atteindre un niveau équivalent ou supérieur à GNU Backgammon et à eXtreme Gammon, et le
justifier par une mesure reproductible dont chaque source est traçable.

## Crédits

- Réseau et moteur de règles — [Alexander Strehl](https://github.com/alexstrehl/backgammon-ai-engine), MIT.
- Table d'équité de match Kazaross-XG2 — Neil Kazaross ; transcription croisée avec
  [blunderDB](https://github.com/kevung/blunderDB), MIT.
- GNU Backgammon — oracle de mesure et référence de la table d'équité. Pas une source de code ni
  de poids.
- [HedgeHog](https://hedgehog-bg.com/) — leur principe « refused, not approximated » est repris
  comme règle de travail, et leurs chiffres publiés ont servi d'hypothèses initiales. Ni leur code
  ni leurs réseaux ne sont utilisés ([ADR-0001](docs/adr/0001-moteur-inference.md)).

Licences : [`THIRD-PARTY.md`](THIRD-PARTY.md).

## Licence

MIT. Voir [`LICENSE`](LICENSE).

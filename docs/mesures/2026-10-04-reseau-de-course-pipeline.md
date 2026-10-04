# 2026-10-04 — Réseau de course hors bearoff pur : pipeline prêt à lancer

**Nature de ce document** : un mode d'emploi et un protocole de jauge. **Aucun entraînement long
n'a été lancé**, aucun poids n'est livré. Les chiffres marqués *mesure* viennent d'un
chronométrage daté ; ceux marqués *hypothèse* sont des extrapolations à confirmer.

## La zone

`classify.in_race_zone(position)` : position non terminée, **sans contact** (`has_contact` faux),
et **hors du domaine de la table bilatérale exacte** (`bearoff_net.contains` faux : un camp n'est
pas rentré, ou a plus de onze pions). C'est la zone où ni la table ni le réseau de bearoff distillé
ne répondent.

Ce n'est pas la classe `race` de `classify` : celle-ci se lit du côté du joueur au trait, et une
position où le trait est rentré alors que l'adversaire ne l'est pas y est `bearoff_noncontact`.
Elle appartient pourtant à cette zone. Le corpus enregistre la classe de chaque ligne, la jauge
la rapporte par strate.

## Les trois outils

| Étape | Outil | Rend |
|---|---|---|
| Extraction | `tools/build_race_corpus.py` | `.npz` : `features`, `probs`, `equity`, `se`, `ids`, `klass`, `pips` |
| Entraînement et export | `tools/train_race_net.py` | `.bin` au format plat du moteur + `.provenance.json` |
| Jauge | `tools/gauge_race_net.py` | rapport JSON et lecture imprimée |

**Étiquettes.** Les positions viennent du jeu 0-ply de l'incumbent contre lui-même (au plus
`--per-game` positions de la zone par partie, à des coups tirés au sort : deux positions voisines
d'une partie ne sont presque qu'un échantillon). Chacune est étiquetée par un **rollout non
tronqué** (`truncate = 0`) : les cinq fréquences emboîtées sont de vraies issues de parties. Une
étiquette porte donc du bruit d'échantillonnage ; son erreur standard est stockée et sert de
**plancher** à toute erreur mesurée. Aucune source extérieure.

**Réseau.** 196 entrées, cinq sorties sigmoïdes emboîtées, ReLU cachées, entropie croisée binaire
par sortie, défaut `--hidden 128,64` (33 600 MACs). Le `.bin` est écrit par `write_model` et relu
par le moteur à la fin de l'entraînement.

## Commandes de lancement

Prérequis : `models/cubeless_prob5_512_512_256_128.bin` (l'incumbent, non versionné), `make build`,
un GPU pour l'entraînement.

```
# 1. corpus d'entraînement et corpus de jauge, deux graines disjointes
python tools/build_race_corpus.py --count 50000 --trials 1296 --workers 12 \
    --seed 20261004 --out build/race_train.npz
python tools/build_race_corpus.py --count 5000 --trials 1296 --workers 12 \
    --seed 20261104 --out build/race_gauge.npz

# 2. entraînement et export
python tools/train_race_net.py --corpus build/race_train.npz --hidden 128,64 \
    --out models/race_128_64.bin

# 3. jauge contre l'incumbent
python tools/gauge_race_net.py --corpus build/race_gauge.npz \
    --candidate models/race_128_64.bin --exclude build/race_train.npz \
    --out docs/mesures/race_128_64-gauge.json
```

Mode fumée de chaque outil (`--smoke`, quelques centaines de lignes, 24 à 36 essais, un
incumbent tiré au sort, CPU) : il prouve la plomberie, pas la force.

## Durées estimées

* **Extraction — le poste qui coûte.** *Mesure* : 6 lignes à 1 296 essais, un processus, machine
  chargée par ailleurs : **3,6 minutes, soit environ 36 s par ligne** (marche de la partie
  comprise ; erreur standard moyenne des étiquettes : 0,0079). *Hypothèse* (mise à l'échelle
  linéaire par processus, sur 6 lignes seulement) : 50 000 lignes sur 12 processus font environ
  **42 heures** ; 5 000 lignes de jauge, environ 4 heures. Le coût est linéaire en `--trials` et
  l'erreur standard décroît en `1/√trials` : 324 essais divisent le temps par 4 pour une erreur
  standard doublée (environ 0,016, *hypothèse*). Choisir avant de lancer ; ne pas lancer 200 000
  lignes à 1 296 essais (environ 7 jours).
* **Mémoire** : un processus d'extraction charge l'incumbent (environ 2 Mo de poids) et un
  interpréteur ; 12 processus tiennent dans les 3 Go libres de la machine de développement
  (*hypothèse*, non mesurée à 12).
* **Entraînement** : *hypothèse* — à 70 à 100 µs par ligne et par époque sur CPU (mesure faite
  sur 240-120-60 et 256-128-64, voir la fiche T72), 128-64 est moins cher ; 50 000 lignes × 200
  époques restent de l'ordre de quelques minutes sur GPU et de l'ordre d'une heure sur CPU.
* **Jauge** : quelques secondes par réseau (une évaluation par ligne).

## Protocole de jauge

Instrument : l'erreur d'équité cubeless money de chaque réseau contre l'équité du rollout de la
même position, sur un corpus de **graine disjointe** de l'entraînement, dont les positions
communes avec l'entraînement sont retirées et comptées (`--exclude`).

Rapporté : MAE, RMSE et biais, globalement et par classe ; la **différence appariée** des erreurs
absolues (candidat − titulaire), son intervalle à 95 % ; l'erreur standard moyenne des rollouts
(le plancher). Négatif favorise le candidat ; un intervalle contenant zéro n'est pas une
différence.

Ce que la jauge **n'est pas** : ni une perte par décision, ni une force de jeu. Elle dit si le
réseau estime mieux l'équité d'une position de course. Dire que cela change le jeu demande une
mesure de décision sur des coups de course une fois le réseau branché dans la recherche — hors du
périmètre de cette fiche, qui ne touche pas à `gn_search` ni à `gn_cube`.

Volume : à 5 000 lignes et une erreur standard de 0,008, la différence appariée a un intervalle
fin, mais il ne vaut que pour la distribution de jeu 0-ply de l'incumbent. Le rapport le dit ;
il ne porte pas sur les positions que la recherche à deux plis rencontre.

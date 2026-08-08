# T39 — Arbitrage des désaccords de videau (money), 2026-08-08

## Ce qui est mesuré

On collecte tous les désaccords de décision de videau **money** entre notre moteur et
gnubg à 0-ply, puis on les fait arbitrer par des instruments plus profonds. Un verdict
n'existe que là où les instruments concordent ; un désaccord d'arbitres est une ligne
« non tranchée », jamais une occasion de choisir sa colonne.

**Protocole.**

- Corpus : 2 000 positions de contact + 1 000 de bearoff (générateur du harnais,
  graine figée), chacune examinée sous deux états de videau (centré, possédé), soit
  **6 000 décisions**.
- Notre décision : évaluation neuronale 0-ply + modèle de Janowski avec les
  efficacités mesurées (x = 0,688 centré / 0,566 possédé / 0,687 adverse), Jacoby.
  **Sans consultation de la table exacte** — c'est le chemin *modèle* qui est mis à
  l'épreuve, pas le moteur livré (voir la réserve 1).
- Leur décision : gnubg 0-ply cubeful (CLI, mêmes états).
- Arbitres, dans l'ordre :
  1. **Table exacte deux-faces** (`gnubg_ts6x11.bd`) quand la position est dans son
     domaine — verdict sans variance ni réserve ;
  2. sinon, **deux colonnes de rollout** menées séparément :
     - *notre colonne* : rollout cubeful tronqué à 11 plis, 3 888 essais par branche
       (ND et DT), graine propre à chaque décision, cache d'évaluation ;
     - *colonne gnubg* : rollout CLI, 1 296 essais, réduction de variance par la
       chance, graine 20260811.
- Critère de résolution d'une colonne : verdict stable aux quatre coins
  e ± 1,96 se (ND et DT).

Données brutes : `t39-arbitrage-money.json` (394 lignes). Banc :
`bench/arbitrate_cube.py`. Durée : ~4 h 40 sur 15 processus.

## Résultats

**394 désaccords sur 6 000 décisions (6,6 %).**

### Domaine exact : 70 décisions, 68–2 pour gnubg — mais lisible

Tous les désaccords issus du corpus de bearoff tombent dans le domaine de la table.
Le verdict brut (68–2) se décompose :

- **45/70 : coût réel nul.** Paires TOO_GOOD / DOUBLE_PASS sur des gains certains où
  les deux actions réalisent exactement la même équité ; le « désaccord » est un
  départage à marge ~10⁻¹⁵.
- **25/70 : coût réel non nul, toutes contre nous, total +1,95 d'équité**
  (maximum +0,36 sur une seule décision). Le motif est massivement homogène :
  **nous disons NO_DOUBLE là où la table dit DOUBLE_TAKE** — le chemin neuronal +
  Janowski **sous-double les courses**.

### Contact : 324 décisions, deux colonnes, verdict = égalité statistique

| | notre colonne | colonne gnubg |
|---|---|---|
| résolues | 114 / 324 (35 %) | 282 / 324 (87 %) |
| soutiennent notre verdict | 45 | 170 |
| soutiennent gnubg | 69 | 111 |
| ni l'un ni l'autre | 0 | 1 |

Les taux de soutien par colonne ne sont **pas comparables** : chaque colonne résout un
sous-ensemble différent. Le seul verdict honnête vient des lignes où **les deux
colonnes sont résolues et concordent** :

- 106 lignes résolues des deux côtés ; **69 concordantes** ;
- **38 pour nous, 31 pour gnubg** — binomiale unilatérale p = 0,235 :
  **aucune supériorité mesurable de part et d'autre**.
- **37 lignes en conflit d'arbitres → non tranchées.** Le motif est fortement
  asymétrique : sur 35 des 37, notre colonne soutient gnubg pendant que la leur nous
  soutient. Les deux instruments portent des biais systématiques différents
  (troncature à 11 plis d'un côté ; politique de jeu et réduction de variance de
  l'autre). On le constate, on ne l'interprète pas.

**Pourquoi notre colonne résout si peu.** 175 des 210 non-résolues sont des fenêtres
DOUBLE_TAKE / NO_DOUBLE où l'écart médian |e_ND − e_DT| vaut 0,042 pour un se médian
de 0,025 : sans réduction de variance, 3 888 essais tronqués ne stabilisent pas les
quatre coins. C'est une limite de l'instrument, pas des décisions.

## Réserves nommées

1. **Le domaine exact ne mesure pas le moteur livré.** En production, la recherche
   (`gn_search`) et le rollout (`gn_rollout`) lisent la table exacte en domaine ; les
   70 défaites ci-dessus ne sont donc pas expédiées. Elles caractérisent le modèle —
   et la sous-double de course vaut vraisemblablement aussi juste **hors** du domaine
   de la table, où rien ne le corrige.
2. **Décisions à 0-ply des deux côtés.** L'arbitrage juge les politiques de doublage
   0-ply, pas les moteurs à leur profondeur de jeu.
3. **Conventions d'équité différentes entre colonnes** (gnubg rapporte par unité de
   videau courant) : les coûts d'équité ne s'additionnent pas d'une colonne à
   l'autre ; seuls les décomptes de verdicts sont agrégés.
4. **Le sous-ensemble de consensus n'est pas un échantillon aléatoire** : il est
   sélectionné par la capacité des deux instruments à résoudre — les fenêtres fines
   en sont sous-représentées.

## Conclusions

- **Contact : rien ne distingue les deux politiques de doublage 0-ply** sur les
  décisions contestées (38–31, p = 0,235, 37 non tranchées).
- **Courses : le modèle neuronal sous-double**, de façon nette et unidirectionnelle.
  En domaine, la table exacte corrige déjà ; hors domaine, c'est un chantier
  identifié (candidat T35/T40 : cible d'entraînement ou heuristique de course).
- **Instrument : notre rollout tronqué manque de puissance** (35 % de résolution) sur
  les fenêtres fines. La réduction de variance est le prochain investissement
  d'instrumentation (fiche T39, reste à faire).

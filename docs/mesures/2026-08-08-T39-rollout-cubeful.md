# T39 — Le rollout cubeful, et son contrôle de non-biais mesuré en volume

**Date** : 2026-08-08 · **Machine** : bureau (15 processus) · **Branche** : `t39-cubeful`

> **Ce que ce rapport établit** : l'arbitre porte maintenant un videau vivant, et là où la
> vérité exacte existe — le domaine de la table bilatérale — il la retrouve sans biais
> mesurable, pour les trois états du videau. **Ce qu'il n'établit pas** : le comportement de
> l'arbitre hors du domaine, où les décisions de videau viennent du modèle ajusté ; la réserve
> structurelle de T39 (un rollout conduit par notre réseau nous favorise) reste entière et
> voyage avec chaque usage.

## Ce qui a été construit

`use_cube` dans `GnRolloutConfig` : chaque essai porte un videau vivant. Avant chaque jet, le
joueur qui peut doubler consulte la décision — **exacte** (les trois équités cubeful stockées,
mécanique §4) dans le domaine de la table, celle du **modèle ajusté** (`gn_cube_decide`, `x`
mesuré par état) ailleurs. Un passe encaisse l'enjeu courant ; une prise le double et transfère
le videau, dont la possession est mise en miroir à chaque tour. Un essai tronqué est valué par
la valeur de feuille cubeful à l'horizon, fois l'enjeu atteint. Les équités restent en unités
du videau initial. `gn_cube` exporte désormais le verdict §4 et le miroir de possession,
plutôt que d'en laisser pousser des copies.

## La convention de la table, fixée par sonde

La première version du contrôle a échoué à 8/18 — et l'échec a été la mesure la plus utile de
la journée. Une course où le meneur à 86 % encaisserait volontiers **maintenant**, mais dont
toutes les fenêtres de double **futures** sont sans valeur, porte la même équité stockée pour
les quatre états du videau (0,8611 partout, position `[2,1] / [1,2,1]`) : les équités cubeful
de la table **excluent l'option de double du tour courant** — elles valent pour un joueur au
trait qui a déjà passé son point de décision. C'est aussi, précisément, la sémantique de la
branche « ne double pas » d'un arbitrage de décision de videau.

D'où `cube_defer_first` : actif, le rollout saute la consultation au ply 0. On l'active pour
arbitrer une décision de videau et pour viser les chiffres de la table ; on le coupe pour une
position d'après-coup, dont l'adversaire entame son tour avec son option intacte. Ce n'est pas
un réglage : c'est le choix de la question posée, et il est documenté dans `gn_rollout.h`.

## Le contrôle de non-biais, en volume

**Protocole** : 360 positions du domaine (graine 20260810), quatre colonnes par position —
cubeless (le témoin, déjà contrôlé par la suite de tests), puis videau centré / possédé /
adverse — rollouts **non tronqués** (aucun biais d'horizon à excuser), 2 592 essais, décisions
de videau exactes, politique de coups cubeful exacte en domaine, `cube_defer_first` actif.
**Graine de rollout par position** : les dés communs servent à comparer des variantes, pas à
mesurer un biais — une graine unique partagée aurait fait de la chance commune du tirage un
faux biais global (constaté avant correction : `mean_z ≈ +0,4` sur la colonne témoin
elle-même). 1 440 rollouts, 3,7 M de parties, 15 processus.

| colonne | n résolus | dans ±1,96 | `mean_z` | pire \|z\| | encaissés | videau moyen |
|---|---:|---:|---:|---:|---:|---:|
| cubeless (témoin) | 266 | 93,6 % | +0,11 | 3,37 | — | — |
| centré | 205 | 93,7 % | +0,12 | 2,98 | 77,2 % | 1,14 |
| possédé | 240 | 93,3 % | +0,13 | 3,10 | 43,6 % | 1,06 |
| adverse | 231 | 92,6 % | +0,10 | 3,52 | 37,8 % | 1,07 |

Deux artefacts de méthode, nommés plutôt que maquillés :

- **La couverture à ~93 % au lieu de 95 %, et le `mean_z` légèrement positif, sont partagés
  par la colonne témoin** — c'est l'approximation normale sur des sommes de ±1 très
  asymétriques (l'erreur-type estimée sous-couvre notoirement quand p s'approche de 1), pas la
  machinerie du videau. Le juge propre est l'**appariement** (même graine par position, les
  quatre colonnes partagent leurs dés) :

  | Δz contre le témoin | n | moyenne | erreur-type |
  |---|---:|---:|---:|
  | centré − cubeless | 205 | **+0,021** | 0,066 |
  | possédé − cubeless | 240 | **+0,022** | 0,047 |
  | adverse − cubeless | 231 | **−0,003** | 0,037 |

  Tous compatibles avec zéro : le videau vivant n'ajoute **aucun biais mesurable** à un
  estimateur dont le témoin est déjà contrôlé.

- **Les positions dégénérées** (erreur-type nulle : l'issue rare, ~1/2000, absente du tirage)
  sont agrégées à part : l'écart maximal y est de 0,0025 — l'ordre de la granularité `1/N`
  d'un estimateur à 2 592 essais (une ligne perdante de probabilité 6,4/N invisible par
  hasard), pas un biais. Le témoin cubeless porte le même écart maximal.

Aucun essai bloqué (0 `stalled` sur 3,7 M de parties). Le videau a réellement vécu : 77 % des
essais au videau centré finissent encaissés sur un passe.

## Ce qui reste à T39

- **L'arbitrage effectif** des désaccords accumulés (§6.3, 3b) : les deux branches d'une
  décision contestée rolloutées avec `cube_defer_first`, les deux colonnes — la nôtre et celle
  de gnubg — publiées ensemble. L'instrument existe maintenant ; la campagne d'arbitrage est
  l'étape suivante.
- **Le match cubeful** : la récursion §9 sait pricer un videau à score, mais un rollout de
  match doit aussi se **terminer** à un score (Crawford, post-Crawford, gain du match) — cette
  machinerie d'état n'existe pas encore, et `gn_rollout.h` le nomme.
- **L'arrêt sur intervalle de confiance** (périmètre de la fiche) : toujours à nombre d'essais
  fixe aujourd'hui.

## Reproduire

```bash
python -m pytest tests/test_rollout.py -q
python bench/rollout_bias.py --positions 360 --trials 2592 --workers 15 \
    --out docs/mesures/t39-non-biais.json
```

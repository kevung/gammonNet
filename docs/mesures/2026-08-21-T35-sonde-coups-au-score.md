# T35 — sonde du jeu de pions au score : le chemin API contre gnubg lui-même

**Date** : 2026-08-21 · **Tâche** : T35 · **Statut** : mesure faite — **le chemin est
fidèle**, et la limite nommée de la sonde du videau est levée

---

## 1. La limite que celle-ci lève

La sonde du videau (`2026-08-21-T35-sonde-videau-au-score.md`) a nommé sa propre
limite : elle ne sonde que le videau. Or la campagne pilote aussi le **jeu de pions**
de gnubg au score, par un tout autre mécanisme — `GnubgEngine._evaluate_at` évalue les
positions résultantes sous un `cubeinfo` de match et les classe par `-eval[5]`, en
s'appuyant sur la convention EMG sondée le 2026-08-09. La cellule DMP de la campagne
(50,94 %) et la moitié money disaient que cette convention n'est pas grossièrement
fausse ; aucune ne la mesurait à un score quelconque.

## 2. Le protocole

`bench/probe_gnubg_moves_at_score.py`, même principe que la sonde du videau :

- **`api`** — le chemin d'évaluation de la campagne : chaque coup légal évalué à
  2 plis, `prune=1`, **cubeless**, sous l'état que la campagne construit
  (`gnubg_state(CENTRED, swapped_match, jacoby=False)` — l'échange étant celui de la
  campagne, puisque `play.result` a déjà rendu le trait). Meilleure équité gagne.
  **Le filtre de racine n'est pas appliqué** : c'est un handicap délibéré et mesuré
  ailleurs (T31), pas la question ici.
- **`cli`** — l'interface de gnubg avec le vrai match posé, son filtre de coups à
  2 plis **ouvert en grand** (`movefilter 2 * -1 0 0`, l'« accepte tout » de gnubg,
  lu en retour dans `show player`) pour qu'il classe lui aussi tous les coups légaux,
  et le videau confié à l'adversaire pour que `play` ne puisse être qu'un coup de
  pions. Le coup joué est apparié au nôtre **par résultat** — identifiant de position,
  le seul format déjà croisé (T02).

**Money est le témoin** : la moitié money de la campagne est mesurée saine, donc le
taux d'accord money est ce à quoi ressemble « le harnais est fidèle ». Si le chemin au
score était cassé, l'accord au score s'en écarterait.

Corpus : 2 000 contact (graine 20260807) + 1 000 fin de partie (graine 20260808), un
jet par position (graine 20260821). Coups forcés et coups terminaux écartés — l'accord
n'y dit rien. **2 566 positions utilisables, 8 contextes, 20 528 décisions en 1 135 s.**

## 3. Le résultat

| Contexte | n | Même coup | Écart d'équité max | Abandons |
|---|---|---|---|---|
| money *(témoin)* | 2 521 | 97,98 % | **0,000** | 45 |
| 2a2a, 3a5a, 5a3a, 4a4a, 7a7a | 2 521 | 97,98 % | **0,000** | 45 |
| post-Crawford 2a1a, 4a1a | 2 521 | 97,82 % | **0,000** | 45 |

Deux choses, et la seconde compte plus que la première :

- **L'accord au score est celui du money**, à 0,16 point près. Le chemin de match ne
  se distingue pas du chemin money, qui est mesuré sain.
- **Les 2 % de désaccord ne coûtent rien** : dans *chaque* cas, l'écart d'équité que
  le chemin API met entre les deux coups est **exactement nul**. Ce sont des égalités
  parfaites — surtout en fin de partie, où plusieurs coups mènent à la même valeur — et
  les deux moteurs les départagent différemment. Un départage d'égalité n'est pas un
  désaccord d'évaluation.

**Abandons** : 45 positions par contexte (1,8 %) où `play` fait *abandonner* gnubg au
lieu de jouer. Aucun réglage de gnubg ne l'en empêche (`help set player`,
`help set automatic`). Ces positions sont comptées à part et jamais devinées : elles
sont trop perdues pour qu'un choix de coup y veuille dire quelque chose.

## 4. Ce que cela établit, et ce que cela n'établit pas

**Établi** : le jeu de pions de gnubg au score, tel que la campagne le pilote, est le
jeu de pions de gnubg. La convention EMG composée se transporte au score sans perte,
post-Crawford compris.

**Non établi** : que notre propre jeu de pions soit bon — ce n'est pas la question de
cette sonde, c'est celle de T31/T34 et, en dernier ressort, celle de la campagne
elle-même. Et le coût du filtre de racine (garde 3) reste ce que T31 a mesuré : il
n'est pas re-mesuré ici, il est retiré des deux côtés.

Avec la sonde du videau, les deux moitiés du pilotage de gnubg au score sont
désormais mesurées. La seule faute trouvée est celle du videau mort, corrigée.

## 5. Reproduire

```bash
python bench/probe_gnubg_moves_at_score.py --contact 2000 --bearoff 1000 \
    --workers 20 --out docs/mesures/t35-sonde-coups-au-score.json
```

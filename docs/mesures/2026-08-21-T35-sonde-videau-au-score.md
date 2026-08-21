# T35 — sonde du videau au score : le chemin API contre gnubg lui-même

**Date** : 2026-08-21 · **Tâche** : T35 · **Statut** : mesure faite, défaut trouvé,
corrigé et couvert par un test — **la moitié match de la campagne est à refaire**

---

## 1. La question, et pourquoi elle se posait

La campagne T35 mesure deux moitiés contre le même adversaire au même réglage
(`gnubg-2ply-f0/1/3-cube2`). Elles se contredisent :

| Moitié | Volume | Résultat |
|---|---|---|
| money, cubeful | 50 000 paires — **complète** | **−0,0119 ppg** [−0,0310 ; +0,0074] |
| match, 7 points | 23 988 paires — partielle | **56,42 % MWC** [56,01 ; 56,84] |

À égalité en money, six points de MWC en match. Découpé par score de départ,
l'écart en match ne vit que là où le videau vit :

| Cellule | Paires | MWC |
|---|---|---|
| DMP (1-away/1-away), videau mort | 533 | 50,94 % |
| videau vivant | 17 734 | 56,34 % |
| post-Crawford | 2 928 | **60,25 %** |

Le jeu de pions est nu — cohérent avec la moitié money. Deux lectures
possibles, et une seule mesure les sépare :

1. notre videau au score est réellement meilleur ;
2. **l'adversaire que nous pilotons par `cfevaluate` n'est pas celui que GNU
   Backgammon est réellement au score.**

Publier « équivalent ou supérieur » sur la seconde serait exactement l'erreur
silencieuse que la règle 2 de `CLAUDE.md` existe pour empêcher.

## 2. L'instrument

`bench/probe_gnubg_at_score.py` pose la même question deux fois, position par
position, videau par videau, score par score :

- **`api`** — le chemin de la campagne, verbatim : `cfevaluate` sous un
  `cubeinfo` construit par `gnubg_engine.gnubg_state`, qui **comprime** le
  match (`match_to = max(away)`) ;
- **`cli_true`** — l'interface de gnubg elle-même, avec le vrai match posé :
  `new match 7`, le vrai score, le vrai drapeau Crawford, le videau et son
  propriétaire posés sur le plateau, puis `hint` ;
- **`cli_compressed`** — la même interface, mais avec la longueur de match
  comprimée comme le chemin API la décrit. `cli_true` contre `cli_compressed`
  isole la compression ; `api` contre `cli_true` isole tout le reste.

En money — la moitié témoin — les deux variantes sont `cli_nobeaver` et
`cli_beaver` : `cubeinfo()` choisit lui-même son défaut de castor quand
`matchto = 0` et la campagne ne le fixe jamais ; plutôt que de le supposer, les
deux sont mesurées.

Chaque réglage est vérifié sur l'accusé de réception de gnubg, et le plateau
par aller-retour d'identifiant de position — qui contrôle la position **et** le
trait d'un seul coup.

**Corpus** : celui de T34, repris verbatim — 600 positions de contact
(`bench/decision_loss.corpus`, graine 20260807) + 300 de fin de partie
(`exact_gap.random_bearoff`, graine 20260808). Douze contextes, deux états de
videau (centré à 1, possédé à 2) : **21 600 décisions comparées en 402 s**.

## 3. Ce que la sonde dit

**Là où la campagne pose réellement la question, les deux chemins ne diffèrent
jamais.**

| Contexte | n | Verdicts identiques | take/pass identiques |
|---|---|---|---|
| money | 1 800 | 100 % [99,8 ; 100] | 1800/1800 |
| 3a5a, 5a3a, 4a4a, 7a7a | 1 800 chacun | 100 % [99,8 ; 100] | 1800/1800 |
| post-Crawford 4a1a, 6a1a | 1 800 chacun | 100 % [99,8 ; 100] | 1800/1800 |

- **La compression du match est exactement gratuite** : `cli_true` et
  `cli_compressed` rendent le même verdict sur 1 800/1 800 positions dans
  **chacun** des dix contextes de match. Une table d'équité de match s'indexe
  par les scores restants, et gnubg le confirme par sa propre interface.
- Les équités concordent à 5·10⁻⁴ près — c'est la **précision d'affichage** de
  `hint` (trois décimales), pas un écart mesuré. Le verdict est la comparaison
  qui tranche.
- Le castor ne change rien au verdict money : 100 % dans les deux réglages.

## 4. Le défaut, et il est unique

4 500 désaccords sur 19 800, et ils sont **tous la même chaîne** :

| gnubg dit (API) | gnubg dit (son interface) | Nous lisions |
|---|---|---|
| `Never redouble, take (dead cube)` | `Cube not available` | **DOUBLE_TAKE** |

`classify_gnubg_verdict` traitait « Never **double** » mais pas « Never
**redouble** » : la règle générique en dessous voit « redouble » (qui contient
« double ») et « take », et conclut *double, et l'autre prend*. **La campagne
faisait donc redoubler gnubg exactement là où gnubg dit de ne jamais
redoubler.**

Le trou vient d'une limite nommée de la sonde de T34 : elle fixait le videau à
1 partout, donc n'atteignait aucun redoublement, donc n'a jamais vu le mot.

### 4.1 Il est atteignable — et d'un seul côté

La boucle de `cubeful.py` garde déjà les videaux morts :

```python
may = may and not crawford
may = may and not (cube >= away_white and cube >= away_black)
```

Elle filtre le videau mort **pour les deux joueurs à la fois**. Elle ne filtre
pas le cas où le videau est mort **pour le seul joueur au trait** :
`away_mover ≤ cube < away_opponent`. Vérifié sur le chemin de la campagne
lui-même (meneur post-Crawford à 1-away, videau 2 possédé, poursuivant à
3-away) :

```
la boucle pose-t-elle la question ?  True
gnubg dit                         :  Never redouble, take (dead cube)
la campagne lit                   :  True   ← elle le fait redoubler
nous, au même état                :  False  ← notre modèle refuse, correctement
```

Le même refus correct de notre côté à 1a/5a, 2a/5a, 2a/7a, 1a/4a. **Le défaut
ne joue que contre gnubg**, jamais contre nous.

Et il coûte cher à sa victime : redoubler quand son propre videau est mort ne
peut rien rapporter — le meneur à 1-away gagne le match avec n'importe quelle
victoire — mais double ce que l'adversaire encaisse s'il gagne. En
post-Crawford, cela transforme « le poursuivant gagne 2 points et reste à
1-away » en « le poursuivant gagne 4 points et remporte le match ». C'est un
cadeau, à sens unique, dans la cellule où la campagne mesure justement son plus
gros écart.

### 4.2 Le journal de la campagne porte la signature

En post-Crawford correct, le videau ne peut **pas** dépasser 2 : le poursuivant
double, le meneur prend et devient propriétaire, et plus personne ne peut
doubler — le meneur parce que son videau est mort, le poursuivant parce qu'il
n'a plus le videau. Or, dans `docs/mesures/t35-match.jsonl` :

| Score de départ | Paires | Videau max > 2 |
|---|---|---|
| post-Crawford | 3 049 | **84,1 %** |
| Crawford | 3 457 | 25,3 % |
| pré-Crawford | 18 455 | 77,3 % |

84 % des paires post-Crawford atteignent un videau de 4 ou 8. Aucune ne le
devrait. La signature est dans les données de la campagne elle-même.

## 5. Conséquences

- **La moitié match de T35 est invalide.** Elle mesure un gnubg estropié en
  match, et l'écart de +6,4 points de MWC est, au moins en grande partie, cet
  estropiement. Elle est à refaire après correction.
- **La moitié money est saine.** En money le videau n'est jamais mort — la
  chaîne n'apparaît pas — et la sonde le confirme : 100 % d'accord sur les
  1 800 décisions money, castor ou pas. Les 50 000 paires restent bonnes.
- Le reste du pilotage au score est **mesuré correct** : conventions de
  `cubeinfo`, orientation du score, propriétaire du videau, compression du
  match, take/pass. La sonde a fait son travail : elle a séparé les deux
  lectures, et c'est la seconde.

## 6. Le correctif

`classify_gnubg_verdict` traite désormais `never …` et tout verdict marqué
`(dead cube)` comme NO_DOUBLE. Couvert par
`tests/test_gnubg_engine.py::test_dead_cube_verdicts_are_never_read_as_a_double`,
qui épingle les douze chaînes du vocabulaire, plus le refus d'une chaîne
inconnue.

## 7. Limites nommées

- Le corpus n'est **pas** la distribution de positions de la campagne : il
  couvre la plage d'équité où les décisions de videau se disputent, ce dont la
  question a besoin, mais le poids de chaque cellule n'est pas celui de la
  campagne.
- La comparaison d'équité est bornée par les trois décimales que `hint`
  imprime.
- **Le jeu de pions au score n'est pas sondé** — seulement le videau. La
  cellule DMP (50,94 %) et la moitié money sont les deux indices qu'il va bien,
  ce ne sont pas des mesures de la convention EMG à un score quelconque. La
  même instrumentation le permettrait (`Gnubg.hints` sous un match posé) ; c'est
  la sonde suivante si elle est jugée nécessaire.
- La **taille** de l'effet sur la MWC n'est pas mesurée ici. La campagne match
  relancée la mesurera par différence.

## 8. Reproduire

```bash
python bench/probe_gnubg_at_score.py --contact 600 --bearoff 300 --workers 3 \
    --out docs/mesures/t35-sonde-videau-au-score.json
```

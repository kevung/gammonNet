# Les jets d'ouverture au score — gammonNet contre GNU Backgammon

**Date** : 2026-09-02 · **Machine** : bureau (16 cœurs) · **Branche** : `fix/crawford-dead-cube`
· **Outil** : `bench/probe_opening_at_score.py` → `docs/mesures/jets-ouverture-au-score.json`

> **Ce que ce rapport affirme.** Une ressemblance mesurée à GNU Backgammon 1.08.003, sur un corpus
> minuscule et délibérément ciblé : les 15 jets d'ouverture non doubles, à 15 contextes de score.
> Il ne dit pas qui a raison ; il dit **où** les deux moteurs divergent et **par quel mécanisme**.

## La question

« La prise en compte du score par gammonNet semble partielle » — le 64 d'ouverture ne bougeait ni à
gammon-go (4-away/2-away) ni à gammon-save (2-away/4-away). Est-ce un défaut de la table, de la
recherche `use_match`, ou autre chose ?

## Le protocole

Même décision posée quatre fois, 2-ply de chaque côté, sur la position initiale :

| colonne | réglage |
|---|---|
| gnubg cubeless | `hint`, `cubeful off`, filtre de coups grand ouvert (`-1`), élagage gnubg actif |
| gnubg cubeful | idem, `cubeful on` — **ce que gnubg joue et affiche** |
| gammonNet `use_match` | k=12, filtre (0,1,3), feuilles cubeless valuées par la table |
| gammonNet `use_match` + `use_cube` | mêmes réglages, feuilles par le modèle §9, videau centré, x = 0,688 |

Équités ramenées à l'**équité normalisée** (`mwc2eq` de gnubg, ±1 = gagner/perdre le videau
courant). Coups appariés par déplacement net des pions. « Coût » = ce que l'oracle dit que le choix
du testé lui coûte, sur l'échelle de l'oracle. Un match de 7 points ; Crawford posé explicitement.

## Les résultats

Accord du meilleur coup, 225 décisions par paire (15 jets × 15 contextes) :

| paire | accord | coûts > 0,02 | coût max |
|---|---:|---:|---:|
| gammonNet `use_match` vs gnubg **cubeless** | **95 %** | **0** | 0,010 |
| gammonNet `use_match` vs gnubg **cubeful** | 77 % | 27 | 0,064 |
| gnubg cubeless vs gnubg cubeful (contrôle) | 80 % | 23 | 0,071 |
| gammonNet `use_match` + `use_cube` vs gnubg cubeful | **89 %** | **2** | 0,035 |

Par contexte, les 27 écarts de la deuxième ligne se concentrent exactement là où le videau est
vivant et le score dissymétrique ou court : 2a2a (4), 4a2a (5), 2a4a (5), 5a2a (1), 2a5a (5), 3a2a
(1), 2a3a (4), post-Crawford 2a1a (2). Money, 7a7a, 4a4a, DMP et les deux parties de Crawford :
zéro. Le contrôle (troisième ligne) a **le même profil**.

Le 64 à 4-away/2-away, joueur au trait mené (gammon-go) :

| moteur | 1er | 2e | 3e |
|---|---|---|---|
| gnubg cubeless | 24/18 13/9 −0,088 | 8/2 6/2 −0,094 | 24/14 −0,100 |
| gammonNet `use_match` | 24/18 13/9 −0,091 | 8/2 6/2 −0,096 | 24/14 −0,097 |
| gnubg cubeful | **8/2 6/2 +0,350** | 24/18 13/9 +0,307 | 24/14 +0,262 |
| gammonNet `use_cube` | **8/2 6/2 +0,294** | 24/18 13/9 +0,270 | 24/14 +0,241 |

## Ce que cela veut dire

1. **`use_match` est complet et fidèle — sur ce qu'il prétend faire.** Contre le cubeless de gnubg
   (même mécanique : prix de gammon issus de la table, `Utility` dans `eval.c`), 95 % d'accord et
   aucun écart qui coûte, à tous les scores. L'échelle coïncide aussi (Δ moyen +0,008, le biais du
   réseau, identique en money).

2. **Gammon-go et gammon-save sont, à l'ouverture, des effets du videau, pas de la table.** Sans
   videau, le mené à 4-away/2-away a une équité négative (perdre l'envoie à 4-away/1-away Crawford)
   et le prix de ses gammons (0,87) est *inférieur* à celui des gammons adverses (1,48). C'est le
   videau — le mené double tôt, à 2 son gammon vaut le match et les gammons du meneur ne valent
   plus rien — qui renverse l'ordre. Un moteur cubeless au score ne peut pas voir cela, et gnubg
   lui-même ne le voit pas en cubeless.

3. **`use_cube` referme l'écart** : 77 % → 89 %, 27 → 2 écarts coûteux. Les deux restants sont
   post-Crawford 2a1a, où le modèle sous-évalue le double immédiat du mené (+0,74 contre +0,945
   pour gnubg) — un écart de modèle, pas de branchement.

4. **Un défaut trouvé et corrigé par la mesure.** Avant cette branche, `use_cube` en partie de
   Crawford valuait un videau vivant : 4a1a Crawford +0,68 contre +0,16 pour gnubg (cubeful ==
   cubeless dans cette partie), 73 % d'accord contre 93 % en cubeless. `gn_cube_decide` savait ne
   jamais doubler, `gn_cube_value` déroulait quand même la chaîne §9. Corrigé (`348e81e`) : la
   valeur à Crawford est la valeur morte. Après correction, `use_cube` y rend exactement le
   cubeless (93 % / 100 %, lignes `cr_*` du JSON).

## Limites nommées

- 225 décisions sur une seule position : c'est un microscope, pas une mesure de force. La campagne
  T35 reste la référence pour toute affirmation de PR.
- gnubg est comparé à lui-même en cubeful : l'accord dit que nous posons la même question, pas que
  la réponse est juste. Les rollouts (T39) arbitrent.
- L'efficacité x = 0,688 est celle mesurée en money (T34) ; aucun ajustement au score n'a été fait.

# Les invariants qui ne se voient pas

Ce sont les propriétés qu'un refactor peut casser **sans qu'aucun test évident ne tombe**, et sans
qu'aucun message n'apparaisse. Chacune a coûté quelque chose au moins une fois.

## 1. La perspective

`GnPlay.result` a **rendu la main**. La valeur d'un coup, pour celui qui le joue, est la
**négation** de ce que le réseau répond sur la position résultante.

L'inverser ne produit ni plantage ni avertissement : **le moteur joue le meilleur coup de son
adversaire, avec une confiance totale.**

La même règle vaut pour l'**état de match** (l'adversaire est à `away_opponent`, pas à
`away_on_roll`) et pour le **propriétaire du videau** (possédé devient adverse). Les deux se
retournent à chaque ply.

## 2. L'exactitude bit à bit

Le projet en dépend en trois endroits :

- l'**empreinte d'évaluation** qui verrouille un journal de campagne ;
- la **reprise** d'une campagne interrompue, qui doit être identique à un run d'une traite ;
- le **corpus de non-régression**.

Elle est fragile de deux façons :

**La contraction FMA.** Le compilateur fusionne `a×b + c` en un FMA — un arrondi au lieu de deux —
et il le fait **selon la forme du code autour**. `-ffp-contract=off` est posé sur `gn_search.c`, et
sur lui seul : l'appliquer à l'inférence déplacerait les sorties du réseau, donc l'empreinte.

**La largeur du lot.** Le noyau calcule **toujours** `GN_EVAL_BATCH` voies : c'est ce qui garantit
qu'un résultat ne dépend pas du nombre de coups frères. Une largeur variable ferait émettre au
compilateur des chemins différents selon la taille.

## 3. La neutralité du cache d'évaluation

Le cache rejoue les réponses du réseau ; il n'en invente aucune. **La passe d'élagage n'a donc pas
le droit de le lire.**

Si elle le lisait, un candidat serait noté par le **grand** réseau quand le cache le contient et par
le **petit** sinon — le classement, donc le coup joué, dépendrait de l'**historique d'évaluation**.
Rien ne planterait ; les runs cesseraient simplement d'être reproductibles.

Et le petit réseau ne doit **jamais écrire** dans ce cache : une seule de ses distributions y serait
servie comme celle du grand pour le reste du processus.

## 4. La pureté des dés

`roll_at` est une fonction pure de `(graine, essai, ply)`. Rien n'avance, rien n'est reporté.

C'est ce qui rend les dés communs réellement communs entre processus, entre ordres d'exécution et
entre profondeurs. Un générateur à état serait équivalent **seulement** tant que les deux variantes
consommeraient le même nombre de tirages — ce qu'elles ne font pas, l'une pouvant finir une partie
un ply plus tôt. L'échec serait silencieux : la mesure serait plus bruitée, sans que rien ne le
dise.

## 5. Le refus plutôt que l'approximation

- Un modèle non évaluable est **refusé**.
- Un score hors table **arrête** la mesure.
- Un coup de GNU Backgammon inappariable **arrête** la mesure au lieu d'être deviné — et c'est ce
  refus qui a révélé que les deux générateurs gardent parfois des intermédiaires différents du même
  coup composé.
- Le filtre est respecté : `prune_k` est relevé à `filter[depth]` quand il est plus petit, sinon on
  chercherait moins de candidats que l'appelant n'en a demandé, et le classement aurait l'air
  normal.

## 6. Ne jamais analyser la notation de coup de GNU Backgammon

L'appariement se fait **par position résultante**, en réutilisant le codec déjà vérifié. Une
seconde façon, non vérifiée, de lire un coup est une source d'erreur silencieuse.

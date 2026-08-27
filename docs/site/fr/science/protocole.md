# Le protocole de mesure

## Ce qu'une affirmation de force doit porter

Trois choses, toujours : **le protocole, le volume, l'intervalle de confiance**. Une force
affirmée sans ces trois-là n'a pas sa place dans ce projet, même sur une page d'accueil.

Il y a une raison quantitative à cette exigence : **en dessous d'environ un million de parties par
paire, les écarts entre bons moteurs ne sortent pas du bruit.** Un chiffre sans son intervalle
laisse croire à une précision qui n'existe pas.

## Les dés communs, et pourquoi ils changent tout

Comparer deux moteurs en leur faisant jouer des parties différentes revient à mesurer la chance
autant que la compétence. Toutes les mesures de force de ce projet emploient des **paires
dupliquées** : la même partie est jouée deux fois, avec les mêmes dés, les moteurs échangeant leurs
places.

Deux conséquences :

- La variance chute de plusieurs ordres de grandeur.
- **Un moteur contre lui-même totalise exactement zéro**, à n'importe quel score. C'est un test, et
  il a servi : il a fallu coller le score au siège plutôt que de le faire voyager avec les moteurs
  pour que la propriété tienne.

Les dés sont une **fonction pure** de `(graine, essai, ply)` — rien n'avance, rien n'est reporté
d'un appel à l'autre. C'est ce qui rend les dés communs réellement communs entre processus, entre
ordres d'exécution et entre profondeurs de récursion. Un générateur à état ne serait équivalent
que tant que les deux variantes consommeraient exactement le même nombre de tirages, ce qu'elles ne
font pas ; l'échec serait **silencieux** — la mesure serait simplement plus bruitée, sans que rien
ne le dise.

## Le bootstrap porte sur les paires, jamais sur les parties

Les deux manches d'une paire partagent leurs dés : elles ne sont **pas indépendantes**. Un
bootstrap sur les parties donnerait un intervalle faussement étroit.

## L'arbitre, et pourquoi il en faut deux

Quand deux moteurs choisissent des coups différents, il faut un tiers pour dire lequel a raison —
et **aucun tiers n'est neutre** :

| Colonne | Arbitre | Biais |
|---|---|---|
| la nôtre | rollout conduit par notre réseau | en notre faveur |
| la leur | GNU Backgammon à profondeur supérieure | en leur faveur |

**Aucune n'est publiée seule.** Le résultat qui vaut quelque chose est celui où les deux colonnes
s'accordent sur le signe : si notre propre arbitre et le leur disent tous deux la même chose, la
conclusion survit au choix de l'arbitre.

## L'empreinte d'évaluation

Chaque journal de campagne porte une **empreinte** du moteur qui l'a produit — un condensé des
sorties du réseau sur des positions fixes. Un build numériquement différent est **refusé** à
l'ouverture du journal, au lieu de mélanger silencieusement deux moteurs dans une même mesure.

C'est ce qui permet à une campagne de plusieurs jours d'être **interrompue et reprise** en restant
identique à un run d'une traite.

## Ce que le projet refuse

- **Conclure « ça marche » sans avoir lancé la commande et lu sa sortie.**
- **Déduire une performance d'une lecture de code.** Aucun chiffre de débit, de latence ou de
  taille ne se tire d'une extrapolation. Ce volet contient plusieurs projections que la mesure a
  démenties ; elles y sont pour cette raison.
- **Approximer plutôt que refuser.** Un score hors de la table d'équité de match arrête la
  mesure ; il ne la fait pas retomber silencieusement en money.

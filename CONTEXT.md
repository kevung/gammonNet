# gammonNet

Un évaluateur de positions de backgammon : une position entre, une évaluation sort. Ce
glossaire fixe le vocabulaire de la **règle de frontière** (`CLAUDE.md`) — *ce dépôt évalue
une position, il ne connaît pas ses appelants* — parce que c'est la confusion de trois mots
voisins qui l'a laissée s'éroder.

## Qui appelle, et qui exécute

**Cible** :
Une forme d'exécution que ce dépôt produit et possède — le natif, `gammonnet serve`, le
module WebAssembly. Une cible se nomme, se mesure et se compare ici, parce qu'elle est à
nous.
_Éviter_ : plateforme, backend

**Runtime** :
L'environnement dans lequel une cible s'exécute et qui décide du coût d'une opération — un
processus système, un pool de workers du navigateur. Deux cibles peuvent partager un
langage et pas un runtime ; c'est le runtime qui tranche, pas le langage.

**Appelant** :
Quiconque appelle la bibliothèque. **Anonyme par construction** : le dépôt ne le nomme pas,
ne compte pas les appelants, ne leur prescrit rien et ne justifie aucune décision par eux.
Un besoin d'appelant entre ici comme une **capacité** à fournir, jamais comme une identité à
servir.
_Éviter_ : **consommateur**, client, aval, downstream — chacun de ces mots suppose un lien
de subordination que ce dépôt n'a pas à porter

**Portage** :
Une réimplémentation indépendante du même modèle dans un autre langage. Ce n'est ni une
cible, ni une dépendance : c'est une **origine de mesures**. Un portage entre dans ce dépôt
par ses chiffres, jamais par son nom ni par ce qu'on attendrait de lui.

## Ce qui autorise un nombre

**Source** :
Le rendu dont un nombre est effectivement lu. La table d'équité de match a une seule source,
`Kazaross-XG2.xml`, et une seule attribution, Neil Kazaross. Une source crée une obligation
de licence.

**Témoin** :
Un rendu tiers du même nombre, consulté pour vérifier une transcription. Un témoin ne crée
**aucune** obligation d'attribution, parce que rien n'en est dérivé — et un témoin peut être
moins complet que la source, auquel cas c'est la source qui fait foi.
_Éviter_ : précédent, référence, second témoin

**Export canonique** :
Un fichier de données que ce dépôt produit pour qu'une valeur n'ait **qu'une seule
écriture**. Il se justifie par le coût des recopies constaté ici ; jamais par l'identité de
qui le lit.

## Ce qui voyage entre les cibles

**Optimisation conceptuelle** :
Une optimisation dont le gain survit à un changement de langage, et qui voyage donc avec sa
**condition d'application** — sans quoi elle est une régression qui se croit une
optimisation. Elle se décide, se mesure et s'écrit ici (ADR-0003).

**Optimisation d'implémentation** :
Une optimisation dont le gain est un artefact du langage ou du compilateur. Elle reste chez
celui qui la porte, sans remontée.

**Mesure** :
Un chronométrage daté, avec son protocole, son volume et son intervalle de confiance. Une
mesure venue d'ailleurs entre ici **comme une mesure** — une donnée — et jamais comme une
relation.
_Éviter_ : estimation, ordre de grandeur, gain attendu

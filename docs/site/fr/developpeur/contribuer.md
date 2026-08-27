# Contribuer

## Les trois règles non négociables

### 1. Rien de non-libre dans un artefact distribué

Un module WebAssembly servi à un navigateur **est une distribution**.

| Interdit | Motif |
|---|---|
| Poids GNU Backgammon, ou tout dérivé | GPL-3 |
| Code GNU Backgammon copié dans le pipeline | œuvre dérivée |
| Réseaux sous clause non commerciale | hors du périmètre de licence |

| Autorisé | Fondement |
|---|---|
| Lire le code et le manuel de GNU Backgammon | la GPL régit la distribution, pas la lecture |
| Le faire tourner comme **oracle de mesure** | *« The output of a program is not, in general, covered by the copyright on the code of the program »* |
| Réimplémenter des idées documentées | une idée n'est pas une œuvre |
| Tables de fin de partie, quelle que soit leur origine | calcul exact reproductible |

**En cas de doute sur une source : ne pas l'intégrer, et poser la question.** Une brique
juridiquement douteuse embarquée dans un artefact distribué est le seul type d'erreur qu'un
correctif ne rattrape pas.

Le répertoire `docs/etudes/` tient le **registre des idées lues et réimplémentées** — la mémoire de
ce qui a été lu, et quand.

### 2. Aucune force n'est affirmée sans mesure

Toute affirmation cite **le protocole, le volume et l'intervalle de confiance**. Une force affirmée
sans ces trois-là n'entre pas, même dans un message de commit.

### 3. Une conclusion de performance se mesure

Aucun chiffre de débit, de latence ou de taille ne se tire d'une lecture de code. Ce dépôt contient
**quatre projections d'optimisation démenties par la mesure**, dont une qui allait dans le mauvais
sens : elles sont conservées, avec leur chiffre, pour que personne ne les refasse.

## Ce qui est attendu d'un changement

- **Un test de non-régression** pour tout composant numérique. Un changement qui déplace une sortie
  doit le faire **visiblement**.
- **Une fiche de mesure** dans `docs/mesures/` pour toute mesure, avec sa commande de reproduction.
- **Des commits atomiques**, au fil de l'eau. Le message dit *pourquoi*, pas *quoi* — le diff dit
  déjà quoi.
- **Consigner ce qui n'a pas marché.** Une branche abandonnée avec sa mesure vaut mieux qu'un
  silence : c'est ce qui empêche la prochaine personne de refaire le même essai.

## La nomenclature

Un réseau ne devient un autre réseau **que si ses poids changent**. Ni le couplage à une table, ni
la compilation en WebAssembly, ni une conversion de format n'en produisent un nouveau. Une
quantification donne « X quantifié », pas « Y ».

Les poids portent donc le nom de leur auteur ; **gammonNet** nomme la configuration.

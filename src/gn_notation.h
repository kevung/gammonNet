/*
 * gn_notation.h -- naming the play that was chosen.
 *
 * ── POURQUOI CECI EST DANS CE DÉPÔT (T86) ──────────────────────────────
 *
 * `CLAUDE.md` pose la frontière : *« ce dépôt évalue une position, il ne
 * connaît pas ses appelants »*, et une notation ressemble d'abord à de la
 * présentation. Trois faits disent le contraire, et c'est le troisième qui
 * tranche.
 *
 *   1. gammonNet PUBLIE DÉJÀ cette notation, sur son autre surface : le champ
 *      `move` de `/v1/eval` (`format_play`, `tools/serve.py`). La question
 *      n'est donc pas « faut-il l'écrire » mais « pourquoi une seule des deux
 *      surfaces publiées la donne ». La même question s'est posée pour le
 *      référentiel des probabilités, et v1.1.0 l'a tranchée du même côté :
 *      les deux surfaces disent la même chose.
 *
 *   2. Elle n'est PAS reconstructible depuis ce que la surface WebAssembly
 *      rend. `resultId` est un PLATEAU, et un plateau ne dit pas quel pion
 *      est allé où : deux appariements différents peuvent laisser le même
 *      plateau. Une reconstruction par différence de plateaux ne peut donc
 *      pas faire mieux qu'un appariement plausible : sur une position
 *      ambiguë, elle nomme un coup que la recherche n'a pas littéralement
 *      choisi. Ce n'est pas une conjecture, c'est ce que l'ambiguïté du
 *      plateau impose à quiconque tente la reconstruction.
 *
 *   3. Donc ce n'est pas une présentation qu'on ajoute, c'est UNE PARTIE DE
 *      LA RÉPONSE QU'ON CESSE DE JETER. La recherche connaît la liste ordonnée
 *      des sous-coups (`GnPlay.moves`) ; la frontière WebAssembly la perdait
 *      en ne rendant que le plateau d'arrivée. Nommer le coup retenu, c'est
 *      dire lequel on a retenu.
 *
 * ── ET SI C'EST ÉCRIT, C'EST LA MÊME QUE CELLE DU PYTHON ───────────────
 *
 * Une troisième notation aurait remplacé une vérité en trop par une vérité en
 * trop. Ce fichier est donc le PORT EXACT de `format_play` / `_point_number`
 * de `tools/serve.py`, et `python/gammonnet/notation.py` fait maintenant
 * appeler celui-ci par le serveur : il n'y a plus qu'une écriture, et
 * `tests/test_notation.py` la tient.
 *
 * La renumérotation ne fait pas appel à une seconde convention : `gn_rules.h`
 * dit déjà que « l'indice i désigne le point (i+1) pour BLANC et (24-i) pour
 * NOIR », et cette formule, lue pour la couleur au trait, EST la numérotation
 * propre de chaque joueur (le point le plus proche de la sortie vaut 1).
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_NOTATION_H
#define GN_NOTATION_H

#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Assez pour quatre sous-coups distincts : « bar/24 » fait six caractères,
 * trois séparateurs, un terminateur. La marge est volontaire ; la fonction
 * refuse plutôt que de tronquer.
 */
#define GN_NOTATION_LENGTH 40

/*
 * Écrit la notation de `play`, vue par `mover`, dans `out`
 * (GN_NOTATION_LENGTH octets). Par exemple `24/18 13/11(2)`.
 *
 * Les sous-coups identiques sont regroupés, dans l'ordre de leur PREMIÈRE
 * apparition — c'est ce que fait le Python, et l'ordre importe : il est celui
 * que la recherche a produit, pas un ordre inventé au moment d'afficher.
 *
 * Un jeu vide (aucun coup légal) rend la chaîne vide, et c'est une réponse :
 * la position où l'on ne peut rien jouer existe.
 *
 * Rend 0, ou -1 si `mover` n'est pas un joueur ou si un sous-coup sort des
 * bornes.
 */
int gn_play_notation(const GnPlay *play, int mover, char *out);

#ifdef __cplusplus
}
#endif

#endif /* GN_NOTATION_H */

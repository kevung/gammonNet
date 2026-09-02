/*
 * gn_notation.c -- le port exact de `format_play` / `_point_number`
 * (`tools/serve.py`). Voir `gn_notation.h` pour ce qui justifie qu'il existe.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <string.h>

#include "gn_notation.h"

/*
 * Le numéro d'un point DANS LA NUMÉROTATION DU JOUEUR AU TRAIT.
 *
 * `gn_rules.h` : « l'indice i désigne le point (i+1) pour BLANC et (24-i) pour
 * NOIR ». Lue pour la couleur au trait, cette formule est déjà la numérotation
 * propre de chaque joueur — le point d'as, le plus proche de la sortie, vaut 1
 * pour les deux. Aucune seconde convention n'est introduite ici.
 *
 * `out` reçoit au plus quatre caractères ("bar", "off", ou un nombre à deux
 * chiffres) plus le terminateur.
 */
static int point_name(int index, int mover, char *out)
{
    if (index == GN_BAR) {
        memcpy(out, "bar", 4);
        return 0;
    }
    if (index == GN_OFF) {
        memcpy(out, "off", 4);
        return 0;
    }
    if (index < 0 || index >= GN_NUM_POINTS) {
        return -1;
    }
    const int number = (mover == GN_WHITE) ? (index + 1) : (GN_NUM_POINTS - index);
    snprintf(out, 4, "%d", number);
    return 0;
}

int gn_play_notation(const GnPlay *play, int mover, char *out)
{
    if (play == NULL || out == NULL
        || (mover != GN_WHITE && mover != GN_BLACK)) {
        return -1;
    }

    out[0] = '\0';
    const int n = play->num_moves;
    if (n <= 0) {
        /* Aucun sous-coup : la chaîne vide, et c'est une réponse. Le Python
         * fait exactement cela (`if not order: return ""`). */
        return (n == 0) ? 0 : -1;
    }
    if (n > GN_MAX_MOVES_PER_PLAY) {
        return -1;
    }

    /* Les paires, dans l'ordre de PREMIÈRE apparition, et leur compte. Au
     * plus quatre sous-coups, donc au plus quatre paires : pas d'allocation. */
    char sources[GN_MAX_MOVES_PER_PLAY][4];
    char targets[GN_MAX_MOVES_PER_PLAY][4];
    int counts[GN_MAX_MOVES_PER_PLAY];
    int distinct = 0;

    for (int i = 0; i < n; i++) {
        char from[4];
        char to[4];
        if (point_name(play->moves[i].from, mover, from) != 0
            || point_name(play->moves[i].to, mover, to) != 0) {
            return -1;
        }
        int found = -1;
        for (int k = 0; k < distinct; k++) {
            if (strcmp(sources[k], from) == 0 && strcmp(targets[k], to) == 0) {
                found = k;
                break;
            }
        }
        if (found >= 0) {
            counts[found]++;
        } else {
            memcpy(sources[distinct], from, sizeof from);
            memcpy(targets[distinct], to, sizeof to);
            counts[distinct] = 1;
            distinct++;
        }
    }

    size_t written = 0;
    for (int k = 0; k < distinct; k++) {
        const int room = (int)(GN_NOTATION_LENGTH - written);
        const int put = (counts[k] > 1)
            ? snprintf(out + written, (size_t)room, "%s%s/%s(%d)",
                       (k == 0) ? "" : " ", sources[k], targets[k], counts[k])
            : snprintf(out + written, (size_t)room, "%s%s/%s",
                       (k == 0) ? "" : " ", sources[k], targets[k]);
        /* Tronquer serait rendre une notation FAUSSE et plausible ; on refuse.
         * La borne est dimensionnée pour que ce cas n'arrive pas. */
        if (put < 0 || put >= room) {
            out[0] = '\0';
            return -1;
        }
        written += (size_t)put;
    }
    return 0;
}

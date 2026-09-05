/*
 * gn_wasm.c -- the WebAssembly face of the evaluator.
 *
 * A shim, deliberately thin. Everything it exposes already exists in
 * `src/gn_infer.h`; what it adds is the two things a browser needs and a native
 * process does not:
 *
 *   1. Loading a model from BYTES rather than from a path. The model arrives
 *      over `fetch`, and there is no filesystem to point at.
 *   2. A single-network global. A page evaluates with one network at a time,
 *      and threading a handle through the JS boundary would buy nothing.
 *
 * On the file trick: `nn_load` of the reference engine takes a path. Rather
 * than fork it -- which would mean maintaining a second reader of the `.bin`
 * format, the exact thing `tools/export_model.py` refuses to do for the writer
 * -- the bytes are written into Emscripten's in-memory filesystem and the path
 * handed to the unmodified loader. MEMFS is RAM; there is no device behind it.
 * The cost is one transient copy of the model, about 2 MiB, freed immediately.
 *
 * SPDX-License-Identifier: MIT
 */

/*
 * `EMSCRIPTEN_KEEPALIVE` sous garde, et ce n'est pas de la politesse : sans
 * elle, ce fichier ne compile que là où Emscripten est installé — donc il ne
 * se vérifie nulle part ailleurs, et une faute de type y survit jusqu'au
 * poste qui sait construire le WASM. Avec la garde, `cc -c` le contrôle
 * partout ; seul l'édition de liens WebAssembly reste propre à emcc.
 */
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

#include <stdio.h>
#include <stdlib.h>

#include "gn_encoding.h"
#include "gn_bearoff.h"
#include "gn_cube.h"
#include "gn_evalcache.h"
#include "gn_gemm_int8.h"
#include "gn_infer.h"

static GnNetwork *g_network = NULL;
static GnNetwork *g_prune = NULL;
static int g_prune_k = 0;
static GnBearoff *g_bearoff = NULL;
static GnEvalCache *g_cache = NULL;

/* MEMFS, not a real path: RAM that `fopen` happens to understand. */
static const char *MODEL_PATH = "/gammonnet-model.bin";
static const char *PRUNE_PATH = "/gammonnet-prune.bin";
static const char *BEAROFF_PATH = "/gammonnet-bearoff.bin";

/*
 * Load a network from a byte buffer.
 *
 * Returns 0 on success. Every non-zero return is a refusal, never a
 * degraded mode:
 *   -1  the buffer could not be staged
 *   -2  the model was rejected by `gn_network_load` -- unreadable, not prob5,
 *       or expecting an input size that is not ours
 */
EMSCRIPTEN_KEEPALIVE
int gnw_load_model(const unsigned char *bytes, int length)
{
    if (bytes == NULL || length <= 0) {
        return -1;
    }

    if (g_network != NULL) {
        gn_network_free(g_network);
        g_network = NULL;
    }

    FILE *staged = fopen(MODEL_PATH, "wb");
    if (staged == NULL) {
        return -1;
    }
    size_t written = fwrite(bytes, 1, (size_t)length, staged);
    fclose(staged);
    if (written != (size_t)length) {
        remove(MODEL_PATH);
        return -1;
    }

    g_network = gn_network_load(MODEL_PATH);
    remove(MODEL_PATH);

    return (g_network == NULL) ? -2 : 0;
}

/*
 * Charger le réseau d'ÉLAGAGE et fixer combien de candidats il laisse passer.
 *
 * `k <= 0` l'éteint et rend la recherche d'avant, bit pour bit. Le défaut natif
 * est 12 : mesuré 98,3 % d'accord avec la recherche non élaguée en contact et
 * une perte dans le bruit, pour x3,9 (docs/mesures/2026-08-27-T3D-...).
 *
 * Ce que ce gain devient DANS UN NAVIGATEUR n'est pas connu : il vient du
 * remplissage des lots, et le lot y rend x2,21 et non x8,5 (T21). Cette
 * fonction existe pour que ce soit MESURÉ là-bas, pas transporté d'ici.
 *
 * Retours : 0 succès, -1 tampon inutilisable, -2 modèle refusé.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_load_prune(const unsigned char *bytes, int length, int k)
{
    if (g_prune != NULL) {
        gn_network_free(g_prune);
        g_prune = NULL;
    }
    g_prune_k = 0;

    if (bytes == NULL || length <= 0 || k <= 0) {
        return (k <= 0) ? 0 : -1;   /* k nul : extinction demandée, pas une faute */
    }

    FILE *staged = fopen(PRUNE_PATH, "wb");
    if (staged == NULL) {
        return -1;
    }
    const size_t written = fwrite(bytes, 1, (size_t)length, staged);
    fclose(staged);
    if (written != (size_t)length) {
        remove(PRUNE_PATH);
        return -1;
    }

    g_prune = gn_network_load(PRUNE_PATH);
    remove(PRUNE_PATH);
    if (g_prune == NULL) {
        return -2;
    }
    g_prune_k = k;
    return 0;
}

EMSCRIPTEN_KEEPALIVE
int gnw_prune_k(void)
{
    return (g_prune == NULL) ? 0 : g_prune_k;
}

EMSCRIPTEN_KEEPALIVE
int gnw_is_loaded(void)
{
    return g_network != NULL;
}

EMSCRIPTEN_KEEPALIVE
int gnw_num_features(void)
{
    return GN_NUM_FEATURES;
}

EMSCRIPTEN_KEEPALIVE
int gnw_num_outputs(void)
{
    return GN_NUM_OUTPUTS;
}

/*
 * Evaluate an encoded feature vector. `out` receives the five probabilities.
 * Returns 0, or -1 if no network is loaded.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_evaluate_features(const float *features, float *out)
{
    if (g_network == NULL) {
        return -1;
    }
    return gn_evaluate_features(g_network, features, out);
}

/*
 * Evaluate `count` feature vectors laid out back to back.
 *
 * The bench path, and any caller analysing a whole match at once. One
 * boundary crossing for
 * many evaluations: at 0-ply speeds the JS/WASM call overhead would otherwise
 * be a large share of what we are trying to measure, and we would be timing
 * the boundary rather than the network.
 *
 * T91: it goes through the BATCH kernel, not a loop over the scalar door.
 * The loop was the last thing in this artifact that needed
 * `-fassociative-math` --
 * `nn_forward_prob5` accumulates in one variable, so the only way to speed it
 * up was to let the compiler reassociate that sum, which cost the module its
 * bit-exact parity with the native engine. The batch kernel is faster AND bit
 * for bit, so the flag is gone and this call is what replaces it.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_evaluate_batch(const float *features, float *out, int count)
{
    if (g_network == NULL || count < 0) {
        return -1;
    }
    return gn_evaluate_features_batch(g_network, features, count,
                                      (float (*)[GN_NUM_OUTPUTS])out);
}

EMSCRIPTEN_KEEPALIVE
float gnw_money_equity(const float *probs)
{
    return gn_money_equity(probs);
}

EMSCRIPTEN_KEEPALIVE
void gnw_free_model(void)
{
    if (g_network != NULL) {
        gn_network_free(g_network);
        g_network = NULL;
    }
    /* Le réseau d'élagage part avec : le laisser derrière ferait qu'une page
     * qui recharge un modèle continuerait d'élaguer avec l'ancien, sans que
     * rien ne le dise. */
    if (g_prune != NULL) {
        gn_network_free(g_prune);
        g_prune = NULL;
    }
    g_prune_k = 0;
}

/*
 * Whether this build was compiled with WASM SIMD.
 *
 * T21 compares a SIMD build against a scalar one, and the only thing worse
 * than an unmeasured penalty is a measurement that silently timed the wrong
 * binary. The flag is baked in at compile time so a loaded module can always
 * say which one it is.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_has_simd(void)
{
#ifdef __wasm_simd128__
    return 1;
#else
    return 0;
#endif
}

/* ── Recherche ──────────────────────────────────────────────────────
 *
 * T21 a rendu son verdict en multipliant un débit d'évaluations MESURÉ par un
 * nombre d'évaluations par décision SUPPOSÉ, puis mesuré par T30. Les deux
 * moitiés sont solides, mais leur produit reste une projection : il suppose que
 * rien d'autre ne coûte, ni la génération des coups, ni l'encodage, ni le
 * parcours de l'arbre.
 *
 * Ces entrées exposent la recherche complète pour qu'une VRAIE décision soit
 * chronométrée dans un VRAI navigateur. C'est la dernière projection du projet
 * qui devient une mesure.
 */

#include "gn_met.h"
#include "gn_notation.h"
#include "gn_position_id.h"
#include "gn_search.h"

/*
 * Décider d'un coup, à partir d'un identifiant de position.
 *
 * L'identifiant plutôt que la structure : il traverse la frontière JavaScript
 * sans que les deux côtés aient à s'accorder sur un agencement de champs, et
 * c'est le codec de T02 -- déjà croisé avec GNU Backgammon -- qui le lit.
 *
 * `out_id` reçoit l'identifiant de la position résultante (au moins 16 octets).
 * `out_evaluations` reçoit le nombre d'évaluations réseau consommées : c'est
 * l'unité que T21 chronomètre, et l'avoir ici rend le coût d'une décision
 * vérifiable plutôt que déduit.
 *
 * Renvoie l'équité du coup retenu -- du point de vue de celui qui le joue --
 * ou -99.0 si la position est illisible, si aucun coup n'est légal, ou si le
 * score demandé sort de la table. Refusé, jamais approximé.
 */
/*
 * ── Les trois réglages qui manquaient, et ce qu'ils changent ─────────
 *
 * Le module exposait la profondeur, les filtres et l'élagage. Trois leviers
 * mesurés du moteur natif restaient inatteignables depuis un navigateur, dont
 * un que l'artefact livre pourtant.
 */

/*
 * LA TABLE EXACTE DE FIN DE PARTIE.
 *
 * L'artefact publie `bearoff_one_sided.bin` — et jusqu'ici rien ne pouvait le
 * charger. T38 a mesuré ce qu'elle comble : 0,00028 d'équité par décision de
 * bearoff, un déficit réel, comblé avec CERTITUDE et non approché. Sans elle
 * la recherche retombe sur le réseau, silencieusement.
 *
 * `length <= 0` la retire. Retours : 0 succès, -1 tampon inutilisable,
 * -2 table refusée.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_load_bearoff(const unsigned char *bytes, int length)
{
    if (g_bearoff != NULL) {
        gn_bearoff_set_shared(NULL);
        gn_bearoff_close(g_bearoff);
        g_bearoff = NULL;
    }
    if (bytes == NULL || length <= 0) {
        return 0;                     /* retrait demandé, pas une faute */
    }

    FILE *staged = fopen(BEAROFF_PATH, "wb");
    if (staged == NULL) {
        return -1;
    }
    const size_t written = fwrite(bytes, 1, (size_t)length, staged);
    fclose(staged);
    if (written != (size_t)length) {
        remove(BEAROFF_PATH);
        return -1;
    }

    g_bearoff = gn_bearoff_open(BEAROFF_PATH);
    /* Le fichier N'EST PAS retiré : la table est lue à la demande, pas
     * chargée d'un bloc — 6,9 Mio qu'on ne veut pas voir deux fois en
     * mémoire. */
    return (g_bearoff == NULL) ? -2 : (gn_bearoff_set_shared(g_bearoff), 0);
}

/*
 * LE CACHE D'ÉVALUATION.
 *
 * Il rejoue les réponses du réseau, jamais n'en invente : T3A a vérifié qu'il
 * ne change AUCUN résultat, et mesuré ce qu'il rapporte — ×1,35 en contact,
 * ×4,6 en course à 2-ply, où les mêmes positions reviennent sans cesse.
 *
 * `log2_entries` dit sa taille : 21 donne deux millions d'entrées, le réglage
 * de la campagne T35. 0 le désactive.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_enable_cache(int log2_entries)
{
    if (g_cache != NULL) {
        gn_evalcache_set_shared(NULL);
        gn_evalcache_free(g_cache);
        g_cache = NULL;
    }
    if (log2_entries <= 0) {
        return 0;
    }
    g_cache = gn_evalcache_create((unsigned)log2_entries);
    if (g_cache == NULL) {
        return -1;
    }
    gn_evalcache_set_shared(g_cache);
    return 0;
}

/*
 * Les N MEILLEURS COUPS, avec tout ce qu'une analyse affiche.
 *
 * `gnw_best_play` ne rend que le premier, ce qui suffit pour jouer et pas pour
 * ANALYSER : une interface montre les candidats, leur classement, leur équité
 * et les cinq probabilités des deux camps. C'est ce que fait `bench/pr.py` et
 * `bench/analyse_match.py` en natif ; il n'y avait pas d'équivalent ici.
 *
 * `out` reçoit, par candidat et dans cet ordre :
 *
 *     [0]   équité du coup, du point de vue de celui qui le joue
 *     [1..5] les cinq probabilités, DU MÊME POINT DE VUE
 *     [6..12] l'identifiant de la position résultante, 14 octets + NUL,
 *             écrits par `out_ids` et non ici
 *
 * soit 6 flottants par candidat dans `out`, et 15 octets par candidat dans
 * `out_ids`. Rend le nombre de candidats écrits, ou -1.
 *
 * UN SEUL RÉFÉRENTIEL, ET C'EST CELUI DU JOUEUR QUI JOUE (v1.1.0).
 *
 * `GnCandidate.probs` décrit la position RÉSULTANTE — donc l'adversaire,
 * comme `gn_search.h` le dit sans détour — tandis que `GnCandidate.equity` du
 * même candidat est déjà retournée du côté du joueur. Cette fonction laissait
 * passer les deux tels quels : deux points de vue opposés dans le même objet,
 * et rien en aval ne pouvait s'en apercevoir, une distribution imbriquée
 * retournée restant parfaitement imbriquée. Sur l'ouverture 3-1, un appelant
 * lisait « 44,56 % de victoires » sous une équité de +0,166 ; c'est arrivé,
 * deux fois.
 *
 * `handle_eval` de `tools/serve.py` a retourné la distribution le 2026-08-29
 * pour `/v1/eval`. Les deux surfaces publiées de gammonNet disent donc
 * maintenant la même chose, et c'est ce que v1.1.0 acte. Le contrôle qui mord
 * est l'identité elle-même : l'équité cubeless money est une fonction DES
 * cinq probabilités, donc à 0-ply, recalculer l'une depuis les autres doit
 * reproduire l'autre — `verify/api_invariants.mjs` le vérifie, et aucune
 * tolérance ne cache une inversion.
 *
 * CE QUI RESTE VRAI ET QU'IL FAUT SAVOIR : au-delà de 0-ply, ces cinq nombres
 * viennent de la passe superficielle qui a servi à classer, pas de la
 * recherche profonde qui a produit l'équité (`gn_search.h`, `GnCandidate`).
 * Le référentiel est le bon ; la PROFONDEUR ne l'est pas. `/v1/eval` tranche
 * autrement — il les omet dès que `ply > 0` plutôt que d'en montrer d'une
 * autre profondeur. Ici on les garde, parce qu'une interface d'analyse les
 * affiche, et on le dit.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_rank_plays(const char *position_id, int turn, int d1, int d2,
                   int ply, int filter_top, int filter_inner,
                   int use_match, int away_on_roll, int away_opponent,
                   int cube, int crawford,
                   int cube_owner, double efficiency,
                   int max_out, float *out, char *out_ids, char *out_notations)
{
    if (g_network == NULL || position_id == NULL || out == NULL
        || max_out <= 0) {
        return -1;
    }

    GnPosition position;
    if (gn_position_from_id(position_id, turn, &position) != 0) {
        return -1;
    }

    GnSearchConfig config;
    if (use_match) {
        const GnMatchState state = {away_on_roll, away_opponent, cube, crawford};
        config = gn_search_config_match(ply, &state);
        if (!config.use_match) {
            return -1;   /* score hors table : refusé, pas rabattu en money */
        }
    } else {
        config = gn_search_config(ply);
    }
    if (filter_top > 0 && ply >= 1) {
        /*
         * LE FILTRE EST ÉLARGI À CE QUE L'APPELANT DEMANDE.
         *
         * Le filtre de coups ne réévalue en profondeur que ses `filter_top`
         * premiers ; les suivants gardent une équité d'une passe plus
         * superficielle. Rendus tels quels dans une même liste, les deux
         * échelles se mélangent et le classement cesse d'être un classement :
         * sur l'ouverture 3-1 à `filter_top = 3`, le 4e coup rendu (-0,0080)
         * était MEILLEUR que le 3e (-0,0135), simplement parce qu'il n'avait
         * pas été cherché aussi loin.
         *
         * `bestPlay` ne souffrait pas de cela — un filtre à 3 suffit pour
         * désigner le meilleur. Une API qui promet « les N meilleurs coups avec
         * leurs statistiques » doit, elle, les avoir tous cherchés à la même
         * profondeur. Le coût monte avec N, et c'est le prix juste.
         */
        config.filter[ply] = (filter_top < max_out) ? max_out : filter_top;
    }
    if (filter_inner > 0 && ply >= 2) {
        config.filter[ply - 1] = filter_inner;
    }
    gn_search_use_prune(&config, g_prune, g_prune_k);
    /* La valuation CUBEFUL des feuilles, quand un videau est en jeu. Elle ne
     * change pas la décision de videau — elle change le COUP : audacieux vers
     * l'encaissement quand on possède le videau, sobre quand on l'a contre
     * soi. `cube_owner < 0` la laisse éteinte, et la recherche reste cubeless.
     * L'efficacité est MESURÉE (bench/fit_efficiency.py), jamais empruntée. */
    if (cube_owner >= 0) {
        gn_search_use_cube(&config, cube_owner, efficiency);
    }

    /*
     * THE BUFFER IS THE WHOLE LEGAL MOVE LIST, NEVER `max_out`.
     *
     * `rank_plays` truncates to the buffer size BEFORE evaluating anything, in
     * move-generation order -- so a buffer of `max_out` would rank `max_out`
     * ARBITRARY plays and call them the best. Measured on the opening 3-1:
     * `max_out = 3` returned a second-best move at -0.1262 where the full list
     * finds -0.0029. The N best moves must not depend on N.
     *
     * `gn_rollout.c` states the same constraint for the same reason. This
     * wrapper walked into it anyway; the fix is to rank everything and emit
     * only what the caller asked for.
     */
    GnCandidate *candidates = malloc(sizeof(GnCandidate) * (size_t)GN_MAX_PLAYS);
    if (candidates == NULL) {
        return -1;
    }
    const int ranked = gn_search_plays(g_network, &position, d1, d2, &config,
                                       candidates, GN_MAX_PLAYS);
    if (ranked <= 0) {
        free(candidates);
        return ranked;
    }
    const int count = (ranked < max_out) ? ranked : max_out;

    for (int i = 0; i < count; i++) {
        const float *p = candidates[i].probs;
        out[i * 6 + 0] = (float)candidates[i].equity;
        /* Le retournement, ici et une seule fois : mes gammons perdus sont ses
         * gammons gagnés, et P(gain) se complémente. Même opération que
         * `invert_probs` dans `gn_search.c` et que `Evaluation.mirrored()` en
         * Python — trois écritures d'un fait, aucune n'étant l'endroit où le
         * mettre en commun sans traverser la frontière du module. */
        out[i * 6 + 1 + GN_P_WIN]     = 1.0f - p[GN_P_WIN];
        out[i * 6 + 1 + GN_P_WIN_G]   = p[GN_P_LOSE_G];
        out[i * 6 + 1 + GN_P_WIN_BG]  = p[GN_P_LOSE_BG];
        out[i * 6 + 1 + GN_P_LOSE_G]  = p[GN_P_WIN_G];
        out[i * 6 + 1 + GN_P_LOSE_BG] = p[GN_P_WIN_BG];
        if (out_ids != NULL) {
            gn_position_id(&candidates[i].play.result, out_ids + (size_t)i * 15);
        }
        /* LE NOM DU COUP, et non seulement le plateau qu'il laisse. Le
         * plateau est ambigu — deux appariements peuvent le produire — donc
         * le rendre seul revient à jeter la moitié de la réponse : quel coup
         * la recherche a retenu. Voir `gn_notation.h`. */
        if (out_notations != NULL) {
            gn_play_notation(&candidates[i].play, (int)position.turn,
                             out_notations + (size_t)i * GN_NOTATION_LENGTH);
        }
    }
    free(candidates);
    return count;
}

/*
 * LA DÉCISION DE VIDEAU, avec ses équités et non seulement son verdict.
 *
 * `out` reçoit, dans cet ordre :
 *
 *     [0] l'action : 0 pas de double, 1 double/prend, 2 double/passe,
 *         3 trop bon pour doubler
 *     [1] l'équité si l'on ne double pas
 *     [2] l'équité si l'on double
 *     [3] le point de prise de l'adversaire
 *     [4..8] les cinq probabilités de la position, du point de vue du joueur
 *            au trait — celles sur lesquelles la décision est prise
 *
 * *« Une décision juste à 0,001 près et une décision juste à 0,5 près ne sont
 * pas la même décision »* (`gn_cube.h`) : c'est pourquoi les deux équités
 * sortent, et pas seulement le verdict.
 *
 * `efficiency` est l'efficacité du videau. Elle est MESURÉE
 * (`bench/fit_efficiency.py`), jamais empruntée à une constante publiée ;
 * l'appelant doit passer celle de son état de videau.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_cube_decide(const char *position_id, int turn, int owner,
                    int use_match, int away_on_roll, int away_opponent,
                    int cube, int crawford, double efficiency, int jacoby,
                    int ply, int filter_top, int filter_inner, double *out)
{
    if (g_network == NULL || position_id == NULL || out == NULL) {
        return -1;
    }

    GnPosition position;
    if (gn_position_from_id(position_id, turn, &position) != 0) {
        return -1;
    }

    GnSearchConfig config;
    GnMatchState state = {away_on_roll, away_opponent, cube, crawford};
    if (use_match) {
        config = gn_search_config_match(ply, &state);
        if (!config.use_match) {
            return -1;
        }
    } else {
        config = gn_search_config(ply);
    }
    if (filter_top > 0 && ply >= 1) {
        config.filter[ply] = filter_top;
    }
    if (filter_inner > 0 && ply >= 2) {
        config.filter[ply - 1] = filter_inner;
    }
    gn_search_use_prune(&config, g_prune, g_prune_k);

    /* La distribution AVANT le jet — ce dont une décision de videau a besoin,
     * et non celle d'après un dé particulier (gn_search.h, gn_search_probs). */
    float probs[GN_NUM_OUTPUTS];
    if (gn_search_probs(g_network, &position, &config, probs) != 0) {
        return -1;
    }

    GnCubeDecision decision;
    if (gn_cube_decide(probs, (GnCubeOwner)owner, use_match ? &state : NULL,
                       efficiency, jacoby, &decision) != 0) {
        return -1;
    }

    out[0] = (double)decision.action;
    out[1] = decision.equity_no_double;
    out[2] = decision.equity_double;
    out[3] = decision.take_point;
    for (int k = 0; k < GN_NUM_OUTPUTS; k++) {
        out[4 + k] = probs[k];
    }
    return 0;
}

EMSCRIPTEN_KEEPALIVE
double gnw_best_play(const char *position_id, int turn, int d1, int d2,
                     int ply, int filter_top, int filter_inner,
                     int use_match, int away_on_roll, int away_opponent,
                     int cube, int crawford,
                     char *out_id, int *out_evaluations, char *out_notation)
{
    if (g_network == NULL || position_id == NULL) {
        return -99.0;
    }

    GnPosition position;
    if (gn_position_from_id(position_id, turn, &position) != 0) {
        return -99.0;
    }

    GnSearchConfig config;
    if (use_match) {
        const GnMatchState state = {away_on_roll, away_opponent, cube, crawford};
        config = gn_search_config_match(ply, &state);
        if (!config.use_match) {
            return -99.0;   /* score hors table : refusé, pas rabattu en money */
        }
    } else {
        config = gn_search_config(ply);
    }
    if (filter_top > 0 && ply >= 1) {
        config.filter[ply] = filter_top;
    }
    if (filter_inner > 0 && ply >= 2) {
        config.filter[ply - 1] = filter_inner;
    }
    /* L'élagage, s'il a été chargé. `gn_search_use_prune` refuse un k nul ou
     * un réseau absent, donc l'appel est sûr dans tous les cas. */
    gn_search_use_prune(&config, g_prune, g_prune_k);

    gn_search_reset_evaluations();

    GnCandidate best;
    if (gn_best_play(g_network, &position, d1, d2, &config, &best) != 0) {
        if (out_evaluations) {
            *out_evaluations = (int)gn_search_evaluations();
        }
        return -99.0;
    }

    if (out_id != NULL) {
        gn_position_id(&best.play.result, out_id);
    }
    if (out_notation != NULL) {
        gn_play_notation(&best.play, (int)position.turn, out_notation);
    }
    if (out_evaluations != NULL) {
        *out_evaluations = (int)gn_search_evaluations();
    }
    return best.equity;
}

/*
 * T73 -- the deterministic int8 GEMM, exposed raw for the native<->Wasm
 * parity check (`wasm-parity-int8`). Not wired into inference yet: no
 * exported model is quantised. This is the kernel alone, on synthetic
 * vectors the native side already computed -- a thin passthrough, like
 * every other export in this file.
 */

EMSCRIPTEN_KEEPALIVE
int gnw_gemm_int8_relu(const int8_t *weights, int rows, int cols,
                       const int32_t *bias, const uint8_t *input, int batch,
                       int shift, uint8_t *out)
{
    return gn_gemm_int8_relu(weights, rows, cols, bias, input, batch, shift, out);
}

EMSCRIPTEN_KEEPALIVE
int gnw_gemm_int8_raw(const int8_t *weights, int rows, int cols,
                      const int32_t *bias, const uint8_t *input, int batch,
                      int32_t *out)
{
    return gn_gemm_int8_raw(weights, rows, cols, bias, input, batch, out);
}

/* ── Le codec de position ───────────────────────────────────────────────
 *
 * POURQUOI CES ENVELOPPES EXISTENT (T86).
 *
 * `gn_position_id`, `gn_position_from_id`, `gn_xgid` et
 * `gn_position_from_xgid` sont dans le module depuis toujours — la recherche
 * s'en sert à chaque appel — mais aucun n'était atteignable depuis
 * JavaScript. Un appelant qui devait fabriquer un identifiant à partir de SON
 * plateau n'avait donc qu'une option : réécrire le codec.
 *
 * C'est arrivé, et la méthode est la seule possible dans ce sens-là :
 * l'algorithme se DÉDUIT, puis se valide empiriquement contre ce module —
 * reproduction de l'identifiant d'ouverture, puis accord à 5,85e-9 sur
 * l'équité rendue. C'est du bon travail, et ce n'en est pas moins un accord
 * avec soi-même : une déduction confirmée par le module qu'elle imite ne
 * vérifie rien. Les deux écritures qui vivent ici — le C, et le Python de
 * `python/gammonnet/codec.py` — sont croisées contre gnubg-nn sur 10 000
 * positions. C'est toute la différence, et c'est pourquoi ces enveloppes
 * existent.
 *
 * LE PLATEAU TRAVERSE LA FRONTIÈRE EN 29 ENTIERS, dans la convention de
 * `gn_rules.h` et sans en inventer une seconde :
 *
 *     [0..23]  les points, comptes SIGNÉS — positif BLANC, négatif NOIR.
 *              L'indice i désigne le point (i+1) pour BLANC et (24-i) pour
 *              NOIR.
 *     [24]     bar[GN_WHITE]        [25]  bar[GN_BLACK]
 *     [26]     off[GN_WHITE]        [27]  off[GN_BLACK]
 *     [28]     le joueur au trait (GN_WHITE = 0, GN_BLACK = 1)
 *
 * Des `int` et non des `signed char` : `HEAP32` est le tampon que JavaScript
 * remplit sans conversion, et 29 entiers ne sont pas un poste de coût.
 *
 * TOUT EST REFUSÉ, RIEN N'EST DEVINÉ. Un plateau structurellement impossible
 * (plus de 15 pions d'une couleur, un point des deux couleurs) est rejeté par
 * `gn_position_is_valid` AVANT d'être encodé : un identifiant plausible tiré
 * d'un plateau faux est précisément le genre d'erreur silencieuse que
 * `CLAUDE.md` §2 nomme.
 */

#define GNW_BOARD_INTS  29
#define GNW_XGID_FIELDS 10

static int gnw_board_to_position(const int *board, GnPosition *out)
{
    if (board == NULL || out == NULL) {
        return -1;
    }
    for (int i = 0; i < GN_NUM_POINTS; i++) {
        const int n = board[i];
        if (n < -GN_NUM_CHECKERS || n > GN_NUM_CHECKERS) {
            return -1;
        }
        out->points[i] = (signed char)n;
    }
    for (int p = 0; p < 2; p++) {
        const int bar = board[24 + p];
        const int off = board[26 + p];
        if (bar < 0 || bar > GN_NUM_CHECKERS || off < 0 || off > GN_NUM_CHECKERS) {
            return -1;
        }
        out->bar[p] = (unsigned char)bar;
        out->off[p] = (unsigned char)off;
    }
    const int turn = board[28];
    if (turn != GN_WHITE && turn != GN_BLACK) {
        return -1;
    }
    out->turn = (unsigned char)turn;
    return gn_position_is_valid(out) ? 0 : -1;
}

static void gnw_position_to_board(const GnPosition *pos, int *board)
{
    for (int i = 0; i < GN_NUM_POINTS; i++) {
        board[i] = pos->points[i];
    }
    board[24] = pos->bar[GN_WHITE];
    board[25] = pos->bar[GN_BLACK];
    board[26] = pos->off[GN_WHITE];
    board[27] = pos->off[GN_BLACK];
    board[28] = pos->turn;
}

/*
 * Le Position ID d'un plateau, vu par le joueur au trait.
 *
 * `out_id` reçoit GN_POSITION_ID_LENGTH octets (14 caractères plus le NUL).
 * Rend 0, ou -1 si le plateau n'est pas une position valide.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_position_encode(const int *board, char *out_id)
{
    GnPosition position;
    if (out_id == NULL || gnw_board_to_position(board, &position) != 0) {
        return -1;
    }
    return gn_position_id(&position, out_id);
}

/*
 * Le plateau d'un Position ID, `turn` au trait.
 *
 * L'identifiant ne porte PAS le joueur au trait : deux positions qui ne
 * diffèrent que par lui partagent leur identifiant, chacune vue de son propre
 * joueur. C'est pourquoi `turn` est un paramètre et non une déduction — et
 * c'est le piège que toute écriture externe de ce codec finit par
 * documenter : l'identifiant que rend `bestPlay` décrit la position D'APRÈS
 * le coup, donc l'autre camp est au trait.
 *
 * `out_board` reçoit 29 entiers. Rend 0, ou -1.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_position_decode(const char *id, int turn, int *out_board)
{
    GnPosition position;
    if (id == NULL || out_board == NULL) {
        return -1;
    }
    if (gn_position_from_id(id, turn, &position) != 0) {
        return -1;
    }
    gnw_position_to_board(&position, out_board);
    return 0;
}

/*
 * Le XGID d'un plateau. `fields` porte les dix champs hors pions, dans
 * l'ordre de `GnXgidFields` :
 *
 *     cube_power, cube_owner, turn, die1, die2,
 *     score_upper, score_lower, flags, match_length, max_cube
 *
 * `fields` peut être NULL : le XGID décrit alors une partie d'argent sans
 * videau, aucun jet posé, le trait pris du plateau.
 *
 * `out` reçoit GN_XGID_LENGTH octets. Rend 0, ou -1.
 *
 * SUR LE DEGRÉ DE VÉRIFICATION, et il n'est pas le même que celui du Position
 * ID : `gn_position_id.h` le dit sans détour — le XGID est ancré sur
 * l'identifiant d'ouverture canonique et sur l'aller-retour, faute d'une
 * implémentation indépendante contre laquelle le croiser. Son orientation est
 * établie, pas oraclée. Un appelant qui en dépend doit le savoir.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_xgid_encode(const int *board, const int *fields, char *out)
{
    GnPosition position;
    if (out == NULL || gnw_board_to_position(board, &position) != 0) {
        return -1;
    }
    if (fields == NULL) {
        return gn_xgid(&position, NULL, out);
    }
    const GnXgidFields f = {
        fields[0], fields[1], fields[2], fields[3], fields[4],
        fields[5], fields[6], fields[7], fields[8], fields[9],
    };
    return gn_xgid(&position, &f, out);
}

/*
 * Le plateau et les champs d'un XGID. `out_fields` peut être NULL si seuls
 * les pions intéressent. Rend 0, ou -1.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_xgid_decode(const char *xgid, int *out_board, int *out_fields)
{
    GnPosition position;
    GnXgidFields f;
    if (xgid == NULL || out_board == NULL) {
        return -1;
    }
    if (gn_position_from_xgid(xgid, &position, &f) != 0) {
        return -1;
    }
    gnw_position_to_board(&position, out_board);
    if (out_fields != NULL) {
        out_fields[0] = f.cube_power;
        out_fields[1] = f.cube_owner;
        out_fields[2] = f.turn;
        out_fields[3] = f.die1;
        out_fields[4] = f.die2;
        out_fields[5] = f.score_upper;
        out_fields[6] = f.score_lower;
        out_fields[7] = f.flags;
        out_fields[8] = f.match_length;
        out_fields[9] = f.max_cube;
    }
    return 0;
}

/*
 * LE COMPTE DE PIPS, et il n'est pas là pour l'affichage.
 *
 * `BRIEF.md` §6 en fait la sentinelle la moins chère du projet : *« si le
 * compte de pips d'une position traduite n'est pas celui qu'on attendait,
 * tout ce qui suit est dénué de sens. Utilisez-le chaque fois qu'une position
 * traverse une frontière de format. »* Un appelant qui convertit son propre
 * plateau vers ces 29 entiers traverse exactement une telle frontière ; lui
 * refuser la sentinelle serait lui demander de faire confiance.
 *
 * Rend le compte, ou -1 si le plateau est invalide.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_pip_count(const int *board, int player)
{
    GnPosition position;
    if (gnw_board_to_position(board, &position) != 0
        || (player != GN_WHITE && player != GN_BLACK)) {
        return -1;
    }
    return gn_position_pip_count(&position, player);
}

/*
 * A CANONICAL SEARCH LEVEL, from the ONE table (`gn_search.c`'s `LEVELS`,
 * issue #25) -- so `wasm/api_invariants.mjs` can hold `Evaluator.level()`'s
 * hand-copied JS numbers to what this build actually ships, rather than
 * trusting that a copy stays accurate forever.
 *
 * `out` receives, in order: ply, filterTop (filter[ply]), filterInner
 * (filter[ply-1], 0 below ply 2), pruneK -- the same four numbers
 * `Evaluator.level()` returns. `out_quality` receives prune_equity_loss,
 * its CI low, its CI high. Returns 0 on success, -1 for an unknown name.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_search_level(const char *name, int *out, double *out_quality)
{
    if (name == NULL || out == NULL || out_quality == NULL) {
        return -1;
    }
    const GnSearchLevel *level = gn_search_level(name);
    if (level == NULL) {
        return -1;
    }
    out[0] = level->ply;
    out[1] = (level->ply >= 1) ? level->filter[level->ply] : 0;
    out[2] = (level->ply >= 2) ? level->filter[level->ply - 1] : 0;
    out[3] = level->prune_k;
    out_quality[0] = level->prune_equity_loss;
    out_quality[1] = level->prune_equity_loss_ci_low;
    out_quality[2] = level->prune_equity_loss_ci_high;
    return 0;
}

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
#include "gn_infer.h"

static GnNetwork *g_network = NULL;
static GnNetwork *g_prune = NULL;
static int g_prune_k = 0;

/* MEMFS, not a real path: RAM that `fopen` happens to understand. */
static const char *MODEL_PATH = "/gammonnet-model.bin";
static const char *PRUNE_PATH = "/gammonnet-prune.bin";

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
 * The bench path, and eventually the search path. One boundary crossing for
 * many evaluations: at 0-ply speeds the JS/WASM call overhead would otherwise
 * be a large share of what we are trying to measure, and we would be timing
 * the boundary rather than the network.
 */
EMSCRIPTEN_KEEPALIVE
int gnw_evaluate_batch(const float *features, float *out, int count)
{
    if (g_network == NULL || count < 0) {
        return -1;
    }
    for (int i = 0; i < count; i++) {
        if (gn_evaluate_features(g_network,
                                 features + (size_t)i * GN_NUM_FEATURES,
                                 out + (size_t)i * GN_NUM_OUTPUTS) != 0) {
            return -1;
        }
    }
    return 0;
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
EMSCRIPTEN_KEEPALIVE
double gnw_best_play(const char *position_id, int turn, int d1, int d2,
                     int ply, int filter_top, int filter_inner,
                     int use_match, int away_on_roll, int away_opponent,
                     int cube, int crawford,
                     char *out_id, int *out_evaluations)
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
    if (out_evaluations != NULL) {
        *out_evaluations = (int)gn_search_evaluations();
    }
    return best.equity;
}

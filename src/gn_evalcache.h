/*
 * gn_evalcache.h -- an evaluation cache (transposition table) for the search.
 *
 * ── WHY A CACHE IS CORRECT HERE ─────────────────────────────────────
 *
 * `evaluate_position` (the single place in gn_search.c a leaf position becomes
 * five probabilities, per T38) renders the RAW distribution of a leaf --
 * `gn_evaluate`'s five outputs, from `pos->turn`'s point of view. It takes no
 * score and no cube: those enter later, in `value_from_probs`. The key for a
 * cache of this call is therefore the position ALONE, and an entry keyed on
 * the position is valid whether the search is running in money or in match
 * play -- the cache never sees a score to get wrong, because it is never
 * handed one.
 *
 * The network itself is loaded once and is fixed for the life of a process
 * (see `gn_infer.h`): the same `GnNetwork *`, asked about the same position
 * twice, returns the same five floats both times. A cache hit therefore
 * returns EXACTLY what `gn_evaluate` would have returned -- checked at the
 * bit by `tests/test_evalcache.py`, not approximated -- so the cache changes
 * only the COST of a search, never its result. A cache that moved a result
 * would be a bug, not an optimisation.
 *
 * ── WHAT THIS DOES NOT CACHE ────────────────────────────────────────
 *
 * The exact bearoff table (`gn_bearoff.h`) is consulted BEFORE this cache at
 * both entry points, and its answers are not stored here: a table lookup is
 * already a single memory read, and spending a slot to make an O(1) lookup
 * "faster" would only add a second place a bearoff answer could theoretically
 * disagree with the table. This cache exists for the one genuinely expensive
 * step, `gn_evaluate` -- a forward pass through four layers.
 *
 * ── COLLISION POLICY, HASH, AND WHY THE KEY MUST BE THE WHOLE POSITION ──
 *
 * Direct-mapped, open addressing, a single slot per bucket: the newest write
 * always wins, no chaining, no probing. A table this size (2^19 entries by
 * default, see GN_EVALCACHE_DEFAULT_LOG2) is sized to make collisions RARE
 * over one search, not to make them impossible -- so every entry stores the
 * FULL 29-byte key, and a lookup that hits an occupied bucket whose key
 * differs is treated as a miss, never as a match. Keying on a truncated hash
 * instead would occasionally hand back another position's distribution as if
 * it were this one's: exactly the silent, plausible, wrong answer CLAUDE.md
 * names as the failure mode to design against.
 *
 * FNV-1a, 64-bit, over the raw bytes of the key. Chosen because it needs no
 * library and no external dependency ("ça compile avec un compilateur et
 * rien d'autre", CLAUDE.md), and because it is specified precisely enough
 * that any correct reimplementation agrees with this one byte for byte.
 *
 * `GnPosition` (`gn_rules.h`) has every field char-sized -- `signed char
 * points[24]`, `unsigned char bar[2]`, `unsigned char off[2]`, `unsigned char
 * turn` -- so the compiler has no alignment gap to insert anywhere inside it,
 * on any platform this project targets. `sizeof(GnPosition) == 29` is
 * therefore not an assumption but a consequence of the struct's own layout,
 * and `gn_evalcache.c` asserts it at compile time. That is what makes hashing
 * and comparing `sizeof(GnPosition)` raw bytes safe: there is no indeterminate
 * padding byte inside a `GnPosition` to leak into a hash or a memcmp. (An
 * *entry* -- the key followed by five floats -- can still have padding of its
 * own between those fields, because a `float` needs 4-byte alignment and 29
 * is not a multiple of 4; that padding is handled by zeroing the whole table
 * once at creation, in `gn_evalcache.c`, and never touching those bytes again.)
 *
 * ── SHARED CACHE OF MODULE, LIKE THE BEAROFF TABLE ──────────────────
 *
 * `gn_evalcache_set_shared` / `gn_evalcache_shared` mirror
 * `gn_bearoff_set_shared` / `gn_bearoff_shared` in `gn_bearoff.h`: a single
 * module-level pointer, NOT LOCKED, for the same reason -- this project's
 * parallelism is by PROCESS (see `bench/`, one worker per core), never by
 * thread. A pointer set once before the first search and only read afterwards
 * needs no synchronisation under that model; if threads are ever introduced,
 * this assumption must be revisited alongside `gn_bearoff.h`'s and
 * `gn_search.c`'s `g_evaluations`.
 *
 * Defaults to NULL: without a call to `gn_evalcache_set_shared`, nothing
 * about a search changes, and every regression corpus measured before this
 * cache existed stays exactly as measured.
 *
 * ── OUT OF SCOPE FOR THIS TASK: WEBASSEMBLY ─────────────────────────
 *
 * `gn_bearoff.c` was already left out of `WASM_SOURCES` in the Makefile when
 * T38 wired it into `gn_search.c` / `gn_choose.c` -- it depends on `mmap` and
 * a 1.2 GiB file that has no business in a browser. This cache has no such
 * dependency and COULD be built for WebAssembly, but wiring it into the WASM
 * target is left alone here, matching the bearoff table's precedent, and
 * because T3A's job is to measure the native gain first. See PLAN.md.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_EVALCACHE_H
#define GN_EVALCACHE_H

#include "gn_infer.h"
#include "gn_rules.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct GnEvalCache GnEvalCache;

/*
 * Default table size: 2^19 = 524 288 entries. Each entry is the 29-byte key,
 * five 4-byte floats and one occupancy byte -- 50 bytes of payload, padded by
 * the compiler to 56 bytes (a float needs 4-byte alignment, and 29 is not a
 * multiple of 4). Measured, not guessed: `sizeof(GnEvalCacheEntry)` is 56 on
 * this project's build, so the default table is exactly 2^19 * 56 = 28 MiB.
 * See gn_evalcache.c for the entry layout.
 */
#define GN_EVALCACHE_DEFAULT_LOG2 19

/*
 * Create a cache with 2^log2_entries slots, all initially empty.
 *
 * Returns NULL on allocation failure, or if log2_entries exceeds 30 -- past
 * that point the bucket count would not comfortably fit an `unsigned long`
 * index on every platform this project targets, and no realistic measurement
 * needs a table that large.
 */
GnEvalCache *gn_evalcache_create(unsigned log2_entries);
void gn_evalcache_free(GnEvalCache *cache);

/*
 * Look up `pos` in `cache`. Returns 1 and fills `probs` with the EXACT five
 * floats a prior `gn_evalcache_store` wrote for this position -- nothing
 * rounded, blended, or interpolated -- and 0 on a miss, leaving `probs`
 * untouched. Updates the hit/miss counters either way.
 */
int gn_evalcache_lookup(GnEvalCache *cache, const GnPosition *pos,
                        float probs[GN_NUM_OUTPUTS]);

/*
 * Record `probs` for `pos`, replacing whatever previously occupied that
 * bucket -- see the collision policy above. Updates the store counter.
 */
void gn_evalcache_store(GnEvalCache *cache, const GnPosition *pos,
                        const float probs[GN_NUM_OUTPUTS]);

/* Counters since the cache was created or last reset. NOT LOCKED -- see the
 * note above about this project's parallelism model. */
unsigned long gn_evalcache_hits(const GnEvalCache *cache);
unsigned long gn_evalcache_misses(const GnEvalCache *cache);
unsigned long gn_evalcache_stores(const GnEvalCache *cache);
void gn_evalcache_reset_counters(GnEvalCache *cache);

/* Number of slots in the table (2^log2_entries as given to _create). Does
 * NOT count how many are occupied -- this table never tracks a fill ratio,
 * only whether a given bucket currently holds a valid entry. */
unsigned long gn_evalcache_capacity(const GnEvalCache *cache);

/* ── The shared cache (T3A) ──────────────────────────────────────────
 *
 * Install (or clear, with NULL) the cache consulted by gn_search.c and
 * gn_choose.c. The cache itself is owned by the caller -- this module never
 * allocates or frees one on its own behalf, exactly like
 * gn_bearoff_set_shared / gn_bearoff_shared.
 */
void gn_evalcache_set_shared(GnEvalCache *cache);
GnEvalCache *gn_evalcache_shared(void);

#ifdef __cplusplus
}
#endif

#endif /* GN_EVALCACHE_H */

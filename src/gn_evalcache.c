/*
 * gn_evalcache.c -- see gn_evalcache.h for what this caches, and why it may.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_evalcache.h"

#include <stdlib.h>
#include <string.h>

/*
 * GnPosition has no padding: every field is char-sized, so there is no
 * alignment gap anywhere inside it, on any platform this project targets.
 * That is what makes hashing and comparing sizeof(GnPosition) raw bytes safe
 * -- see the long note in gn_evalcache.h. If gn_rules.h ever widens a field,
 * this assertion fails at compile time instead of silently letting an
 * indeterminate byte into a hash or a memcmp.
 */
_Static_assert(sizeof(GnPosition) == 29,
               "GnEvalCache hashes and compares GnPosition as 29 raw bytes; "
               "see gn_evalcache.h for why that requires an unpadded struct");

typedef struct {
    GnPosition key;
    float probs[GN_NUM_OUTPUTS];
    unsigned char occupied;
} GnEvalCacheEntry;

struct GnEvalCache {
    GnEvalCacheEntry *entries;
    unsigned long capacity; /* a power of two */
    unsigned long mask;     /* capacity - 1 */
    unsigned long hits;
    unsigned long misses;
    unsigned long stores;
};

/*
 * FNV-1a, 64-bit. The two constants are the published offset basis and prime
 * for this variant -- not tuned, not reimplemented from any project's source,
 * just the algorithm's own definition, chosen because it needs no dependency
 * and any correct reimplementation agrees with this one byte for byte.
 */
#define FNV_OFFSET_BASIS 0xcbf29ce484222325ULL
#define FNV_PRIME        0x100000001b3ULL

static unsigned long long fnv1a(const unsigned char *data, size_t len)
{
    unsigned long long hash = FNV_OFFSET_BASIS;
    for (size_t i = 0; i < len; i++) {
        hash ^= data[i];
        hash *= FNV_PRIME;
    }
    return hash;
}

GnEvalCache *gn_evalcache_create(unsigned log2_entries)
{
    /* A table wider than 2^30 buckets would not comfortably fit an unsigned
     * long index on every platform this project targets, and no realistic
     * measurement needs one that large -- see gn_evalcache.h. log2_entries
     * == 0 (a single bucket) is legal: small and pointless, but not unsafe,
     * and the collision test in tests/test_evalcache.py wants a tiny table
     * on purpose. */
    if (log2_entries > 30) {
        return NULL;
    }

    GnEvalCache *cache = malloc(sizeof(GnEvalCache));
    if (cache == NULL) {
        return NULL;
    }

    const unsigned long capacity = 1UL << log2_entries;
    /*
     * calloc, not malloc followed by a manual loop: the zeroed bytes are what
     * makes every slot start unoccupied (occupied == 0), AND -- see
     * gn_evalcache.h -- what keeps the padding bytes between an entry's key
     * and its probs deterministic from the very first store onward. A store
     * only ever overwrites the key, the probs, and the occupancy byte; it
     * never touches the gap between fields, so that gap stays whatever this
     * calloc set it to for the entire life of the table.
     */
    GnEvalCacheEntry *entries = calloc(capacity, sizeof(GnEvalCacheEntry));
    if (entries == NULL) {
        free(cache);
        return NULL;
    }

    cache->entries = entries;
    cache->capacity = capacity;
    cache->mask = capacity - 1;
    cache->hits = 0;
    cache->misses = 0;
    cache->stores = 0;
    return cache;
}

void gn_evalcache_free(GnEvalCache *cache)
{
    if (cache == NULL) {
        return;
    }
    free(cache->entries);
    free(cache);
}

static unsigned long bucket_of(const GnEvalCache *cache, const GnPosition *pos)
{
    const unsigned long long hash =
        fnv1a((const unsigned char *)pos, sizeof(GnPosition));
    return (unsigned long)(hash & cache->mask);
}

int gn_evalcache_lookup(GnEvalCache *cache, const GnPosition *pos,
                        float probs[GN_NUM_OUTPUTS])
{
    if (cache == NULL || pos == NULL || probs == NULL) {
        return 0;
    }

    const GnEvalCacheEntry *entry = &cache->entries[bucket_of(cache, pos)];

    /*
     * The occupancy byte alone would not be enough: two different positions
     * can hash to the same bucket (that is the whole point of storing the
     * full key rather than trusting the hash). Comparing the 29 raw bytes of
     * the key is what tells this position apart from whichever one last
     * wrote this slot -- see gn_evalcache.h for why that comparison is safe.
     */
    if (entry->occupied && memcmp(&entry->key, pos, sizeof(GnPosition)) == 0) {
        memcpy(probs, entry->probs, sizeof(entry->probs));
        cache->hits++;
        return 1;
    }
    cache->misses++;
    return 0;
}

void gn_evalcache_store(GnEvalCache *cache, const GnPosition *pos,
                        const float probs[GN_NUM_OUTPUTS])
{
    if (cache == NULL || pos == NULL || probs == NULL) {
        return;
    }

    /* Direct replacement, no chaining, no probing: whichever position last
     * hashed here wins the slot. See gn_evalcache.h for why this is a
     * deliberate simplicity rather than an oversight -- the table is sized
     * to make this rare during one search, not to make it impossible. */
    GnEvalCacheEntry *entry = &cache->entries[bucket_of(cache, pos)];
    memcpy(&entry->key, pos, sizeof(GnPosition));
    memcpy(entry->probs, probs, sizeof(entry->probs));
    entry->occupied = 1;
    cache->stores++;
}

unsigned long gn_evalcache_hits(const GnEvalCache *cache)
{
    return (cache != NULL) ? cache->hits : 0;
}

unsigned long gn_evalcache_misses(const GnEvalCache *cache)
{
    return (cache != NULL) ? cache->misses : 0;
}

unsigned long gn_evalcache_stores(const GnEvalCache *cache)
{
    return (cache != NULL) ? cache->stores : 0;
}

void gn_evalcache_reset_counters(GnEvalCache *cache)
{
    if (cache == NULL) {
        return;
    }
    cache->hits = 0;
    cache->misses = 0;
    cache->stores = 0;
}

unsigned long gn_evalcache_capacity(const GnEvalCache *cache)
{
    return (cache != NULL) ? cache->capacity : 0;
}

/*
 * The shared cache (T3A). A single module-level pointer, deliberately not
 * locked -- see the note in gn_evalcache.h. This mirrors gn_bearoff.c's
 * g_shared exactly: parallelism here is by process, never by thread.
 */
static GnEvalCache *g_shared = NULL;

void gn_evalcache_set_shared(GnEvalCache *cache) { g_shared = cache; }

GnEvalCache *gn_evalcache_shared(void) { return g_shared; }

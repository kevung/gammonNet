/*
 * gn_parallel.c -- see gn_parallel.h.
 *
 * One mutex, one condition variable, one list of open groups. Tasks in this
 * project are subtrees of a search -- a millisecond at the very least -- so a
 * single lock taken twice per task costs nothing measurable, and buys a pool
 * simple enough to read in one sitting. If a profile ever says otherwise, the
 * lock is the thing to replace, not the contract.
 *
 * SPDX-License-Identifier: MIT
 */

#include "gn_parallel.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* A thread can only exit where threads exist: everywhere but a WebAssembly
 * build without `-pthread`. */
#if !(defined(__EMSCRIPTEN__) && !defined(__EMSCRIPTEN_PTHREADS__))
#define GN_SCRATCH_RELEASE_AT_EXIT 1
#include <pthread.h>
#endif

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
#define GN_PARALLEL_TLS _Thread_local
#else
#define GN_PARALLEL_TLS __thread
#endif

/*
 * Every scratch block of a thread, chained through a 64-byte header that
 * keeps the block itself 64-byte aligned. The pool's own threads live as long
 * as the process and keep their blocks; but a caller may evaluate from
 * short-lived threads -- a server running each request on a new one is the
 * case that made this matter (issue #35: ~1 MB lost per request) -- so the
 * chain is freed when its thread exits, by a pthread key destructor. The
 * `_Thread_local` pointers that hold these blocks vanish with the same
 * thread; only another key destructor re-entering the engine on that dying
 * thread could still read one, and nothing here does.
 */
typedef union GnScratchHeader {
    union GnScratchHeader *next;
    unsigned char pad[64];
} GnScratchHeader;

static GN_PARALLEL_TLS GnScratchHeader *t_scratch = NULL;

#ifdef GN_SCRATCH_RELEASE_AT_EXIT
static pthread_key_t g_scratch_key;
static pthread_once_t g_scratch_once = PTHREAD_ONCE_INIT;
static int g_scratch_key_ok = 0;

static void release_scratch(void *chain)
{
    GnScratchHeader *h = chain;
    while (h != NULL) {
        GnScratchHeader *const next = h->next;
        free(h);
        h = next;
    }
    t_scratch = NULL;
}

static void create_scratch_key(void)
{
    g_scratch_key_ok = (pthread_key_create(&g_scratch_key, release_scratch) == 0);
}
#endif

void *gn_parallel_scratch(size_t size)
{
    const size_t rounded = (size + 63) & ~(size_t)63;
    const size_t total = sizeof(GnScratchHeader) + (rounded == 0 ? 64 : rounded);
    GnScratchHeader *h = aligned_alloc(64, total);
    if (h == NULL) {
        fprintf(stderr, "gammonnet: mémoire de travail indisponible (%zu octets)\n",
                size);
        abort();
    }
    memset(h, 0, total);
    h->next = t_scratch;
    t_scratch = h;
#ifdef GN_SCRATCH_RELEASE_AT_EXIT
    pthread_once(&g_scratch_once, create_scratch_key);
    if (!g_scratch_key_ok || pthread_setspecific(g_scratch_key, t_scratch) != 0) {
        /* Without the key every exiting thread would leak its blocks: a slow
         * failure no caller would see. Stop now instead. */
        fprintf(stderr, "gammonnet: libération de la mémoire de travail impossible\n");
        abort();
    }
#endif
    return h + 1;
}

/* WebAssembly runs this pool only when the module is built with `-pthread`
 * (`make wasm-threads`, which defines __EMSCRIPTEN_PTHREADS__): the same
 * pthreads code, on Web Workers sharing one memory. Every other WebAssembly
 * build, and the instrumentation builds, stay serial. */
#if (defined(__EMSCRIPTEN__) && !defined(__EMSCRIPTEN_PTHREADS__)) || \
    defined(GN_TIE_CENSUS) || defined(GN_BATCH_FILL_STATS) || \
    defined(GN_BATCH_SPARSITY_SWITCH)
#define GN_PARALLEL_SERIAL_ONLY 1
#endif

#ifdef GN_PARALLEL_SERIAL_ONLY

int gn_parallel_set_threads(int threads)
{
    return (threads == 1) ? 1 : -1;
}

int gn_parallel_threads(void)
{
    return 1;
}

void gn_parallel_for(int n, GnParallelTask fn, void *ctx)
{
    for (int i = 0; i < n; i++) {
        fn(ctx, i);
    }
}

#else

#include <pthread.h>
#include <stddef.h>

typedef struct GnGroup {
    GnParallelTask fn;
    void *ctx;
    int n;
    int claimed;   /* indices handed out so far, under g_lock */
    int finished;  /* calls returned so far, under g_lock */
    struct GnGroup *older;
    struct GnGroup *newer;
} GnGroup;

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_wake = PTHREAD_COND_INITIALIZER;

/* Groups that still have unclaimed indices, oldest first. A helper takes from
 * the OLDEST group: older groups sit higher in the tree, so their tasks are
 * the largest, which is what balances the load. */
static GnGroup *g_oldest = NULL;
static GnGroup *g_newest = NULL;

static int g_threads = 1;
static int g_stop = 0;
static int g_workers = 0;
static pthread_t g_worker_ids[GN_PARALLEL_MAX_THREADS];

static void unlink_group(GnGroup *g)
{
    if (g->older != NULL) {
        g->older->newer = g->newer;
    } else {
        g_oldest = g->newer;
    }
    if (g->newer != NULL) {
        g->newer->older = g->older;
    } else {
        g_newest = g->older;
    }
    g->older = g->newer = NULL;
}

/* Under g_lock: hand out one index of `g`, unlinking it once exhausted. */
static int claim(GnGroup *g)
{
    const int index = g->claimed++;
    if (g->claimed == g->n) {
        unlink_group(g);
    }
    return index;
}

/* Run one claimed task outside the lock, then account for it. */
static void run(GnGroup *g, int index)
{
    pthread_mutex_unlock(&g_lock);
    g->fn(g->ctx, index);
    pthread_mutex_lock(&g_lock);
    if (++g->finished == g->n) {
        pthread_cond_broadcast(&g_wake);
    }
}

static void *worker(void *unused)
{
    (void)unused;
    pthread_mutex_lock(&g_lock);
    for (;;) {
        if (g_stop) {
            break;
        }
        if (g_oldest != NULL) {
            GnGroup *g = g_oldest;
            run(g, claim(g));
            continue;
        }
        pthread_cond_wait(&g_wake, &g_lock);
    }
    pthread_mutex_unlock(&g_lock);
    return NULL;
}

static void stop_workers(void)
{
    pthread_mutex_lock(&g_lock);
    g_stop = 1;
    pthread_cond_broadcast(&g_wake);
    pthread_mutex_unlock(&g_lock);
    for (int i = 0; i < g_workers; i++) {
        pthread_join(g_worker_ids[i], NULL);
    }
    g_workers = 0;
    g_stop = 0;
}

int gn_parallel_set_threads(int threads)
{
    if (threads < 1 || threads > GN_PARALLEL_MAX_THREADS) {
        return -1;
    }
    if (threads == g_threads) {
        return g_threads;
    }
    stop_workers();
    g_threads = 1;
    for (int i = 0; i < threads - 1; i++) {
        if (pthread_create(&g_worker_ids[i], NULL, worker, NULL) != 0) {
            stop_workers();
            return -1;
        }
        g_workers++;
    }
    g_threads = threads;
    return g_threads;
}

int gn_parallel_threads(void)
{
    return g_threads;
}

void gn_parallel_for(int n, GnParallelTask fn, void *ctx)
{
    if (n <= 0) {
        return;
    }
    if (g_threads <= 1 || n == 1) {
        for (int i = 0; i < n; i++) {
            fn(ctx, i);
        }
        return;
    }

    GnGroup group = {fn, ctx, n, 0, 0, NULL, NULL};
    pthread_mutex_lock(&g_lock);
    group.older = g_newest;
    if (g_newest != NULL) {
        g_newest->newer = &group;
    } else {
        g_oldest = &group;
    }
    g_newest = &group;
    pthread_cond_broadcast(&g_wake);

    while (group.finished < group.n) {
        if (group.claimed < group.n) {
            /* Our own tasks first: they are what we are waiting for. */
            run(&group, claim(&group));
        } else if (g_oldest != NULL) {
            /* Ours are all handed out but not all back: help elsewhere
             * rather than sleep. Never a deadlock -- whatever we pick up is
             * finite, and our own stragglers run on threads that do not
             * wait on us. */
            GnGroup *other = g_oldest;
            run(other, claim(other));
        } else {
            pthread_cond_wait(&g_wake, &g_lock);
        }
    }
    pthread_mutex_unlock(&g_lock);
}

#endif /* GN_PARALLEL_SERIAL_ONLY */

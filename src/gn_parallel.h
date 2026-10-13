/*
 * gn_parallel.h -- a small fork/join pool for the search, native only.
 *
 * WHY
 *
 * A 3-ply decision takes 6.5 s and a 4-ply one ~128 s on ONE core
 * (docs/mesures/2026-10-13-profil-decision-niveaux.md), on machines with 16.
 * The search tree is made of independent subtrees -- the twenty-one rolls of
 * a chance node, the candidates of a root -- whose values are combined by a
 * weighted sum in a FIXED order. Computing those subtrees on several threads
 * and summing them in the same order gives the same bits as one thread: the
 * network is bit-identical per item however positions are batched
 * (gn_infer.h), and the evaluation cache only ever returns what the network
 * would have returned. tests/test_parallel_search.py holds that equality.
 *
 * THE CONTRACT
 *
 * `gn_parallel_for(n, fn, ctx)` calls `fn(ctx, i)` exactly once for every
 * `i` in [0, n) and returns when all calls have returned. Calls may run on
 * any thread, in any order, concurrently: `fn` must write only to its own
 * slot `i` of `ctx`. Nested calls are allowed -- a task may itself call
 * `gn_parallel_for` -- and cannot deadlock: a waiting thread runs pending
 * tasks itself rather than sleeping on them.
 *
 * With one thread (the default), or under a WebAssembly build without
 * `-pthread`, `gn_parallel_for` is a plain loop over i = 0 .. n-1 on the
 * calling thread. Nothing changes for a caller that never asks for threads.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef GN_PARALLEL_H
#define GN_PARALLEL_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The most threads a pool may hold (the caller's thread included). */
#define GN_PARALLEL_MAX_THREADS 256

typedef void (*GnParallelTask)(void *ctx, int index);

/*
 * Set the number of threads searches use, the calling thread included:
 * 1 restores the serial engine exactly. Returns the number actually in
 * effect, or -1 if `threads` is out of [1, GN_PARALLEL_MAX_THREADS] or the
 * pool could not be (re)built -- in which case the previous setting stays.
 *
 * Not to be called while a search runs on another thread. Under a
 * WebAssembly build without `-pthread`, and in the instrumentation builds
 * whose counters are plain globals (GN_TIE_CENSUS, GN_BATCH_FILL_STATS,
 * GN_BATCH_SPARSITY_SWITCH), any value above 1 is refused rather than
 * silently ignored.
 */
int gn_parallel_set_threads(int threads);

/* The number of threads in effect (1 when serial). */
int gn_parallel_threads(void);

void gn_parallel_for(int n, GnParallelTask fn, void *ctx);

/*
 * A zeroed, 64-byte aligned block of `size` bytes, for a thread's own scratch
 * held through a `_Thread_local` POINTER. Why a pointer and not a
 * `_Thread_local` array: under WebAssembly with threads the initial image of
 * thread-local storage ships inside the module, and the scratch arrays of
 * this library weighed 1.19 MB of zeros there. Never returns NULL: out of
 * memory it stops the process with a message, the only answer that is not a
 * plausible wrong one. The block is never freed (threads live as long as the
 * process; see gn_parallel.c).
 */
void *gn_parallel_scratch(size_t size);

#ifdef __cplusplus
}
#endif

#endif /* GN_PARALLEL_H */

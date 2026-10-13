/*
 * threads_bench_worker.mjs -- one 2-ply decision per position, timed at
 * several thread counts, inside a real browser's Web Worker.
 *
 * Driven by `bench/browser_threads.mjs`. The worker (not the page) runs the
 * search because the threaded module blocks on its helpers, which a page's
 * main thread may not do. Every thread count's rankings are compared with the
 * one-thread rankings, bit for bit (JSON of every equity and result): a speed
 * that changed an answer would not be a speed.
 *
 * SPDX-License-Identifier: MIT
 */

import { Evaluator } from "./gammonnet.mjs";

const START = "4HPwATDgc/ABMA";

async function bytes(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} : ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

/* A fixed walk of real decisions: 0-ply self-play, positions with at least
 * two legal plays, dice from a fixed linear congruential generator. */
function walk(ev, count) {
  let state = 20261013;
  const die = () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return 1 + Math.floor((state / 2147483648) * 6);
  };
  const out = [];
  let id = START;
  let turn = 0;
  let plies = 0;
  while (out.length < count) {
    const d1 = die();
    const d2 = die();
    let ranked;
    try {
      ranked = ev.rankPlays(id, turn, d1, d2, { ply: 0, max: 2 });
    } catch {
      ranked = [];
    }
    if (ranked.length >= 2) out.push({ id, turn, d1, d2 });
    plies += 1;
    if (ranked.length === 0 && plies > 2) {
      id = START; turn = 0; plies = 0;
      continue;
    }
    if (ranked.length > 0) id = ranked[0].resultId;
    turn = 1 - turn;
    if (plies > 200) { id = START; turn = 0; plies = 0; }
  }
  return out;
}

self.onmessage = async ({ data }) => {
  try {
    const { build, threadCounts, decisions, level } = data;
    const { default: factory } = await import(`../build/wasm/${build}`);
    const ev = await Evaluator.create(
      factory, await bytes("../models/cubeless_prob5_512_512_256_256.bin"));
    const options = Evaluator.level(level);
    ev.loadPrune(await bytes("../models/prune_32.bin"), options.pruneK ?? 12);
    const cases = walk(ev, decisions);

    const rows = [];
    let reference = null;
    for (const threads of threadCounts) {
      ev.setThreads(threads);
      // One untimed decision first: compilation tiers and thread start-up.
      ev.rankPlays(cases[0].id, cases[0].turn, cases[0].d1, cases[0].d2, options);
      const answers = [];
      const start = performance.now();
      for (const c of cases) {
        answers.push(ev.rankPlays(c.id, c.turn, c.d1, c.d2, options)
          .map((p) => [p.resultId, p.equity]));
      }
      const seconds = (performance.now() - start) / 1000 / cases.length;
      const digest = JSON.stringify(answers);
      if (reference === null) reference = digest;
      rows.push({ threads, seconds, identical: digest === reference });
    }
    self.postMessage({
      ok: true, rows, decisions: cases.length, level,
      hardwareConcurrency: navigator.hardwareConcurrency,
      crossOriginIsolated: self.crossOriginIsolated,
    });
  } catch (error) {
    self.postMessage({ ok: false, error: String(error?.stack || error) });
  }
};

# Getting started

## What the release contains

| File | What it is |
|---|---|
| `manifest.json` | The file names for this release — read it instead of copying them |
| `strehl-prob5-512-512-256-128_v1_….bin` | Network weights, **float32** — 2.1 MiB |
| `…​.bin16` | The same, **float16** — 1.06 MiB. Prefer this one on the web |
| `strehl-prune-32_v1_….bin` / `.bin16` | The **pruning network**: it sorts moves so the big one only scores a handful |
| `gammonnet-simd.mjs` + `.wasm` | The WebAssembly engine, SIMD build |
| `gammonnet.mjs` + `.wasm` | The same, scalar, for environments without SIMD |
| `api/gammonnet.mjs` | The JavaScript API: the `Evaluator` class |
| `api/pool.mjs`, `api/worker.mjs` | The Web Worker pool |
| `verify/` | The 2 000-position reference and the parity check |
| `evidence/` | The raw measurements behind every figure |

```{admonition} Why the weights are not called "gammonNet"
:class: note

The weights are **Alexander Strehl's** work (MIT) and carry his name. **gammonNet** names the
*configuration* — network, search, match equity, bearoff. A network only becomes a different
network when its weights change; renaming would claim credit for what we did not produce.
```

## The shortest path

```javascript
import { Evaluator } from "./api/gammonnet.mjs";
import factory from "./gammonnet-simd.mjs";

// The archive names its own files: never hard-code a version into your code.
const files = await (await fetch("./manifest.json")).json();

const weights = new Uint8Array(
  await (await fetch("./" + files.network_fp16)).arrayBuffer());
const evaluator = await Evaluator.create(factory, weights);

// The pruning network: ×3.65 on a 2-ply decision in a browser, for an equity
// loss that is inside the noise. Optional, strongly recommended.
const prune = new Uint8Array(
  await (await fetch("./" + files.prune_fp16)).arrayBuffer());
evaluator.loadPrune(prune, files.prune_k);

const best = evaluator.bestPlay("4HPwATDgc/ABMA", 0, 3, 1,
                                { ply: 2, filterTop: 3, filterInner: 1 });
console.log(best.equity, best.resultId, best.evaluations);
```

`"4HPwATDgc/ABMA"` is a **Position ID** in GNU Backgammon's format: the standard encoding of a
position, which every backgammon program can produce. The `0` that follows names the player on
roll.

## A whole match, without freezing the page

A 2-ply decision costs ~2 s in a browser: a hundred of them on the thread that draws, and the
interface is frozen for minutes. The pool hands decisions to Web Workers, **one decision per
task**, and returns to the event loop between them.

```javascript
import { EvaluatorPool } from "./api/pool.mjs";

// HOW MANY WORKERS: emphatically not `navigator.hardwareConcurrency`. It counts
// THREADS, while throughput is bounded by physical cores and memory bandwidth —
// each worker reloads its own copy of the weights, there being no
// `SharedArrayBuffer` on a static host.
const size = EvaluatorPool.suggestedSize();

const pool = await EvaluatorPool.create(
  size, "./api/worker.mjs", "./gammonnet-simd.mjs", weights,
  { pruneBytes: prune, pruneK: files.prune_k });

const { done, cancel, schedule } = pool.decide(
  decisions,                       // [{ positionId, turn, d1, d2, options }, …]
  { kind: "rankPlays",
    options: Evaluator.level("normal"),
    onProgress: (n, total) => console.log(`${n}/${total}`) });

const analyses = await done;       // parallel to `decisions`, or `null` if cancelled
console.log(schedule.toJSON());    // this job's scheduling report
pool.destroy();
```

`cancel()` stales what is queued and what is in flight **without destroying the workers**: their
weights stay loaded, and the pool serves the next request immediately.

```{admonition} Measure on your device; do not take our word for it
:class: tip

`suggestedSize()` is a **prudent rule drawn from three readings**, not a measurement of your
device: the platform does not say how many physical cores it has, and `hardwareConcurrency` is
capped at 4 on iOS whatever the phone. `schedule.toJSON()` reports each job's idleness — that is
what settles the question, on the machine that matters.
```

## Position identifiers, and a deliberate boundary

gammonNet does **not** read match files — that is a deliberate boundary of the project. It consumes
**positions**. To analyse a match, have a program that reads matches do it (GNU Backgammon exports
Position IDs) and pass the positions one at a time.

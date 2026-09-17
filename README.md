# gammonNet

A backgammon position evaluator for the browser and for native code — a neural network, an
expectiminimax search, a match equity table and exact bearoff tables.

**It is built on [Alexander Strehl's `backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine)
(MIT): the network weights and the rules engine come from there, trained by self-play.** Written
here: the position codec, the 0→4-ply search and its move filters, the match equity inside the
search, the pruning network, the WebAssembly port and the Web Worker pool — and every measurement
on this page.

**Measured equivalent to GNU Backgammon at 2-ply** — on 50 000 duplicate pairs, in money and in
match play, reproduced on a second machine.

📖 **[Documentation](https://kevung.github.io/gammonNet/)** — user manual, scientific manual and
developer manual, in [English](https://kevung.github.io/gammonNet/en/) and
[French](https://kevung.github.io/gammonNet/fr/).

> One position goes in, one evaluation comes out. This repository does not know its callers: no
> user, no account, no storage, no game library. Everything distributed is permissively licensed,
> with no usage clause — a WebAssembly module served to a browser *is* a distribution, which rules
> out strong copyleft and non-commercial terms.

## Strength, as measured

### Against GNU Backgammon

Full configuration — network, 2-ply filtered search, match equity, bearoff tables, cube — against
GNU Backgammon at the same settings, common dice, bootstrap over duplicate pairs.

| Protocol | Volume | Result | 95 % CI |
|---|---|---|---|
| money, cubeful | 50 000 pairs | **−0.0119 ppg** | [−0.0310 ; +0.0074] |
| match, MWC | 50 000 pairs | **50.42 %** | [50.16 ; 50.69] |

Equivalent, confirmed. **Superior is not established**: in money the interval contains zero, in
match the +0.42 points of MWC clear equality by a hair. eXtreme Gammon has never been measured
here. ([T35](docs/mesures/2026-08-26-T35-verdict.md))

### Performance rating

600 contact decisions, arbiter GNU Backgammon at 3-ply over every legal move. The figures
published for this model are reproduced at all three depths, each inside its interval.

| Configuration | PR | 95 % CI | Published |
|---|---|---|---|
| 0-ply | **1.088** | [0.802 ; 1.412] | 1.06 ✅ |
| 1-ply | **0.499** | [0.330 ; 0.705] | 0.50 ✅ |
| 2-ply `(0,1,3)`, no pruning | **0.273** | [0.190 ; 0.364] | 0.22 ✅ |

The 1-ply figure — 0.499 against 0.50 published, two independent chains and two different
arbiters — is the strongest validation of the search this repository has produced.
([T3E](docs/mesures/2026-08-27-T3E-performance-rating.md))

### Against Backgammon Sage (Open Sage)

The strongest published free engine — MPL-2.0 including its weights, `stage9`: nineteen networks
with a backgame-aware pair strategy — runs locally, so it can be measured directly rather than
through a third-party calibration. Its level labels are offset by one (its `1ply` is raw network
evaluation, our 0-ply), so every comparison is matched on **real depth**, never on the label.

| Protocol | Volume | Result |
|---|---|---|
| Head-to-head, duplicate dice, 0-ply, cubeless money | 500 000 pairs — **1 000 000 games** | **+0.0322 ppg** [+0.0288 ; +0.0356] |
| Paired equity loss per disputed decision, 0-ply | 2 000 decisions | **−0.00682** [−0.00789 ; −0.00575] |
| Paired equity loss per disputed decision, 2-ply | 2 000 decisions | **−0.00232** [−0.00323 ; −0.00137] |

Ahead at both depths, and the head-to-head figure depends on **no arbiter at all**. But the
finding that matters is the third line against the second: **the advantage falls to 34 % of its
value between 0-ply and 2-ply**, on non-overlapping intervals. Two plies of search hand back two
thirds of our static edge — their networks make better use of search than ours does. One position
class flips sign: `holding` goes from −0.00505 at 0-ply to +0.00225 at 2-ply (interval still
contains zero), and that is the family their model specialises in.
([T93](docs/mesures/2026-09-07-T93-ecart-decompose.md),
[T94](docs/mesures/2026-09-07-T94-tete-a-tete-0ply.md))

Nothing of theirs is copied, embedded or used as a training teacher: it is executed as a
measurement instrument, exactly as GNU Backgammon is.

### On a real match

A 7-point match played by humans, analysed decision by decision against GNU Backgammon: **139
decisions, 19 disagreements (13.7 %), and none costing more than 0.0195 equity.** The two engines
diverge where several moves are worth the same, never where a game is decided.
([T3C](docs/mesures/2026-08-27-T3C-analyse-de-match.md))

## Cost in the browser

One 2-ply `(0,1,3)` decision from the opening position, default `k=12` pruning, one worker, median
of 3 passes, desktop Ryzen 7 PRO 6850U.

| Browser | Previous kernel | Shipped kernel |
|---|---|---|
| Chromium 152 | 1.498 s | **0.334 s** — ×4.48 |
| Firefox 154 | 1.155 s | **0.686 s** — ×1.68 |

The same file costs twice as much in Firefox as in Chromium, which is why a speed verdict needs
both. ([T91](docs/mesures/2026-09-03-T91-wasm-noyau-par-defaut.md))

Pruning itself is ×3.65 on a 2-ply decision for an equity loss inside the noise, so it is the
default; a 0-ply decision costs ~6 ms
([T21b](docs/mesures/2026-08-27-T21b-navigateur-elagage.md)). A full 7-point match — 139
decisions — took **50 s on 8 Web Workers** against 212 s on one, and 8 is the useful number of
workers: 16 buys 4 to 6 % of wall time for twice the memory
([T87](docs/mesures/2026-09-02-T87-ordonnancement.md)). Both of those predate the kernel above and
have not been re-measured since.

The WebAssembly artefact is **bit-for-bit with the native engine** — max\|Δ\| = 0 on 2 000
positions, in the scalar *and* the SIMD build.

## Using a release

Every release ships a self-contained archive — weights, WebAssembly, the JavaScript API, the
means to verify it, and the raw evidence behind every published figure.

| | |
|---|---|
| `strehl-prob5-…​.bin` / `.bin16` | network weights, float32 and float16 (half the size) |
| `strehl-prune-32_…​.bin` / `.bin16` | the pruning network |
| `gammonnet-simd.mjs` / `.wasm` | the WebAssembly engine (prefer the SIMD build) |
| `api/gammonnet.mjs` | the JavaScript API — `Evaluator` |
| `api/pool.mjs`, `api/worker.mjs` | the Web Worker pool |
| `verify/` | check for yourself that this artifact returns the right numbers |
| `evidence/` | the raw measurements behind each figure in the release notes |
| `manifest.json` | the file names for this release — read it instead of hard-coding them |
| `NOTICE`, `THIRD-PARTY.md`, `SHA256SUMS` | attribution, licences, checksums |

```js
import { Evaluator } from "./api/gammonnet.mjs";
import factory from "./gammonnet-simd.mjs";

// The archive names its own files — never hard-code a version into your code.
const files = await (await fetch("./manifest.json")).json();

const weights = new Uint8Array(await (await fetch("./" + files.network_fp16)).arrayBuffer());
const evaluator = await Evaluator.create(factory, weights);

const prune = new Uint8Array(await (await fetch("./" + files.prune_fp16)).arrayBuffer());
evaluator.loadPrune(prune, files.prune_k);   // ×3.65, strongly recommended

const level = Evaluator.level("normal");   // ply, move filters, pruning width

// The 5 best moves, each with win / gammon / backgammon probabilities and equity.
// `probs` is `[win, win_g, win_bg, lose_g, lose_bg]`, nested, and since v1.1.0 it
// is the MOVER's — the same side as the `equity` beside it. The pre-v1.1.0
// `forMover` field is gone rather than left beside an already-mirrored `probs`.
const moves = evaluator.rankPlays("4HPwATDgc/ABMA", 0, 3, 1, { ...level, max: 5 });

// Cube decision: no-double, double-take and double-pass equities, and the verdict.
const cube = evaluator.cubeDecision("4HPwATDgc/ABMA", 0, { ...level, owner: 0 });
```

Three levels are exposed — `instant` (0-ply), `normal` (2-ply filtered `(0,1,3)` with `k=12`
pruning, the table above) and `thorough` (the same without pruning; its only timing, ~9.8 s,
predates the current kernel and stands as an upper bound) — along with every parameter: depth,
move filters, pruning width, evaluation cache, cubeful or cubeless valuation, match score, cube
ownership and cube efficiency. See the
[settings reference](https://kevung.github.io/gammonNet/en/manuel/settings.html).

Verify before you trust it — the archive carries a 2 000-position benchmark and the check that
reads it, which **refuses** any deviation beyond 1e-6:

```sh
node verify/parity.mjs           # WebAssembly matches the native engine
node verify/api_invariants.mjs   # the API answers what it promises
```

**Known limits.** The exact bearoff table is *not* shipped: the one the engine consults weighs
1.2 GiB. The endgame therefore falls back on the network, which costs 0.00028 equity per bearoff
decision on average — and up to 0.0919 in the worst case observed. A replacement has been measured
but is **not wired in yet**: a 528 KiB network distilled from the exact table plays the same 8 000
decisions with a worst case of 0.0014, below GNU Backgammon's own 0.0023
([T78](docs/mesures/2026-08-28-T78-distillation-bearoff.md)). The
[limits page](https://kevung.github.io/gammonNet/en/manuel/limits.html) lists every one of them.

## Building from source

```bash
make setup     # Python environment, pinned third-party sources, C engine
make build     # native library
make wasm      # WebAssembly module
make test
```

Python ≥ 3.10 and a C compiler; Emscripten for the browser target. `models/*.bin` is not in the
repository: the weights are rebuilt from Strehl's vendored sources at a pinned commit, which also
verifies on every release that the export chain still works.

## HTTP server (`serve`)

A third target beside the native library and the WebAssembly module: a process that speaks HTTP
instead of exposing a library, for a caller whose language is not C and for whom a network hop is
cheap against the cost of a search. It loads the **same pinned float16 artifact the WebAssembly
target ships**, verifies its SHA-256 before opening a socket, and refuses to start on a mismatch
([#18](https://github.com/kevung/gammonNet/issues/18)).

```bash
python tools/fetch_release.py           # downloads the pinned network + pruning weights
python tools/serve.py --port 8080       # 0-ply by default, 4-ply at most, --max-ply to cap lower
curl -s localhost:8080/healthz
```

Three endpoints, JSON in, JSON out, a non-200 status on any error (invalid XGID, illegal position,
bad parameters) — never a 200 with an error disguised as a result:

| Route | Request | Response |
|---|---|---|
| `POST /v1/eval` | `{xgid, ply}` | `{best_move, equity, candidates: [{move, equity, probs}], ply, probs}` |
| `POST /v1/cube` | `{xgid, kind: "double"\|"take", decider_away, opponent_away, cube, decider_on_roll}` | `{should_double, too_good, no_double, double_take, double_pass, should_take, take, pass, probs}` |
| `POST /v1/rollout` | `{xgid, trials, max_depth, seed}` | `{trials, equity, std_err, win_prob}` |

The contract, in the places it is easy to get wrong:

- `ply` in the response is the depth **actually applied**, never the one requested — read it back
  rather than assume the request was honoured.
- `/v1/eval` needs an XGID carrying a roll (the two dice digits in its 4th field); `/v1/cube` does
  not, since away scores and cube value are explicit request fields, so the same call serves money
  (either away score `0`) and match play. Crawford is assumed false: a documented limitation, not a
  silent guess.
- `/v1/rollout` ignores any dice the XGID carries — a rollout answers for the position *before* a
  roll. `max_depth: 0` plays every trial to completion, the only case where `win_prob` is an
  observed frequency rather than the honest `0.0` a truncated trial reports: it ends on an
  evaluation, not an outcome.
- **A distribution and the equity beside it always describe the same player** — the mover on
  `/v1/eval` and `rankPlays`, the decider on `/v1/cube` and `cubeDecision`. So
  `2·win + win_g + win_bg − lose_g − lose_bg − 1` reproduces that equity exactly, and
  `tests/test_serve.py` and `verify/api_invariants.mjs` both check it. (Underneath,
  `GnCandidate.probs` holds the *resulting* position's distribution — the opponent's — which both
  published surfaces mirror.) `/v1/cube`'s four cube equities are the one thing that does not
  follow the deciding player: they are always the **doubler's**, `take` / `pass` their negation.
- The two surfaces differ on **depth**, deliberately: past 0-ply the probabilities come from the
  shallow ranking pass while the equity comes from the deep search. `/v1/eval` therefore omits
  `probs` for candidates once `ply >= 1`; `rankPlays` keeps them, because an analysis UI displays
  them.

Measured, not assumed: 100 sequential `/v1/eval` requests over loopback HTTP, 0-ply — **2.4 ms per
request**. A 2-ply request costs **≈ 15 s**, because `/v1/eval` applies **no move filter**: its
2-ply is the unfiltered search, not the filtered `(0,1,3)` the browser preset uses. That is why
`--max-ply` exists, and why a deployment should set it against the caller's own latency budget.

Containerised (`Dockerfile`): the image fetches the pinned weights at *build* time and bakes them
in — no network access at run time, and the SHA-256 gate still runs on every start as the final
check that the image's own bytes were not altered afterwards.

```bash
docker build -t gammonnet-serve .
docker run --rm -p 8080:8080 gammonnet-serve
```

## What is reused, what is written here

| Component | Origin | Status |
|---|---|---|
| Network weights, rules engine, `.bin` reader | Strehl, MIT | reused, isolated behind an interface |
| Kazaross-XG2 match equity table | Neil Kazaross | reused, cross-checked against GNU Backgammon |
| Position ↔ 196-feature codec | — | written here |
| Expectiminimax search 0→4 ply, move filters | idea documented in the GNU Backgammon manual; no code taken | written here |
| Match equity inside the search | GNU Backgammon architecture: cubeless network, conversion after | written here |
| Pruning network, distilled from the big one | — | written here |
| WebAssembly port, Web Worker pool, SIMD kernels | — | written here |

## Project status

Phases 0 through 5 are complete, and v1.3.0 is the artefact they produce. Phase 4 — a
project-specific model — stays closed: it was conditional on the existing model proving
insufficient, and it did not. Phase 8 delivered the browser speed above. Phase 9 found this engine
ahead of the strongest published free one at both depths, and found the edge eroding with search —
the one thing it changed in the plan of work. Phase 7 is under way: going past parity with GNU
Backgammon rather than matching it.

| | Tasks | State |
|---|---|---|
| 0 — Foundations & instrument | T00 → T05 | ✅ |
| 1 — Reproduce published figures | T10 · T11 · T12 | ✅ |
| 2 — Browser | T20 → T23 | ✅ |
| 3 — Depth & exactness | T30 → T3E | ✅ |
| 4 — Project-specific model | — | closed |
| 5 — Publication | T50 · T51 | ✅ |
| 7 — Going further | T70 → T83 | in progress |
| 8 — Speed where the caller pays | T84 → T91 | ✅ |
| 9 — Against the strongest published free engine | T92 → T95 | ✅ (T95 not opened) |

Every task carries a report in [`docs/mesures/`](docs/mesures/), which distinguishes what was
measured from what was estimated. Working documents: [`CLAUDE.md`](CLAUDE.md) (rules),
[`BRIEF.md`](BRIEF.md) (context, sources, licences), [`PLAN.md`](PLAN.md) (task sheets),
[`THIRD-PARTY.md`](THIRD-PARTY.md) (licence inventory).

## Credits

- Network and rules engine — [Alexander Strehl](https://github.com/alexstrehl/backgammon-ai-engine), MIT.
- Kazaross-XG2 match equity table — Neil Kazaross; read from `Kazaross-XG2.xml`, the rendering
  GNU Backgammon ships and loads by default.
- GNU Backgammon — measurement oracle and match equity reference. Not a source of code or weights.

## Licence

MIT. See [`LICENSE`](LICENSE) and [`THIRD-PARTY.md`](THIRD-PARTY.md).

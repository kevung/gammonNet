# gammonNet

A backgammon position evaluator for the browser and for native code — a neural network, an
expectiminimax search, a match equity table and exact bearoff tables.

**Measured equivalent to GNU Backgammon at 2-ply.** Not asserted: measured, on 50 000 duplicate
pairs, in both money and match play, and reproduced independently on a second machine.

📖 **[Documentation](https://kevung.github.io/gammonNet/)** — user manual, scientific manual and
developer manual, in [English](https://kevung.github.io/gammonNet/en/) and
[French](https://kevung.github.io/gammonNet/fr/).

> One position goes in, one evaluation comes out. This repository does not know its callers: no
> user, no account, no storage, no game library. Everything distributed is permissively licensed,
> with no usage clause — a WebAssembly module served to a browser *is* a distribution, which rules
> out strong copyleft and non-commercial terms.

## Strength, as measured

Full configuration — network, 2-ply filtered search, match equity, bearoff tables, cube — against
GNU Backgammon at the same settings, common dice, bootstrap over duplicate pairs.

| Protocol | Volume | Result | 95 % CI |
|---|---|---|---|
| money, cubeful | 50 000 pairs | **−0.0119 ppg** | [−0.0310 ; +0.0074] |
| match, MWC | 50 000 pairs | **50.42 %** | [50.16 ; 50.69] |

**Equivalent, confirmed. Superior: not established** — and eXtreme Gammon has never been measured
here. In money the interval contains zero; in match the edge is +0.42 points of MWC, separated
from equality but by a hair. ([T35](docs/mesures/2026-08-26-T35-verdict.md))

### Performance rating

600 contact decisions, arbiter GNU Backgammon at 3-ply over every legal move. The published
reference figures for this model are reproduced at all three depths, each inside its interval.

| Configuration | PR | 95 % CI | Reference |
|---|---|---|---|
| 0-ply | **1.088** | [0.802 ; 1.412] | 1.06 ✅ |
| 1-ply | **0.499** | [0.330 ; 0.705] | 0.50 ✅ |
| 2-ply `(0,1,3)`, no pruning | **0.273** | [0.190 ; 0.364] | 0.22 ✅ |

The 1-ply figure — 0.499 against 0.50 published, two independent chains and two different
arbiters — is the strongest validation of the search this repository has produced.
([T3E](docs/mesures/2026-08-27-T3E-performance-rating.md))

### On a real match

A 7-point match played by humans, analysed decision by decision against GNU Backgammon: **139
decisions, 19 disagreements (13.7 %), and none costing more than 0.0195 equity.** The two engines
diverge where several moves are worth the same, never where a game is decided.
([T3C](docs/mesures/2026-08-27-T3C-analyse-de-match.md))

## Cost in the browser

Opening position, Chromium, one worker. The pruning network sorts the moves so the big network
scores only a handful of them.

| Configuration | Evaluations | Cost per decision |
|---|---|---|
| 0-ply | 16 | **6 ms** |
| 1-ply | 7 475 | 2 289 ms |
| 2-ply `(0,1,3)`, no pruning | 38 721 | 9 813 ms |
| **2-ply `(0,1,3)`, pruning `k=12`** | 15 142 | **2 689 ms** |

Pruning is ×3.65 on a 2-ply decision for an equity loss inside the noise, so it is the default.
With 8 Web Workers throughput reaches 26 667 eval/s (×6.2), and a full 7-point match is analysed
in **74 s**. WebAssembly matches the native engine exactly in scalar builds (max\|Δ\| = 0) and to
6.4e-7 with SIMD.

## Using a release

Every release ships a self-contained archive — weights, WebAssembly, the JavaScript API, the
means to verify it, and the raw evidence behind every published figure.

| | |
|---|---|
| `strehl-prob5-…​.bin` / `.bin16` | network weights, float32 and float16 (half the size) |
| `strehl-prune-32_…​.bin` / `.bin16` | the pruning network |
| `gammonnet-simd.mjs` / `.wasm` | the WebAssembly engine (prefer the SIMD build) |
| `api/gammonnet.mjs` | the JavaScript API — `Evaluator` |
| `api/pool.mjs`, `api/worker.mjs` | the Web Worker pool — a match in 74 s instead of 350 |
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
const moves = evaluator.rankPlays("4HPwATDgc/ABMA", 0, 3, 1, { ...level, max: 5 });

// Cube decision: no-double, double-take and double-pass equities, and the verdict.
const cube = evaluator.cubeDecision("4HPwATDgc/ABMA", 0, { ...level, owner: 0 });
```

Three analysis levels are exposed — `instant` (0-ply, ~6 ms), `normal` (2-ply filtered with
pruning, ~2.7 s) and `thorough` (the same without pruning, ~9.8 s) — along with every underlying
parameter: depth, move filters, pruning width, evaluation cache, cubeful or cubeless valuation,
match score, cube ownership and cube efficiency. See the
[settings reference](https://kevung.github.io/gammonNet/en/manuel/settings.html).

Verify before you trust it — the archive carries a 2 000-position benchmark and the check that
reads it, which **refuses** any deviation beyond 1e-6:

```sh
node verify/parity.mjs           # WebAssembly matches the native engine
node verify/api_invariants.mjs   # the API answers what it promises
```

**Known limits.** The exact bearoff table is *not* shipped: the one the engine consults weighs
1.2 GiB. The endgame therefore falls back on the network, which costs 0.00028 equity per bearoff
decision on average — and up to 0.0919 in the worst case observed. The
[limits page](https://kevung.github.io/gammonNet/en/manuel/limits.html) lists every one of them.

A replacement has been measured but is **not wired in yet**: a 528 KiB network distilled from the
exact table plays the same 8 000 decisions with a worst case of 0.0014, below GNU Backgammon's own
0.0023 — see [T78](docs/mesures/2026-08-28-T78-distillation-bearoff.md).

## Building from source

```bash
make setup     # Python environment, pinned third-party sources, C engine
make build     # native library
make wasm      # WebAssembly module
make test
```

Python ≥ 3.10 and a C compiler; Emscripten for the browser target. Note that `models/*.bin` is not
in the repository — the weights are rebuilt from Alexander Strehl's vendored sources at a pinned
commit, which also verifies on every release that the export chain still works.

## HTTP server (`serve`)

A standalone process that speaks HTTP instead of exposing a library — the `blunderdb serve` shape
applied here: one generic evaluator, any consumer (gammonGo today, Desktop/blunderDB tomorrow —
[kevung/blunderDB#119](https://github.com/kevung/blunderDB/issues/119)) points at it over the
network instead of embedding this repository. It loads the **same pinned float16 artifact the
WebAssembly target ships**, verifies its SHA-256 before opening a socket, and refuses to start on
a mismatch — never a server answering on the wrong weights ([#18](https://github.com/kevung/gammonNet/issues/18)).

```bash
python tools/fetch_release.py           # downloads the pinned network + pruning weights
python tools/serve.py --port 8080       # 0-ply by default, 4-ply at most, --max-ply to cap lower
curl -s localhost:8080/healthz
```

Three endpoints, JSON in, JSON out, a non-200 status on any error (invalid XGID, illegal
position, bad parameters) — never a 200 with an error disguised as a result:

| Route | Request | Response |
|---|---|---|
| `POST /v1/eval` | `{xgid, ply}` | `{best_move, equity, candidates: [{move, equity, probs}], ply, probs}` |
| `POST /v1/cube` | `{xgid, kind: "double"\|"take", decider_away, opponent_away, cube, decider_on_roll}` | `{should_double, too_good, no_double, double_take, double_pass, should_take, take, pass, probs}` |
| `POST /v1/rollout` | `{xgid, trials, max_depth, seed}` | `{trials, equity, std_err, win_prob}` |

`ply` in the response is the depth **actually applied**, never the one requested — a caller must
read it back rather than assume its request was honoured (the same discipline gammonGo's own
client already applies to `evald`). `/v1/eval` needs an XGID that carries a roll (the two dice
digits in its 4th field); `/v1/cube` does not — the decider's away scores and the cube value are
explicit request fields, not read from the XGID's own score/cube fields, so the same call works
for money (either away score `0`) and match play. `/v1/rollout` ignores any dice the XGID carries:
a rollout answers for the position *before* a roll, and `max_depth: 0` plays every trial to
completion — the only case `win_prob` is an observed frequency rather than the honest `0.0` a
truncated rollout reports (`gn_rollout.h`: a truncated trial ends on an evaluation, not an
outcome).

`probs` — `{win, win_g, win_bg, lose_g, lose_bg}` — carries the network's five raw nested
probabilities alongside the equity, per `gn_infer.h`'s own insistence that the distribution is the
real output. `/v1/eval` omits it for a candidate scored below the network (`ply >= 2`, where the
number would describe a shallow ranking pass, not the move). `/v1/cube`'s `probs` is always the
**decider's own** distribution (`decider_on_roll: false` mirrors it), while the four cube equities
are always the **doubler's**; `take`/`pass` (kind `"take"`) are their exact negation. Crawford is
not part of this contract and is assumed false — a documented limitation, not a silent guess.

Measured, not assumed: 100 sequential `/v1/eval` requests over loopback HTTP, 0-ply, this
machine — **2.4 ms/request**. A single 2-ply decision with the default `k=12` pruning network —
**≈ 15 s**, which is why `--max-ply` exists and why a production deployment should set it with the
caller's own latency budget in mind, not this repository's.

Containerised (`Dockerfile`): the image fetches the pinned weights at *build* time and bakes them
in — no network access needed at run time, and the SHA-256 gate still runs on every start as the
final check that the image's own bytes were not altered afterwards.

```bash
docker build -t gammonnet-serve .
docker run --rm -p 8080:8080 gammonnet-serve
```

## What is reused, what is written here

The network weights come from
[`alexstrehl/backgammon-ai-engine`](https://github.com/alexstrehl/backgammon-ai-engine) (MIT),
trained by self-play.

| Component | Origin | Status |
|---|---|---|
| Network weights, rules engine, `.bin` reader | Strehl, MIT | reused, isolated behind an interface |
| Kazaross-XG2 match equity table | Neil Kazaross | reused, cross-checked against GNU Backgammon |
| Position ↔ 196-feature codec | — | written here |
| Expectiminimax search 0→4 ply, move filters | idea documented in the GNU Backgammon manual; no code taken | written here |
| Match equity inside the search | GNU Backgammon architecture: cubeless network, conversion after | written here |
| Pruning network, distilled from the big one | — | written here |
| WebAssembly port, Web Worker pool | — | written here |
| ×9 forward-pass throughput, bit-exact | — | written here |

## Project status

Phases 0 through 5 are complete, and v1.0.1 is the artefact they produce. Phase 4 — a
project-specific model — stays closed: it was conditional on the model proving insufficient, and it
did not. Phase 7 is under way: going past parity with GNU Backgammon rather than matching it.

| | Tasks | State |
|---|---|---|
| 0 — Foundations & instrument | T00 · T01 · T02 · T03 · T04 · T05 | ✅ |
| 1 — Reproduce published figures | T10 · T11 · T12 | ✅ |
| 2 — Browser | T20 · T21 · T22 · T23 | ✅ |
| 3 — Depth & exactness | T30 → T3E | ✅ |
| 4 — Project-specific model | — | closed |
| 5 — Publication | T50 · T51 | ✅ |
| 7 — Going further | T70 → T77 | in progress |

Every task carries a report in [`docs/mesures/`](docs/mesures/), which distinguishes what was
measured from what was estimated. Working documents: [`CLAUDE.md`](CLAUDE.md) (rules),
[`BRIEF.md`](BRIEF.md) (context, sources, licences), [`PLAN.md`](PLAN.md) (task sheets),
[`THIRD-PARTY.md`](THIRD-PARTY.md) (licence inventory).

## Credits

- Network and rules engine — [Alexander Strehl](https://github.com/alexstrehl/backgammon-ai-engine), MIT.
- Kazaross-XG2 match equity table — Neil Kazaross; transcription cross-checked with
  [blunderDB](https://github.com/kevung/blunderDB), MIT.
- GNU Backgammon — measurement oracle and match equity reference. Not a source of code or weights.

## Licence

MIT. See [`LICENSE`](LICENSE) and [`THIRD-PARTY.md`](THIRD-PARTY.md).

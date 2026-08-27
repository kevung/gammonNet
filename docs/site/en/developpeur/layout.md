# Repository layout

## The boundary rule

> **This repository evaluates a position. It does not know its callers.**

| Here | Elsewhere |
|---|---|
| network, search, match equity, bearoff | storage, game libraries |
| training, strength measurement | **match import**, multi-criteria search |
| | user interface |

No notion of user, account, session or persistence enters here. That is why match analysis has
**GNU Backgammon read the file** and consumes only position identifiers.

## Directories

| | |
|---|---|
| `src/` | the C engine: rules, encoding, inference, search, match equity, cube, tables |
| `python/gammonnet/` | the `ctypes` wrapper — no domain logic, only the boundary crossing |
| `bench/` | measurement instruments. One benchmark per question |
| `tests/` | ~1 500 tests, including the non-regression corpus |
| `tools/` | weight export, pruning-network training, artefact packaging |
| `wasm/` | the browser port: C module, JavaScript API, worker pool, measurement pages |
| `docs/mesures/` | **one record per measurement** — protocol, volume, interval, command |
| `docs/etudes/` | ideas investigated but not implemented, and the reading register |
| `vendor/` | third-party sources at a pinned commit. Gitignored |

## Two targets, one code

The **same** C serves both. `WASM_SOURCES` must therefore track `SOURCES`: when the search gained
dependencies during phase 3, the WebAssembly target stopped compiling — **which is the right way to
fail**, but only showed at the next build.

## The flow of a decision

```
Position ID
   └─ gn_position_from_id
        └─ gn_search_plays
             ├─ gn_legal_plays              (rules)
             ├─ pruning pass                (small network, if configured)
             ├─ shallow pass                (big network, batched)
             │    └─ evaluate_cheap: exact table, then cache, then network
             ├─ value_sweep                 (probabilities → equity, money or match)
             └─ deep pass                   (recursion over the best filter[d])
```

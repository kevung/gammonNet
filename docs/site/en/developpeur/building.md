# Building, testing, measuring

## Native

```sh
make setup     # venv, vendored sources at the pinned commit
make build     # build/libgammonnet.so
make test      # ~1 500 tests
```

No exotic system dependency: the target is "it compiles with a compiler and nothing else".

## Build variants, and what they change

| | Effect |
|---|---|
| default (`-O2`) | development build; outputs **bit-identical** to the scalar path |
| `NATIVE_FP=1` | ~4× faster, outputs moved by about 6e-7. The campaign build |
| `-ffp-contract=off` | set unconditionally on `gn_search.c` — see [](invariants) |
| `-DGN_BATCH_FILL_STATS` | instruments batch fill |

The **evaluation fingerprint** differs between these builds, and a campaign journal refuses it: that
is intended.

## WebAssembly

```sh
make wasm         # scalar and SIMD
make wasm-parity  # parity BEFORE any speed figure
```

`gn_wasm.c` compiles **without** Emscripten (the include is guarded), so `cc -c` checks it anywhere;
only linking needs `emcc`.

## The artefact

```sh
make artifact VERSION=v1
```

The script **refuses** to produce an incomplete directory: it replays the non-regression corpus
before writing anything, and reports any missing piece.

## Writing a benchmark

Every benchmark here follows the same shape, and it is not a style:

1. **The protocol at the top of the file**, including what the measurement does *not* say.
2. **Two columns whenever an arbiter is involved**, never one.
3. **A confidence interval**, bootstrapped over the independent unit.
4. **A pilot before the volume.**
5. **An explicit refusal** when an input is out of domain.
6. **`--workers`, and it must be true**: a benchmark whose documentation advertised parallelism
   without implementing it cost 68 minutes where 6 sufficed.

# Verifying the artefact yourself

## Parity with the reference engine

```sh
node verify/parity.mjs
```

It compares the WebAssembly module against the native engine over a **2 000-position** reference and
**refuses** beyond 1e-6.

```
✅ scalar   max|Δ| = 0.000e+0
✅ SIMD     max|Δ| = 6.407e-7
```

The scalar build is **exact**. The SIMD build reassociates sums, hence 6.4e-7 — bounded, documented,
and with no effect on the move chosen.

## API invariants

```sh
node verify/api_invariants.mjs
```

Parity says the module **computes** like the native engine. This says it **answers what it
promises** — that the ranked candidate list is ordered by equity, that its first entry is the move
`bestPlay` returns, that every candidate carries five usable probabilities, that those probabilities
describe **the same player as the equity beside them**, and that with the move filter off, the N
best moves do not depend on N.

The frame-of-reference check is the newest, and it took two misreadings of the same kind to get
written. A nesting check cannot do it: a mirrored distribution is still perfectly nested. What bites
is the identity — cubeless money equity **is** a function of the five probabilities, so at 0-ply,
recomputing one from the others must reproduce it. Under an inversion the reconstruction comes out
with the opposite sign, and no tolerance hides that. Alongside it, the move that **ends** the game:
its probabilities were zeroed, which, mirrored, said "certain win, no gammon" on a bear-off that
wins a gammon.

That last one is not decoration. `rankPlays` once sized its candidate buffer to the number of moves
you asked for, and the search truncates to its buffer **before evaluating anything**, in
move-generation order — so asking for 3 moves ranked 3 arbitrary ones. On the opening 3-1 the
second-best move came back at −0.1262 where the full list finds −0.0029. Nothing looked wrong:
plausible probabilities, plausible equities, a descending order. Only comparing two calls revealed
it.

With the filter **on**, the top N legitimately do depend on N — a filter of N deep-searches the N
most promising moves of a shallow pass, and the true N-th may lie outside it. GNU Backgammon
behaves the same way.

## Checksums

```sh
sha256sum -c SHA256SUMS
```

The `sha256` of the weights must match the one recorded in `verify/*.provenance.json` — unchanged
since the first day of the project.

## The raw measurements

`evidence/` holds the data behind every figure in the release notes. Nothing is aggregated: these
are the benchmarks' own outputs.

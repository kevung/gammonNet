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

## Checksums

```sh
sha256sum -c SHA256SUMS
```

The `sha256` of the weights must match the one recorded in `verify/*.provenance.json` — unchanged
since the first day of the project.

## The raw measurements

`evidence/` holds the data behind every figure in the release notes. Nothing is aggregated: these
are the benchmarks' own outputs.

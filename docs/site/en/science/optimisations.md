# Optimisations, and the four projections the measurement refuted

## Constraint

**Go faster without degrading the analysis.** That excludes anything trading quality for time. Only
**exact** gains remain — the result does not move by a bit — or **measured-free** ones.

## What was gained

| | Before | After | |
|---|---|---|---|
| 2-ply decision `(0,1,3)` | 2.0075 s | **0.306 s** | **×6.6** |
| 3-ply decision | 60 to 96 s | **10.60 s** | ×5.7 to ×9 |
| Artefact (weights) | 2.1 MiB | **1.06 MiB** | ×1.99 |

## Batch inference

Weights are read once for thirty-two positions instead of once per position: ×8.5 native, ×2.21 in a
browser. **Bit-identical to the per-position path** — not merely close.

## The pruning network, and the ceiling it first hit

**The projection said ×4.3. The measurement gave ×1.36.**

```{admonition} The cause, and it is instructive
:class: important

The kernel computes **32 lanes regardless**. Pruning removed 82 % of the evaluations but only
**26 % of the work**: every node still made its call, with five positions instead of twenty. **A
call with five positions costs exactly what a call with thirty-two costs.**

Measured fill: **14.5 %** of lanes carried a useful position.
```

## Filling the batches — the gain that unlocked the rest

Pooling the survivors of all **twenty-one rolls** of a node into the same batches raised fill from
14.5 % to **80.5 %**, and lanes computed from 831 136 to 150 112.

The gain **transports to the browser**: ×3.65 measured on Firefox against ×3.9 native — the open
question, since batching only buys ×2.21 there.

## Input sparsity

The 196-feature vector has only **26 non-zero entries** on average, and **38.3** for a 32-move
sibling union.

**Exact, not approximate**: in IEEE 754, `acc + w × 0.0` *is* `acc`, without rounding. Measured
**×1.15** on a decision at any depth.

## The four refuted projections

This is the most useful section on this page: **four times, reasoning about operation counts
predicted the wrong outcome.**

| Projection | Measurement |
|---|---|
| "Pruning should give ×4.3" | **×1.36** — the kernel computes 32 lanes regardless |
| "Group passes to keep the small network in cache" | **2.2 % slower** |
| "Also merge the small network's batches" | **0.7 to 0.9 %** — inside the noise, branch abandoned |
| "Skip 80 % of the first layer" | **slower** when indexed indirectly; the columns had to be **compacted** |

The fourth deserves detail: skipping zero inputs by indexing `w_row[nonzero[idx]]` did **five times
fewer multiplications** and ran **slower**. Live columns and their weights had to be gathered into
**contiguous** buffers so the hot loop stayed a stream. **Access pattern beats operation count.**

## FMA contraction, caught by a verification

Checking that a loop rearrangement changed nothing, equities moved by ~3e-9. Batch composition,
uninitialised memory (valgrind) and non-determinism were all ruled out by measurement.

What remained was **contraction**: the compiler fuses `a×b + c` into an FMA — one rounding instead
of two — **depending on the shape of the surrounding code**. `-ffp-contract=off` on the search file,
and only there. Measured cost: **1 %**.

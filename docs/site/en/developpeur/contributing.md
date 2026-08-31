# Contributing

## Three non-negotiable rules

### 1. Nothing non-free in a distributed artefact

A WebAssembly module served to a browser **is a distribution**.

| Forbidden | Reason |
|---|---|
| GNU Backgammon weights, or anything derived | GPL-3 |
| GNU Backgammon code copied into the pipeline | derivative work |
| Networks under a non-commercial clause | outside this project's licensing |

| Allowed | Basis |
|---|---|
| Reading GNU Backgammon's code and manual | the GPL governs distribution, not reading |
| Running it as a **measurement oracle** | *"The output of a program is not, in general, covered by the copyright on the code of the program"* |
| Reimplementing documented ideas | an idea is not a work |
| Bearoff tables, whatever their origin | exact, reproducible computation |

**When in doubt about a source: do not integrate it, and ask.** A legally doubtful component
embedded in a distributed artefact is the one kind of mistake a patch cannot undo.

`docs/etudes/` keeps the **register of ideas read and reimplemented** — the memory of what was read,
and when.

### 2. No strength is claimed without measurement

Every claim cites **protocol, volume and confidence interval**.

### 3. A performance conclusion is measured

No throughput, latency or size figure follows from reading code. This repository contains **four
optimisation projections refuted by measurement**, one of them going the wrong way: they are kept,
with their figures, so nobody repeats them.

## What a change is expected to carry

- **A non-regression test** for any numerical component. A change that moves an output must do so
  **visibly**.
- **A measurement record** in `docs/mesures/`, with its reproduction command.
- **Atomic commits.** The message says *why*; the diff already says *what*.
- **Record what did not work.** An abandoned branch with its measurement beats silence.

## Naming

A network only becomes a different network **when its weights change**. Quantisation gives
"X quantised", not "Y". Weights therefore carry their author's name; **gammonNet** names the
configuration.

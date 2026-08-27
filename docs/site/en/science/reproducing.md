# Reproducing every measurement

## Prepare

```sh
make setup     # Python environment, vendored sources at the pinned commit
make build     # the native library
make model     # weights, exported from the vendored source
```

Weights are **not in the repository**: they come from Alexander Strehl's work at a pinned commit.
Rebuilding them also verifies the export chain still works.

## Strength

```sh
python bench/run_t35.py --mode money --pairs 50000 --workers 24 \
    --journal docs/mesures/t35-money.jsonl \
    --ours-ply 2 --ours-filter 0,1,3 --gnubg-ply 2 --gnubg-filter 0,1,3
python bench/report_t35.py --journal docs/mesures/t35-money.jsonl
```

Campaigns are **segmentable**: `Ctrl-C`, a shutdown or `--minutes` interrupt them, and rerunning the
same command resumes. A segmented run is **bit-identical** to a single run — tested.

## Error rate (PR)

```sh
python bench/pr.py --decisions 600 --plies 0,1,2,2@0 --arbiter-ply 3 --workers 24
```

`2@0` means 2-ply **without** pruning: several configurations in one pass, hence a single
arbitration. The arbiter is cached — it depends only on the corpus and its depth.

## Match analysis

```sh
python bench/analyse_match.py --match test.sgf --ply 2 --prune-k 12 --max-decisions 400
```

## Optimisations

```sh
make bench-decision
make bench-encoding
python bench/prune_search.py --contact 300 --race 150 --ks 2,3,5,8,12 --workers 26
```

## Browser

```sh
make wasm && make wasm-parity          # parity BEFORE any speed figure
node wasm/harness.mjs --browser firefox --page /wasm/decision.html --build simd
node wasm/harness.mjs --browser firefox --page /wasm/workers.html  --build simd
```

## Verify the published artefact

```sh
node verify/parity.mjs
```

Expected: `max|Δ| = 0` scalar, ~6.4e-7 SIMD, over the 2 000-position reference.

## Tests

```sh
python -m pytest tests/ -q       # ~1 500 tests, ~10 min
```

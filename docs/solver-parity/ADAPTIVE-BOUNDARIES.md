# Adaptive ten-second problem-size boundaries

This study uses independent exponential bracketing and integer binary search to
find a ten-second boundary for each native solver version. A version stops
expanding after its first failed size. It then searches smaller sizes between
its last success and failure. The candidate and its adjacent sizes receive two
runs; every knapsack size includes both profit variants. Failed confirmations
remain recorded and can lower the reported boundary.

The displayed value is the **largest sampled, confirmed size**, not an absolute
solver limit. Integer-programming difficulty is not monotonic in variable count.
A larger untested instance can be easier than a smaller failed one. The report
preserves observed reversals, unconfirmed discoveries, search ceilings and every
actual input and decision. Missing outcomes are unknown, never synthetic
failures or estimated completion times.

After both searches, timing points within the smaller confirmed boundary (plus
its adjacent size) are shared where needed. The weaker version is not run across
the stronger version's large-size range. Each curve uses only actual observations
for that version. Discovery uses one run; confirmation uses two. A knapsack
point summarizes both variants and all its runs, with the complete timing range.
No full-cohort completion-time estimate is shown if any run is unfinished.

## Recorded results

The local run records **162 measurements across 71 sampled inputs** in **931.62 seconds**, plus two loader probes. The measured tooling source is `f724bd01795a87b2c310ba368c66d36bb09f660f`. Every headline size passes two runs per version and every knapsack variant.

| Category | Before confirmed | Optimized confirmed | Next tested failure (before / optimized) |
| --- | --- | --- | --- |
| Knapsack | 33 items / 33 model variables | 407 items / 407 model variables | 34 / 408 in natural size units |
| Assignment | 17 tasks / 289 model variables | 17 tasks / 289 model variables | 18 / 18 in natural size units |
| Facility location | 8 sites / 136 model variables | 8 sites / 136 model variables | 9 / 9 in natural size units |
| Bin packing | 17 items / 108 model variables | 17 items / 108 model variables | 18 / 18 in natural size units |
| Production planning | 11 periods / 88 model variables | 11 periods / 88 model variables | 12 / 12 in natural size units |
| Routing | 21 cities / 42 model variables | 21 cities / 42 model variables | 22 / 22 in natural size units |
| Weighted queens | 23 queens / 92 model variables | 23 queens / 92 model variables | 24 / 24 in natural size units |

Knapsack expands from 33 to 407 items (12.33 times the sampled size). At 33 items, the older correlated case takes 9.990 and 9.730 seconds; the boundary is sensitive to host timing. Both 407-item optimized variants complete near 28 ms. The other six confirmed capacities match.

One assignment timeout reports 25.724 seconds internally but 8.819 seconds externally. The host clocks disagreed; the cause is not established. That observation remains unfinished and has no completion-time estimate. Its second confirmation also reaches the limit with consistent clocks. No completed result has this discrepancy.

The [complete portable record](checkpoints/boundaries.json) preserves raw results, inputs, decisions, untested cohorts and clock details. Earlier observations are not pooled into this adaptive experiment.

## Models and interpretation

Inputs use deterministic extensions of the previous seeded model blocks. The
new generator preserves their existing data where dimensions coincide. Facility
location now has twice as many customers as candidate sites; bin packing uses
`ceil(items/3)` candidate bins. These dimensions differ from some cases in the
previous fixed suite, so this is a separate study.

| Category | Natural size | Model variables | Search domain |
| --- | --- | --- | --- |
| Knapsack | Items `n`, both profit variants | `n` Binary | 8..512 |
| Assignment | Tasks/workers `n` | `n*n` Binary | 3..32 |
| Facility location | Sites `n`, customers `2*n` | `n+2*n*n` Binary | 2..16 |
| Bin packing | Items `n`, bins `b=ceil(n/3)` | `n*b+b` Binary | 4..32 |
| Production planning | Periods `n`, eight options | `8*n` Binary | 3..48 |
| Circuit routing | Cities `n` | `2*n` integer, including cost columns | 4..96 |
| Weighted queens | Queens `n` | `4*n` integer, including diagonal/cost columns | 4..32 |

Counts compare versions within one category, not difficulty across categories.
The native driver and before/current runtime libraries are the same preserved
products as the earlier seven-category study. There is no solver algorithm or
ABI change in this experiment.

Every accepted solution is independently checked against its original model,
objective and auxiliary values. Exact optimality is reported by the backend;
this study does **not** independently recompute all reference optima. Matching
reported objective and bound alone is not an independent optimality certificate.
Cross-version and repeated optimum disagreements, better feasible peer solutions,
contradictory peer bounds, malformed results and process failures reject the
study instead of becoming a size boundary.

## Execution and reproduction

Every solve uses Native/BAB, Exact, one thread, no starts, seed zero, zero gap
allowances and a ten-second internal budget. Capture allows eleven seconds plus
at most 0.5 seconds cleanup. The full invocation is bounded to 2,400 seconds,
480 subprocess attempts including loader probes, and 32 distinct sizes per
category. Confirmation can reconsider a changed boundary at most six times.
A ceiling or unfinished confirmation is reported as unresolved.

The generator, source hashes and search policy are fixed before measurement.
Each deterministic input is saved and hashed before its first solve. Every
attempt is recorded before launch; raw output, monotonic offsets, search choices
and every failed confirmation are retained. Two loader probes establish the
actual library cohorts, and final integrity checks cover source, driver, inputs
and libraries. Preparation/validation occurs outside internal solve timing.

From the repository root, using the preserved local products:

```sh
python3 -B experiments/optimize/benchmark_boundaries.py \
  --output-dir build/adaptive-boundaries/results
```

Choose a new output directory for another study. Existing directories are never
overwritten. The runner builds or downloads nothing and does not resume or retry
an interrupted solve. Sixteen focused generator/runner tests cover encodings,
original validation, independent search behavior, confirmation and budget gates.

The complete portable results are linked from the benchmark page. Earlier
[fixed category results](CATEGORY-SCALING.md), [capacity results](CAPACITY-SCALING.md)
and [algorithm results](ALGORITHMIC-CHECKPOINT.md) remain separate checkpoints.

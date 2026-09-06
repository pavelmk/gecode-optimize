# Native search algorithm checkpoint

This checkpoint adds a bounded exact optimization for binary capacity models in
`Gecode::Optimize`. It adds no new model class, public option or ABI. The larger
commercial-parity roadmap remains unfinished and on hold.

## Changes

Ordinary native search recognizes a pure capacity model: every active variable
is Binary with domain `[0,1]`, and one integral row covers every variable with
strictly positive weights and an upper capacity, or the equivalent negative
weights and lower capacity. The opposite row side must be absent or redundant.
Active indicators, globals, additional rows and uncovered columns are excluded.
Explicit checked-LP and local-neighborhood construction retain their existing
behavior.

An exact item/capacity dynamic program computes the best objective for each
at-most capacity. The full table keeps reconstruction independent of overwritten
predecessors. Capacity is capped at **65,536**, and the complete table, including
its base row, at **one million 64-bit cells** (at most 8 MB of table storage).
The frozen 80-variable knapsack uses 27,378 cells. Shape or size-cap misses fall
back to ordinary search. Time/cancellation checks remain active; an unfinished
computation supplies no bound. Costs are normalized for both objective senses;
the exact offset remains separate.

After reconstructing and independently recomputing its binary witness, row load
and original objective, the optimization supplies a **one-sided objective bound**
and an owning, domain-checked branch preference. Existing search still validates
and publishes incumbents, statuses, bounds and node counts. DP cells are
preprocessing work, not invented search nodes. Generic smallest-domain,
minimum-first branching and non-DP frontier order remain unchanged. DP hints
follow each engine's actual descent order; BestBound favors the region containing
the verified DP witness only when objective bounds tie, preventing a flat exact
bound from delaying that solution behind unrelated siblings. Original Gecode
user-defined branchers and numerical HiGHS solving are unaffected.

This is a deliberately capped, pseudopolynomial exact special case, using the
standard take/skip recurrence described in
[MIT's knapsack notes, pages 1–3](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/95e744ee64464cb6bc8f8264faeea080_MIT6_006F11_rec21.pdf).
It is not a new general MILP engine or a state-of-the-art core knapsack solver.
The small eligible model can avoid a long enumeration without tuning parameters
or new dependencies.

## Validation

The frozen solver product is `b57bf49ad`; final source identity and runtime hashes
are retained in the accepted benchmark record. The current **70/70 Release
CTest entries pass**, including the original native tests, actual FlatZinc and
MiniZinc pipeline, and **84 Python tests**. The **12 affected native ASan/UBSan
tests pass**, using the existing instrumented native/HiGHS build with leak
checking disabled and halt-on-error enabled. The new backend-disabled boundary
case also passes. Release and sanitizer gates ran in parallel in separate build
directories; their elapsed times are validation durations, not performance
comparisons. The earlier full sanitizer/platform records remain historical.

The new native capacity test checks **1,494 finite-oracle and budget
configurations**, including both objective senses and row orientations, signed
and zero costs, offsets, aliases/tombstones, caps, fallback models, starts,
LP bypass and clone ownership. A zero-cost tie fixture requires all three search
modes to finish within a linear node quota. Two coordinator-only fault cases
interrupt after one completed DP row: neither cancellation nor allocation
failure may publish the tighter optimum bound or a witness from that partial
table. Existing frontier, start, neighborhood and fault-publication assertions
remain intact. All 2,963 preserved original source/input hashes still match.

The final FAST gate passes **35/35** in **5.8439 seconds** external wall time.
The capture helper passes **13/13** short process fixtures, and its benchmark
validator passes **7/7** tests. An existing macOS process-group cleanup race was
exposed by these fixtures: the helper now reaps an exiting leader before one
bounded retry when group termination initially returns permission denied.
Persistent denial and reaping failures still propagate. Initial failed fixture
runs remain in the local record. This changes the helper hash between pilot
and accepted studies; both final cohorts use the same fixed helper. The driver,
runner, models, reference records and time limits are unchanged.

## Accepted measured results

Final measured source is `5d533bcd4f66e9f065e24bac5ed7a7c976d715db`; only the
capture harness changed after compiled solver commit `b57bf49ad`. All **60/60**
returned witnesses pass independent checks. Before completes **24/30** runs;
after completes **30/30**. There are six before-cohort solver time limits and
no hard timeouts, output failures or validation errors. Ordinary Native improves
from **7/8 to 8/8** completed problem units and DepthFirst from **1/2 to 2/2**;
a unit requires all three repetitions to prove the independently known optimum.
The fixed panel takes 18.8507 seconds including its two separate loader probes.

| Problem / route | Before completion | Now completion | Before median wall time | Now median wall time |
| --- | --- | --- | --- | --- |
| Knapsack / ordinary Native | 0/3 | 3/3 | Unfinished at 2 s solver limit | 12.55 ms |
| Knapsack / DepthFirst | 0/3 | 3/3 | Unfinished at 2 s solver limit | 10.46 ms |
| Facility location / Native | 3/3 | 3/3 | 453.43 ms | 453.99 ms |
| Assignment / Native | 3/3 | 3/3 | 105.34 ms | 106.50 ms |
| Binary TSP / Native | 3/3 | 3/3 | 34.85 ms | 34.39 ms |
| Production / Native | 3/3 | 3/3 | 19.91 ms | 20.60 ms |
| Bin packing / Native | 3/3 | 3/3 | 10.74 ms | 10.91 ms |
| Circuit TSP / Native | 3/3 | 3/3 | 20.06 ms | 21.93 ms |
| Weighted queens / Native | 3/3 | 3/3 | 19.40 ms | 21.02 ms |
| Bin packing / DepthFirst | 3/3 | 3/3 | 10.83 ms | 10.57 ms |

**Lower time is better; higher completion is better.** All these problem types
were supported before and remain supported. For knapsack the change makes a
previously unfinished solve complete within this limit; it adds no model class.
No speed ratio is assigned to an unfinished baseline. Current knapsack returns
and proves **−2464** in every run. Previously, ordinary Native returned −1947;
DepthFirst returned −1792, −1780 and −1792. These minimization objectives favor
lower values. Its 159 current DFS admissions replace roughly 1.87–1.88 million
admissions in the unfinished baseline; the bin-packing control stays at 57.

The eight completed control units have mixed wall-time changes: median changes
range from 2.4% less to 9.4% more. The largest absolute increase is circuit TSP,
about 1.88 ms; its internal solve median actually falls slightly. Weighted queens
rises about 1.62 ms externally and 0.17 ms internally. These small desktop timings
remain visible and do not establish a general speed improvement or absence of
overhead. The benchmark page plots the recorded medians and all repetition ranges.

## Rejected ordering pilot

An initial generic objective-endpoint/DFS-ordering experiment passed 70 Release
CTest entries and 35 FAST cases, but its 60-run timing panel did not justify
shipping it. Both versions completed 7/8 ordinary Native and 1/2 DFS units.
Ordinary knapsack's two-second incumbent worsened from **−1947 to −1831**;
the independently known optimum is −2464. DFS bin packing grew from 57 to 75
admitted nodes. A small DFS knapsack incumbent improvement did not offset that
regression. The generic defaults and their path-dependent fixture changes were
reverted. All pilot records and failures from initial test development remain
available, separately from the accepted comparison.

The same frozen problem panel is reused to assess the narrower algorithm.
Because the pilot informed development, this is an adaptive regression panel,
**not an untouched holdout**. No instance, reference, repetition or time limit
is removed to improve the result.

## Fixed comparison method

The immediate prior source is `530a3b7837205d8255c6640425018831d3f8ee0e`, whose
C++ solver binaries were compiled at `c2fabb78f1fc3bcfd7432eb71cfdb22656cd3f60`.
Before rebuilding, all required runtime libraries were copied and hashed.
The same benchmark executable loads each cohort through process-local library
paths; actual dynamic-loader traces and post-run hashes verify the cohorts.
The before/after build configuration is the same Release AppleClang/macOS
configuration. No original checkout file or saved benchmark input is modified.

Eight existing instances were selected before observing candidate performance:
six binary families (knapsack, facility location, assignment, TSP, production,
bin packing) plus native circuit TSP and weighted queens. Ordinary Native solves
all eight. Explicit DepthFirst separately solves knapsack and bin packing.
The ten problem/route units each receive three alternating before/after pairs:
**60 measured executions**, two-second solver limits, three-second child caps
and a 240-second outer allowance. Two additional loader probes establish
runtime provenance; they are retained separately from measurements.

All builds and agent solver work stop before timing. Ordinary desktop activity
can still affect short runs. The exact source, complete input/reference hashes,
all outcomes, internal solve time and external wall time are retained. No
solver start or known optimum is supplied. Independent original-problem
validators check each returned witness and objective. Saved optima come from
prior independent combinatorial oracles; their frozen records and witnesses
are rechecked without repeating expensive enumeration.

**Lower completion time is better; higher optimal completion is better.**
All three repetitions must finish with independently verified optima for a
completion-time bar or paired speed ratio. Time-limited runs remain unfinished,
including when their incumbent equals the known optimum. Every attempted run
stays in the denominator. Ordinary Native has no public node counter; missing
counts remain unavailable. DepthFirst reports actual frontier counters.

## Evidence and reproduction

The [complete public record](checkpoints/native-algorithms.json) includes
all repetitions and the audited summary. Private local artifacts remain in
`build/comparison-algorithms/`: `before/manifest.json`, build/test logs,
`fast-accepted.json`, `fast-accepted-wall.json`, and `final-results/` with loader traces,
raw solver output, `report.json`, `summary.json` and local resolved paths.
The rejected pilot remains in `results/`; the same measured executable is
preserved byte-for-byte in `fixed-driver/`.

```sh
cmake --build build/native-compat --target optimize-native-benchmark --parallel 2
python3 -B experiments/optimize/benchmark_native_algorithms.py \
  --before-libraries build/comparison-algorithms/before/lib \
  --after-libraries build/native-compat/gecode/optimize \
  --after-libraries build/native-compat \
  --binary build/comparison-algorithms/fixed-driver/optimize-native-benchmark \
  --output-dir build/comparison-algorithms/new-results
```

The preserved baseline is a prerequisite; never recreate it from candidate
libraries. Output directories must be new. This runner is currently for the
recorded macOS dynamic-library layout; it does not claim Windows/Linux runtime
validation. Build before measuring, then stop other project jobs. The benchmark
page imports frozen evidence without invoking any solver.

The earlier [before-project comparison](BENCHMARKS.md) and
[ninth checkpoint](NINTH-CHECKPOINT.md) retain their original cohorts and results.
They are not pooled with these measurements. Three repeated pairs form a small
diagnostic, not evidence of statistical significance or industrial-wide speed.

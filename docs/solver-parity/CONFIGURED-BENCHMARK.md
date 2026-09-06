# Family-specific native benchmark settings

This study compares ordinary Native/BAB with explicitly configured routes in
**the same accepted solver build**. It isolates settings from implementation
changes. Every solve has ten seconds, one thread, exact discrete guarantees,
zero gap tolerances, and no supplied starting solution or oracle objective.

## Why the earlier results differed

The previous seven-family boundary study invoked only `solve_native`. The
older 18-family experiment used a different native LP-informed policy, common
starting solutions, objective-aware AFC branching, and optional LP primal and
neighborhood heuristics. Its observations are not pooled into this study.
The separate historical MIPLIB numerical comparison used HiGHS; that is also a
different solver route and baseline.

## Selection and supported combinations

The driver exposes ordinary native search, root LP, root LP with checked covers,
LP after bound changes (interval four) with covers, DFS reliability branching,
and combinations with a bounded radius-four incumbent neighborhood. Every
configuration reports its exact settings and actual LP, cut, probe and
neighborhood counters. Requested features can be skipped when a model is
already solved; a true flag alone is not evidence of useful work.

Eligible pure binary knapsacks retain the exact capacity dynamic program.
Requesting checked LP disables that program. Above its one-million-cell cap,
a separate LP fallback is eligible. Binary reliability and Hamming neighborhoods
are unsuitable for routing and queens, which contain integer variables and
native globals. Their ordinary native global propagators remain active.

Integer presolve remains available as an explicit API. Its current postsolve
contract returns an original feasible witness with unknown optimization status
and no transferred global bound. This benchmark does not invent an optimal
status by composing that API with exact solving. A production proof-preserving
presolve composition is separate implementation work.

## Measurement method

An exploratory pilot compares every exposed route at the next previously
failing binary size. All candidate outcomes are retained. No neighborhood configuration beat the selected preset for its family; a few
paired times improved slightly, and one facility incumbent improved.
The family policy is then saved before the independent adaptive measurement begins; it never picks
the fastest route after seeing an individual result. Knapsack dispatch depends
only on the table admission rule. Selection and measurement reuse these seeded
families, so they are not an independent holdout.

Both versions use the same executable and libraries. Inputs are saved before
execution, checked against the deterministic generator, and hashed. The complete
solve call is timed with a steady clock, including optional work and cleanup.
Capture is bounded at eleven seconds. Loader traces, build/source identities,
configuration fields, counters, witnesses and final hashes are checked. Exact
optimality is backend-reported; original feasibility, objective and auxiliary
values are independently validated. Inconsistent exact optima or contradicted
bounds reject the study. No incomplete run becomes a completed timing.

Each cohort doubles to a failure or a fixed search ceiling, bisects independently,
and confirms the candidate and neighboring sizes twice. Both knapsack profit
variants must pass. These are sampled boundaries; difficulty is not monotonic
and larger untested sizes remain unknown. A reached search ceiling is a lower
bound on supported size, never a discovered solver limit.

## Recorded results

The separate pilot records **42 candidate measurements** in **181.33 seconds**. The adaptive comparison records **176 measurements** across **78 sampled inputs** in **794.28 seconds**. All source, driver, input and library integrity checks pass. Every returned solution passes original-model validation. There are no process errors, hard timeouts or memory stops.

| Category | Previous settings | Configured | Next failure / configured ceiling |
| --- | --- | --- | --- |
| Knapsack | 407 items | 512 items | Search ceiling reached; the upper limit is still unknown. |
| Assignment | 17 tasks | 31 tasks | Next tested failure: 32 tasks (0/2 completed). |
| Facility location | 8 sites | 16 sites | Search ceiling reached; the upper limit is still unknown. |
| Bin packing | 17 items | 30 items | Next tested failure: 31 items (0/2 completed). |
| Production planning | 11 periods | 28 periods | Next tested failure: 29 periods (0/2 completed). |
| Routing | 21 cities | 21 cities | Next tested failure: 22 cities (0/2 completed). |
| Weighted queens | 23 queens | 23 queens | Next tested failure: 24 queens (0/2 completed). |

Knapsack and facility location reach the fixed generator ceilings, so their configured results mean **at least 512 items** and **at least 16 sites**. No upper solver limit is established for either. Assignment, bin packing and production have adjacent observed failures. The unchanged native controls confirm 21 routing cities and 23 weighted queens.

Production at 28 periods finishes near 9.6 seconds; routing at 21 cities also has a narrow time margin. Exact sampled boundaries can move with host activity or another seed. Aggregate completion rates are not compared because each configuration samples different sizes.

## Selected settings and actual activity

| Category | Selected settings | LP calls | Covers | Probe calls |
| --- | --- | ---: | ---: | ---: |
| Knapsack | Exact capacity DP; LP + reliability above its cap | 127995 | 29 | 1280 |
| Assignment | Checked LP bounds at the root | 11 | 0 | 0 |
| Facility location | Checked LP bounds updated during search | 1824 | 0 | 0 |
| Bin packing | Checked LP bounds at the root | 12 | 0 | 0 |
| Production planning | Updated LP bounds, covers and reliability branching | 369563 | 45 | 1920 |
| Routing | Native circuit and table constraints | 0 | 0 | 0 |
| Weighted queens | Native distinct and table constraints | 0 | 0 | 0 |

Activity totals include discovery and confirmation solves for the configured cohort. Root-cover LP calls are already included in the LP total. Neighborhoods are disabled in the selected policy; all pilot neighborhood attempts and the one accepted facility incumbent improvement remain in the portable evidence.

**Validation:** seven focused runner tests and three driver test groups pass. The driver tests execute 28 tiny route/model combinations with independent exhaustive optimum checks, actual mechanism activity checks, malformed-input rejection and start isolation. The solver libraries are unchanged, so the prior 70-test Release and 35-case FAST solver gates are retained rather than presented as newly executed.

The [complete portable record](checkpoints/configured.json) includes the projection, every adaptive input/run/decision, and the entire exploratory pilot. The [saved policy](checkpoints/configured.json) specifies the active settings for reproduction. Ordinary public solve defaults are unchanged; these are explicit benchmark presets.

## Reproduction

Build the separate driver without rebuilding or modifying solver libraries:

```sh
python3 -B experiments/optimize/build_configured_benchmark.py
python3 -B experiments/optimize/benchmark_configured.py --pilot \
  --binary build/configured-bench/optimize-configured-benchmark \
  --output-dir build/configured-bench/NEW-PILOT
python3 -B experiments/optimize/benchmark_configured.py \
  --policy experiments/optimize/configured-policy.json \
  --binary build/configured-bench/optimize-configured-benchmark \
  --output-dir build/configured-bench/NEW-RESULTS
```

Choose new output directories; prior evidence is never overwritten. The driver
build manifest is required alongside the executable. The historical frozen
benchmarks and core solver runtime remain unchanged.

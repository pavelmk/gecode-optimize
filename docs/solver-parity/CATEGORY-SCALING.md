# Native scaling across seven benchmark categories

The expanded local study covers **33 fixed cases and 132 measured runs** across
knapsack, assignment, facility location, bin packing, production, circuit routing
and weighted queens. With ten-second solver limits, the largest tested knapsack
size proved in both repetitions and **both distributions** rises from **32 to
384 model variables**. The other six category maxima are unchanged.

This measures the existing [capacity algorithm](ALGORITHMIC-CHECKPOINT.md);
there is no solver algorithm, API or ABI change in this study. The earlier
[52-run capacity study](CAPACITY-SCALING.md) remains a separate record. Its
knapsack and assignment inputs are reused, so this is not a new independent
sample of those families. Neither study establishes general CPLEX/Gurobi parity
or a solver's maximum problem size.

## Largest tested groups proved within ten seconds

The main knapsack group at each size requires all four results per version:
two uncorrelated and two correlated runs. Every other category requires both
repetitions of its single variant. The 512-variable uncorrelated stress point
is retained separately with its variant count; it cannot stand in for a missing
correlated variant in the main category maximum.

| Category | Tested main model-variable counts | Before | Current |
| --- | --- | ---: | ---: |
| Knapsack, both distributions | 8, 32, 128, 384 | 32 | 384 |
| Assignment | 9, 25, 81, 256 | 256 | 256 |
| Facility location | 8, 28, 104, 300 | 104 | 104 |
| Bin packing | 15, 36, 65, 102 | 102 | 102 |
| Production | 24, 48, 96, 192 | 48 | 48 |
| Circuit routing | 8, 16, 24, 32 | 32 | 32 |
| Weighted queens | 16, 32, 40, 48 | 48 | 48 |

The knapsack ratio is **12 times the tested variable count**, not a speed ratio.
Untested intermediate or larger sizes could change each maximum. Variable
counts compare versions within a category; they do not rank difficulty across
these different formulations. Circuit routing uses `2*n` model variables for
`n` cities, including one cost variable per successor. Weighted queens uses
`4*n` for `n` queens, including diagonal and cost variables. Thus the largest
native routing case has **16 cities / 32 model variables**, and the largest
queen case has **12 queens / 48 model variables**. These variables are integer,
not Binary; the other five categories use Binary formulations.

## Complete case census

Before returns **50 Optimal and 16 TimeLimit** results; current returns
**58 Optimal and 8 TimeLimit**, out of 66 runs each. All **132 returned witnesses**
pass independent original-model validation. There are no missing observations
or discarded limits. The complete measured invocation takes **277.4355438
seconds**, including two loader probes and measurement preflight; model and
reference freezing occurs separately.

Each entry below shows proved optima out of two repetitions. `0/2, limit`
means both runs return feasible incumbents with `TimeLimit`. It is not an
infeasibility result. All objectives are minimization values, with negative
profit used for knapsack. Production reports the encoded linear objective;
its documented constant relates that value to physical production/holding cost.

| Case | Model variables | Reference objective | Before | Current |
| --- | ---: | ---: | --- | --- |
| Knapsack uncorrelated, sanity | 8 | -337 | 2/2 | 2/2 |
| Knapsack uncorrelated, small | 32 | -1,096 | 2/2 | 2/2 |
| Knapsack uncorrelated, medium | 128 | -4,318 | 0/2, limit | 2/2 |
| Knapsack uncorrelated, large | 384 | -13,832 | 0/2, limit | 2/2 |
| Knapsack correlated, sanity | 8 | -62 | 2/2 | 2/2 |
| Knapsack correlated, small | 32 | -312 | 2/2 | 2/2 |
| Knapsack correlated, medium | 128 | -1,211 | 0/2, limit | 2/2 |
| Knapsack correlated, large | 384 | -3,648 | 0/2, limit | 2/2 |
| Assignment, 3 tasks | 9 | 87 | 2/2 | 2/2 |
| Assignment, 5 tasks | 25 | 162 | 2/2 | 2/2 |
| Assignment, 9 tasks | 81 | 146 | 2/2 | 2/2 |
| Assignment, 16 tasks | 256 | 145 | 2/2 | 2/2 |
| Facility, 2 sites / 3 customers | 8 | 90 | 2/2 | 2/2 |
| Facility, 4 sites / 6 customers | 28 | 147 | 2/2 | 2/2 |
| Facility, 8 sites / 12 customers | 104 | 224 | 2/2 | 2/2 |
| Facility, 12 sites / 24 customers | 300 | 350 | 0/2, limit | 0/2, limit |
| Bin packing, 4 items / 3 available bins | 15 | 3 | 2/2 | 2/2 |
| Bin packing, 8 items / 4 available bins | 36 | 3 | 2/2 | 2/2 |
| Bin packing, 12 items / 5 available bins | 65 | 4 | 2/2 | 2/2 |
| Bin packing, 16 items / 6 available bins | 102 | 5 | 2/2 | 2/2 |
| Production, 3 periods / 8 options | 24 | 267 | 2/2 | 2/2 |
| Production, 6 periods / 8 options | 48 | 484 | 2/2 | 2/2 |
| Production, 12 periods / 8 options | 96 | 1,447 | 0/2, limit | 0/2, limit |
| Production, 24 periods / 8 options | 192 | 4,600 | 0/2, limit | 0/2, limit |
| Circuit routing, 4 cities | 8 | 320 | 2/2 | 2/2 |
| Circuit routing, 8 cities | 16 | 384 | 2/2 | 2/2 |
| Circuit routing, 12 cities | 24 | 408 | 2/2 | 2/2 |
| Circuit routing, 16 cities | 32 | 436 | 2/2 | 2/2 |
| Weighted queens, 4 queens | 16 | 105 | 2/2 | 2/2 |
| Weighted queens, 8 queens | 32 | 121 | 2/2 | 2/2 |
| Weighted queens, 10 queens | 40 | 86 | 2/2 | 2/2 |
| Weighted queens, 12 queens | 48 | 98 | 2/2 | 2/2 |
| Knapsack uncorrelated, stress | 512 | -18,731 | 0/2, limit | 0/2, limit |

The [complete public record](checkpoints/category-scaling.json) includes every
repetition's status, incumbent, bound and internal/external time, along with
all frozen models, references and provenance. Time ratios remain absent if
either version has an unfinished repetition. Tiny completed cases and two
repetitions do not support a general speed claim.

## Inputs and independent optima

All sizes, seeds and generation rules are frozen before measurement. There is
one nested seeded instance per tier and variant, repeated twice without model
replacement. No optimum is planted to favor a search order.

| Category | Generation and independent reference |
| --- | --- |
| Knapsack | Existing seeds 20260906/20260907; weights 1..31, capacity `6*n`, uncorrelated profits 1..100 or weight plus 0..10. Exact minimum-weight-by-profit DP, distinct from the product's weight-indexed objective DP. |
| Assignment | Existing seed 20260908; top-left squares of a 16-by-16 cost matrix, entries 1..100. Exact column-subset assignment DP. |
| Facility location | Seed 20260909; prefixes of 12 sites and 24 customer coordinates in 0..30, Manhattan service cost plus one, opening cost 15..60. Enumerate site subsets and independently choose each customer's cheapest open site; the tiny case also permits full binary enumeration. |
| Bin packing | Seed 20260910; item-weight prefixes in 2..10. Capacity follows the existing total-weight/available-bin rule and is increased only if deterministic first-fit needs too many bins. Exact item-subset DP over bin count and last-bin load, checked against small set-partition enumeration. |
| Production | Seed 20260911; nested demands in 1..7, eight quantity options, fixed/unit/overtime costs and bounded inventory. Exact inventory-state DP; small quantity schedules independently check physical and encoded objectives. |
| Circuit routing | Seed 20260912; prefixes of 16 points in 0..99, Manhattan arc costs plus one on nonself arcs. Exact Held-Karp subset DP, checked against tiny tour enumeration. |
| Weighted queens | Seed 20260913; top-left squares of a 12-by-12 cost matrix in 1..50. Independent queen-placement enumeration with original row, column and diagonal checks. |

References are computed before the manifest is frozen. Measurement checks
their hashes and original witnesses without recomputing optima. Binary TXT
contains `incumbent 0`. Native TXT contains a reference-free zero placeholder
vector required by the legacy format; the driver discards it. Neither format
feeds the oracle witness, its objective or a solution start into the solver.

The 384-item knapsacks use 887,425 DP cells. The 512-item point needs 1,576,449,
exceeding the one-million-cell admission cap, so ordinary search handles it.
It remains visible as a single-variant stress group. Capacity and coefficients
matter as well as item count; the observed gain does not extend automatically
to larger capacities, multiple rows, globals or other categories.

## Execution, validation and reproduction

Every call uses ordinary Native/BAB, `Exact`, one thread, seed zero, zero gap
tolerances and a ten-second internal limit. There are two paired repetitions:
before/current in the first, current/before in the second. Per-child capture
allows 11 seconds plus at most 0.5 seconds for cleanup; the complete invocation
has a cooperative 1,500-second allowance. The runner reaps each child before
launching the next and records monotonic start/end offsets. Solver and external
durations use monotonic clocks; UTC timestamps are annotations. External time
also includes process startup, parsing, model construction and output.

The preserved before cohort is source `530a3b783`, compiled product `c2fabb78f1`.
The current cohort is the unchanged accepted capacity-algorithm product.
Both use the same frozen ten-second-capable driver, SHA256
`fa2a8b1f7afcc93589d941dd9e92383bf79a9f11a3bdf73b8213cae11f3c49a4`.
The measured source/tooling head is `272d360d02b7c4ed1b511d82219bd11c3b0c7394`;
the model manifest SHA256 is
`855c2630073be58b62682532d53f9a58314e7638ca242fbc8b3004a902b10e11`.
Loader probes and final input/source/driver/library integrity checks pass.
Eight generator and nine runner tests pass (**17 new tooling tests**); prior
solver correctness results are retained without claiming a new solver build.

From the repository root, freeze into a new directory before measurement:

```sh
python3 -B experiments/optimize/benchmark_category_scaling.py \
  --freeze-only --freeze-dir build/category-scaling/frozen
```

Use the printed manifest hash and the existing frozen driver in a separate run:

```sh
python3 -B experiments/optimize/benchmark_category_scaling.py \
  --freeze-dir build/category-scaling/frozen \
  --manifest-sha256 PRINTED_SHA256 \
  --binary build/capacity-scaling/fixed-driver/optimize-native-benchmark \
  --before-libraries build/comparison-algorithms/before/lib \
  --after-libraries build/native-compat/gecode/optimize \
  --after-libraries build/native-compat \
  --output-dir build/category-scaling/results
```

These example directories already contain this study's evidence; choose new
freeze/output directories for another invocation. The runner performs no build
or download. Local raw logs and path details remain under
`build/category-scaling/`; the public JSON above is portable. The seven selected
families do not time scheduling, graph coloring, continuous/nonlinear models,
every native global or every API capability. Those remain separate capability
and correctness questions in the broader roadmap.

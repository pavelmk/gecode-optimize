# Native capacity scaling

With a ten-second solver allowance, the largest tested knapsack size proved
optimal in both repetitions rises from **32 to 384 binary variables** in each
of two fixed distributions. That is a **12-fold increase in tested size**,
not a speed ratio or an estimate of the solver's maximum size. The assignment
control remains at **256 variables**. Both versions reach their time limit at
the 512-variable knapsack stress point.

This study measures the existing bounded exact capacity optimization from the
[algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md). No solver algorithm, option
or ABI changed for this measurement. The broader commercial-parity roadmap
remains incomplete.

## Largest tested size

A size counts only if both repetitions return independently verified `Optimal`
results within the internal ten-second allowance. Every tested point, including
the 512-variable stress case, participates in this calculation.

| Family | Tested binary variables | Before | Current | Ratio of tested sizes |
| --- | --- | ---: | ---: | ---: |
| Uncorrelated capacity | 8, 32, 128, 384, 512 | 32 | 384 | 12 |
| Correlated capacity | 8, 32, 128, 384 | 32 | 384 | 12 |
| Assignment | 9, 25, 81, 256 | 256 | 256 | 1 |

There is one seeded instance at each size. The two repetitions measure the same
instance, not two independent samples. Sizes between the listed points were not
tested. In particular, the before result does not establish that 32 is its
largest solvable size, and the current correlated result gives no upper limit.

## Complete outcome census

All **52 required observations** completed and returned an independently valid
original-model witness. Before proves **16/26** optima and reaches its time
limit in **10/26** runs; current proves **24/26** and reaches its time limit in
**2/26**. No failed or capped result is removed. The whole invocation takes
**150.1307507 seconds**, including two separate loader probes and preparation.

Each table cell reports the number of proved optima out of two repetitions.
`0/2, limit` means both runs return `TimeLimit` with feasible incumbents, not
that the model is infeasible. Objectives minimize negative profit for capacity
models and positive cost for assignment.

| Family | Variables | Reference objective | Before | Current |
| --- | ---: | ---: | --- | --- |
| Uncorrelated capacity | 8 | -337 | 2/2 | 2/2 |
| Uncorrelated capacity | 32 | -1,096 | 2/2 | 2/2 |
| Uncorrelated capacity | 128 | -4,318 | 0/2, limit | 2/2 |
| Uncorrelated capacity | 384 | -13,832 | 0/2, limit | 2/2 |
| Uncorrelated capacity, stress | 512 | -18,731 | 0/2, limit | 0/2, limit |
| Correlated capacity | 8 | -62 | 2/2 | 2/2 |
| Correlated capacity | 32 | -312 | 2/2 | 2/2 |
| Correlated capacity | 128 | -1,211 | 0/2, limit | 2/2 |
| Correlated capacity | 384 | -3,648 | 0/2, limit | 2/2 |
| Assignment | 9 | 87 | 2/2 | 2/2 |
| Assignment | 25 | 162 | 2/2 | 2/2 |
| Assignment | 81 | 146 | 2/2 | 2/2 |
| Assignment | 256 | 145 | 2/2 | 2/2 |

The [complete public record](checkpoints/capacity-scaling.json) retains all
individual statuses, incumbent objectives, bounds and internal/external times,
plus the frozen models and reference witnesses. A speed ratio is left absent
whenever either version has an unfinished repetition. Sub-millisecond solves
and two repetitions do not support a general timing claim; the primary result
here is the difference in proved sizes.

## Frozen inputs and independent references

The 13 cases, sizes, distributions, seeds and order were fixed and hashed before
measurement. There are no planted optima or selected replacement instances.

- Capacity tiers contain 8, 32, 128 and 384 Binary variables with weights drawn
  uniformly from 1 through 31. Capacity is `6*n`. Uncorrelated profits are
  uniform from 1 through 100 with seed `20260906`; correlated profits are
  `weight + uniform(0,10)` with seed `20260907`. Each family uses nested item
  prefixes. The 512-item uncorrelated stress case continues the same prefix.
- Assignment uses 3, 5, 9 and 16 tasks, encoded as 9, 25, 81 and 256 Binary
  variables. Costs are uniform from 1 through 100, using the top-left square
  of one 16-by-16 master matrix with seed `20260908`. Row and column equalities
  are represented by pairs of lower-bounded sparse rows: `4*q` rows and
  `4*q*q` nonzeros for `q` tasks. This control is outside the single-row DP.
- Capacity reference optima use exact minimum-weight-by-profit dynamic
  programming, independently of the product's weight-indexed objective DP.
  Assignment references use exact column-subset dynamic programming. Small
  subset/permutation enumeration tests cross-check both oracles. The measured
  phase verifies frozen identities and original witnesses without recomputing
  the references. Solver TXT files contain `incumbent 0`; no reference objective
  or reference assignment enters solve options.

The product's work depends on capacity as well as variable count. Its complete
table has `(n+1)*(capacity+1)` cells and is capped at one million cells, with a
separate capacity limit of 65,536. The 384-item cases use **887,425 cells**;
the 512-item case would need **1,576,449**, so it deliberately exercises the
unchanged ordinary-search fallback. Both cohorts return incumbent -11,574 in
both stress repetitions without proving the reference optimum -18,731. This
visible limit prevents extrapolating the 12-fold size result to arbitrary
capacities, larger models or additional constraints.

## Execution and provenance

The runner makes two alternating paired repetitions: before/current for every
case in the first repetition and current/before in the second. Each call uses
ordinary Native/BAB, `Exact`, one thread, seed zero, zero gap tolerances and a
**10-second internal limit**. Capture allows **11 seconds per child**, plus at
most 0.5 seconds for cleanup; the invocation has a **cooperative 600-second
allowance**. Internal limits include native compilation/search/checking but
not the driver's sparse model construction. External times additionally include
startup, parsing, construction and output. Cooperative cleanup can make a
time-limited result's reported duration slightly exceed ten seconds.

One adjacent pair of recorded UTC start times implies an apparent 51.3 ms
overlap. The runner executes sequentially and reaps each child before launching
the next; elapsed durations use monotonic clocks. UTC timestamps therefore do
not independently establish nonoverlap or machine quietness.

Before libraries are the preserved source `530a3b783` / compiled product
`c2fabb78f1`. Current libraries contain the accepted capacity algorithm and all
five runtime library hashes match the prior algorithm-checkpoint candidate.
Two loader probes verify the actual cohorts. The same freshly frozen executable
serves both versions; its sole driver change raises the accepted time-limit
argument ceiling from five to ten seconds. The earlier study's frozen driver
remains unchanged.

The measured source/tooling head is `f76dd776af77d2b416d58ea164099b8fdca22dc5`.
The frozen model manifest SHA256 is
`ce41bc1e75e35c6dbe708b65ff3f97904533aa66c9f57b1e10d9534b55ff13d3`.
Model, source, executable, baseline-manifest and loaded-library integrity checks
all pass. Eighteen new generator/runner tests pass in **1.430 seconds**, including
reference isolation, hash rejection, ten-second classification, stress-point
inclusion and structured failed-probe preservation. These are tooling checks;
the existing solver product and its prior correctness gates are unchanged.

Reproduction uses `experiments/optimize/benchmark_capacity_scaling.py`: first
`--freeze-only --freeze-dir NEW_DIRECTORY`, then a separate measurement with
the printed `--manifest-sha256`, a ten-second-capable frozen driver, the preserved
and current library directories, and a new output directory. Local evidence is
under `build/capacity-scaling/`; the public JSON above includes the report,
summary, models and validation record without workstation paths.

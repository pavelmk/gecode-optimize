# Before and after: supported problems and measured time

The [adaptive boundary study](ADAPTIVE-BOUNDARIES.md) searches the two native
versions separately under ten-second limits. Expansion stops after a failed
size, followed by bounded search and confirmation; the result is a sampled
boundary, not an absolute solver limit. Original witnesses are independently
validated, while optimality is reported by the backend without a separate
reference oracle. Its observations remain separate from the fixed panels.

For the fixed local native size panel, see the
[seven-category scaling study](CATEGORY-SCALING.md): 33 fixed cases, 132 runs,
ten-second limits, grouped knapsack variants and explicit integer-model
dimensions. Its observations remain separate from the earlier studies below.

This is the preserved before-project to ninth-checkpoint study. The later
[native algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md) has its own fixed
comparison panel and separately retained observations.
The subsequent [capacity scaling study](CAPACITY-SCALING.md) holds that solver
product fixed and measures the largest tested sizes proved within ten seconds:
32 to 384 variables for each of two knapsack distributions, unchanged assignment
capacity, and an explicitly retained 512-variable fallback limit. Its 52 runs
remain separate from the historical timing panels below.

These results compare preserved pre-project Gecode binaries with the ninth
integrated implementation on 5 September 2026. **Less elapsed time is better;
more completed, checked solves is better.** An unsupported API has no timing.
A time-limited solve is unfinished and must not be scored as a fast completion.

The visual benchmark page is the `/progress` route in the sibling
`benchmark-site` project. Its downloadable JSON contains every repetition and
support notes. This document also enters Gecode's native Doxygen documentation
through the Optimize task pages. The source checkout and old benchmark artifacts
remain unchanged.

## What was compared

- **Before:** preserved `enhanced-binary` and `enhanced-fzn` binaries from the
  pre-project experimental Gecode 6.4 checkout. This baseline already had native
  integer CP, global constraints, FlatZinc, parallel CP and an experimental
  binary linear adapter. It is not untouched upstream Gecode.
- **Now:** compiled product `c2fabb78f1fc3bcfd7432eb71cfdb22656cd3f60`, measured
  from documentation/report head `2da8c21a64dddcce6aed58232238a0a138675509`.
  Later documentation changes do not change the measured solver binaries.
- **Machine and limits:** Apple M1 Pro, macOS 15.7.4, one solver process at a time,
  three paired repetitions in alternating version order, a two-second solver
  limit, no supplied solution starts. Startup, input reading, search and output
  are included in external wall time. A separate process deadline contains
  overruns; time limits are cooperative, not exact wall-time completion promises.
- **Scope:** five existing pure-binary MIPLIB models and four unchanged native
  FlatZinc regression fixtures. These are two distinct panels, not a pooled
  performance score or a representative industrial benchmark.

The preserved before binaries are self-contained; the current executables load
shared Gecode libraries. Actual loader paths and library hashes are retained.
This is an end-to-end comparison of usable builds and routes. It does not isolate
algorithm changes from process startup, loading or file-format costs.

## Binary optimization: completion improved, not every runtime

The old route is the experimental binary `auto` adapter. The new route is
`optimize-file` using HiGHS 1.15.1. Original TXT and MPS inputs are independently
checked for exact mathematical equivalence. Each returned witness is checked
against the original integer rows/domains, and completed answers must match the
known optimum. Numerical HiGHS termination is not an exported exact proof.

| Model | Before: completed runs | Now: completed runs | Before: median completion wall | Now: median completion wall |
| --- | ---: | ---: | ---: | ---: |
| p0033 | 3/3 | 3/3 | 16.43 ms | 30.77 ms |
| p0201 | 0/3 | 3/3 | No completion within limit | 640.65 ms |
| p0282 | 0/3 | 3/3 | No completion within limit | 159.08 ms |
| p0548 | 0/3 | 3/3 | No completion within limit | 70.55 ms |
| lseu | 0/3 | 3/3 | No completion within limit | 190.52 ms |

The current route completed all five models in every repetition, versus one
model before: **15/15 versus 3/15 completed runs**. All returned witnesses were
feasible under independent exact checking, including the twelve old runs that
stopped without proof. The old p0201 witness equals the known optimum, but the
solver had not established completion; it is counted as unfinished. This panel
measures optimal completion, not merely time to any feasible solution.

p0033 takes more wall time now. The four censored models have no old completion
time, so no finite speedup ratio is claimed for them. A two-second cap is not a
measured time to optimum. Binary models were supported before and now; the
improved result is practical completion on these inputs, not newly added binary
problem-class support.

## Native CP: retained correctness, more startup-scale wall time

Both versions use the original native FlatZinc path, matching the existing exact
expected-output fixtures. This oracle is not an independent mathematical proof.
All **12/12 runs per version** matched, including termination output.

| Original fixture | Before median external wall | Now median external wall |
| --- | ---: | ---: |
| Job-shop scheduling | 5.04 ms | 10.60 ms |
| Cumulative scheduling | 4.21 ms | 9.19 ms |
| Sudoku | 4.56 ms | 9.88 ms |
| Multidimensional knapsack | 4.44 ms | 9.37 ms |

These tiny cases take longer end to end in the current shared-library build.
Median reported internal search is approximately 0.02–0.18 ms, much smaller
than process wall time. Startup, loading, parsing and output therefore dominate;
these results do not establish a twofold slowdown in the underlying propagation
or search algorithms. The public page shows the longer bars and the build-layout
difference explicitly. No regression result is hidden because it is unfavorable.

## Capability changes are distinct from timing changes

The initial source snapshot is `e10562fd9`. The implemented API scope is described
in the [current guide](README.md) and native Optimize Doxygen task pages.

| Problem or workflow | Before project | Ninth checkpoint |
| --- | --- | --- |
| Binary/bounded integer CP, globals and native FlatZinc | Already supported | Retained; explicit owning model/compiler routes added |
| General continuous LP and mixed continuous/integer linear models | No general numerical MP route | Numerical HiGHS LP/MILP with explicit scale and guarantee limits |
| Continuous convex quadratic objective | No dedicated numerical QP API | Bounded continuous weighted-affine-square subset through HiGHS; no arbitrary Hessian/QCP/MIQP |
| LP observations, basis starts, rays and sensitivity | No unified owning original-model API | Numerical data and evidence; selected-basis coefficient/equality-RHS sensitivity |
| Repeated solves and application workflows | Application-managed | Sessions, serial scenarios, ordered objectives, grouped conflicts, weighted L1 repair and ranked pools, each with documented limits |
| Native incumbent neighborhoods | Application-defined heuristics possible | One explicit bounded BinaryHamming improvement attempt; C++ only |
| Owning optimization C/Python package | No corresponding Optimize facade | Versioned handles and Python ctypes; installed ninth libraries tested; older wheel unchanged |
| General MIQP/QCP/global nonlinear MP | No equivalent dedicated engine | Still outside Optimize scope; original finite-domain/FloatVar facilities remain distinct |
| Parallel native CP | Already supported | Retained; added Optimize routes currently use one worker |
| Production learning/parallel hybrid/action callbacks | No matching integrated hybrid facility | Remains unfinished |

Missing support does not mean Gecode could never express a related model using
custom CP code. Conversely, a new wrapper does not make a complete problem class
or all combinations of workflows supported. HiGHS-delivered capability is
labeled numerical and delegated. No CPLEX/Gurobi execution or parity is claimed.

## Fresh regression and evidence

The fresh **35/35 FAST gate passed in 5.8003 seconds external wall time**
(5.7168 seconds reported inside its runner). Its unchanged outer budget is
28 seconds; compilation is excluded. The new sensitivity fixture checks 63
conditions; the native neighborhood fixture checks 14, including a real local
improvement and the independently enumerated global optimum of −29. These are
correctness-fixture times, not large-model new-feature benchmarks.

The previous eighth-to-ninth comparison is a separate historical result in
[NINTH-CHECKPOINT.md](NINTH-CHECKPOINT.md). Five complete paired 33-case runs
passed; an additional current panel hit the four-second `cp_distinct` deadline.
That failed repeat remains disclosed. It is not part of this pre-project panel
and is not replaced by the fresh FAST pass.

Raw evidence is in `build/before-project-comparison/results/`: `report.json`
retains commands, all 54 run records and original/model/binary/runtime hashes;
`summary.json` contains the graph-ready repeated measurements;
`provenance.public.json` contains path-free provenance; and `current-fast.json`
plus `current-fast-wall.json` record the fresh gate. The committed page snapshot
is [checkpoints/benchmark-page.json](checkpoints/benchmark-page.json).

Reproduce from the implementation repository with preserved original artifacts:

```sh
python3 -B experiments/optimize/benchmark_progress.py \
  --before-source /path/to/original/gecode \
  --current-build build/native-compat \
  --output-dir build/progress-repeat \
  --seconds 2 --repetitions 3 --budget-seconds 180
```

The output directory must be new. Do not compile, generate documentation or run
other test jobs during timing. Reproduction requires the preserved original
experimental binaries and their metadata, current compiled libraries and cached
inputs; it does not download or rebuild solvers. The runner exposes the exact
path options through `--help`. It retains failed/censored outcomes and refuses
to silently compare mismatched input mathematics.

The page's `scripts/import-progress.py` imports records without running solvers.
Short-run medians have no statistical confidence intervals; there is no broad
holdout, memory comparison or overall solver score. Actual Windows/Linux
execution and a ninth-checkpoint wheel rebuild remain outside this batch.

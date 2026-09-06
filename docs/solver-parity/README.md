# Additive optimization API

This branch adds `Gecode::Optimize`, an owning sparse numerical model API with a
HiGHS LP/MILP backend, persistent sessions, native global constraints,
numerical conflict diagnostics, weighted feasibility repair, ranked solution pools
and exact integer presolve with owning reconstruction.
An explicit bounded integer bridge also compiles this model to native Gecode
search. An explicit [checked LP hybrid](NATIVE-LP.md) adds safe integer relaxation
deductions, with separate LP statistics and unchanged default routing. Existing
`Space`, propagator and search interfaces remain available.
The [algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md) adds bounded exact binary capacity
optimization to the
[ninth integrated checkpoint](NINTH-CHECKPOINT.md), which includes selected-basis
LP sensitivity and a bounded native incumbent neighborhood. Regression and
immediate prior-version timings are recorded separately from historical results.
Further roadmap implementation is on hold; commercial parity remains incomplete.

The common Native solve now uses a [structural automatic policy](NATIVE.md):
it preserves eligible DP and selects compatible checked LP, covers and bounded
branching without problem-family labels. Direct `solve_native` remains the
ordinary route. Bounded exact presolve, independent components, duplicate-column
symmetry and compact knapsack DP now extend this policy. The separate C++
`solve_native_race` option tries this policy and ordinary BAB under one shared
budget, then selects a route. Exploration/restarting may increase CPU work or
solve time; longer trials can pay off if they discover a better search strategy.
MiniZinc exposure and parallel racing remain future work. The final three-cohort
benchmark compares the original pre-algorithm runtime, automatic racing and
frozen family presets; the earlier studies below keep their own observations.

The [configured benchmark](CONFIGURED-BENCHMARK.md) compares ordinary settings
with explicitly selected algorithm settings in the same current solver build.
It preserves admitted knapsack DP, enables checked LP where effective, and uses
bounded reliability branching for production and oversized knapsacks. The
runner's [saved family policy](checkpoints/configured.json)
is explicit; public API defaults were unchanged during that study. All candidate pilot
results, activity counters and adaptive measurements are retained separately.

The [adaptive boundary study](ADAPTIVE-BOUNDARIES.md) searches each native version
independently, stops expansion after a failed size, and confirms sampled
ten-second boundaries. Original witnesses are checked independently; optimality
remains the exact backend's claim without a separate reference oracle. This
study and the fixed panels below retain their own observations and methods.

The [seven-category scaling study](CATEGORY-SCALING.md) records 132 runs of the
unchanged native product. Knapsack is one category requiring both distributions
to pass at each size; its tested maximum rises from 32 to 384 variables. The
other six category maxima are unchanged, and native routing/queen dimensions
distinguish input entities from actual model variables.

The earlier [capacity scaling study](CAPACITY-SCALING.md) measures the unchanged native
product with ten-second limits. Across two fixed knapsack distributions, the
largest tested size proved in both repetitions rises from 32 to 384 variables;
the 512-variable fallback remains unfinished. Assignment stays at 256 variables.
These are sampled size results, not general solver limits or speed ratios.

The [before/after benchmark report](BENCHMARKS.md) separates existing native
capabilities, added numerical routes, completion rates and measured runtimes.
Gecode's native Doxygen documentation now includes an Optimize task guide from
[`doxygen/optimize.hh`](../../doxygen/optimize.hh), covering the current API and
these backend boundaries.

## Build and run

The standalone component needs C++17 and CMake 3.21+. It does not build native
Gecode. With an installed HiGHS 1.15 package on `CMAKE_PREFIX_PATH`:

```sh
cmake -S gecode/optimize -B build/optimize -DCMAKE_BUILD_TYPE=Release
cmake --build build/optimize -j 4
ctest --test-dir build/optimize --output-on-failure
build/optimize/optimize-example
```

For this isolated workspace, the separately copied and pinned HiGHS source is
`../deps/HiGHS` relative to the implementation checkout. The tested configure
command is:

```sh
cmake -S gecode/optimize -B build/optimize \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
  -DGECODE_OPTIMIZE_HIGHS_SOURCE="$PWD/../deps/HiGHS"
```

The dependency is HiGHS 1.15.1, commit
`04024d701f79feb8e2f18bc3df0dffc04ef05088`, from
[ERGO-Code/HiGHS](https://github.com/ERGO-Code/HiGHS).
Configuration never downloads dependencies. An unavailable installed package
produces a configure error; it does not silently select another solver.
`-DGECODE_OPTIMIZE_WITH_HIGHS=OFF` builds the model, checker, I/O and workflow
coordination without a numerical backend; solving reports `Unsupported`.

For a combined native Gecode build, use `-DGECODE_ENABLE_OPTIMIZE=ON` at the
repository root. This option defaults to OFF, preserving the existing build.
When integer and search components are enabled, the combined build also enables
`GECODE_OPTIMIZE_WITH_NATIVE` by default. A standalone optimization build cannot
enable that bridge; use the combined build described in [NATIVE.md](NATIVE.md).
After installation, use either `find_package(GecodeOptimize CONFIG REQUIRED)`
for the standalone package or `find_package(Gecode CONFIG REQUIRED COMPONENTS
optimize)` for the combined package. Both expose `Gecode::optimize` and
`Gecode::gecodeoptimize`. A native-only component request does not require HiGHS.

## Model and solve

```cpp
#include <gecode/optimize/solve.hpp>
#include <limits>
namespace O = Gecode::Optimize;

O::Model model;
auto open = model.add_binary("open");
auto quantity = model.add_continuous(0, 100, "quantity");
const double inf = std::numeric_limits<double>::infinity();
model.add_row({{quantity, 1}, {open, -100}}, -inf, 0, "capacity");
model.add_row({{quantity, 1}}, 40, inf, "demand");
model.minimize({{open, 12}, {quantity, 0.5}});

O::SolveOptions options;
options.time_limit_seconds = 10;
options.primal_start = {{open, 1}}; // Partial hint, not a fixed assignment.
auto result = O::solve(model, options);
if (result.has_solution()) {
  double produced = result.value(quantity);
  // Check result.termination separately before claiming completion.
}
```

The example's optimum is 32. Continuous, integer, binary, semicontinuous and
semiinteger domains are represented explicitly. Rows have lower and upper
bounds; objectives support minimization, maximization and offsets. Duplicate
terms are normalized deterministically. Successful edits advance the model
revision. Handles carry a model identity and never-reused slot; removed slots
remain tombstones. Results and model snapshots own their data and survive edits.

`SolveResult` separates termination from incumbent availability. It records the
backend/version, validated original-variable values, objective, best bound,
gaps and elapsed time. Missing bounds/gaps remain missing. `has_solution()` does
not imply optimality, and `Optimal` is explicitly **numerical** for this backend.
Original rows, variable domains, integrality and objective are independently
recomputed before a candidate is accepted. This checker is not a proof verifier
or an exact certificate for general real arithmetic.

`SolveOptions::primal_start` accepts unique, finite, original-variable entries.
Individual domains are checked; complete starts must also satisfy all original
constraints. Invalid starts return `InvalidModel` with an explanation. Partial
starts may be completed or repaired by HiGHS; `start_submitted` only says the
backend accepted the hint, not that the hint became an incumbent. Starts use
handles rather than a solver's compacted column numbering.

For repeated edits, [SolveSession](SESSIONS.md) retains compatible LP basis
state and revalidates old MIP witnesses before submitting them as hints. For
infeasible models, [analyze_conflict](DIAGNOSTICS.md) reports original rows,
bounds and domain groups with explicit numerical irreducibility semantics.
Set `SolveOptions::backend = Backend::Native` for the bounded exact-integer
route. The [typed global helpers](GLOBALS.md) retain all-different, element,
table, cumulative, circuit and Regular constraints; `Auto` selects native Gecode for
active globals and HiGHS for other models. The [fast regression command](FAST-REGRESSION.md)
covers both routes and these workflows within one 28-second budget.

[LP observations](LP-OBSERVATIONS.md), [explicit basis starts](LP-BASIS.md) and
[numerical rays/Farkas evidence](LP-EVIDENCE.md), together with
[selected-basis LP sensitivity](LP-SENSITIVITY.md), retain original-model identity
and distinguish accepted data from diagnostics. [Scenario batches](SCENARIOS.md)
apply sparse overrides under one budget. These workflows have C and Python
bindings. The separate [MiniZinc registration](MINIZINC.md) is opt-in and includes
build/install compiler checks.

The C++ [native neighborhood API](NATIVE-NEIGHBORHOODS.md) optionally attempts
one checked binary incumbent improvement within the shared search budget.

## Limits and numerical contracts

- `capabilities()` identifies the numerical backend and current limitations.
  HiGHS rejects `Exact` and `Certified`; numerical solving is never substituted for
  them. The existing certified binary LP module is unchanged.
- Time limits cover snapshot copying, structural validation, conversion, solving
  and candidate checking. Cancellation uses a shared monotonic token. Backend
  calls are cooperative and may overrun; actual elapsed time is reported. A
  candidate first observed after the deadline is not accepted. A candidate
  observed in time can be checked after the cutoff and retained with a limit
  termination status.
- The first HiGHS adapter supports one worker per solve. Other thread counts
  return `Unsupported`, avoiding unreliable changes to HiGHS's global scheduler.
  Concurrent heterogeneous HiGHS sessions are not an advertised capability.
- Default native relative/absolute MIP gap tolerances are `1e-4`/`1e-6`.
  Feasibility/integrality tolerances are `1e-7`/`1e-6`. The backend receives the
  stricter feasibility/integrality tolerance for MIP feasibility checks.
- Reported relative gap is `abs(primal-dual)/max(1,abs(primal),abs(dual))`.
  `native_backend_gap` preserves HiGHS's convention separately. Native relative
  stopping criteria use HiGHS's convention, not the normalized reported gap.
- Finite bounds, objective costs and offsets must have magnitude below `1e20`;
  nonzero matrix coefficients must have magnitude strictly between `1e-12` and
  `1e15`. Unsupported scaling is rejected before HiGHS can discard coefficients.
  Semi variables currently require a finite positive nonzero-domain lower bound
  and finite upper bound at most 100000. These are adapter limits, not claims
  about all possible HiGHS formulations or native Gecode domains.

## Additional workflows and model exchange

[Ordered objectives](WORKFLOWS.md) use an explicit highest-priority-first vector,
one outer deadline/cancellation token and independently checked retention rows.
Stage completion requires an agreeing numerical bound. Both native MIP gap
targets are zero for this workflow. Degradation is explicit, and an unfinished
stage never becomes a claimed lexicographic optimum. Multi-stage node budgets
remain unsupported until cumulative consumed-node reporting is available.

[Constraint helpers](CONSTRAINTS.md) describe bounded indicators and Boolean
AND/OR formulations, including generated rows, original logical validation and
the restrictions needed to keep bound-derived formulations valid after edits.

[Model I/O](IO.md) documents the deliberately supported LP and free-MPS syntax.
The readers reject unsupported semantics. Writers retain double precision,
verify reimported model equivalence, then replace the destination atomically.
This does not imply support for every vendor-specific LP/MPS extension.

The JSON command-line runner supports cold-start correctness checks:

```sh
build/optimize/optimize-file experiments/solver-bench/miplib-cache/p0033.mps \
  --time-limit 30 --relative-gap 0 --absolute-gap 0 --seed 0
python3 experiments/optimize/verify_miplib.py \
  --binary build/optimize/optimize-file \
  --output build/optimize/miplib-correctness.json
```

The runner's budget includes file import, and its JSON distinguishes import,
solve and total wall time. The five-model harness uses the existing suite's
separate exact parser and assignment checker, matches the original input
hashes, and compares rounded feasible binary witnesses against the published
optima. It never passes reference solutions to the solver. These runs establish
correctness on those instances; they are not a MIPLIB2017 performance comparison
or evidence of commercial-solver speed parity.

## Repair, C and Python

`relax_feasibility` accepts selected row/bound sides and positive L1 penalties.
It builds a distinct private model, minimizes weighted violations and optionally
refines the original objective at minimum violation. The returned original
residuals distinguish a repaired point from a feasible solution of the unchanged
model. See [repair semantics and supported domains](RELAXATION.md).

The build also produces the versioned shared C library `gecodeoptimize_c`.
Installed CMake consumers link `Gecode::optimize_c` and include
`gecode/optimize/c_api.h`. The Python 3.9+ ctypes package lives in `python/`:
set `PYTHONPATH` to that directory and `GECODE_OPTIMIZE_LIBRARY` to the absolute
shared-library path. There is no runtime download or solver implementation in
Python. [Bindings](BINDINGS.md) describes ownership, typed globals/logic,
sessions, errors and the remaining workflow/binary-distribution work.

See [implementation status](IMPLEMENTATION.md) for remaining roadmap work and
[validation evidence](VALIDATION.md) for completed checks and their limits.

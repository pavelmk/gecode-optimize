# Native finite integer bridge

`gecode/optimize/native.hpp` provides an optional compiler from the sparse
optimization model to actual native Gecode `Space`, `IntVarArray`, integer
propagators and branch-and-bound search. It is an additive route: existing
native Gecode modeling, globals, search classes and FlatZinc behavior are not
changed. The typed [global registry](GLOBALS.md) retains six native constraint
families. The [owning FlatZinc capture/compiler](FLATZINC-COMPILER.md) and
separate [command-line route](FLATZINC-DRIVER.md) support a documented subset;
broader global and FlatZinc predicate coverage remain future work.

```cpp
#include <gecode/optimize/native.hpp>

using namespace Gecode::Optimize;
Model model;
auto x = model.add_integer(-3, 5, "x");
auto enabled = model.add_binary("enabled");
model.add_row({{x, 2}, {enabled, 1}}, 1, 7);
model.minimize({{x, -3}, {enabled, 2}}, 4);

SolveOptions options;
options.backend = Backend::Native;
options.guarantee = Guarantee::Exact;
auto result = solve(model, options); // automatic native algorithm selection
```

`solve_native(ModelSnapshot, options)` and `solve_native(Model, options)` accept
backend `Auto` or `Native`; explicitly requesting `Highs` is a mismatch and
returns `Unsupported`. The entry point itself always selects native search.
`native_capabilities()` reports whether this bridge was compiled in and its
supported subset. The common dispatcher controls its own `Auto` policy.

The common `solve(model, options)` routes `Backend::Native` here, and
`capabilities(Backend::Native)` exposes the same capability report. Common
`Auto` selects native Gecode for active native globals and HiGHS for other
models. The result always identifies the actual backend; explicit selections
are never substituted.

## Automatic native algorithm policy

The common `solve(model, options)` now uses `solve_native_auto` when it selects
Native. Applications select the native backend once; they do not need to label
problem families or set individual algorithm flags. `Backend::Auto` continues
to choose Native for active globals and HiGHS otherwise. Direct `solve_native`
retains ordinary BAB for callers requiring the preceding behavior.

The initial policy inspects model structure under the existing solve budget:

- Preserve eligible exact knapsack DP using the same admission routine as DP.
- Keep ordinary propagation for globals, indicators, nonbinary variables,
  tiny models (at most four active variables), unavailable checked LP, or
  optional-route option/numeric incompatibilities.
- Use root checked LP for nonnegative unit-coefficient rows, updated checked LP
  every four observed bound changes for signed unit rows, and updated LP with
  verified covers and bounded reliability for general binary rows.
- Reliability uses at most 128 probe status calls and DFS with the existing
  frontier storage cap. Nonzero gap options use the compatible LP/BAB route.
- Limit extra inspection to 4096 variable/row slots and 65536 row/objective
  nonzeros; larger inputs retain ordinary native solving.

The actual backend and an `Automatic native policy:` explanation appear in each
result. Snapshotting, selection, compilation and solving share time/cancellation
and node accounting. No oracle, inferred starting solution, benchmark family
label or neighborhood is used. Eligible ordinary integer models additionally
use the exact preprocessing pipeline described below.

The default remains a conservative structural heuristic. The thresholds are
provisional resource limits, not predictions of a speedup. Opt-in online strategy
selection is available separately through the native racing API below; neither
policy implies broad gains on unseen models.

## Optional automatic strategy racing

`solve_native_race` is an opt-in C++ entry point for native Gecode, accepting a
`Model` or `ModelSnapshot`. It is not yet surfaced as a MiniZinc/FlatZinc option.
It integrates the automatic presolve, independent components, identical-column
symmetry, compact knapsack DP and suitable checked-LP/branching choices above.
It compares that automatic route against ordinary native BAB (which also keeps
eligible exact knapsack DP), without problem-family labels or known objectives.

```cpp
NativeRaceOptions race;
race.solve.backend = Backend::Native;
race.solve.guarantee = Guarantee::Exact;
race.solve.time_limit_seconds = 120;
race.exploration_seconds = 8; // total nominal exploration, not per candidate
race.probe_node_limit = 50000; // per candidate; global node limit still applies
auto result = solve_native_race(model, race);
```

Two sequential probes receive equal local time/node allowances. A full proof
ends the solve immediately. Otherwise, selection prefers the better validated
original-model incumbent, then the stronger valid global bound, with the
automatic route winning ties. The selected strategy restarts with the remaining
global budget. Its search tree is not resumed, and probe incumbents are retained
for the result rather than injected as starts that would disable preprocessing.
Original-model incumbents/bounds survive an unproductive restart. No result from
an unfinished independent component is treated as a complete-model proof.

**Racing can increase total CPU work and solve time.** Both exploration and
restarting repeat work; early progress can select the wrong eventual winner.
Conversely, several seconds or longer of exploration may quickly identify a
substantially more effective path and pay off during a longer solve. This is a
heuristic with no speedup guarantee. Probes run sequentially on one worker, not
in parallel. Defaults allow two seconds total exploration and 4096 nodes per
probe; a finite solve deadline caps nominal exploration at 25% of the remaining
time. Zero exploration selects the ordinary automatic policy. Raising exploration
time and node allowances permits longer trials; it does not extend the global
deadline. Cooperative propagation/LP calls may overrun local deadlines.

Every probe, restart, snapshot, reconstruction and final validation shares one
monotonic deadline, cancellation token and cumulative node count. Local probe
exhaustion does not cancel subsequent work. Results include the probe count,
selected route, cumulative nodes and an overhead notice. Supplied starts,
globals, indicators and incompatible options retain the direct automatic path.
`solve_native_auto` and the common `solve(..., Backend::Native)` do not silently
enable racing. Existing explicit native/LP/frontier APIs are unchanged.

Racing validation: all 75 tests pass after a full isolated Release rebuild.
The race fixture checks exhaustive min/max optima, actual two-probe/restart
execution, cumulative node caps, starts, cancellation and invalid input; it also
passes with native checked LP disabled. Race and shared-budget tests pass in a
backend-free build. Nested budget-slice tests verify that local exhaustion leaves
the parent usable and cannot relax an inherited cap.

Before racing was added, the isolated Release build passed all 74 CTest entries,
including the original FAST suite and the new automatic/presolve/component/symmetry
tests. Five focused tests pass with checked LP disabled, and four pass in a
backend-free build. All four changed mechanisms pass AddressSanitizer and
UndefinedBehaviorSanitizer checks; leak detection is unavailable on this macOS
runtime. Knapsack tests exercise 1568 independent-oracle and budget configurations.
The original measured benchmark library remains byte-identical. These are
correctness/resource checks, not a new performance comparison.

## Exact automatic preprocessing

Within the automatic native route, bounded ordinary Integer/Binary linear models
can use three additional transformations. The original model first passes native
structural and arithmetic admission; reductions cannot turn an unsupported input
into a silently accepted one. Supplied starts retain the established direct path.
Globals, indicators, semivariables and inspection-cap misses retain that path too.

1. **Presolve:** at most four passes and 65536 propagation row visits. Fixed
   variables and redundant rows are removed, and bound deductions are retained.
   Finalized partial reductions are also equivalent. The reduced continuation
   requests Exact, original witnesses are reconstructed and checked at tolerance
   zero, and only the actual reduced solve can establish optimality or
   infeasibility. Full objective values, including fixed-variable offsets, agree;
   certified reduced bounds transfer without another offset adjustment. The
   standalone `postsolve` utility still returns only a feasible historical point.
2. **Independent components:** the active variable/ordinary-row incidence graph
   must be disconnected. At most 64 components are solved sequentially under one
   time/node budget. Their objectives exclude the original offset; original
   evaluation adds it once. Every component must prove optimality before an
   original optimum is published. A proven infeasible component establishes
   original infeasibility. Partial assembly returns no original incumbent/bound.
3. **Interchangeable columns:** equal types, domains, objective coefficients and
   coefficients in every active row establish exact permutation symmetry.
   Ordering adjacent members retains an optimum from every equivalence class.
   Returned witnesses are checked on the original model. This first implementation
   does not detect permutations of entire bin/machine blocks or general graph
   symmetries. Domains with magnitude above 500 million skip ordering, keeping
   generated row activity within conservative native arithmetic limits.

The same 4096 variable/row slots and 65536 nonzero inspection caps apply.
Eligible knapsack DP is checked before transformations and again for reduced
components, preserving its specialized route. New original results must be
validated and published within the cancellation/deadline budget, including
preprocessing cleanup; hitting a node quota does not invalidate the final
admitted node's completed proof. No conflict learning is added.

Build the bridge from the repository root with `GECODE_ENABLE_OPTIMIZE=ON`,
the integer/search components enabled, and `GECODE_OPTIMIZE_WITH_NATIVE=ON`.
The last option defaults to ON when those native components exist. A standalone
`-S gecode/optimize` build supports the numerical or backend-free component;
explicitly requesting native support there fails with top-level build instructions.
HiGHS can be disabled in a combined native-only optimization build with
`GECODE_OPTIMIZE_WITH_HIGHS=OFF`. Its explicit native route still works.

## Supported mathematical subset

- Every active variable has type `Integer`, `Binary` or `SemiInteger`, with
  finite integral bounds inside `Gecode::Int::Limits::min` through `max`.
  Semi-integer domains are exactly `{0} union [lower, upper]`, represented by a
  native `IntSet`; their zero alternative is retained.
- Original linear coefficients and finite row bounds are integral and inside
  the same native limits. Infinite row sides are allowed. Equality, lower-only,
  upper-only, ranged, empty and redundant rows are supported.
- Each original row and each original indicator expression must satisfy
  `sum_i max(abs(a_i*effective_lower_i), abs(a_i*upper_i)) <= Int::Limits::max`.
  Effective lower bounds include zero for semi-integer variables. This
  conservative condition bounds all products and partial activities without
  relying on cancellation or on other constraints to tighten domains.
- Both objective senses are supported. The objective expression obeys the
  same activity condition with `Int::Limits::max / 2`, reserving space for the
  native cost equality. The offset is integral, and its magnitude plus the
  largest absolute attainable expression bound must not exceed `2^53`. Thus
  all objective values can also be represented exactly by the result's double
  fields.

Unsupported continuous domains, fractional numbers, missing finite variable
bounds, and excessive activity/objective ranges return `Unsupported` before
search. Bounds are never silently rounded and an unsupported formulation is
never reported as infeasible. Even a fixed continuous variable is outside this
initial integer compiler. A caller may construct an explicitly equivalent
integer model, but the bridge does not infer or rewrite that intent.

## Bounded binary knapsack strengthening

Ordinary native search recognizes one narrow exact subproblem at the root:
every active variable must be an original `Binary` with domain exactly `[0,1]`,
and one capacity row must cover every active column with strictly positive
integer weights. The row may be written as `weights*x <= capacity` or its
sign-reversed lower-bound form. An opposite side is allowed only when it is
nonrestrictive for nonnegative weights. Active indicators, globals, additional
rows, uncovered variables, fixed binaries and binary-valued `Integer` variables
use the existing native path.

An exact dynamic program minimizes the signed objective over this capacity
row. Maximization negates the coefficients internally; the offset is kept
separate. Capacity remains capped at 65,536. Two rolling `int64_t` rows store
values, and one decision bit per item/capacity pair preserves exact traceback.
Work is capped at 32 million transitions and the accounted DP payload at 8 MiB,
including rows, decisions, weights, costs and witness. Larger instances fall back
before allocation. A cooperative 250 ms local preprocessing limit can abandon
DP without publishing partial evidence; native search keeps the global budget. An objective for which all-zero is already optimal
also keeps the ordinary minimum-first path. The recurrence uses work proportional
to the admitted table size; it is pseudo-polynomial in numeric capacity.

The reconstructed binary witness is checked against the capacity and objective
before use. The native space receives only the proven objective-side bound
(`cost >= optimum` for minimization, reversed for maximization), which preserves
all original feasible assignments. The owning witness orders native choices;
it never fixes the model or directly publishes a result. Ordinary native search,
strict incumbent cutoffs and independent original-model candidate checking still
establish the returned status and solution.

This work runs once during root construction and shares cancellation and time
limits, with checks every 256 recurrence cells, each row, and during reconstruction. It consumes no
search-node admissions. Allocation failure follows the existing `MemoryLimit`
contract; time or cancellation does not publish an unfinished artifact. Explicit
NativeLP, frontier relaxation and restricted local neighborhoods bypass the DP.
No generic objective-sign value ordering or generic DFS traversal change is
enabled. Benefits apply to this admitted subproblem, not general CP or MIP.

## Original indicators and exact validation

Active typed indicators use their original row and activation value. The
compiler validates the entire mutable snapshot, including generated-row
origins, captured domains and guarded numerical lowerings, then replaces those
generated rows with native reified integer constraints. For a ranged indicator
both sides are implications from the same activation literal. The numerical
helper's optional inactive gate retains its exact equality with the activator,
so objectives and other rows that reference that exposed gate keep their
meaning. Nonintegral, outward-rounded M values in the discarded lowering do
not make an otherwise supported original integer indicator unsupported.

Every candidate is mapped back to the original variable slots, including
tombstones. A separate integer checker reads the original snapshot, checks
variable domains, original rows, original indicators and gate equalities, and
recomputes the objective using `int64_t`. Its arithmetic is protected by the
compiler's product and absolute-activity limits. The native cost variable must
match that recomputed objective. The candidate must additionally pass the
existing original-model numerical checker, including its retained numerical
lowerings, before `solution_validated` can become true.

`Guarantee::Exact` therefore refers to preserved integer arithmetic and native
finite-domain search on this explicit subset. It is not just numerical
feasibility relabeled as exact. Completed branch-and-bound establishes optimality
or infeasibility through native propagation and exhaustive search with sound
strict objective cuts. The bridge does not emit an independently checkable
proof artifact; `Guarantee::Certified` returns `Unsupported`.

`Guarantee::Numerical` accepts the same supported subset and runs the same
integer search and checks. Feasibility and integrality tolerances never relax
the integer checker. Relative/absolute gap options do not enable early stopping
in this route; it attempts full optimality even when positive gaps are allowed.

## Complete native starts

`SolveOptions::primal_start` accepts one complete exact assignment through
`solve(..., Backend::Native)` and `solve_native`. Values use owner-aware original
variable handles; duplicate, foreign/deleted, nonfinite, nonintegral,
out-of-domain or infeasible complete input returns `InvalidModel`. No rounding
is performed, including for a `Numerical` guarantee or near-integral values.
The zero alternative of a SemiInteger domain remains valid.

Supply every active ordinary variable. A missing live indicator `inactive_gate`
is derived from its exact activation relation; chains are completed forward
without guessing, and an explicit inconsistent gate is rejected. A retained
gate after `remove_indicator()` has no such live meaning and must be supplied.
Other private/fixed slots are not inferred. Any unresolved active slot returns
`Unsupported`; values are never fixed in the original search as partial hints.

```cpp
SolveOptions options;
options.backend = Backend::Native;
options.guarantee = Guarantee::Exact;
options.primal_start = {{x, 2}, {enabled, 0}}; // all ordinary active variables
const auto answer = solve_native(model, options);
// start_submitted reports accepted input; solution_validated checks the witness.
```

Full native preflight and exact original row/indicator/global/objective checks
precede publication. A second independent public validator must also pass.
A timely accepted start is stored as an owning incumbent (`start_submitted` and
`solution_validated` true), then the unfixed original root receives a strict
integer objective cutoff. Exhausting this improvement problem proves the
retained incumbent optimal; it never makes the original model infeasible.
Later limits or operational failures preserve an earlier timely validated
incumbent, while invalid/late starts publish nothing. The original snapshot,
revision, constraints and variable bounds are unchanged.

Start checking uses the shared clock/cancellation token and no search node or
extra native propagation. Zero time, pre-cancellation and zero node quota stop
before start processing. Model edits require full revalidation and objective
recomputation on the next solve; there is no persistent native session or
implicit previous-result reuse. This slice does not add repair, partial
completion search or an automatic cold-start heuristic. See
[NATIVE-PRIMALS-DESIGN.md](NATIVE-PRIMALS-DESIGN.md) for the later portfolio scope.

## Search, limits, and results

The first implementation uses one deterministic worker, smallest-domain-first
variable branching and minimum-value-first alternatives. `threads != 1`, a
nonzero random seed, or an unresolved partial primal start returns
`Unsupported`. Complete exact starts are accepted as described above.

One shared `SolveBudget` covers structural validation, compilation, native
search and candidate checking. The `Model` overload also deducts the time used
to create its owning snapshot; moved-from model errors become `InvalidModel`
results instead of escaping that overload. Native search statistics contribute
newly visited nodes to the budget. A native stop object checks cancellation,
deadline and node limits, in that priority order.

Stopping is cooperative. Individual native propagation and recomputation calls
cannot be interrupted, so the wall time may exceed the requested deadline.
Budget checks after backend calls and after original-model checking exclude
late candidates; an earlier validated incumbent may still be returned. At an
exact node-limit boundary the bridge conservatively reports `NodeLimit`, even
if a candidate or exhaustion was observed in the same call.

Interrupted results have no `best_bound`, absolute gap or relative gap: this
bridge does not yet maintain a global bound over the unfinished search
frontier. Only proven optimal completion sets `best_bound == objective` and
zero gaps. Proven infeasibility has no incumbent or objective. An exact
interrupted incumbent remains an exactly checked feasible witness; its status
does not claim optimality. Historical results retain original identity, revision,
values and tombstone layout after subsequent model edits.

## Build and verification

`native.cpp` has a backend-disabled stub when `GECODE_OPTIMIZE_WITH_NATIVE` is
absent. Enabling it requires native Gecode integer, search, kernel and support
libraries, their matching generated configuration header, and the thread
library. It does not require the minimodel library or HiGHS. The build
integration owns native dependency discovery and links; the source itself
never fetches anything. The native test target must use the same enable macro.

`test/optimize/native.cpp` compares tiny problems to a separate exhaustive
integer oracle for both senses, negative coefficients/offsets, ranged rows,
semi-integers and both indicator activation values. It also covers gate
references, redundant/constant/empty models, generated fractional M values,
model history, tombstones, foreign handles, hostile snapshots, node-limited
incumbents, zero deadlines, cancellation, backend mismatch, disabled builds,
unresolved partial starts and deliberate integer/floating range failures.

`test/optimize/native_starts.cpp` independently enumerates the original finite
domains and predicates, including globals, semi-integer holes, live and removed
gates, and both objective senses. It checks every accepted start against this
oracle, then verifies that the original unfixed problem is still optimized.
Separate test-hook builds inject cancellation, allocation errors and operational
failures around validation, publication, LP preparation, cutoff posting, frontier
transfer and cleanup; interrupted bounds are checked against the oracle.

Local complete-start checks passed 2,636 configurations with native Gecode and
HiGHS, both normally and with the bridge, test, native libraries and HiGHS built
using address/undefined sanitizers. The native-only hook build passed 1,350
configurations. Existing native, LP, frontier, reliability-branching and global
regressions also passed. These are correctness checks, not performance
benchmarks or a claim of native MILP parity with commercial solvers.

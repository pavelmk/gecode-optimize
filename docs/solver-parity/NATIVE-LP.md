# Native Gecode with checked sparse LP deductions

`solve_native_lp` is an explicit C++17 entry point joining the bounded-integer
sparse relaxation to the owning optimization model API. `solve()`, `Auto`, and
ordinary `solve_native()` retain their existing behavior. A performance default
has not been selected from the correctness measurements below.

```cpp
#include <gecode/optimize.hh>
namespace O = Gecode::Optimize;
O::Model model;
auto x = model.add_integer(-2, 10);
auto y = model.add_integer(0, 10);
model.add_row({{x, 2}, {y, 3}}, 7,
              std::numeric_limits<double>::infinity());
model.minimize({{x, 1}, {y, 1}}, 8);
O::NativeLpOptions options;
options.solve.guarantee = O::Guarantee::Exact;
options.solve.time_limit_seconds = 10;
auto outcome = O::solve_native_lp(model, options);
const auto& result = outcome.result;
if (result.has_solution()) {
  // Historical original-model values; inspect termination separately.
  const auto value = result.value(x);
}
const auto lp_calls = outcome.relaxation.lp_calls;
```

Both `Model` and owning `ModelSnapshot` overloads are available, including in a
backend-free build. Check `native_lp_capabilities().available`; a missing native
engine, HiGHS library, or compiler with the checked 128-bit implementation gives
`Unsupported`. In particular, the current MSVC certificate implementation is not
available; the facade does not silently run a different solver on that platform.
Consumers need only the optimization headers and exported library target, not
HiGHS headers. A combined top-level native build with
`GECODE_ENABLE_OPTIMIZE=ON`, `GECODE_OPTIMIZE_WITH_NATIVE=ON` and
`GECODE_OPTIMIZE_WITH_HIGHS=ON` enables the implementation on supported compilers.
The optional legacy MiniModel component itself need not be enabled.

## Original semantics and derived relaxation

The existing native compiler owns enforcement of all original rows, reified
indicators, inactive-gate identities and native globals. It supports finite
Integer/Binary/SemiInteger variables, integral bounds/coefficients/offsets, and
the conservative arithmetic limits in [NATIVE.md](NATIVE.md). Unsupported
continuous or fractional data is rejected without rounding.

The LP projection contains only ordinary active linear rows. It excludes
indicator-generated big-M rows and their original conditional rows, and excludes
global constraints. Those remain fully enforced by native propagation. Each
ranged row becomes up to two canonical sparse `A*x >= b` rows. Tombstones are
removed only from the private column representation, and every reported value
maps back to its original slot. SemiInteger variables keep their native domain
holes; the LP uses the enclosing `[0, upper]` box. Omitting constraints and holes
makes a valid relaxation, not a substitute definition of feasibility.

Minimization costs enter directly. Maximization negates the linear costs and
links an auxiliary LP cost to the negative of the native objective variable.
The original offset stays outside the relaxation and is restored exactly in
reported results. In addition to the native guards, LP coefficients, row bounds
and objective coefficients must have magnitude at most `1e9`; objective absolute
activity is limited to half the native integer range. A model accepted by the
plain native bridge can therefore be Unsupported in the hybrid entry point.

Numerical HiGHS row multipliers only propose deductions. The separate checked
integer certificate implementation verifies the weak-duality bound and any
objective-cutoff interval reductions before native domains change. Numerical LP
infeasibility is counted as a diagnostic and never suffices to prune a space.
Every returned witness is independently checked against all original integer
constraints and the original objective. `Guarantee::Exact` is supported for this
bounded discrete subset; `Guarantee::Certified` is still Unsupported because
the solver does not export a full independently checkable search proof.

## Scheduling, ownership and budgets

Default `NativeLpFrequency::Root` attempts an LP at root propagation, and
`bound_tightening=true` retains the resulting affine certificate for cheap exact
reevaluation in descendant boxes. `AfterBoundChanges` requests reoptimization
after `bound_change_interval` observed variable interval changes; the interval
must be positive. These are propagator scheduling policies, not promises of
exactly one LP call per search node. Fully assigned spaces need no LP call.

Each solve owns a separate backend workspace. Cloned spaces share it through
owning references; access is serialized and every call resets all column bounds,
including bounds widened when visiting a sibling. A previous basis is a hint.
It is never a certificate for another box. The workspace is destroyed after
search finishes, while copied results and statistics remain available.

The shared solve budget includes snapshotting, native/LP compilation, search and
original-witness validation. Cancellation, zero time and zero node limits are
checked before LP construction. Cancellation/time limits remain **cooperative**:
native propagation and an in-progress LP call cannot be preempted. Each LP
attempt has its own HiGHS limit of 0.2 seconds and 10,000 simplex iterations;
that backend time limit also is cooperative and is not a strict latency bound.
Candidates arriving after the shared deadline are not newly published.

Only one deterministic worker and seed zero are supported. Complete exact
starts use `options.solve.primal_start`, including the live indicator gate
completion and exact input checks in [NATIVE.md](NATIVE.md#complete-native-starts).
A validated start is published before expensive LP/root-cover preparation; the
unfixed native root then receives its strict objective cutoff. Root covers
still use original global rows/domains, and cutoff-dependent filtering is not
promoted to globally reusable cuts. Unresolved partial starts are unsupported.
Interrupted results may retain a previously validated incumbent but
have no global bound or gap: a checked bound at one search node is not a bound
over the unresolved search frontier. Full exhaustion has the existing native
Optimal/Infeasible semantics. These limitations are explicit in capability
metadata, not hidden fallback rules.

The separate `relaxation` record reports LP calls/time, accepted/rejected
certificates, ignored numerical infeasibility reports, filtering evaluations,
conditional checks, variable fixings and interval tightenings. Counts describe
the entire solve, including cloned/recomputed spaces; they are not unique-node
counts. `result.backend` and `backend_version` identify both engines.
Empty or zero matrices can obtain a checked box bound without calling HiGHS;
the accepted-bound count can therefore exceed the LP-call count.

## Optional verified root covers

```cpp
options.root_cover_cuts = O::NativeRootCoverSettings{}; // absent by default
options.root_cover_cuts->max_rounds = 4;
options.root_cover_cuts->max_work = 4000000;
auto strengthened = O::solve_native_lp(model,options);
const auto& cuts = strengthened.relaxation.root_cover;
// cuts.requested, cuts.completion, cuts.cuts, cuts.work, cuts.lp_calls
```

This setting runs the [root cover loop](CUT-LOOP.md) before creating native
search spaces. Its immutable source contains the original normalized ordinary
linear rows, original objective coefficients and original LP domain hulls.
Every cover is independently proved globally valid for that source. Neither
indicator-generated rows nor constraints discovered at a search node become
proof premises. General integer terms can participate only when the cover
transformation supports their original domain; other rows are skipped and
counted. The original native indicators, globals, domain holes and witness
checker remain active throughout search.

Each successful round produces a fresh immutable augmented sparse backend.
The existing integer LP posting helper posts its implied cover rows natively
as well as using them in LP solves. Full native coefficient/activity preflight
precedes that publication. Every model column and reported original identity
keeps its previous meaning. Maximization remains normalized by negating costs;
the original objective offset stays outside both the root loop and its cuts.

The solve retains the root loop's original source, exact cut records, current
model and earlier checked-bound evidence for the entire search lifetime.
Cloned native actors own the augmented backend and their own checked
certificates. Root-loop certificates are **not seeded** into actors or the
frontier: a last-round augmentation may not have been solved yet, while an older
retained bound belongs to a different augmented matrix. The normal actor
re-evaluates the backend it actually owns. The older BAB API still has no
interrupted global bound, even if the root loop obtained a checked bound.

`NativeRootCoverSettings` exposes total root rounds/work, cut count/nonzeros,
augmented model columns/rows/nonzeros, separator row/term caps and the rational
selection denominator. Defaults match the experimental loop. Zero caps are
valid and stop that optional preprocessing. Other separation heuristics retain
their bounded experimental defaults. The denominator must be a power of two
from 1 through 1,048,576; validation also runs in builds without LP capability.
Public callers do not need experimental or HiGHS headers.

The root loop shares the outer solve's cancellation/node predicate and remaining
absolute deadline. After it returns, the bridge rechecks the outer budget to
report its precise time/cancellation/node reason. Root LP attempts do not count
as native node admissions. Time remains cooperative around LP, separation and
native work. No source is pruned using floating infeasibility or a raw LP primal.

Root round/work/storage/separation limits preserve the verified augmentation
already completed. `NoPrimalSuggestion` and `InvalidSuggestion` also preserve
the original solve: numerical suggestions select cuts only. If no backend was
created, the bridge constructs the original backend when the outer budget
allows. Consequently these cut limits are not limits on total native search
storage or work. `CallbackError`/`BackendError` stop with solve `BackendError`;
`AllocationFailure` stops with `MemoryLimit`. No operational error is presented
as successful separation or as original infeasibility.

The nested `relaxation.root_cover` record reports requested/not-started state,
explicit cut completion, rounds/augmentations, accepted cuts/nonzeros, work,
projection/skipped-row diagnostics, and all root-loop LP calls/time and checked
or rejected bounds. Its LP counters are already included in the enclosing
`relaxation` totals. Those totals combine every intermediate root backend with
only the retained backend's **post-handoff delta**, so root calls are not counted
twice. A skipped row or `NoNewCuts` does not establish complete cover separation.

## Validation and remaining work

`optimize-native_lp` checks finite-model configurations using an independent
integer enumeration oracle: signed coefficients and domains, ranged/one-sided
rows, both senses and offsets, original-slot tombstones, SemiInteger holes,
reified indicators/gates and all-different semantics. Each model runs with root
and repeated LP schedules, filtering on/off and intervals 1/3. Additional tests
cover independent concurrent solves, historical result ownership, changed bounds,
malformed options/snapshots, unsupported scale/types/guarantees/partial starts/workers,
zero budgets/cancellation, and absent interrupted frontier bounds. Both native
and HiGHS source libraries are instrumented in the combined ASan/UBSan check.

The same product oracle now runs with root covers off/on, including a combined
binary cover, all-different, reified indicator, semi-integer and offset fixture.
Targeted root-limit tests verify unchanged optima through every exposed cap,
including the last-round unsolved-backend handoff and empty models without LP
suggestions. A coordinator build with `GECODE_NATIVE_ROOT_CUT_TEST_HOOKS` injects
missing/invalid suggestions, operational errors and cancellation at preparation
boundaries. It verifies that hints never decide feasibility, failures cannot
publish incumbents or seed bounds, and requested Exact classification survives
interruption. Existing frontier fault hooks remain independently available.

The normal and fully instrumented native+HiGHS checks pass 759 native LP
oracle/root-cover configurations. The frontier companion passes 2,723
configurations with both preparation and search-lifecycle fault hooks enabled.
Backend-free and native-only builds also pass the explicit unavailable-LP
boundary checks. These are correctness checks; no timing benchmark was run.

This delivers the W5 public bridge and a bounded W7 global-root-cover option.
Dynamic local cuts, presolve/postsolve composition, stronger branching, and a measured automatic
hybrid policy remain separate roadmap work. The API currently has no C/Python
binding and does not capture arbitrary pre-existing Spaces or FlatZinc models.

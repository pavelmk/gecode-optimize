# Explicit native frontier search

`solve_native_search` provides depth-first or best-bound search with a bounded
owning frontier and conservative interrupted global objective bounds. It is an
explicit opt-in API. `solve`, Auto routing, `solve_native` and `solve_native_lp`
keep their existing defaults and behavior.

```cpp
#include <gecode/optimize/native_search.hpp>
using namespace Gecode::Optimize;

Model model;
auto x = model.add_integer(0, 5);
auto y = model.add_integer(-1, 5);
model.add_row({{x, 2}, {y, 3}}, 7,
              std::numeric_limits<double>::infinity());
model.minimize({{x, 1}, {y, 1}}, -6);

NativeSearchOptions options;
options.solve.guarantee = Guarantee::Exact;
options.solve.time_limit_seconds = 10;
options.solve.node_limit = 10000;
options.order = NativeSearchOrder::BestBound;
options.max_open_nodes = 1000;
// Optional, requiring native checked-LP capability:
// options.relaxation = NativeLpSettings{};
// options.relaxation->frequency = NativeLpFrequency::AfterBoundChanges;
// options.relaxation->root_cover_cuts = NativeRootCoverSettings{};

auto answer = solve_native_search(model, options);
if (answer.result.has_solution()) {
  const auto original_x = answer.result.value(x);
  (void)original_x;
}
// best_bound may be available even after NodeLimit/MemoryLimit/Cancelled.
// Inspect termination separately from incumbent presence and gap values.
```

## Supported models and evidence

The same compiled native model, propagators and independent original-model
checks used by `solve_native` are reused. Supported variables are finite
Integer, Binary and SemiInteger, with integral bounds, linear coefficients,
row sides and objective offset. Native reified indicators and all-different,
element, table, cumulative and circuit constraints retain their original
semantics. Inactive variable/row/global/indicator records remain historical
original slots; the original model and revision are never mutated.

The conservative native integer activity limits and exact double objective
range in [NATIVE.md](NATIVE.md) apply. Continuous variables, nonintegral data,
unresolved partial starts, multiple workers, nonzero random seeds and exported proof
certificates are explicitly unsupported. Options must select Auto or Native;
this entry point never routes to a numerical solver to handle a different class.
Missing native support also returns `Unsupported` with no solution or bound.

Numerical/Exact requests retain their requested result classification. Search
uses exact discrete propagation and checked original integer witnesses; this
is not an exported independent proof certificate. The completed finite search
can establish `Optimal` or `Infeasible`. Nonzero gap settings do not enable early
termination: all pruning requires an exact incumbent comparison. Other tied
optima may be pruned; this is optimization, not a solution-enumeration API.

## Stable frontier and global-bound invariant

Each queued entry owns a stable propagated native `Space`. Its key is an exact
lower bound on the objective without the constant offset, normalized to
minimization. Maximization uses the negative cost variable bound. A child
inherits its parent's bound and may strengthen it after successful propagation.
The queue never substitutes the current node's bound for the global bound.

The narrow [binary knapsack DP](NATIVE.md#bounded-binary-knapsack-strengthening)
can strengthen the original root objective bound when no relaxation is requested.
It preserves every original feasible assignment and supplies an owning witness
preference. For DepthFirst, only this DP preference is complemented so the
existing last-enqueued-child descent follows the witness's inequality arm.
BestBound retains the objective bound as its primary key and, on equal bounds,
prefers the unique queued region that still contains the verified DP witness.
This flag is computed once on a stable space before enqueue; the comparator
does not scan domains. Other ties retain creation order. Ordinary models retain
their existing value and child order. Node admissions, active-parent coverage
and original-model witness validation remain unchanged.

`BestBound` selects the smallest normalized bound, with creation sequence as a
deterministic tie-breaker after the narrowly scoped DP preference above.
`DepthFirst` selects the newest queued stable node.
Alternatives are evaluated in native choice order before their parent leaves
the frontier; the most recently enqueued child is therefore expanded next in
DepthFirst mode. This is a frontier implementation, not the existing BAB
engine's clone/recomputation order. Children are propagated when admitted, so
best-bound priorities reflect deductions available before queue selection.

During expansion, the parent remains owned and its bound remains active while
each alternative is cloned, committed, propagated and independently validated.
A child is either safely enqueued or fully discharged. Only after every
alternative has been accounted for is the parent removed. The `Choice` remains
alive throughout all commits. New children receive any strict incumbent cutoff
before propagation; stable queued parents need not be modified to use a newly
found incumbent. A queued region whose bound cannot improve the incumbent is
safely pruned.

For normalized minimization, the interrupted global bound is the minimum of:

- the independently validated incumbent, if present;
- every queued region's inherited/propagated bound;
- the active root or expanding parent's bound, if its region is unresolved.

The parent deliberately overlaps already-created children during partial
expansion. This may weaken the bound, but preserves coverage of every unvisited
alternative. Maximization reverses the normalized bound, then the original
objective offset is added. Exact compilation bounds ensure these conversions
stay representable. A semantic implementation error falls back to the initial
compiled objective-box bound instead of authorizing propagated evidence.

For example, minimize `2*x+y-17` with binary `x,y`. DepthFirst can find `-15` in
the `x=1` region while the `x=0` sibling still contains the optimum `-17`. Stopping
after four admitted nodes returns incumbent `-15` and global bound `-17`; it must
not report the current region's bound `-15` as a global optimum.

## Node, storage and time budgets

One `SolveBudget` covers snapshot creation, structural validation, compilation,
root construction, propagation, candidate checking, frontier operations and
cleanup. Cancellation and deadlines are cooperative; native propagation, LP
calls and individual allocations are not preemptible. Candidates are published
only after exact and independent numerical original-model checks and a final
time/cancellation check. A candidate whose validation finishes after an observed
stop is excluded; the active region remains represented.

The node quota counts admitted root/child propagation attempts. Admission checks
the complete budget, then charges one node. That admitted node may finish and
publish a validated incumbent if time/cancellation permits, even when it uses
the final allowed node. The next admission is blocked. A root solved with a
quota of one may therefore finish optimally. This differs deliberately from the
older BAB stop-adapter timing; the older APIs are unchanged. A quota of zero
stops before compilation and consequently has no objective-box bound.

`max_open_nodes` counts storage reservations for queued spaces, the active
parent, and an in-flight child. It is a node-count limit, not a byte or operating
system memory guarantee. Zero rejects root storage with `MemoryLimit`; one can
process a root but cannot expand a branch because its parent must remain owned
while a child is created. Actual allocation or native clone failures also
return `MemoryLimit`. The parent bound remains available when expansion fails.

An interrupted result keeps any earlier timely validated incumbent. Its finite
bound may be absent when compilation never established an initial objective
box. A zero gap does not override an interruption status. Completion is reported
only after every region is discharged. `Infeasible` has no incumbent or finite
best bound. An interruption after all regions were discharged still has its
interruption status; no late completion status is manufactured.

`NativeFrontierStatistics` reports admitted nodes, expanded parents, failed
nodes, bound-pruned nodes, accepted feasible leaves, peak storage reservations,
and unresolved represented regions at termination. The unresolved count may
include an overlapping parent and its already-enqueued children; it is not a
count of disjoint search regions or bytes. Each solve owns its frontier and,
when enabled, its relaxation workspace independently.

## Complete starts and the frontier

`options.solve.primal_start` accepts complete exact starts using the same
[original-model and live-gate completion contract](NATIVE.md#complete-native-starts)
as ordinary Native. No arbitrary partial completion or fixing is performed.
The owning incumbent and its normalized integer cost are installed before LP
setup, root allocation and propagation. Its check consumes shared time/memory
but no admitted node, feasible search leaf or reliability probe.

The original root is left unfixed and receives a strict cost cutoff. The initial
whole-model bound remains active through setup/faults; subsequently every
unresolved improvement region remains represented. The original global bound
is the minimum of the normalized incumbent and these unresolved region bounds,
with maximization/offset restored at the public boundary. An incumbent alone
never replaces missing region evidence. Exhausting all improving regions proves
the retained solution optimal, even if the root fails under the strict cutoff.
A timely start survives later limits or failures, while late validation publishes
nothing. Zero time/cancel/node budgets preserve the existing early-stop policy.

## Optional checked LP

`NativeLpSettings` contains the existing frequency, bound-tightening and bound
change interval controls. `NativeLpOptions` inherits those controls, preserving
normal `.frequency`, `.bound_tightening`, `.bound_change_interval` and `.solve`
member usage for `solve_native_lp`. `NativeSearchOptions.relaxation` is absent
by default; no LP model, workspace or solve is created in that case.

An explicit relaxation uses the same sparse bounded-integer LP actor and
independently checked integer bounds/cuts as [NATIVE-LP.md](NATIVE-LP.md). Numerical
infeasibility alone cannot prune a native region. Globals and indicators remain
native constraints and are omitted from the ordinary linear relaxation.
`native_lp_capabilities().available` identifies the extra build requirement:
native Gecode, HiGHS and checked wide-integer compiler support. Missing support
returns `Unsupported`, not a fallback to an unrequested method. The inherited
per-attempt LP time/iteration limits are cooperative. `answer.relaxation` holds
the existing LP statistics separately from frontier statistics.

`options.relaxation->root_cover_cuts` optionally uses the same bounded original-
source global cover preparation as `solve_native_lp`; it is absent by default.
See [root cover semantics and counters](NATIVE-LP.md#optional-verified-root-covers).
Only original ordinary rows and original LP boxes prove cuts. The native
compiler still enforces all original globals, indicators and semi-integer holes.
The new immutable augmented backend and its exact cut attribution remain owned
through the search, and the existing posting helper also posts its implied rows
natively. No certificate from an earlier root-loop matrix seeds a frontier key.

If preparation stops on a root-only cap or lacks a usable numerical selection
hint, search proceeds with its verified partial augmentation (or the original
backend). Shared time/cancellation/node stops prevent search from starting.
Operational root-loop errors remain explicit solve errors. An interrupted
frontier before native root propagation retains only its initial compiled
objective-box bound; it cannot replace that with a raw LP objective or an
unassociated historical certificate. Later keys use the existing propagated
integer bound invariant. Root LP attempts do not consume native node admissions.
`answer.relaxation.root_cover` records the separate root completion and counts;
its LP counters are already included in total `answer.relaxation` counters.

## Optional binary reliability

```cpp
Gecode::Optimize::NativeSearchOptions options;
options.solve.guarantee = Gecode::Optimize::Guarantee::Exact;
options.branching = Gecode::Optimize::NativeBranchingSettings{};
options.branching->max_probe_status_calls = 128;
auto answer = Gecode::Optimize::solve_native_search(model, options);
// answer.branching contains separate probe, history, selection and work counts.
```

`BinaryReliability` ranks original Binary variables using directional native
propagation gains. It is absent by default. General integers, semi-integers and
generated indicator gates use the existing brancher when no eligible binary
split is selected. A removed indicator's retained gate remains excluded by its
original metadata. Candidate enumeration uses a deterministic bounded prefix;
this initial policy does not claim complete candidate exploration.

The coordinator probes one fully constrained clone at a time. Native globals,
original indicators, semi-integer holes and any checked LP/root-cover actor
remain active. Both finite directions must complete before their history pair
is published. Two finite pairs make a variable reliable by default; completed
failed directions have a separate categorical rank and never enter a mean as
infinity. Ties favor the original variable slot. Zero/invalid ranking scores
fall back to the built-in brancher.

These are binary unit-step propagation-gain estimates, not classical LP
fractional-displacement pseudocosts. Every probe is discarded. It cannot publish
an incumbent, tighten the parent, seed a child bound or eliminate a sibling.
After selection, both real children follow the existing admission, propagation
and original-witness checks. The active parent's old bound covers interruption
throughout probing and partial child transfer.

All probe status attempts charge the shared node budget. This counts admitted
attempts: cancellation/time expiry at the final pre-status check can consume
a slot without executing propagation, just as for ordinary admissions. Thus
`answer.branching.budget_nodes` equals `answer.frontier.admitted_nodes` plus
`answer.branching.probe_status_calls`; `admitted_nodes` continues to describe
only real search regions. A pair starts only when the remaining node quota can
hold its two attempts and two ordinary child admissions. The last admitted
attempt may finish, subject to shared time/cancellation checks. The absent
branching option preserves the prior node accounting and search path.

Settings bound candidates per decision, total/per-decision probe status calls,
history entries, coordinator work and consecutive nonimproving pairs. Zero
resource caps skip optional work; `reliability_samples` must be positive. A
probe also needs one spare slot under `max_open_nodes`. Optional cap exhaustion
preserves completed ranking observations and falls back when necessary; actual
allocation failures remain MemoryLimit. Shared stops and operational errors
preserve the existing interruption/error classification and bound safeguards.

The work counter meters candidate storage, scans, history comparisons and a
fixed allowance per planned probe pair. It is not a propagator-instruction or
byte limit. `status()` runs to fixpoint/failure, with cooperative checks around
it; observed propagator executions are reported separately. Probe LP calls and
seconds are subsets already included in the solve-wide relaxation totals.
Neither an LP floating infeasibility report nor a raw LP point decides a native
prune. The design and later LP-pseudocost requirements are in
[BRANCHING-DESIGN.md](BRANCHING-DESIGN.md).

`test/optimize/native_branching.cpp` is an independent original-box oracle for
the enabled policy. Its coordinator build uses
`GECODE_NATIVE_BRANCHING_TEST_HOOKS` plus `GECODE_NATIVE_SEARCH_TEST_HOOKS` to
inject failures in probe preparation/publication and manual child transfer.
The hooks are not a production callback API. Coverage includes every small
node quota, caps, native globals/indicators, min/max, offsets, tombstones,
history reuse, failed pairs, a real deadline expiry, adversarial scores,
clone-then-fallback lifecycle, and concurrent independent solves.

The normal and fully instrumented native+HiGHS coordinator runs pass 2,397
original-oracle/budget/fault configurations. Native-only passes 2,381; the core
build verifies explicit unavailable and malformed-option behavior. The unchanged
frontier coordinator also passes all 2,723 default-policy configurations. Native,
adapter and HiGHS code were instrumented together; no timing benchmark was run.

Build integration adds `native_branching` to the ordinary test list and a
separate native coordinator executable compiling the test and native adapter
with both hook macros above. Link native int/search/kernel/support plus the
normal Optimize foundation, and HiGHS only for the enabled LP variant. A
120-second CTest timeout accommodates the injected one-second deadline test
and instrumented native propagation. Production libraries must omit the hooks.

## Correctness coverage

`test/optimize/native_search.cpp` computes complete original-box integer optima
with an independent oracle. Both search orders are tested across every node
quota through exhaustion and a range of storage caps. Fixtures include signed
coefficients, both objective senses and offsets, ties, infeasibility, empty and
fixed models, tombstones, semi-integer domains, original indicators and all five
native global constraint families. Every returned incumbent is checked against
the original model, and every finite interrupted bound is compared to the exact
oracle optimum. Dedicated sibling-better examples require a nonzero incumbent
gap at interruption.

A coordinator build with `GECODE_NATIVE_SEARCH_TEST_HOOKS` injects cancellation
and allocation failure at root construction, cloning, commitment, propagation,
validation, enqueue and parent discharge. It checks late-candidate exclusion and
parent coverage during partial expansion. This macro is a test-only source hook;
there is no production callback surface. Backend-free tests verify unavailable
capabilities and malformed options. Combined native/HiGHS tests exercise the
optional actor and its limits. Native and vendor libraries used in sanitizer
checks must be instrumented and match the compiled native kernel headers.

Additional cover tests combine both search orders, min/max and offsets,
semivariables, tombstones, original indicators and all-different constraints.
They compare every finite interrupted bound and incumbent to the original
finite-product oracle across node/storage quotas and zero/one/four root rounds.
Root-only caps preserve the same optimum. A separate
`GECODE_NATIVE_ROOT_CUT_TEST_HOOKS` coordinator checks root preparation errors,
hint-only failure handling and cancellation; existing frontier lifecycle fault
tests continue to run independently of those preparation hooks.

The normal and fully instrumented native+HiGHS builds pass 2,723 frontier
configurations with both hook sets enabled. A native-only build passes 2,217
configurations and explicitly rejects the unavailable LP route; the backend-free
build also verifies unavailable capability and invalid-option behavior.

These are correctness gates. The API is not automatically enabled, and no
performance advantage over BAB, HiGHS or commercial solvers is claimed without
separate benchmark evidence.

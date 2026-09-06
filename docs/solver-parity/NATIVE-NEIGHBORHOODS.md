# Explicit native primal neighborhoods

`solve_native_neighborhoods()` adds one optional BinaryHamming improvement
attempt to the existing native frontier. It retains native constraints and
shares only an independently checked better original-model assignment. Existing
`solve()`, Native/BAB, NativeLP and `solve_native_search()` behavior and defaults
are unchanged. The API is experimental; no automatic speedup or commercial
primal-portfolio parity is claimed.

Include [`native_neighborhoods.hpp`](../../gecode/optimize/native_neighborhoods.hpp):

```cpp
using namespace Gecode::Optimize;
Model model;
auto x = model.add_binary();
auto y = model.add_binary();
auto z = model.add_binary();
model.add_row({{z, 1}, {y, -1}}, -std::numeric_limits<double>::infinity(), 0);
model.minimize({{x, 100}, {y, -20}, {z, 1}});

NativeNeighborhoodOptions options;
options.search.solve.backend = Backend::Native;
options.search.solve.guarantee = Guarantee::Exact;
options.search.solve.node_limit = 2000;
options.search.solve.time_limit_seconds = 1.0;
options.search.order = NativeSearchOrder::DepthFirst;
options.neighborhood.radius = 1;
options.neighborhood.max_status_calls = 128;
options.neighborhood.time_limit_seconds = 0.05;

const auto answer = solve_native_neighborhoods(model, options);
const auto& result = answer.search.result;
if (result.has_solution()) {
  const double value = result.value(x);
  (void)value;
}
```

The outer result contains the normal `NativeSearchResult` and separate
`NativeNeighborhoodStatistics`. It preserves original model identity/revision,
slot masks, objective sense/offset and historical result ownership. The Model
overload charges snapshot creation to the solve deadline and translates
moved-from Model errors consistently with other native routes.

## Supported search and neighborhood

All current bounded exact native integer, Binary, SemiInteger, indicator and
global preconditions apply to the entire original model. Full structural and
native arithmetic admission happens before search. Unsupported original
fractional/continuous/overflow models are not silently relaxed. Numerical
requests still use the native exact integer witness checker; Certified proof
export, parallel workers, nonzero random seeds and gap stopping remain outside
the native frontier contract. [Native semantics](NATIVE.md),
[frontier semantics](NATIVE-SEARCH.md)

The attempt waits for a validated incumbent, either from a supported complete
start or ordinary search. It runs at the first surviving stable main parent,
before that parent's Choice or reliability probes. If an incumbent first appears
during ordinary child expansion, that expansion finishes before the attempt.
If global proof is already complete, no attempt runs. This heuristic cannot
create a cold run's first feasible point. [Complete starts](NATIVE-PRIMALS-DESIGN.md)

Distance includes every active, originally nonfixed Binary slot whose
`indicator_origin` is absent. It excludes tombstones and generated inactivity
gates, including retained origin-tagged gates after indicator removal. A removed
gate remains an ordinary free/user-constrained original variable; exclusion
from distance never derives its value. Other untagged private frontend Binary
slots count normally. The metric counts IR slots: distinct equality-linked
variables count separately, while a handle repeated in a global counts once.

For the frozen incumbent x*, the isolated native model contains

```
sum(x_i for selected slots with x*_i=0)
+ sum(1-x_i for selected slots with x*_i=1) <= radius
```

and the strict original objective improvement condition. Native +1/-1 row
coefficients, array dimensions, total absolute activity and RHS are checked
before posting. The strict cutoff uses the exact compiled cost without offset
and native strict relations, including maximization; it does not subtract one
from an arbitrary endpoint or use a floating tolerance cutoff.

All other integer/semis remain free within their original domains. Radius zero
can improve those variables while keeping selected binaries fixed. An empty
selection, excessive selection size or radius at least its size produces an
explicit skip. The selection is never truncated to fit a cap. Pure general
integer models continue normal proof search with no BinaryHamming attempt.

The original model is compiled once under the shared budget. A fresh native
Space is posted from that compilation for the optional attempt, without an LP
actor. Rows, indicator semantics, globals and objective equality stay intact.
The original snapshot and main numerical backend/cut evidence are unchanged.
Local DFS uses the ordinary native brancher, without reliability probes or
recursive heuristics. Main search may independently use its existing checked
LP, root covers and BinaryReliability settings.

## Proof and publication

Main queued nodes and the active parent remain represented throughout the
attempt. Local infeasibility/exhaustion, bounds and distance rows never enter
global proof storage. The fresh neighborhood is global, so an improvement may
be outside the active main node. Only the original model, the frozen incumbent
cutoff and the specified distance restrict its candidates.

A candidate passes exact original domains, rows, indicator/gate relations,
all global payloads and objective checks, followed by the public numerical
validator as an extra consistency check. Its exact Hamming distance and strict
improvement are checked independently of propagation. Local Spaces/Choices are
released before the final deadline and publication gate. A late or partially
checked candidate is discarded; the earlier incumbent remains. A timely
published improvement survives a later global stop/error. Heuristic publication
never sets or clears the historical `start_submitted` flag.

For normalized minimization, the interrupted global bound is the minimum of
the incumbent and all ordinary queued/active region bounds, with the normal
conservative initial-box fallback on semantic failure. A local bound is never
included. After improvement, ordinary exact incumbent pruning may discharge
the active parent or later children. Only ordinary frontier completion can
return original Optimal or Infeasible.

## Limits and counters

All limits are cooperative around native posting, propagation and whole checker
calls; a call itself can run beyond a time limit before the next checkpoint.
The complete solve clock includes original snapshot/compilation, native
reposting, scans, validation and cleanup. The local clock begins before its
first eligibility/preflight scan and ends at cleanup/publication. Global
cancellation takes precedence over global time and node limits.

| Setting | Meaning |
|---|---|
| `radius` | Exact maximum number of changed eligible Binary slots. |
| `max_status_calls` | Local admitted status attempts, including the root. The last admitted attempt may finish validation at this cap. |
| `max_distance_variables` | Maximum complete Binary selection size; exceeding it skips the formulation. |
| `max_source_entries` | Logical original model fields admitted for optional posting/checking; not bytes. |
| `max_coordinator_work` | Deterministic charged source/eligibility/distance visits and DFS/candidate actions; not propagator instructions. |
| `max_local_spaces` | Resident local ancestors plus an in-flight child, including the fresh local root. |
| `time_limit_seconds` | Finite nonnegative local elapsed cap, also constrained by the remaining whole-solve time. |

Finite provisional defaults are defined in the header. Zero caps skip/end
optional work. Unknown policies or invalid time values are option errors. A
local cap ends only the heuristic; an actual allocation/native memory failure
or whole-solve stop ends the solve honestly.

Before each optional status admission, the implementation preserves two ordinary
child admissions under a finite shared node quota. A local attempt requires
at least three remaining slots. Reliability probes retain their own existing
two-probe-plus-two-child reserve. The current ordinary brancher has two
alternatives; this policy must be revisited before allowing another arity.

The disjoint accounting identity is

```
answer.neighborhood.budget_nodes
  == answer.search.branching.budget_nodes
  == answer.search.frontier.admitted_nodes
   + answer.search.branching.probe_status_calls
   + answer.neighborhood.status_attempts
```

The two `budget_nodes` fields are the same total, not additive. A status attempt
is charged before its final pre-status stop check, so it may consume a slot
without running propagation. `completed_status_calls` counts returned status
calls. `attempts` counts admitted fresh root constructions (at most one), not
nodes; a stop immediately before construction can still consume that attempt.
`accepted_improvements` is at most one and is separate from ordinary
`feasible_leaves`. Local LP work is absent.

Local Spaces must also fit `search.max_open_nodes` together with queued main
nodes and the active parent. Refusing an optional reservation yields
LocalStorageLimit and resumes main search; the ordinary frontier's own storage
limit can still terminate it. `peak_local_spaces` records local reservations;
`peak_total_spaces` includes ordinary and local peaks. Neither measures bytes.

Source entries count one per active variable, objective marker/offset/sense
(three), active row marker/bounds (three) and each term. Active indicators use
eight relation fields, one per term/generated row, and three per saved domain.
Globals count their marker and every argument/payload scalar, with a marker per
Table tuple and three scalars per Regular transition. Strings and tombstones
are not source payload entries. Scanning a tombstone still consumes coordinator
work. No flattened global argument copy is allocated during admission.

Each source-entry charge is also coordinator work; do not add those two counts
to estimate total work. Coordinator work also charges outer container/eligibility
visits, each constructed/checked distance element, DFS frame/alternative actions,
and candidate slot extraction. Native posting/propagation and whole checker
algorithms are governed by source-size/time/status limits, not a fictitious
instruction counter. A cap can leave `eligible_variables` or `source_entries`
as an observed prefix; a partial selection is never solved.

Completion distinguishes skipped/not-started, Improved/NoImprovement, each local
resource cap, GlobalStop and Error. `stop_reason` carries an outer termination
when it interrupts/rejects the attempt. A successful earlier attempt remains
historical if ordinary proof search later stops. Zero-cap priority follows
global time/cancel, local time, explicit status-zero, shared admission reserve,
then encountered scan/storage/formulation limits.

## Validation and remaining scope

[`native_neighborhoods.cpp`](../../test/optimize/native_neighborhoods.cpp) uses an
independent finite-product oracle for original feasibility and objectives, plus
original global truth tables/event/transition walkers. It checks complete and
interrupted results, both objective senses, offsets, semis, aliases, tombstones,
all globals, indicators/gate removal, local caps, shared quotas, LP/reliability
composition and concurrent independent solves. The coordinator variant injects
stops/errors through compilation, posting, DFS, validation, release and
publication. The outside-parent fixture retains a better global optimum outside
the searched neighborhood, so local improvement cannot masquerade as global
optimality. Sanitizer/provenance evidence is recorded with the implementation
commit report; this document does not claim remote CI or benchmark speedups.

The implementation gate uses this source list for an independent coordinator
executable: `model.cpp`, `result.cpp`, `validate.cpp`, `constraints.cpp`,
`globals.cpp`, `native.cpp`, and the test above. Compile native.cpp and the test
with `GECODE_NATIVE_NEIGHBORHOOD_TEST_HOOKS=1` for fault checks. The normal test
needs no hook macro. Native+HiGHS builds must use matching generated native and
HiGHS configuration headers; sanitizer tests instrument every linked foundation.
The backend-disabled test verifies an explicit Unsupported result.

Future general-integer release neighborhoods, node-attributed RINS/RENS,
partial-start repair, repeated/adaptive schedules and automatic defaults remain
separate gates. The research and held-out benefit plan is in
[the W9b design](NATIVE-NEIGHBORHOODS-DESIGN.md). This slice improves an existing
incumbent when successful; the roadmap's cold first-feasible improvement and
W10 explanation/LCG work remain unfinished.

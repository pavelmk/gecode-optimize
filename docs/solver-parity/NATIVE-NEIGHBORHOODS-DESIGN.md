# W9b: bounded native primal neighborhoods

Design and implementation boundary, 2026-09-05. The first bounded BinaryHamming
slice is implemented; see [the current API and limits](NATIVE-NEIGHBORHOODS.md).
No performance benefit is claimed. W9a complete starts are implemented; see
[the start contract](NATIVE-PRIMALS-DESIGN.md). This extends roadmap **W9, primal
portfolio**. W10 remains the separate explanation/LCG project.

The first slice should be one explicitly requested, LP-free **BinaryHamming**
improvement attempt inside the native frontier coordinator. It searches the
original model plus a distance restriction and a strict incumbent cutoff,
retains every native global constraint, and shares only a completely checked
better incumbent with the main search. All existing solve routes and defaults
remain unchanged. This does not yet provide a first feasible solution, general
integer neighborhoods, RINS, RENS, partial-start repair, or an adaptive portfolio.

## Source audit and research basis

The audit includes the current `NativeSpace`, `compile`, `prepare_start`,
`check_exact`, `BinaryReliability`, and `native_frontier_impl` in
[`native.cpp`](../../gecode/optimize/native.cpp), the public
[`native_search.hpp`](../../gecode/optimize/native_search.hpp) counters, and
[`SolveBudget`](../../gecode/optimize/result.hpp). Symbol references are used
because integration moves line numbers.

| Existing mechanism | Consequence for the first neighborhood |
|---|---|
| `compile` checks finite integral domains, coefficients, activity, objective, and native global limits; `Compiled` holds original slot mapping and pointers into the input's global payloads. | Reuse that validated compilation within the same synchronous solve. Retain the input and compilation until all local Spaces are destroyed. Do not change, reindex, or make a partially relaxed `ModelSnapshot`. |
| `NativeSpace` posts original rows, semis, reified indicators, globals, objective equality, and the ordinary binary-alternative brancher. It optionally attaches a checked LP actor. | Construct a fresh original Space with a narrow private “do not attach LP” option. Keep all other posting identical. Cloning a current node carries its local domains and potentially an LP actor; cloning a solved incumbent fixes every decision. Neither is the proposed global neighborhood. |
| A frontend start passes exact original checking, then publishes original-slot values and a scalar normalized incumbent. | Reuse exact arithmetic and the staged witness representation, but not `publish_start`: a heuristic candidate must not set `start_submitted`. Complete-start acceptance and its gate completion keep their existing semantics. |
| The frontier keeps an active parent until all alternatives are evaluated/enqueued, and aggregates queued plus active bounds. | Run optional search only at a stable parent boundary, before a `Choice` or reliability probe exists. The main parent remains alive and represented throughout the call. |
| Shared `SolveBudget` counts ordinary admissions and reliability probe attempts. `frontier_checkpoint` checks time/cancellation, allowing a final admitted node to finish at the node quota. | Add a third disjoint category for neighborhood status attempts. Do not start a nested public solve with a new clock or zeroed counters. |
| A checked LP backend can copy a primal suggestion, but its propagator does not publish an owning current-node observation. Siblings reuse numerical workspace state. | The root-cover suggestion or last workspace solution cannot supply current-node RINS/RENS data. Defer that interface instead of treating stale observations as node data. |

Primary research supports four distinct candidates. The accessible publisher
abstracts were inspected; detailed implementation observations below come from
the pinned open source files, not a claim to have read paywalled full papers.

| Candidate | Required data and useful behavior | Decision |
|---|---|---|
| Local branching, Fischetti and Lodi (2003) | Distance constraints define subproblems around an incumbent. Their full method is an exact strategic branching scheme, including treatment of other regions. [Paper](https://doi.org/10.1007/s10107-003-0395-5) | Use the simple binary distance neighborhood as an optional heuristic. Retain the existing global frontier; do not claim to implement the paper's complete branching scheme. |
| RINS, Danna, Rothberg and Le Pape (2005; online 2004) | Incumbent and relaxation information select an improvement neighborhood. [Paper](https://doi.org/10.1007/s10107-004-0518-7) | Later: requires an owning, attributed relaxation observation and a precisely mapped original subproblem. Cannot address absence of an incumbent. |
| RENS, Timo Berthold (2014; online 2013) | Fix integral relaxation variables and restrict fractional integer variables to floor/ceiling choices. No incumbent is required. [Paper](https://doi.org/10.1007/s12532-013-0060-9) | A later first-feasible comparison after numerical point-to-native-domain conversion is explicit. It is not the same task as incumbent improvement. |
| CP LNS, Shaw (1998) | Remove selected decisions and repair by constraint search; the original paper uses related vehicle visits and limited discrepancy search. [Paper](https://doi.org/10.1007/3-540-49481-2_30) | Later LP-free general-integer comparison: release a deterministic subset and fix its complement. Easier arithmetic than integer distances, but requires a justified release policy. |

SCIP source was inspected at immutable revision
`44fcc87317ed9f3c3b265649b3ef8263ed2bc6ce` (2026-09-03), obtained from the
official repository. No code or tuning constants are copied.

- [`heur_localbranching.c`](https://github.com/scipopt/scip/blob/44fcc87317ed9f3c3b265649b3ef8263ed2bc6ce/src/scip/heur_localbranching.c):
  `addLocalbranchingConstraintAndObjcutoff` constructs the binary distance row;
  `setupAndSolveSubscipLocalbranching` copies the problem, bounds subproblem
  effort, and translates/checks solutions. `heurExecLocalbranching` charges
  prior effort and checks copy limits. This supports explicit setup accounting
  and mapped original validation; its evolving neighborhood/radius schedule is
  beyond this slice.
- [`heur_rins.c`](https://github.com/scipopt/scip/blob/44fcc87317ed9f3c3b265649b3ef8263ed2bc6ce/src/scip/heur_rins.c):
  `determineFixings` compares incumbent and current LP values; the execution
  path requires an optimal current LP and incumbent, checks the fixing rate,
  and bounds the subproblem. Its wrapper disables recursive subsolvers and
  expensive extra work. Our corresponding boundary is no recursive heuristic,
  no reliability probes, and no local LP actor in W9b.
- [`heur_rens.c`](https://github.com/scipopt/scip/blob/44fcc87317ed9f3c3b265649b3ef8263ed2bc6ce/src/scip/heur_rens.c):
  setup copies/mappings and limits are separate from execution; solution
  translation is followed by `SCIPtrySolFree` checks. It also disables recursive
  subsolvers and, in the reduced configuration, expensive dual-bound work.
  A local solver's candidate or status is therefore not sufficient provenance
  for our original-model result.

## Proposed additive API and exact scope

The implementation uses a new wrapper over existing option/result layouts.
The public header contains the complete statistics and completion enum:

```cpp
enum class NativeNeighborhoodPolicy { BinaryHamming };

struct NativeNeighborhoodSettings {
  NativeNeighborhoodPolicy policy = NativeNeighborhoodPolicy::BinaryHamming;
  std::size_t radius = 1;
  std::uint64_t max_status_calls = 128;
  std::size_t max_distance_variables = 4096;
  std::size_t max_source_entries = 100000;
  std::size_t max_coordinator_work = 100000;
  std::size_t max_local_spaces = 64;
  double time_limit_seconds = 0.05;
  void validate() const;
};

struct NativeNeighborhoodOptions {
  NativeSearchOptions search;
  NativeNeighborhoodSettings neighborhood;
};

struct NativeNeighborhoodResult {
  NativeSearchResult search;
  NativeNeighborhoodStatistics neighborhood;
};

NativeNeighborhoodResult solve_native_neighborhoods(
    const ModelSnapshot&, const NativeNeighborhoodOptions& = {});
NativeNeighborhoodResult solve_native_neighborhoods(
    const Model&, const NativeNeighborhoodOptions& = {});
```

These small finite values are provisional limits for an explicit experimental
entry point, not evidence of good automatic defaults. Keep them fixed during
initial correctness checks; revisit using the benefit gate below. Zero resource
caps skip optional work. Reject unknown enums, NaN, infinity and negative local
times as option errors. Native backend availability, whole snapshot validation,
native subset support, guarantee, single-worker/seed and complete-start checks
keep the existing public ordering and behavior. `Certified` remains unsupported.
The Model overload must catch moved-from `snapshot()` errors consistently with
the other public native routes.

Only the new entry point enables the helper. Its inner `search` still supports
the current optional checked LP and BinaryReliability, but those are features
of the ordinary proof search. The neighborhood uses native propagation alone.
No `ModelSnapshot`, `GlobalPayload`, kernel/search class, C or Python ABI change
is required. C/Python exposure can follow a separately reviewed stable C++ slice.

Let B contain every active original IR slot satisfying all of:

1. Its declared type is `Binary`, and its already compiled original domain is
   exactly `{0,1}`. Fixed binaries contribute no distance and are omitted.
2. Its `indicator_origin` is absent. Exclude both live generated inactivity
   gates and retained origin-tagged gates after removal. The latter stay free
   original variables; exclusion is just a distance-selection policy, never
   permission to derive or fix their value.
3. It appears once, in increasing original slot order. Tombstones are excluded;
   owner/slot mappings come from the validated original compilation.

This is **distance over IR slots**, not a claim to discover independent semantic
decisions. Two different binary slots constrained equal count twice when both
change. A repeated argument in a global adds no slot. Frontend aliases interned
to one handle count once. Other private frontend slots have no universal origin
tag; ordinary Binary slots among them count by the same explicit rule.

Do not truncate B to meet a cap: that would silently change the neighborhood.
No eligible slots, too many slots, or a radius at least `|B|` produces a named
skip outcome. The last case would duplicate the whole original improvement
search. Pure general-integer models therefore solve normally and record
`NoEligibleBinary`; they do not become unsupported. Integer and SemiInteger
slots remain free under their original domains in a mixed model. Radius zero
is meaningful: it fixes B to the reference binary assignment while allowing
other original slots to improve.

For the frozen checked incumbent x*, post

```
d_B(x,x*) = sum(x_i : i in B, x*_i=0)
           + sum(1-x_i : i in B, x*_i=1) <= radius.
```

Equivalently, native coefficients are +1 or -1 and the upper bound is
`radius - number_of_ones`. Check all size additions, casts, coefficient-array
lengths, RHS subtraction, and worst absolute activity before native allocation
or posting. Since each participating variable is binary, the activity envelope
is at most `|B|`; use the same conservative native linear limit as ordinary
compiled rows. A representability failure skips this optional formulation with
`FormulationLimit`; it never reports original infeasibility. A malformed source
model remains a whole-solve input error even if the eventual neighborhood is
empty or skipped.

The reference objective is exact compiled integer cost c*, excluding the exact
original offset. Post native `cost < c*` for minimization or `cost > c*` for
maximization using `IRT_LE` / `IRT_GR`, matching W9a. Avoid unchecked `c*-1`,
`c*+1`, floating cutoff tolerances, or offset subtraction in double. A constant
objective or empty improvement set may immediately fail this local search;
that is only `NoImprovement`. A well-formed generated candidate that does not
strictly improve the frozen reference exposes an implementation error.

## Scheduling, ownership and candidate publication

Attempt at most once per solve. Wait for a validated incumbent, supplied by W9a
or the ordinary frontier. Select the first surviving stable parent after the
usual incumbent-bound prune, before reliability probing or `parent->choice()`.
If an incumbent is first found while expanding an ordinary parent, complete
that expansion normally and wait until the next such boundary. If all regions
are already discharged, return the ordinary completion and record
`ProofCompletedBeforeAttempt`. Never delay established global completion to
run a duplicate heuristic.

Freeze the reference incumbent vector and normalized cost for the entire
attempt. The synchronous coordinator need not duplicate the already owning
result vector just for reference access: it must refrain from mutating it until
the attempt's candidate is fully staged. Run no callbacks that permit concurrent
model/result mutation. Concurrent solves have independent coordinators,
incumbents, counters and local Spaces; no shared heuristic history is introduced.

Compile the original model once, as today, under the solve's clock/token. Reuse
that exact `Compiled` data for the optional fresh native construction. A private
constructor mode suppresses only LP actor attachment, with its current default
preserved. It must not copy/clear the shared backend, mutate its counters, or
change original rows. Native globals, indicators, SemiInteger holes, objective
equality and brancher are all posted unchanged. This avoids a second IR
compilation and stale current-node observations; it does not avoid the real
cost of reposting the native model.

Start the local clock and source/work accounting **before** eligibility scans,
source preflight, allocation, native posting and cutoff posting. Thread a narrow
private stop context through this construction path so the existing checks at
variables, rows, globals and long conversion loops also see its local deadline.
The ordinary path can use the existing budget unchanged. Check immediately
before and after each potentially long native posting call. Original compilation
already checks the shared budget across its conversion loops; test cancellation
there too. Allocation, structure validation, a global posting operation and a
native propagation fixpoint remain cooperative operations: a call may overrun
its deadline before the next check. Do not describe the time cap as a hard
preemptive limit.

Use a small coordinator-owned DFS with RAII frames containing stable local
Spaces, their owning `Choice`, and the next alternative. Obtain `choice()` only
after `status()==SS_BRANCH`. Clone the stable parent, commit the corresponding
choice on the clone, then admit/status the child. Retain parent and Choice until
all alternatives finish, or dispose of the entire local stack on a local/global
stop. Never commit a choice from a different state, retain raw Space pointers
past destruction, or call the main frontier's witness-publishing evaluator.
There is no local reliability history, second heuristic, or recursive BAB call.

At `SS_SOLVED`, stage original-slot values/mask and the exact objective, including
tombstone convention and offset. Run the existing independent exact original
checker and the public numerical validator as an additional consistency gate.
Verify the local Hamming restriction and strict reference improvement separately.
All original indicator relations and every current global payload are checked;
the numerical validator alone is not sufficient for an Exact native result.

After checking the first improvement, stop local expansion. Destroy local
Choices/Spaces, then check global time/cancellation and the local deadline once
more. Only then publish prepared values, mask and objective through nonthrowing
moves and install the main normalized scalar incumbent. Preserve
`start_submitted` as historical input-start provenance. No partially checked
candidate or late candidate is published. A fault/stop after publication retains
the new timely incumbent, just as W9a retains a timely start.

Do not route candidate validation through `prepare_start` or its full node-limit
checkpoint. An already admitted final local node may finish its exact validation
at a node quota, subject to time/cancellation; it must not be rejected as an
unadmitted start. Neighborhood witnesses increment their own accepted counter,
not ordinary `feasible_leaves` or probe counters.

## Budget contract and separate statistics

All time is part of the original solve, including common compilation, optional
native reconstruction, scans, posting, local status, validation and release.
Local `elapsed_seconds` covers the attempt from first preflight to cleanup.
Its effective deadline is the earlier of local start plus local cap and the
solve deadline. No new SolveBudget clock or cancellation token is created.

The exact node accounting identity becomes

```
shared budget nodes = frontier.admitted_nodes
                    + branching.probe_status_calls
                    + neighborhood.status_attempts.
```

Keep `branching.budget_nodes` as the existing solve-wide total for compatibility,
and document the third component for this new wrapper; expose the same total
in neighborhood statistics without inviting callers to add it twice. A status
attempt is charged before the final pre-status time/cancellation check. Thus an
admitted attempt may not execute propagation, as already happens in frontier
and reliability accounting. Report `completed_status_calls` separately. No
charge for direct exact vector checking, native construction or cutoff posting
is invented as a search node.

Optional local admissions must leave **two ordinary child admissions** available
under a finite global node quota. Before each local admission, compute remaining
with checked subtraction and require `remaining >= 3` (one local plus reserve
two). The current default brancher and BinaryReliability both use two
alternatives; assert/test that contract. A future multi-alternative brancher
must revise the reservation rather than reuse the constant. If optional work
cannot preserve the reserve, end it as `SharedNodeReserve`, then continue the
ordinary parent. Existing reliability pairs still require their own two probes
plus two ordinary children. This reservation protects admissions, not time or
the existence of two feasible children.

At actual global cancellation/time expiry, stop the whole solve with the usual
precedence (cancellation, time, then node limit). A local cap or reservation
boundary ends only the heuristic. Before every status admission check all caps,
guard counters against overflow, then increment the shared and local counters
together. After admission, status and candidate checking use time/cancellation
checks, not a fresh full node admission check. A local status cap can therefore
be reached by a final candidate-producing attempt without losing that candidate.

`max_source_entries` bounds the optional preflight/posting/validation input size.
Define entries explicitly as active variable slots, row/objective terms,
indicator terms and relation fields, and each primitive global argument/payload
cell, with checked sums. Empty structures and scalar fields still cost an entry.
Scan with checkpoints and no unbounded intermediate `global_variables()` copy.
Reject optional setup before allocating native arrays if the cap is exceeded.
Report this count as `source_entries`; it is not elapsed work or a byte estimate.

`max_coordinator_work` bounds a specified deterministic counter: charge each
eligibility/source-entry visit, distance-entry construction/check, local frame
admission/choice/alternative, and original-slot candidate extraction visit.
Check before each charged action and record the exact consumed units. Bulk
reservations must use checked arithmetic and precede the action. Native
propagator internals and whole checker algorithms are opaque to this counter;
their work is covered by elapsed time, source-size admission and status limits.
Do not claim a global instruction budget. Existing branching work and local
coordinator work remain separate; SolveBudget currently has no generic shared
work counter.

`max_local_spaces` limits resident local ancestors plus in-flight child. In
addition, queued main nodes + active main parent + every local resident Space
must fit the existing `search.max_open_nodes`. Count reservations before cloning
or construction, including the fresh local root. A local reservation refusal
produces `LocalStorageLimit` and resumes main search; an actual allocation/native
memory failure stops the solve as `MemoryLimit`. Space counts are not bytes:
global payloads/propagator state vary in size. Do not retain an extra uncounted
root template. Report local peak and total main-plus-local peak separately;
existing frontier peak retains its original main-search meaning.

Statistics include `requested`, `attempts` (at most one),
`eligible_variables`, `source_entries`, `coordinator_work`, `status_attempts`,
`completed_status_calls`, `failed_nodes`, `feasible_candidates`,
`accepted_improvements` (at most one), `peak_local_spaces`, `peak_total_spaces`,
`budget_nodes`, `elapsed_seconds`, and a completion enum. A local root
construction admission counts as an attempt even if stopped before construction
or its first status.
Eligibility scans before construction are still charged and timed. Local LP
calls are exactly zero; ordinary LP totals and probe LP subsets keep their
existing meaning.

Local completions are `NotStarted`, `NoIncumbent`,
`ProofCompletedBeforeAttempt`, `NoEligibleBinary`, `NonrestrictingRadius`,
`FormulationLimit`, `SourceLimit`, `WorkLimit`, `StatusLimit`,
`SharedNodeReserve`, `LocalStorageLimit`, `LocalTimeLimit`, `NoImprovement`,
`Improved`, and `GlobalStop`/`Error` with the outer termination reason. A zero cap
must have a deterministic applicable limit outcome, with zero solver attempts.
Set completion after cleanup and the last stop check, so a late cancellation
cannot be hidden behind `NoImprovement`. Keep operational failures distinct
from an ordinary unsuccessful neighborhood.

## Proof boundary and interruption results

Let z be original cost normalized to minimization, without offset. Before the
attempt, unresolved original regions have bounds b_1,...,b_m (including active
parent b_A) and an original feasible incumbent has value U. During local work,
retain exactly that main frontier and active-parent coverage. The neighborhood
is a subset of the original feasible set and need not lie in the current node.
Its root/child bounds, failures, exhaustion, and Hamming row never enter global
bound storage or the global cut pool.

A newly checked local witness with U' < U can replace U. The conservative global
bound remains `min(U', b_1, ..., b_m, b_A)`, with missing terms omitted only when
their original regions have actually been discharged. Its validity follows from
the old region bounds plus the feasible witness; it does not follow from a local
dual bound. Map to original sense with the original exact offset as the current
frontier does. No original region is removed because a neighborhood is exhausted.

After a successful attempt, recheck the main active bound against the new
incumbent before selecting a branch. Existing exact bound pruning may now
discharge the parent. Otherwise apply normal incumbent cutoffs to ordinary
children. A neighborhood point outside the active parent is still a valid
global incumbent and must not be rejected merely for that fact.

If a local cap is reached, discard its unresolved local stack, preserve the
main active parent, and continue proof search. If a global limit or memory
failure stops the solve, return its real termination, the last timely validated
incumbent, and the conservative bound over unchanged queued/active original
regions. A backend/checker exception uses the existing semantic-error fallback
to the initial whole-model objective box; it must not convert a local exception
into original infeasibility. No successful witness is removed merely because a
later cleanup checkpoint stops the solve.

Only ordinary frontier exhaustion/pruning may set original `Optimal` or
`Infeasible`. Local `NoImprovement`, even after exhaustive search, is never
original optimality. Keep optional search out of the ordinary success/failure
message when it never ran; add explicit requested-policy provenance for this
new API and local stats when it did.

## First implementation and correctness gates

Proposed files: new `gecode/optimize/native_neighborhoods.hpp`, private helpers
inside `native.cpp` (or one private header if that improves lifetime review),
new `test/optimize/native_neighborhoods.cpp`, and this design plus the native
search documentation. Factor only the shared witness-staging and private stop
context needed by this slice; avoid refactoring the working frontier while
adding a heuristic. The parent integration owns CMake/umbrella/install/CI and
later bindings. Register a coordinator test variant for deterministic allocation,
stop and candidate-corruption hooks; production exposes no test callback.

The acceptance oracle must enumerate the original tiny model independently,
without reading a local Space or trusting the production validator's answer.
Enumerate all feasible assignments, original objectives, exact Hamming distances,
and the restricted improvement set. For every limited run assert a reported
incumbent belongs to the original set; for minimization `best_bound <= optimum
<= incumbent`, reversing inequalities for maximization. If no incumbent exists,
still check the correct global-bound side. Absence of a bound must follow the
established compile/setup rules, not erase evidence after a local failure.

Required fixtures and fault gates:

1. Min/max, positive/negative costs, nonzero and extreme exact offsets, constant
   objective, poor and already optimal external starts, first ordinary incumbent,
   and no-incumbent/no-surviving-frontier paths. An improvement outside the
   active main node is mandatory: freeze a node whose binary restriction
   excludes the unique global improvement, and verify its acceptance without
   dropping that node or any sibling.
2. Radius 0, 1, `|B|-1`, `|B|`, no B, fixed binaries, mixed general integers,
   SemiInteger zero/hole, negative integer values, tombstones, foreign handles,
   moved Models and publicly corrupted snapshots. Two equality-linked Binary
   slots require distance two; repeated handles in globals count once. Live
   gates are excluded from distance but checked, and a removed retained gate
   stays an unconstrained/user-constrained original variable, never inferred.
3. Native indicators for both activation values, ranged/constant rows and every
   global payload: AllDifferent, Element, Circuit (offset/singleton), Table
   (including hole encodings), Cumulative (aliases/zero durations/half-open),
   Regular (empty/aliased words and dead transitions). Use source-level truth
   tables/event/transition oracles. Include cases where a linear relaxation
   suggests a better assignment that the original global rejects.
4. Exact distance coefficient/activity limits and checked size counter overflow,
   including pure arithmetic boundary tests without billion-element allocations.
   Optional representation caps skip safely; unsupported original fractional or
   overflow models remain Unsupported before any early neighborhood shortcut.
5. Local status caps 0/1/2 and final-admitted witness, global quotas around the
   two-slot reserve, with/without BinaryReliability and checked LP/root covers.
   Assert the disjoint node identity at every fault hook, no LP calls from the
   local Space, and independent work/space peaks. Local cap exhaustion must
   resume ordinary proof; global exhaustion must stop it honestly.
6. Deterministic cancellation/time and allocation faults before/during common
   compilation, preflight, fresh native construction, distance/cutoff posting,
   root status, choice/clone/commit, extraction, original checking, local cleanup,
   immediately before publication and after publication. Inject a bad candidate
   and assert BackendError plus conservative original bound, not an accepted
   rounded witness. A validation or cleanup finishing after stop must not publish
   a staged improvement; an earlier accepted one survives.
7. Enumerate quota/fault positions for both frontier orders, multiple pending
   siblings and a partially expanded parent. Compare every interrupted bound to
   the independent full optimum. Repeat concurrent independent solves and
   check that source snapshots, previously returned results and optional shared
   LP evidence have not changed.
8. Existing ordinary Native/BAB, NativeLP, complete starts, frontier, branching,
   original globals and disabled-backend tests remain green. With the new route
   disabled, compare the existing deterministic admission trace and outcomes.
   Run native-only, combined Native+HiGHS, and full-source ASan/UBSan variants
   with matching generated headers/libraries; no mixed instrumented ABI inputs.

No broad timing run belongs to this implementation gate. First prove a fixture
where the attempt improves a feasible incumbent within a known small admission
cap, and one where it adds overhead without improving. These establish behavior,
not an out-of-box speedup.

## Benefit gate and later W9 work

After correctness, compare baseline frontier to the explicit wrapper under the
same external wall budget and shared status budget, with all compilation,
reposting, validation and release included. Use paired repeats with a frozen
configuration and separate held-out families: binary covering/packing,
assignment/network, mixed bounded-integer and native global scheduling models.
Report attempted/skipped/failed neighborhoods, full setup cost, validated
improvements, time to fixed target quality, objective trajectory, proof
completions, valid global-bound trajectory, memory/space peak and per-family
regressions. Use a defined normalized primal integral only where references
support it; never average unrelated raw objectives.

Separate cold runs from runs given the same external incumbent. This first
heuristic waits for an incumbent, so it cannot improve time to first feasible
solution in a cold run; any additional scan/setup overhead before that event
must be negligible and measured. Its cold-run claim can only concern subsequent
incumbent quality. Preserve the roadmap's first-feasible requirement as unfinished
W9 work. Automatic enabling needs held-out, end-to-end benefit without material
tail regressions; a few hand-picked successful neighborhoods do not establish
that condition. No performance threshold or automatic default is asserted here.

Next compare LP-free variable-release LNS on bounded general integers. Choose
and report a deterministic released set, fix only its complement to a checked
incumbent on a fresh original Space, and reuse this same isolation/publication
controller. Treat each alternative release rule as an explicit experiment.

Before RINS/RENS or LP-guided diving, add an owning observation containing
original/compiled model identity, node identity, exact domain snapshot, column
mapping, relaxation provenance/status, copied finite primal values and the
objective/cutoff state that produced them. Never read “the last LP solution”
from a sibling-shared backend. Numerical equality/rounding may select a
restricted search, but supplies no primal witness or global proof. RENS must
intersect floor/ceiling proposals with exact original/current domains, including
SemiInteger holes; RINS must state whether it restricts a current node or the
whole original model. Only exact original checking can publish a candidate.

Keep repair of partial starts, controlled dives, several neighborhoods/radii,
adaptive rewards and restart schedules as separate later slices. Measure a
deterministic baseline first; then consider cost-aware scheduling with explicit
reset per solve and fixed held-out evaluation. None of these neighborhoods may
promote restricted infeasibility, a numerical bound, or a local cut into a
global proof. The W10 explanation/LCG requirement is unaffected.

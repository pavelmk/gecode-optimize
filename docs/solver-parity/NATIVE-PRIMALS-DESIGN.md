# W9: native starts and a bounded primal portfolio

Status: W9a complete exact starts are implemented; later partial completion and
portfolio sections remain research/design. The design inspected integration
head `a067cebe9878a6cd9ef25c9982e814851dd25642` on 2026-09-05; implementation is
based on `8ae59d5c1`. See [NATIVE.md](NATIVE.md#complete-native-starts) for the
implemented contract. No cold-start or performance improvement is claimed.

The first slice should accept **one complete, exactly feasible original-model
start**, retain it as an incumbent, and search the unchanged native problem for
strict improvements. Use the existing `SolveOptions::primal_start` on ordinary
Native/BAB, NativeLP and the explicit frontier. It needs no new search engine,
LP solve, brancher, model mutation, or feasibility subsearch. Keep partial
completion and a bounded heuristic portfolio as separate subsequent slices.

This provides immediate practical value for repeat solves and application
solutions. It does not establish cold-start improvement: supplied solutions
must not be counted as solutions found by a new heuristic. Automatic heuristic
work should remain absent until its development and held-out benefit gates pass.

## Baseline before W9a and the missing seam

| Current source | Relevant behavior | Consequence for W9 |
|---|---|---|
| [`result.hpp`](../../gecode/optimize/result.hpp), `StartValue`, `SolveOptions`, `SolveResult` | A sparse owning list of handles/values; complete starts must be feasible; partial values are hints. `start_submitted` means acceptance, while `solution_validated` establishes an incumbent. Results retain model identity/revision and original slots. | Reuse this input and result contract. No second native start API or shared result ABI extension is needed for W9a. |
| [`native.cpp`](../../gecode/optimize/native.cpp), `compile`, `check_exact` | Full mutable-snapshot structure validation, conservative integral/activity/range preflight, exact original rows/indicators/globals/objective checking. Candidate checks also call the public numerical validator. | Run full compile preflight before invoking arithmetic whose safety depends on it. Reuse the exact checker for starts, with an explicit input-error category. |
| `NativeSpace`, `solve_native_impl` in the same file | Original native constraints, objective equality, optional checked LP actor and built-in brancher. BAB returns improving leaves; `constrain()` posts strict original-sense cost improvement. Every nonempty start returned `Unsupported` before W9a. | Add one staged incumbent before search and a strict cost restriction on the otherwise unfixed root. BAB/NativeLP share this implementation. |
| `native_frontier_impl` | Exact propagated bounds; active parent retained while all children are processed; normalized min/max bound aggregation; original witness publication. Nonempty starts returned `Unsupported` before W9a. | Seed its existing scalar incumbent and owning result, preserving the whole original region through setup and interruption. |
| [`search.hh`](../../gecode/search.hh), `Search::Base`; [`seq/bab.hpp`](../../gecode/search/seq/bab.hpp) | Low-level `Engine::constrain()` exists, but the typed `BAB<T>`/`Base<T>` wrapper does not expose it. Sequential BAB can retain an external best Space internally. | Do not add kernel/search API merely to insert a start. Root cost restriction plus an externally owned incumbent is simpler. |
| [`lp-relaxation.hpp`](../../gecode/minimodel/lp-relaxation.hpp), `IntegerBoundPropagator`; [`lp-backend.hpp`](../../gecode/minimodel/lp-backend.hpp) | Actors retain checked residual certificates. A backend call can optionally copy a numerical primal suggestion, but the actor currently does not request/expose a node observation. Shared workspace bounds/basis change between siblings. | Complete starts need no LP observation. Diving/RINS requires a new owning, node-attributed observation seam; reading the workspace's last solution is insufficient. |
| [`solve.cpp`](../../gecode/optimize/solve.cpp), `prepare_start`, `SolveSession` | HiGHS validates/submits sparse starts; numerical tolerance policy differs. Persistent Native sessions are explicitly unsupported. | Do not quietly reuse tolerance-rounded HiGHS preprocessing or claim that native start support adds tree/basis/session persistence. |

Compile currently makes exact sums safe by bounding integral coefficient,
domain, activity and objective ranges. The native start checker must not be
called as an unrestricted public validator on arbitrary doubles or uncompiled
snapshots. Native `status()`/BAB recomputation remains cooperative work that
cannot be interrupted internally. W9 must preserve this limitation honestly.

## Research and the choices it supports

Commercial APIs distinguish candidate starts, completion/repair effort and
search preferences. Gurobi exposes partial `Start` and separate `VarHintVal` /
`VarHintPri`; CPLEX distinguishes feasibility checking, solving a fixed problem,
sub-MIP completion and repair. Our W9a corresponds to a checked complete start,
with exact native semantics; it does not duplicate all these policies. Do not
introduce a no-check mode. [Gurobi variable attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#start),
[CPLEX 22.1.2 start effort](https://www.ibm.com/docs/en/cofz/22.1.2?topic=mip-starting-from-solution-starts)

Danna, Rothberg and Le Pape's RINS uses relaxation information to construct an
incumbent neighborhood, then searches a subproblem. The paper also distinguishes
guided dives. This motivates separate construction and improvement phases;
RINS cannot supply the first feasible point without an incumbent. The accessible
publisher abstract was inspected; detailed engineering below is grounded in
SCIP source and our own contracts, not a claim to have read the paywalled full
paper. [Paper, Mathematical Programming 102 (2005)](https://link.springer.com/article/10.1007/s10107-004-0518-7)

SCIP's `heur_rins.c` checks for a current optimal LP and an incumbent, computes
fixings, creates a separate mapped problem, copies limits and imposes a bounded
subproblem node allowance. Its setup-cost and success accounting is a useful
engineering checklist, not a source of constants to copy. Inspect
`determineFixings`, `wrapperRins` and `heurExecRins`. The current documentation
source was readable through search; versioned 7.0.2 source gives a stable
historical comparison. No SCIP code is copied by this design.
[Current implementation](https://www.scipopt.org/doc/html/heur__rins_8c_source.php),
[versioned implementation](https://scipopt.org/doc-7.0.2/html/heur__rins_8c_source.php)

SCIP's generic diving separates candidate scoring from a controller that owns
an auxiliary search path and controls LP resolve frequency. Reuse that
separation of responsibilities with native clones; do not embed a nested solve
inside a value-selection callback. [SCIP diving design](https://www.scipopt.org/doc-3.2.0/html/DIVINGHEUR.php),
[current controller API](https://www.scipopt.org/doc/html/group__PublicSpecialHeuristicMethods.php)

Shaw's CP neighborhood search removes decisions and repairs the remaining
subproblem using constraint search. Fischetti and Lodi's local branching controls
neighborhoods with distance constraints. Both fit Gecode's ability to preserve
native global constraints on clones. The neighborhood restriction itself is
not globally valid; retaining the complement is required if it is used for
proof search. Our initial heuristic design retains the ordinary frontier
instead. [Shaw, CP98](https://doi.org/10.1007/3-540-49481-2_30),
[Local branching (2003)](https://link.springer.com/article/10.1007/s10107-003-0395-5)

Berthold's RENS constructs a rounding neighborhood without requiring an
incumbent, so it is a relevant cold-start comparison. Feasibility pump alternates
relaxation projection and rounding, introducing objective/basis/cycling
machinery that is unnecessary for W9a and premature before node observations.
Evaluate these after a simple bounded native dive and repair baseline.
[RENS, author thesis Chapter 7](https://www.zib.de/userpage/berthold/Berthold2014.pdf),
[Feasibility pump, original publication](https://cris.unibo.it/handle/11585/17405)

Hendel's ALNS framework selects neighborhoods with bandit methods and accounts
for expensive unsuccessful calls. The current SCIP ALNS implementation separates
neighborhood construction, effort limits and reward. This supports a later
cost-aware scheduler; a deterministic fixed schedule is the auditable starting
point. Learn only after per-heuristic measurements exist, with reset per solve
and frozen held-out evaluation. [Author report](https://www.zib.de/userpage/hendel/publication/adaptive-large-neighborhood-search-for-mixed-integer-programming/),
[SCIP ALNS implementation](https://www.scipopt.org/doc/html/heur__alns_8c.php)

## W9a: exact complete-start contract

Use `options.primal_start = {{x, 2}, {y, 0}, ...}` with the existing Native
backend selection, or the nested `solve` member of NativeLP/NativeSearch options.
Absence preserves the exact current route. No automatic native start is inferred
from a previous result or an unrelated session.

A complete start must determine exactly one value for **every active
ModelSnapshot variable slot**. Callers supply the ordinary variables; the
native adapter may fill a missing **live indicator inactivity gate** from its
validated logical definition. Fixed/private variables with no such definition
still need an entry. Inactive tombstones need none and cannot be supplied.

For active indicator metadata, its exact relation is
`gate = (activator == active_value ? 0 : 1)`. Once the activator is known,
fill a missing gate or check that an explicitly supplied gate agrees. Only a
validated, active indicator can authorize this derivation. A retained gate
from a removed indicator may now be free or user-constrained: its historical
`indicator_origin` tag does not authorize any value. It needs an explicit entry
like any other active variable.

Use a bounded forward queue keyed by known variable slots so gate-as-activator
chains work regardless of metadata order. Visit each dependency once; the
unique gate ownership established by structural validation bounds storage and
work. Do not solve equations backward to infer a user activator or choose a
value in an unseeded cycle. Unresolved slots make the start incomplete. This is
deterministic semantic completion, not a search/repair heuristic.

The C indicator call returns `has_gate`/`gate`, and Python returns an
`Indicator` carrying `inactive_gate`; callers can supply those handles explicitly,
but ordinary complete starts need not know live derived gates. Derived values
still occupy the owning result's original model slots and pass all original
checks. A list of FlatZinc source outputs can remain incomplete because of
other private variables: a future source helper needs the owned compiler
mapping, rather than guessing them.

Processing order and outcomes:

1. Validate options, full snapshot structure, backend/guarantee support and
   native subset preconditions. Unsupported fractional models, continuous
   variables, overflow or `Certified` remain unsupported even if a submitted
   assignment happens to satisfy some rows. Keep unavailable-backend precedence.
2. Under the same solve clock/token, map entries by original owner-aware handle.
   Reject foreign/deleted/out-of-range handles, duplicates, nonfinite values,
   nonintegral values and exact domain violations as `InvalidModel` input errors.
   A valid SemiInteger zero alternative is allowed; its forbidden hole is not.
   A value such as `1 - 1e-12` is not one, even for a `Numerical` native request.
3. Complete/check only the live indicator gates as above. If nonempty input
   still leaves an active slot unresolved, return `Unsupported` with an
   actionable complete-start requirement. Do not silently discard it, fix it,
   or perform completion in W9a. Malformed supplied entries remain input errors.
4. Independently check original ordinary/ranged rows, original indicator
   activation and its gate relation, every global payload, domains and original
   objective. Skip lowered indicator rows only in the exact original checker;
   retain the existing second public validator as an additional consistency
   gate. Any disagreement with a well-formed complete input is reported,
   never rounded away. Report which start condition failed where practical.
5. Stage owning original-slot values, active mask, exact original objective and
   native cost in temporaries. Compute cost by checked subtraction of the exact
   offset; require it within compiled cost limits. Check cancellation/deadline
   after all checks and allocating work. Publish all incumbent fields and
   `start_submitted=true` together with nonthrowing moves/scalar assignments.
6. Retain this witness through later setup, LP preparation, search and cleanup.
   A later limit or operational error changes termination, not its historical
   exact feasibility. Never replace it with a worse/tied candidate merely
   because the candidate arrived later. Any improvement is validated afresh.

`check_exact` currently throws generic runtime errors for bad solver witnesses.
Refactor its failure reporting narrowly so an invalid user assignment becomes
`InvalidModel`, while a bad solver-produced candidate remains `BackendError`.
Do not catch all exceptions around validation and relabel allocation, indexing
bugs or backend failures as user errors. No changes to the proven arithmetic
range preconditions are required.

An empty `primal_start` means absent, including zero-active-variable models.
There is no new explicit empty-start representation. Such models follow the
existing ordinary constant/empty-model solve behavior.

### Strict cutoff and ownership for all three routes

Let `c(x)` be the compiled integer cost without the original offset `o`; let
`u` be the start's compiled cost. Post `c < u` for minimization or `c > u` for
maximization on the **unfixed original root**, after incumbent publication and
before its first search propagation. Use native `IRT_LE` / `IRT_GR`, matching
`NativeSpace::constrain()`. Avoid unchecked `u-1`, `u+1`, subtracting an offset
in double, or posting a floating objective cutoff. Native limit endpoints and
constant objectives need explicit tests.

For BAB, retain the validated start outside the engine. A fresh root already
restricted to strict improvement is sufficient: its clones/recomputation retain
the restriction, and subsequent engine incumbents tighten it normally. An
exhausted improvement tree with a retained start returns `Optimal`, the retained
objective as `best_bound`, and zero gaps. It never returns original-model
`Infeasible`. If interrupted, return the retained witness with the actual limit;
ordinary BAB still has no finite interrupted global bound. An accepted start
alone is never a lower bound or a proof of optimality.

Do not build a completely fixed candidate Space simply to feed the low-level
BAB `constrain()` entry point. That would add propagation/node-accounting and
ownership complexity and could invoke LP work just to verify an already exact
assignment. The direct original checker plus cost-only root restriction is the
first implementation choice. No `search.hh` or native kernel changes are needed.

For NativeLP, perform pure option/capability checks first, then validate/publish
the start before expensive optional root-cover/backend preparation. The checked
LP actor sees the strict objective domain on the native root and can use its
existing exact residual filtering. Root covers remain derived solely from the
original global rows/domains. Do not put the incumbent restriction into a cut's
global source model, cache cutoff-dependent reductions across looser solves,
or promote any floating LP infeasibility report. Root LP setup failure after
publication may leave a valid start alongside the honest failure status.

For the frontier, set its normalized incumbent to `u` for minimization and `-u`
for maximization, while keeping `initial_bound`/`active_bound` for the entire
original region alive through all setup and root-evaluation failure points.
The start does not count as a feasible search leaf, admitted node or reliability
probe. Child incumbent cutoffs and bound pruning then use the existing route.
No queued region is removed merely because the start is present.

Write normalized objective `z=c` for minimization or `z=-c` for maximization and
normalized incumbent `U`. Search region `R` satisfies `z<U`; all excluded points
have `z>=U`. Therefore a bound for the original problem is
`min(U, bounds of all unresolved regions in R)`. When R is exhausted it is U.
Map this back using `o+z` for minimization and `o-z` for maximization. The start
is a primal witness in this formula; it does not authorize replacing a missing
active-region bound with U. On semantic failure retain the existing conservative
initial-bound fallback. Model/revision and original values remain unchanged.

### Budget and publication boundaries

Keep the current early checkpoint: zero time, pre-cancelled token or zero node
quota returns that limit without processing/publishing a start. W9a does not
introduce a special free-validation mode under an already expired solve. With
a positive remaining node quota, exact vector checking consumes elapsed time
and memory but **no search node**, because it performs no `status()` call.

Checkpoint entry scans and row/global boundaries, and recheck after a potentially
expensive whole-global validation. Exact and numerical validation, allocations,
LP setup, native construction, propagation and release all use one solve budget.
There is no hard instruction limit inside a global checker or native propagation.
A late candidate is not published; an earlier timely incumbent survives. Check
again after resource release before return, preserving cancellation-over-time
precedence. Applying a cutoff is not a proof-producing free search admission.

Preserve each engine's existing node-limit contract. Frontier admits/charges
nodes and allows the final admitted propagation to finish under time/cancel;
BAB uses its existing statistics/stop observer and may conservatively report a
limit even if a final call found evidence. Do not accidentally homogenize these
contracts or add an uncounted validation search as part of start support.

All start state is solve-local and owning. No mutable user vector, raw Space,
reference to a transient compiled column map, or workspace pointer is retained.
Reusing a result after edits requires a new complete start and full validation
against the new snapshot, including its changed objective. Concurrent independent
solves may consume the same immutable snapshot/start data; cloning a single
Space concurrently remains forbidden.

## Subsequent partial starts and primal construction

Partial-start **preferences** choose where to search first; they do not shrink
the main feasible set. A later explicit completion mode can impose supplied
values on an isolated completion clone under a small shared subbudget. Failure
of that clone says nothing about original infeasibility and must return to
ordinary search. Repair is different again: it may release or change supplied
values, so successful repair need not respect every hint. Report submitted,
completed, repaired, accepted and rejected separately when those modes exist.

Do not overload W9a's error policy: a complete infeasible start is an input error
there. A future request for repair must explicitly select a repair policy with
its own nonfatal `NoCandidate` outcome. If preference-based branching is added,
its alternatives must still cover the actual native domain, including holes.
A hint disappearing after propagation is simply unavailable guidance.

### Required node LP observation seam

Add this only in a later reviewed slice. A retained observation should own:

- source model identity/revision, sparse column-to-original-slot mapping and
  the exact immutable augmented LP model/cut attribution;
- a node/region identity plus the actual variable intervals supplied to the LP,
  objective sense/offset mapping, and observation sequence;
- copied finite primal suggestions, shape/status diagnostics and work counters;
- the cutoff context and whether the point predates further domain changes.

The shared serialized backend's last point may belong to a sibling, probe or
previous solve. Request/copy values in the call that owns the complete input
box; never fetch them later from a mutable global `Highs` solution. A node's
interval box can include SemiInteger holes or other CP-forbidden values. The
point is only guidance. Check chosen values against current native domains;
intersect restrictions with those domains. Stale/missing/NaN data means skip or
refresh within budget, never pruning. A root-cover selection vector is not a
current-node observation. Numerical LP success is not an exact integer witness.

Initially prefer a coordinator-requested bounded observation at a stable node
on a separate heuristic backend/workspace. This may duplicate one LP solve but
makes model/region and accounting explicit. Only optimize to actor-published
immutable observations after clone ownership, invalidation and no-default-cost
tests pass. Existing proof certificates and main workspace need no mutation.

### Bounded portfolio order

| Phase | First scoped experiment | Preconditions and termination | What may cross back |
|---|---|---|---|
| Construction | Deterministic native dive, prefer valid rounded current-LP values or a simple objective/domain rule | Stable node clone; cap depth, candidate scans, status attempts, optional LP calls and one backtrack. Preserve every native global. | Only a newly exact-checked complete original witness. |
| Repair/completion | Bounded DFS on an isolated clone with a selected subset fixed or preferred | Owning requested subset; shrink/release fixings explicitly; stop at subbudget. No recursive portfolio. | Validated witness, never a restricted-problem bound. |
| Cold-start alternative | RENS-style neighborhood around current LP: intersect domains with floor/ceil interval | No incumbent needed; checked floor/ceil conversion, domain-hole intersections and whole original checker. Empty neighborhood is harmless failure. | Validated witness. |
| Improvement | RINS-style agreement neighborhood | Requires incumbent and fresh current-node LP. Fix selected integer variables that numerically agree, using exact incumbent integers; restrict an isolated clone only. | Strictly improved exact witness; agreement is heuristic, not proof. |
| Improvement | Binary local branching / CP LNS | Incumbent required. Binary Hamming ball or selected domain fixings; general integer distances deferred unless arithmetic/modeling is proved. | Improved witness; no local restriction or failure promoted globally. |
| Later scheduling | Adaptive selection among measured successful operators | Deterministic baseline first, isolated per-solve statistics, bounded setup cost and stalled-call limits. | Scheduling preferences, never proof strength. |

For binary incumbent `x*`, a local-branching neighborhood is
`sum(x[j] for x*[j]=0) + sum(1-x[j] for x*[j]=1) <= k` over explicitly selected
original binary variables. Validate k and checked activity/count arithmetic;
exclude generated gates from selection. If k=0 it may contain only the incumbent
on selected variables; exhaustion under strict improvement is only a failed
neighborhood. Nonbinary variables are not silently treated as binary distances.

A node-local clone contains original constraints plus node restrictions. A
global neighborhood rebuilt from the immutable original snapshot contains
original constraints plus declared neighborhood restrictions; it must not
inherit local proof cuts or stale objective-dependent deductions. Choose and
record one scope. An incumbent can lie outside a current node, so incompatible
RINS fixings on a node clone merely make that neighborhood empty. Do not relax
node domains secretly to include it. Never delete globals, indicators or gates
to make a heuristic subproblem easier.

While a heuristic executes, the ordinary active parent remains represented in
the frontier; the heuristic never discharges it or its siblings. A returned
solution can improve the global incumbent even if produced in another owned
original-model neighborhood, after complete validation. Freeze the reference
incumbent during each call for reproducible construction/reward; publish an
improvement only after it finishes. Later ordinary children receive the latest
strict cutoff. Probe-only BinaryReliability remains probe-only; do not start
publishing its solved clones as an incidental shortcut.

### Portfolio budgets and provenance

Use a shared `SolveBudget` with nested **caps**, not restarted independent solve
clocks or recursive public solve calls. Separate total heuristic status attempts,
per-call node/status caps, depth, candidate/term scans, LP calls/iterations,
resident clone/storage limits and stalled-call limits. Before optional work,
reserve room for ordinary search progress as BinaryReliability does. Charge
all actual/admitted propagation attempts once, alongside ordinary admissions
and reliability probes. Report the disjoint accounting identity explicitly;
LP heuristic calls are subsets of the solve total, never added a second time.

Outer time/cancellation stops end the solve. A local heuristic quota, missing
observation or an empty neighborhood ends that heuristic with a distinct outcome
and resumes ordinary search. Allocation/backend/checker faults retain earlier
incumbents and conservative frontier coverage but return the honest operational
failure; they must not masquerade as a successful heuristic or completed solve.
Destroy clones and owned subproblem state within the same deadline. Bound
construction/storage before allocation where possible; a work counter cannot
claim to bound arbitrary native propagation or LP internals.

Initial scheduling should be explicit opt-in with zero overhead when absent:
one bounded construction attempt near the root, then ordinary search; only
with an incumbent and after a measured stall, try a bounded improvement
neighborhood. Caps/frequencies are experimental settings selected on development
instances and frozen before held-out testing. Do not copy SCIP's default node
percentages into Gecode or advertise adaptive learning before enough comparable
per-call data exist. Normalize reward by real effort, include failed calls,
and never use unavailable/invalid gaps as zero loss.

## First implementation slice and acceptance gates

W9a source scope: `gecode/optimize/native.cpp`, a new
`test/optimize/native_starts.cpp`, and the Native/NativeLP/NativeSearch documentation.
Update capability limitations and existing start-unsupported assertions. A small
private prepared-incumbent helper can serve BAB and frontier. Root registration
adds standard/coordinator tests; no model, LP, C API, search/kernel or public
result layout changes should be needed. C/Python ordinary Native calls already
carry the common start vector, so add thin integration cases to their existing
tests when the component is integrated. NativeLP/frontier bindings are a separate
capability, not implied by the common C API.

The same independent finite-product original-semantics oracle used for native
branching should enumerate every feasible start on small models and test poor,
best and tied starts. It must not compute expected feasibility with the production
validator. Require all three routes (LP where available), both senses, signed
coefficients/offsets, empty/constant objectives, feasible/infeasible models,
Integer/Binary/SemiInteger holes, sparse/tombstone slots, aliases, reified
indicators and every native global. Test implicit and explicit live gates,
wrong explicit gates, reversed metadata ordering, chained gates, unresolved
cycles, and removal followed by reuse of the retained gate with a different
value. Missing retained gates or unrelated private slots must remain incomplete.
Include C/Python starts containing ordinary user variables but omitting their
live generated gate; they must be accepted after deterministic completion.

Every returned witness must equal a feasible original assignment and have the
exact original objective; every `Optimal` must equal the oracle optimum. At
every node quota and resident cap, compare finite frontier bounds with that
optimum and the retained incumbent; ordinary BAB must not invent interrupted
bounds. Specifically test strict-root failure with a feasible start (optimal,
never infeasible), better solutions outside the start assignment, max negation,
integer limit endpoints, and objective-only edits invalidating old scalar costs.

Fault hooks should cover entry mapping, each validation phase, after staged
validation but before publication, after publication, before/after cutoff,
LP/root-cover preparation, root allocation/status, first candidate, child
admission/enqueue and final release. Inject cancellation/time and allocation/
backend errors; late inputs never publish, timely incumbents survive, identity
and active-parent coverage remain correct. Include zero limits, pre-cancel,
invalid handles/duplicates/fractional near-integers, out-of-domain zero/holes,
mutated snapshots, disabled backends, unsupported guarantees and concurrent
independent solves. No-start cases must retain previous answers, admission
counts and LP-call behavior.

Run assertion-enabled core, Native-only, combined Native+HiGHS and complete
matching-source ASan/UBSan configurations. Keep generated config, native archives,
modified adapter and HiGHS instrumented consistently. Use production and
coordinator-hook variants; fault-hook code is excluded from production. Then
run existing native/global/LP/frontier/branching regressions and installed consumer
checks. These are proposed checks, not results of this documentation task.

## Benefit evaluation and decisions about defaults

Separate the following experiments and include all setup/validation time:

1. **Explicit complete-start utility:** same models with no start, a modest
   independently generated feasible start, and a high-quality start. Measure
   start validation cost, time/node work to strict improvement, optimality proof,
   and interrupted retained quality. Include failed starts as API error cases,
   not as performance wins. Record how each external start was obtained.
2. **Cold-start construction:** no external incumbent, previous session or hidden
   benchmark solution. Compare native baseline, a simple bounded dive, repair,
   then RENS/other operators separately. Measure feasible-solution rate and time
   to first exact-validated solution, time to target objective, objective
   trajectory, total time/memory and ordinary proof progress displaced.
3. **Warm improvement:** fixed independently obtained incumbent, matched total
   budgets; compare each RINS/LNS operator and the fixed schedule before an
   adaptive scheduler. Account for neighborhood setup, failed calls and LP
   refreshes. No bound or optimum from a neighborhood counts as a global result.

Use exhaustive synthetic fixtures for semantic gates, the existing FAST suite
for regression/integration, and isolated broader family benchmarks for benefit.
Report compatible-subset exclusions rather than silently dropping hard models.
Keep warm-start experiments distinct from the earlier completed benchmark
ledger. Build and benchmark phases must not overlap; freeze executable/config/
seed and development-selected settings before paired held-out runs. Report
per-family results and timeout/unknown handling, not averages of unrelated raw
objectives. Use primal integrals only with an explicit normalized definition
and reference-quality data; missing first solutions remain failures/censored
observations, never zero time or zero gap.

Before the held-out run, preregister family weights, time caps, exclusions and
an allowed regression margin. Use paired instances with several deterministic
seed/configuration replications where applicable. Report first-feasible success
separately from a capped time metric (for example PAR-2: a run without a timely
validated solution costs twice its time cap), so dropping failures cannot make
an operator look fast. Require a positive held-out improvement with a paired
uncertainty interval, no increase in invalid outputs, and no family/proof-progress
regression beyond that preregistered margin. A speedup on successful runs alone
or a pooled average hiding a family failure does not pass. Do not pick the
margin or family weights after seeing held-out outcomes.

W9a can become the ordinary behavior for an explicitly provided supported
complete start after correctness gates pass; it adds no automatic work for
users who provide none. An automatic portfolio requires repeatable cold-start
benefits across held-out compatible families, no invalid witness/bound, bounded
worst-case overhead and an acceptable per-family regression profile. If those
gates fail, keep it explicit or remove the unhelpful operator. W9 remains partial
until cold-start and improvement scheduling, partial completion, ownership and
budget contracts are implemented and measured; start acceptance alone does not
close the commercial primal-heuristic capability gap.

Independent design review found no mathematical or lifecycle blocker in the
live-gate completion, publication/cutoff, frontier-bound or neighborhood-scope
contracts. The subsequent implementation received an independent read-only
review with no concrete blocker. Validation results are recorded in the
implemented Native documentation.

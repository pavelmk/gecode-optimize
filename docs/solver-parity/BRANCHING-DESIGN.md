# W8: budgeted native reliability branching design

Status: the bounded W8a slice is implemented as an explicit optional policy;
the remaining sections retain the design rationale and W8b research boundary.
It was designed against native frontier commit `73ff282b9`. See
[NATIVE-SEARCH.md](NATIVE-SEARCH.md#optional-binary-reliability) for the implemented
API, validation and precise accounting. Solver defaults remain unchanged.

The implemented first slice is an explicit, bounded **binary
propagation-gain reliability policy in the frontier coordinator**. Probe full
native clones, learn directional bound gains, and use the results only to select
a variable. Preserve the built-in brancher as fallback. This establishes the
budget and lifecycle machinery before introducing classical LP-displacement
pseudocosts for general integer variables. It does not complete all of W8 or
claim equivalence to commercial solver branching.

## Current implementation and constraints

[`NativeSpace`](../../gecode/optimize/native.cpp) constructs compact integer
variables, semi-integer holes, ordinary rows, reified original indicators,
native globals, objective equality and an optional checked LP actor. It finally
posts `INT_VAR_SIZE_MIN()` / `INT_VAL_MIN()`. Its copy constructor delegates to
`Space(other)` and updates both variable and cost handles; clones retain all
propagators and the LP actor's owning backend/certificate state.

The explicit frontier in the same file owns stable Spaces. `evaluate()` charges
a node admission, calls `status()`, reads the propagated integer cost bound,
and checks every incumbent against the original snapshot before publication.
An expanding parent remains in `active_bound` until every child has been
evaluated and either discharged or enqueued. Interrupted bounds aggregate the
incumbent, every queued region and this active parent. Maximization uses a
negated internal bound; the original offset is added only at the public boundary.

There is currently no candidate callback, pseudocost table, per-node LP primal
point, probe accounting or way to interrupt the inside of `Space::status()`.
The LP actor's propagated integer bound is valid evidence; a root-cover-loop
primal suggestion is an old heuristic vector and is not a current-node point.
An optional LP actor may run during a probe, including verified global root
covers. Its raw floating status or objective must not become pruning evidence.

The kernel's [`Choice`/`Brancher` contract](../../gecode/kernel/core.hpp) requires
a stable preceding status and at most one `choice()` per decision; a later
choice invalidates older choices on that Space. `clone()` is logically const
but temporarily updates forwarding pointers. Probing must therefore be
sequential and must never interleave concurrent clones of the same parent.

## Research and how it applies

Achterberg, Koch and Martin's *Branching Rules Revisited* defines directional
pseudocosts as observed objective gain divided by branch displacement from the
LP point. Reliability requires enough observations in both directions;
unreliable variables receive bounded strong-branching evaluations, stopped
after a limited run without an improved score. This motivates count-based
initialization and lookahead caps, but native propagated integer gains are a
different observation from solved LP gains. [Paper, §§2.2–2.6](https://webdoc.sub.gwdg.de/ebook/serien/ah/reports/zib/zib2004/paperweb/reports/ZR-04-13.pdf)

Gamrath's *Improving Strong Branching by Domain Propagation* evaluates
propagation inside tentative branches before LP evaluation. This is directly
relevant because our native globals can reveal consequences absent from the
ordinary linear relaxation. Its computational results do not establish a
benefit for this implementation; we must measure cloning, propagation and LP
cost together. [Paper](https://webdoc.sub.gwdg.de/ebook/serien/ah/ZIB/ZR-13-47rev.pdf)

SCIP's versioned implementation keeps directional counts, caps candidate and
LP-iteration effort, distinguishes infeasible directions from finite samples,
and can reduce strong-branching effort under degeneracy. Iteration-limited
samples have explicit policy controls. Inspect `needsStrongBranching`,
`continueStrongBranchingLookahead`, and the update section of `execRelpscost`;
do not transplant SCIP's richer LP/conflict statistics into fields we cannot
measure. [SCIP 10.0.0 source](https://scipopt.org/doc-10.0.0/html/branch__relpscost_8c_source.php)

The current upstream release source adds discounted/ancestor histories and
tree-size lookahead machinery. Those are later experiments, not prerequisites
for a first bounded policy. Version-pin comparisons rather than relying on a
moving `master` or copying default constants. [SCIP v10.0.2 source](https://raw.githubusercontent.com/scipopt/scip/v10.0.2/src/scip/branch_relpscost.c)

Our decisions below are a proposed Gecode design, not claims that these sources
implement the same native algorithm. No proprietary source is used or copied.

## Coordinator split versus a custom brancher

| Choice | Advantages | Additional obligations | Recommendation |
|---|---|---|---|
| Coordinator selects a typed split and posts it on a clone | Budget, parent ownership, observations and errors stay together; no new kernel actor; straightforward fault injection | Preserve stable status and fallback choice sequencing; prove split coverage and progress | First frontier-only implementation |
| Small native brancher with integer column/split in its `Choice` | Natural `choice/commit/archive` integration; could later serve BAB/recomputation | Clone-safe view arrays, brancher identity, archive round trips, actor disposal, no raw parent pointers or mutable shared learning state inside choices | Revisit only when BAB/recomputation support is required |
| Variable-selection callback embedded in the existing brancher | Small-looking selection hook | Callback has no safe independent probe/budget ownership contract; capturing parent Space or coordinator state complicates cloning | Do not use for strong probing |

Keep the existing brancher installed. The enabled coordinator bypasses
`choice()` only when it has selected a manual split. It posts `rel()` on each
child and then uses the existing `evaluate()`/enqueue path. For a fallback,
create exactly one built-in choice after all probes are destroyed. Do not create
a choice before probing, call parent `status()` a second time gratuitously, or
commit a stale choice. Subsequent child status handles the dormant built-in
brancher's normal variable scan. Test this explicit assumption against the
kernel lifecycle suite, including parents cloned repeatedly before fallback.

## First implementable slice: binary directional gains

Add an optional `NativeBranchingSettings` to `NativeSearchOptions`, absent by
default. Initial policy name: `BinaryReliability`. Scope is original active
`VariableType::Binary` columns whose current domain is exactly `{0,1}`. Exclude
generated indicator gates from the initial candidate panel using the typed
indicator metadata; never rely on a variable name. All other variable types,
including two-valued semi-integers, retain the existing brancher as fallback.
Mixed models remain fully supported because the fallback eventually branches
on every remaining unassigned compact variable.

The internal candidate is an owning value record, not a public callback:

```cpp
struct SplitCandidate {
  std::size_t original_slot;
  int compact_column;
  int split;                 // first slice: 0
};
// Down: x <= split; Up: x >= split + 1.
```

Validate the mapping, current domain, integral split and `split+1` before any
clone. The generic helper can use checked wider arithmetic and require
`min(x) <= split < max(x)`, but this first policy emits only binary splits.
Future general-integer splits partition the actual domain even with holes:
`D ∩ (-∞,k]` and `D ∩ [k+1,∞)` are disjoint and cover `D`. Both are nonempty
when `k` lies between distinct domain extrema, and both strictly reduce it.
Never replace a sparse domain with its hull when posting the split.
The implemented candidate panel is local to one call on a stable parent, so
no persistent decision identifier is needed. Delayed child observations or
cached probe reuse would require an explicit decision/generation identifier.

Store a solve-local directional history per eligible original slot. No history
survives a model edit, another solve, a worker, or a changed relaxation policy.
Each direction has a checked sample count, finite running mean and zero-gain
count. A stable probe gives

`gain = max(0, normalized_child_bound - stable_parent_bound)`.

Compute the integer subtraction in a wider checked type before converting a
ranking value to floating point. Binary observations have unit displacement;
this is a native directional-gain statistic, **not** the LP pseudocost
`gain / fractional_distance`. A reliable variable initially needs two finite
completed observations in each direction. Two is an experimental opt-in
starting point, not a tuned default recommendation.

Rank by `(min(down,up), max(down,up), -original_slot)` lexicographically, using
means for reliable histories and current completed probe gains when available.
This avoids arbitrary multiplication/epsilon scores and produces stable ties.
Unknown history starts at zero, is marked unknown, and remains eligible for
bounded initialization. All-zero or insufficient-information panels fall back
to the original brancher. Later compare this score with the literature's
weighted/product scores under the same work budget.

Candidate enumeration is a deterministic bounded scan of compact columns.
Build only a capped panel; use a bounded heap if history ordering is desired.
Charge every examined column and comparison. For early exploration, a
solve-local rotating start index can avoid permanent prefix starvation, but
must be explicit in the trace and reset per solve. First implementation may
use a fixed prefix to minimize hidden state; the benefit gate must expose that
limitation.

## Probe interface and publication rules

The coordinator keeps one stable parent baseline and frozen incumbent version
for the whole candidate panel. A probe owns one `unique_ptr<NativeSpace>`:

1. Check shared stop state and deterministic probe/work/storage allowances.
2. Reserve one resident-Space slot, clone the stable parent, and post one split.
3. Charge the probe propagation attempt before calling `status()`.
4. Recheck cancellation/time after status, then read only a stable normalized
   integer cost bound. Clamp it below by the parent's inherited bound.
5. Destroy the clone, recheck stop state, and stage the directional observation.
6. Publish a pair of observations only after both directions complete and the
   publication checkpoint passes. A half-pair never increments reliability.

Do not call the ordinary `evaluate()` helper for probes: it admits search nodes,
checks/publishes incumbents and discharges regions. Extract a narrowly scoped
propagation/bound observation helper while leaving ordinary evaluation's
publication sequence intact. Probe outcomes distinguish finite stable gain,
native failure, cancelled/time stopped, and operational error. An `SS_SOLVED`
probe is only a stable finite observation; it does not publish a solution.

Native failure is a categorical ranking event for the current candidate, not
an infinite pseudocost sample. For the first slice, do not update either finite
history from a pair containing a failed direction, and do not reuse a failed
probe as a proof to skip ordinary child evaluation. A completed failed pair
may prioritize that split using a separate leading rank of two/one/zero failed
directions; it never stores infinity in the means. Both normal children are
still created and evaluated. No probe tightens the parent, applies a learned fixing, changes
the incumbent, seeds an enqueue bound, or removes an unresolved region.

Ordinary selected children can later contribute directional history only when
the parent baseline and incumbent version match the stored decision record,
both observations are stable/finite, and that `(decision,direction)` was not
already sampled by a probe. The first implementation should collect probe
pairs only; delayed-child updates are a separately tested optimization.

## Coverage and bound proof

Let `R` be the active parent's feasible region, already intersected with any
ancestor incumbent cutoffs. Its stored bound `b` is valid for all of `R`.
Probing copies `R` and adds a temporary disjunction arm; destroying that copy
does not change `R`, the parent Space or `b`. Mutable backend warm starts can
change numerical effort but cannot change this ownership/proof statement:
the LP backend restores every requested bound and each actor checks its own
certificate against its own domains. Keep the immutable root-cut evidence
alive exactly as in the current frontier.

For the selected split, `R = R_down ∪ R_up` and the regions are disjoint.
Until both normal arms are discharged or safely enqueued, retain the parent
and `active_bound=b`. Partial expansion can temporarily duplicate coverage;
it must never omit an arm. After complete transfer, ordinary propagated child
keys and checked incumbents replace the parent. Pseudocosts affect only which
partition is chosen, so even corrupt, stale or deliberately adversarial scores
cannot invalidate the global bound or delete a feasible point.

Before the first normal child is propagated, an interrupted public bound must
therefore be exactly the previously established frontier/parent aggregate,
regardless of how strong any discarded probe appeared. Max sense and offsets
use the existing normalization unchanged. Finite-domain progress plus the
complete fallback preserves termination when the outer limits allow exhaustion.

## Budget and failure contract

Proposed opt-in settings (all finite):
`max_candidates_per_decision`, `max_probe_status_calls`,
`max_probe_status_calls_per_decision`, `max_branching_work`,
`reliability_samples`, `max_nonimproving_pairs`, and `max_history_entries`.
Example starting caps are 8 candidates, 128 total probe status calls, 8 per
decision, 100,000 coordinator work units, 2 samples, and 2 nonimproving pairs.
These are experiment settings; no automatic policy is selected by them.
Zero resource/lookahead caps skip the corresponding optional work; a zero
reliability sample threshold is invalid because an empty history must never be
treated as initialized. All-zero caps must exactly select built-in fallback.

| Resource or event | Required behavior |
|---|---|
| Shared cancellation/deadline | Check before/after cloning, posting, propagation, clone destruction, pair publication and selection; preserve active parent; return the precise outer stop |
| Shared node limit | In the enabled policy, charge every probe status attempt through `SolveBudget::add_nodes()` as well as ordinary admissions; publish `budget_nodes = admitted_nodes + probe_status_calls`; document this explicit opt-in accounting change |
| Probe budget / branching work cap | Stop probing, keep earlier completed ranking observations, and use a valid selected split or built-in fallback; this cap does not terminate the solve |
| Remaining node quota | Do not begin a probe pair without room for both probe directions and two normal child admissions; check using safe remaining-count arithmetic; each actual admission still rechecks the shared limit |
| Resident Spaces | Count queued Spaces + active parent + temporary probe against the existing `max_open_nodes`; process directions sequentially; never hold a probe while constructing a real child |
| Insufficient optional probe slot/history cap | Skip optional probing/history growth; normal child allocation retains existing MemoryLimit behavior |
| Allocation exception | Return MemoryLimit with parent still represented; do not treat an actual allocator failure as a successful optional cap exit |
| Native/backend implementation error | Return BackendError and the existing conservative initial-bound fallback; do not continue on potentially corrupted semantic state |
| Invalid options / count overflow | Reject before search, or fail explicitly before the overflowing update; never silently wrap |

`max_branching_work` bounds coordinator scans, comparisons, samples and
allocation sizes. It is **not** a hard bound on propagator instructions. Native
`status()` runs to fixpoint/failure and is cooperative only at its boundaries.
Use `StatusStatistics` to report observed propagation work, but do not promise
an interruptible per-propagator quota without separate kernel work. An LP actor
uses its existing per-attempt limits; its calls/time are already part of total
relaxation statistics. Report probe-specific LP deltas separately as a subset,
not additional calls to add to the solve total. Later LP-iteration budgets need
a measured backend counter and explicit API, rather than inferring iterations
from elapsed time.

Stop lookahead after the configured number of complete nonimproving pairs.
Zero objective gain is an observation, not numerical failure or proof that a
candidate has no future value. For degenerate objectives, use the fixed small
probe cap and fallback initially. Later evaluate inference/domain-reduction
signals; do not label a zero native gain as measured LP dual degeneracy.

## Classical LP pseudocost extension after the first gate

W8b needs a copied finite **current-node** LP point with source/backend identity
and the exact parent box at which it was obtained. Requesting it must consume
the same budget and report its LP calls. A projected or stale root hint is not
a classical branching point. Candidate fractional coordinates must satisfy a
positive, explicitly checked displacement; skip near-integral or nonfinite
coordinates without making a feasibility claim.

For a candidate `xbar`, a standard split uses `k=floor(xbar)`;
`d_down=xbar-k`, `d_up=k+1-xbar`. Both must be strictly positive and bounded
away from floating underflow for heuristic division. Domain holes require an
explicit convention: initially reject fractional candidates whose point lies
outside the actual domain intervals, or use the adjacent feasible values with
separate metadata; never silently mix the two displacement definitions.

Keep native propagated-gain and numerical LP-gain histories separate. A finite
checked bound need not be the LP optimum, and differences of two lower bounds
are not the true relaxation improvement. They remain useful ranking hints but
must be labeled accordingly. Genuine LP-optimal samples require a backend
completion contract; iteration-limited observations need separate counts and
weights and cannot establish reliability merely by repetition. Confidence
intervals, discounted histories, degeneracy scores, symmetric transfer, learned
branching, probe-result reuse and parent fixings are later experiments.

## Implementation ownership and acceptance gates

First source slice:

- `native_search.hpp`: append opt-in settings and branching statistics.
- `native.cpp`: coordinator-owned candidate/split/probe/history helpers and
  conditional branch selection only; preserve BAB/ordinary NativeLP defaults.
- `test/optimize/native_branching.cpp`: independent tiny oracle and pure
  history/budget/trace tests; extend existing frontier fault tests minimally.
- CMake/CI registrations plus NATIVE-SEARCH documentation and a small explicit
  FAST correctness case, coordinated with their owner.

No kernel, native global implementation, model schema, parser, C/Python API,
root-cover proof logic or HiGHS dependency changes are required for W8a.
Run a no-native build to validate unavailable capability and malformed options.
Native-only and combined LP/root-cover builds must exercise the same policy.

W8a implementation validation: 2,397 combined configurations pass both normal
and complete native+HiGHS ASan/UBSan builds; 2,381 native-only configurations
and the core unavailable/options checks pass. The existing default frontier
coordinator retains its 2,723 passing configurations. Independent reviews of
the probe lifecycle, parent coverage and pair publication found no correctness
blocker. Generated-gate exclusion uses the original variable metadata, including
retained gates after indicator removal. Performance gates below remain open.

Correctness gates are mandatory before benefit measurements:

1. Enumerate every original assignment for tiny binary/mixed models; compare
   optima, all returned witnesses and every interrupted global bound. Include
   min/max, signed/zero costs, offsets, ties, infeasibility, empty/fixed models,
   tombstones, holes, original indicators/gates and all native global families.
2. Verify exact split coverage and strict progress on sparse domains; verify
   binary-only eligibility and complete fallback on general/semi-integer models.
3. Cross all node quotas through exhaustion, zero/one/pair probe caps, work and
   history caps, both frontier orders, resident limits 0/1/2, LP off/on and root
   covers off/on. Assert explicit shared-node and subset-LP counter identities.
4. Inject cancellation, time expiry and allocation/backend errors at every
   probe lifecycle gate, between directions, before sample publication, after
   selection and through ordinary child transfer. Assert unchanged parent
   coverage, no probe incumbent/bound publication and no half-pair reliability.
5. Inject adversarial/zero/huge history scores. Only traversal may change.
   Repeat identical runs and concurrent independent solves; verify no model,
   history, parent-domain or sibling-bound leakage. Stress clone-then-fallback
   against brancher lifecycle checks under full-source ASan/UBSan.

Then compare whole-command wall time, time to first solution, total LP work,
search admissions **plus probes**, peak live Spaces and bound progress across
several families. Include fixtures where small-domain branching is already
good, propagation-heavy scheduling/globals, sparse binary packing/covering,
zero-cost degeneracy and mixed general-integer fallback. Separate tuning from
held-out instances; preserve timeouts and failed/unsupported runs in reports.
Show ablations for baseline, ranking without probes, fixed bounded probes, and
reliability reuse with identical outer budgets and root-cut settings.

An implementation can ship as experimental when exact/fault/build gates pass.
Automatic/default use requires reproducible whole-solve improvement on a
held-out panel and explicit protected-regression thresholds agreed before
tuning. Fewer admitted nodes alone is insufficient when probing consumes the
saved work. The existing frontier remains the default until that gate passes.

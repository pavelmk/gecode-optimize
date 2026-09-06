# Serial scenario batches with owning original-model evidence

Design proposal, 2026-09-05. No scenario implementation or default routing change
is claimed here. Local API baseline includes O1 LP observations (header 8789972ae,
implementation 27705581b) and the existing model/session/result interfaces.

## Recommendation and commercial scope

Start with an explicit serial batch of independent models, each defined by sparse
absolute overrides of one immutable base snapshot. Reuse a private HiGHS session
for compatible numerical models; preserve explicit Native one-shot solving for
its admitted exact integer subset. Complete the correctness, lifetime and budget
contracts before adding parallel scheduling or any sharing of search regions.
This is a useful convenience and reoptimization feature, not a claim of integrated
multi-scenario search performance, stochastic programming, nonanticipativity or
robust optimization.

Gurobi's integrated multi-scenario API accepts changes to linear costs, variable
bounds and linear RHS values. A single optimize call addresses the specified
scenarios; an empty scenario includes the base model. The documented model class
is broad, but has one objective and is treated as MIP even for continuous data.
Scenario callbacks/cuts have cross-scenario validity restrictions. These are
commercial scope references, not a promise that this first implementation admits
all those classes or uses the same search algorithm. The documentation does not
establish a particular internal tree representation.
[Official multi-scenario feature](https://docs.gurobi.com/projects/optimizer/en/current/features/multiscenario.html).

Gurobi separates scenario solution, objective and bound attributes (`ScenNX`,
`ScenNObjVal`, `ScenNObjBound`) and uses `GRB.UNDEFINED` to represent inherited
attributes. Our proposal instead uses typed optional overrides and an ordinary
status-bearing result per scenario. Missing data remains absent, including after
interruption. There is no batch scalar objective or bound across different
objective functions.
[Official scenario attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/multiscenario.html).

CPLEX 22.1.2 provides explicit routines to change
[linear objective coefficients](https://www.ibm.com/docs/en/cofz/22.1.2?topic=c-cpxxchgobj-cpxchgobj),
[variable bounds](https://www.ibm.com/docs/en/cofz/22.1.2?topic=c-cpxxchgbds-cpxchgbds),
[linear RHS values](https://www.ibm.com/docs/en/icos/22.1.2?topic=c-cpxxchgrhs-cpxchgrhs),
and the [objective offset](https://www.ibm.com/docs/en/icos/22.1.2?topic=c-cpxxchgobjoffset-cpxchgobjoffset).
Its [problem modification guidance](https://www.ibm.com/docs/en/icos/22.1.2?topic=application-change-problem-object)
explains reuse of an LP basis after compatible edits. That is the verified CPLEX
engine workflow this serial proposal targets. No equivalent CPLEX engine scenario
attribute family was established by the documentation reviewed; this is not a
claim that CPLEX cannot be used for scenario analysis. IBM's
[Decision Optimization scenario notebook](https://www.ibm.com/docs/en/ws-and-kc?topic=models-working-multiple-scenarios)
is a separate experiment-management layer, not evidence of an engine shared-tree
API or of CP Optimizer functionality.

| Change or behavior | Gurobi multi-scenario | Verified CPLEX path | Proposed first slice |
|---|---|---|---|
| Linear objective coefficient | `ScenNObj` | `CPXchgobj` | Absolute sparse replacement, including zero |
| Variable bounds | `ScenNLB` / `ScenNUB` | `CPXchgbds` | Independently optional lower/upper |
| Linear row sides | `ScenNRHS` on existing rows | `CPXchgrhs`; ranged rows have separate representation | Optional lower/upper on ranged rows |
| Objective constant | Not one of the documented four scenario overrides | `CPXchgobjoffset` | Explicit finite offset override |
| Same variables/matrix | Base structure retained | Model-edit workflow can change more | Structure, types and objective sense fixed |
| Original base solve | Include an empty scenario | Solve the original object | Include an empty definition explicitly |
| Search sharing | Integrated multi-scenario solve | Reoptimization verified | Serial session state reuse only |
| Per-case outcome | Scenario values/objective/bound | Each solve has its own result | Full per-case status, checks, history |
| Export one scenario | `singleScenarioModel` | Ordinary changed model | Owning `materialize(id)` snapshot |

The extraction comparison is supported by Gurobi's
[model-query reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/c/queries.html).
The commercial references are primary documentation fetched on 2026-09-05.
Gurobi links use mutable `current` documentation (the
[documentation index](https://docs.gurobi.com/projects/optimizer/en/current/index.html)
identifies release 13.0); a release-specific feature URL could not be fetched, so no frozen-source
claim is made. IBM references above explicitly identify 22.1.2. Implementation
should record solver versions with results, independently of these reference
versions.

## Candidate API

Names below are proposed, not declarations already present in installed headers.
The first implementation should add `scenarios.hpp`, `scenarios.cpp`,
`test/optimize/scenarios.cpp`, a fake-coordinator fixture, and `SCENARIOS.md`.
C/Python bindings and build registration follow after the C++ contract passes.

```cpp
struct ScenarioVariableBounds {
  Variable variable;                       // handle in original base
  std::optional<double> lower, upper;       // absent = inherit base side
};
struct ScenarioRowBounds {
  Constraint row;                          // handle in original base
  std::optional<double> lower, upper;
};
struct ScenarioDefinition {
  std::string name;
  std::vector<Term> objective_coefficients; // absolute overrides, NOT increments
  std::optional<double> objective_offset;
  std::vector<ScenarioVariableBounds> variable_bounds;
  std::vector<ScenarioRowBounds> row_bounds;
};
struct ScenarioId {
  ModelId batch_id = 0;
  std::uint64_t index = 0;
};
enum class ScenarioReuse { Automatic, Cold };
struct ScenarioBatchOptions {
  SolveOptions solve;
  ScenarioReuse reuse = ScenarioReuse::Automatic;
  // Explicit structural caps; final defaults require allocation tests.
  std::size_t max_scenarios = 1000;
  std::size_t max_patch_entries = 1000000;
  std::size_t max_saved_value_slots = 10000000;
  std::size_t max_work = 100000000;
};
enum class ScenarioRunState { NotStarted, Attempted };
enum class ScenarioBatchCompletion { Rejected, Interrupted, Complete };

class ScenarioBatch {                       // private immutable shared artifact
public:
  ModelId id() const;
  const ModelSnapshot& base() const;
  std::size_t size() const;
  ScenarioId scenario(std::size_t index) const;
  const ScenarioDefinition& definition(ScenarioId) const;
  ModelSnapshot materialize(ScenarioId) const; // owning copy, original slot order
  Variable map(Variable original) const;      // reject foreign/deleted base IDs
  Constraint map(Constraint original) const;
};
struct ScenarioCheck {
  bool identity_valid = false;
  bool objective_matches = false;
  ValidationReport validation;              // scenario's original constraints
};
struct ScenarioOutcome {
  ScenarioId scenario;
  ScenarioRunState state = ScenarioRunState::NotStarted;
  std::optional<SolveResult> result;         // owning private scenario identity
  std::optional<ScenarioCheck> check;        // absent until candidate checked
  SessionStatistics reuse_delta;            // zero for cold/native
  double elapsed_seconds = 0;
};
struct ScenarioBatchResult {
  std::shared_ptr<const ScenarioBatch> batch; // absent if admission failed
  ScenarioBatchCompletion completion = ScenarioBatchCompletion::Rejected;
  std::optional<Termination> stop_reason;    // never a batch objective status
  std::optional<std::size_t> offending_scenario;
  std::string message;
  std::vector<ScenarioOutcome> outcomes;     // all admitted cases, input order
  SessionStatistics reuse_statistics;
  std::size_t attempted = 0, resolved = 0;
  double elapsed_seconds = 0;
  bool all_resolved() const;
  double value(ScenarioId, Variable original) const;
};
ScenarioBatchResult solve_scenarios(const ModelSnapshot&,
    const std::vector<ScenarioDefinition>&, const ScenarioBatchOptions& = {});
ScenarioBatchResult solve_scenarios(const Model&,
    const std::vector<ScenarioDefinition>&, const ScenarioBatchOptions& = {});
```

`value` resolves an original base variable only through its owning batch mapping
and the selected scenario's validated result. It never rewrites that result's
owner to the base model. Different scenarios may have different feasible sets and
objectives; a feasible scenario point need not satisfy the base model. A separate
caller-requested validation against the base is possible, but is never implied.

## Admission and minimal supported class

Admit every definition before the first backend call. This makes malformed later
scenarios deterministic errors instead of consuming a partial solve budget first.
A failed admission returns no executable batch or partial materialization and
leaves the caller's model, definitions and sessions untouched. Report the first
invalid scenario/field in input order; resource/time/cancel can stop admission
before all errors have been inspected. No backend infeasibility claim follows
from malformed input.

Definitions use absolute values relative to the base, never changes relative to
the preceding scenario. Empty scenarios mean exactly the base; duplicate/empty
names are allowed because typed ordinal IDs supply identity. Identical definitions
are retained as separate requested cases. Missing objective terms inherit the base
coefficient, which is zero if absent. An explicit zero override removes that term
from canonical sparse storage. An absent offset inherits the base offset.

Reject foreign, deleted or malformed IDs, duplicate coefficient overrides,
duplicate variable/row records, and records with neither side specified. Lower
and upper in a single record are applied simultaneously. Reject NaNs and
nonfinite objective values; bound infinities follow existing `Model` rules.
Reject reversed final bounds as InvalidModel, matching current model admission;
don't reinterpret invalid bound pairs as an infeasible mathematical scenario.
Binary bounds must remain within `[0,1]`. No hidden coercion, clamping, rounding,
or sum-of-duplicates interpretation is permitted. A row's unspecified side is
inherited independently; changing both sides of an equality requires specifying
both sides. The base objective sense stays fixed.

The smallest implementation scope is ordinary linear models with Continuous,
Integer and Binary variables, including inactive variable/row slots and constant
rows. Each case must satisfy its requested backend's existing numerical or exact
admission rules; no continuous relaxation substitutes for an integer solve.
SemiContinuous/SemiInteger, active indicators and typed globals are explicitly
Unsupported initially, even if the base is solvable through an existing one-shot
route. Protected origin records/metadata must not be silently erased to enter
this class. Initially reject nonempty indicator/global metadata, including its
inactive history, if a complete owner-remapping implementation is not included;
state that additional granularity limit in capabilities. This conservative bound
is preferable to accidentally retaining invalid lowering guards after widened
scenario bounds. Supporting harmless inactive metadata is a separate mapped-copy
test before removing that restriction.

This is a restriction of the new workflow, not a reduction of existing `solve`,
Native, global, QP, LP-observation or session capability. An explicit Numerical
HiGHS case remains Numerical; an explicit Exact Native case keeps exact native
admission. Certified remains Unsupported. Current Auto routing is preserved:
ordinary linear Auto requests go to HiGHS, including the existing behavior for
an unsupported Exact request. Never use a private numerical session to turn an
explicit Native request into a HiGHS solve. Cold mode and Automatic mode must
choose the same backend class for an admitted request.

For first delivery, reject nonempty common `solve.primal_start` explicitly rather
than silently dropping it or applying a base-feasible start to incompatible
scenarios. A later per-scenario start field can provide precise semantics. Existing
session reuse may submit an earlier incumbent only through its normal independent
revalidation against the new scenario; this is an implementation hint, not evidence
that any scenario was solved. No scenario-specific callbacks or solver policies
are introduced in this slice.

## Ownership, reconstruction and session reuse

Own the complete validated original base once, plus normalized sparse definitions.
Reserve a fresh private model owner through the existing Model ID allocation path.
Use that private owner consistently across materialized scenarios so the session
can reuse matrix state. Give scenario `i` a distinct private revision `i+1`, after
checked ordinal/revision range validation. These revisions are internal identities,
not the original Model's mutation count. Same-owner different-scenario results
must still fail an exact revision check against the wrong scenario.

All original slots, including tombstones, survive materialization. Rebase every
variable, row and objective-term handle to the private owner. Validate the complete
private snapshot after patching; an unrewritten reference fails closed. No helper
variables or rows are needed for the ordinary linear first slice. Do not rebuild
only the active rows and compact away tombstones. Do not overwrite original result
identity merely to expose convenient base-variable lookups.

`ScenarioBatch` has a private constructor and const owned data, so callers cannot
alter its definitions after admission. `materialize` returns a new owning copy with
the documented private owner/revision; altering that copy cannot mutate the batch.
`ScenarioBatchResult` owns the artifact after the input Model, a temporary snapshot,
the input definitions and the local session are destroyed. Outcome results already
own their primal vectors, masks, scalars and messages. Store one base and sparse
patches, not a full matrix snapshot per scenario. Result storage is necessarily
proportional to retained primal slot vectors; cap the worst-case scenario-count
by original-slot-count product with checked multiplication before solving.

Use a batch-private `SolveSession` in Automatic mode for HiGHS; do not mutate a
user-supplied session in the first API. Materialize every case from the base, even
when reusing a backend instance. The existing session already compares actual
matrix/types/slots and modifies bounds/costs/row sides/offsets; it doesn't trust
revision alone. Compatible edits can retain a basis. Earlier MIP witnesses are
rechecked before reuse. MIP trees and cuts are not retained by the current session.
Cold mode uses independent one-shot solves. Native cases always use the existing
one-shot native backend; session reuse counters are zero, not fabricated.

Capture counter deltas for model loads, incremental updates, unchanged models,
basis warm starts and incumbent starts. Check monotonicity/overflow instead of
subtracting unsigned counters blindly. Counts describe attempts to reuse state,
not measured speedups or proof reuse. Do not cache or infer solved outcomes across
identical/dominated scenarios in the first version: the backend remains responsible
for every recorded solve. `materialize` is the path to explicitly run diagnostics,
LP observations or other supported workflows on an individual scenario later.

## Shared budgets and the missing node-accounting prerequisite

Construct one outer `SolveBudget` before copying, normalization, allocation or
admission. Every loop checks its time/cancel state; structural work/storage caps
are separate from solver nodes. Pass only `remaining_seconds()` and the same
cancellation token to a stage. A local solve budget is an allowance inside that
outer deadline, not a fresh grant of the original limit. Recheck the outer budget
immediately before entering the backend, after return, around validation, before
publishing a candidate/status and after destroying temporary/backend state.
Future internal shared-budget entry points can pass the same budget object
instead of deriving a remaining-time allowance.

Define structural cap units explicitly: scenarios, patch records, saved original
value slots, and metered coordinator element visits. Checked storage-cap overflow
or exhaustion returns MemoryLimit; coordinator work exhaustion returns
IterationLimit with a message naming that cap, not a claimed solver iteration
count. A zero cap permits zero units. Caps apply before reserve/copy and during
normalization, validation and materialization, with deterministic work charging.
An empty request completes only after valid admission and a final budget gate.

A returned candidate is not promoted merely because it was timely inside a local
stage if the outer batch is already stopped. Earlier fully checked and published
scenario outcomes remain intact; the current outcome preserves its actual stopped
status and no late candidate is accepted. Unstarted cases have no SolveResult,
no solution and no bound. Cancellation takes precedence over time, then nodes,
matching SolveBudget. Cooperative propagation/backend cleanup can overshoot wall
time; this does not authorize an additional solve or late publication.

**Current gap:** `SolveResult` has no consumed-node field; HiGHS checks local
`mip_max_nodes` but does not add its deltas to a shared SolveBudget. Passing the
same positive node limit to every session call is therefore incorrect. A remaining
wall-clock allowance cannot solve this accounting problem.

Recommended first delivery: absent node limit is supported; zero quota stops
before a backend call; a positive node limit on a multi-scenario request is
explicitly Unsupported until the following private adapter prerequisite is ready.
A single scenario can preserve ordinary one-shot node-limit behavior without
claiming cumulative node statistics. Do not claim a supported whole-batch node
budget while this restriction remains. If node-limited batches are a mandatory
acceptance requirement for the first delivery, implement the prerequisite first;
do not relax this gate.

The required follow-up is a private stage adapter accepting the shared SolveBudget
and an optional backend/session state. For HiGHS, apply only the remaining node
quota and charge newly observed cumulative-run deltas once, including final info
and exception paths. Check counter reset/monotonicity against pinned 1.15.1 source.
For native BAB, reuse its existing BudgetStop statistics observer with the same
outer state; for frontier, charge admitted/probe nodes under its documented rules.
Continuous LP node usage is zero by contract; an unavailable MIP counter is not
zero. If usage becomes unknowable, stop the batch explicitly and retain earlier
outcomes, rather than opening another quota. No public ABI change is necessary
for an internal stage record containing `optional<uint64_t> consumed_nodes`.
Backend-defined node units differ; a batch uses one selected backend class and
must report that definition. Exact node-boundary tests are required independently
of time tests, and public one-shot defaults must remain unchanged.

## Status, validation and publication rules

A scenario is resolved by a valid Optimal, Infeasible or Unbounded backend outcome
under that backend's documented guarantee. Optimal numerical outcomes retain their
requested solver-gap interpretation; don't force zero gap or relabel them exact.
InfeasibleOrUnbounded, Unsupported, InvalidModel, numerical/internal failures and
all limits remain explicit. Stop after the first unresolved/error outcome in the
first serial coordinator; later cases stay NotStarted. Continue after definite
infeasibility or unboundedness because scenarios are independent.

A Complete batch means every requested scenario was resolved. A batch containing
all infeasible scenarios is still a completed batch; it is not a new proof that
the base model is infeasible. An empty admitted batch completes with no solve;
solving the base requires an explicit empty definition. Never aggregate unrelated
primal objectives or bounds into a synthetic best solution, expected value, or
worst-case robust objective. Those are separate user-defined mathematical models.

Before accepting any candidate, verify raw backend model ID/revision, dimensions,
active mask and a finite optional primal objective. Reject NaN bounds or invalid
bound orientation; retain meaningful signed infinite bounds under the common
result contract, rather than conflating an infinite bound with an absent one.
Independently evaluate the
original base with the selected overrides, not only backend arrays. Use the common
validator and compensated objective evaluation including offset. Exact native
completion also needs checked integer validation in the admitted native range;
arithmetic inability is an explicit failure, never an Exact upgrade from a float
check. Recompute/compare the scenario objective and preserve genuine bound ordering
errors; no epsilon clamp to manufacture a zero gap. A valid point supplied beside
Infeasible disproves that status and must prevent resolved classification, even
if the vendor's `solution_validated` flag is false. Unknown optional fields stay
absent. No proof certificate is invented.

All checks and allocating copies precede a single publication gate. If result
validation fails, stop with explicit invalid-evidence diagnostics; don't retain a
forged optimality status or rewrite its identity. Earlier outcomes and their
ownership remain valid. A timely incomplete feasible candidate can be retained
only with its original incomplete termination and no resolved claim. The local
backend cannot transfer a bound from another scenario or from an unvalidated
private snapshot.

## Conformance, reuse experiments and rollout

1. Exhaustively enumerate tiny signed Integer/Binary boxes for both senses,
   different costs/offsets, zeroed/new objective terms, each bound side and each
   row side. Compare every materialized feasible set and optimum with an evaluator
   reading base plus raw definitions independently. Include an empty definition
   between two edited cases to detect patch leakage.
2. Use analytic continuous LPs with known optima, fractional recourse, infeasible
   cases and truly unbounded cases. Compare cold and reused results at unlimited
   budget: status, objective, feasibility and permissible bounds, not a particular
   degenerate primal/basis. Large-offset cancellation and bound ordering receive
   separate adversarial tests.
3. Cover aliases of caller containers, post-call edits/destruction, tombstones,
   identical scenarios, duplicate names, foreign IDs, wrong scenario revision,
   missing masks, sparse objective zero/delete, ±infinite sides, conflicting
   bounds, malformed late cases, empty batches and structural caps. Failed late
   admission must have zero solver calls and no partial batch.
4. Inject deterministic fake stage outcomes/checkpoints for cancellation during
   admission, materialization, solving, validation, publication and cleanup; test
   zero deadline and no second call after exhaustion. Supply foreign/stale results,
   invalid primal values, malformed masks/objectives/bounds, false infeasibility,
   invalid counters and allocation failure. Earlier published outcomes must
   survive, while unstarted slots stay explicitly empty.
5. Test actual missing-backend, explicit Native/Exact, Numerical HiGHS and
   unsupported class/guarantee/start boundaries in core, HiGHS-only and combined
   builds. Native ordinary integer outcomes must match cold `solve_native`; no
   session fallback or global/indicator stripping is allowed.
6. Assert session counter behavior for compatible bounds/cost/offset/row edits,
   unchanged cases and retained basis/incumbent validation. Replay scenarios in
   different orders: unlimited mathematical outcomes must agree; solve time and
   basis choices need not. Under a single finite total budget, compare safety and
   accounting rather than expecting identical completed prefixes.
7. Once the private node bridge exists, use forced per-stage counts and real tiny
   MIPs/native trees. Verify budgets below/equal/above each cumulative boundary,
   counter resets, zero-node LPs, unknown counters, exception paths and saturation.
   Never multiply the requested node limit by the number of scenarios.
8. Run assertions-enabled C++17 core/normal and complete facade/backend ASan+UBSan
   tests, existing workflow/session regressions, installed consumers and the
   uncontended FAST gate. Add C/Python only after ownership/status semantics are
   stable; bindings must copy scenario results and retain typed mappings.

After correctness passes, choose a fixed small subset of existing benchmark
models with bounded RHS/bound/cost perturbations and report cold-versus-session
loads, solves, wall time, memory and validated outcomes. Preserve baselines and
solver versions; separate correctness from timing, and don't infer a speedup from
reuse counters alone. The first feature needs no performance claim to be useful.
A shared-search extension requires independently scoped feasible regions,
scenario-specific bounds/incumbents, globally or selectively valid cuts, and
per-scenario exhaustion proofs. It is a later algorithm project, not a parallel
loop wrapped around these serial outcomes.

# Owning serial scenario batches

`scenarios.hpp` adds an explicit serial workflow for ordinary linear models.
Every scenario starts from one immutable base snapshot, applies sparse absolute
overrides, and receives its own owning result. HiGHS can reuse a private session;
explicit Native requests use the ordinary native solver. This API does not share
MIP search trees, combine scenario objectives, or construct a stochastic or robust
optimization problem. The commercial comparison and later shared-search/node
accounting work are in [the scenario design](SCENARIOS-DESIGN.md).

```cpp
Model model;
auto production = model.add_integer(0, 100);
auto demand = model.add_row({{production, 1}}, 20,
                            std::numeric_limits<double>::infinity());
model.minimize({{production, 3}}, 5);

ScenarioDefinition peak;
peak.name = "peak";
peak.row_bounds = {{demand, 40, std::nullopt}};
peak.objective_coefficients = {{production, 4}}; // replace cost 3 with 4

auto batch = solve_scenarios(model, {{}, peak}); // base is an explicit empty case
if (batch.all_resolved()) {
  auto peak_id = batch.batch->scenario(1);
  if (batch.outcomes[1].result->has_solution())
    double amount = batch.value(peak_id, production);
}
```

## Overrides and admission

An omitted bound side, coefficient or offset inherits the base value. A zero
coefficient removes its sparse objective term. Overrides are replacements,
including when a scenario follows another changed case. Row and variable lower
and upper bounds are applied together, so a legal final interval never fails
because one side would be temporarily reversed. The objective sense, matrix,
types, variables and rows remain fixed.

All definitions pass structural admission before any backend solve. Foreign or
deleted handles, duplicate overrides, records with no bound side, nonfinite costs
or offsets, NaN bounds and reversed final intervals return InvalidModel. Bound
infinities follow the existing Model contract: negative infinity is legal only
as a lower side, positive infinity only as an upper side. Binary bounds stay
inside `[0,1]`. Empty/duplicate names are allowed; names never identify a case.
Malformed later cases cause zero backend calls and no published batch artifact.

The initial class is active Continuous, Integer and Binary variables and ordinary
linear rows, including constants and inactive variable/row slots. Any nonempty
indicator/global metadata is Unsupported, including harmless inactive history.
Active semi-variables and nonempty common primal starts are Unsupported. No
hidden constraints or metadata are erased to enter this class. Existing solve,
Native, QP and global APIs retain their separate support.

Backend-specific limits still apply at each solve. A structurally valid scenario
can return Unsupported for a numerical range, native nonintegral data, requested
guarantee or unavailable backend. The workflow stops there and retains earlier
completed outcomes. Auto keeps the existing ordinary-linear HiGHS routing; it
does not silently switch an Exact request to Native. Explicit Native requests
retain their requested guarantee and native admission. Certified is not supplied
by either current backend.

An empty valid batch completes without invoking a solver, after the admission
and budget gates. Solving the base requires an explicit empty definition. An
already cancelled token, zero deadline or zero node quota stops before any solve.

## Ownership and evidence

The admitted `ScenarioBatch` owns the historical base and definitions. It creates
one fresh private model owner and gives case `i` revision `i+1`. Every original
slot, including tombstones, survives. All private variable, row and objective
handles are rebased. `materialize(id)` returns a new owning snapshot; editing it
cannot change the artifact. `map(original_handle)` checks the base owner and live
slot. Outcomes never rewrite private result identity to the base model.

`ScenarioBatchResult.model_id/revision` identifies the caller's original source,
even after rejected admission. `batch` is absent if admission failed. Successful
admission creates one outcome slot per requested case, in input order. Model
edits/destruction, definition edits and local session destruction do not invalidate
the batch, materializations, result vectors or mapped value access.

A returned backend result is checked for exact owner/revision, requested guarantee,
slot dimensions and active mask. Every claimed incumbent is independently checked
against the materialized original model. Its objective must equal the same
compensated original-model reevaluation used by the common result adapter; the
offset participates in that evaluation. Explicit Native witnesses additionally
pass a checked integer evaluator of original domains, rows and objective. This
does not upgrade a requested Numerical guarantee or fabricate a proof certificate.

`ScenarioCheck.identity_valid` concerns the raw result identity. The separate
`candidate_examined` flag determines whether `validation`, `objective_matches`
and `exact_witness_validated` contain candidate checks. A status-only reply can
have a checked identity without an available candidate. A feasible raw candidate
beside Infeasible disproves that status even if `solution_validated` is false.
Finite original variable bounds that bound the objective in the improving
direction also refute an Unbounded reply. Other infeasibility/unboundedness
completion claims remain the backend's stated guarantee, not new independent
proof certificates.

NaN bounds and incorrect bound ordering produce explicit invalid-evidence failure.
Meaningful signed infinite bounds remain present, with unavailable gaps under the
ordinary result contract. Missing bounds remain absent; no zero gap is invented.
Optimal requires an independently valid incumbent and actual backend Optimal
completion. Numerical completion keeps the backend's requested gap convention;
this workflow does not force zero MIP gaps or call numerical outcomes Exact.
Exact Optimal additionally requires a present finite global bound equal to the
independently checked exact objective. Unknown termination enumerators are invalid
evidence, rather than new public stop reasons.

## Completion, reuse and budgets

Complete means every requested case reached Optimal, Infeasible or Unbounded
under its backend contract. Definitive infeasibility or unboundedness does not
stop later independent scenarios. The first unresolved status, error or limit
stops the serial coordinator. Later outcomes remain NotStarted without a result.
Earlier checked outcomes survive. A timely incomplete incumbent can be retained
with its incomplete status; a late current candidate is discarded. A final
cleanup timeout can leave all individual cases resolved while the batch remains
Interrupted, so `all_resolved()` also checks batch completion.

Automatic reuse creates a batch-private HiGHS SolveSession. Each next model is
materialized anew from the base; the session's actual content comparison controls
reuse. A compatible LP basis can survive, and a previous MIP incumbent is only a
hint after original-model revalidation. No MIP trees/cuts are retained. Cold uses
independent one-shot solves. Native always uses one-shot solves. The recorded
session counters and per-stage deltas describe the latest observed session
state, not a speedup claim. Cold/Native counters are zero by definition.

One outer steady clock starts at workflow entry, including options, source
acquisition, admission, materialization, solve, independent checks and cleanup.
Each stage receives only the remaining time plus the same cancellation token.
No late stage can publish an incumbent or complete the batch. Cancellation takes
precedence over time, then node limits. Calls and allocation cleanup are
cooperative; wall time can overshoot while an indivisible operation finishes.

Node scope is deliberately narrower: absent quota is supported; zero stops before
any solve; a positive quota with one scenario is forwarded once under the ordinary
backend contract. A positive quota with multiple scenarios is Unsupported until
consumed-node reporting can charge one shared count. It is never independently
reset for every scenario. No cumulative consumed-node value is reported.

Storage caps cover scenario count, total objective/variable-bound/row-bound patch
records, and the product of scenario count and original variable-slot count.
Offsets consume their fixed definition storage rather than a patch record.
Checked cap overflow/exhaustion returns MemoryLimit. `max_work` meters coordinator
element visits: variable/row/term entries in source passes; variable/row slots in
scratch scans; patch/definition entries; name bytes before copied storage; and
exact-validator term/row visits. Each invocation of a source pass charges again.
Backend internals are not counted. Exhaustion returns IterationLimit with a
coordinator-cap message, not a backend iteration count. Zero caps allow zero units.
The Model overload must acquire its initial owning snapshot through the existing
Model API; this indivisible copy is included in time, but its allocation precedes
the snapshot-based structural preflight. Subsequent owned copies are precharged.

## Tests and extension boundary

The normal test compares tiny signed integer/binary scenario feasible sets in
both directions with an independent raw base-plus-overrides enumerator. It checks
both objective senses, widened/tightened bounds, costs/offsets, constant rows,
tombstones, history, analytic LP and continuous recourse examples, cold/session
equivalence, actual Native and missing-backend behavior.

The separately compiled coordinator fixture substitutes an independent finite-box
oracle only at the private solve boundary. It injects malformed owner/revision,
mask/objective/guarantee/bounds, false infeasibility, incomplete witnesses,
allocation failure and cancellation at admission/solve/check/cleanup gates. Every
coordinator-work boundary is exercised, and the single-case versus multi-case node
contract is checked directly. The seam is absent from production builds.

The feature remains explicit. Shared node accounting, per-case starts, mapped
indicator/semi/global scenarios, parallel execution and shared search are separate
future changes. Performance experiments must compare actual validated cold/reuse
runs; session counters alone do not establish an improvement.

Guarantee admission is independent of backend availability and batch size:
Numerical is admitted on all routes, and Exact requires explicit Native.
Certified and Auto/HiGHS Exact are Unsupported before any attempted scenario,
including an empty batch. An empty batch with an admitted guarantee is Complete
without invoking a backend. Attempted supported requests retain strict raw
result-guarantee validation; unsupported guarantees are not relabeled Numerical.

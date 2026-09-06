# Explicit exact integer presolve and reconstruction

`gecode/optimize/presolve.hpp` provides `presolve_integer`. It applies sound
integer interval propagation, removes proven redundant rows, substitutes fixed
variables, and returns an owning reconstruction map. The utility itself invokes
no solver, and its `postsolve` does not transfer optimization status or bounds.
The common Native automatic route now uses a separate bounded exact composition,
as described in [NATIVE.md](NATIVE.md): it solves the reduced model exactly and
restores original proof status and bounds under the artifact's equivalence
contract. General performance gains require subsequent benchmarks.

```cpp
#include <gecode/optimize/presolve.hpp>
#include <gecode/optimize/solve.hpp>
using namespace Gecode::Optimize;

Model original;
auto fixed = original.add_integer(2, 2, "fixed");
auto free = original.add_integer(-2, 2, "free");
original.add_row({{fixed, 3}, {free, -2}}, 4, 8, "range");
original.maximize({{fixed, -3}, {free, 2}}, 11);

PresolveOptions options;
options.time_limit_seconds = 1;
auto presolved = presolve_integer(original, options);
if (presolved.model) {
  // The private model has free in [-1,1], objective 5+2*free, and a fresh ID.
  auto reduced_solution = solve(presolved.model->reduced());
  if (reduced_solution.has_solution()) {
    auto recovered = presolved.model->postsolve(reduced_solution);
    if (recovered.exact_witness_validated) {
      const double original_fixed = recovered.solution.value(fixed);
      (void)original_fixed;
    }
  }
}
```

## Scope and guarantees

The initial active model class is finite Integer/Binary domains with integral
linear coefficients, finite row sides, and objective coefficients/offset. Row
sides may be infinite. Input integers must have magnitude at most `2^53`, as
represented by the model's double fields. Nonintegral data is rejected rather
than rounded or silently scaled.

Active Continuous, SemiContinuous, SemiInteger, indicator, and global constraints
are `Unsupported`. Inactive tombstones remain in the owned original model and
its mappings; their inactive metadata has no reduced-model semantics. Public
snapshots receive structural validation before any transformation. Invalid
identities, references, ranges or expression structure return `InvalidModel`.

All transformations use checked signed 64-bit arithmetic, including every
product, intermediate sum, subtraction and directed integer division. Division
by zero and signed minimum divided by minus one fail closed. Integer values
exported into the reduced double model, including substituted bounds and the
objective offset, must remain within `[-2^53,2^53]`. Unsupported arithmetic returns
`Unsupported` with no model artifact and cannot establish infeasibility. This
portable implementation has the same arithmetic boundary on platforms without
compiler-specific 128-bit integers. It may conservatively reject an otherwise
valid model whose expressions require wider intermediates or exports.

`PresolveResult.guarantee` is `Exact` for the transformation arithmetic, not a
claim that an optimization problem has been solved or that a proof certificate
has been exported. `Infeasible` is returned only for a checked contradiction in
an original row under bounds logically implied by the original model, or for a
contradictory constant row after exact fixed-variable substitution.

## Reductions and invariants

For a row `L <= sum(a_j*x_j) <= U`, each term has a minimum and maximum over the
current integer box. Their exact sums detect contradictions and rows implied
entirely by the current box. For each variable, subtract its contribution to
obtain the minimum and maximum activity of the other terms.

The lower side implies `a_j*x_j >= L - maximum_other`. The upper side implies
`a_j*x_j <= U - minimum_other`. Positive and negative coefficients select the
appropriate upper/lower bound and mathematical floor/ceiling division. Every
proposal for a row uses the same unchanged row-entry box; only after all
proposals are checked are they intersected into the current bounds. Each bound
change records its original row and variable, side, old/new integer bound and
pass index.

Every tightened bound is an implication of the original model. Therefore no
original feasible integer assignment is removed. A dropped redundant row is
true over the tightened box, so its removal introduces no new feasible point.
Further tightening only shrinks that box and preserves the redundancy argument.
The objective is not used as an implicit cutoff or deduction assumption.

After propagation stops, all fixed variables are substituted into retained rows
and the objective using exact arithmetic. The objective sense remains unchanged;
its offset incorporates all fixed contributions. Empty rows are either exact
tautologies and removed, or exact contradictions. Retained variable/row slots
are compacted into a new `Model`, with new model identity and ordinary stable
handles. Every reduced assignment maps to exactly one original assignment by
restoring fixed values, and every original feasible assignment has its reduced
projection. This feasible-set equivalence preserves the original objective.

## Owning mappings and historical solutions

`PresolvedModel` owns the immutable original snapshot, reduced snapshot and
slot-indexed mappings. Its public accessors expose const views:

- `variables()` contains one record per original variable slot. An active record
  holds either a reduced handle or a fixed integer value, plus its tightened
  bounds. Inactive tombstones have neither.
- `rows()` contains one record per original row slot. Active retained rows have a
  reduced handle and exact substituted constant; removed active rows are marked
  redundant. For rows proved redundant before substitution, no fixed constant
  needs to be computed. Names remain available in the original snapshot, and
  retained private names are copied.
- `original()` and `reduced()` retain independent identities. The original model
  and revision are never mutated. Later user edits or destruction of the input
  model do not invalidate the owning artifact or historical reconstructed values.

`postsolve` checks the candidate's reduced identity, revision, slot count and
active mask. It does not trust a candidate objective, cached gap, status, or
`solution_validated` flag as evidence of feasibility. Values must be finite and
within the requested distance of an integer; tolerance is in `[0,0.5)` and
zero requires already integral values. After rounding, all reduced bounds and
rows are checked with exact integer arithmetic. Fixed values are restored and
all active original bounds, rows and the original objective are checked again.
The two exact objectives must agree. Deleted original slots contain NaN and
remain inactive.

On success, `exact_witness_validated` is true and `solution` is a validated
original historical feasible point. Its scalar termination is `Unknown`, and
its global bound and gap fields are absent. Input Numerical/Exact guarantee and
backend identity are preserved for context; certificate guarantees are not
transferred. No optimality, rank or global-bound claim is manufactured from
reconstruction. Keep the reduced solver result separately if its completion
status is needed. Automatic transfer of optimization proof/status is a separate
future workflow contract.

## Work limits and statuses

All source validation/copying, propagation, finalization and artifact creation
share one monotonic time budget and cancellation token. Checks are cooperative,
including a final check before returning: an observed deadline or cancellation
prevents publication of a new artifact or infeasibility result. Structural
validation and individual allocations are not interruptible operations.
Postsolve is a separate explicitly invoked validation operation.

`max_passes` limits full propagation passes. `max_row_visits` limits visits to
active non-redundant rows during propagation; structural checks and algebraic
finalization are not counted as propagation visits. Both limits may be zero.
Finalization still substitutes declared/deduced fixed variables and checks
constant rows. All of that work remains charged to the time budget.

| Status | Meaning |
| --- | --- |
| `Fixpoint`, termination `Optimal` | A full propagation pass made no bound changes; the artifact is exactly equivalent. This does not establish original feasibility or an objective optimum. |
| `Incomplete`, termination `IterationLimit`, with artifact | Work limit reached; all published reductions are sound and the finalized partial model remains exactly equivalent. It is not claimed to be a propagation fixpoint. |
| `Incomplete`, `TimeLimit` or `Cancelled`, without artifact | The total budget stopped before publication. |
| `Infeasible` | Checked exact contradiction, attributed to an original row and, when applicable, variable. No reduced artifact is returned. |
| `Unsupported` / `InvalidModel` / `Error` | Explicit capability, input or processing failure; no artifact or inferred infeasibility. |

`passes` counts completed passes; `row_visits` counts propagation visits even in
an unfinished pass. `fixed_variables` and `removed_rows` describe finalized
reductions when an artifact is available. The change trace is attribution, not a
standalone proof-certificate format.

## Correctness gate

`test/optimize/presolve.cpp` independently enumerates complete feasible sets and
objectives. It checks all signed two-variable rows with coefficients from -3 to
3 and bounds from -5 to 5, and 600 generated three-variable models under complete,
pass-limited and row-visit-limited propagation. Reduced assignments reconstruct
bijectively to the full original feasible set, with matching objective values.

Additional checks cover signed floor/ceiling cases, chain propagation, equality
fixing, constant contradictions, all-fixed models, objective cancellation,
tombstones, fresh identities and history after edits, malformed/stale postsolve
candidates, explicit unsupported metadata/classes, multiplication/sum/export
overflow, and signed-minimum/-1 division. An integer parity model demonstrates
that a propagation fixpoint can still be infeasible, preventing a false solved
status. Interruption regressions cover a zero deadline and a pre-cancelled
token; they do not inject cancellation at every internal propagation or
finalization checkpoint. The utility is not automatically enabled; backend
integration and performance evaluation remain separately gated by the
solver-parity plan.

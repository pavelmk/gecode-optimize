# Explicit weighted feasibility relaxation

`relax_feasibility` constructs and solves a separate linear model in which only
selected original row sides or variable bounds can be violated. Every selected
side receives its own nonnegative continuous slack and strictly positive finite
penalty. The first objective minimizes their weighted L1 sum. Unselected row
sides, variable bounds, integrality, and original logical constraints remain hard.
The original `Model` or `ModelSnapshot` is never modified.

```cpp
#include <gecode/optimize/relaxation.hpp>
using namespace Gecode::Optimize;

Model model;
auto production = model.add_integer(0, 4, "production");
auto demand = model.add_row({{production, 1}}, 6,
                           std::numeric_limits<double>::infinity(), "demand");
model.minimize({{production, 3}}, 10);

RelaxationOptions options;
options.rows = {{demand, RelaxationSide::Lower, 5}};
options.optimize_original_objective = true;
options.solve.time_limit_seconds = 10;
auto repair = relax_feasibility(model, options);
// Minimum weighted violation is 10: produce 4, missing demand is 2.
// Original cost at that repair is 22. The original demand is still infeasible.
if (repair.has_repair()) {
  const auto amount = repair.original_values.at(production.id);
  const bool originally_feasible = repair.original_validation.valid;
  (void)amount; (void)originally_feasible;
}
```

## Mathematical meaning

For selected lower side `a*x >= l`, the private row is `a*x + s >= l`.
For selected upper side `a*x <= u`, it is `a*x - s <= u`. In either case
`s >= 0`, and the original selected side is disabled. Selecting both sides
creates two independent slacks. Variable bound selections use a penalty row with
coefficient one on that variable. All coefficients, bounds, weights, and reports
remain in original model units; there is no automatic weight normalization.

The first objective is `min sum(penalty_i * s_i)`. Positive penalties make its
minimum equal to the minimum weighted sum of actual side violations, subject to
numerical tolerances. These violations are recomputed independently from original
row activities and variable values. They are not merely read from slack variables.

With `optimize_original_objective = true`, a second stage optimizes the original
objective, including its sense and offset, subject to a hard upper lock on the
first stage's optimal weighted slack sum. Requested degradation is zero. Each
stage requests zero native absolute and relative MIP gaps, and completion also
requires an independently checked feasible witness and agreeing finite numerical
global bound. Existing feasibility and integrality tolerances still apply.

`original_objective_optimized` means optimal **within the minimum-violation repair
region**. It does not mean that an infeasible original model has become feasible,
or that the solution optimizes the original objective over any broader region.
A repair can have zero violation and be feasible in the original model.

## Evidence and provenance

- `source_model_id` and `source_revision` identify the untouched original input.
- `private_model` has a fresh model identity. Original variable and row slots,
  including tombstones, are retained; penalty variables and rows are appended.
  `private_variables` maps each original variable slot to its private handle.
- `private_model.objective` retains the original objective. Without phase two it
  describes the elastic feasible region, not a model already locked to minimum
  violation. With an established phase-two lock it also contains that hard row,
  whose handle is `violation_lock`. The first objective can be reconstructed from
  `items` as `sum(item.penalty * item.slack)`.
- Every `workflow` stage and its `final_solution` belongs to the private model.
  Passing an original variable handle to that result's `value()` is an error.
  Stage records provide their own objective, bound, status, and numerical gap.
- `original_values` uses original variable slots. `original_validation` reports
  original feasibility and residual maxima, including indicators. It is usually
  invalid when the minimum violation is positive. No original feasible
  `SolveResult` or `solution_validated = true` is manufactured.
- Each `item` identifies exactly one original row or variable side and includes
  its name, bound, weight, private slack/row handles, independently computed
  activity, violation and weighted violation, and private slack value. Items are
  ordered by original row slot then variable slot, with lower before upper.
- `minimum_weighted_violation` is the first stage's verified weighted slack
  objective. `weighted_violation` is the selected original residual sum at the
  returned repair. They agree within numerical tolerances when minimum violation
  was established, but are intentionally reported separately.

All evidence is `Guarantee::Numerical`, including backend optimality and the
independent long-double residual checks. Exact or Certified requests return
`Unsupported`. No proof certificate or exact infeasibility/optimality claim is
provided. Weighted residual checks account for the sum of penalties times the
absolute feasibility tolerance and floating-point accumulation error. Very large
weights therefore magnify the permitted weighted residual discrepancy. Precision
or backend numeric-range limitations return an explicit failure or `Unsupported`.

## Supported domains and hard constraints

| Input | Behavior |
| --- | --- |
| Continuous or Integer selected bounds | Replace the selected private bound by infinity and add its penalty row. Integrality remains hard; fractional integer endpoints keep their original units. |
| Binary selected bounds | Widen only to intrinsic `[0,1]`. Binary integrality and its intrinsic domain stay hard. A fixed binary can be repaired by paying for the selected fixing bound. |
| SemiContinuous or SemiInteger, untouched bounds | Preserve `{0} union [lower, upper]`, including the zero disjunct, and the backend's existing support limits. Ordinary row sides involving semis can be selected. |
| Semi-variable selected bounds | `Unsupported`; a conventional interval slack alone would incorrectly penalize the legal zero disjunct. |
| Active indicators, untouched bound dependencies | Copy and rebind all original metadata, gates, generated rows and captured-domain guards to the fresh private identity. Indicators remain hard and are independently validated. |
| Indicator-generated row selection or indicator-participating variable bound selection | `Unsupported`; these would invalidate the original logical semantics or captured big-M justification. Select an ordinary row instead. |
| Typed active globals | `Unsupported` until an explicit relaxation formulation is implemented. Inactive global tombstones are harmless and omitted from the fresh private model. |
| Empty expressions and constant contradictory rows | Supported, including models with no original variables. |
| No selected sides | Solve the hard model with zero first objective. Its infeasibility remains infeasibility. Optional phase two optimizes the original objective. |

Public snapshots undergo structural validation before construction, and the
private snapshot is validated again. Foreign, absent or deleted selectors,
duplicate selections of the same side, nonfinite selected sides, invalid side
enumerators, and nonpositive/nonfinite weights return `InvalidModel`. The API does
not repair malformed model structure or contradictory lower/upper ordering.
Nonempty primal starts return `Unsupported` until private slack mapping is
implemented. Models that require continuous penalty slacks need a numerical
backend supporting them; requesting the finite-domain Native backend cannot
silently change those slacks' domain.

## Budgets and incomplete outcomes

A single end-to-end monotonic budget covers construction, both solves, validation,
and reporting. Remaining time decreases between stages, and both stages share a
cancellation token. No candidate returned after the total budget stops is
promoted. A node limit can be used for a single-stage repair; two-stage node
limits are `Unsupported` until consumed-node accounting is available across the
backend boundary. Zero time or node budgets stop immediately.

Inspect status and evidence flags separately:

| Outcome | `has_repair()` | `minimum_violation_established` | `original_objective_optimized` |
| --- | --- | --- | --- |
| First stage completed, no phase two requested | true | true | false |
| Both stages completed | true | true | true |
| First stage limited, with an independently validated timely candidate | true | false | false |
| Second stage limited or unbounded, with a retained valid candidate | true | true | false |
| Total deadline/cancellation reached before promotion | false | false | false |
| Hard constraints infeasible in first stage | false | false | false |

Malformed witnesses, inconsistent bounds, or an apparent optimum with an open
independently recomputed gap produce `NumericalFailure`. A forged cached gap field
cannot establish completion. A later oracle's false infeasibility claim conflicts
with a known retained witness and is reported as numerical failure.

## Correctness checks

`test/optimize/relaxation.cpp` includes independent exhaustive integer arithmetic
for weighted repairs; objective ties resolved in both senses with negative
offsets; penalty-priority changes; continuous, fractional-integer-bound, binary,
semi and hard-indicator cases; constant contradictions; hard infeasibility and
unbounded second objectives; tombstones; malformed selectors/snapshots; explicit
unsupported combinations; source immutability and private handle provenance.

A second compile mode, `GECODE_RELAXATION_TEST_FAKE_SOLVER`, replaces only the solve
oracle. It deterministically checks first/second-stage interruption and
cancellation, invalid witnesses, false objective values, forged zero gaps,
inconsistent/missing/open bounds, bad identity/active masks (including interrupted
results), honest and forged objectives with large offset cancellation, and false
infeasibility without sleeps or runtime-sensitive timing assumptions. Compile it
with `model.cpp`, `result.cpp`, `validate.cpp`, `constraints.cpp`, `globals.cpp`,
`workflow.cpp`, and `relaxation.cpp`, omitting the real `solve.cpp`.

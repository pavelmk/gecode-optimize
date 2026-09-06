# Continuous LP observations: O1

`solve_lp_observed` returns an ordinary owning `SolveResult` plus an immutable
`shared_ptr<const LpObservations>`. `SolveSession` has the same overloads. The
observation artifact owns the exact historical `ModelSnapshot`; source handles,
revision, names and tombstones survive edits, reset, and model/session destruction.
No `SolveResult` layout or ordinary solve API changed.

This first implementation accepts **original Continuous linear models** through
HiGHS with `Guarantee::Numerical`. Auto selects that same backend. Native, Exact,
Certified, any active integer/binary/semi variable (including fixed integers),
indicators, and native globals return explicit Unsupported; no relaxation,
conversion of variable types, or automatic fallback occurs. The model is validated
and admitted before a persistent backend is mutated. Missing HiGHS is also
explicit Unsupported. A malformed model or observation tolerance is InvalidModel.

```cpp
#include <gecode/optimize/lp_observations.hpp>
#include <gecode/optimize/session.hpp>
using namespace Gecode::Optimize;
Model model;
auto x = model.add_continuous();
auto y = model.add_continuous();
auto demand = model.add_row({{x, 1}, {y, 1}}, 4,
                           std::numeric_limits<double>::infinity());
model.minimize({{x, 2}, {y, 3}}, 7);
auto observed = solve_lp_observed(model);
// Check the solve status and each group's state before using optional fields.
if (observed.observations &&
    observed.observations->dual_point().state == LpObservationState::Available) {
  double demand_dual = *observed.observations->row(demand).dual; // 2
  double y_reduced_cost = *observed.observations->column(y).reduced_cost; // 1
  (void)demand_dual; (void)y_reduced_cost;
}
```

## Groups and original coordinates

The primal row, dual point, and basis groups independently report NotRequested,
Available, Unavailable, or Rejected with a typed reason and message. Missing data
is never represented by zero. Raw vector length/identity errors and failed
numerical checks are distinguished from absent backend data. Invalid input or
allocation failure can prevent creating an artifact altogether.

* `rows()` and `columns()` retain original slot counts, including inactive
  tombstones. Handle accessors reject foreign IDs, tombstones, and out-of-range
  slots. Backend row/column maps are checked against the exact active source.
* Original row activities and signed lower/upper slacks are recomputed from the
  source matrix and validated primal values. An infinite bound side has no slack.
  Tiny negative slacks remain signed; they are not silently clipped.
* Duals and reduced costs satisfy the original objective convention
  `A^T pi + r = c`, for both minimization and maximization. HiGHS already restores
  its public solution to the passed model after presolve and objective-sense
  conversion. The adapter scatters those coordinates back to original slots.
* A feasible constant row omitted by backend conversion still receives an
  independently recomputed activity/slacks and a zero dual marked
  `DerivedConstantRow`. The other row duals are marked `Backend`.
* Basis status is a typed copy, with original-bound position, dimension, and
  basic-count checks. It requires both backend basis and info validity flags.
  The entire basis group is unavailable if an active constant row was elided;
  the implementation does not invent a full original basis. No independent
  nonsingularity or numerical conditioning claim is made.

Primal row observations require an independently validated finite source point.
Duals and basis initially require a timely final Optimal primal point and valid
backend info/primal flags; duals additionally require valid feasible dual flags.
An infeasible or unbounded solve does not produce an O1 ray or dual certificate.
An empty model solved without a backend call can have an available empty primal
row group, while its dual and basis groups are unavailable (`NoBackendSolve`).
`duals=false` and `basis=false` suppress their respective requests/publication.

## Independent numerical KKT checks

The checker uses original rows, costs, bounds and source values, rather than the
backend's presolved/packed matrix or its reported residuals. It checks:

1. Original primal feasibility and objective consistency.
2. Dual normal-cone signs at finite row/column bounds.
3. Stationarity `s*c - A^T(s*pi) - s*r`, where `s` is +1 for min and -1 for max.
4. Complementarity against the endpoint selected by each signed multiplier.
5. The signed normalized primal-minus-dual gap, with the common objective offset
   cancelled **before** accumulation.

Accumulation uses checked compensated `long double` arithmetic. Uncollapsed sum
and correction components flow into slack, stationarity, complementarity and
basis checks, including platforms where `long double` has double precision.
A nonzero multiplier requiring an infinite endpoint prevents a finite dual
objective/gap; the checker never treats that product as zero. Overflow,
nonfinite entries, malformed dimensions or coordinate maps reject publication.

Check tolerances are explicit, finite, nonnegative absolute quantities in
original units. Defaults are `1e-7` for dual feasibility and stationarity,
`1e-6` for complementarity and objective gap. The primal check uses the solve's
feasibility tolerance. Effective backend primal/dual tolerances are recorded
when obtained; they do not replace the independently requested check tolerances.
Residuals and signed gap are retained without clipping, including a small
negative gap accepted within absolute tolerance. Large objective offsets cannot
hide a meaningful gap by rounding both reported objective scalars together.

These are **numerical observations**, not exact certificates. An accepted KKT
report and its `dual_objective_estimate` do not strengthen the ordinary result's
guarantee or overwrite its backend best bound. A rejected dual or basis group
also does not erase an otherwise valid ordinary primal solve result.

## Budgets and repeated sessions

One shared monotonic budget starts before source snapshot copying and covers
conversion, backend execution, passive collection, independent checks, and raw
capture destruction. Public getters do no solver work. The collector uses only
current `getSolution`, `getInfo`, `getBasis`, and option values; it does not call
ray, ranging, basis factorization or extra optimization routines.

O1 chooses a conservative whole-call publication policy: if the final budget
checkpoint detects cancellation/time/node exhaustion, **all observation groups
are cleared**, with requested groups Unavailable/Interrupted and NotRequested
groups unchanged. This also clears groups that completed earlier. The timely
independently validated ordinary primal incumbent is retained, and the solve's
termination reflects the limit. The final gate runs after raw capture vectors
have been destroyed. A private deterministic test cancels at this boundary,
without sleeps or production hooks. Budget enforcement is cooperative; memory
allocation/destruction and solver calls are not forcibly preempted.

Every call creates a new artifact and new raw vectors. Limited/error solves
cannot expose the prior call's duals or basis. Session edits compare source
content and compact mappings, not only revision numbers; updated costs, bounds,
rows, sense or offset are reflected in the new artifact. Session basis reuse
remains internal and does not imply that the new result has an exportable basis.

## Verification and remaining scope

`test/optimize/lp_observations.cpp` checks real HiGHS analytic min/max/ranged-row
solutions, constant-row scattering, tombstones and duplicate names, historical
ownership, same-revision snapshot edits, repeated observed/ordinary session
calls, disabled groups, missing backend/admission, infeasible and unbounded
models, cancellation and malformed input.

`test/optimize/lp_observations_checks.cpp` exercises the pure private checker with
known primal/dual data and corrupted flags, IDs, revisions, masks, vector lengths,
NaNs, infinities, basis statuses, stationarity/sign/complementarity/gap failures,
large-offset and `1e16 + 1 - 1e16` cancellation, and post-collection cancellation.
It never substitutes fake data into a production solve. The private detail
header is not installed.

The separate [basis submission API](LP-BASIS.md) now provides owning basis starts;
the observation operation itself remains passive. Rays, sensitivity/ranging,
MIP relaxation observations, QP observations and exact dual proofs remain outside
O1. The subsequent research and
implementation boundaries are in [LP-OBSERVATIONS-DESIGN.md](LP-OBSERVATIONS-DESIGN.md).
Bindings use separate owning observed-result handles and copied ordinary results;
the public C++ artifact contains no borrowed backend memory.

The [C/Python guide](BINDINGS.md#original-coordinate-lp-observations) documents
the installed binding surface. One [FAST](FAST-REGRESSION.md) case checks
analytic min/max objectives, original duals, reduced costs, slacks and basis/KKT
availability. Completed integrated and installed-consumer checks are recorded
in [validation](VALIDATION.md).

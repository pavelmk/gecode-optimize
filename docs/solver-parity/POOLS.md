# Solution pools over finite discrete projections

`solve_pool` returns distinct assignments to a specified finite Integer/Binary
projection. Each completed optimization selects the best remaining projection
class under the original scalar objective. Variables outside the projection may
have many feasible completions; the pool returns one optimal completion per
selected class, not all of those assignments. Continuous recourse is supported
by HiGHS. Tied classes have unspecified order.

```cpp
#include <gecode/optimize/pool.hpp>
using namespace Gecode::Optimize;

Model model;
auto open = model.add_binary("open");
auto production = model.add_continuous(0, 10, "production");
model.add_row({{open, -10}, {production, 1}},
              -std::numeric_limits<double>::infinity(), 0);
model.maximize({{production, 2}, {open, -3}});
PoolOptions options;
options.projection = std::vector<Variable>{open};
options.max_solutions = 3;
options.solve.time_limit_seconds = 10;
auto pool = solve_pool(model, options);
// Two classes: open=1, production=10, objective=17;
//              open=0, production=0, objective=0.
// A subsequent infeasibility solve establishes that no other class remains.
for (const auto& entry : pool.entries) {
  const double quantity = entry.solution.value(production);
  const bool ranked = entry.rank_established;
  (void)quantity; (void)ranked;
}
```

## Identity, ranking, and completion

`PoolOptions.projection` defaults to every active Integer/Binary variable in
original slot order. Explicit projections retain caller order, must have unique
live original handles, and may leave other discrete variables outside the
projection. Every projected domain must have finite bounds. Non-projected
Continuous and Integer recourse may be unbounded; the selected backend must be
able to solve the resulting subproblem. Unbounded or ambiguous objective results
do not establish a ranked representative or pool exhaustion.

An empty projection is rejected for a model with active variables. In particular,
a continuous-only model is not called an enumerable pool. A model with no active
variables has one possible empty tuple; it contributes one representative if
feasible, or none if infeasible.

Each entry contains:

- An independently validated historical `SolveResult` using the original model
  identity, revision, variable slots and objective, including its offset and
  sense. Original model edits after the call do not change these stored values.
- Its canonical integer `projection_values` tuple in projection order.
- `rank_established`, indicating that this remaining-model solve completed with
  an independently checked objective and closed global-bound gap.

Historical entry `termination` is `Unknown`, and scalar global bounds and gaps
are cleared. A later-ranked representative is not an optimum of the unrestricted
original model. Its rank evidence lives in the pool result, not in an invented
original-model optimality claim. `attempts` retain each remaining solve's status,
objective, bound and guarantee, including failed or interrupted attempts.

`ranked_prefix` counts the established ordered prefix. An interrupted timely
candidate can be stored as one final **unranked** entry, after which enumeration
stops. A later independently feasible point that improves an earlier claimed
rank beyond the declared numerical allowance contradicts that evidence. This
returns `NumericalFailure`, clears rank flags, and retains historical feasible
values only. Other later interruptions or unsupported solver operations do not
revoke already established ranks.

| `completion` | Meaning | Pool `termination` |
| --- | --- | --- |
| `RequestedLimit` | `max_solutions` ranked representatives found; no extra exhaustion solve was performed | `SolutionLimit` |
| `Exhausted` | A definite infeasible remaining-model solve established that no further projection class exists | `Optimal`, meaning this pool workflow completed; the final attempt is `Infeasible` |
| `Incomplete` | Budget, ambiguity, unsupported class, numerical failure or other error stopped the workflow | The explicit stopping reason |

Even if the requested count happens to equal the total number of feasible
classes, reaching that count is not labeled exhaustion. Request a larger count
to allow the final infeasibility check. This is not a promise of commercial
solver solution-pool completeness over arbitrary mixed or real-valued models,
nor a heuristic diversity pool. The finite projection defines exactly what is
being distinguished and exhausted.

## Numerical and exact evidence

Each ranked solve requests zero backend absolute and relative MIP gaps. The
workflow checks original/remaining model feasibility, stable identity and active
slot masks, recomputes the original objective, and independently recomputes the
gap from the returned global bound. Cached gap fields cannot establish ranking.
All active integer values, including private binary witnesses, are rounded and
rechecked; canonical integers must lie inside their original interval without a
bound tolerance. Every canonical integer value and every projected domain endpoint must be exactly
representable with magnitude at most `2^53`, and projected width must not
exceed `2^53`.

`Guarantee::Numerical` with HiGHS is the default. Original row feasibility and
continuous values remain tolerance-qualified. Objective/gap and rank comparisons
use the greater of the requested absolute feasibility tolerance and 64 double
machine epsilons times objective/bound scale. Finite domain size does not turn
numerical backend infeasibility or optimality into an exact proof.

`Guarantee::Exact` requires explicit `Backend::Native`, and every resulting model
must fit that backend's exact finite-integer subset and arithmetic limits. Its
rank comparisons and closed-gap requirement allow no numerical discrepancy.
Native rejects continuous recourse and unsupported ranges or coefficients.
`Certified` is unsupported; no proof certificate is generated. Infeasibility and
rank evidence are obtained from the actual solver, with original-model witness
checks, rather than inferred from a search timeout or a requested entry count.

## Safe projection exclusions

After accepting a ranked tuple `v`, the private model adds a disjunction saying
that at least one projected variable differs. For an integer `x` with effective
bounds `L=ceil(lower)` and `U=floor(upper)`, possible witnesses are:

- If `v > L`: binary `b` and `x + (U-v+1)*b <= U`. Setting `b=1` requires `x<=v-1`.
- If `v < U`: binary `b` and `x - (v+1-L)*b >= L`. Setting `b=1` requires `x>=v+1`.

The sum of all witnesses is constrained to be at least one. Every differing
integer tuple admits a witness; the excluded tuple admits none. Non-projected
variables never enter these exclusions, so all completions of a tuple are
excluded together. A tuple whose projected domains are all singletons produces
a constant contradiction, allowing a subsequent infeasibility solve to establish
exhaustion. Coefficients are derived from actual finite bounds, checked for exact
integer representation, and never replaced with guessed large constants.

The original snapshot is copied, preserving slot identities and metadata.
Private witness variables and rows are appended only to that copy. They are
removed from historical entry values by original slot mapping before independent
original-model validation. The original `Model` revision and contents remain
unchanged. Structural validation treats public snapshots as untrusted.

Active indicators, active typed globals, SemiContinuous and SemiInteger variables
are explicitly unsupported in this initial pool workflow. Inactive metadata is
preserved. Existing linear Boolean rows and ordinary ranged rows remain hard.
Foreign, duplicate or deleted projection handles and zero `max_solutions` are
invalid input. Infinite, overly wide or continuous projected domains return
`Unsupported`.

## Budgets, starts, and checks

One monotonic deadline and cancellation token cover copying, all solves,
exclusions, validation and result construction. A candidate returned after the
shared budget stops is not promoted. Earlier accepted entries remain historical
results. Multiple-solve node limits are unsupported until the backend reports
cumulative consumed nodes; a requested pool of one can use a node limit.

An original primal start may be used for the first solve under the common start
contract. Subsequent starts are cleared because earlier assignments have been
excluded. Thread, seed and solver capability restrictions remain those of the
chosen backend.

`test/optimize/pool.cpp` compares min/max pools with exhaustive integer arithmetic,
checks partial projections and ties, verifies analytical continuous recourse,
exercises original history after edits, and covers constants, tombstones,
unsupported metadata/domains, exact Native when available, and missing-HiGHS
behavior. A fake solve mode, `GECODE_POOL_TEST_FAKE_SOLVER`, enumerates all private
integer/binary variables independently and checks the no-good formulations
without using the implementation's validator as its oracle. It also exercises
interruption, late cancellation, forged identity/masks/objectives/bounds, repeated
projections, ambiguous or witness-contradicted infeasibility, wrong guarantees,
large-offset cancellation and contradictory ranks.
Compile that mode with model/result/validate/constraints/globals/pool sources and
omit the real solve/native sources.

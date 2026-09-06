# Ordered linear objective workflow

`gecode/optimize/workflow.hpp` adds `solve_lexicographic` for a `Model` or owning `ModelSnapshot`. It solves linear objectives in the supplied order: the first entry has highest priority. There is no implicit sorting, blended-weight interpretation or Pareto-front enumeration.

```cpp
Model model;
auto x = model.add_integer(0, 4);
auto y = model.add_integer(0, 4);
model.add_row({{x, 1}, {y, 1}}, 2,
              std::numeric_limits<double>::infinity());

LexicographicObjective first;
first.objective = {{{x, 1}}, 2, ObjectiveSense::Minimize};
first.absolute_degradation = 1;
LexicographicObjective second;
second.objective = {{{y, 1}}, 0, ObjectiveSense::Minimize};

auto result = solve_lexicographic(model, {first, second});
// First optimum: x+2 = 2. The permitted degradation gives x+2 <= 3.
// Second optimum: y = 1, with final x = 1.
```

Objective expressions follow the same canonical structure as snapshots: finite nonzero coefficients, ascending unique variable slots, active same-model handles and a finite offset. Invalid objectives anywhere in the list are rejected before the first solve. An empty list is invalid. Every original model constraint remains active; its original scalar objective is replaced privately for each phase. The original model and revision are never mutated.

## Meaning of completion

Both native MIP gap targets are forced to zero for each phase, regardless of `SolveOptions.relative_gap` and `absolute_gap`. A phase advances only after the numerical backend reports `Optimal`, supplies an independently validated solution and provides a finite agreeing global bound. Bound discrepancy must not exceed `max(feasibility_tolerance, 64 * double_epsilon * max(1, abs(objective), abs(bound)))`. The objective is independently recomputed and compared to the stage report; the gap is recomputed from that objective and the supplied bound, rather than trusted from a cached gap field. Missing/inconsistent bounds or objective disagreement stop the workflow with `NumericalFailure`.

The guarantee remains **Numerical**. `termination == Optimal` and `completed_numerically()` mean all ordered stages completed under these numerical checks and the requested degradation/feasibility tolerances. They do not certify exact lexicographic optimality. Exact or certified policy requests are explicitly `Unsupported`.

For achieved stage value `v`, permitted degradation is

`absolute_degradation + relative_degradation * abs(v)`.

Minimization creates an upper objective threshold; maximization creates a lower threshold. A later stage may use the entire permitted degradation. Consequently its final objective vector can differ from earlier stages' attained objective values. The last objective's degradation is checked for validity but has no later stage on which to act.

Locks are formed from independently accumulated linear terms, with offsets included in the degradation calculation. Linear lock activity and total objective activity use separate compensated sums. The total includes the offset in its accumulator before the terms, preserving small residuals when a large linear subtotal cancels against the offset, including on platforms where `long double` has the precision of `double`. This avoids subtracting a large offset from an already rounded reported objective. Conversion to a double row bound rounds toward a tighter region. Unsupported overflow, an unrepresentable lock that loses the incumbent, or a backend numerical-range rejection ends the workflow explicitly; the implementation never substitutes infinity and drops the lock.

Independent checks evaluate the final candidate against the original model, every accumulated lock row and the original objective retention thresholds. Feasibility tolerances still apply in original units, including at zero requested degradation. This is numerical validation rather than exact arithmetic.

## Results and interrupted work

- `stages` contains each attempted phase's numerical `SolveResult`, its input index/name, completion flag and optional retention threshold in original objective units. These stage results refer to the original variable identities but to private phase objectives and lock rows.
- `completed_stages` counts phases accepted for progression. No phase is promoted solely because it has a good incumbent.
- `final_solution` owns the latest timely independently checked original-model feasible assignment, including deleted slots. Its scalar objective evaluates the **original model objective**. That objective need not have been optimized, so `final_solution.termination` is `Unknown` and no scalar bound/gap is advertised. Read the workflow's termination and phase results instead.
- `objective_values` evaluates every requested objective at `final_solution`, in priority order. It is empty when no validated solution is available.
- A limited or failed phase stops the workflow immediately. A timely feasible incumbent can be retained without claiming that the phase is complete. Later infeasibility contradicting an already validated retained assignment is reported as `NumericalFailure`, not as proof that the original model is infeasible.

One outer monotonic budget and cancellation token cover snapshot copying, structural checks, all solves, lock construction and candidate checks. Every phase receives only the remaining time. Limits remain cooperative inside backend calls; elapsed time can exceed a deadline, but a phase returning after the outer deadline is not promoted and its new candidate is discarded. A previously timely validated solution remains available. Zero time or pre-cancellation stops before solving.

Node limits are supported for a single objective through the existing adapter. Any node limit on a multi-stage request returns `Unsupported` until consumed-node reporting supports a true aggregate budget. Threads, numerical ranges and other backend restrictions remain those of `solve`.

An explicit primal start is used only for the first phase. Later phases clear it because a start feasible for the original constraints may violate a new objective lock. This initial workflow does not transfer backend bases or reuse a search tree between phases.

## Validation coverage

The standalone workflow test uses exhaustive independently generated integer assignments as an oracle for conflicting objectives, input-order priority, mixed min/max senses, offsets and absolute/relative degradation. It also checks continuous models, large-offset lock construction, large-term/offset cancellation residuals, empty/tombstoned models, original-model immutability, infeasibility, a later unbounded phase, zero deadlines, cancellation, node-budget restrictions, unsupported guarantees, malformed objectives and precision overflow. This is correctness testing, not performance measurement.

The same test file has a `GECODE_WORKFLOW_TEST_FAKE_SOLVER` mode, linked with `model.cpp`, `result.cpp`, `validate.cpp`, `workflow.cpp` and the validation dependencies (`constraints.cpp`, plus `globals.cpp` where present), but without `solve.cpp`. Its deterministic backend exercises an incomplete second phase, cancellation during a phase, missing optimum bounds, a candidate violating a prior lock, contradictory later infeasibility, correctly reported cancellation residuals, and forged objective/bound values with cached zero gaps. It checks diminishing per-phase deadlines and cleared later starts without sleeps or timing-dependent assertions. This coordinator mode is also suitable for full ASan/UBSan instrumentation of the owned workflow and foundation sources.

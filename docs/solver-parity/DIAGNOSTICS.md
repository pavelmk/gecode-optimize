# Numerical conflict diagnosis

`gecode/optimize/diagnostics.hpp` provides `analyze_conflict(model, options)` for
linear LP/MILP models. It first asks a feasibility oracle whether the original
constraint system is infeasible. Only after an unambiguous numerical infeasible
result does it run a deterministic deletion filter. The original model, its
objective, revision, and stable handles remain unchanged.

```cpp
#include <gecode/optimize/diagnostics.hpp>
#include <limits>
using namespace Gecode::Optimize;
Model model;
auto stock = model.add_continuous(0, 10, "stock");
model.add_row({{stock, 1}}, 11, std::numeric_limits<double>::infinity(), "demand");
ConflictOptions options;
options.solve.time_limit_seconds = 30;
options.retain_deletion_witnesses = true;
auto conflict = analyze_conflict(model, options);
// On completed analysis: the demand row and stock's upper bound form the
// conflict. Its lower bound is unnecessary and is removed from the result.
if (conflict.irreducible()) {
  for (const auto& group : conflict.groups) {
    // Inspect group.name, kind, and original row/variable/indicator handles.
    // group.deletion_witness satisfies the conflict with this group removed.
  }
}
```

## What is minimal

The result is **group-minimal**: deleting any one reported group makes the
remaining conflict numerically feasible. This is not a minimum-cardinality
conflict, and groups containing several conditions are not individual IIS
members. Different deletion orders can produce different valid conflicts.

| Group | Included conditions | Removing the group |
| --- | --- | --- |
| `Row` | Both finite sides of one original ranged row | Removes that whole row |
| `LowerBound` | A continuous/integer variable's finite lower bound | Sets its lower bound to negative infinity |
| `UpperBound` | A continuous/integer variable's finite upper bound | Sets its upper bound to positive infinity |
| `Integrality` | One ordinary integer variable's integer restriction | Makes it continuous, preserving retained numeric bounds |
| `VariableDomain` | A binary or semi-variable's entire domain, including bounds and integer restrictions | Makes it continuous and free |
| `IndicatorComponent` | Connected original indicators, their generated rows, and the full domains of every participating variable and auxiliary gate | Deactivates those indicators and generated rows, and makes their participating variables continuous and free |

Unbounded continuous variables need no domain group. Deleted variable and row
slots remain tombstones. Ordinary Boolean-helper rows are treated as rows.
Variable-domain groups preserve semi-variable semantics `{0} union [lower,upper]`
while retained; removing one removes the entire disjunction, not just its
nonzero interval. Ordinary integer bounds are kept as their original numeric
endpoints: relaxing integrality of `[0.25,0.75]` permits real values in that
interval rather than rounding it into an empty integer interval.

Indicator components connect indicators sharing any activator, original term
variable, or auxiliary gate, transitively. Their component groups include every
such variable's complete original domain. This deliberately coarser granularity
keeps captured-domain guards and safe big-M lowerings intact whenever an
indicator remains active. It also handles exposed gates used by other indicators.
No generated indicator row is presented as an independent original logical
cause. `indicators`, `generated_rows`, and `grouped_variables` provide the full
attribution. A component can be an irreducible one-group conflict even when a
smaller individual logical conflict exists inside it.

The deterministic deletion order is original ordinary row slot order, then
variable slot order (lower bound, upper bound, integrality, or whole domain),
then indicator components ordered by their lowest participating variable slot.
Each attempted deletion either permanently removes an infeasible subset's
unnecessary group or retains a group with an independently checked feasible
deletion witness. All deletions are relaxations, so witnesses remain feasible
after later unnecessary groups are removed. When witness retention is enabled,
they are also independently rechecked against the final reported subset.

## Status, evidence, and budgets

`ConflictStatus::Feasible` returns an independently validated feasible assignment
in `feasible_witness`, using original variable slots. The original objective is
irrelevant: every private oracle model uses a constant zero objective. An
unbounded original optimization problem can therefore have a feasible
constraint system and return `Feasible` here.

`Irreducible` means the filter finished and every retained group's necessity was
established. `infeasibility_established` records whether an unambiguous numerical
infeasible oracle result has been obtained. Before that point, a stopped or
ambiguous analysis is `Unknown` and reports no conflict. Afterwards it is
`Incomplete` and reports the last numerically established infeasible subset;
that subset must not be called an IIS. Its `necessity_verified` flags identify
groups for which deletion feasibility has already been checked. Backend
unavailability, invalid input, and failures have explicit statuses. `termination`
is the stopping reason, or `Optimal` for completed feasibility and `Infeasible`
for completed conflict diagnosis.

All evidence is `Guarantee::Numerical`, using the backend's numerical
infeasibility determination and independent original-unit feasibility and
integrality tolerances for witnesses. No exact proof, rational certificate,
minimum-size guarantee, or solver-native conflict refiner is claimed.
`Exact` and `Certified` requests return `Unsupported`.

One outer monotonic budget covers copying, partitioning, every oracle solve,
and witness checking. Each solve receives only the remaining time and the same
cancellation token. Any interrupted, ambiguous, invalid, or failed oracle stops
analysis; even a limited oracle carrying a feasible incumbent is not advanced.
An oracle returning after the outer budget stops cannot establish a new fact.
Limits are cooperative inside backend calls and elapsed time can exceed the
requested limit. A node limit is explicitly unsupported because cumulative
backend node consumption is not yet reported. Sparse starts are ignored; other
options are validated and native gap targets are forced to zero.

The filter needs at most one initial feasibility solve plus one solve per
candidate group. Repeated model copies and numerical solves make this suitable
for diagnostic work, not a replacement for a specialized large-model conflict
refiner. Optional deletion witnesses can occupy one full original-slot vector
per retained group; they are omitted by default. No reference assignments or
cross-model witness caches are used.

## Checks

The normal test executable covers contradictory rows, bound/row attribution,
integer-only infeasibility, whole binary/semi domains, constant contradictions,
feasible and originally unbounded models, tombstones, indicator components,
untouched original snapshots, and independent reconstruction and validation of
every retained deletion witness. The separate
`GECODE_DIAGNOSTICS_TEST_FAKE_SOLVER` mode supplies a deterministic oracle to
test interrupted and ambiguous results, late cancellation, invalid witnesses,
contradictory statuses, decreasing shared deadlines, and retention of the last
established infeasible subset without timing-dependent sleeps.

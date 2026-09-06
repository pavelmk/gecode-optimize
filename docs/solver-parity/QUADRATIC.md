# Explicit bounded continuous quadratic optimization

`quadratic.hpp` adds `QuadraticModel`, immutable owning `QuadraticSnapshot`, and
`solve_quadratic`. It does not change `Model`, `solve()`/Auto, native solving, or
any existing workflow. A quadratic wrapper/snapshot cannot bind to their linear
model overloads. This is an initial convex/concave QP capability, not MIQP, QCP,
arbitrary-Hessian, or general nonlinear support.

## Model and result contract

All original variables are continuous with explicit finite bounds. Constraints
are ordinary linear rows, with finite or infinite row sides. The objective is a
linear part plus strictly positive weighted squared affine forms for minimization,
or the linear part minus those forms for maximization:

```cpp
#include <gecode/optimize/quadratic.hpp>
using namespace Gecode::Optimize;
QuadraticModel model;
auto x = model.add_continuous(-5, 5, "x");
auto y = model.add_continuous(-5, 5, "y");
model.add_row({{x, 1}, {y, 1}}, 1, 3);
model.minimize_squares({{{{x, 1}}, -2, 1, "x target"},
                       {{{y, 1}}, -1, 2, "y target"}});
const auto result = solve_quadratic(model);
if (result.result.has_solution()) {
  const double value = result.result.value(x);
  (void)value;
}
```

`maximize_concave_squares` makes the negative-square convention explicit. Both
objective setters replace the complete objective, canonicalize duplicate terms,
and advance the revision even for quadratic-only changes. They stage allocating
work before committing; malformed input leaves the previous model/revision intact.
Removing a variable referenced by a row, linear objective, or square is rejected.
Deleted slots remain tombstones. Wrapper moves preserve identity; moved-from
wrappers reject access except their zero identity/revision. Snapshots own their
history after edits/destruction, and copying or moving a snapshot retains a usable
immutable view. There is no public conversion to the private linear core model.

Result identity, active mask, values and handles refer to original wrapper slots.
Auxiliary variables/rows are private. `validate_quadratic` independently checks
original rows/bounds, objective and gradient; it establishes numerical primal
validity, not optimality. `QuadraticResult.result.solution_validated` is set only
for a checked original quadratic candidate. Raw lifted objective/duals are never
presented as an independent proof.

The following are unavailable by construction or return `Unsupported`: unbounded
original variable domains, integer/binary/semi domains, indicators/globals,
arbitrary Hessian input, quadratic constraints, native backends, Exact/Certified
requests, primal starts, node quotas, multiple workers and nonzero random seeds.
The first interface does not support QP sessions, pools, repair, lexicographic
retention, diagnostics, LP/MPS I/O or CLI integration. Additive C/Python bindings
use distinct model/result handles; see [the binding contract](BINDINGS.md#distinct-continuous-quadratic-models). Existing typed entry
points reject the wrapper rather than solving only its linear part. A future
quadratic objective retention constraint would require QCP support.

## Lowering, acceptance and numerical bounds

Write `s=1` for min and `s=-1` for max. The backend always minimizes
`F=s*offset+(s*c)'x+sum w*(a'x+b)^2`. Each square receives a private continuous
residual `z` with `z-a'x=b`; its sole Hessian entry is `Qzz=2*w` under HiGHS's
`0.5*x'Q*x` convention. This diagonal Hessian is PSD by construction, including
singular cases. The implementation does not expand a rounded Gram matrix.

The uploaded LP coefficients, bounds, costs, dimensions and Hessian are checked
against the intended representation before running. Nonzero matrix/Hessian values
at or below `1e-12`, matrix/Hessian magnitudes at or above `1e15`, finite bounds,
affine offsets or linear costs at or above `1e20`, overflow and incompatible
HiGHS index sizes require explicit rescaling and return `Unsupported`. Private
residuals may have free domains; original variables must have finite boxes.

A vendor `Optimal` status is accepted only after these independent gates:

- Original numerical primal feasibility, compensated original objective/gradient,
  and lifted residual/objective agreement.
- Original normalized row/bound dual signs and complementary slackness. A positive
  row dual selects a finite lower side, a negative one a finite upper side.
  The backend already minimizes `F`, so its duals are already normalized.
- Stationarity against the original unregularized objective, with tolerance
  `stationarity_tolerance * (1+abs(gradient)+abs(bound dual)+sum abs(A*row dual))`.
  Complementarity uses an absolute original-unit tolerance.
- An independently enclosed lower bound on `min F`, plus an offset-free upper
  enclosure on the primal-minus-bound gap no larger than `optimality_tolerance`.

The defaults are stationarity/complementarity `1e-7` and absolute optimality
acceptance `1e-6`. `optimality_tolerance` is separate from the common solver's
requested search gaps: this QP adapter has no early relative/absolute search-gap
cutoff. It requires HiGHS optimal completion and its own numerical acceptance.
Large objective constants do not relax any of these gates.

For any finite tangent value `t`, `w*z*z >= 2*w*t*z-w*t*t`. Combining these
inequalities with sign-valid original row multipliers produces an affine lower
bound. Minimize that affine residual over every original finite variable box.
This remains sound for imperfect duals and singular curvature. The checker uses
outward `nextafter` enclosures of each binary64 arithmetic operation; it does not
subtract a guessed epsilon or invert a Hessian. Overflow or unsupported arithmetic
makes the bound unavailable. Production does not change the process rounding mode.
IEEE binary64, nearest rounding, preserved subnormals and no fast-math are required;
`quadratic_capabilities().available` reflects that arithmetic environment as well
as backend availability. Missing HiGHS has no fallback.

The original offset cancels algebraically before computing
`checks.gap_upper_bound`. `SolveResult.absolute_gap` instead uses the independently
outward-rounded full bound and rounded full objective. Near a huge offset, its
reported gap can therefore be larger than the offset-free acceptance gap. Both
are retained honestly. A regression with offset `1e16` passes the tight centered
gap while retaining a full scalar gap of at least one unit; it does not invent a
zero scalar gap. Contradictory bound ordering becomes `NumericalFailure`, with
scalar bound/gaps unavailable, never a clamped zero.

All accepted solves retain `Guarantee::Numerical`: primal feasibility and KKT use
tolerances, even though the finite-box lower-bound enclosure is independently
checked. A feasible original point can survive an iteration/numerical failure;
that is not an optimality claim. An infeasible vendor status is explicitly a
numerical conclusion without an independently checked Farkas certificate, and a
valid raw primal witness disproves it even if the vendor declined `value_valid`.
A feasible finite-box QP cannot be unbounded; such a backend report is a numerical
failure. Nonfinite, foreign, stale or malformed raw evidence is rejected.

## Budgets and solver setting

A shared monotonic budget covers snapshot copying, compilation/upload, backend
work, original checking and publication. A zero deadline/pre-cancelled token stops
before solving. Late candidates and bounds are excluded. Limits are cooperative:
the pinned active-set path does not forward the general callback to its QP loop,
so cancellation is checked before/after backend work, not promised to preempt a
factorization. The remaining time is passed to HiGHS. The default QP iteration cap
is 100,000. Auxiliary/nonzero caps are checked before growing backend structures;
allocation failures return `MemoryLimit` with original provenance.
The pinned active-set nullspace limit remains 4,000; factorization/nullspace
failures are reported as backend failures, not infeasibility or nonconvexity.

The initial runtime is pinned HiGHS 1.15.1's `qpasm`, one worker, zero seed, and
**zero diagonal regularization**, with no hidden retries. The pinned default is
`1e-7`, which perturbs the working objective. Reproducible comparison in
`test/optimize/quadratic.cpp` found:

| Original-model acceptance, macOS arm64 pinned build | Regularization 0 | Pinned default `1e-7` |
| --- | --- | --- |
| 360 min/max cases checked against exact rational 2-D KKT active-set enumeration | 360 accepted | 172 accepted; 188 rejected by the original checks |
| Six scaled rank-one cases, weights `1,1e-2,1e-4,1e-6,1e-8,1e-10` | 3 accepted | 4 accepted |

Both settings reach the iteration cap on the rank-one weights `1e-4` and `1e-6`
in this fixture/build. At `1e-8`, zero regularization fails the original KKT gate
while `1e-7` passes. These are explicit limitations, not solved instances or timing
results. Counts may vary with backend/platform arithmetic; every accepted result
must still pass the same gates. Broader accurate behavior favors zero for this
first slice; a later conditioning/retry policy needs its own budget and original
witness retention tests. The test-only regularization override is absent from
production and is not a supported runtime option.

## Validation evidence

The standalone tests cover:

- Immutable ownership/revision/mutation failure, foreign/tombstone handles, moved
  models/snapshots and compile-time rejection by existing linear/native/workflow
  entry points.
- 360 exact rational KKT oracle cases with both senses, plus analytic interior,
  equality, active bounds/rows, fixed/empty/constant objectives, singular curvature,
  a mixed curvature ratio of `1e12`, large offsets and infeasibility cases.
- 22,688 exact signed dyadic checks of interval sums/products using an independent
  arbitrary-width integer reference, plus 400 exact tangent/row-dual/box formulas,
  subnormal arithmetic, cancellation, overflow and changed rounding modes.
- Fake backend replies: wrong identity/revision/mask, malformed primal/auxiliary/
  objective/duals, false optimal/infeasible/unbounded statuses, interrupted primal
  retention, and huge constants masking a nonoptimal point. Deterministic hooks
  exercise cancellation before/after backend/checking and allocation failure.
- Core-only missing-backend behavior, production without test hooks, and fully
  instrumented ASan/UBSan foundation/QP/HiGHS builds. A separate fast-math build of
  the arithmetic checker verifies its fail-closed support gate.

`quadratic_bound.hpp` is a private implementation/test header; public clients use
`quadratic.hpp`, also included by `<gecode/optimize.hh>`. Both standalone and
combined packages install the public header and exclude the private checker.
CMake registers production, exact-bound, isolated coordinator and (GCC/Clang)
arithmetic-rejection tests; the last compiles only the checker with fast-math.
Installed consumers exercise the public solve or the backend-disabled response.
No performance/default-routing claim is made by these conformance runs.

Pinned implementation/source findings, derivation and primary algorithm papers
are in [QUADRATIC-DESIGN.md](QUADRATIC-DESIGN.md), including the HiGHS Hessian and
regularization code, Feldmeier's QP thesis, Forsgren–Gill–Wong active-set methods,
Boyd–Vandenberghe duality, and OSQP as a future differential oracle. Arbitrary
Hessians, unbounded original domains and stronger infeasibility certificates remain
separate research/verification gates.


## C and Python

The explicit wrapper is available through the version 1 C ABI and the Python
`QuadraticModel`, `WeightedSquare`, `QuadraticOptions`, `QuadraticResult` and
`QuadraticChecks` classes. These types preserve the finite-box, positive-square,
convex-min/concave-max scope and all numerical acceptance gates described above.
Ordinary linear models, sessions and result accessors cannot accept their handles.
[Binding examples and ownership rules](BINDINGS.md#distinct-continuous-quadratic-models)
cover atomic objective replacement, copied arrays, historical slot identities,
original checks, vendor diagnostics and explicit evidence availability.

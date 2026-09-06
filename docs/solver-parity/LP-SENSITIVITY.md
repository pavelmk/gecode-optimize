# O4: continuous LP coefficient and equality sensitivity

`analyze_lp_sensitivity` computes owning, original-coordinate intervals for one
specified optimal LP basis. The implemented parameters are a single objective
coefficient and the common RHS of an equality. Each interval varies that
parameter alone while retaining the selected basic entities and nonbasic bound
statuses. Every accepted interval is numerical data, not an exact certificate.

```cpp
#include <gecode/optimize/lp_sensitivity.hpp>

using namespace Gecode::Optimize;
Model model;
auto x = model.add_continuous();
auto y = model.add_continuous();
auto balance = model.add_row({{x, 1}, {y, 1}}, 3, 3);
model.minimize({{x, 2}, {y, 1}}, 7);
auto observed = solve_lp_observed(model);
LpSensitivityOptions options;
options.parameters = {LpObjectiveParameter{x}, LpEqualityRhsParameter{balance}};
auto analysis = analyze_lp_sensitivity(observed, options);
if (analysis.sensitivity) {
  const auto* entry = analysis.sensitivity->objective(x);
  if (entry && entry->group.state == LpSensitivityState::Available) {
    // For the y basis: coefficient x in [1, +infinity].
    // entry->interval has tagged endpoints, slope and numerical checks.
  }
}
```

The source operation is explicit. Analysis does not solve for missing
observations, submit or repair a basis, mutate an existing session, or choose a
different backend. An O2 basis solve can supply its observed child to select a
different source basis. Basis dependence matters even at an identical degenerate
optimum: with `x+y=0`, nonnegative variables and zero objective, the x-basic
basis permits coefficient x in `[-infinity,0]`; the y-basic basis permits
`[0,+infinity]`.

## Admission and scope

The input must be a numerical Optimal O1 result with immutable source data,
accepted primal/dual/KKT observations and an available complete basis. The
mutable outer result's status, owner, revision, masks, finite assignment and
objective are checked independently before factorization. The reference basis
point is then reconstructed and checked against the source assignment. Unknown
statuses, foreign/deleted request IDs, duplicate requests, invalid tolerances,
empty requests and unsupported backend selections fail explicitly.

All active source variables must be Continuous. Active indicators/globals,
quadratic/nonlinear data, MIP/semis, elided constant rows, zero-row/column sources,
singular or changed bases, and missing HiGHS are not admitted. Auto uses the
HiGHS numerical factorization route; Native is Unsupported. The existing HiGHS
conversion admission is reused, including its finite coefficient/bound limits;
this operation does not introduce a weaker model conversion.

Ranged, one-sided and free source rows and infinite unvaried bounds may restrict
supported intervals. Requests to vary inequality/ranged-row sides, variable
bounds, matrix entries or multiple parameters simultaneously are not in this
slice. An equality request moves both finite equal bounds together. Fixed
columns, free nonbasic columns, and redundant equalities are handled explicitly;
a basic equality logical yields a singleton RHS interval. A singleton is valid
data, distinct from unavailable data.

## Private factorization and original checks

The implementation uses pinned HiGHS 1.15.1 at
`04024d701f79feb8e2f18bc3df0dffc04ef05088` in a new private instance. It loads the
original admitted LP, sets a complete **non-alien** basis, and calls
`getBasicVariables` to form an inverse from that known basis. It requires an
invert, the exact original requested statuses and a fully checked original
entity ordering. Singular factorization is rejected without repair. The private
instance must retain Notset model status and invalid solve information.

The backend interface exposes only factor-system solves. Production uses
`getBasisSolve` and `getBasisTransposeSolve`; it never calls optimization
`run`, `solve_lp_observed` or `getRanging`. The original solve result and its O1
observations remain unchanged. A factor order is published only after all
count, index, owner, uniqueness, mask and basic-status checks succeed.

The combined matrix is `[A,I]`, with logical coordinates `z=-A*x`. Original row
lower/upper statuses swap for the logical variable, and logical bounds are
`[-row.upper,-row.lower]`. Objective sense is normalized during algebra and
mapped back once. Each returned FTRAN/BTRAN vector is independently checked
against the original, unscaled basis matrix. No second scaling or public-row
sign correction is applied to HiGHS's original-coordinate linear-system output.

The reconstructed reference point must pass original rows/bounds, agree with
the source assignment, and pass independent numerical stationarity, dual-sign,
complementarity and offset-free gap checks. Compensated accumulation includes
the objective or reduced-cost anchor in the same sum as all contributing terms;
large objective offsets and `10^16 - 1 - 10^16` do not erase a residual by
prematurely collapsing an intermediate dot product. Long double is used where
the platform provides extra precision; correctness does not assume it does.

For a coefficient, the unchanged primal basis point and the derivative of
nonbasic reduced costs define the interval. Fixed nonbasic variables impose no
dual-sign condition; free nonbasic variables impose both signs. For an equality
RHS, original finite sides constrain the affine basis point; the derivative of
the selected moving logical bound is subtracted from its own inequality.

No small derivative is silently clipped to zero. Finite endpoints are absolute
parameter values and are rechecked after conversion to double. Overflow of a
finite endpoint is rejected, never reported as infinity. An infinite endpoint
is tagged and accepted only when every affine inequality permits that direction.
Numerical tolerances qualify residual/endpoint checks; they do not deliberately
widen the computed interval. Numerical errors can make a particular request
Unavailable/Rejected even when other requests pass. A residual test is not a
condition estimate or a forward-error certificate.

The source investigation and commercial API comparisons are retained in
[LP-SENSITIVITY-DESIGN.md](LP-SENSITIVITY-DESIGN.md). In particular, raw HiGHS
basic-variable bound movement is not renamed as a Gurobi/CPLEX bound sensitivity
attribute; those operations have different semantics.

## Ownership, availability and budgets

The artifact owns a copy of the exact original outer result, shares its immutable
O1 observations, and owns its selected basis. Original slot masks include
tombstones. Lookups reject foreign/deleted historical handles and return null
for a live historical entity that was not requested. Model or session edits,
reset and destruction never update an existing artifact. Accessors do no
factorization, optimization or other backend work.

Complete means every requested interval passed; Partial means some per-request
checks failed. Neither status upgrades the numerical qualification. Whole-call
time/cancellation, resource, allocation and cleanup failure clear **every**
interval and every Available state, including ranges computed before a Partial
outcome. Original solve history, a previously validated factor order and
completed check diagnostics may remain present. Their presence does not imply
interval availability. Optional residuals remain absent until calculated;
default false diagnostic flags do not establish that a check ran.

A single monotonic allowance starts before option validation and source copying.
It includes admission, private factorization, system solves, checking and final
backend/vector-capacity release. Cancellation uses the same shared token.
Factorization and triangular solves have cooperative uninterruptible regions:
the operation checks before/after calls and clears availability if the final
allowance expired, rather than claiming a hard process-kill deadline. Invalid
options retain their input rejection even if an invalid negative deadline or an
already-cancelled token is also supplied.

Caps cover active rows, columns, nonzeros, request count, `m*m` factor admission,
logical retained slots, coordinator visits and attempted factor-system calls.
They are not an exact RSS, CPU instruction or hidden backend-iteration count.
`basis_solves` is charged once immediately before a call to the private factor
interface; a failing call can stop before the HiGHS accessor is reached.
`factor_setup_attempted` is separate. `max_work=0` on a nonempty input stops
before factorization with ResourceLimit/IterationLimit. Remaining stop reasons
and preflight rejections are reported explicitly; no limit triggers a retry,
relaxation or different basis.

## Verification of this slice

Local correctness runs use Apple Clang 17, C++17, assertions enabled, and the
matching frozen Regular/O1/O2 facade dependencies in
`build/regular-bindings/{normal,off,sanitize}`. The private conversion bridge and
new sources were freshly compiled; no older facade was substituted for the new
implementation. Normal and full ASan/UBSan runs use the pinned matching HiGHS
foundation. Sanitizer runs set `detect_leaks=0` and `halt_on_error=1`; no leak
detection claim is made. Build time and these runs are not performance evidence.

| Test | Independent coverage |
|---|---|
| `lp_sensitivity_factor.cpp` | Actual factor-only accessors, mixed structural/logical order and signs, scaled rows, original residuals, singular rejection, unchanged basis and no optimization status |
| `lp_sensitivity.cpp` and `lp_sensitivity_oracle.hpp` | Analytic min/max/offset intervals; 16 exact rational boxed two-variable cases using vertex objective comparisons rather than production tableau algebra; endpoint/interior/outside comparisons; original-unit scaling; fixed/free/zero-cost variables; degeneracy, redundant equality singleton, ranged source rows, ownership/session edits/tombstones, large-cancellation residual and an actual-backend Partial caused by an unrepresentable limiting endpoint |
| Same main test in backend-free build | Missing source observations and a valid synthetic O1 artifact with an explicitly missing factor backend; no false available intervals |
| `lp_sensitivity_coordinator.cpp` | Separately compiled fake factor interface with bad counts/order/owners/vectors/NaN/residuals; per-request Partial; tiny finite derivatives and finite overflow; quota and malformed-option admission; allocation/backend exception; deterministic phase, partial and final-destructor cancellation; subsequent clean reuse |

The rational oracle enumerates the original feasible vertices and compares
objectives using checked small rational arithmetic. It is deliberately not a
copy of the production basis equations. Fixed-basis RHS endpoints have separate
closed-form rational witnesses. Broader random rational matrices, condition
estimates, commercial differential tests and simultaneous perturbations remain
future coverage; no CPLEX/Gurobi execution or full sensitivity parity is claimed.

The integrator owns CMake/install/umbrella and installed-consumer registration.
The main facade needs `lp_sensitivity.cpp` and `lp_sensitivity_backend.cpp`; only
the backend needs the existing HiGHS definition/includes. The normal test links
the facade. The coordinator separately compiles `lp_sensitivity.cpp` with
`GECODE_OPTIMIZE_TEST_LP_SENSITIVITY=1` and supplies the test factor/checkpoint
symbols; production contains neither test symbol. The factor experiment links
HiGHS directly and is enabled only with that backend. Private backend/detail
headers are excluded from installation. Owning [C/Python bindings](LP-SENSITIVITY-BINDINGS.md),
installed consumers and FAST registration are integrated and validated in the
[ninth checkpoint](NINTH-CHECKPOINT.md).

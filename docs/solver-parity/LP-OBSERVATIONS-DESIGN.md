# Continuous LP observations, bases, rays and sensitivity

Design baseline, audited 2026-09-05 against the integration source at `8ae59d5c1`
and local HiGHS **1.15.1**, commit
`04024d701f79feb8e2f18bc3df0dffc04ef05088`. No builds, solver runs or timing
experiments were performed for this design. O1 has subsequently been implemented;
the [API guide](LP-OBSERVATIONS.md) and [validation record](VALIDATION.md) describe
its delivered scope and completed checks. O2–O4 remain separate work, and this
design does not establish commercial-solver parity.

The first implementation should expose **owning observations of a completed
ordinary continuous LP solve**: original row activities, two-sided slacks,
row dual values, reduced costs, a numerical KKT report, and a basis when one
already exists. Default `solve` behavior should remain unchanged. Public basis
submission, ray recovery and sensitivity calculations should follow in separate
gated slices because they require different validation and can perform work.

## Commercial API target and scope

| Capability | Parity target | Proposed delivery |
|---|---|---|
| Row duals and reduced costs | Gurobi `Pi`/`RC`; CPLEX `getpi`/`getdj` | First slice, original model coordinates, explicit availability and numerical checks |
| Row activities/slacks | Gurobi `Slack`; CPLEX activity/slack queries | First slice, separate lower and upper slack for ranged rows |
| Basis status | Gurobi `VBasis`/`CBasis`; CPLEX basis queries | First slice export, later checked submission |
| Advanced simplex data | Basis inverse, basis solves, reduced rows/columns | Later explicit operation; not stored densely in every result |
| Infeasibility/unboundedness evidence | Farkas multipliers and primal improving direction | Separate budgeted recovery plus original-model checking |
| Objective/RHS/bound sensitivity | Gurobi `SAObj*`, `SARHS*`, `SALB*`, `SAUB*`; CPLEX `objsa`/`rhssa` | Start with objective coefficients and equality RHS; general bound changes need an explicit perturbation definition |

Dual values are solution observations. Basis-dependent allowable perturbation
intervals are a separate calculation. Gurobi defines these intervals relative
to the current optimal basis, and CPLEX sensitivity routines require an optimal
basis. Neither is a simultaneous-parameter guarantee.
[Gurobi row attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#sarhslow),
[Gurobi variable attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#saobjlow),
[CPLEX objective sensitivity](https://www.ibm.com/docs/en/icos/22.1.1?topic=o-cpxxobjsa-cpxobjsa),
[CPLEX RHS sensitivity](https://www.ibm.com/docs/en/icos/22.1.0?topic=r-cpxxrhssa-cpxrhssa).

The initial observation entry point accepts only active `Continuous` variables,
ordinary linear rows and one linear objective. It rejects every active Integer,
Binary, SemiContinuous or SemiInteger variable, including fixed discrete
variables; every active original indicator; and every active native global.
Checking only `Compiled::discrete` is insufficient for semantic metadata.
Quadratic models stay in their distinct API. No automatic LP relaxation, fixed
MIP, indicator lowering, private repair/pool model, or Native fallback is
permitted. A future explicit relaxation artifact can have its own identity and
observations. HiGHS-only numerical support is sufficient for the first slice;
missing backend, Native, Exact and Certified requests remain explicit
`Unsupported` results. Keep the existing numerical adapter's coefficient/bound
admission limits; this API does not silently rescale or weaken rejected input.

## Audited source hooks and prerequisites

Line references below refer to the audited source, not a generated listing.

| Existing hook | Consequence for implementation |
|---|---|
| `gecode/optimize/solve.cpp:47–124`, `Compiled`/`compile` | `slots` maps compact backend columns to original variable slots. Preserve this mapping and the full original active mask. |
| `solve.cpp:94–106`, row conversion | **`row_slots` is not currently a backend-row map.** It records every active row before empty rows are elided. Keep its topology-signature role or rename it, and add an independently checked `backend_row_slots` map populated only when a row is emitted. A constant row between two nonconstant rows must not shift later duals. |
| `solve.cpp:100–106, 384–413` | Constant rows and a model with no active variables can return before HiGHS runs. Their original activities can be computed, but there is no vendor basis or vendor dual vector to retrieve. |
| `solve.cpp:246–291`, `compatible`/`prepare` | Bounds, objective coefficients, row sides, sense and offset are updated in place. Owner, matrix, types and slot changes reload. Observations must describe the new solve, never the previously retained basis/duals. |
| `solve.cpp:437–483`, callback scope/run | Capture after `run()` returns, while the same session is serialized and its callback/budget lifetime is valid. No result accessor may later call the live HiGHS instance. |
| `solve.cpp:483–530`, candidate checking | Use the already validated original assignment. Copy/check duals and basis before returning or invalidating the session. Preserve the existing exclusion of late candidates. |
| `gecode/optimize/result.hpp:117`, `SolveResult` | Existing results own variable values/masks but no row metadata. New observations need independent owning row masks, source identity and snapshot provenance. |
| `gecode/optimize/session.hpp:22–35` | Content is checked even if a manually supplied snapshot reuses a revision. Public observation/basis compatibility must not depend on revision alone. |

HiGHS supplies `HighsSolution::{value_valid,dual_valid,col_value,col_dual,
row_value,row_dual}` and a separate `HighsBasis`. Flags, vector lengths,
finite values and mathematical checks are separate gates. A nonempty vector
does not establish availability. Its `basis.valid` means the basis has been
factored by HiGHS; it does not by itself establish primal or dual feasibility.
[Pinned structures](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HStruct.h#L20).

After nontrivial presolve, HiGHS reconstructs `solution_` and the available basis
in the **passed LP's** coordinates, then may clean up with simplex. Read only the
final public `getSolution()`/`getBasis()` results; do not read reduced-problem or
internal `ekk` arrays. The passed LP still excludes our tombstones and constant
rows, so Gecode's mapping step remains necessary. An interior-point solution
without crossover can have valid duals but no basis.
[Pinned postsolve path](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L1800).

HiGHS's simplex extraction already converts its internal minimization and
negated row-activity conventions back to the model's objective sense and row
activity. **Do not flip maximization duals a second time.** Row basis statuses
are also translated back to row lower/upper activity bounds.
[Pinned solution/basis extraction](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/simplex/HEkk.cpp#L1344).

## First C++ contract

Use an additive result wrapper and entry point so ordinary results need not
retain another snapshot or change memory cost. Names below are proposed, not
frozen symbols:

```cpp
struct LpObservationOptions {
  SolveOptions solve;
  bool duals = true;
  bool basis = true;
  LpCheckTolerances checks; // finite, nonnegative, independently documented
};

struct LpObservedResult {
  SolveResult result;
  std::shared_ptr<const LpObservations> observations;
};

LpObservedResult solve_lp_observed(const ModelSnapshot&,
                                  const LpObservationOptions& = {});
// Matching Model overload and SolveSession::solve_lp_observed overload.
```

Add an LP-specific capability record for compiled support of dual observations,
basis export/submission, evidence recovery and sensitivity. Build capability
does not imply that a particular solve produced a dual point or a basis; those
remain per-result availability states.

`LpObservations` is immutable, with a privately owned original snapshot or
equivalent complete immutable data required for validation. It records owner,
revision, objective sense/offset, backend/version, requested tolerance values,
effective backend settings, and a content fingerprint for diagnosis. Correctness
comparisons use checked contents, not a hash as an authorization token. Expose
original `Variable`/`Constraint` lookups and bulk arrays indexed by original
slots. Names are labels, never identifiers.

Each group has `NotRequested`, `Available`, `Unavailable` or `Rejected` plus a
reason/message; zero-length data is distinct from unavailable data. Reasons
include unsupported model, no backend solve, interrupted before capture, no
primal point, no dual point, no basis, elided constant rows, invalid dimensions,
nonfinite data, failed numerical checks and allocation budget. Retain original
active masks even when a group is unavailable. Deleted slots have no value and
must reject scalar lookup; foreign IDs and wrong kinds are errors. Zero must
never serve as an unavailable scalar sentinel.

Proposed groups:

* **Primal rows:** independently accumulated `activity`, `lower_slack =
  activity-lower`, `upper_slack = upper-activity`. An absent finite side has no
  corresponding slack, rather than a magic infinity. Use compensated sums;
  report conversion overflow explicitly. Do not clamp a small negative slack.
* **Dual point:** complete mapped `row_dual` and `reduced_cost` vectors, plus
  vendor feasibility metadata and the independent check report below. Publish
  ordinary-objective duals initially only for a timely, validated primal point
  with final Optimal status and `dual_valid`/valid info. Interrupted Phase I
  data is deliberately unavailable until a later phase-aware contract exists.
  CPLEX likewise warns that an infeasible primal-simplex iterate can expose
  Phase I duals rather than the original objective's duals.
  [CPLEX dual query](https://www.ibm.com/docs/en/icos/22.1.2?topic=g-cpxxgetpi-cpxgetpi).
* **Basis:** explicit mapped enums `Lower`, `Basic`, `Upper`, `Zero`,
  `NonbasicUnspecified`, never C++/HiGHS ordinal casts. Require valid flags,
  exact dimensions, recognized statuses and a consistent basic count. `Basic`
  does not mean nonzero and a fixed entity may be nonbasic on either side.
  Initially make the full basis unavailable when our conversion elides an
  active constant row; do not fabricate an original basis by padding zeros.
* **Checks:** original primal validity, dual sign/stationarity/complementarity
  residuals, objective estimates and separately measured gap. Basis validity,
  primal validity and numerical KKT acceptance remain distinct booleans.

For a feasible elided constant row in an otherwise solved LP, use activity zero
and reconstruct row dual zero with provenance `DerivedConstantRow`, not
`BackendObserved`. Check its original sides under the same numerical convention.
All other backend row duals must map through `backend_row_slots`. If no backend
solve occurs, initially publish only independently computed primal observations;
dual and basis groups say `NoBackendSolve`.

Failure to obtain an optional basis does not invalidate a valid primal result.
Rejected observation data stays absent and never manufactures a dual bound or
an optimality claim. Memory/cancellation during collection must leave already
completed owning results coherent. Capture/check allocations and work count
against the same monotonic whole-call budget. Late observation groups are
absent with a reason; accessors are passive bounded copies. Preserve the
existing solve deadline convention rather than upgrading a late backend status.

## Dual signs, offset handling and independent numerical checks

For the original problem, write

```text
f(x) = c^T x + c0,    L <= A x <= U,    l <= x <= u.
s = +1 for minimization and -1 for maximization.
pi = public row dual; r = public reduced cost.
A^T pi + r = c.
alpha = s*pi; beta = s*r; d = s*c.
```

In minimization a lower-active row has nonnegative `pi`, an upper-active row
nonpositive `pi`; signs reverse in maximization. Equality row duals are free.
These are the same public conventions described for Gurobi, and match the
pinned HiGHS extraction above.
[Gurobi Pi](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#pi).

Check against the original matrix and validated original values, independently
of the adapter's packed matrix:

1. `d - A^T alpha - beta` stationarity residual for every active column.
2. Normal-cone signs and complementarity for each original row and variable.
   Equivalently split `alpha = alpha_plus-alpha_minus` and
   `beta = beta_plus-beta_minus`, using positive and negative parts. Positive
   multipliers require a lower side; negative multipliers require an upper
   side. Complementarity products use the corresponding slack. Fixed variables
   and equality rows allow either sign. Free entities require zero multiplier.
3. The normalized dual objective estimate is

   ```text
   s*c0 + alpha_plus^T L - alpha_minus^T U
        + beta_plus^T l - beta_minus^T u.
   ```

   Skip exactly zero terms before touching an infinite endpoint. A nonzero
   multiplier requiring an infinite endpoint prevents a finite dual estimate;
   do not silently truncate the multiplier or multiply zero by infinity.
4. Accumulate the normalized primal-minus-dual gap directly with the common
   objective offset cancelled **before** accumulation and narrowing. Report
   the original-sense dual estimate separately; max reverses lower/upper-bound
   interpretation. Do not derive a tiny gap by subtracting two rounded large
   objective scalars.

Use checked compensated `long double` accumulation, but do not assume it is
wider than `double` on Windows, overflow-proof, or an exact certificate.
Preserve raw residuals; no clipping of failed sign tests, negative gaps or large
rounding discrepancies. Expose absolute metrics in original units with explicit
stationarity/dual-feasibility, complementarity and objective-gap tolerances.
Complementarity/gap have objective units; primal row and variable violations
retain their own units. Relative metrics may be informative but must not allow
an unrelated large offset or redundant bound to relax an absolute gate.

The dual objective is an **estimate** when stationarity holds only numerically;
with unbounded variable domains, a small residual does not automatically imply
a finite rigorous bound. Never overwrite `SolveResult::best_bound` from this
observation group. Exact/Certified results require a separate exact or outward
verified certificate pipeline. Iterative refinement and rational reconstruction
are useful later research paths, not properties obtained by merely returning
HiGHS doubles. [Gleixner, Steffy and Wolter, iterative refinement](https://optimization-online.org/wp-content/uploads/2015/06/4948.pdf),
[Gleixner and Steffy, limited-precision LP oracles](https://arxiv.org/abs/1912.12820).

The current adapter configures primal feasibility tolerance but not an explicit
LP dual tolerance. An observation request should record both effective backend
tolerances and its own check tolerances. If the new API sets dual tolerance,
set/reset it on **every** reused solve, including subsequent ordinary solves;
reject unsupported backend option ranges before mutating the session.

## Basis submission and edited sessions

First export basis status only; a basis is an optional warm-start artifact,
not a complete solver checkpoint or proof. Later add immutable `LpBasis` tokens
and an explicit `basis_start` option. Initial submission should require the
same owner, revision, checked original contents and compact mappings. Reject
foreign/deleted identities, invalid enums, missing/extra slots and invalid
lower/upper/zero statuses before calling HiGHS. Check zero-row cases ourselves:
the pinned alien-basis zero-row branch reads column statuses before its general
size check. [Pinned setBasis](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L2732).

A later explicit `CompatibleMatrixHint` policy may allow cost/bound/row-side,
sense or offset edits with stable owner, types, matrix and maps. Revalidate
statuses against new bounds. Passing an external basis as `alien` can cause
factorization/repair; expose submission and repair/rejection separately from
whether the final solve was optimal or faster. Never take a caller's
`valid=true` as proof of nonsingularity. Initial tests should include singular
and wrong-basic-count inputs. A failed submission should leave the session
usable through a clean reload, with no stale evidence available.

Internal retained-basis reuse can continue using the existing content-based
compatibility policy. It does not permit publishing old duals after a new edit.
Each result keeps its own historical owner/revision/content and remains readable
after model edits, model destruction, session reset/destruction and another
solve. A zero-time or failed second solve must not inherit the first result's
observations, even if HiGHS still retains a useful basis internally.

Do not expose factorization pointers. Ordered basic entities, basis solves and
tableau queries need a separate serialized, budgeted operation or an owning
factorization artifact. `getBasicVariables` encodes columns as nonnegative
indices and rows as `-(row+1)`; convert to a checked tagged entity instead of
exposing this signed index convention. Basis matrix row/slack orientation must
be frozen before exposing `B^{-1}` or reduced rows. [Pinned advanced API](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/Highs.h#L679).

## Rays: explicit work and separately checked evidence

`getDualRay` and `getPrimalRay` are **not passive getters** when supplied an
output buffer. The pinned implementation may disable presolve, change costs or
relax integrality and call `run()` to recover evidence. A presence-only query
does not guarantee that materializing the ray needs no work; an invertible
representation may be missing. Even a known ray can require a basis solve.
No-row models may return no vendor ray despite simple unboundedness.
[Pinned declaration](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/Highs.h#L596),
[pinned recovery](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsInterface.cpp#L1571).

Implement a later `analyze_lp_evidence(snapshot, options)` using a **private**
HiGHS instance and its own explicit whole-operation budget. Record the source
owner/revision/content, analysis termination, evidence availability, and any
additional solve counts separately from the original solve. Never alter an
existing result or persistent session's final status/options/basis. Leave
ordinary `InfeasibleOrUnbounded` ambiguous until actual checked evidence exists.

Independent checks must cover more than backend flags:

* A primal improving direction requires finite nonzero `d`, original recession
  conditions, and `s*c^T d < 0`. A finite lower bound requires `d_j >= 0`; a
  finite upper bound requires `d_j <= 0`; both require zero. Apply the same rule
  to `A*d` for row sides. An unboundedness claim additionally needs an original
  feasible base point. Direction-only evidence is not a feasibility proof.
* For a dual/Farkas direction `y`, form `z = -A^T y`. Require compatible finite
  sides for each signed row/variable multiplier, and a strictly positive
  contradiction margin

  ```text
  sum(y_i>0 ? y_i*L_i : y_i*U_i)
    + sum(z_j>0 ? z_j*l_j : z_j*u_j) > 0,
  ```

  with zero terms omitted. This expresses that every feasible point would
  imply `0 >= positive_margin`. Objective sense and objective offset play no
  part in infeasibility evidence. Normalize scale deterministically, reject
  zero/nonfinite vectors, recompute all activities/margins and do not assume a
  Gurobi Farkas vector has HiGHS's sign convention.

Numerically small recession/stationarity errors still cannot certify an
infinite trajectory or exact contradiction. Label accepted doubles numerical
evidence and retain residuals/margin. Exact proof is deferred. Original bound
contributions are essential: a row vector alone can miss the contradiction.
Hand-derived feasible points/directions and exact rational test arithmetic must
be independent of the upstream ray checker.

## Sensitivity: define the perturbation before naming an endpoint

HiGHS `getRanging` requires an optimal result and an initialized simplex
instance, and unscales internal simplex data. Its `HighsRangingRecord` contains
value/objective endpoints and entering/leaving internal variables. The cost
records contain `num_col + num_row` entries in this pinned version; publish only
the checked original column portion. Entering/leaving indices use a combined
column/row space with sentinel `-1`, unlike `getBasicVariables`' negative row
encoding. Validate each field before mapping it.
[Pinned ranging implementation](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsRanging.cpp#L70).

The pinned code already handles max cost signs, reverses internal row-bound
directions and includes the objective offset through the objective value.
Map its public result once. Test min/max/offset cases rather than reproducing
these transforms in the wrapper.
[Pinned output conversion](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsRanging.cpp#L528).

Critically, `col_bound_up` is not automatically “allowable increase of the
column's upper bound.” Upstream tests change the currently active bound of a
nonbasic entity, move both bounds of a fixed entity, and for a basic entity
use the lower bound in the upward test and upper bound in the downward test.
Rows use the analogous rules. Thus directly renaming these arrays `SALB*`,
`SAUB*` or separate ranged-row RHS intervals would be incorrect.
[Pinned bound perturbation tests](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/check/TestRanging.cpp#L266).

Implement sensitivity after basis export/submission has passed conformance:

1. Start with one objective coefficient at a time and an equality row's common
   RHS, in original absolute parameter values. Require a validated optimal
   basis; degenerate endpoints may equal the current value.
2. An explicit analysis owns a source snapshot and chosen basis, and uses a
   private backend under a budget. If backend repair changes the selected
   basis, report that identity/change or reject the requested-basis analysis.
   Do not advertise ranges for an unspecified replacement basis.
3. Extend to a typed `Perturbation {entity, LowerOnly|UpperOnly|MoveEquality|
   TranslateRange}` only after each semantics has its own algorithm/tests.
   Keep the other bound fixed for one-side perturbations and intersect with
   domain consistency. Translating a ranged interval preserves its width;
   changing one side does not. Fixed variable bounds are a separate case.
4. Return finite endpoints, unbounded endpoints and unavailable endpoints as
   distinct tagged values, with the selected basis/provenance, numerical
   guarantee, optional predicted objective and optional limiting entity.
   No claim about simultaneous changes, uniqueness, or how far another
   optimal basis might extend the interval. A dual “shadow price” is only a
   local marginal under the stated perturbation and may be nonunique.

## C and Python extension

Preserve ABI v1 record sizes. Add versioned LP observation option/info records
and new symbols rather than append fields to `gecode_opt_options_v1` or existing
result-info layouts. Reuse ordinary Model and Session handles, but return a
distinct owning observed-result token. `lp_observed_result_copy_result` returns
a new owning ordinary Result handle; observation access returns copied data or
a separate immutable token. Neither may borrow live session vectors.

Use exact record sizes, zero reserved fields, explicit enum maps, checked
owner/kind/deleted IDs, `uint64_t` size-to-native checks before allocation and
bounded output buffers with required counts. Scalar queries return an explicit
presence flag or typed unavailable error. Bulk values have active/present masks;
infinite range endpoints have their own kind. API failures remain distinct from
solve termination and unavailable optional groups. Keep exception boundaries
and registry-lock discipline identical to the existing C ABI.

Python adds `LpObservationOptions`, `LpObservedResult`, immutable check records
and owning `LpBasis`/`LpAnalysis` classes as later slices land. Use the same C ABI,
explicit `close`/context managers, library-aware entities and tuple/list copies.
Results and bases outlive source objects. New two-pass read queries may not
perform analysis or mutate a session; analysis is an explicit call. No NumPy
dependency is needed for the first API.

## Independent tests and implementation gates

| Gate | Required meaningful evidence |
|---|---|
| O1: original observations | Analytic LP panel below, fake backend corruption tests, lifecycle tests, missing-backend build, normal/ASan/UBSan and installed C/Python consumers. No basis, ray or sensitivity availability is inferred from optimal status alone. |
| O2: basis submission | Exact dimensions and full enum matrix, wrong owner/kind/revision/content, tombstones, zero rows/columns, invalid basic count, singularity, rejected submission then successful fresh solve, edited-session warm/cold objective agreement. No timing claim from reuse counters. |
| O3: evidence recovery | Analytic primal/dual rays with independent rational witnesses, mixed row/bound contradiction, unknown/limited and no-row cases, extra-work budgets, cancellation, no change to source session/result, fake zero/nonfinite/wrong-direction/missing-base-point data. |
| O4: sensitivity | Exact small-basis parameter intervals, interior/end/outside perturbations solved independently, min/max and offsets, degenerate/redundant rows, free/fixed/basic/nonbasic statuses, endpoint infinity/sentinels, changed-basis provenance and strict one-parameter semantics. |

Analytic LP fixtures should include:

* `min 2*x + 3*y + 7`, `x+y >= 4`, `x,y >= 0`: optimum `(4,0)`,
  objective 15, row dual 2, reduced costs `(0,1)`. Change the cost of `x` alone:
  the selected solution remains optimal for coefficient in `[0,3]`; beyond
  3 the optimizer switches to `y`, and below 0 the model is unbounded.
* `max 2*x + 7`, `x <= 4`, `x >= 0`: objective 15 and row dual 2. The
  corresponding `min -2*x + 7` has objective -1 and row dual -2. Bounds must not
  duplicate the active row in these sign fixtures, avoiding ambiguous duals.
* A ranged row `1 <= x <= 3` with a free variable: `min x` tests the lower
  side, `min -x` the upper side. Add equality, free/redundant row, fixed variable
  and bound-only LP fixtures; accept valid nonunique duals by KKT rather than
  asserting one arbitrary basis or dual vector.
* Deleted columns/rows and a feasible constant row between two nonconstant
  rows. Nonconsecutive original slots, duplicate names and later additions
  must map correctly. Constant-row basis unavailability is explicit.
* Presolve off/on including reduction to empty, scaling-sensitive coefficients,
  and large cancelling products/objective offsets. Check original values and
  signs, not reduced arrays. A no-crossover fixture must demonstrate duals
  without a basis once an algorithm selector/test seam is available.
* Farkas fixture `x >= 1` as a row and `x <= 0` as a variable bound: row
  multiplier 1, bound multiplier -1, contradiction margin 1. Primal-ray fixture
  `min -x`, `x >= 0`: base point 0 and direction 1, including the no-row path.
  An infeasible model with an improving recession direction must not be
  mislabeled unbounded merely because the direction check passes.
* Equality sensitivity fixture `min 2*x+5`, `x=b`, `0<=x<=10`: selected-basis
  RHS interval `[0,10]` and value `2*b+5`; just outside is infeasible. Add a
  degenerate endpoint case where the numerical optimizer can choose a
  different valid basis without violating the source solution semantics.

Fake backend fixtures must independently corrupt dual flags, info flags,
dimensions, row maps, enums, NaN/Inf, max signs, objective offsets, stationarity,
normal-cone signs and complementarity. Also return an old plausible dual vector
after a cost/bound edit and after a zero-time solve. No old observations may
appear in the new result. Keep copied historical observations readable after
destruction and concurrent independent solves. C/Python tests exercise query
sizes, undersized/null buffers, wrong-kind/stale tokens and repeated closes.

The existing FAST gate should add at most one small analytic observation case
after O1 integrates, with asserted case counts and the same whole-command
budget. Full observation/sensitivity correctness panels belong in CTest;
research accuracy/performance sweeps remain separate. Do not make timing
claims from this design or from builds running concurrently with root gates.

Suggested ownership: one agent owns new `lp_observations.hpp/.cpp` and the
independent checker/tests; root owns the small `solve.cpp` collector hook,
`session.hpp` wiring and build/install changes; a binding agent owns only
`c_api.*`/Python/conformance additions after the C++ records freeze. Add rays
and sensitivity in later separate files so passive result collection remains
auditable. Review source mappings and numerical equations before accepting O1;
do not count O2–O4 as complete because HiGHS already has similarly named methods.

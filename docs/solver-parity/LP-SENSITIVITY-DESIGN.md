# O4: numerical sensitivity of a specified optimal LP basis

Design record, 2026-09-05. This proposal is preserved separately from the
[implemented first slice and its verification](LP-SENSITIVITY.md); planned gates
below must not be read as completed test evidence. Source inspection uses Optimize at `069a66c7c` plus the completed
O3 files, and HiGHS 1.15.1 at
`04024d701f79feb8e2f18bc3df0dffc04ef05088`. O1 observations, O2 basis submission,
and O3 evidence recovery remain separate operations.

## Recommended first slice

Add `analyze_lp_sensitivity(const LpObservedResult&, options)`. It owns the
historical source, selected original-coordinate basis, and checked reference
point. It computes one-parameter **fixed-basis numerical intervals** using a
fresh private HiGHS factorization. Its first two parameter kinds are an original
objective coefficient and the common RHS of an original equality row.

This is additional linear algebra, with its own time/cancellation and work
limits. It performs **zero optimization runs**, never changes a Session or the
input result, and never silently chooses another basis. It requires a timely
optimal continuous LP result with available O1 primal, dual/KKT, and basis
groups. An ordinary primal optimum without a basis is insufficient. The caller
can explicitly obtain suitable observations or submit a basis using O1/O2 first.

Use the existing sparse factorization, not a new dense linear algebra package.
Derive perturbation inequalities from original coefficients and bounds, and
check every returned linear-system solution against that matrix. Do not expose
HiGHS bound-ranging arrays as commercial-solver lower/upper sensitivity fields.
Use `getRanging` only as a test comparator where its perturbation is demonstrably
the same. This is a refinement of the O4 direction in
[LP-OBSERVATIONS-DESIGN.md](LP-OBSERVATIONS-DESIGN.md).

Variable lower/upper bounds, separate sides of inequality/ranged rows, fixed
variable movement, range translation, matrix coefficients, simultaneous
perturbations, and ranges across multiple optimal bases remain explicit future
work. Ranged/inequality rows may occur in the source LP and restrict supported
coefficient/equality intervals; only *requests to vary their bounds* are outside
the first slice. A degenerate basis is not automatically unsupported.

## Commercial semantics and the actual difference to close

| Capability | Documented commercial meaning | Proposed O4 treatment |
|---|---|---|
| Objective coefficient | Gurobi `SAObjLow/Up`, CPLEX `CPXobjsa`: absolute coefficient endpoints associated with an optimal basis | First slice, original coefficient and objective sense |
| Equality RHS | Gurobi `SARHSLow/Up`; CPLEX RHS sensitivity moves both equality bounds together | First slice, explicitly `a*x = t` |
| Variable LB and UB | Gurobi `SALBLow/Up`, `SAUBLow/Up`; CPLEX `CPXboundsa` has four outputs | Separate future one-side requests; opposite side stays fixed |
| Ranged-row sides | CPLEX `getRangeSA` treats lower and upper sides independently | Future typed lower-only/upper-only requests |
| Translating a range | CPLEX Concert RHS sensitivity describes simultaneous motion of both bounds | Future explicit translation, with width preserved |
| Fixed variable bounds | Gurobi bound sensitivity reports the fixed value and says no sensitivity information is available | Explicit unavailable reason for independent-bound requests; moving both fixed bounds would be a different parameter |
| No basic solution | Gurobi sensitivity attributes require a basic solution; CPLEX objective/RHS routines require an optimal basis | Reject admission without an available, checked basis |

These are basis-dependent intervals, not a guarantee that a particular primal
point, the entire optimal face, or the solution is unique. A basis can stop being
optimal while another basis represents the same optimum. Changing multiple
parameters within their individual intervals need not preserve optimality.
[Gurobi variable attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#saobjlow),
[Gurobi RHS attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html#sarhslow),
[Gurobi basis availability](https://docs.gurobi.com/projects/optimizer/en/current/concepts/attributes/types.html),
[CPLEX objective sensitivity](https://www.ibm.com/docs/en/icos/22.1.1?topic=o-cpxxobjsa-cpxobjsa),
[CPLEX variable-bound sensitivity](https://www.ibm.com/docs/en/cofz/22.1.2?topic=b-cpxxboundsa-cpxboundsa).

Do not treat the two vendors' ranged-row `RHS` fields as an interchangeable
original lower bound. Gurobi documents `addRange` as an equality with an added
bounded slack: changing only that equality RHS at fixed slack width translates
the original interval. CPLEX distinguishes independent `getRangeSA` sides from
simultaneous `getRHSSA` motion. Our model already stores original lower and upper
bounds, so expose the perturbation itself, without importing an ambiguous vendor
representation. [Gurobi addRange](https://docs.gurobi.com/projects/optimizer/en/current/reference/python/model.html#Model.addRange),
[CPLEX range-side API](https://www.ibm.com/docs/en/icos/22.1.0?topic=c-ilocplex-2),
[CPLEX simultaneous RHS motion](https://www.ibm.com/docs/en/icos/22.1.0?topic=gm-getrhssa-method-double-double-irange-int32-int32).

Infinity is an endpoint direction, not unavailable data or a large finite
number. CPLEX examples use `CPX_INFBOUND` to encode it; our public representation
must tag it explicitly. Sensitivity also depends on numerical quality. A small
linear-system residual does not alone bound forward error for an ill-conditioned
basis. [CPLEX infinity convention](https://www.ibm.com/docs/en/icos/22.1.2?topic=clt-performing-sensitivity-analysis),
[CPLEX numerical quality guidance](https://www.ibm.com/docs/en/icos/22.1.2?topic=problems-numeric-difficulties).

## What pinned HiGHS getRanging actually does

The following are source-derived findings, not executed reproductions.

* `Highs::getRanging` calls `getRangingInterface`, which constructs a solver
  object from the **original** `model_.lp_`, then invokes `getRangingData`.
  There is no `run`, `solveLp`, or optimization fallback in this chain.
* `getRangingData` rejects non-optimal status and an uninitialized simplex
  instance. It calls `unscaleSimplex`, modifying internal working arrays, and
  performs FTRAN for every nonbasic structural/logical entity. It is not a
  passive vector getter; its main loop contains no time/cancellation polling.
* It clips basic values to bounds and nonbasic reduced costs to feasible signs,
  filters tableau coefficients at `1e-9`, and rounds endpoint magnitudes below
  `1e-13` to zero. These decisions are not exact endpoint certification or the
  caller's original-unit checker tolerances.
* Objective arrays have `n + m` entries in this version, although only the first
  `n` represent source objective coefficients. Column bound arrays have `n`
  entries, row bound arrays `m`. Every record has value, predicted objective,
  entering-index, and leaving-index arrays. Combined indices use structural
  columns followed by logical rows, with `-1` as absence.
* Max objective-cost endpoints are already swapped/negated on output. Original
  row-bound directions are also swapped/negated. Endpoint objective values
  start from the backend objective, including its offset. A wrapper applying
  these transformations again would be wrong.

Sources: [public wrapper](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L2191),
[interface](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsInterface.cpp#L1825),
[preconditions and unscaling](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsRanging.cpp#L70),
[numerical thresholds and FTRAN loop](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsRanging.cpp#L133),
[output conversion](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsRanging.cpp#L516).

Most importantly, bound-up/down describe status-dependent experiments. Upstream
tests move the active side of a nonbasic entity, both sides of a fixed entity,
the lower bound for a basic entity's upward test, and its upper bound for the
downward test. The basic branch can compute a moved basic value after a pivot or
bound flip. The test then **reoptimizes** and compares the endpoint objective;
it does not assert that the original basis/status assignment remains optimal.
[Basic-bound algorithm](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsRanging.cpp#L459),
[column experiments](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/check/TestRanging.cpp#L261),
[row experiments](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/check/TestRanging.cpp#L399).

A symbolic discriminator, independently reviewed by the model/solver agent:

```text
minimize y
x - y = 1
0 <= x <= 3; 0 <= y <= 2
selected basis: x basic, y at its lower bound, equality logical nonbasic
reference point: x=1, y=0
```

For this fixed basis/status assignment, the largest possible lower bound on
`x` is `1`. The pinned basic-bound-up branch can instead reach `x=3, y=2`, with
objective `2`, by moving/pivoting the entering variable. That endpoint cannot be
renamed `SALBUp(x)`. This exact model must become a regression before any bound
sensitivity implementation. No live HiGHS output for it was produced during
this design-only task.

## Source proof of factorization without an optimization run

Use the following precise chain on a fresh private `Highs`. This deliberately
differs from O2's alien-basis submission, where reporting repair is useful.

1. Validate complete original source, slot masks, all statuses, finite-bound
   compatibility, and exactly `m` basic entities. Reject
   `NonbasicUnspecified`, wrong dimensions, foreign IDs, and unsupported model
   data before touching the backend. Pass an unchanged ordinary continuous LP.
2. Construct a complete `HighsBasis` with `alien=false`, `valid=true`,
   `useful=true`, explicit statuses, and a nonempty origin. The non-alien
   `setBasis` path checks consistency and copies statuses; it does not optimize
   or repair. `newHighsBasis` invalidates the internal EKK basis/invert.
3. Call `getBasicVariables` with an allocated `m`-entry buffer. When no invert
   exists, it calls `formSimplexLpBasisAndFactor(..., true)`. That routine
   initializes EKK through `moveLp`, sets the supplied basis, and calls
   `initialiseSimplexLpBasisAndFactor(true)`.
4. The `true` flag forbids rank-deficiency repair: singularity returns an error,
   rather than introducing logical columns. A successful result has an invert;
   check `hasInvert()` explicitly. Recheck the public statuses and decoded basic
   entity set against the requested basis. An unexpected change rejects the
   analysis. Permutation of the same basic entities is allowed and recorded.
5. Only then use dense-buffer `getBasisSolve` / `getBasisTransposeSolve`.
   Both require an existing invert. Their implementations perform FTRAN/BTRAN
   and contain no optimization call. Pass null sparse-output arguments: avoid
   unnecessary sparse count/index paths and validate all dense output values.

This is a source proof of the intended call path, **not runtime evidence**.
Before shipping, a direct fresh-instance regression must exercise this exact
sequence without `run`, on ordinary/scaled/mixed-logical/singular bases. Keep
production optimization entrypoints absent from the factorization helper.

Sources: [non-alien setBasis and invalidation](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L2732),
[getBasicVariables](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsInterface.cpp#L1438),
[factor setup](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsSolution.cpp#L1850),
[no-repair branch](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/simplex/HEkk.cpp#L1441),
[basis solve accessors](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L2344),
[upstream singular-basis test](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/check/TestAlienBasis.cpp#L684).

Do not substitute alien `setBasis` and assume its temporary factor survives:
the alien path can complete/repair the basis, and `newHighsBasis` still invalidates
EKK afterward. Do not call `getRanging` after this sequence: an invert alone does
not establish its optimal-model-status and initialized-solve prerequisites.

## Original coordinates, signs, scaling, and presolve

Use original finite lower/upper bounds and objective coefficients. Let `s=+1`
for minimization, `s=-1` for maximization. In the private basis algebra define

```text
u = (x, z), z = -A*x
M = [A, I], M*u = 0
h = (s*c, 0)
structural bounds: col_lower <= x <= col_upper
logical row bounds: -row_upper <= z <= -row_lower
```

An original row's `Lower` status becomes logical `Upper`,
and original `Upper` becomes logical `Lower`. Basic stays Basic; fixed logicals
have both bounds equal. `getBasicVariables` uses nonnegative structural indices
and `-(row_index+1)` for logicals, **not** ranging's `n+i` convention. Decode
negative indices with checked arithmetic, avoiding signed-min negation. Save the
ordered `B` entities; do not assume basic order is original slot order.
[Public encoding](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/Highs.h#L681),
[row status conversion](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/simplex/HEkk.cpp#L1226),
[logical column sign](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/util/HighsSparseMatrix.cpp#L1618).

The basis-solve interface refreshes its original-LP/scaling pointers. FTRAN
applies row scaling before the factor solve and basis-column scaling after it;
BTRAN uses the reverse order. Thus pass original-unit RHS/cost vectors and check
the answers against original `B`; do not rescale the public answers again.
Logical columns use reciprocal row scaling within the basis-column conversion.
[Interface scaling path](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsInterface.cpp#L1480),
[FTRAN/BTRAN scaling](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/simplex/HSimplexNla.cpp#L96),
[scale factors](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/simplex/HSimplexNla.cpp#L245).

O1 observations already own the original model and mapped postsolve basis. A
source solve may have used presolve; the new analysis imports the *original*
matrix, has no presolve/optimization call, and refactors that selected original
basis. HiGHS's normal solve path reconstructs original basis statuses and may run
original-LP simplex cleanup after postsolve; that work belongs to the original
solve, not this analysis. IPM without crossover/PDLP may yield no basis. Return
NoBasis rather than running crossover implicitly.
[Postsolve and original cleanup](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L1837).

Local mapping hooks, at the inspected Optimize revision:

| File/location | Required reuse or preservation |
|---|---|
| `gecode/optimize/solve.cpp:78` `Compiled` | `slots` and `backend_row_slots` map backend indices to original slots |
| `solve.cpp:89` `compile` | Exact structure/range admission and lossless matrix conversion; constant rows are elided |
| `solve.cpp:163` `prepare_basis` | Existing public status conversion; O4 uses its own fully checked non-alien path |
| `solve.cpp:606` observation collector | Remains passive; do not add sensitivity computation here |
| `solve.cpp:745` `observed_solve` | Existing whole-budget and post-cleanup policy is the lifecycle precedent |
| `lp_observations.hpp:100` `LpObservations` | Immutable source/metadata/groups; retain shared ownership |
| `lp_basis.cpp` factories and compatibility | Reuse complete masks/status/entity checks; do not weaken same-source semantics |

O1 basis export is unavailable when an active constant row was elided. Preserve
that boundary; do not invent an inverse mapping. Tombstones retain slots in the
new result, with inactive data absent. Historical observations remain usable
after model edits/destruction; analysis does not consult the live model. A
different revision is a different analysis input, even if its numerical data
happen to match. No automatic stale-basis transplant is offered.

## Interval algorithm and independent checks

First reconstruct the selected basic solution, not just a feasible point:
assign every nonbasic `u_N` to its selected bound, fixed value, or zero for a
genuinely free `Zero` status, then solve `B*u_B = -N*u_N`. Solve
`B^T*pi = h_B` and form `d = h - M^T*pi`. Recompute original activities and
objective with compensated wide accumulation. Check basis-point agreement with
the source result, finite data, original primal feasibility, reduced-cost signs,
stationarity, complementarity, and offset-free primal/dual gap. This prevents a
feasible O1 primal/dual point and an unrelated feasible-looking basis from being
combined into invented ranges. Original duals are `s*pi`; original structural
reduced costs are `s*d_x`.

For every solve check `B*v-rhs` or `B^T*v-rhs` using the independent original
matrix. Record absolute and scaled residuals, with the exact tolerances used.
Reject nonfinite values and lossy nonzero underflow, and handle cancellation
while traversing matrix data. Do not label residual acceptance a condition-number
or exactness guarantee. A later condition estimator can be added explicitly.

For an objective coefficient `c_j = c_j0 + delta`, let `q` have `s` in structural
position `j` and zero elsewhere. Solve `B^T*v=q_B` when `j` is basic; otherwise
`v=0`. Then

```text
d(delta) = d(0) + (q - M^T*v)*delta
```

Intersect all nonbasic dual-feasibility inequalities: `d>=0` at a lower bound,
`d<=0` at an upper bound, `d=0` for a free nonbasic entity. A fixed entity has
no reduced-cost sign restriction. Primal values/bounds are unchanged. Original
objective change is `x_j*delta`, independent of objective sense; `s` is used only
in normalized optimality inequalities. The coefficient anchor is zero when that
active original variable has no explicit objective term.

For equality `a_i*x = b_i0 + delta`, the logical variable is fixed to
`-b_i0-delta`. If it is nonbasic, its derivative is `-1` and
`u_B' = B^-1*e_i`; all other nonbasic derivatives are zero. Intersect every
original/logical primal-bound inequality along `u(delta)`; costs and nonbasic
dual signs are unchanged. Also check the original direction equations and
finite-side derivative conditions. Original objective change is
`c^T*x'*delta`, agreeing with the selected original row dual times `delta`.

If an equality logical is basic, nonbasic values stay fixed and this basis
forces its old activity. Moving its common bound therefore gives a singleton
interval at the reference RHS. Check the baseline fixed activity and report the
singleton explicitly; do not use HiGHS's basic-bound pivot range. Redundant
equalities and degeneracy are covered by this case.

Intersect linear scalar inequalities in `long double` with checked arithmetic.
Both finite endpoints are absolute parameter values, not allowable deltas.
Retain anchor, derivative, and limiting original entity/side where determinable.
The final interval must contain its anchor; reversed, NaN, unrepresentable finite,
or numerically inconsistent results are Rejected for that request. Do not widen
a range by the primal tolerance or snap a tiny slope to zero and declare an
infinite range. If numeric uncertainty prevents reliable classification, report
it. A zero-width interval is valid and distinct from unavailable data.

The checker independently re-evaluates the complete affine inequality family at
finite endpoints. A finite endpoint needs at least one matching limiting
inequality; an infinite endpoint needs sign compatibility of every derivative
in that direction. These are tolerance-qualified numerical checks, not a proof
covering arbitrarily large perturbations. Testing interior samples alone is
insufficient to validate endpoint maximality or infinity.

## Proposed owning API

Names below are a design sketch, not a released header. Avoid modifying
`SolveResult`, O1 records, `SolveOptions`, or existing C ABI structs.

```cpp
struct LpObjectiveParameter { Variable variable; };
struct LpEqualityRhsParameter { Constraint row; };
using LpSensitivityParameter =
  std::variant<LpObjectiveParameter, LpEqualityRhsParameter>;

struct LpSensitivityOptions {
  Backend backend = Backend::Auto;             // Auto resolves to HiGHS
  double time_limit_seconds = infinity;
  std::shared_ptr<CancellationToken> cancellation;
  std::vector<LpSensitivityParameter> parameters;
  LpSensitivityTolerances checks;
  LpSensitivityLimits limits;
};

enum class LpRangeEndKind { Finite, NegativeInfinity, PositiveInfinity };
struct LpRangeEnd { LpRangeEndKind kind; std::optional<double> value; };
struct LpParameterInterval {
  LpRangeEnd lower, upper;
  double anchor;
  std::optional<double> objective_slope;        // original sense, no offset
  // Optional limiting original entity/side; tied limiters are not unique.
  LpIntervalCheckReport checks;
};
struct LpSensitivityEntry {
  LpSensitivityParameter parameter;
  LpSensitivityGroup group;                   // state, typed reason, message
  std::optional<LpParameterInterval> interval;
};

class LpSensitivity;                          // immutable, owning
struct LpSensitivityResult {
  ModelId model_id;
  Revision revision;
  LpSensitivityCompletion completion;         // Complete/Partial/Interrupted/Rejected
  std::optional<Termination> stop_reason;
  std::shared_ptr<const LpSensitivity> sensitivity;
  LpSensitivityWork work;
  double elapsed_seconds;
};
LpSensitivityResult analyze_lp_sensitivity(
  const LpObservedResult&, const LpSensitivityOptions&);
```

`LpSensitivity` owns a copy of the ordinary source result, a shared immutable O1
observation, an owning selected `LpBasis`, backend/version metadata, reference
basis/KKT checks, original row/column masks, ordered factor-basis identities, and
entries in request order. Original-slot lookup returns objective/equality entry
or explicit NotRequested; foreign and historical tombstone handles throw
`ModelError`. Copies of public results/arrays never borrow backend vectors.
`LpRangeEnd::value` is present exactly for Finite; the whole interval is absent
unless its group is Available. Infinity endpoints cannot be substituted as
finite parameter values.

Require a nonempty explicit parameter list, reject duplicates and invalid kinds,
and preflight all IDs and request shapes before factorization. A one-sided/ranged
row passed as `LpEqualityRhsParameter` is Unsupported, not approximated as an
equality. Requested group failure is separate from an unchanged source Optimal
termination. Never infer Infeasible/Unbounded from an interval or factorization
failure. The guarantee is always Numerical; no exact/certified setting is
offered, and no MIP node/gap or primal-start options are silently ignored.

Whole-input failures reject all groups. Per-parameter numeric failure may coexist
with other complete entries: use Partial when some requested intervals are
available, Rejected when none are; Complete requires every request to be
available. On any whole-operation
deadline/cancellation/work/resource failure, clear **all** availability, retaining
only completed diagnostics and historical source data. This matches the
conservative O1/O3 cleanup policy. Accessors do no work after publication.

## Budgets, resource limits, and failure boundaries

Start the monotonic budget before copying the mutable outer result or scanning
the source. The immutable observations may be shared; complete result values
still need an owning copy. Check all size arithmetic against `size_t`,
`ptrdiff_t`, container limits, and pinned `HighsInt` before allocating/traversing.

Initial configurable guards should bound active rows/columns, matrix nonzeros,
requests, retained logical slots, coordinator element visits, and the number of
basis linear-system calls. Choose conservative defaults after the first
conformance panel; do not claim timings from design. Guard possible dense
factor fill using checked row-count-square admission if needed, but label it a
logical resource guard, not a precise bound on HiGHS allocator overhead or RSS.
Stream one requested derivative and its matrix scan at a time; do not allocate a
full `m*n` tableau or explicit inverse. Count only actual FTRAN/BTRAN accessor
invocations as `basis_solves`; use a separate `factor_setup_attempted` flag.
Optimization runs are structurally zero, not inferred from an iteration counter.

Set a single-threaded private backend and remaining time where supported, but
document that factorization and triangular solves contain uninterruptible
regions. No callback promises a hard kill deadline there. Poll before/after
each backend call and during our loops; after private backend/raw buffer release,
check the still-live budget again before publishing. An overrun is Interrupted
and publishes no intervals. No automatic retry with presolve, another basis, a
different tolerance, or a cold solve is allowed. Allocation/backend exceptions
must clear states before constructing error strings and must not escape future
C boundaries.

First-slice non-admissible cases: non-Continuous variables including semis;
active indicators/globals; quadratic/nonlinear models; missing HiGHS; explicit
Native; non-optimal or malformed source result; missing O1 groups or failed KKT;
unknown/incomplete statuses; mismatched owner/revision/masks; active constant
rows elided by O1; invalid finite coefficients/bounds or adapter threshold
violations; singular/changed basis; unsupported perturbation; exceeded caps.
Empty/zero-row sources without a backend basis remain NoBasis in the first
slice. A later checked local bound-only analysis can support them explicitly.
Infinite unvaried bounds are valid and simply omit their inequality side.

## Conformance gates before release

1. **Prove the factor-only path at runtime.** Fresh private instances, no `run`,
   complete non-alien basis, `getBasicVariables`, invert, FTRAN/BTRAN. Test
   singular same-size bases, zero rows, unknown/free/fixed statuses, mixed
   structural/logical columns, nontrivial scaling, and original residuals.
   Compare requested/returned identities, not just the count of Basic statuses.
2. **Independent exact small-basis oracle.** Test-only rational elimination on
   integer/rational matrices derives the entire affine inequalities and endpoint
   ratios independently. Do not copy production interval code into the oracle.
   Enumerate small bases to show basis dependence under degeneracy.
3. **Analytic parameter panel.** `min 2*x+y`, `x+y=b`, `x,y>=0`, at `b=3`
   gives objective-x range `[1,+inf]`, objective-y `[-inf,2]`, equality RHS
   `[0,+inf]` for the `y` basis. Verify sign-reversed maximization and offsets.
   Add finite two-sided bounds, negative/free variables, fixed variables,
   duplicate/redundant equalities, logical-basic singleton RHS, zero costs,
   zero-width intervals, and one-sided/ranged source rows that restrict ranges.
4. **Endpoint/interior/outside checks.** Independently re-solve selected finite
   perturbations only in tests. Inside, the selected basis affine point/dual
   must satisfy original KKT. At finite endpoints, verify the exact oracle's
   limiting condition. Outside, verify fixed-basis failure; do not demand that
   the solver's new optimum or objective must differ. Test infinite directions
   by the analytic inequalities, not a handful of large samples.
5. **HiGHS/commercial differential checks.** Compare getRanging costs and
   compatible nonbasic equality-RHS endpoints on well-scaled nondegenerate
   cases. Include the basic-bound counterexample and prohibit its renaming.
   Optional CPLEX/Gurobi tests require existing licensed installations and
   matched source basis/parameter semantics; absence must not be reported as
   vendor conformance. No vendor installation is required for the core oracle.
6. **Numerical adversaries.** Scaled rows/columns, nearly singular bases,
   tiny nonzero derivatives, NaN/infinite/overflowed outputs, finite-versus-
   infinite endpoint confusion, interval excluding anchor, incompatible slopes,
   cancellation such as `1 + 1e16 - 1e16`, and offsets dominating objective
   changes. Test residual acceptance without overstating forward accuracy.
7. **Ownership and edits.** Tombstones, wrong entity kind/owner, deleted requested
   slot, mutable outer result with bad status/identity/masks/scalars, model/session
   destruction, session edits after observation, and reanalysis of both old and
   new observations. Old analysis must remain unchanged and addressable only by
   its original historical handles.
8. **Fault and budget seams.** Private separately compiled test access layer
   supplies corrupted factor order/vector/status and deterministic phase/final-
   cleanup cancellation; production has no callbacks/hooks beyond the real
   backend. Fail before snapshot copy, during setup, between requests, and after
   otherwise available intervals. Allocation faults and prior successful
   analysis must not leak stale groups. Assert no optimization operation is
   requested by the coordinator.
9. **Build gates.** Backend-free admission, numerical normal, fully instrumented
   ASan/UBSan including HiGHS, installed C++ consumer, then owning C99/Python
   tests after bindings land. Standalone tests explicitly keep assertions active
   under Release/NDEBUG. Later add one analytic min/max O4 case to FAST without
   weakening its whole-run deadline; build time stays separate.

## File ownership and subsequent slices

First vertical implementation: new `gecode/optimize/lp_sensitivity.hpp/.cpp`,
private factor/checker interface, `test/optimize/lp_sensitivity.cpp`, a separate
coordinator/fault test, and delivery documentation. Root owns CMake, install,
umbrella header, and FAST wiring. If sharing the existing numerical conversion
requires extracting a private helper from `solve.cpp`, agree that small ownership
change first; leave its passive observation and session behavior unchanged.
Do not duplicate a weaker coefficient admission path in the new analyzer.

The first C/Python binding should take an owning O1 observed-result token and
checked versioned request records, return a distinct immutable sensitivity token,
and offer bounded per-entry/bulk retrieval. Extended endpoint kind and group
availability have separate explicit enums. Copied source observations/results
outlive all model/session/input handles. Use existing registry ownership and
exception boundaries, exact struct/element sizes, zero reserved fields, and
preflighted buffers; no getter may trigger factorization or solving.

Then extend the same algebra to explicit finite lower-only/upper-only bound
changes, equality/fixed movement, and fixed-width range translation, each with
its own affine definition and independent oracle. For a basic entity, changing
one bound keeps the selected basic value until it becomes infeasible; for an
inactive nonbasic side, keep its selected active value unchanged. Include bound
consistency and fixed/free special cases. This closes the four-output commercial
API gap without relying on HiGHS's differently defined movement arrays.

Optimal-face ranges, degeneracy graph traversal, simultaneous parametric regions,
matrix-coefficient sensitivity, condition estimation, and exact interval
certificates need separate designs. The distinction between one selected basis
and multiple optimal bases is also a research topic in sensitivity/parametric
programming; the bounded implementation need not solve that broader problem.
[Research overview: Gal and Greenberg, Advances in Sensitivity Analysis and Parametric Programming](https://link.springer.com/book/10.1007/978-1-4615-6103-3).

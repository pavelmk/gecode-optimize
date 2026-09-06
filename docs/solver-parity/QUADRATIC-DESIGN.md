# W13 design: bounded convex continuous QP through HiGHS

Status: research/design only, 2026-09-05. No QP source implementation or shared
`Model`, native, solve, workflow or binding change is authorized by this document.

## Recommendation and first support boundary

Implement an isolated `QuadraticModel` / `QuadraticSnapshot` wrapper, an explicit
`solve_quadratic` backend, and an independent original-objective/KKT/bound checker.
The first supported class is **finite-box continuous variables, ordinary linear
constraints, and positive weighted squared affine objective terms**. Minimize a
convex objective or maximize a concave objective. Preserve singular curvature,
fixed variables and empty/constant terms correctly; do not require positive
definiteness. Return `Unsupported` for unbounded original variable domains,
integer/binary/semi variables, indicators, CP globals, arbitrary Hessians,
quadratic constraints, nonconvex objectives, starts, sessions and Exact/Certified
solve requests in this first slice. This is a useful bounded least-squares and
penalty-objective feature, not MIQP, QCP, nonlinear or full QP parity.

Lower each square to a private residual variable and a diagonal Hessian. This
establishes convexity structurally, preserves the user's original factored
objective, and avoids forming a rounded Gram matrix. Keep the existing linear
model API and binary layout unchanged. A distinct snapshot type without an
implicit conversion makes accidental use by an older linear workflow a compile
error. Build registration/umbrella inclusion is the only shared change needed
for the first C++ vertical slice.

Finite original boxes are a deliberate initial restriction: they make a
residual-corrected global lower bound available without inverting a possibly
singular Hessian or treating small stationarity residuals as exactly zero.
Removing that restriction requires additional bound/curvature verification;
it must not be simulated by inventing large artificial bounds.

## Pinned source findings

The local dependency is **HiGHS v1.15.1**, commit
`04024d701f79feb8e2f18bc3df0dffc04ef05088`. The installed integration build has
`HIPO=OFF`. The following findings come from that source, not an assumption about
current development documentation.

| Contract | Pinned evidence and implication |
| --- | --- |
| Objective convention | `c0 + c'x + 0.5*x'Q*x`. Lower triangular column-compressed entries represent one symmetric Hessian. Diagonal contribution is `0.5*Qjj*xj^2`; one off-diagonal entry contributes `Qij*xi*xj`. [QP README](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/qpsolver/README.md), [Hessian evaluation](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/model/HighsHessian.cpp#L218-L235). |
| Hessian upload | `HighsHessian` uses `dim_`, `format_`, `start_`, `index_`, `value_`; prefer canonical lower CSC with `start.size()==dim+1`, sorted unique row indices, and finite values. [Type](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/model/HighsHessian.h), [assessment/normalization](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/model/HighsHessianUtils.cpp#L22-L82). |
| Upload may change data | Assessment sums duplicates, normalizes the triangle, filters small values and completes missing diagonals. Square asymmetry is rejected; upper triangular entries in triangular input can be moved/summed. Avoid relying on correction/warnings; preflight and inspect the uploaded representation. [Normalization](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/model/HighsHessianUtils.cpp#L321). |
| Convexity is not established | `okHessianDiagonal` only rejects a diagonal sign inconsistent with the sense. Passing it is not a PSD proof. For example, `[[1,2],[2,1]]` has positive diagonal and eigenvalues `3,-1`. Later negative-curvature detection is not a complete acceptance test. [Diagonal test](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/model/HighsHessianUtils.cpp#L169-L211), [solve gate](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L1343-L1372). |
| No MIQP | A QP with integrality is rejected unless `solve_relaxation` was requested. That latter path drops integrality; it is not MIQP support. The adapter must never enable it as a fallback. [Dispatch](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L1343-L1372). |
| Actual initial algorithm | The active-set solver is the default; HiPO is used only when selected and compiled/available. It maintains a reduced Hessian and has a nullspace limit, default 4000. Explicitly select `qpasm` for reproducible first-slice behavior; do not infer HiPO availability from recent docs. [QP dispatcher](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L4139-L4350), [options](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsOptions.h#L1390-L1408). |
| Regularization changes the working objective | `solveqp` adds `qp_regularization_value` to each stored diagonal; the default is `1e-7`. The source explicitly describes perturbed solutions. Final HiGHS checks use the original model. Our acceptance checks must also use the unregularized original squares. [Regularization](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/qpsolver/a_quass.cpp#L130-L193), [settings](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/qpsolver/settings.hpp#L40-L54). |
| Dual values are available, not automatic proof | Original-sense column and row duals are returned; multiply by the objective sense sign to normalize. `getDualObjectiveValue` is available, but its computation assumes meaningful dual data and selects bound contributions from primal location. Preserve it as a vendor diagnostic, not an independently verified bound. `mip_dual_bound` is a MIP field and is not the QP bound. [Dual mapping](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/qpsolver/a_quass.cpp#L65-L85), [dual objective](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsSolution.cpp#L1329-L1398). |
| Final numerical checks | HiGHS computes original objective/KKT failures and calls `checkOptimality` for a QP reported optimal. Recheck independently rather than assuming that report establishes convexity or exact optimality. [Final checks](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L4333-L4346). |
| Cancellation limits | The active-set call receives time/iteration limits, but the inspected path does not pass the general HiGHS callback object to QUASS. Check cancellation before/after backend work and exclude late candidates; do not advertise an in-loop interrupt callback. Propagation, factorization and phase-I work are cooperative. [QP call](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L4139-L4350), [time checks](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/qpsolver/quass.cpp#L350-L365). |

The [current official solver documentation](https://ergo-code.github.io/HiGHS/dev/solvers/)
likewise cautions that the diagonal convexity check can miss nonconvexity. It is
supporting context, not the version pin or an authorization to enable new solvers.

## Objective semantics and lowering

Let `s=+1` for minimization and `s=-1` for maximization. Define the original
objective explicitly as

```
f(x) = c0 + c'x + s * sum_k w_k (a_k'x + b_k)^2,  w_k > 0.
```

The maximization entry point is named `maximize_concave_squares` so its negative
penalties are explicit. Its normalized minimized objective is

```
F(x) = s*f(x) = s*c0 + (s*c)'x + sum_k w_k (a_k'x+b_k)^2.
```

For each square, introduce private continuous `z_k` and linear equality
`z_k - a_k'x = b_k`. Minimize `s*c0 + (s*c)'x + sum w_k*z_k^2`, with diagonal
`Q[z_k,z_k]=2*w_k` and zero curvature on original `x` columns. Residual variables
may be free; only original variables require finite boxes. The backend Hessian
is PSD by construction, including when some original directions are flat.
Auxiliary values and rows stay private; result slots use original wrapper
variables, including tombstones. Square names/indices identify diagnostics.

This formulation uses `O(sum nnz(a_k)+number_of_squares)` extra linear entries
and diagonal curvature. Expanding `2*sum w_k*a_k*a_k'` can cause quadratic fill-in
and floating rounding can destroy exact PSD of the submitted matrix. The lifted
route avoids both issues, at the cost of additional rows/columns and possible
conditioning/nullspace costs. These costs must be measured, not assumed away.

Reject non-finite or underflowed/generated coefficients, dimensions outside
`HighsInt`, values beyond HiGHS's infinity/range limits, and nonzero entries at
or below the configured removal threshold. Multiplication by two for the
Hessian must stay finite and nonzero. Do not silently drop small `a_k` or weights.
Set the matrix threshold explicitly to `1e-12`, as the existing adapter does,
and audit the round-tripped backend model before solving. Do not form or alter
the original linear/constant terms by an expanded-square cancellation.

Initial solver setting recommendation: `qpasm`, one worker, zero seed,
`qp_regularization_value=0`, and an explicit bounded nullspace/iteration policy.
The zero-regularization choice needs direct comparison with the pinned default
on singular/ill-conditioned fixtures before adoption. A later robustness fallback
may use nonzero regularization only with separate recorded settings and the same
unregularized acceptance gates; no retry may restart the total budget.

## Exact proposed C++ surface

Candidate declarations; implementation review may simplify names, not semantics:

```cpp
struct WeightedSquare {
  std::vector<Term> terms;  // original Variable handles; canonicalized
  double offset = 0;
  double weight = 1;       // strictly positive finite
  std::string name;
};

class QuadraticSnapshot;   // immutable owning data; private construction
class QuadraticModel {
public:
  QuadraticModel();
  QuadraticModel(QuadraticModel&&) noexcept;
  QuadraticModel& operator=(QuadraticModel&&) noexcept;
  QuadraticModel(const QuadraticModel&) = delete;
  ModelId id() const noexcept;
  Revision revision() const noexcept;
  Variable add_continuous(double lower, double upper, std::string name = {});
  Constraint add_row(const std::vector<Term>&, double lower, double upper,
                     std::string name = {});
  void set_bounds(Variable, double lower, double upper);
  void set_bounds(Constraint, double lower, double upper);
  void set_coefficient(Constraint, Variable, double);
  void remove(Variable);   // reject references in rows, linear cost or squares
  void remove(Constraint);
  void minimize_squares(const std::vector<WeightedSquare>&,
                        const std::vector<Term>& linear = {}, double offset = 0);
  void maximize_concave_squares(const std::vector<WeightedSquare>&,
                        const std::vector<Term>& linear = {}, double offset = 0);
  QuadraticSnapshot snapshot() const;
};

struct QuadraticOptions {
  SolveOptions solve;      // Numerical + Auto/Highs only; no node quota/start
  std::uint64_t iteration_limit = 100000;
  std::size_t max_auxiliary_variables = 100000;
  std::size_t max_lifted_nonzeros = 2000000;
  double stationarity_tolerance = 1e-7;
  double complementarity_tolerance = 1e-7;
};
struct QuadraticValidation {
  bool primal_valid = false, objective_valid = false;
  bool kkt_available = false, kkt_valid = false, bound_valid = false;
  double max_stationarity = 0, max_complementarity = 0;
  std::optional<double> original_objective, normalized_lower_bound;
  std::vector<double> square_values, original_gradient;
  std::string message;
};
struct QuadraticResult {
  SolveResult result;  // original owner/revision/slots, not lifted identity
  QuadraticValidation checks;
  std::optional<double> vendor_objective, vendor_dual_estimate;
  std::uint64_t qp_iterations = 0;
};
QuadraticResult solve_quadratic(const QuadraticSnapshot&,
                               const QuadraticOptions& = {});
QuadraticResult solve_quadratic(const QuadraticModel&,
                               const QuadraticOptions& = {});
BackendCapabilities quadratic_capabilities();
```

`QuadraticSnapshot` exposes const variable/row/full-objective views and identity,
not a public `ModelSnapshot` or `Model&`, and has no conversion operator. Its
private data can contain a copied `ModelSnapshot` plus squares for compiler reuse.
The mutable wrapper can privately own `Model`: normalize/validate every square
and finish all allocating staging before calling `Model::set_objective` for the
linear part and revision increment, then swap the already-staged squares without
throwing. Thus quadratic-only objective changes advance the same revision, and
failed mutation preserves both old objective and revision. Moves preserve the
owner; moved-from access fails explicitly. Snapshot data owns all metadata after
model destruction. Do not attach squares to an externally accessible linear
`Model` with the same identity/revision.

An import from an existing linear model, if added later, must allocate a fresh
wrapper owner and return an explicit original-to-wrapper handle mapping, while
rejecting unsupported active types/metadata. It must not borrow the original
owner and create two different objectives with identical identity and revision.

## Independent numerical acceptance and original dual checks

1. Validate snapshot structure and finite-box scope before backend construction.
   Establish convexity from positive square weights and affine terms, not a
   user flag or HiGHS status. No arbitrary sparse Hessian input in this slice.
2. Validate finite primal values in original slots, bounds and original rows.
   Compute each `a_k'x+b_k` with compensated accumulation including its offset;
   compute the full original objective and gradient independently of the lifted
   Hessian and auxiliary values. Preserve numerical residuals and check the
   lifted equalities/auxiliary objective too. Never use a rounded auxiliary value
   as the authoritative original square residual.
3. The proposed backend always minimizes normalized `F`, so its original-column
   and original-row duals already have normalized signs: do not multiply them by
   `s` a second time. Multiply by `s` only when exposing original-sense duals to
   callers. For `L<=Ax<=U`, a positive normalized row
   multiplier belongs to a lower side and a negative multiplier to an upper
   side. Fixed/equality rows allow either sign. Check absent-side signs,
   complementarity, and stationarity `grad(F)-A'lambda-z=0`. Use both absolute
   and scale-aware residual reports; a large objective offset must not mask a
   gradient residual. Do not trust `dual_valid` without size/finite/sign checks.
4. A vendor `Optimal` result is promoted only with independently valid original
   primal/objective, known convexity, accepted original KKT residuals, and a
   residual-corrected bound whose ordered original objective gap closes within
   requested tolerances. Otherwise retain a valid primal point but report
   `NumericalFailure`/the actual interruption, with no invented optimum or gap.
   A contradictory `bound > primal` for minimization is not silently clamped.
5. `Guarantee::Numerical` remains essential: primal feasibility and KKT acceptance
   use explicit tolerances. An independently enclosed dual bound is not an exact
   primal-feasibility or complete solve certificate. Exact and Certified solve
   requests return `Unsupported`. Vendor dual objective estimates stay separate.

A finite-box continuous objective is bounded whenever feasible. Therefore a
backend `Unbounded`/ambiguous infeasible-or-unbounded report is a numerical failure
for this slice, not a valid unbounded conclusion. A numerical infeasible report
must not coexist with an independently valid primal witness. If accepted as
`Infeasible`, identify it as the backend's numerical conclusion; do not claim an
independently checked Farkas certificate. Stronger infeasibility validation is a
separate later feature.

## Residual-corrected lower bound: proposed verifier

Use the original positive squares and any finite chosen `t_k`, for example a
numerical approximation of `a_k'x+b_k`. Completing a square gives

```
w*z^2 >= 2*w*t*z - w*t^2,  w>0.
```

Choose any finite signed row multipliers `lambda_i`, selecting finite row lower
bounds for positive multipliers and finite upper bounds for negative ones. Set a
multiplier to zero when its chosen side is unavailable; it is a proposal, not a
solver-authenticated proof value. Define

```
r = s*c + sum_k 2*w_k*t_k*a_k - A'lambda
K = s*c0 + sum_k (2*w_k*t_k*b_k - w_k*t_k^2)
            + sum_i lambda_i * selected_row_bound_i
D = K + sum_j min(r_j*l_j, r_j*u_j).
```

Then `D <= min F(x)` for every original feasible point. The calculation uses the
original rows/bounds/squares, not the lifted matrix. It remains valid with a
singular Hessian, inaccurate duals, nonstationary candidate, or infeasible
candidate; those may only make the bound weaker. This is a derived application
of weak duality and the quadratic conjugate, not a claim that HiGHS exports such
a certificate. This parameterization also avoids division by small square
weights. [Boyd and Vandenberghe, *Convex Optimization*, duality/conjugates](https://web.stanford.edu/~boyd/cvxbook/).

Implement checked one-sided enclosures, not a guessed epsilon subtracted from a
floating answer. Enclose each arithmetic operation and use the lower endpoint
for `K`. For a residual interval `[rlo,rhi]`, use a lower enclosure of the minimum
of all four endpoint products with `[l,u]`. Overflow, non-finite arithmetic,
unsupported rounding behavior, or budget exhaustion makes the bound unavailable.
Test the enclosure routine against an exact rational oracle, including subnormals,
cancellation and extreme ratios. Require IEEE semantics/no fast-math, or use a
verified higher-precision alternative; do not assume `long double` is wider on
arm64. Keep the Numerical solve guarantee even if the bound subroutine is checked.

Convert the final bound back as `D` for minimization or `-D` for maximization;
`F` already included the signed original offset, so do not add it twice. Restore
row/bound dual signs and report original objective values consistently. Never use
a MIP bound field, a stationarity residual rounded to zero, or the vendor primal
objective as a substitute for this computation.

For a future unbounded original domain, a nonzero residual can make its box
infimum `-infinity`, even if tiny. Supporting those models with strong finite
bounds needs verified stationarity or a retained positive-curvature residual
bound, or independently justified finite domain tightening. Do not drop this
residual or clip the domain to make a gap appear closed.

## Old-route safety and integration gates

| Existing entry point | First-slice rule and required regression |
| --- | --- |
| `solve(Model/ModelSnapshot)`, Auto | Unchanged. Wrapper is not convertible; use only explicit `solve_quadratic`. Optional future typed `solve(QuadraticSnapshot)` may delegate, never expose its private linear part as a user model. |
| `solve_native`, `solve_native_lp`, `solve_native_search` | No quadratic overload or implicit conversion. Compile-time detection tests show wrapper/snapshot cannot bind. Explicit `Backend::Native` passed to `solve_quadratic` returns `Unsupported`. |
| `presolve_integer` and postsolve | No wrapper conversion, so integer presolve cannot drop squares. Future quadratic substitution must update square offsets/full objective and preserve owning identity. |
| pools, repair, lexicographic workflow, diagnostics | No wrapper overload in Q1. Do not convert to the private linear snapshot. A later feasibility-only diagnostic may deliberately ignore an objective, but must have a typed documented contract. Quadratic retention locks are QCP and cannot be passed to a linear lex workflow. |
| incremental `Session` | Reject by type; no hidden Hessian omission or stale basis. A dedicated QP session is later work with its own revision and warm-start rules. |
| common validation | Add a typed quadratic checker. Internal reuse of ordinary row/bound validation is permitted, but its linear objective cannot be returned as the original quadratic objective. |
| LP/MPS I/O and CLI | No wrapper export/import in Q1. Existing strict parsers continue rejecting nonlinear LP syntax and unsupported MPS sections; add explicit QP-file negative fixtures. No file may be partially written before unsupported capability is reported. |
| C API/Python | No opaque wrapper token is an existing linear Model token. Future QP bindings use a new handle kind and versioned objective payload; existing functions reject a wrong kind. No ABI struct reinterpretation, no addition of hidden squares to existing Model tokens. |
| snapshots/results | Existing C++ aggregate `ModelSnapshot` layout stays unchanged. QP snapshots are immutable distinct types; results retain wrapper owner/revision and original slots. All lifted indices remain private. |

If shared `ModelSnapshot` quadratic metadata is introduced in a later version,
all of these routes require explicit active-quadratic capability checks before
any transformation/backend conversion. Every full-replacement versus linear-only
objective mutation must be specified, and serialized/binary compatibility must
be versioned. The isolated wrapper avoids that cross-cutting risk now.

## Implementation allocation and budget contract

Proposed independently owned files:

- `gecode/optimize/quadratic.hpp/.cpp`: wrapper, immutable snapshot, typed full
  objective, transactional normalization/mutations, structure/point validation.
- `gecode/optimize/quadratic_solve.cpp`: pinned HiGHS lowering, options/statuses,
  original KKT and bound acceptance, backend-off boundary.
- `gecode/optimize/quadratic_bound.hpp/.cpp`: private numerical enclosure and
  original-form lower-bound checker, if separation keeps the first two files small.
- `test/optimize/quadratic.cpp`, `test/optimize/quadratic_bound.cpp`: model, oracle,
  fake-backend coordinator and enclosure tests.
- `docs/solver-parity/QUADRATIC.md`: implemented contract and actual validation.

Root owns registration, installation/umbrella integration and capability exposure.
Expose the supported class through `quadratic_capabilities()`; leave the ordinary
`Model` capability response unchanged until its API can express quadratic data.
No existing shared source needs editing beyond that integration for Q1. Avoid a
new required dense linear-algebra dependency. Reuse the pinned HiGHS build; OSQP
is an optional differential research oracle, not a new runtime requirement.

One monotonic budget starts before snapshot/copy and covers normalization,
preflight/lifting, backend import, solve and independent acceptance. Pass the
remaining deadline and QP iteration limit to HiGHS. No starts, node quotas or
multiple workers in Q1; reject rather than silently reinterpret them. Check a
cancelled token before/after backend work and before publishing; a live active-set
callback is not promised. Enforce auxiliary/nonzero caps before large allocations.
No missing HiGHS fallback. Nullspace/solver failures are explicit, not evidence
of nonconvexity, infeasibility, or a supported problem becoming an LP.

## Conformance and research gate

1. **Foundation, no backend:** identity/revision, move/destruction/history,
   tombstones, reference-protected removal, transactional malformed square input,
   canonical term duplicates, invalid weights, both named sense methods, and
   compile-time non-conversion to every old route. Keep old snapshots unchanged.
2. **Exact tiny oracle:** rational KKT active-set enumeration for small rational
   strictly convex problems, plus analytic singular cases. A vertex/grid search
   is not an exact QP oracle. Cover unconstrained interior points *inside the
   finite box*, active bounds, equalities, ranged rows, fixed variables, empty
   objectives, constant squares, both senses/offsets, rank deficiency and ties.
3. **Lowering/metamorphism:** verify `Qzz=2w`; reconstruct residuals; split a square
   into two identical half-weight squares; change its affine sign; permute original
   slots; duplicate/reorder linear rows; reverse objective sense/sign; add large
   objective constants. Require identical original objectives and admissible gaps.
4. **Adversarial numerics:** positive-diagonal indefinite Hessian rejection by API,
   near-singular Gram factors, extreme weights/coefficient ratios, threshold
   filtering, overflow/underflow, large-offset cancellation, raw auxiliary/objective
   mismatch, missing/malformed/incorrect-sign duals, nonzero residual on a wide
   box, bound above primal, false optimal/infeasible/unbounded reports. Perturbed
   working-model solutions must pass the unregularized checker or fail explicitly.
5. **Coordinator/budgets:** zero deadline, pre/mid-work cancellation, iteration,
   storage and allocation limits, late valid/invalid candidates, foreign/stale
   identities and mask errors, unavailable backend, Exact/Certified rejection,
   original model unchanged. No status or bound manufactured by a fake oracle.
6. **Integration:** ordinary/native/hybrid/HiGHS regressions and installed C++
   consumer; core-only and full ASan/UBSan builds; Linux/macOS/Windows. C/Python
   remain explicitly outside Q1, with negative handle/type tests when added.
7. **Evaluation after correctness:** compare lifted versus direct diagonal/simple
   factored QPs against raw pinned HiGHS and an independently implemented solver.
   Use application-generated bounded least-squares/portfolio/penalty problems,
   report primal/KKT residuals and checked gaps alongside time and memory. The
   Maros–Mészáros collection is a later broad QP corpus: an arbitrary-Hessian or
   unbounded-domain instance is outside Q1 unless an equivalent supported form is
   established. Do not count unsupported exclusions as solved benchmark cases.

Primary research to read/replicate next:

- Michael Feldmeier, *Going quadratic: Applying advanced techniques from linear
  programming to convex quadratic programming*, MPhil, University of Edinburgh,
  2024: reduced-Hessian implementation, ratio tests, pricing and its limitations.
  [Author's thesis](https://era.ed.ac.uk/bitstreams/977adea4-6729-4707-a3be-ff55faf95b33/download).
- Anders Forsgren, Philip E. Gill and Elizabeth Wong, *Primal and dual active-set
  methods for convex quadratic programming* (2015): KKT systems and primal/dual
  active-set initialization; guide degeneracy and singular-case tests.
  [Paper](https://arxiv.org/abs/1503.08349).
- Bartolomeo Stellato et al., *OSQP: An Operator Splitting Solver for Quadratic
  Programs*, Mathematical Programming Computation 12, 2020: independent algorithm
  family for differential numerical checks, not a convexity oracle.
  [Authors' page](https://web.stanford.edu/~boyd/papers/osqp.html),
  [official residual/infeasibility conditions](https://osqp.org/docs/solver/index.html).
- István Maros and Csaba Mészáros, *A Repository of Convex Quadratic Programming
  Problems*, Imperial College report DOC97/6 (1997), journal version 1999: source
  benchmark formulation and objective conventions.
  [Original report](https://www.doc.ic.ac.uk/research/technicalreports/1997/DTR97-6.pdf).

A future arbitrary sparse Hessian API requires a separate verified PSD/NSD
acceptance mechanism. A floating Cholesky failure does not distinguish singular
PSD from indefinite input reliably; tolerating negative pivots or projecting
negative eigenvalues changes the model. Exact/rational or rigorously enclosed
factorization, or sufficient verified diagonal-dominance subclasses, are possible
later gates. Convexity only on an equality-restricted feasible space is also
outside Q1. Preserve these boundaries until their own proofs and conformance
oracles exist.

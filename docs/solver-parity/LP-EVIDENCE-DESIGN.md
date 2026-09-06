# O3: explicit recovery of numerical LP evidence

Original design, 2026-09-05. The bounded O3 auxiliary-model implementation is
documented in [LP-EVIDENCE.md](LP-EVIDENCE.md). O1 and O2 remain independent;
this operation adds no vendor ray getter, new default routing, or exact certificate.

## Recommendation: explicit auxiliary models

Use a new `analyze_lp_evidence(Model/Snapshot, options)` operation, owning the
original source and using fresh private numerical LP backends. Do not accept a
mutable Session or change an existing SolveResult. First recover evidence through
explicit normalized auxiliary LPs rather than calling the vendor ray getters.
The caller is authorizing actual additional work with a new whole-operation
budget; passive accessors never trigger recovery.

Pinned HiGHS 1.15.1 `getDualRay` can zero costs, change integrality/Hessian handling,
disable presolve, call `run`, and invalidate primal/dual info while restoring
objective data. `getPrimalRay` can also change options and run again. Even a known
ray may need a basis solve. Recovery paths assert the existence of an invertible
representation after the internal solve, complicating interrupted recovery. The
no-row path returns no ray even for a simple unbounded bound-only LP. These are
reasons to avoid treating retrieval as a harmless query.
[HiGHS recovery source](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsInterface.cpp#L1571),
[public declarations](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/Highs.h#L596).

Explicit auxiliary LPs allow exact accounting of requested backend calls and
independent model construction/checking. The first implementation can call the
existing one-shot linear solver on private `Model` instances with remaining time
and the shared cancellation token. It needs no solve.cpp/session changes or
backend getters. Its costs are extra solves and larger auxiliary matrices;
reusing a vendor ray as a checked fast path remains a later, separately tested
optimization.

## Supported source and candidate API

Admit original Continuous linear models only, with no active indicators/globals,
through Auto/HiGHS and Numerical guarantees. Fixed Integer/Binary variables are
still unsupported. Native, Exact, Certified, semis, QP and active logical/global
models fail explicitly; no relaxation or silent metadata erasure is allowed.
Own and structurally validate the complete source snapshot, including original
IDs, revision, tombstones and protected metadata. Check existing adapter numerical
ranges and the expanded auxiliary dimensions/nonzeros before allocating or
solving. Inactive metadata remains owned and must pass structural validation.

Proposed names, not frozen declarations:

```cpp
enum class LpEvidenceRequest { Automatic, PrimalRay, Farkas, Both };
struct LpEvidenceOptions {
  SolveOptions solve;                 // Numerical LP policy and total time/cancel
  LpEvidenceRequest request = LpEvidenceRequest::Automatic;
  LpEvidenceTolerances checks;        // finite nonnegative absolute tolerances
  LpEvidenceLimits limits;           // finite dimensions/nonzeros/work/storage caps
};
enum class LpEvidenceCompletion { Complete, Interrupted, Rejected };
struct LpEvidenceResult {
  LpEvidenceCompletion completion;
  std::optional<Termination> stop_reason;
  std::string message;
  std::shared_ptr<const LpEvidence> evidence;
};
LpEvidenceResult analyze_lp_evidence(const ModelSnapshot&, const LpEvidenceOptions& = {});
LpEvidenceResult analyze_lp_evidence(const Model&, const LpEvidenceOptions& = {});
```

Finalize typed reasons for resource/unsupported/invalid-evidence boundaries before
header approval. `Complete` means the requested analysis completed; it is not an
original-model optimality or feasibility status. An analysis can complete with
no accepted evidence. Do not create an ordinary original-model SolveResult,
original best bound, or original gap from the auxiliary outcomes.

`LpEvidence` will have a private constructor and immutable owned fields:

* Exact original source snapshot and source identity/revision; original active
  masks and slot counts. Checked Variable/Constraint accessors reject foreign,
  deleted, and out-of-range IDs.
* Separate typed primal-ray and Farkas groups: NotRequested, Available,
  Unavailable, or Rejected, with reason and message. Available always means
  accepted **numerical evidence**, never an exact proof.
* Primal evidence: an original-slot feasible base point and normalized direction,
  independently computed original row-direction activities, base validation,
  recession residuals, and normalized objective slope. Publish the pair only
  after both checks pass; direction alone cannot imply unboundedness.
* Farkas evidence: signed original row multipliers, derived original column-bound
  multipliers, each selected finite side and its contribution, signed contradiction
  margin and stationarity residuals. Zero multiplier is distinct from unavailable;
  its selected side is absent and contribution zero.
* Ordered owning auxiliary-stage records with phase kind, private model identity,
  dimensions, attempted flag, actual backend/version/termination, independent
  candidate validation and an explicitly named `auxiliary_result` if a full
  SolveResult is retained. Its objective/bound/gap belongs exclusively to that
  private auxiliary model. No source identity rewriting is permitted.
* Attempted phase/backend-call counts and elapsed time. No hidden fallback calls.

The artifact and its vectors remain usable after caller models, snapshots,
options and private backend instances are destroyed. Stage identities and explicit
phase names must prevent interpreting a feasibility objective of zero as an
original objective value. Store only needed stage models/mappings; avoid retaining
multiple full matrices unless justified by the provenance contract and storage cap.

## Auxiliary LPs and original checks

Write the source as `L <= A*x <= U`, `l <= x <= u`, objective `c*x+c0`; let
`s=+1` for min and `s=-1` for max. All transformations use original finite-side
semantics and preserve explicit maps to original slots.

### Feasible base point

Copy the source feasible set to a private owner with objective zero and offset
zero. A candidate must pass independent original bound/row validation, exact
source-slot mapping and finite active-value checks. An Infeasible claim accompanied
by a correctly sized independently feasible assignment is inconsistent backend
evidence, even if its `solution_validated` flag is false.

This phase does not optimize the original objective. Its Unbounded status is
impossible because its objective is identically zero; treat that as a backend
error. A source feasibility claim is recorded as stage evidence, not promoted
into an exact original proof.

### Improving direction

Build a bounded direction LP minimizing `s*c*d`, with no objective offset.
Every active direction component is in `[-1,1]`, additionally restricted by the
original variable bounds:

| Source sides | Direction bounds |
|---|---|
| Both finite | `d=0` |
| Only finite lower | `0<=d<=1` |
| Only finite upper | `-1<=d<=0` |
| Both infinite | `-1<=d<=1` |

For each original row, both finite sides require `A*d=0`; lower-only requires
`A*d>=0`; upper-only requires `A*d<=0`; a free row imposes no recession restriction.
The zero direction is always feasible and the objective is bounded by the box.
Thus auxiliary Infeasible/Unbounded statuses are backend errors, not ordinary
"no ray" results. The no-row case works through the same bounded auxiliary LP.

Independently normalize a finite nonzero candidate by positive infinity norm,
retaining orientation. Reject nonfinite arithmetic or normalization that erases
nonzero entries through underflow. Recompute source variable and row recession
conditions and strict improvement `s*c*d < -minimum_improvement`. A validated
source feasible base point is mandatory before publication. An infeasible source
can have an improving recession direction; that is not unboundedness evidence.

### Farkas contradiction

Introduce one nonnegative multiplier for each finite side of every active source
row and column. Missing infinite sides have no multiplier column. Let row lower/
upper multipliers be `p,q` and variable lower/upper multipliers `a,b`. Solve:

```text
maximize  L*p - U*q + l*a - u*b
subject to A^T*(p-q) + a-b = 0
           sum(p)+sum(q)+sum(a)+sum(b) <= 1
           p,q,a,b >= 0
```

The zero point is always feasible, and the normalization bounds this objective.
An Infeasible/Unbounded auxiliary status is inconsistent backend output. Equality
or fixed sides may both have multipliers; their algebraic signs stay explicit.
Constant source rows are supported: their multiplier contributes only to the
normalization row and contradiction objective, so a contradictory constant row
can produce evidence without any source column.

Recover signed original row multipliers `y=p-q` with checked compensated
arithmetic. Normalize by a positive deterministic scale, initially
`max(abs(y))=1`, and independently derive `z=-A^T*y` in original coordinates.
The returned auxiliary bound multipliers are not trusted as a substitute for
this original computation. Recheck stationarity using the published normalized
values, and compute:

```text
margin = sum(y_i>0 ? y_i*L_i : y_i*U_i)
       + sum(z_j>0 ? z_j*l_j : z_j*u_j).
```

Skip exactly zero multipliers before selecting/touching an infinite side. Any
nonzero multiplier requiring an infinite endpoint rejects finite contradiction
publication. Require a strictly positive signed margin above the explicit
minimum; never flip a failed sign to manufacture acceptance. Original objective
sense and offset play no role in this evidence.

All original accumulations use checked compensated arithmetic, preserving sum
and correction until relevant differences are taken. Tolerances and normalization
must be recorded, and signed residuals/margins must not be clipped. Finite-precision
recession/stationarity checks cannot certify an infinite trajectory or an exact
contradiction. These values remain numerical diagnostics under all statuses.

### Cross-evidence consistency

A source point accepted by the declared primal tolerances and a positive Farkas
contradiction accepted by its declared tolerances may overlap near a numerical
boundary. If both occur, return explicit inconsistent-evidence rejection and
retain the diagnostic residuals/margins; do not publish mutually incompatible
accepted conclusions. Never resolve this conflict by upgrading one to Exact,
changing tolerances silently, discarding a inconvenient point, or overwriting an
existing result. Tests must deliberately create this overlap with different
primal and contradiction tolerances.

## Phase selection, budgets and failure publication

Automatic runs source feasibility, then direction recovery when a feasible point
is available or Farkas recovery after an infeasible stage (at most two calls).
Explicit PrimalRay requires feasibility plus direction; explicit Farkas can run
its normalized contradiction LP directly. Both requests may require three calls.
A phase rendered unnecessary/impossible by an earlier result remains explicitly
NotAttempted; counts must not fabricate a solve. A bounded source can complete
with no strict improving direction and no Farkas contradiction.

Construct one outer monotonic SolveBudget before copying or admission. Every
phase receives only remaining time and the same cancellation token. Check before
starting, after backend return and destruction, during transformation/checking,
and after temporary cleanup before publication. Never grant each auxiliary solve
the original full time limit. All models are LPs, so branch-and-bound node usage
is zero; structural work and backend-call caps are separate quantities, not
invented solver nodes. Reject simultaneous primal_start initially rather than
applying it to unrelated auxiliary variables.

Every requested stage and candidate is treated as untrusted: exact private
identity/revision, masks and dimensions; finite primal objectives; valid signed
infinite or finite bounds where applicable; no NaNs; independently validated
auxiliary and original values. Optimal normalized auxiliary status requires a
valid finite candidate. Candidate feasibility alone may yield numerical evidence
without requiring its auxiliary objective to be proven optimal, but any limited
status must remain visible and publication must still be timely. A stage limit
or budget exhaustion stops further work; no hidden retry or recovery LP follows.

Initial publication should be conservative: a final budget overrun clears accepted
evidence groups, retains explicit stage/diagnostic information, and reports the
limit. Backend factorization/cleanup is cooperative and can overshoot; it cannot
be advertised as forcibly preempted. Resource caps need deterministic checked
counts for expanded variables, rows, nonzeros, retained slots and element visits.
Malformed late input must not consume backend work before admission is complete.

## Test matrix before runtime integration

1. Hand-derived/rational small primal witnesses: `min -x`, `x>=0`, base 0 and
   direction 1; upper-only/max variants; mixed rows, fixed/free variables,
   equality and ranged rows. Check slope independently and offset invariance.
2. Farkas row/bound witness: row `x>=1`, bound `x<=0`, `y=1`, `z=-1`, margin 1.
   Add multirow contradictions, upper/lower sign variants, fixed/ranged sides,
   free entities, constant rows, and objective sense/offset independence.
3. Infeasible source with an improving recession direction: missing/invalid
   base point prevents primal publication. Feasible point plus tolerance-qualified
   positive Farkas margin must trigger cross-evidence inconsistency diagnostics.
4. Tiny rational enumeration/linear algebra checks of the auxiliary transforms,
   independent of generated private rows and the vendor's own ray checker.
   Normalized direction/Farkas zero points must always validate.
5. Original tombstones, duplicate names, mapped private owners/revisions,
   mutation/destruction of all caller containers and existing session/history
   invariance. Old results and options must remain unchanged by analysis.
6. Fake zero, nonfinite, wrong orientation, wrong dimension/mask/owner/revision,
   bad selected infinite side, stationarity and strict-margin failures; large
   cancellation and normalization underflow. No vectors published from bad data.
7. Impossible auxiliary statuses, forged infeasibility beside a feasible point,
   absent optimal candidates, wrong auxiliary objective/bound/gap semantics,
   valid infinite bounds and ordinary unavailable evidence.
8. Deterministic cancellation/limits at copy, admission, phase boundaries,
   validation, publication and cleanup; exact attempted counts; no subsequent
   solve after stop; bounded storage/work overflow checks and allocation failure.
9. Core missing-backend/unsupported admission, normal real HiGHS and fully
   instrumented facade/backend sanitizer panels, existing O1/O2 regressions and
   installed consumers. No performance claim from concurrent test execution.

C/Python bindings, FAST registration, vendor-ray fast paths and exact certificate
verification follow only after the C++ algorithm, ownership and publication gates.

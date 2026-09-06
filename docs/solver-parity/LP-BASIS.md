# Owning LP basis starts: O2

`make_lp_basis` copies either an available O1 basis or caller-created
`LpBasisData` into an immutable owning `LpBasis`. `solve_lp_with_basis` and its
`SolveSession` overload return an ordinary observed solve plus a separate
submission report and an owning reference to the requested basis. Existing
`SolveOptions`, `LpObservationOptions`, and O1 record layouts are unchanged.

```cpp
using namespace Gecode::Optimize;
auto first = solve_lp_observed(model);
if (first.observations &&
    first.observations->basis().state == LpObservationState::Available) {
  LpBasisSolveOptions options;
  options.basis = make_lp_basis(*first.observations);
  auto next = solve_lp_with_basis(model, options);
  // next.submission describes submission; next.observed.result describes solve.
}
```

## Initial source and status policy

A basis source must be an ordinary Continuous linear model with no active
indicator/global records or constant rows. Each row/column status vector has
exactly the original slot count; live slots have a status, tombstones have none.
Every enum is checked explicitly. Lower/Upper require the corresponding finite
bound; Zero requires a free row/column. Fixed entities may be nonbasic on either
side. NonbasicUnspecified lets HiGHS choose its nonbasic position. Basic statuses
are permitted on any entity, but the total number of basic entities must equal
the number of active rows. These structural checks do not claim nonsingularity,
primal feasibility, dual feasibility, or optimality. A valid nonoptimal basis is
a legitimate start.

Caller data is copied before the factory returns. Changes to its source or status
arrays cannot alter the artifact. Basis origin records whether the factory used
caller data or an O1 observation. An unavailable O1 basis cannot be converted
into an empty or fabricated start.

The first submission policy requires the same source model owner, revision,
original variable/row slot identities and active masks. Active variable types,
bounds and names; active row bounds, names and matrix terms; and objective sense,
offset and coefficients must match exactly under ordinary scalar/string equality.
The same revision alone is insufficient: public snapshots are untrusted. Inactive
payloads do not describe the mathematical model and need not match; inactive
variable/row identities and masks still must match. Every complete input snapshot
is independently structurally validated, including original protected metadata.
Active indicators/globals remain unsupported.

Changing a cost, bound, row side, sense, offset or active name/revision requires a
new basis artifact. More permissive compatible-matrix hint policies are deferred.
The existing internal session basis reuse policy is unchanged and is separate
from this public source-matched submission contract. Foreign source owners,
malformed dimensions/statuses and source mismatches fail before backend/session
mutation. A missing `basis` is an explicit InvalidModel input error; the API never
silently turns into an ordinary solve. Simultaneous `primal_start` is rejected
rather than assigning implicit precedence.

Numerical HiGHS is the only supported backend/guarantee. Native, Exact and
Certified remain explicit Unsupported. A missing HiGHS build returns Unsupported
without a backend attempt. Basis factories perform structural checks without
requiring an installed numerical backend. Empty models can carry a valid empty
basis; the existing direct empty-model solve performs no basis submission and
reports NotAttempted.

## What submission states mean

* **NotAttempted:** admission, unsupported routing, a pre-submission limit, or an
  empty model prevented a backend basis call. The ordinary result explains why.
* **Accepted:** HiGHS accepted and returned structurally valid statuses identical
  to the request, before optimization.
* **Repaired:** HiGHS accepted but changed at least one status during its immediate
  basis factorization/repair step. This includes completing/replacing singular
  structural columns with logical row columns, and any nonbasic normalization.
* **Rejected:** backend submission or validation of its returned status data
  failed. Allocation failure also prevents completing submission and has the
  separate ordinary MemoryLimit termination. No fallback optimization occurs.
* **Interrupted:** the submission/checking phase crossed its cooperative budget;
  complete accepted-status information is not published.

`backend_attempted` records whether `setBasis` was entered. `statuses_changed` is
absent until the accepted returned statuses have been completely checked; false
is distinct from absent. An accepted/repaired submission can be followed by a
limited, infeasible, unbounded or failed solve. It is not evidence that the final
solve is optimal or faster. Changes to the *final optimum basis* do not retroactively
turn Accepted into Repaired. Earlier submission facts may survive a later solve
limit, while O1 follows its own conservative final-limit clearing policy.

The result retains the requested basis and its original source independently of
the input options, model and session. Final observations and ordinary result are
separate owning historical artifacts. No checkpoint, saved search tree, exact
proof, conditioning guarantee or independent nonsingularity certificate is
provided.

## Backend mechanics, cleanup and budget

Pinned HiGHS 1.15.1 checks and factors nonzero-row alien bases inside `setBasis`,
which may repair singular or incomplete bases. O2 always uses that alien path for
nonzero rows, even when the source artifact came from HiGHS observations. It does
not trust a caller-provided validity flag. Returned statuses are inspected and
compared **immediately after `setBasis`, before `run`**. All compact slots are
mapped explicitly to original slots and revalidated.
[HiGHS setBasis](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/Highs.cpp#L2732),
[alien basis accommodation](https://github.com/ERGO-Code/HiGHS/blob/04024d701f79feb8e2f18bc3df0dffc04ef05088/highs/lp_data/HighsSolution.cpp#L1850).

The pinned alien zero-row branch indexes internal column-status storage before
its general dimension check. O2 avoids that branch: zero rows require zero basic
entities and exact dimensions, so the basis matrix has dimension zero; a checked
non-alien basis uses HiGHS's consistency path. This limited exception does not
trust a potentially singular nonzero-dimensional caller basis.

The shared monotonic budget starts before source copying and covers admission,
conversion, basis preparation, factorization/repair, optimization, O1 checks and
cleanup. Interrupt callbacks and the remaining HiGHS time limit are installed
before submission. Remaining time is reapplied before optimization without
restarting the outer clock. Factorization/scaling may contain uninterruptible
regions; checks around those regions prevent a late phase from publishing a
false completion but do not guarantee forced wall-clock preemption.

Rejected or interrupted submission unwinds the callback scope before discarding
the dirty backend. The next session call loads a clean model. A backend rejection
does not trigger a hidden cold solve. Ordinary subsequent solves reset their
per-call options and work normally. Explicit submitted bases are not counted as
an internally retained `basis_warm_starts` statistic. Other model-load/update
statistics retain their existing meanings.

## Verification and build integration

`test/optimize/lp_basis.cpp` covers copied factory ownership, malformed IDs/statuses,
missing/extra slots, invalid finite-side/zero statuses, incorrect basic counts,
all active-content/revision compatibility gates, missing starts/backend,
unsupported policies, simultaneous primal starts, a nonoptimal accepted basis
whose final optimum basis differs, singular repair, safe zero-row submission,
tombstones, ordinary/observed session reuse, disabled O1 groups and pre-cancellation.

`test/optimize/lp_basis_failure.cpp` is a **separately compiled test variant**.
Compile `solve.cpp` with `GECODE_OPTIMIZE_WITH_HIGHS=1` and
`GECODE_OPTIMIZE_TEST_LP_BASIS_FAILURE=1`, and link this test with the remaining
ordinary Optimize objects plus real HiGHS. The test supplies the private selector
`Detail::lp_basis_test_cancel()`. Immediately after a successful *real* `setBasis`
mutation, the variant injects either a backend error result or cancellation. It
checks no fallback, no stale observation publication, callback/dirty-state cleanup,
and a successful next ordinary solve with a new model load. The variant also
covers zero-row rejection. Its selector and injection code are absent from
production binaries; the normal test uses unmodified backend return values.

Normal and fully instrumented facade/HiGHS ASan+UBSan panels are required, along
with backend-free admission tests and O1/ordinary solve/session regression tests.
`lp_basis_detail.hpp` is private and must not be installed. Root build registration
and later C/Python bindings remain separate integration work. Rays, basis solves,
sensitivity/ranging and compatible-edited-source hints remain outside O2.

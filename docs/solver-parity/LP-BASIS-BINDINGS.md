# C and Python basis submission

This additive ABI v1 surface binds [the O2 basis contract](LP-BASIS.md). It supports ordinary continuous linear models through the numerical HiGHS route. Native, Exact, and Certified solve requests return `Unsupported`; no relaxation or solver fallback occurs. Basis construction itself needs no backend.

`basis_from_model` copies the current model snapshot and caller status arrays. Counts include every original variable and row slot, including deleted history. Status `-1` denotes an inactive slot; every active slot needs one of the explicitly mapped `GECODE_OPT_LP_BASIS_*` values. The factory checks dimensions, domains, status applicability, and basic count. It cannot promise nonsingularity: HiGHS factorization occurs only during a budgeted submission. `basis_from_observed` requires an owning observation token whose basis group is available. A detached Python `LpObservations` value contains observations, not the full source model, and is not an input to this factory.

`solve_lp_with_basis` and `session_solve_lp_with_basis` take the existing `gecode_opt_lp_options_v1` record. Its exact outer and nested sizes, zero reserved fields, finite tolerances, and request flags are checked. Simultaneous primal starts are invalid. The basis must match the current source owner, revision, active entities, labels, matrix, bounds, and objective. Inactive payload content is not compared. Edits, even edits to an equivalent model, require a new basis. Admission failures never submit a basis or trigger an ordinary solve. Session recovery after a backend submission failure follows the C++ clean-reload policy.

The result keeps the solve's ordinary termination and a separate submission report. `Accepted` means the statuses returned immediately after `setBasis` matched the request. `Repaired` means HiGHS changed them during that operation. Neither is a numerical optimality certificate, a final optimal basis, or a saved search checkpoint. A later time limit may coexist with accepted submission facts. `statuses_changed` has an explicit presence flag; it is absent before a completed submission. Final observations can be unavailable independently of the requested basis and submission report.

All tokens own their data. `basis_result_copy_basis`, `basis_result_copy_observed`, and the existing `lp_observed_result_copy_result` allocate independent registry tokens; closing a parent, model, or session leaves copied children valid. Results retain historical original entity identities. Entity lookups reject wrong kind, foreign owner, out-of-range and deleted slots. Wrong or destroyed opaque tokens return `INVALID_HANDLE`. Missing requested basis is the distinct `NO_BASIS` error (defensive handling of an empty C++ result); missing observations retain `NO_OBSERVATIONS`. A present but unavailable basis observation is a `MODEL_ERROR`, with an actionable message. C++ exceptions never cross the C boundary.

Array and text queries use null/capacity zero to obtain the required count. Short buffers receive no partial output; text counts include the terminating NUL. Input counts are checked for address/vector overflow before traversal. Factory output handles are initialized to zero before work. Info output records require exact `sizeof` and return zero reserved fields. No accessor returns borrowed vector storage. Registry lookup retains shared ownership and releases the global registry lock before copying or solving; per-model and per-session locks preserve existing serialization. Destroy invalidates its token immediately while a lookup already in flight may complete using its retained ownership.

Python exposes `LpBasis`, `LpBasisInfo`, `LpBasisOrigin`, `LpBasisSubmissionState`, `LpBasisSubmission`, and `LpBasisSolveResult`. Ordinary sequences work without NumPy; `None` denotes inactive statuses. Booleans, fractional values, unknown integers, and statuses outside the ABI range are rejected before C conversion. Basis information and submission reports are frozen values; status lists are immutable tuples. Owners support explicit `close()` and context managers.

```python
from gecode_optimize import Model, LpBasis, Session, load_library

library = load_library()
with Model(library) as model:
    x = model.add_variable(lower=0, upper=10)
    model.add_row([(x, 1)], lower=4)
    model.set_objective([(x, 2)], offset=7)
    with model.solve_lp_observed() as first:
        basis = LpBasis.from_observed(first)
    with basis, Session(library) as session:
        with session.solve_lp_with_basis(model, basis) as submitted:
            print(submitted.submission.state, submitted.termination)
            observed = submitted.copy_observed()
# The independently owned historical result survives every context above.
with observed, observed.copy_result() as result:
    assert result.value(x) == 4
    assert result.objective == 15
```

For application code, construct and share a public `Library(path)` instance when selecting a library explicitly; using the same implicit default also shares an ABI instance. Python rejects cross-library entities and owners. Same-library foreign model identity reaches the C++ admission gate and returns `InvalidModel`, preserving its status rather than turning it into an opaque-handle error.

`test/optimize/lp_basis_c_api.c` is an actual C99 consumer. `python/tests/test_lp_basis.py` covers accepted and repaired submission, nonoptimal requested basis versus final basis, historical child ownership, tombstones, source edits, invalid enums/counts/options, cancellation and zero-time reset, empty/zero-row models, max sense and offsets, missing backend, and unavailable export. Existing C++ O2 tests exercise the separately compiled post-real-submission failure seam; production contains no injected hook. These bindings add no claim of checkpointing, basis transfer between revisions, rays, sensitivity ranges, or exact proof.

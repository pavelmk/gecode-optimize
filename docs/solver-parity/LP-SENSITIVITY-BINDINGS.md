# Numerical LP sensitivity from C and Python

The additive version-1 bindings expose
[`analyze_lp_sensitivity`](../../gecode/optimize/lp_sensitivity.hpp) on an owning
O1 observed result. They retain original IDs, selected basis, check diagnostics,
and per-request availability. They perform no optimization solve and never
turn an analysis into an ordinary solver Result. See the
[C++ sensitivity scope](LP-SENSITIVITY.md) for the algorithm and numerical limits.

```python
from gecode_optimize import (
    Model, LpSensitivityOptions, LpObjectiveParameter, LpEqualityRhsParameter,
    LpSensitivityState,
)

with Model() as model:
    x = model.add_variable()
    y = model.add_variable()
    balance = model.add_row([(x, 1), (y, 1)], lower=3, upper=3)
    model.set_objective([(x, 2), (y, 1)], offset=7)
    with model.solve_lp_observed() as observed:
        with observed.analyze_sensitivity(LpSensitivityOptions(parameters=(
            LpObjectiveParameter(x), LpObjectiveParameter(y),
            LpEqualityRhsParameter(balance),
        ))) as analysis:
            for entry in analysis.entries or ():
                if entry.group.state is LpSensitivityState.AVAILABLE:
                    print(entry.parameter, entry.interval.lower,
                          entry.interval.upper)
```

For the selected y basis, the example's objective-x coefficient range is
`[1,+infinity]`, objective-y is `[-infinity,2]`, and common equality RHS is
`[0,+infinity]`. These are absolute parameter values, varied **one at a time**
for this selected basis/status assignment. They are not simultaneous-change
ranges or ranges over all optimal bases. Objective slopes and limiter IDs use
original coordinates and original objective sense; the objective offset is
absent from the slope.

## Owning results and truthful states

`LpSensitivityResult.info` separates Complete, Partial, Interrupted and Rejected
analysis completion from each entry's group state/reason. A Partial result may
contain accepted intervals and rejected requests. Every accepted interval is
Numerical. No exact/certified option is offered. Original source termination
and original O1 check results remain unchanged.

- `entry(index)`, `entries`, `objective(variable)`, and `equality_rhs(row)` return
  copied immutable entries. A valid historical entity that was not requested
  returns `None` from the two ID lookups. Foreign or deleted IDs raise an error.
- `LpRangeEnd` distinguishes a finite value from negative or positive infinity.
  Its value is present exactly for a finite endpoint. An unavailable interval
  is `None`; a finite singleton remains a present interval with equal endpoints.
- An interval includes its anchor, optional original-objective slope, optional
  original limiting entities/sides, and independent interval-check diagnostics.
  Limiting conditions need not have a unique representative under ties.
- `reference_checks` retains copied primal/KKT/system diagnostics. Missing
  residuals remain `None`. Default false flags do not prove a check ran; default
  zero maxima do not establish acceptance. Consult the entry state and interval
  checks for accepted sensitivity evidence.
- `factor_order` contains typed original Variable/Row IDs in the validated
  factor order. It need not be slot order. `active_slots(Variable)` and
  `active_slots(Row)` include historical tombstones.
- `copy_source_observed()` returns an independent O1 owner even after rejection
  without a sensitivity artifact. Its `copy_result()` is unchanged source-solve
  history. `copy_basis()` returns an independent selected Basis owner when
  available; it does not establish factorization or interval success.

Copied dataclasses, source children and basis children survive closing the
analysis, source, model or session. A selected basis still obeys the existing
O2 source/revision compatibility checks. The analysis does not consult a live
model after capture. Accessors do no solver, factorization or analysis work.

The initial supported source is an original continuous linear LP with timely
Optimal O1 primal/dual checks and complete basis, analyzed through HiGHS/Auto.
Native, MIP/semis, active indicators/globals, quadratic input, elided constant
rows, unavailable basis, arbitrary replacement basis and inequality/range-side
perturbations remain explicit rejections. To use an O2 result, first obtain its
owning observed child. There is no implicit source solve or fallback.

## Time, cancellation and resource quotas

`LpSensitivityOptions` contains purpose-built backend/time/cancellation,
`LpSensitivityTolerances`, `LpSensitivityLimits`, and an explicit nonempty
parameter tuple/list. It accepts no ignored SolveOptions fields. All eight C++
quotas are exposed. Limits are logical guardrails, not exact RSS/instruction
bounds; time limits are cooperative across non-preemptive backend work.

One enclosing time allowance includes Python/C request preparation, C++ work,
and input cleanup. Each layer deducts only its own preparation time. A whole
operation limit clears every requested interval, even if completed earlier;
source/basis/reference history remains available as diagnostics. The C and
Python final cleanup checks apply to every index/bulk/ID interval view and its
message, so a late result cannot retain stale accepted ranges.

`work.preparation_visits` counts C marshalling visits separately. One visit is
charged per copied request and deducted once from runtime `max_work`.
`coordinator_visits` retains the C++ count. Oversized request/work admission
rejects before allocating/copying its array. Python uses a bounded sentinel
only for this guaranteed C count-rejection path; it does not partially marshal
or analyze an oversized request list.

`basis_solves` and `max_basis_solves` use **attempted private factor-system
calls**. An allocation/argument failure may precede the underlying HiGHS
FTRAN/BTRAN accessor. Factor setup has its separate attempted flag. These
counts are not optimization runs or iterations.

`Cancellation.copy()` and C `cancellation_copy` produce independent owners of
the same cancellation state. Closing one owner leaves the others usable;
cancellation through any owner reaches all of them. `cancelled` /
`cancellation_is_cancelled` reads the state. O4 Python retains a private owner
through the call and final cleanup check, so explicitly closing the caller's
token after admission cannot discard a returned analysis. Invalid options keep
their original rejection precedence even with a stopped token or negative time.

## C ABI details and verification

The new records/symbols are in [`c_api.h`](../../gecode/optimize/c_api.h), under
`sensitivity_*` and `analyze_lp_sensitivity`. Existing ABI-1 record layouts are
unchanged. The input is an observed-result token of the correct registry kind;
ordinary Result, Model, Session, evidence, and quadratic tokens are rejected.

All new outer/nested/request record sizes must match exactly and reserved input
fields must be zero. Numeric optional values have explicit presence. Outputs
initialize sizes and reserved fields; counted text includes NUL. NULL with zero
capacity queries a bulk/text size; a short buffer writes no elements. Default
options leave the request list empty, requiring an explicit list. Invalid ABI
shape returns the usual error and a zero output token. Safe semantic admission
returns structured analysis rejection. `NO_SENSITIVITY` distinguishes a missing
artifact; source copy and outer info/work/message remain usable.

The independent binding panel covers analytic min/max endpoints and offsets,
logical-basis singletons, real numerical Partial results, typed IDs/tombstones,
source/basis ownership, malformed records, counted buffers, quota accounting,
invalid-option precedence and final cleanup. The private C++ cleanup fixture
compiles its own C API object with
`GECODE_OPTIMIZE_TEST_SENSITIVITY_BINDING` and `GECODE_OPT_C_API_EXPORTS`, then
links **only the C++ facade**; it must not also link the ordinary C wrapper.
The hook is absent from production. Python uses deterministic post-call
cancellation/clock hooks to check its separate cleanup and token-close boundary.
All standalone C/cleanup fixtures undefine NDEBUG to keep assertions active in
Release. Build results and exact frozen dependency hashes are recorded with the
binding evidence separately; this panel makes no performance claim.

The final isolated binding panel passed on macOS arm64: C99 against normal
HiGHS/native, backend-off core, and fully instrumented standalone HiGHS;
the private cleanup fixture against normal and instrumented HiGHS; and all
83 Python tests in each of those three variants. Backend-off cases verify
explicit rejection and ownership rather than executing supported intervals.
The instrumented Python run used the Framework Python 3.14 executable with
Clang's ASan runtime preloaded, `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`
and `UBSAN_OPTIONS=halt_on_error=1`. It completed all 83 tests in 2.389 seconds
without a sanitizer finding. Leak detection was disabled, and this run does
not instrument the Python interpreter itself.

The saved evidence directory is
`implementation/agents/results/build/lp-sensitivity-bindings` in this workspace.
It retains per-command JSON, compile/link/run logs and
`completion-artifacts.json` with SHA-256 hashes of the final source, frozen
facade inputs and instrumented outputs. Its instrumented C wrapper hash is
`30f0e3ddfa1c4f57d51a8b18fe5f12e22303077a16fb908219bc42839661d01f`.
These are isolated binding checks; the combined branch regression and
performance comparison are separate integration gates.

# O4: owning C and Python sensitivity bindings

Design only, 2026-09-05. This proposal targets the frozen
[`lp_sensitivity.hpp`](../../gecode/optimize/lp_sensitivity.hpp) contract at
`ee8964ea9132995fb0c9aa304817b4fc2c162687`, integrated at `db2076651`.
The [algorithm and source research](LP-SENSITIVITY-DESIGN.md) define the
mathematical scope. This document proposes additive bindings; it claims no
binding implementation, execution, or performance result.

## Operation and scope

Expose one explicit operation on an owning **O1 observed result**:

```c
int32_t gecode_opt_v1_analyze_lp_sensitivity(
    gecode_opt_handle observed,
    const gecode_opt_sensitivity_options_v1* options,
    gecode_opt_handle* analysis);
```

```python
with observed.analyze_sensitivity(LpSensitivityOptions(parameters=(
    LpObjectiveParameter(x), LpEqualityRhsParameter(balance),
))) as analysis:
    entry = analysis.objective(x)
    if entry is not None and entry.group.state is LpSensitivityState.AVAILABLE:
        interval = entry.interval
```

The first scope remains one original objective coefficient or the common RHS
of an equality, varied alone while retaining the selected basis/status
assignment. Values, slopes and limiting entities are in original coordinates
and objective sense. Every accepted interval is qualified **Numerical**.
The analysis performs private factorization and linear-system work, with zero
optimization runs; property access performs neither operation.

There is no Model or Session overload, automatic observation solve, replacement
basis, arbitrary supplied basis, ordinary Result input, or conversion from a
quadratic result. O2 callers explicitly obtain its owning observed child first.
Native, MIP/semis, active indicators/globals, non-optimal source, unavailable
duals/basis, active elided constant rows and unsupported parameter kinds retain
the C++ rejection reasons. Unvaried infinite sides remain supported as allowed
by C++. This layer introduces no feature-dropping fallback.

## Registry ownership and immutable history

Add a distinct `SensitivityResult` registry kind. Its box owns:

1. A shared reference to the exact input O1 registry object, captured before
   analysis. It survives even when C++ cannot create a sensitivity artifact.
2. The returned `LpSensitivityResult`, which owns any immutable sensitivity
   artifact and its selected basis, source result, checks and intervals.
3. An optional final binding-cleanup stop override, described below.

No raw solver, model, session, factorization buffer or borrowed child pointer
crosses the C boundary. Registry locks cover token lookup/publication only;
they are never held during analysis. Wrong-kind and destroyed tokens fail
before use. In-flight calls retain shared ownership if another caller closes
the input token. Closing the analysis releases only its ownership.

Two explicit child-copy operations are useful:

| Operation | Meaning and lifetime |
|---|---|
| `copy_source_observed` | Creates an independent O1 token from the exact saved input. The copied SolveResult and shared O1 observations remain unchanged even if O4 rejects or stops. It survives source/analysis/model/session close. |
| `copy_basis` | Creates an independent existing Basis token from the selected immutable `LpBasis`, when present. Otherwise return the existing `NO_BASIS` API error. Do not reconstruct a basis from statuses or transplant it to another revision. |

Do not offer a new O4 `copy_result`, `has_solution`, or solver-termination field.
The copied O1 child's existing `copy_result()` exposes original solve history,
not an optimum established by sensitivity analysis. A basis child is historical
selected input; its presence does not establish that factorization or any
requested interval succeeded.

The runtime owner confirmed that `LpSensitivity::original()` preserves the exact
input SolveResult and the same immutable O1 observations; analysis modifies
only separate diagnostics/ranges. Retaining the source registry object permits
that same guarantee even on an early O4 rejection without an artifact.

## Additive C ABI records

Keep ABI version 1 and every existing record layout and symbol unchanged. Add
explicit enum mappings for completion, reason, group state, parameter kind,
range-end kind and limiter side. Do not depend on C++ enum ordinals. All new
records use an exact `struct_size`, zero reserved fields, fixed-width scalars,
counted arrays, and copied text. No C++ `bool`, `size_t`, union layout or pointer
to retained output storage is public ABI.

The following is the proposed record inventory; final field ordering belongs
to the reviewed implementation, without changing the listed meanings.

| Record | Required content |
|---|---|
| `gecode_opt_sensitivity_request_v1` | Tagged `ObjectiveCoefficient` or `EqualityRhs`; original `gecode_opt_id` of the required Variable or Row kind. |
| `gecode_opt_sensitivity_checks_options_v1` | Original-unit primal tolerance; the four O1 KKT tolerances; absolute and relative original-system residual tolerances. |
| `gecode_opt_sensitivity_limits_v1` | All eight C++ limits: rows, columns, nonzeros, requests, basis solves, factor entries, retained slots and work. |
| `gecode_opt_sensitivity_options_v1` | Backend, time limit, cancellation token; nested checks/limits; request pointer and count. |
| `gecode_opt_sensitivity_info_v1` | Original owner/revision, completion/reason, present stop reason, artifact/basis presence, entry/factor-order/row-slot/column-slot counts, elapsed time, numerical qualification. |
| `gecode_opt_sensitivity_work_v1` | `factor_setup_attempted`, `basis_solves`, `coordinator_visits`, `retained_slots` copied from C++; separate binding `preparation_visits`. None is interpreted as iterations or bytes. |
| `gecode_opt_sensitivity_group_v1` | State and reason, with message through counted text access. |
| `gecode_opt_sensitivity_end_v1` | Finite/NegativeInfinity/PositiveInfinity tag and an explicitly present finite value exactly for Finite. |
| `gecode_opt_sensitivity_limiter_v1` | Original typed entity, Lower/Upper/Fixed/Free side, and `dual_condition`. Presence is separate from its zero-filled inactive storage. |
| `gecode_opt_sensitivity_interval_checks_v1` | Accepted flag, inequality count, optional maximum endpoint violation, lower/upper direction-checked flags, message through counted text. |
| `gecode_opt_sensitivity_entry_v1` | Request, group, explicit interval presence; anchor, endpoints, optional objective slope, optional limiters, and interval checks when present. |
| `gecode_opt_sensitivity_reference_checks_v1` | Copied primal ValidationReport, O1-shaped KKT diagnostics, basis-point-match flag, optional point/system/scaled-system residuals. Messages remain individually addressable. |

The limits record has eight quota fields, exactly matching the frozen C++
header. Every input nesting level, including every request element, is validated
before reading its remaining fields. A defaults function initializes exact
sizes/reserved fields for the options and nested records. Defaults contain an
empty request list, so the caller must supply an explicit nonempty list; NULL
options must not silently mean “all coefficients.”

Use the existing optional-number convention for genuinely optional finite
metrics. A finite endpoint value must be finite; an infinite endpoint has no
numeric value. The infinite direction, absent endpoint number, missing interval,
zero coefficient, and singleton interval are five different states. Never use
`1e20`, zero, or a missing value as an infinity substitute.

Scalar ABI/count/enum validation errors return the ordinary API error with the
output handle zero. Empty/duplicate requests, incompatible source, foreign or
deleted source IDs, and unsupported perturbations are passed to the C++ admission
path after safe marshalling, retaining its structured rejection and no-factor
preflight. A request whose C ID has the wrong entity kind is an ABI argument
error. Do not add a second semantic admission policy in the wrapper.

Before allocation, check pointer/count relationships, uint64-to-size_t and
ptrdiff conversions, container maxima and multiplication overflow. Request
copying must honor `max_requests` and `max_work` rather than allocate an
arbitrarily oversized input only for the runtime to reject it. A bounded
marshaller may return an owning ResourceLimit rejection with saved source
identity and zero backend work; it must not fabricate an attempted factorization.
Document exactly which copied request visits are charged and debit them once
from the runtime's remaining coordinator-work quota.

Every C entry point is exception-safe. Allocate and fill an owning box before
publishing its token. Catch conversion, allocation and runtime exceptions using
the existing boundary policy. Output structures are initialized before filling;
all reserved/output absence storage stays zero. Bulk/text calls first check the
entire output contract: NULL with capacity zero queries the count; a short
buffer returns `BUFFER_TOO_SMALL` and writes no elements. UTF-8 text counts
include the terminating NUL.

## Passive accessors and original identity

Use the `gecode_opt_v1_sensitivity_` prefix for:

```text
destroy, info, work, checks_options, reference_checks,
copy_source_observed, copy_basis,
entry(index), entries, objective(original_variable), equality_rhs(original_row),
factor_order, active_slots(entity_kind), text(field,index)
```

`text` addresses outer message, backend version, each entry group message,
present interval-check message, and the distinct reference primal/KKT messages.
No output refers to temporary text storage. Missing artifacts return a new
`NO_SENSITIVITY` API error for artifact-only getters; info/work/outer message and
source copy remain available. Assign its numeric error code after O3's additive
codes are integrated, without renumbering existing errors.

Entries retain request order. An original-ID lookup must distinguish:

| Input/status | Result |
|---|---|
| Correct historical owner, live Variable/Row, requested parameter | Copy the entry and its effective group/optional interval. |
| Correct historical owner and live entity, that parameter not requested | Explicit `requested=false`; Python returns `None`. This is not a failed analysis or an empty interval. |
| Foreign owner, wrong kind, deleted/out-of-range historical slot | Error; no lookup by name, current live model, or unchecked vector offset. |

`factor_order` returns an ordered array of existing typed original IDs. It is
the checked backend factor ordering, not original slot order. Logical entities
retain their original Row IDs. The binding never encodes negative backend
indices, swaps row sides, or negates maximization sensitivities a second time.
The runtime publishes this vector only after the full count, uniqueness,
owner/mask and basic-status comparison succeeds. It may still be retained as
history when a later request/check/limit fails; it is not interval availability.

Original active masks include tombstones. Bulk mask access includes inactive
slots; individual sensitivity lookup rejects them. A source edit/destruction
cannot change mappings, copied entries, selected basis or factor order. Limiter
IDs follow the same original mapping; tied limiting conditions need not select
a unique representative. No extra basis algebra belongs in the binding.

Reference checks are **copied diagnostics**, separate from source O1 checks and
from interval availability. Preserve every optional residual's presence.
`ValidationReport.model_valid` reports a structurally valid source;
`valid` reports accepted primal validation. It is not a separate O4 completion
flag. A default false `basis_point_matches` or KKT `accepted` does not establish
that that check ran. Do not invent a KKT-examined bit absent from the C++ contract
or turn default zero maxima into an available accepted check. Expose the raw
flags, optional metrics and messages with these meanings; consumers establish
interval acceptance from the effective entry state and interval checks.

## Shared time, limits and final cleanup

Options are purpose-built analysis options, not SolveOptions. There are no
ignored node limits, threads, primal starts, search gaps, optimization methods
or Exact/Certified flags. Requesting explicit Native remains Unsupported.
The time limit is cooperative; factorization/triangular solves may finish after
it and are checked before publication. No binding silently retries.

Start one monotonic enclosing clock before retaining/copying source inputs and
marshalling requests. Retain the same cancellation state. Python takes an independent registry owner
through additive `cancellation_copy` before the call, so explicit close of the
caller's owner cannot break its final `cancellation_is_cancelled` check. The
private owner is released before publication. Debit elapsed
marshalling time from the C++ time allowance once, with checked nonnegative
remaining time. Python keeps all marshalled arrays/token owners alive through
the C call. Its request-array preparation also consumes the user's specified
time: begin the Python clock before building the native request buffer and pass
the remainder to C. The C result reports its enclosing elapsed time; Python
retains its preparation duration and includes it once in its owning result's
elapsed-time view. Preserve that accounting after close/copy rather than reading
a clock during passive access. Avoid subtracting the same elapsed portion twice.

The C++ whole-limit policy clears all intervals even if some were computed
earlier. A binding cleanup checkpoint is needed after releasing its temporary
request/copy buffers and before publishing the result. On a late cancellation
or time limit, preserve source/check/basis/order history but override effective
completion to Interrupted, reason to Stopped, and stop reason to the actual
limit. At that point **every requested entry** becomes Unavailable/Stopped and
has no interval. The following access paths must all apply the override:

- index, bulk and original-ID entry getters;
- interval/check message access and any Python convenience interval property;
- per-entry groups, outer completion and outer message.

Unrequested live-ID lookup stays explicitly unrequested. There is no raw
pre-override interval getter. Historical source, selected basis and completed
reference diagnostics may remain readable, without implying accepted O4
evidence. Exceptions during publication must not leak a token or partially
published accepted entry. A private compile-only cleanup checkpoint fixture,
following O3, can test this without timing sleeps or production callbacks.

`basis_solves` counts attempted private factor-system calls, not optimization
calls or mathematical requests. A failure can precede the underlying HiGHS
FTRAN/BTRAN accessor; successful private calls reach one such accessor each. `factor_setup_attempted` is separate. Work/retention
and factor-entry quotas are logical guardrails, not exact RSS or instruction
bounds. Binding marshalling counters must be accounted explicitly without
renaming them backend work; the implementation should preserve the C++ counted
work and separately report preparation visits if it adds those visits to totals.

## Python surface and lifetime

Use frozen copied records for parameter descriptors, options/limits/tolerances,
range ends, limiters, interval/reference diagnostics, entries, work and info.
Entities retain the existing library-associated Variable/Row types. The owning
`LpSensitivityResult` supports close/context management and passive properties;
copied tuples/dataclasses survive close. `copy_source_observed()` and
`copy_basis()` return independent context-managed owners. Closing a parent must
never close a previously returned child.

`LpRangeEnd(kind, value)` retains the finite/infinite tag. Do not flatten an
unavailable interval and an unbounded interval into the same `None` pair.
Objective slopes and endpoints are copied directly in original sense; offsets
are not added to slopes. Source optimum, analysis Complete, available basis,
available interval and accepted reference KKT remain distinct fields.

Validate Python entity type and library association before marshalling;
historical owner/revision/tombstone checks remain in the C++ contract. Require
an explicit parameter sequence; reject unknown Python options rather than
dropping them. Never construct an ordinary Result from O4 fields.

## Implementation and conformance gates after approval

Proposed owned files: additive `c_api.h/.cpp`, Python binding/init, new
`test/optimize/lp_sensitivity_c.c`, new Python sensitivity tests, and a concise
binding reference. Add a separate private cleanup fixture if the runtime panel
cannot exercise binding-only cleanup. The integrator owns CMake, installation,
consumer registration and the shared performance gate. Freeze the runtime
source before final evidence; do not link an O4-absent facade archive.

1. **ABI admission and output safety.** Outer/nested/request sizes and reserved
   fields, unknown enums, NULL/count mismatches, count overflow and quota
   preflight, required-count queries, short buffers, optional flags, UTF-8 text,
   and zero output handle after API failure. Keep assertions enabled in Release
   by undefining NDEBUG in each standalone C fixture.
2. **Analytic signs/endpoints.** For `min 2*x+y`, `x+y=3`, `x,y>=0`, select the
   y basis: objective-x `[1,+infinity]`, objective-y `[-infinity,2]`, equality
   RHS `[0,+infinity]`. Check anchors/slopes and mirrored maximization/offset
   cases against independent arithmetic. Cover finite, singleton and infinite
   ends, zero objective coefficients and a logical-basic equality singleton.
3. **Provenance and factor order.** Mixed structural/logical basis, source
   tombstones, reordered factors, foreign/deleted/unrequested IDs, source edits,
   and source/session/analysis close. Copied O1 result/observations must match
   the input even after rejected O4. Copied basis retains its source and its
   usual compatibility checks.
4. **Truthful availability.** Not-optimal/no-basis/failed source checks,
   unsupported Native/MIP/global/parameter, missing backend and zero-row or
   elided-row source. Distinguish no artifact, no selected basis, unavailable
   request, numerical rejection, singleton and accepted interval. Expose absent
   KKT/point/system metrics as absent, never accepted zeros.
5. **Partial and stopped analyses.** A mixed per-request result copies every
   reason without promoting Partial to Complete. Whole time/cancel/resource
   limits erase all intervals. A deterministic post-runtime binding cancellation
   must revoke index/bulk/lookup intervals and messages, retain raw diagnostic
   history, and leave independently copied source/basis children usable.
6. **No hidden solving.** Getter and copy operations preserve work counters and
   do no backend work. Report factor-setup attempts and attempted factor-system calls from
   the runtime. Do not use a source Optimal status to synthesize analysis success
   or infer zero optimization work from a vendor iteration count.
7. **Build matrix.** C99 and Python on core/backend-off, normal pinned HiGHS,
   and fully instrumented matching HiGHS plus facade, then installed consumers.
   Re-run existing binding conformance after additive symbols land. No timing
   or throughput claim belongs to this correctness panel.

The runtime owner has confirmed unchanged source history, fully validated
factor-order publication and whole-limit interval clearing. The integrator
approved this contract and the separate preparation-work debit; implementation
evidence will be recorded separately from this design after runtime alignment.

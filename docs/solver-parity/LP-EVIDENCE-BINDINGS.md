# Numerical LP evidence in C and Python

The additive ABI 1 and Python interface expose the explicit additional-work
[O3 workflow](LP-EVIDENCE.md). It searches private auxiliary models for a feasible
base point and improving recession direction, or an original-side Farkas
contradiction. It never changes a source model, session or historical solve result.
`Complete` describes completion of the analysis. `Available` denotes independently
checked **numerical evidence**, not an exact certificate or proof of an infinite
feasible trajectory.

```python
from gecode_optimize import (Model, LpEvidenceOptions, LpEvidenceRequest,
                             LpEvidenceState)

saved_stage = None
with Model() as model:
    x = model.add_variable()  # continuous, lower 0, upper +infinity
    model.set_objective([(x, -1)], offset=7)
    with model.analyze_lp_evidence(
            LpEvidenceOptions(request=LpEvidenceRequest.BOTH)) as analysis:
        print(analysis.info.completion, analysis.info.stop_reason)
        group = analysis.primal_ray
        if group is not None and group.state == LpEvidenceState.AVAILABLE:
            print(analysis.base_value(x), analysis.direction_value(x))
        diagnostics = analysis.diagnostics  # copied frozen records, or None
        if analysis.info.has_evidence:
            saved_stage = analysis.copy_stage(1)  # owning recession-stage child
# The typed child survives model and analysis destruction.
if saved_stage is not None:
    with saved_stage:
        stage = saved_stage.info
        print(stage.private_model_id, stage.phase, stage.candidate_examined)
        print(stage.raw_result)  # reported auxiliary fields, not a source Result
```

Use `LpEvidenceRequest.FARKAS` for only the contradiction model, `PRIMAL_RAY`
for feasible-base and recession models, `AUTOMATIC` for at most two auxiliary
solve calls, or `BOTH` for at most three. All requested private models are prepared
before any solve. Prepared but unused stages have `attempted=False`, no raw
result and no examined candidate. An automatic analysis of an infeasible source
can skip its prepared recession stage and solve its Farkas stage instead.

## Two independent evidence groups

`analysis.primal_ray` and `analysis.farkas` are independent copied group records
with state, typed reason and message. Either is `None` if admission produced no
artifact. A group can be NotRequested, Available, Unavailable or Rejected; these
are different from the outer analysis completion and stop reason. The original
source ID/revision, stage count, attempted call count and work count remain in
`analysis.info`, including on interrupted analysis. The outer message is available
on every owning result, including rejected admission.

`analysis.diagnostics` contains the captured tolerances, primal/Farkas diagnostic
summaries, and complete original column/row slot arrays. The arrays preserve
source handles and inactive tombstones. Absent values are `None`; a computed
zero is `0.0`. A base check is `None` when no original base check was published.
A valid base point alone does not make a primal direction Available. A zero
Farkas multiplier has no selected side or bound and contributes a present zero.
Nonzero signed multipliers select original finite lower sides when positive and
upper sides when negative. Contributions and their positive contradiction margin
are computed from those original sides, not auxiliary bound multipliers.

Raw diagnostic values can remain populated after rejection or a whole-operation
limit. Read the group state before treating them as accepted evidence.
`analysis.slot(original_handle)` deliberately exposes those diagnostics.
`direction_value`, `base_value` and `multiplier` are stricter typed getters:
the former two require an effectively Available primal-ray group, and the latter
requires an effectively Available Farkas group. All validate the captured source
owner, slot and active status. Thus `base_value` is deliberately narrower than
the C++ base-only accessor; a base-only point remains inspectable in diagnostics.
A final C-binding cleanup timeout/cancellation revokes every accepted getter as
well as effective group availability. Diagnostic records can still be copied.

## Private stages and ownership

`analysis.copy_stage(index)` returns an independently owning `LpEvidenceStage`
child token. It retains shared immutable evidence and its checked stage index;
closing either the model or parent analysis does not close this child. A child
contains no ordinary Result conversion or `has_solution` convenience property.
Closing the child releases only its own ownership.

Its copied `info` records the phase, private model owner/revision, dimensions,
nonzeros, attempted flag, examined-candidate flag and optional independent
auxiliary check. `columns` maps each private auxiliary Variable to an original
source Variable or Row and, when applicable, its original finite side. The
private variable ID is never rewritten to the original source ID. Original
source IDs on mappings remain stable after model edits and destruction.

`info.raw_result` is explicitly reported backend diagnostic data. Its
`termination_code`, `guarantee_code`, `reported_solution_validated`, scalars and
bounds are **not assertions by the binding** that a rejected stage result is
valid. Integer codes are retained even if an injected backend supplied an unknown
value. The same is true of `raw_values`: each slot separately reports value
presence and mask presence, and preserves malformed values/mask codes for
diagnosis. A value-vector/mask length mismatch is not silently truncated or
reinterpreted as a valid original assignment. `raw_backend`, version and message
are copied strings. No stage getter reruns a solve or checker.

This distinction matters because O3 keeps raw auxiliary data when its independent
checker rejects an owner, objective, mask, status or bound. Turning such data into
an ordinary Result would falsely transfer that Result's validation semantics.
The typed stage preserves provenance without doing that. An auxiliary objective,
bound or gap belongs only to its private model. It is never a source-model
objective, optimization bound or source-model Result. C++ auxiliary snapshots
remain C++-only in this first binding; no private Model import is offered.

## Budgets and explicit scope

`LpEvidenceOptions` carries an embedded ordinary `Options`, the request,
finite nonnegative check tolerances and resource caps. Python marshalling time
is deducted from a copied time allowance. C snapshot/copy preparation is deducted
before one call to the C++ analyzer; its auxiliary stages receive only the
remaining time and shared cancellation token. A final binding check runs after
temporary input cleanup. If it expires, the owning wrapper overrides effective
availability to Unavailable/Stopped while preserving immutable diagnostic data.
It never exposes the artifact's earlier availability as current acceptance.

Time is cooperative around indivisible copies, factorization and destruction.
C `elapsed_seconds` includes the C call's input preparation, analysis and cleanup;
Python-only marshalling is charged against the allowance but is not added to that
C timing field. Node zero stops immediately. Positive node quotas are passed to
these LP solves, which consume no branch-and-bound nodes. The
`max_auxiliary_solves` limit and `attempted_calls` count **public auxiliary solve
invocations**, including local constant/empty decisions; they are not raw vendor
run telemetry. The separate coordinator work and logical retained-slot caps
retain the C++ definitions. No performance improvement is inferred from counts.

Only continuous linear sources with Numerical policy and Auto/HiGHS are admitted.
Fixed integers, semis, active globals/indicators, Native, Exact/Certified and
caller starts are explicitly Unsupported. Inactive source metadata remains
owned and structurally checked. No source is silently relaxed or stripped.
Unavailable backend support remains an explicit status. The API does not accept
QuadraticModel handles and does not modify a caller Session. There is no implicit
analysis while reading existing O1 observations or ordinary Results.

## ABI records and tests

Use `gecode_opt_v1_evidence_options_default`, then
`gecode_opt_v1_analyze_lp_evidence`. The options and embedded SolveOptions require
the exact version-1 sizes; all reserved fields must be zero. Request enums and
numeric limits are checked. Every output record and typed array has an explicit
size argument. Optional values have a presence flag; absent outputs and reserved
fields are zero-initialized. Text/arrays use NULL plus capacity 0 to query the
required size; text counts include NUL. Short arrays remain unchanged and return
BUFFER_TOO_SMALL. Wrong-kind/destroyed opaque tokens, foreign/deleted source IDs,
and invalid stage indices fail explicitly. NO_EVIDENCE is the additive error
code 10 for missing artifacts or unavailable accepted-evidence getters.

Normal library builds contain no injected callbacks. The separately compiled
`GECODE_OPTIMIZE_TEST_EVIDENCE_BINDING` fixture cancels at the C cleanup boundary
after real accepted ray and Farkas analyses. It checks effective group revocation,
all typed accepted getters, preservation of NotRequested, and raw child history
after parent/model/token destruction. It links its own C API object against only
the C++ facade, avoiding duplicate registries or wrapper exports.

The C99 tests retain assertions under Release `NDEBUG`. Python and C panels cover
analytic ray/Farkas signs, objective sense/offset, free/fixed/ranged and zero-row
cases, both original coordinate systems, tombstones, copied frozen records,
private child lifetime, absent checks/values, requested/unused phases, scope,
limits/cancellation and all version/buffer/type boundaries. The C++ O3 coordinator
suite separately supplies malformed backend evidence and verifies that it is
rejected before group acceptance.

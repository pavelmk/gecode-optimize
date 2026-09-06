# Serial scenario batches in C and Python

The additive ABI 1 scenario API exposes the owning C++ workflow in
[SCENARIOS.md](SCENARIOS.md). It solves independent sparse variations of one
ordinary linear source model. Automatic reuse uses a private numerical session;
Cold and Native use independent calls. These are serial batch solves, without
shared search trees or commercial multi-scenario performance claims.

```python
from gecode_optimize import (Model, VariableType, ScenarioDefinition,
    ScenarioVariableBounds, ScenarioRowBounds, ScenarioOptions)

with Model() as model:
    x = model.add_variable(VariableType.INTEGER, 0, 10)
    demand = model.add_row([(x, 1)], lower=3)
    model.set_objective([(x, 2)], offset=7)
    cases = [ScenarioDefinition("base"),
             ScenarioDefinition("higher demand", row_bounds=[
                 ScenarioRowBounds(demand, lower=5)]),
             ScenarioDefinition("higher unit cost", [(x, 4)],
                 variable_bounds=[ScenarioVariableBounds(x, upper=8)])]
    with model.solve_scenarios(cases, ScenarioOptions()) as batch:
        for index in range(batch.info.scenario_count):
            case = batch.scenario(index)
            outcome = batch.outcome(case)
            # Later cases can be NotStarted after an earlier incomplete solve.
            if outcome.result is not None and outcome.result.has_solution:
                print(batch.definition(case).name, batch.value(case, x))
        first = batch.scenario(0)
        mapped_x = batch.map(x)
        saved = batch.copy_result(first)  # independent owning ordinary Result
# saved uses the private owner/revision, so use mapped_x, not original x.
with saved:
    if saved.has_solution:
        print(saved.value(mapped_x))
```

Each coefficient, objective offset and bound side is an **absolute override**.
Missing fields inherit the historical base; zero coefficients remove terms.
Names do not identify scenarios. A `ScenarioId` contains its private batch owner
and input index. All calls validate the owner and index. Maps validate the
historical original model owner and live variable/row slot, including tombstones.
Later edits to the caller model do not make a historical mapping stale. An ID
from another batch or a deleted slot in the captured base is rejected.

`ScenarioDefinition`, bound records, IDs, outcome/check metadata and session
counters are copied frozen Python records. Input term/bound sequences become
tuples when a definition is created. A definition returned by the batch retains
original source IDs. Model destruction, batch close and later source edits do
not invalidate already copied records. `copy_result(case)` returns a separately
owned ordinary Result; it remains alive when the batch closes. It keeps the
private model owner and case revision `index+1`; original source IDs cannot be
used directly with its ordinary `value` accessor. Retain `batch.map(original)`
for that purpose. No borrowed child handle or implicit linear-model conversion
is exposed. The C++ `materialize` operation remains C++-only in this first binding.
There is no public Session-based scenario call: session reuse is batch-private.

## Evidence and incomplete outcomes

The batch info contains the original model ID/revision, optional admitted batch
ID, completion, optional stop reason and offending input index, attempted/resolved
counts, work counter, elapsed time and actual session reuse counters. A rejected
batch has no admitted definitions or per-case outcomes. The owning batch message
is available even after rejection. Successful admission creates an outcome for
each case; an unattempted outcome has no Result and no check. The passive
`check(case)` accessor returns `None` if no check was published. An existing check
can have `candidate_examined=False`; its Python `validation` is then `None`, not
a default record claiming validity. Backend status, independent identity checks
and candidate validation are separate facts. Infeasible/unbounded numerical
statuses are not new exact certificates.

C records use explicit presence flags for all optional outcomes, checks, offsets,
stop reasons and offending indices. Absent output fields and reserved fields are
zero-initialized. Validation data is meaningful only when `candidate_examined`;
otherwise its numeric fields and optional objective are absent/zero. Finite or
infinite optional bounds on a copied Result retain the ordinary Result presence
contract; missing bounds are never represented as a present zero.

Numerical is the admitted guarantee on all routes. Exact requires explicit Native.
Certified and Auto/HiGHS Exact are Unsupported even for an empty batch. An empty
batch with an admitted guarantee and available budget completes without a backend call. Active semis,
all indicator/global metadata (including inactive history), common starts and
quadratic models are outside this workflow's scope. A distinct QuadraticModel
cannot be passed to this ABI operation. Unsupported data is never silently
removed, and the caller model is never modified.

## One allowance and bounded admission

The Python wrapper deducts its input-marshalling time from a copied SolveOptions.
The C wrapper deducts its snapshot/array-copy time before calling the C++ batch
once. Each case then gets the remaining whole-batch time and the same cancellation
token. No per-case limit is reset by either binding. C input cleanup is checked
before publishing overall Complete; timely individual histories survive a final
whole-call timeout. Time/cancellation remain cooperative around indivisible
allocation/copy/backend operations. C `elapsed_seconds` measures the C call's
preparation, workflow and input cleanup; Python-only marshalling is charged to
the allowance but is not added to this C timing field.

An absent node quota uses the normal backend contract; zero stops before any solve. A positive node
limit with exactly one case is forwarded once. Positive multi-case node limits
are explicitly Unsupported until cumulative consumed-node reporting exists.
There is no invented batch node counter. Session counters indicate actual reuse
operations and do not prove performance improvement.

The v1 options include scenario, patch-entry, saved-value-slot and coordinator
work caps. The C wrapper checks definition and aggregate patch counts before
allocating its copied patch arrays. The C++ workflow owns the documented
`max_work` element-visit meter; language-boundary conversion is timed but not
reported as backend iterations or silently added to that work counter. Invalid
array shapes, version sizes, reserved fields and enum values return C API errors
with a zero output handle. Semantic invalid patches return an owning Rejected
batch with InvalidModel and the offending case index. An input storage cap can
return an owning Rejected MemoryLimit result before definitions are copied.

## C ABI contract and conformance

Use `gecode_opt_v1_scenario_options_default` to initialize the options, then
`gecode_opt_v1_solve_scenarios` with counted definition records and their exact
`sizeof(gecode_opt_scenario_definition_v1)`. Every definition and nested bound
record has an exact v1 `struct_size`, all reserved fields must be zero, and
presence fields must be exactly 0 or 1. Options also validate their embedded
ordinary SolveOptions version before reading its optional fields. Count/pointer
and representable allocation lengths are checked. Names are copied UTF-8 strings
(NULL means empty). Side values whose presence flag is zero are ignored; present
NaN or directionally invalid infinity is rejected by semantic admission.

`scenario_batch_*` accessors are passive copies; none solves or analyzes again.
Text/buffer access uses NULL and capacity 0 to query required size, followed by a
caller-owned buffer. Text counts include the trailing NUL. Short output arrays
remain unchanged and report BUFFER_TOO_SMALL plus the required count. Typed bound
arrays additionally require the exact element size. Objective arrays and returned
bound records preserve the originally requested sparse patch order and IDs.

Tests include C99 boundary/ownership/buffer checks and Python hand-computed and
exhaustively enumerated integer min/max cases on Native and HiGHS, cold/session
agreement, original identity/tombstone history, copied Result lifetime, invalid
sizes/counts/presence, rejected patches, missing backend, zero time/cancellation,
all outer caps, node scope and unavailable candidate checks. The C++ workflow's
separate deterministic coordinator tests cover interrupted/forged raw evidence;
the bindings call that same coordinator once and do not substitute a new oracle.

# Version 1 C and Python bindings

The additive optimization facade has a versioned C99 ABI and a small Python
`ctypes` package. Both build the same owning model and call the same
solver/session implementation as C++. They support continuous, integer, binary,
semicontinuous and semiinteger variables, ranged linear rows, a single linear
objective with an offset and min/max sense, edits, numerical LP/MPS I/O, solver
selection, limits, sparse primal starts, cancellation, persistent sessions, and
immutable historical results. Typed AllDifferent, Element, Table, Cumulative,
Circuit and Regular records, bounded indicators, and Boolean AND/OR helpers are
also exposed.
Ranked discrete-projection pools and explicit weighted feasibility repairs have
separate owning workflow results, including copied nested solve results.
Scenario batches, finite-box continuous quadratic objectives expressed as weighted
squares, LP observations, basis submission, ray/Farkas evidence and basis
sensitivity analysis have dedicated owning interfaces described below.
Atomic bulk variable, row and CSR construction is exposed through the same
C++ transaction boundary; see [bulk construction](BULK.md#c-and-python-bulk-construction).

This is a bounded first binding surface. There are no C/Python builders for
arbitrary quadratic expressions, multiobjective workflows, conflict refinement,
callback registration, lazy constraints or proof certificates. Those require
additional versioned entry points. The explicit native selector reaches only models in the C++ native
backend's supported subset. Binding availability does not imply that either
solver backend was built. `capabilities` reports backend availability; unsupported
models and guarantees return a solver `UNSUPPORTED` result without changing the
requested semantics. Standalone `Model.solve(AUTO)` selects Native when the
model has active typed globals, otherwise HiGHS. A persistent session's AUTO
route remains HiGHS and explicitly rejects active globals. Explicit Native is
available through standalone solves and supported standalone workflows;
persistent Native session calls return `UNSUPPORTED`. A session never silently
changes its backend.

## Using Python

No Python solver implementation or extension-module ABI is involved. Python 3.9+
uses the standard library and the built `gecodeoptimize_c` shared library. For
source-tree use, put the repository's `python/` directory on
`PYTHONPATH` and set `GECODE_OPTIMIZE_LIBRARY` to an absolute path to the shared
library (`.dylib`, `.so`, or `.dll`). Alternatively pass that path or an explicit
`Library` instance to `Model`, `Session`, and `Cancellation`. Importing the Python
package does not load the library. Failure to locate/load a binary is explicit.
The [experimental macOS wheel recipe](WHEELS.md) packages a matching library
that the installed package discovers automatically. Explicit library arguments
and `GECODE_OPTIMIZE_LIBRARY` take precedence over that bundled library; this
recipe does not publish to PyPI or provide Linux/Windows distributions.

```python
from gecode_optimize import Model, Options, Session, Termination, VariableType

with Model() as model, Session() as session:
    quantity = model.add_variable(VariableType.INTEGER, upper=8, name="quantity")
    model.add_row({quantity: 2}, lower=3)
    model.set_objective({quantity: 3}, offset=-1)
    with session.solve(model, Options()) as result:
        if result.termination == Termination.OPTIMAL:
            print(result.objective, result.value(quantity))  # 5.0, 2.0
    model.set_bounds(quantity, 4, 8)
    historical = session.solve(model)

# Results own their snapshot data and survive model/session destruction.
with historical:
    print(historical.objective, historical.value(quantity))  # 11.0, 4.0
```

Use `close()` or context managers for Model, Session, Result, PoolResult,
RepairResult and Cancellation.
Sequential `close()` is idempotent; later operations raise `RuntimeError`.
Destructors provide only best-effort fallback cleanup. Variable, Row, GlobalConstraint and Indicator values are
immutable typed identities, not owners, and remain useful for historical result
lookup. Cross-model, removed, and wrong-kind identities are rejected. Imported
models have new owner/slot identities; old identities cannot index their results.
Library-instance checks prevent accidentally mixing Python objects created
through separate `Library` instances. Python integers are range checked before
conversion to fixed-width C fields, and strings containing embedded NUL are
rejected. Names and paths use UTF-8; filesystem support for those paths follows
the platform C++ I/O implementation.

An `ApiError` has a numeric `code` and copied error text. It represents malformed
arguments, bad handles, rejected model edits, or wrapper/backend exceptions.
Ordinary solver outcomes, including infeasibility, limits, missing backends and
unsupported guarantees, are represented by `Result.termination`. Always inspect
`has_solution` before reading values. Optional objective/bound/gap properties are
`None` when absent. `values` returns fresh per-slot records with separate `active`
and `present` masks; a removed slot cannot be mistaken for a zero-valued variable.
`backend`, `backend_version`, `message`, `info`, and session `statistics` are copies.

## Typed globals and logical helpers

```python
from gecode_optimize import Model, VariableType

with Model() as model:
    x = model.add_variable(VariableType.INTEGER, 0, 2)
    y = model.add_variable(VariableType.INTEGER, 0, 2)
    distinct = model.add_all_different([x, y], name="distinct")
    model.add_table([x, y], [(0, 1), (2, 0)])
    model.set_objective({x: 1, y: 2})
    with model.solve() as result:  # AUTO chooses Native for typed globals
        print(result.termination, result.objective)
    model.set_name(distinct, "different choices")
    model.remove(distinct)
```

`add_element(index, elements, result, index_base=0)` selects an array variable
using the explicit base. `add_circuit(successors, index_base=0)` requires one
cycle through the nonempty successor array. `add_cumulative(starts, durations,
heights, capacity)` has mandatory tasks with fixed integer durations/heights and
half-open intervals; a zero duration or height uses no resource. Global arrays
preserve aliases: AllDifferent([x,x]) is infeasible, and repeated Table/Element
variables retain equality of their occurrences. No alias is silently removed.
Integer constants and bases use checked int64 conversion; the shared model
contract additionally requires exact representation within +/-2^53. Native
execution has its narrower finite-domain integer limits. In Python, mismatched
tuple arity is rejected before posting. C tables take an explicit row-major flat
array, arity, tuple count and value count; checked multiplication must reproduce
the provided value count. Cumulative arrays carry separate checked counts.
A table of arity zero with no tuples is false, while one empty tuple is true.

These methods return `GlobalConstraint` identities; `remove` and `set_name`
accept them. Removing a variable referenced by an active global is rejected.
A removed global cannot be renamed or removed again. All record building and
identity validation work even when no solver backend is compiled. LP/MPS export
rejects active typed globals, and an unsupported solver route returns
`UNSUPPORTED` without dropping the records. See [GLOBALS.md](GLOBALS.md) for the
shared model and Native semantics.

`add_indicator(activator, active_value, terms, lower, upper, name="")` requires
a Binary activator and an actual Python bool for `active_value` (C accepts exactly
0 or 1). It invokes the bounded C++ formulation: required inactive activity
bounds must be finite, M is derived, and original logical metadata remains for
independent validation. The returned `Indicator` includes `inactive_gate`, which
is a Variable or None. `model.remove(indicator)` removes its generated rows and
metadata in one revision; an auxiliary gate remains as a variable and may then
be removed through `model.remove(indicator.inactive_gate)` when unused. Widening
domains that justified the indicator is rejected until its formulation is rebuilt.
Generated row identities are not exposed by this binding, and their semantics
cannot be weakened through generic row edits. Active indicators cannot be exported
to LP/MPS through the strict I/O facade. A tautological indicator still has a
logical identity even when no gate or row was required.

`add_boolean_and(result, inputs=())` and `add_boolean_or(result, inputs=())`
atomically post ordinary rows and return None. Variables must have Binary type;
AND(empty) fixes true, OR(empty) fixes false. Duplicate inputs and output/input
aliases follow the C++ helper's logical semantics. This initial binding exposes no
row list or helper-group removal for Boolean postings; their generated ordinary
rows stay in the model. Build explicit rows when individual row editing/removal
is required. C++ helpers perform validation/allocation before commit, and wrapper
output conversion adds no allocation after posting; malformed bound/type/owner,
dimension and required-output cases leave model identity/revision unchanged.

## C ownership and ABI contract

Include `gecode/optimize/c_api.h` from C99 or C++, link `gecodeoptimize_c`, and
check every API return code. The header contains only fixed-width C fields and
plain caller-owned records. All exported functions use the `gecode_opt_v1_`
prefix and `gecode_opt_v1_abi_version()` returns 1. Published enum values are
mapped explicitly to C++ enums. Options and metadata records have versioned
names and exact-size checks; initialize options using
`gecode_opt_v1_options_default(&options, sizeof options)`. A NULL options pointer
requests defaults. Size mismatches and unknown enums fail. Struct layout follows
the platform's standard C ABI; callers must not use packed/reordered records.

Opaque `uint64_t` handles identify Model, Session, Result, Cancellation, PoolResult
or RepairResult objects.
Zero is invalid. A registry checks kind and lifetime, and tokens are not reused.
Entity identities contain owner, slot, an explicit kind (Variable=1, Row=2,
GlobalConstraint=3, Indicator=4) and a reserved zero field. The added kinds and
entry points preserve the existing ABI-1 24-byte identity layout. New clients
require these additive symbols; old clients retain their existing entry points. Keep these tokens and identities within the library/process instance
that created them; they are not serialized addresses or transferable capabilities.
The registry itself holds ownership; C callers must destroy every successfully
created owning handle. Results have independent ownership and never borrow model,
session, backend-vector, or caller-array memory.

All non-NULL pointers must refer to live, correctly aligned accessible C storage.
The caller remains responsible for actual buffer lengths and NUL termination;
portable C cannot validate arbitrary addresses or detect an undersized allocation
behind a valid pointer. Counts are checked for exact address/vector-size
representability before conversion. A nonzero input count requires a non-NULL
array. Coefficients and primal starts must be finite; bounds, options and model
edits use the C++ facade's domain/range checks. Inputs must remain stable for the
duration of a call and are copied before a backend solve. Outputs must not alias
input objects or each other. On an API error, output storage is unspecified unless
the specific rule below says otherwise; model builder failures follow the C++
facade's transactional checks.

Creating/solving functions zero the output owner token before work, except when
the output pointer itself is invalid. `result_number` returns a `present` flag and
sets the value to zero when absent. `result_value` returns `NO_SOLUTION` if no
validated incumbent exists. `result_values` exposes the original slot mask and
writes zero for absent/deleted values with distinct presence flags. Query buffer
sizes using all NULL buffers and capacity zero, allocate, then call again. Text
sizes include the terminating NUL. Insufficient capacity returns
`BUFFER_TOO_SMALL`, reports the required capacity, and writes no buffer elements.
Immutable results make the two-call buffer protocol stable.

Every fallible C entry point catches all C++ exceptions; none cross the boundary.
`last_error()` is a fixed-size, thread-local, NUL-terminated message (at most 4095
bytes). Copy it before the next ordinary API call on that thread, which clears or
replaces it. Version and error-message queries leave it intact. `MODEL_ERROR` is
used for facade validation exceptions, `INVALID_ARGUMENT` for C-record misuse,
`INVALID_HANDLE` for stale/wrong-kind opaque tokens, and `INTERNAL_ERROR` for other
backend exceptions. They are distinct from solver termination values.

## Concurrency, sessions, and limits

Registry ownership lookup holds a short global mutex; it never holds that mutex
through solver execution. Each model serializes edits and snapshot creation.
Each session serializes solve/reset/statistics. A session solve first copies the
model under its lock, releases that lock, then locks the session; there is no
model/session lock-order cycle. Independent model/session objects can solve
concurrently, subject to backend behavior. Results are immutable and can be read
concurrently. Cancellation uses the shared monotonic C++ token and can be signaled
from another thread. A canceled token cannot be reset.

Destroy removes the token immediately. An operation that already acquired shared
ownership may finish successfully; a later lookup fails cleanly. This prevents
use-after-free, and deliberately does not promise that destroy cancels or waits
for an in-flight solve. Concurrent Python `close()` calls on the same owner are
not promised to be idempotent; coordinate ownership at the application level.

Every solve receives fresh options. Model edits use the C++ session's compatibility
checks to select a backend update or rebuild; no C-level basis or witness memory
is exposed. Time limits subtract wrapper preparation and session-lock waiting
before entering the solver. They remain cooperative limits, not process-kill
wall-clock guarantees; snapshots, mutex waits, cleanup and output copying can
finish after the deadline. `elapsed_seconds` is the underlying C++ solve's measured
elapsed time, excluding the wrapper preparation and session-lock wait. Canceling
an active solve uses the same backend callback lifetime rules as the C++ API.

## Validation and build integration

The shared target compiles `c_api.cpp` with `GECODE_OPT_C_API_EXPORTS` and links the
matching `gecodeoptimize` build. A C++ wrapper and foundation library must use the
same headers/layout; do not link a wrapper built before a `ModelSnapshot` layout
change to a newer C++ foundation binary. The public C layout is independent of
those internal C++ layouts. CMake/install registration is owned by the main build.
The Python package contains no build-time code generator or runtime download.

The C conformance file must be compiled as **C99**, then linked with the shared
library. It checks malformed/null/oversized arguments, API/solver error separation,
wrong-kind/foreign/deleted identities, copied result buffers, immutable result
lifetime, session edits, cancellation, and explicit/missing backend selection.
The Python suite exercises analytic LP/MIP and continuous recourse optima, all five
variable domains including the semi zero branch, min/max offsets, model edits,
I/O and destination preservation, bad Python conversions, lifetime/context
management, starts, missing/canceled/unsupported results, independent parallel
solves and thread-local errors.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  GECODE_OPTIMIZE_LIBRARY=/absolute/path/to/libgecodeoptimize_c.so \
  python3 -m unittest discover -s python/tests -v
```

Run the same C and Python suites against backend-enabled and backend-disabled
builds. A disabled backend must return `UNSUPPORTED`, not skip the contract tests.
C ownership/error paths are also exercised with address/undefined sanitizers.
Expanded tests cover every typed global builder, aliases, nonzero/negative bases,
zero-arity tables, zero-resource cumulative tasks, removed/foreign handles,
checked dimensions and atomic failed edits; indicator domain guards/removal and
Boolean truth tables also run through this same C ABI. Native-aware assertions
require actual native optima/infeasibility when Native is available and explicit
UNSUPPORTED results otherwise; no backend-dependent contract case is skipped.
These small conformance tests do not establish backend performance, concurrent
speedup, full commercial Python API compatibility, binary distribution support,
or portability beyond the platforms actually tested. Native-enabled integration,
shared-library export/install loading, and Windows calling convention checks belong
to the matching main-build CI matrix; a local macOS run alone is not that matrix.

## Solution pools

`Model.solve_pool(PoolOptions(...))` calls the same repeated-optimization workflow
as C++: one representative per finite Integer/Binary projection assignment.
Continuous recourse is optimized within each class; it is not enumerated.
`projection=None` uses all active Integer/Binary variables in original slot order.
An explicit projection preserves caller order and must contain unique, active
variables with supported finite domains. An empty projection is supported only
when the source has no active variables; requesting it for a nonempty model
returns `UNSUPPORTED`. See [POOLS.md](POOLS.md) for arithmetic and backend limits.

```python
from gecode_optimize import Model, Options, PoolOptions, VariableType

with Model() as model:
    x = model.add_variable(VariableType.INTEGER, -1, 1)
    y = model.add_variable(upper=4)  # continuous recourse
    model.add_row({x: 1, y: 1}, lower=2)
    model.set_objective({x: 2, y: 1}, offset=5)
    with model.solve_pool(PoolOptions(Options(), max_solutions=5,
                                     projection=[x])) as pool:
        print(pool.completion, pool.ranked_prefix)
        for i in range(pool.info["entry_count"]):
            entry = pool.entry(i)  # frozen copied metadata, no owning token
            with pool.entry_result(i) as result:
                print(entry.projection_values, entry.rank_established,
                      result.objective)  # (-1,): 6; (0,): 7; (1,): 8
```

`PoolCompletion` is independent of `Termination`. `EXHAUSTED` requires the
remaining-model infeasibility check; reaching `max_solutions` gives
`REQUESTED_LIMIT` / `SOLUTION_LIMIT`, even if that last entry happens to be the
final feasible class. `ranked_prefix` counts entries with established rank.
An interrupted timely candidate may be returned as a final unranked entry;
inspect its flag instead of assuming every returned objective has a proved rank.
Ties have unspecified order. Numerical ranks/exhaustion are tolerance-qualified;
Exact enumeration requires an explicitly supported Native request.

`entry_result(i)` allocates a **new owning Result** with historical source
identity and masks. It survives closing the pool and source model. Its
termination is `UNKNOWN` and its global bound/gaps are absent: a later pool solve
optimizes a restricted feasible set and cannot supply a new original-model
optimality claim. `attempt(i)` is frozen metadata preserving that oracle's
termination, guarantee, optional objective and **remaining-model** bound. An
attempt's bound must not be interpreted as a bound on the unrestricted source.
`projection`, `entry(i)` and `attempt(i)` copy data without allocating C owner
tokens; indexed retrieval avoids creating handles for entries the caller will
never inspect.

C callers initialize `gecode_opt_pool_options_v1` with
`gecode_opt_v1_pool_options_default`. `has_projection=0` requires a NULL pointer
and count zero; `has_projection=1` distinguishes an explicitly empty projection.
`pool_info`, `pool_entry_info`, and `pool_attempt_info` require the exact record
size. `pool_projection`, `pool_entry_projection`, and `pool_message` use the
existing query/allocate/copy buffer protocol. `pool_entry_result` returns a
token that must be destroyed with `result_destroy`; the parent owner uses
`pool_destroy`. All handles are kind checked.

## Feasibility repairs

`Model.relax_feasibility(RepairOptions(...))` selects explicit row or variable
bound sides and minimizes their positive weighted L1 violation. Unselected sides
and integrality stay hard. Narrowed Binary bounds can relax only within the
intrinsic `[0,1]` domain. Optional phase two optimizes the original objective
among minimum-violation repairs. The source model is never edited.

```python
from gecode_optimize import (Model, Options, RepairOptions,
                            RelaxationSelection, RelaxationSide)

retained = None
with Model() as model:
    x = model.add_variable(upper=2)
    demand = model.add_row({x: 1}, lower=3, name="demand")
    model.set_objective({x: -1})
    options = RepairOptions(
        solve=Options(),
        selections=[RelaxationSelection(demand, RelaxationSide.LOWER, 1)],
        optimize_original_objective=True,
    )
    with model.relax_feasibility(options) as repair:
        if repair.has_repair:
            print(repair.original_value(x), repair.weighted_violation)  # 2, 1
            print(repair.original_validation.valid)  # False: demand still fails
            print(repair.item(0).violation)  # independently recomputed: 1
            private_x = repair.variable_map[x.slot].private
            retained = repair.final_result()

# An explicitly private result remains independently owned and usable.
if retained is not None:
    with retained:
        print(retained.value(private_x))
```

`has_repair` means the assignment passed the private repair model and independent
repair checks; it does not mean that it is feasible for the original model.
`original_validation` is the separate frozen original-model validation report.
Always inspect `has_repair` before reading original values or interpreting that
report. `minimum_violation_established` and `original_objective_optimized` are
separate flags. An `OPTIMAL` repair termination establishes only the requested
repair workflow, not original feasibility or unconstrained original optimality.
The optional scalar observations are `minimum_weighted_violation`,
`weighted_violation`, and `original_objective`; absence is `None`.

`variable_map` returns copied frozen records for every original variable slot,
including tombstones, with the source ID, private ID (or None before private
construction), and historical active mask. `original_values` separately returns
active/present/value records, with None for missing or deleted slots.
`original_value(variable)` accepts only an active source variable. Private IDs
are rejected there; source IDs are rejected when indexing private solve results.
All historical masks and observations remain available after source destruction.

`item(i)` includes the original source row or variable, selected side, copied
name, original bound, penalty, private slack/penalty-row IDs, and independently
recomputed optional activity/violation/weighted-violation/slack-value observations.
Items follow the C++ canonical order (row sides, then variable sides), not input
selection order. `stage(i)` returns copied name, index, completion flag and
optional retention threshold. `stage_result(i)` returns a new owning **private**
Result for that stage. Different stage revisions can reflect different lock
rows. `final_result()` returns a new owning private feasible Result, with
`UNKNOWN` termination and no scalar global bound. Neither accessor silently
remaps the result to the source model. `violation_lock` exposes the optional
private row identity, and `objective_values` copies the ordered workflow values.
`info` also preserves the internal workflow termination, guarantee and stage
counts separately from repair completion. `workflow_message` is copied text.
The binding does not expose an editable private model or a general
multiobjective builder.

C callers initialize `gecode_opt_repair_options_v1` through its default function
and pass `gecode_opt_relaxation_selection_v1` records. Each contains a Variable or
Row ID, explicit Lower/Upper enum, zero reserved field and positive finite
penalty. Indexed metadata access checks record sizes and bounds before writing.
The optional-number record uses an explicit presence flag and zero absent value;
there is no NaN absence sentinel. `repair_original_values` and
`repair_variable_map` support all-NULL buffers with capacity zero to query the
original slot count. Short buffers report the required size and leave every
array element unchanged. `repair_text` supports message, workflow message,
original validation message, item name and stage name; non-indexed fields require
index zero. A missing violation lock returns presence zero and a zero ID.
Private/final/stage Result handles must be destroyed separately from
`repair_destroy`.

Both workflows copy all options and snapshot the model before entering C++.
Existing cancellation tokens and cooperative time limits apply across their
stages; wrapper preparation is subtracted first. Unsupported starts, node
budgets, variable domains, active globals/indicators and guarantees retain their
documented C++ outcome; no fallback or semantic dropping occurs. Pools and repairs
use standalone workflow calls, never a persistent session. See
[POOLS.md](POOLS.md) and [RELAXATION.md](RELAXATION.md) for the precise support
matrix.

Malformed ABI sizes/reserved fields, unknown side/kind enums, impossible counts,
NULL nonempty arrays, and nonpositive/nonfinite penalties return an API error.
Well-formed workflow requests with a foreign/deleted/duplicate selected entity or
other invalid model semantics return a workflow `INVALID_MODEL` result, following
C++. Missing backends and supported-API/unsupported-solver requests return
`UNSUPPORTED` result owners. Retrieval using a foreign/deleted source identity
returns `MODEL_ERROR`; retrieving a missing validated assignment returns
`NO_SOLUTION`. Out-of-range nested indices return `INVALID_ARGUMENT`, with a zero
owner token from result-producing calls. Closing an owner invalidates its token
without invalidating already copied child Results.

These are additive ABI-1 symbols and new versioned records; existing records and
identity layouts are unchanged. The updated Python package requires a library
exporting the new symbols and reports a missing symbol explicitly at load time.
New tests include numerical and Native pools, recourse, negative projections,
ties/max offsets, requested-limit versus exhaustion, zero-variable/zero-item
workflows, historical tombstones, repair binary-domain guards, phase-two locks,
private/original ownership, malformed C records/buffers, cancellation, and a
source close during an active pool call. The threaded fixture checks the call is
still unfinished before cancel/close when HiGHS is present; it does not assert
which backend callback was active. Backend-disabled builds check explicit owning
Unsupported outcomes rather than skipping API contracts.

## Atomic bulk construction

`Model.add_variables(sequence[VariableSpec])`, `add_rows(sequence[RowSpec])` and
`add_rows_sparse(SparseRowBatch)` each make one C mutation call. They return
handles in input order and advance the revision once for a nonempty batch.
A valid empty batch leaves the revision unchanged, including a CSR with a valid
unused column mapping. Foreign/deleted mappings are still errors in that case.
Python names and arrays remain alive through conversion and the call; C copies
them. All five variable types and ordinary row canonicalization apply unchanged.

The additive ABI 1 records have exact size/reserved checks and separate array
counts. Output capacity must be supplied before mutation: unlike result
retrieval, there is no NULL-buffer query that posts a batch. Errors leave output
elements and model state unchanged. Post-commit C ID copies do not allocate.
An interrupted Python interpreter or a `MemoryError` while constructing Python
return objects after a successful C call cannot roll back the C transaction.
The [bulk API contract and example](BULK.md#c-and-python-bulk-construction)
specify CSR dimensions, UTF-8 validation, ownership, and tested failure cases.


## Distinct continuous quadratic models

The additive QP binding uses `QuadraticModel` and `QuadraticResult` in Python and
new `quadratic_model_*`, `quadratic_solve`, and `quadratic_result_*` C symbols.
They are separate registry kinds, not aliases for ordinary model/result handles.
Ordinary solve, session, pool, repair and mutation operations reject a quadratic
handle. No operation converts a quadratic model to its private linear core.
The existing ABI remains version 1 with all earlier layouts and symbols unchanged;
the updated Python package requires the new additive symbols from its library.

The scope matches [the C++ quadratic contract](QUADRATIC.md): continuous variables
with explicit finite bounds, ordinary linear rows, and positive weighted squared
affine forms. Integer/semi domains, indicators, globals, arbitrary Hessians, QCP,
nonconvex objectives, QP sessions and QP workflow retention are unavailable.
`Library.quadratic_capabilities()["available"]` (C: `quadratic_capabilities`)
reports whether the numerical HiGHS QP backend and required arithmetic environment
are available. It does not claim support for other quadratic problem classes.

```python
from gecode_optimize import QuadraticModel, QuadraticOptions, WeightedSquare

with QuadraticModel() as model:
    x = model.add_continuous(-4, 4, name="decision")
    model.add_row({x: 1}, lower=0)
    model.minimize_squares([WeightedSquare({x: 1}, offset=-2, weight=2)],
                           linear={x: 4}, offset=-7)
    historical = model.solve(QuadraticOptions())

with historical:  # still owns original values and checks after model.close()
    if historical.has_solution:
        print(historical.value(x), historical.objective)  # about 1, -1
    print(historical.termination, historical.checks)
```

`minimize_squares(squares, linear=(), offset=0)` minimizes
`linear + offset + sum(weight * residual**2)`.
`maximize_concave_squares` maximizes
`linear + offset - sum(weight * residual**2)`; weights stay strictly positive.
Each residual is `sum(coefficient * variable) + square.offset`.
Both methods replace the complete objective atomically. They accept `WeightedSquare`
records whose `terms` are ordinary mappings or sequences of `(Variable, coefficient)`
pairs, as for linear row construction. No NumPy dependency or borrowed solver buffer
is involved. Names and term arrays are copied. Malformed later squares, wrong-owner
IDs, nonpositive weights, nonfinite input and invalid linear terms preserve the old
objective and revision. A variable still referenced by a square cannot be removed.
Rows, finite variable bounds and row coefficients can be edited explicitly; removed
slots retain their historical identities in already completed results.

For C, initialize each `gecode_opt_weighted_square_v1` with zero reserved fields and
`struct_size=sizeof(record)`, then call `quadratic_model_set_objective` with a counted
array, separately counted linear terms, `GECODE_OPT_MINIMIZE` or
`GECODE_OPT_MAXIMIZE`, and the original objective offset. The latter sense means
**subtract** the positive squares. `NULL` arrays require zero counts. Non-NULL
strings must be accessible NUL-terminated UTF-8. The entire square/name/term input
is copied and validated before the C++ objective transaction commits.

```c
gecode_opt_handle model = 0, result = 0;
gecode_opt_id x;
gecode_opt_term term;
gecode_opt_weighted_square_v1 square = {0};
gecode_opt_quadratic_options_v1 options;
/* Check every returned API error code in production code. */
gecode_opt_v1_quadratic_model_create(&model);
gecode_opt_v1_quadratic_model_add_continuous(model, -4, 4, "x", &x);
term.variable = x; term.coefficient = 1;
square.struct_size = sizeof(square); square.terms = &term;
square.term_count = 1; square.offset = -2; square.weight = 1;
gecode_opt_v1_quadratic_model_set_objective(model, &square, 1, NULL, 0,
                                           GECODE_OPT_MINIMIZE, 0);
gecode_opt_v1_quadratic_options_default(&options, sizeof(options));
gecode_opt_v1_quadratic_solve(model, &options, &result);
gecode_opt_v1_quadratic_model_destroy(model);
/* Inspect using quadratic_result_*; ordinary result_* rejects this token. */
gecode_opt_v1_quadratic_result_destroy(result);
```

`QuadraticOptions.solve` is the existing `Options` record. The QP-specific options
expose the C++ iteration/storage limits and stationarity, complementarity and
optimality acceptance tolerances, with identical defaults. Both outer and embedded
C options require exact v1 sizes before their other fields are consumed; reserved
fields must be zero. Malformed options raise a binding/model error. Unsupported
policies (Native, Exact/Certified, starts, node quotas, multiple workers or nonzero
seed) return explicit `UNSUPPORTED` solver results. There is no backend fallback or
silent option drop. `optimality_tolerance=1e-6` is an absolute numerical acceptance
tolerance in original objective units, independent of large objective offsets and
of the common options' requested search gaps. Production regularization is zero.

Cancellation retains shared token ownership throughout solve. Snapshot copying and
C preparation are charged to the same end-to-end time limit. Backend cancellation
is cooperative and QPAS is checked before and after the backend call; this is not
a hard latency promise. A late candidate is not returned as an accepted solution.
A result owns its original snapshot identity, copied slot masks/values and checks
after model edits or destruction. No pointer to solver-owned memory crosses C.

`QuadraticResult.info` includes original model/revision, slots, termination,
guarantee, accepted-solution flags, elapsed time, QP iteration count and configured
regularization. It remains a numerical result even when its checks pass.
`objective`, `best_bound`, `absolute_gap`, `relative_gap` and `native_gap` use explicit
optional presence (`None` in Python). `vendor_objective` and `vendor_dual_estimate`
are separate optional diagnostics for the backend's normalized minimization
problem; they are not independent original-model bounds.

`checks` is an immutable copied `QuadraticChecks` record. Primal/objective validity,
KKT availability/validity and bound validity remain distinct flags, independent of
termination. KKT residual maxima are absent unless KKT evidence is available.
Original objective, normalized lower bound and offset-free `gap_upper_bound` have
separate presence fields. The offset-free gap can be tight while the rounded full
scalar `absolute_gap` is larger; neither is silently replaced by the other.

`values` copies original-slot records with distinct active and present masks.
`value(variable)` rejects foreign/deleted IDs and unvalidated candidates.
`square_residuals` contains the original affine residuals, **not** their squared
weighted contributions, in objective input order. `original_gradient` contains
derivatives of the original objective in original-slot order; inactive slots are
zero. Both arrays are `None` when complete original-objective evaluation is
unavailable, and may be empty for a successfully checked empty model. The C array
accessor reports length zero in the unavailable case; inspect `objective_valid`
to distinguish that from a valid empty array. Query/copy and short-buffer atomicity
follow the existing ABI conventions.

QP conformance adds C99 wrong-kind, destroyed, foreign and tombstone handle cases;
malformed outer/nested options and square records; atomic objective failures;
copy/query buffers; unavailable evidence; and historical results. Python adds 18
closed-form min/max parameter combinations, coupled squares with an equality and
nonzero original gradient, constant objectives, huge offsets, row edits, copied
inputs, removal/destruction, and explicit missing-backend/unsupported/limited
states. These supplement the C++ exact-bound and backend-coordinator oracles;
passing the bindings tests does not expand the numerical solver's supported scope.


Local validation of this binding slice: the C99 consumer and all 37 Python test
methods passed with both backends disabled, with Native+HiGHS enabled, and against
fully ASan/UBSan-instrumented facade/native/HiGHS libraries. The Python sanitizer
run preloaded the ASan runtime before loading the shared library. LeakSanitizer
is unavailable on this macOS configuration; the successful runs used address and
undefined-behavior checks with leak detection disabled. These are local conformance
results; cross-platform CI execution and binary wheels are separate validation.


## Original-coordinate LP observations

The additive O1 surface exposes ordinary continuous LP row activities/slacks,
row duals, column reduced costs, basis statuses and independent numerical KKT
checks. It requires HiGHS and Numerical policy; it does not relax fixed integer
variables, active indicators or globals into this scope. Explicit Native,
Exact/Certified and unsupported model classes return Unsupported. Basis export is
not basis submission, a ray, a sensitivity interval or a proof certificate.
`Library.lp_observation_capabilities()` returns an immutable record containing
availability, dual/basis support, backend/version and copied limitations.

```python
from gecode_optimize import Model, LpObservationOptions, LpObservationState

with Model() as model:
    x = model.add_variable(lower=0, upper=10)
    demand = model.add_row({x: 1}, lower=3)
    model.set_objective({x: 1}, offset=7)
    with model.solve_lp_observed(LpObservationOptions()) as observed:
        data = observed.observations
        result = observed.copy_result()
        if data is not None and data.dual_point.state == LpObservationState.AVAILABLE:
            marginal_cost = data.row(demand).dual
# data is a frozen Python copy; result is a separately owned ordinary Result.
with result:
    status = result.termination
```

`Session.solve_lp_observed(model, options)` uses the same options and owning result
contract. Options contain the existing `Options` record plus `duals`/`basis`
Boolean requests and four finite, nonnegative absolute tolerances in original
units: `dual_feasibility`, `stationarity`, `complementarity`, and `objective_gap`.
Defaults match C++ (1e-7, 1e-7, 1e-6, 1e-6). The shared cooperative deadline covers
snapshot conversion, backend solving and observation checks; binding preparation
reduces the remaining solve deadline. Requests do not change ordinary solve or
session defaults. A limited new session solve never returns the previous solve's
duals or basis as new observations.

`LpObservedResult` is a distinct token. Its `info` contains the original ordinary
result metadata and separate observation identity/count/presence fields;
`copy_result()` creates a new ordinary Result handle. Closing the observed result
cannot close that copy. `observations` is either `None` or an immutable copied
`LpObservations`, with original model ID/revision, frozen metadata/groups/checks,
and tuples of all historical row and column slots. It has no borrowed solver
storage and remains usable after the result/model/session closes. Its `row(id)`
and `column(id)` lookups reject wrong kinds, foreign owners and tombstones;
bulk `rows`/`columns` retain inactive slots with absent fields. IDs refer to the
historical snapshot, so later removal from the live model cannot erase an older
observation.

The primal-row, dual-point and basis groups independently distinguish
NotRequested, Available, Unavailable and Rejected, each with a typed reason and
copied message. Empty available arrays differ from unavailable evidence. A valid
primal point can exist while duals or basis are unavailable. Optional metrics and
row/column values are `None` when missing. Their C records use `present=0,value=0`
and `has_basis=0,basis=0` for absence; zero without its flag has no mathematical
meaning. Checks retain their own validity flags and optional residual maxima,
dual objective estimate and normalized primal-minus-dual gap. The gap cancels the
common objective offset before accumulation. Accepted KKT observations remain
Numerical and never upgrade the ordinary result to Exact or Certified.

Dual signs follow `A^T * row_dual + reduced_cost = c` in the original objective
sense. Row lower slack is `activity-lower`, upper slack is `upper-activity`; an
infinite side has no slack value. After adapter elision of constant rows, complete
original basis export is unavailable. A dual accepted for a retained model can
include original constant-row dual zero tagged DerivedConstantRow. Backend duals
are tagged Backend; missing duals use None. Metadata includes requested original
check tolerances, the primal check tolerance and optional effective vendor
primal/dual tolerances, plus backend name/version.

The C functions `solve_lp_observed` and `session_solve_lp_observed` return distinct
owning tokens. `lp_observed_result_copy_result` is their only conversion to ordinary
Result. Versioned options/info/metadata/group/row/column/check records have exact
size validation and zero reserved fields, including the nested solve options.
Bulk row/column functions additionally validate `element_size`; standard
query/copy functions check counts and write no elements on a short buffer. All
accessors are passive copies and do not solve or perform analysis. The additive
`NO_OBSERVATIONS` error covers a missing observation owner; `info` and result-copy
remain available in that case. ABI version 1 and all older record layouts remain
unchanged. C declarations are in `gecode/optimize/c_api.h`.

Tests in `test/optimize/lp_observations_c.c` and
`python/tests/test_lp_observations.py` check analytic min/max dual signs and
reduced costs, huge objective offsets, primal slacks, basis positions and constant
row basis absence. They also exercise opt-out groups, exact-size/reserved/flag
errors, buffer atomicity, wrong-kind/foreign/deleted handles, historical ownership,
session edits and stopped calls, unsupported fixed-MIP/global/Native/Exact
requests, and backend-free absence. These bindings complement the C++ observation
checker/oracle tests and do not expand the admitted solver scope.
The new C99 conformance test and all 44 Python test methods pass locally with
both backends disabled, with HiGHS enabled, and with the complete facade/HiGHS
path instrumented by ASan+UBSan. The sanitizer Python host preloads ASan; leak
detection is disabled because LeakSanitizer is unsupported on this macOS setup.
Combined native integration and cross-platform execution remain separate gates.

## Native starts through the existing ABI

The existing `Options.primal_start` now reaches the complete-start native path
without an ABI change. Supplied entries must be exact integers satisfying their
original domains; no rounding is performed, even for Numerical policy. Every
active original slot must be known. Missing live `inactive_gate` slots may be
derived from their indicator's exact activator relation, including seeded chains;
explicit inconsistent gates are invalid. Remaining partial starts are Unsupported.
A gate retained after indicator removal must be supplied explicitly and is never
derived from its old origin tag. Once independently checked and published, a
start is an incumbent for strict-improvement search on the original unfixed model.
It is not a domain fixing. This applies to supported standalone native solves;
persistent Native sessions remain Unsupported. See
[NATIVE-PRIMALS-DESIGN.md](NATIVE-PRIMALS-DESIGN.md).

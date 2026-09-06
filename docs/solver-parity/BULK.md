# Atomic bulk model construction

The C++ model supports `add_variables(vector<VariableSpec>)`,
`add_rows(vector<RowSpec>)` and `add_rows_sparse(SparseRowBatch)`. Each nonempty
batch is a single atomic edit and advances the model revision once. A valid
empty batch is a no-op. Returned handles follow input order, belong to the same
model and receive fresh slots after existing tombstones.

```cpp
#include <gecode/optimize.hh>
namespace O = Gecode::Optimize;
O::Model model;
auto vars = model.add_variables({
  {O::VariableType::Integer, -3, 7, "production"},
  {O::VariableType::Continuous, 0, 10, "recourse"}
});
O::SparseRowBatch rows;
rows.columns = vars;
rows.row_start = {0, 2};
rows.column = {0, 1};
rows.coefficient = {2, 3};
rows.lower = {7};
rows.upper = {std::numeric_limits<double>::infinity()};
rows.names = {"demand"};
auto constraints = model.add_rows_sparse(rows);
model.minimize({{vars[0], 4}, {vars[1], 5}}, 2);
```

The CSR column array is an explicit mapping to **unique live variable handles**;
its order need not match model slots. Every mapping entry is checked, including
unused columns. Indices refer to that array. Row offsets start at zero, are
monotone, and end at the coefficient count. Their length is one more than the
number of lower/upper bounds. Names are empty or have one entry per row. Empty
rows retain their ordinary mathematical meaning, including constant
contradictions. Rows can refer to existing variables only; adding variables and
then rows is two distinct atomic batches, not one cross-batch transaction.

Within each row, unsorted or repeated column indices use exactly the ordinary
row builder's deterministic compensated coefficient coalescing. This preserves
the existing numerical model contract; it does not introduce exact rational
arithmetic. All five variable domains, finite-coefficient rules, infinite-bound
conventions and validation errors are the same as the scalar API.

Validation, normalization, names and return handles are prepared before any
entity is appended. Allocation or validation failure leaves the previous model,
its revision, and existing entity references unchanged. Final vector growth is
the last potentially throwing operation; entity moves are required to be
nonthrowing. Capacity grows geometrically so repeated small batches do not
introduce quadratic reallocation behavior. Successful additions can invalidate
existing references into the model, as with ordinary vector-backed additions;
stable handles and owning historical snapshots remain valid.

CSR handling uses memory proportional to columns, rows and nonzeros, plus the
owning model and temporary normalized rows. It never materializes a dense
rows-by-columns matrix. Column-identity validation sorts a temporary ID array;
each row's terms use the existing canonical sort/coalescing routine. This API
reduces call overhead and gives atomic construction; no measured solver speedup
or zero-copy data ownership is implied.

`optimize-bulk` checks scalar/batch equivalence, arbitrary CSR mapping order,
large-coefficient cancellation, all variable domains, tombstones, historical
snapshots, malformed CSR dimensions/indices, stale/foreign handles, invalid late
entries, no-op batches and moved-from models. Allocation failure is injected at
each successive allocation until every batch type succeeds; failed calls must
retain original values, revision and reference addresses. A 16,384-square
diagonal model permits no individual allocation above 4 MiB, making accidental
dense construction fail the test. The fast gate's `bounded_integer` case also
uses the bulk variable and CSR row paths and retains its independent optimum
oracle. Bulk column insertion and general edit transactions remain subsequent
API work; the C/Python bulk surface is described below.

## C and Python bulk construction

ABI 1 adds `gecode_opt_v1_model_add_variables`, `model_add_rows` and
`model_add_rows_sparse`. The input records are `gecode_opt_variable_spec_v1`,
`gecode_opt_row_spec_v1` and `gecode_opt_sparse_row_batch_v1`. Every record has
an exact `struct_size` and a zero `reserved` field. Set variable bounds
explicitly in C; the enum does not change a supplied upper bound.

Each function requires a caller-owned ID array whose capacity covers the
already-known number of input entities. For CSR that number is `lower_count`.
There is **no size-query mutation**: a short output returns `BUFFER_TOO_SMALL`
and posts nothing. A nonzero output capacity requires a non-NULL pointer;
a valid zero batch permits NULL with zero capacity. API errors leave output
array elements untouched, so callers must use returned IDs only after `OK`.
Outputs must not overlap input records/arrays/names. All non-NULL pointers must
refer to accessible storage of the declared length for the entire call.

Conversion, UTF-8 validation, string copies, output-capacity checks, and C++
normalization happen before commitment. The result IDs are copied into caller
storage without allocation after the atomic C++ operation. No C++ exception
crosses the ABI. API/model errors preserve the model and revision. Successful
nonempty calls advance the revision once, and valid empty calls do not.
A separate variable batch followed by a row batch remains two transactions.

CSR has independent pointer/count pairs for columns, row starts, column indices,
coefficients, lower bounds, upper bounds and names. A valid zero-row CSR still
has `row_start={0}` and validates any supplied column mapping. Indices are
unsigned 64-bit integers with checked conversion to the platform's `size_t`;
there is no truncation on a 32-bit consumer. NULL arrays require count zero.
Names may be omitted with count zero or supplied one per row. An individual
NULL name means the empty string. Bulk C names must be NUL-terminated UTF-8;
invalid/overlong encodings, surrogates and values above U+10FFFF are rejected.
The first NUL terminates a C name. Python rejects embedded NULs before calling C.
Input arrays and strings can be released or changed after the call returns.

Python exports `VariableSpec`, `RowSpec` and `SparseRowBatch`; each accepts
ordinary sequences, and a `RowSpec.terms` also accepts a mapping. Each public
bulk method performs exactly one C mutation call, returning a tuple of handles.
No NumPy dependency or per-nonzero C call is involved. Data is copied; this is
not a zero-copy buffer protocol. Python default variable upper bounds match the
scalar binding: 1 for Binary, +infinity otherwise.

```python
from gecode_optimize import Model, VariableSpec, SparseRowBatch, VariableType

with Model() as model:
    x, y = model.add_variables([
        VariableSpec(VariableType.INTEGER, -3, 7, "production"),
        VariableSpec(upper=10, name="recourse"),
    ])
    rows = model.add_rows_sparse(SparseRowBatch(
        columns=[x, y], row_start=[0, 2], column=[0, 1],
        coefficient=[2, 3], lower=[7], upper=[float("inf")],
        names=["demand"],
    ))
```

Python conversion failures occur before the C mutation. The C transaction
covers input validation, normalization and model allocation. Constructing Python
return objects after a successful C call can itself raise `MemoryError`; Python
interpreter allocation failure is not a rollback protocol. Existing handles and
owning results retain their historical identities across successful batches and
model destruction. A historical result cannot look up a variable added later.

The C99 consumer exercises all three bulk functions, output preflight, invalid
records/counts, malformed UTF-8, all five domains, late model failures, CSR
mapping/offset errors, unused foreign/deleted zero-row mappings, revision and
result-history preservation. Python conformance adds scalar/CSR model-file
and optimum equivalence, Unicode name lifetime, empty contradictions,
wrong-library handles, checked index conversions and dispatch counting for a
1,024-nonzero batch. Local C99 and all 28 Python tests pass with both backends
disabled and with Native+HiGHS; C99 and Python also pass against a fully
ASan/UBSan-instrumented numerical foundation and HiGHS. These are correctness
checks; no timing claim or completed Windows runtime verification follows.

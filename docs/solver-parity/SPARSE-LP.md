# Sparse certified binary and bounded-integer LP relaxation

The experimental LP relaxation now has a complete CSR path through model storage,
HiGHS import, exact certificate preparation and original Gecode constraint
posting. W5 now also has a separate explicit bounded-integer model, exact
interval certificate checker and bound-change-aware native propagator. The
original binary API remains strict. This experimental component does not change
the `Gecode::Optimize` API or its backend selection.

## API and storage

```cpp
namespace LP = Gecode::Experimental::LpRelaxation;
LP::SparseLinearModel model;
model.row_start = {0,2,4,6};
model.column = {0,1, 1,2, 0,2};
model.a = {1,1, 1,1, 1,1};
model.b = {1,1,1};
model.c = {1,1,1};
auto backend = std::make_shared<LP::SparseBackend>(std::move(model));
// In a Gecode Space with binary IntVarArgs x and integer objective z:
LP::binary_linear_minimize(home,x,z,backend,LP::Frequency::EveryNode);
```

The model is `min c*x`, with `a*x >= b` and `x` binary. Row `i` occupies
`[row_start[i],row_start[i+1])`; `a[k]` belongs to `column[k]`. Offsets must start at
zero, end at the number of values and be nondecreasing. Columns in each row must
be strictly increasing, within range, with no duplicate indices or explicit zero
values. Empty rows and the default empty model are supported. Malformed public
CSR data is rejected before import, posting or certificate arithmetic. Individual
coefficients retain the existing magnitude limit of `1e9`; native posting also
checks Gecode dimensions and objective limits.

`SparseLinearModel` contains only CSR arrays and the dense row RHS/objective
vectors. `SparseBackend` takes an immutable owned copy, with no dense matrix
shadow. HiGHS receives CSR directly; its internal working representation and
basis are additional storage. Native rows allocate coefficient/variable arrays
only for the nonzeros in that row. Matrix import, validation and posting take
`O(rows + columns + nnz)` input work. HiGHS itself may perform more work or allocate
additional factorization storage depending on the problem.

The original `LinearModel {a,b,c}`, `Backend(LinearModel)` and dense posting/checker
entry points remain available. `Backend` now derives from `SparseBackend` and
retains its original public `const LinearModel model`. It converts constructor
input to CSR once, then uses CSR on subsequent LP/certificate/propagation calls.
Consequently the legacy backend retains both representations; choose
`SparseBackend` for sparse storage. `LP::sparse_model(dense)` converts the current
contents of a mutable dense model. Dense posting reads the current contents on
each call. There is no hidden cache keyed by a mutable model's address, and
mutating constructor input cannot alter either published backend model.

The standalone checker accepts
`LpCertificate::SparseMatrixView{row_start,column,values,columns}`. The view borrows
arrays only for that call; a prepared `Certificate` owns its residual data.
Optional `PreparationStats` counts rows visited, residuals initialized and
nonzero coefficient products. Validation visits CSR entries, then arithmetic
visits only entries whose row has a nonzero quantized multiplier. The legacy
dense checker overload converts on each preparation; repeated evaluation should
reuse the resulting certificate or use CSR directly.

## Proof and ownership invariants

HiGHS supplies candidate row multipliers, not pruning decisions. Multipliers are
quantized to nonnegative `q/2^20`. The checker constructs the exact affine bound

```
(q*b + sum_j min((2^20*c - A^T*q)[j] * lower[j],
                 (2^20*c - A^T*q)[j] * upper[j])) / 2^20.
```

All products/sums use checked signed 128-bit arithmetic. Integer ceiling is valid
because this component's objective is integral. Invalid dimensions, malformed
CSR, nonfinite/out-of-range multipliers and arithmetic overflow produce no
certificate, with caller outputs unchanged. Platforms without the existing
checked 128-bit support keep the conservative no-certificate fallback. Binary
conditional filtering uses the same exact residuals and checks its arithmetic.
Sparse storage does not introduce floating-point summation into certification.

The shared backend still serializes access. Every LP call replaces all column
bounds, including bounds relaxed when another sibling uses the workspace. A
simplex basis is a hot start only. Spaces/clones share backend ownership and may
reuse immutable certificates, evaluated against their own boxes. Tests cover
sibling recovery after an infeasible numerical LP and concurrent serialized
callers. Original native constraints and objective equality remain posted.
Numerical infeasibility alone never fails a Gecode space. For a completely zero
matrix, the backend uses the exact zero-multiplier box bound without calling
HiGHS; original native constant rows still enforce infeasibility.

## Explicit bounded integers

```cpp
LP::BoundedIntegerModel model;
model.linear.row_start = {0,2};
model.linear.column = {0,1};
model.linear.a = {1,1};
model.linear.b = {-1};
model.linear.c = {2,9};
model.lower = {-3,-3};
model.upper = {3,3};
auto backend = std::make_shared<LP::BoundedIntegerBackend>(std::move(model));
LP::IntegerOptions options;
options.frequency = LP::Frequency::EveryNode;
options.bound_tightening = true;
options.bound_change_interval = 4;
// x must already contain initialized IntVars; existing holes are preserved.
LP::integer_linear_minimize(home,x,z,backend,options);
```

The objective is exactly `min c*x`, with integral coefficients, finite integral
domains and rows `A*x >= b`. Negate a row to express `<=`, or post both directions
for equality. There is no objective offset, floating coefficient, variable-type
inference or arbitrary coefficient rounding. `BoundedIntegerBackend` is unrelated
to `SparseBackend` in the type hierarchy: it cannot silently enter the binary
posting API. `validate_integer_model` and `post_native_integer` provide explicit
validation and original native posting without an LP backend.

Backend construction validates and owns the model. Every endpoint must lie in
Gecode's finite integer limits, domains must be nonempty, and coefficients/RHS
retain the magnitude limit of `1e9`. To keep original native linear propagation
within exact arithmetic, every row must satisfy
`sum max(abs(a_j*lower_j),abs(a_j*upper_j)) <= Int::Limits::max`. The objective
has the same check with `Int::Limits::max/2`, reserving the other half for its
equality's objective variable. Products fit int64 under these endpoint/coefficient
limits and sums are checked before addition. Unsupported ranges throw
`invalid_argument` before posting; tighten domains or use an exactly equivalent
integer formulation. These conservative limits can reject mathematically valid
models. They are deliberate proof boundaries, not declarations of infeasibility.

Native posting intersects the supplied variables with the original domains,
preserves existing holes, bounds the objective to its checked expression range,
and posts every original sparse row and objective equality. Gecode retains the
actual domains; the continuous LP sees their interval hulls. Later LP boxes must
be subsets of the original model domains. Shared calls restore all endpoints,
including looser siblings; the backend remains serialized. Numerical LP status
and objective values alone never justify pruning.

The standalone checker exposes `Certificate::lower_bound_integer`,
`Certificate::filter_integer` and dense/CSR `integer_lower_bound` helpers. Unlike
the native adapter, it accepts full int64 endpoints whenever its checked int128
arithmetic and int64 result succeed. Existing `lower_bound` and `filter` remain
binary. With `s=2^20`, residual `r=s*c-A^T*q`, constant `q*b`, and original-box
numerator `B=q*b+sum min(r_j*l_j,r_j*u_j)`, a cutoff `c*x <= U` requires

```
r_j*x_j <= s*U - (B - min(r_j*l_j,r_j*u_j)).
```

Positive residuals give an upper bound by integer floor division; negative
residuals give a lower bound by integer ceiling division. Zero residuals need no
individual cut. Every cut uses the same original box, so simultaneous
intersections are safe. `IntegerFilterResult` returns the integer lower bound,
intersected endpoint arrays, and an infeasibility flag. When infeasible, its
endpoint arrays have no further semantic meaning. Checked endpoint products,
additions/subtractions, signed minimum divided by `-1`, and quotient narrowing
fail closed, preserving the caller's result on failure. A prepared certificate
is valid for its original row/objective data only; it has no mutable public
residual fields or association with arbitrary later model edits.

`IntegerOptions` defaults to a bound-only LP at each observed interval change.
The root is always attempted; `bound_change_interval` counts variables whose
lower or upper endpoint changed since the previous propagation observation.
It does not wait for binary assignments. Bound tightening is opt-in. Retained
certificates can react to objective cutoffs and narrower boxes without an LP
call; interval holes and objective-only events do not count as LP reoptimization
events. Root frequency with tightening retains that certificate in descendants.
Clones copy their own scheduling state while sharing immutable certificates and
backend ownership. `Stats::variable_bound_tightenings` counts changed variable
intervals, and `variable_fixings` still counts resulting assignments.

## Validation

These are correctness/storage checks, not timing benchmarks:

- Existing standalone certificate edge/overflow tests and 3,000 exhaustive
  randomized binary models.
- `sparse-certificate.cpp`: malformed offsets/indices, duplicate and zero entries,
  corrupted multipliers, exact arithmetic overflow, unchanged failed outputs,
  3,000 dense/CSR comparisons with independent assignment/filtering oracles, and
  looser sibling boxes. Diagonal matrices of size 32,768 and 65,536 verify linear
  container storage and exact operation counts; corresponding dense int64
  matrices would occupy 8 and 32 GiB.
- `backend.cpp`: original tests plus dense/CSR equivalence over all 27 boxes of a
  triangle, immutable input snapshots, malformed CSR rejection, zero matrices
  and serialized sparse sibling calls.
- `propagator.cpp`: 120 independently enumerated models in both storage forms,
  including negative costs, empty/infeasible/constant rows and fixed variables.
  Native, root/node bounds, root/node fixing and throttled fixing run DFS/BAB at
  three recomputation distances: 8,640 configurations. Checks include complete
  solution sets, optimal objectives and backend disposal.
- `sparse-storage.cpp`: a 16,384-square diagonal model passes backend import,
  native actor posting and exact certification in both binary and signed integer
  forms under a 16 MiB single-C++-allocation
  guard. Dense int64 materialization would require 2 GiB. The observed largest
  allocation in the tested build was 1 MiB. This guard does not assert a bound on
  total memory or numerical factorization memory for arbitrary models.
- `integer-certificate.cpp`: 3,000 independent signed box/cut oracles, 625 strict
  interval cuts and 14,669 cutoff-feasible witnesses; dense/CSR equivalence,
  negative division, fixed/empty boxes, zero residuals, looser siblings, corrupted
  candidates, int64 extrema and checked int128 overflow with unchanged results.
- `integer-backend.cpp`: signed original domains, fractional LP optimum 4.5
  certified as integer bound 5, immutable input, sibling recovery, 80 serialized
  calls, zero matrices, and rejection at native domain/activity proof boundaries.
- `integer-propagator.cpp`: 80 independently enumerated signed models in 1,920
  DFS/BAB configurations; all original solutions and optima, holes, fixed/empty
  models, clone/recomputation/disposal behavior, nonassignment bound scheduling,
  and a targeted residual interval cut checked against every cutoff-feasible
  assignment.
- `integer-driver.py`: native/LP integer modes, warm/cold starts, both branching
  policies and legacy dense/CSR binary compatibility checked against independent
  exhaustive enumeration; malformed/fractional/infinite input is rejected.

All eight C++ tests pass with C++17, assertions enabled, and
`-Wall -Wextra -pedantic`, including ASan+UBSan builds. The sanitizer run instruments
the test/adapter code, HiGHS, and the native Gecode support/kernel/search/integer
libraries; those native libraries contain the `ActorLink` sentinel correction.
Address and undefined behavior errors halt the tests. Leak detection is disabled
for the macOS run, so this is not a sanitizer leak-detection claim; explicit
shared-owner lifecycle assertions still run. Use the same instrumentation for
HiGHS and the adapter: mixing instrumented libc++ vector operations with an
uninstrumented numerical dependency is unsafe.

The standalone tests can be compiled from the repository root without any solver:

```sh
mkdir -p build/sparse-lp
c++ -std=c++17 -Wall -Wextra -pedantic -UNDEBUG -I. \
  experiments/lp-relaxation/tests/certificate.cpp -o build/sparse-lp/certificate
c++ -std=c++17 -Wall -Wextra -pedantic -UNDEBUG -I. \
  experiments/lp-relaxation/tests/sparse-certificate.cpp -o build/sparse-lp/sparse-certificate
build/sparse-lp/certificate
build/sparse-lp/sparse-certificate
c++ -std=c++17 -Wall -Wextra -pedantic -UNDEBUG -I. \
  experiments/lp-relaxation/tests/integer-certificate.cpp -o build/sparse-lp/integer-certificate
build/sparse-lp/integer-certificate
```

For the binary/integer backend and propagator tests and `sparse-storage.cpp`, use the configured
native Gecode build include directory **before** the source directory, plus the
HiGHS source/generated include directories. Link HiGHS and the existing native
`gecodeminimodel`, `gecodeint`, `gecodesearch`, `gecodekernel`, `gecodesupport`
libraries and their normal platform dependencies. Tests are header based and
must compile against the changed source checkout. Existing experiment build
commands still compile the expanded backend and propagator tests; compile the
additional standalone sources explicitly until they are added to a build target.
Native libraries and source headers must come from the same kernel revision;
in particular, do not mix older brancher sentinel headers with libraries built
after the `ActorLink` sentinel correction.

## Opt-in experiment route

The isolated `experiments/lp-relaxation/driver.cpp` accepts a final `--sparse`
argument. Its input parser writes CSR directly, validates incumbents by nonzeros,
and uses sparse native posting/backend construction. It keeps the original
six-argument behavior as the default, and labels output `matrix_storage` as
`dense` or `csr`. Both the native-only executable and the `WITH_LP` executable
support the flag. For example, using the existing experiment build outputs:

```sh
path/to/lp INPUT node size 5000 0 1 --sparse
path/to/stock INPUT none size 5000 0 1 --sparse
```

Compare feasibility/objective and independently validate returned assignments
before collecting performance data. The sparse parser retains the experiment's
10,000-row/column limits but removes the dense matrix product limit for the
explicit sparse route. The main solver-bench experiment and its defaults are
unchanged. No new timing results or claimed speedups accompany this slice.

The new `--integer` route always uses CSR. It requires a literal `bounds` and
`n` lower/upper pairs immediately after the objective coefficients; sparse rows
and the incumbent trailer follow as before. Example with optimum `-23`:

```text
2 1
2 9
bounds -3 3 -3 3
-1 2 0 1 1 1
incumbent 1 -3 2
```

```sh
path/to/lp INPUT node size 5000 0 1 --integer
path/to/lp INPUT root-tight size 5000 1 1 --integer
path/to/lp INPUT node-tight size 5000 1 1 --integer
path/to/stock INPUT none size 5000 0 1 --integer
python3 experiments/lp-relaxation/tests/integer-driver.py \
  --lp path/to/lp --native path/to/stock
```

`root-tight` and `node-tight` enable exact interval cuts and are accepted only
for integer inputs. Output adds `variable_domain` (`binary` or `bounded-integer`)
alongside `matrix_storage`; consumers should not infer variable domains from
the storage format. Integer incumbents are checked against every original row
and domain, and unsupported extra trailing content is rejected. The existing
default and `--sparse` binary inputs retain their format and behavior.

## Remaining W5 gates

This completes the finite bounded-integer proof path within the stated native
range restrictions. It does not add continuous objectives, first-class
semi-continuous/semi-integer domains, objective offsets, rational coefficient
normalization, mixed-variable relaxation groups or a public Optimize-to-native-LP
bridge. External native integer-domain holes remain enforced, but are not new
typed domain metadata in this model. Continuous objectives must never receive
the integer-ceiling rule. The LP budget is a bounded work attempt, so a valid
certificate need not be the best LP bound. The existing per-call limits remain
10,000 simplex iterations and an additional 0.2 seconds of HiGHS runtime. The
workspace has no caller cancellation/deadline parameter; a future public bridge
must account for that cooperative call latency or extend the contract. These
limits are not a hard wall-clock guarantee for a complete search. Shared LP pooling or parallel basis
ownership remains deferred; serialized workspace access is intentional.

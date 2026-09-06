# Exact scoped cover-cut records

`gecode/minimodel/lp-cuts.hpp` adds an explicit cut-record, cover-separation and
bounded-pool layer beside the existing experimental LP headers. It does not
modify `solve`, native propagation, HiGHS import, default presets or the existing
`lp-strengthening.hpp` behavior. This is a first W7 proof/ownership slice, not a
complete branch-and-cut implementation.

## Source and proof contract

```cpp
#include <gecode/minimodel/lp-cuts.hpp>
namespace LP = Gecode::Experimental::LpRelaxation;
namespace Cuts = LP::Cuts;

LP::BoundedIntegerModel model;
model.linear.row_start = {0,2};
model.linear.column = {0,1};
model.linear.a = {-3,-3};
model.linear.b = {-5};                 // 3*x + 3*y <= 5
model.linear.c = {0,0};
model.lower = {0,0}; model.upper = {1,1};
Cuts::SourceModel source(std::move(model));

auto cut = Cuts::verify_cover(source,
    Cuts::CoverProof{0,{1,0},Cuts::Scope::global()});
// cut.inequality(): columns {0,1}, coefficients {1,1}, upper 1.
```

`SourceModel` validates and owns an immutable `BoundedIntegerModel` snapshot.
The native domain/coefficient/activity limits described in [SPARSE-LP.md](SPARSE-LP.md)
apply. Copies of `SourceModel` share identity; a separately constructed equal
model has a distinct identity. Input mutation, source-handle destruction, and
moving the source do not alter retained cut records. Accessing a moved-from
source is rejected. This module has no connection to mutable Optimize model
IDs or revisions: a later integration must explicitly establish and preserve
that association.

`CoverProof` is untrusted input: an original row index, selected original column
indices, and a scope. The checker obtains coefficients, signs, bounds and
weights from the owned source. Selected indices are sorted; duplicates, absent
terms and fixed variables are rejected. There is no interface for attaching a
validity label to an arbitrary user-supplied inequality. `VerifiedCut` has a
private constructor, read-only proof/inequality accessors, and retains the source
snapshot, scope, exact capacity and cover weight.

Proof verification does not depend on a candidate LP point, floating tolerance,
dual multiplier, objective value or solver status. Calling `verify_cover` on a
valid cover that does not violate a particular point still succeeds.

## Exact transformation and validity

The original row is `A*x >= b`. Within the certified box, substitute exactly
fixed integer variables, whose contribution is `F`. Every remaining nonzero
term must have an integral binary domain `[0,1]`. Other free integer terms are
explicitly unsupported; terms fixed to any supported signed integer value can
be substituted. Zero coefficients cannot occur in canonical source CSR.

For each free term, use literal `x[j]` when `a[j]<0`, and literal `1-x[j]` when
`a[j]>0`. Then the row is exactly equivalent, inside its scope, to

```text
sum(abs(a[j]) * literal[j]) <= sum(positive free a[j]) - b + F.
```

All weights are positive. If a selected subset has total weight strictly greater
than the capacity, its literals cannot all equal one. Therefore
`sum(selected literals) <= number_selected - 1` is valid. Translating complemented
literals back to original variables yields canonical coefficients in `{-1,1}`
and a checked integral upper bound. If the capacity is negative, the empty cover
proves `0 <= -1` in that scope. Equality of cover weight and capacity is
insufficient and is rejected.

The implementation reuses `Strengthening::Detail::add`, `subtract`, `Term` and
`PackingRow` from `lp-strengthening.hpp`, along with its established signed-literal
translation and grow-then-minimize cover rule. It does not invoke the legacy
dense `Builder`: that API returns strengthened dense rows without the original
proof/scope ownership needed here. The legacy clique, pair, fixing and cover
features remain unchanged. Checked signed int64 arithmetic protects new fixed
substitution and rational-point operations; unsupported arithmetic fails without
publishing an unchecked record. This cut layer does not require int128 support.

## Global and local scope

A global proof uses the original model bounds and must not carry a local box.
A local proof carries lower/upper arrays for every original variable; they must
form nonempty subintervals of the source bounds. Local bounds are never silently
promoted to global validity, even when they happen to equal the source box.

For example, `2*x+2*y+2*z <= 4` permits `x=y=1` when `z=0`. Inside the local box
`z=1`, exact substitution proves `x+y <= 1`. That cut must not enter the sibling
with `z=0`.

```cpp
Cuts::Box node{source.model().lower,source.model().upper};
// Tighten node bounds for the intended proof scope, then:
auto local = Cuts::verify_cover(source,
    Cuts::CoverProof{row_index,cover_columns,Cuts::Scope::local(node)});
bool usable = local.applies_to(source,current_node_box);
```

`applies_to` requires the same immutable source identity and a valid current box
contained in the certified local box. Global records accept any valid box inside
their original source domains. Malformed, empty, widened and foreign-model boxes
fail that guard. The proof uses interval hulls; it does not depend on unrecorded
domain holes, node IDs, mutable variable handles or an assumed tree ancestry.

This module intentionally has no operation that posts a `SparseCut` to a solver.
A future consumer must preserve original-variable mapping and check scope at the
point of use. Copying the naked inequality and discarding its record would
discard the information required for safe local reuse.

## Deterministic bounded separation

```cpp
Cuts::FractionalPoint point{{3,3},4};   // x=y=3/4
Cuts::SeparationOptions options;
options.max_work = 100000;
auto separated = Cuts::separate_covers(source,point,Cuts::Scope::global(),options);
```

The point is an exact rational vector with a shared positive int64 denominator.
It must lie in the requested box; it need not satisfy all original rows. Points
and checked operations that cannot be represented in the supported arithmetic
are rejected. Converting numerical LP solutions to this rational representation
is a future adapter responsibility. There is no hidden floating rounding policy.

The separator tries point-value, descending-weight and literal-index orderings,
with explicit index tie breaks. Starting from a bounded number of positions, it
grows a cover, then removes light terms while the remaining weight still exceeds
capacity. Each candidate must be exactly violated by the rational point and must
pass the independent source-based proof checker before being returned. A fixed
merge-sort schedule makes budget prefixes independent of the standard library's
`std::sort` implementation.

Defaults bound work to 100,000 units, 256 visited rows, 512 source nonzeros per row,
32 returned cuts, four returned cuts per row and four starts per ordering. Work
units cover box/point coordinates, source-term visits, sorting comparisons and
output entries, greedy/minimization steps, proof reconstruction and cut-key
comparisons. Source construction/validation is a separate one-time operation.
Ordinary allocation, vector copying and destruction are not wall-clock budget
measurements; their sizes are bounded by source shape and accepted work/output.

The result reports reached work/row/cut caps, oversized and unsupported rows,
arithmetic rejections and duplicate cuts. Work exhaustion preserves previously
verified returned cuts. A zero work or cut budget can return immediately without
validating unused point/proof input. This is a bounded heuristic: an empty result
does not prove that no violated cover exists. No wall-clock or performance claim
follows from its work counter.

## Bounded pool and duplicate policy

```cpp
Cuts::CutPool pool(source,Cuts::PoolLimits{64,4096,16384});
for (const auto& cut : separated.cuts) pool.insert(cut);
auto active_records = pool.applicable(current_node_box);
```

The pool accepts only verified records for its source identity. Defaults limit
it to 64 records, 4,096 total cut nonzeros and 16,384 stored local-scope endpoint
values. These are structural storage limits, not an allocator byte/RSS promise;
the shared source snapshot is stored once. Capacity rejection and allocation
failure leave the previous pool unchanged. No eviction or unproved weakening is
performed to make a new record fit.

Canonical equality compares sorted columns, signs and upper bounds, independent
of original-row provenance or the order of a submitted cover. An existing
identical cut with a broader proved scope makes a narrower candidate redundant.
A separately verified broader candidate can replace narrower identical records,
including a global proof replacing local ones. Incomparable local boxes remain
separate; the pool never takes their interval hull or guesses their union is a
valid scope. Returned records are owning values and retain their historical scope
after later pool edits. The pool does not implement general inequality dominance,
lifting, aging, effectiveness scoring or thread-safe concurrent mutation.

## Correctness checks and remaining W7 work

`experiments/lp-relaxation/tests/cuts.cpp` uses independent original-row enumeration
without calling Gecode search, HiGHS, the legacy strengthening algorithm or the
certificate checker as an oracle. It exercises 750 signed integer models with
global and local scopes: 2,092 verified covers, 20,884 rejected proof requests,
955 separated cuts and 659 feasible sibling witnesses that would be removed if
scope checks were omitted. Targeted fixtures cover signed complements, positive
and negative fixed integers, strict/equal capacity, empty contradictions,
immutable identity, stale/foreign records, forged claims, pool scope dominance,
capacity rejection, arithmetic overflow and exact fractional separation.

All work limits from zero through 299 produce reproducible bounded prefixes on
the same fixture. A 16,384-variable source verifies that point-coordinate scans
also stop at the work cap and that a two-term pool record remains sparse.

The standalone test requires a configured native include directory for Gecode
configuration headers, but links neither a solver nor native Gecode libraries:

```sh
c++ -std=c++17 -Wall -Wextra -pedantic -UNDEBUG -DGECODE_NO_AUTOLINK \
  -Ipath/to/configured-gecode-build -I. \
  experiments/lp-relaxation/tests/cuts.cpp -o build/lp-cuts/cuts
build/lp-cuts/cuts
```

Normal and ASan+UBSan runs pass with assertions enabled and the warning flags
above. The sanitizer run instruments the complete cut implementation, since it
is header based and links no solver libraries. Address/undefined-behavior errors
halt the test; leak detection is disabled for the macOS run.

Remaining work includes cut consumption with scoped native/LP ownership,
interrupted-search behavior, numerical candidate conversion, integration with the
legacy strengthening API, lifted covers, verified clique/MIR/Gomory families,
cut aging/selection and performance evaluation. No change to default solver
behavior or timing benchmark accompanies this slice.

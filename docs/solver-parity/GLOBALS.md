# Native global constraints

The owning model now retains typed all-different, variable element, allowed
table, cumulative-resource, circuit and sparse deterministic Regular constraints. They have stable
model-aware handles, names, revisions and tombstones like linear rows. Adding
a malformed constraint leaves the model unchanged. Removing a referenced
variable requires removing the global first. Bounds may change freely because
these records retain semantics, rather than a bound-dependent linear lowering.

```cpp
#include <gecode/optimize.hh>
namespace O = Gecode::Optimize;
O::Model m;
auto a = m.add_integer(0, 10);
auto b = m.add_integer(0, 10);
O::add_cumulative(m, {a, b}, {3, 2}, {1, 1}, 1, "machine");
m.minimize({{a, 1}, {b, 1}});
auto result = O::solve(m); // Auto routes active globals to native Gecode.
```

| Helper | Original semantics |
| --- | --- |
| `add_all_different` | Every listed integer value differs. Empty/singleton lists are true; duplicate variable occurrences make a longer list infeasible. |
| `add_element` | `result == elements[index-index_base]`, with index constrained to the array range. Empty arrays are infeasible. Array duplicates and aliases with index/result retain their meaning. |
| `add_table` | The ordered variable tuple belongs to the listed allowed tuples. Arity is checked, duplicate tuples are harmless, and aliases must agree. No tuples is false; an allowed empty tuple is true. |
| `add_cumulative` | Fixed nonnegative durations and heights, nonnegative capacity, and integer start times. Each mandatory task uses its height on `[start,start+duration)`. Zero duration or height consumes no resource. Repeated starts describe simultaneous tasks. |
| `add_regular` | The signed integer word follows a deterministic transition table from the initial state to a final state. Missing transitions reject, repeated variables retain equality, and an empty word accepts exactly when its initial state is final. Sparse declared state IDs are compacted for native posting; see [Regular](REGULAR.md). |
| `add_circuit` | The nonempty successor array forms exactly one cycle through every node. An explicit index base supports negative or positive labels. A singleton points to itself; multiple disjoint cycles are infeasible. |

All referenced variables must have integer, binary or semi-integer type. The
public records use signed 64-bit symbols/constants restricted to the exactly
representable range ±2^53. The original-model checker rounds values only within
the requested integrality tolerance, then applies the discrete predicates.
Values outside that exact integer range are rejected by the global checker.
`ValidationReport::violated_globals` counts violated active records.

`Backend::Auto` selects the native bridge when any active global exists, and
HiGHS otherwise. Explicit HiGHS requests reject these models. A build without
native support reports Unsupported; it never drops a global or silently solves
only the linear relaxation. The native bridge still requires all active model
variables and linear data to fit its documented finite integer subset. Globals
do not add continuous-variable support. Persistent HiGHS sessions, the current
conflict oracle and LP/MPS export reject active globals explicitly.

The native compiler posts Gecode's existing domain-consistent distinct, element,
table and circuit propagators and cumulative resource propagation. Equal fresh
variables preserve aliases when a native propagator requires distinct variable
objects. Shifted index variables support arbitrary allowed index bases without
requiring a negative-offset native circuit call. Zero-resource tasks are removed
before posting cumulative, preserving the documented half-open semantics.
The original payload remains available for independent checking and ordered
objective workflows.

Native constants/array counts must fit Gecode's integer limits. Task end bounds,
individual and aggregate energy, and capacity × domain-width × task-count
products are checked before native cumulative posting. For positive-resource
tasks, let `B` be the largest absolute start/end bound, `E` total task energy,
`C` capacity, and `h` the smallest height. The conservative condition
`2*C*B + E <= Int::Limits::max*h` protects envelope sums, edge-finding
subtractions, divisions and the resulting integer casts. Task count squared
must also fit the native integer indexing range. Zero-resource tasks are ignored;
singleton tasks need only the direct height/capacity check. Pairwise-disjunctive
resource tasks use native unary propagation after an int64 comparison, avoiding
overflow in the cumulative implementation's sum of its two smallest heights.
Excessive ranges return Unsupported. These guards can reject large but otherwise
valid formulations; the model is never weakened to make posting succeed.
Every native candidate passes the separate original global
predicates with zero integrality tolerance before it can be accepted with an
Exact guarantee. Proof certificates are still unsupported.

`test/optimize/globals.cpp` enumerates complete finite products using separate
predicates and checks both the independent validator and native min/max optima.
It covers aliases, negative labels, zero/empty cases, circuit subtours, task
boundary semantics, lifecycle/identity, malformed payloads, large arithmetic,
unsupported numerical routes and preservation through ordered objectives.
These are the first typed globals in the registry. Optional/variable-duration
scheduling, cumulative variables, counting/packing globals and general native
reification remain work in W4. The owning [FlatZinc compiler](FLATZINC-COMPILER.md)
now preserves the documented forms of these six global families. Regular has
separate signed-word enumeration and C/Python [binding checks](REGULAR-BINDINGS.md).

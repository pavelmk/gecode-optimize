# Sparse deterministic regular constraints

`add_regular` retains an owning deterministic finite automaton and its ordered
integer word in the original optimization model. Native solving posts Gecode's
existing DFA propagator; the independent original-model checker walks the
original sparse transition function. It is an additional typed global, with no
change to default search or propagation settings.

```cpp
#include <gecode/optimize/globals.hpp>
#include <gecode/optimize/solve.hpp>
namespace O = Gecode::Optimize;
O::Model model;
auto x = model.add_integer(-1, 1);
auto y = model.add_integer(-1, 1);
// Accept (-1, 1) and (1, -1). State 0 is an ordinary initial state.
O::add_regular(model, {x, y}, 4, 0,
  {{0, -1, 1}, {0, 1, 2}, {1, 1, 3}, {2, -1, 3}}, {3}, "opposite");
model.minimize({{x, 1}});
O::SolveOptions options;
options.guarantee = O::Guarantee::Exact;
auto result = O::solve(model, options); // Auto selects Native for active globals.
```

## Original semantics and ownership

`RegularData` owns `variables`, `state_count`, `initial_state`, `transitions` and
`final_states`. `RegularTransition` contains `(from, symbol, to)`. State IDs use
`uint64_t`; the declared count must be positive and every referenced state must
be strictly below it. Symbols use `int64_t` within the exact public constant
range ±2^53. State labels are metadata, so they need not fit an integer variable
or a double. A declared count close to the uint64 limit needs no dense storage.

| Input | Meaning or admission |
| --- | --- |
| Missing `(state, symbol)` transition | Reject the word. |
| Duplicate `(from, symbol)` key | Reject the model, including identical duplicate edges. This interface describes a function, not an NFA. |
| Repeated final state | Harmless set duplication. |
| Empty word | Accepted exactly when the initial state is final. |
| Empty final set | No word is accepted. |
| Empty transition set | Only an empty word can be accepted. |
| Unreachable state, transition or final | Retained in the original record and checked structurally. |
| Repeated variable in the word | The repeated positions must take the same value. |
| Negative or zero symbol, state zero | Ordinary symbol/state values in this typed API. No reserved failure state. |

Every word variable must be a live, same-model Integer, Binary or SemiInteger
handle. The original record follows existing global names, revisions, removal
and tombstone rules. Failed addition leaves the model unchanged. An active
record prevents removal of any referenced variable; removing it releases those
guards. Changing a variable's bounds keeps the same automaton semantics.
Snapshots copy and own all automaton data. Publicly edited snapshots undergo
full structural checking, including malformed inactive records. Empty-word and
empty-language fast paths occur only after complete structural and native
admission.

The general numerical checker rounds only within its requested integrality
tolerance before evaluating the discrete original word. Native exact solving
and complete-start admission require integral values without rounding. A
candidate must satisfy every original row, domain, indicator and global before
publication. This adds no proof-certificate format; `Certified` stays unsupported.

## Native lowering and conservative storage limits

The compiler compacts only referenced state IDs, including the initial state
and finals. It creates its own transition and deduplicated-final arrays with
explicit native sentinels. Gecode `DFA(..., false)` normalizes the state layout
with optional minimization disabled. The native extensional propagator owns its
DFA data. Aliased word positions use equal fresh native variables, preserving
source equality while satisfying Gecode's distinct-variable-object requirement.
Space cloning retains ordinary native ownership; no pointer into temporary
transition buffers survives posting.

Alphabet symbols must fit `Gecode::Int::Limits`, even in unreachable transitions
or an empty word. The rest of the model still has to meet the bounded native
integer/linear arithmetic contract. Large exact public symbols can therefore
validate correctly yet return `Unsupported` when solving natively.

The private `native_regular_limits.hpp` preflights native allocation/index
arithmetic before creating a DFA or layered graph. Its conservative sufficient
conditions use word length `n`, referenced-state count `Q`, edge count `T`, and
distinct-symbol count `S`:

- `n`, `Q`, and `T` are below `INT_MAX`, with `Q > 0`, leaving room for count-plus-one arrays.
- `Q * (n + 1) <= INT_MAX`, protecting signed initialization/index products in the layered graph.
- `n * T <= UINT_MAX`, protecting aggregate layer-edge counts.
- `S < INT_MAX/2 + 1`, so the native hash table's next strictly larger power of two remains a positive signed shift.
- When every symbol fits `short`, `S <= USHRT_MAX`, protecting the short-valued graph's per-layer support count.

Products are checked by division, with overflow-sized input rejected before
multiplication. These are storage-safety bounds, not a claim that such large
models fit available memory. Allocation failure still returns `MemoryLimit`.
Compaction loops share the outer solve deadline/cancellation checks; DFA
construction and propagation are cooperative native calls, with checkpoints
before and after them. There is no hard wall-clock interruption inside those
calls and no added probing or solver work hidden outside the existing budget.

The conditions follow the implementation in
[`dfa.cpp`](../../gecode/int/extensional/dfa.cpp),
[`dfa.hpp`](../../gecode/int/extensional/dfa.hpp), and
[`layered-graph.hpp`](../../gecode/int/extensional/layered-graph.hpp), not an
assumed external automaton representation. The private helper is not an
installed API.

## Routes and validation evidence

Ordinary Native/BAB, NativeLP, and both frontier orders enforce the native
Regular propagator and the original checker. NativeLP omits the global from its
linear relaxation, while retaining it in the full native model and checking all
incumbents. Thus an LP bound alone cannot establish original feasibility.
Complete starts, interrupted bounds, tombstones, min/max offsets and native
clones keep their existing contracts.

Explicit HiGHS, persistent HiGHS sessions, current conflict extraction, exact
linear presolve, feasibility relaxation, and LP/MPS export reject active Regular
records. They never drop the language constraint. Export rejection happens
before replacing the destination. A backend-free build still supports
construction and independent validation and reports unsupported native solving.

`test/optimize/regular.cpp` independently generates accepted words by following
all labeled paths, then enumerates the complete product of each tiny original
variable domain. It compares that language with checker results and solver
optima, including all partial two-state transition functions over `{-1,1}`,
initial/final combinations and word lengths zero through three. Additional
cases cover repeated handles, semis, duplicate finals, huge sparse state IDs,
unreachable data, signed objective costs and offsets, complete and invalid
starts, all small frontier node quotas, concurrent solves, lifecycle/history,
mutated payloads, unsupported routes and atomic export rejection. Pure boundary
cases test each native arithmetic condition and one value beyond it without
allocating enormous graphs; an actual 65,536-symbol short alphabet exercises
the production support-count guard.

The existing native-start, frontier, branching and globals oracles also compile
against the enlarged variant; their independent predicate visitors explicitly
handle Regular. All optimization facade objects must be rebuilt when adding
this variant alternative. Borrowing an old facade archive would violate the
C++ object layout; only matching native/HiGHS foundation libraries may be reused.

The separate source compiler now admits the six-argument FlatZinc spelling; the local
[`fzn_regular.mzn`](../../gecode/flatzinc/mznlib/fzn_regular.mzn) declares
`gecode_regular(x,Q,S,d,q0,F)`. Its state labels and symbols start at one, and
transition target zero means failure, as described by the official
[MiniZinc regular documentation](https://docs.minizinc.dev/en/2.3.2/predicates.html).
These source conventions must be translated explicitly; they are not the
zero-based typed API's semantics. Regex/NFA interfaces, reified regular,
set-valued regular and new automatic portfolio policies remain outside this
slice.

The isolated implementation gate passed the combined native/HiGHS and
backend-free builds (5/5 tests each), and ASan+UBSan with every facade source and
both native/HiGHS foundations instrumented (5/5, no suppressions). The Regular
oracle checked 2,619 configurations and 25,985 original assignments; the
combined run performed 263 native-route solves, including interrupted solves.
Assertions were enabled throughout. These are correctness gates, not timings
or evidence of a performance benefit. The sanitizer runtime used
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1` and
`UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`.

The FlatZinc compiler's independent path-language oracle adds every two-state
transition matrix over symbols `1..2`, every initial/final combination, and word
lengths zero through three, with domains also containing rejected symbols 0
and 3. It covers raw aliases/literals, zero transitions, empty/duplicate/interval
finals, malformed and nonliteral parameters, exact product overflow, payload
limits, cancellation, history, and combinations with table, reification and
linear objective mapping. Its source checker uses the original row-major table
rather than the typed sparse automaton. Actual parser/CLI integration belongs
to the separate CLI gate; these tests construct authoritative capture records.

The subsequent source-compiler gate passed 5,992 configurations and 303,429
original assignments with Native+HiGHS, native-only, and fully instrumented
Native+HiGHS ASan/UBSan. The backend-free compiler gate passed 5,990
configurations with the same assignment count (two native-dependent setup cases
are absent). The typed Regular oracle remained green after compiler integration.

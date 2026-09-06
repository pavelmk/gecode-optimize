# Explicit FlatZinc source-record compiler

The first C++ compiler slice admits finite integer/Boolean declaration domains,
declaration aliases, interval and finite-set membership (including holes), signed integer
comparisons, integer plus/minus, sparse linear equalities/inequalities, Boolean
linear equality with variable integer RHS, bool2int, Boolean equality/order/not,
AND/OR (including arrays), and clauses. It also admits integer `<=` reification,
integer `<=`/equality implication, AllDifferent, 1-based integer Element and
positive-arity `gecode_table_int`, explicit-offset `gecode_circuit`, and the
four-argument fixed-data `gecode_cumulatives`/`cumulatives` interface, and
six-argument deterministic `gecode_regular`.
It retains satisfaction versus min/max
and the actual integer variable or literal objective. The separate opt-in `fzn-gecode-optimize` driver uses this compiler; the existing
`fzn-gecode` path is unchanged.

```cpp
#include <gecode/optimize.hh>

// records is a complete FlatZinc::Capture::Records from the opt-in parser.
auto compiled = Gecode::Optimize::compile_flatzinc(records);
if (compiled.compiled) {
  Gecode::Optimize::SolveOptions options;
  options.backend = Gecode::Optimize::Backend::Native;
  options.guarantee = Gecode::Optimize::Guarantee::Exact;
  auto result = Gecode::Optimize::solve(compiled.compiled->model(), options);
  auto checked = Gecode::Optimize::validate_flatzinc(*compiled.compiled, result);
}
```

Compilation uses the complete **raw** declaration/domain/predicate records.
The parser's normalized alias state and coverage entries are retained for audit
but never replace a source predicate. A removed equality therefore cannot be
lost through an incomplete registry observer. Each source namespace/index maps
to a stable model variable; repeated declaration aliases retain separate source
mapping entries and output positions. Bool and int slot zero are different.

An immutable owning artifact is published only after every source predicate,
objective, control annotation and output entry is admitted. Unknown predicates,
equality reification, other globals, float/set variables and unhandled
search controls are explicitly Unsupported in this first slice. These limits
apply even when a construct appears redundant or an ordinary native poster
supports it. No solver is called during compilation, and no partial model is
returned on rejection.

The additional predicate names are `int_le_reif`, `int_lin_le_reif`,
`int_le_imp`, `int_lin_le_imp`, `int_eq_imp`, `all_different_int`,
`array_int_element`, `array_var_int_element`, `gecode_table_int` and
`gecode_circuit`, `gecode_cumulatives`, `cumulatives` and `gecode_regular`. Linear coefficients and RHS are
integer parameters; operands may be integer references or literals. The last
argument of a reified/implication predicate is Boolean. Full `<=` reification
posts both implications: guard true enforces `sum <= k`, guard false enforces
`sum >= k+1`. The complement and constant substitution use checked integer
arithmetic and exact model-number conversion. An `_imp` predicate imposes only
the true-guard implication. Literal or fixed guards are simplified only after
operand/type admission. Equality reification remains Unsupported.

Guarded relations retain the existing indicator's original logical metadata;
its finite-domain M is conservatively derived, never guessed. Native solving
uses the retained original integer implication. Numerical backends use the
safe linear formulation, followed by the independent original-source check.
Private indicator gates are not source variables or output entries.

AllDifferent preserves every occurrence, including aliases and repeated
literals; duplicates can make it infeasible. Integer Element uses precisely
the source array order and indices `1..size`; an empty array or out-of-range
index is infeasible. `array_int_element` requires a parameter integer array;
`array_var_int_element` admits integer references and literals. This follows the
[FlatZinc integer signatures](https://docs.minizinc.dev/en/latest/lib-flatzinc-int.html),
even though the existing native registry shares a permissive poster for the two
names. Boolean Element, offset/2-D Element and other global predicates remain
Unsupported. Literal global operands receive private fixed integer slots, with
equal literals sharing a slot while occurrences remain present in the global.
Empty AllDifferent is true. Globals remain typed global metadata: explicit
HiGHS solving rejects the full compiled model rather than dropping them;
Native/Auto can use the native global propagators within their supported domain.

`gecode_table_int` takes an array of integer references/literals and a flat
parameter-integer relation in row-major order. The operand arity must be positive
and divide the cell count exactly. A positive-arity empty relation is false.
Repeated rows, repeated variables, aliases and fixed operands retain their source
meaning. Variable or Boolean relation cells are InvalidInput. A zero-arity empty
flat relation is Unsupported because flattening has lost the distinction between
zero tuples and one empty tuple; a zero-arity relation containing cells is
InvalidInput. Other names, including `table_int`, `fzn_table_int` and Boolean-table
variants, are not inferred aliases. This whitelist follows this repository's
`gecode_table_int` MiniZinc declaration and registry entry; see the pinned-source
[signature design](FLATZINC-GLOBALS-DESIGN.md).

`gecode_circuit(offset, successors)` requires a nonnegative integer literal
offset and a nonempty array of integer references or literals. Nodes are the
source positions `offset..offset+size-1`; successors must form one cycle visiting
every node. A singleton is true exactly when its value equals the offset. A
self-loop in a larger array, a subtour or an out-of-range successor is false.
Every position remains present, including repeated handles, declaration aliases
and fixed literals; the compiler does not deduplicate nodes or infer an offset
from output-array dimensions. It posts typed `CircuitData` and retains the raw
predicate for a separate source-order cycle check.

The index endpoint is checked before posting and must remain within the exact
model-number range. Negative offsets are Unsupported for this explicitly scoped
low-level signature; the bundled high-level MiniZinc wrapper shifts negative
index sets before emitting it. Wrong types/arity and an empty successor array
are InvalidInput. Unprefixed, double-prefixed, wrapper, reified, cost-circuit and
subcircuit names are not inferred aliases. This follows the bundled registry's
two-argument `gecode_circuit` entry; generic typed Model circuit capabilities do
not widen that FlatZinc signature. Large exact offsets can compile while Native
range preflight returns Unsupported. Explicit HiGHS rejects the retained global.

Exactly four arguments to `gecode_cumulatives(starts, durations, heights, capacity)`
or the legacy spelling `cumulatives` denote one resource with fixed task data.
The three integer arrays must have equal lengths. Starts may be integer
references or literals. Every duration, height and capacity must be an integer
literal or have a nonempty singleton domain established by original declarations,
assigned values and raw domain intersections on its alias representative. The
compiler does not propagate ordinary equality rows, fix an unfixed parameter to
its lower bound, or infer a parameter from an empty domain's dummy model slot.
Referenced fixed parameters keep their source mappings and original checks;
only literal starts may create private fixed slots.

Durations and heights must be nonnegative (negative values are InvalidInput).
Negative capacity and nonfixed parameters are Unsupported in this slice. Task
usage is `start <= time < start+duration`, so zero duration or zero height uses no
capacity and equal end/start times do not overlap. Repeated/aliased starts still
describe separate tasks whose demands add. An empty schedule with nonnegative
capacity is true; a positive-duration task above capacity is infeasible.
The original checker reads parameter values from the raw source, builds checked
integer endpoints and processes ending demands before starting demands at each
time. It does not reuse the embedded `CumulativeData` constants as source proof.

The bundled legacy four-argument poster has a known singleton shortcut imposing
`height <= capacity` even at zero duration. Thus `durations=[0], heights=[2],
capacity=1` is feasible under the implemented half-open semantics but rejected by
that old shortcut. This specific disagreement is tested and is not treated as a
reason to weaken the independent source oracle. See the scheduling evidence in
[FLATZINC-GLOBALS-DESIGN.md](FLATZINC-GLOBALS-DESIGN.md).

Six- and seven-argument calls remain explicitly Unsupported: their machine arrays,
per-machine bounds and upper/lower resource rules are distinct semantics. Other
arities of the two selected names are InvalidInput. `fzn_cumulative`,
`fzn_cumulatives`, optional scheduling and guessed prefix aliases remain
Unsupported. Actual native solving retains its additional endpoint, energy and
propagation arithmetic guards; exact source representability does not imply
native support. No scheduling constraint is silently dropped for HiGHS.

Exactly six arguments to `gecode_regular(word, Q, S, d, q0, F)` describe a
deterministic finite automaton. This explicit compiler requires positive `Q`
and `S`, an integer-literal initial state in `1..Q`, exactly `Q*S` literal
integer transition cells in row-major order, and a literal integer final-state
set contained in `1..Q`. Every target must be in `0..Q`; target zero means
failure. Word operands are integer references or literals and must take values
in `1..S` to be accepted. The signature and ordering follow this repository's
[`fzn_regular.mzn`](../../gecode/flatzinc/mznlib/fzn_regular.mzn) and registry;
the state/symbol convention follows the official
[MiniZinc regular documentation](https://docs.minizinc.dev/en/stable/lib-globals-extensional.html#regular).

The compiler subtracts one from positive state IDs while retaining symbol
labels, and omits zero-target edges. This produces the typed sparse
`RegularData`; state zero in that typed API is an ordinary state, so the source
failure state must never be copied as a usable transition. The separate
original-source checker walks the retained raw row-major table with checked
index arithmetic, rejects input symbols outside `1..S`, and treats a zero
target as rejection. It does not use the compiled sparse transition record as
evidence. Empty words are accepted exactly when `q0` belongs to `F`, including
when every table cell is zero; an empty final set rejects every word. Duplicate
finals are harmless. Repeated operands, declaration aliases and private literal
slots retain every source position.

All automaton parameters must be primitive captured literals/set data. A
reference with a singleton original domain is still InvalidInput in these
parameter positions; ordinary propagation and alias domains never infer a DFA.
Wrong arity/type, nonpositive counts, out-of-range states/targets and incorrect
matrix cell counts are InvalidInput. Integer/product representability failure
is Unsupported. `regular`, `fzn_regular`, `gecode_regular_set`, regex/NFA,
reified and guessed prefix variants remain Unsupported. These admission checks
also apply to an empty word and after an earlier contradiction.

Checked work/storage admission precedes sparse-payload allocation and expansion
of interval final sets. Payload accounting charges three scalar parameters,
word positions, original table cells, three cells per retained nonzero edge,
and every expanded final-state entry. Private fixed word variables use the
existing variable limit. Time/cancellation and work exhaustion publish no
partial artifact. The native bridge's additional alphabet/count/layer safety
limits remain separate from exact source representability. Explicit HiGHS
rejects the resulting global; Native and Auto retain whole-model checking.
See [REGULAR.md](REGULAR.md) for typed ownership, backend limits and tests.

Finite domain lists are normalized privately, preserving the raw lists for
checking and history. Declaration domains and every raw `int_in` restriction are
intersected on the declaration-alias representative. Intervals stay symbolic: a
sparse set spanning ±2^53 does not trigger interval enumeration. Lists are sorted
and deduplicated with metered work, intersected exactly, then filtered by interval
bounds. A contiguous result becomes bounds alone; a remaining holey result gets
its exact hull plus one unary typed table. An empty result produces an explicit
contradictory row. Raw literal `int_in` remains a checked constant predicate.
This also admits finite-set restrictions that supply bounds for otherwise
unbounded declarations. Boolean intrinsic bounds remain `0..1`. Output-array
index sets retain their separate contiguous-index requirement.

A retained unary domain table has the same backend boundary as other globals:
explicit HiGHS returns Unsupported. If intersection removes every hole, the
ordinary linear model can still use HiGHS. Native domain/activity limits apply
independently of frontend representability; compilation alone does not promise
that every admitted model can be solved by every backend.

Integer arithmetic uses checked int64 operations and exact conversion to model
doubles (integers within ±2^53). Declared aliases use cycle checking and path
compression. Signed constants and duplicated variable coefficients are combined
before posting. Domain contradictions become explicit contradictory rows rather
than invalid bound pairs. Integer variables must have finite explicit bounds
after declaration aliases and membership restrictions; no artificial large bounds
are supplied. Backend-specific activity limits may still reject a compiled model.
Arithmetic that cannot be checked safely is Unsupported, or a failed source
witness check if encountered during checking.

`FlatZincCompileOptions` bounds source and generated variables/rows, generated
nonzeros, value depth and structural work. It supports a monotonic deadline and
cancellation token. Work counts visited records, operands, copied data and alias
traversals; it is not a CPU-cycle bound. Parsing is a separate operation with its
own input limits. Allocation, standard-container operations and source copying
are cooperative; compilation checks the deadline again before publication.
Invalid input, Unsupported, resource exhaustion, cancellation and deadline have
distinct frontend outcomes. None is an infeasibility proof.
Generated-variable limits include private gates/fixed literal slots. Global
operand occurrences count against the nonzero/work budget, and each global counts
as a generated constraint. Table operands plus every relation cell, including
duplicate rows, count as nonzeros; a unary domain table counts its operand and
remaining members. Each input domain list is also capped by `max_nonzeros` before
normalization/copying, so even a large duplicate-only list can be rejected.
Circuit successor occurrences count as nonzeros, including repeats; one circuit
counts as a generated constraint and fixed literals count as private variables.
Cumulative counts all three arrays plus its scalar (`3*task_count+1`) as payload
cells, one generated constraint, and any private literal start slots. Count and
work admission precede payload allocation; the original checker reserves at most
two events per task. Its public interface has no cancellation/deadline argument,
so callers can checkpoint around validation but not interrupt the event sweep.
Sorting comparisons, intersection scans and table rows/cells consume `max_work`;
limits are reserved before the corresponding private payload allocation. No
interval width is charged or enumerated. These are structural limits, not byte
or elapsed-time guarantees. Indicator posting reserves a conservative maximum
footprint before the transactional helper allocates, then charges the actual
generated rows/gates; a tight cap can reject an operation whose eventual simplified
form would be smaller. No partial artifact is published.

`validate_flatzinc` checks result identity/revision, the complete active mask,
every compiled model slot, and tolerance-qualified integer rounding. It then
checks every original declared domain/alias/fixed value and every raw predicate
with independent integer operations, and recomputes the original objective.
Reification/implication is evaluated directly as source Boolean logic;
AllDifferent compares source values, Element indexes the source array, Table
compares directly with original flat rows, Circuit walks raw source successors
from source node zero through every node, and domain membership reads the raw
interval/list. The evaluator does not read a generated global to establish source
truth.
These checks never infer source truth from generated rows or helper values.
This exact check of a rounded point does not upgrade a numerical solver bound or
its overall guarantee. Results remain usable after parser/input destruction or
later changes to the caller's source records.

`format_flatzinc_solution` buffers output only after that full witness check.
Integer/Boolean scalars, repeated array values, and checked arrayNd dimensions
are reconstructed from typed records; arbitrary legacy string fragments are not
executed or copied as formatting instructions. The result contains assignments
and `----------`, never an optimality/enumeration marker. The separate driver must
apply the distinct satisfaction/optimization/interruption status contract.
Requested output annotations must have a corresponding captured output entry.

The compiler has no FlatZinc parser, Space, registry or HiGHS linkage dependency.
It builds in the backend-free optimization component. The installed `capture-records.hh` uses only standard C++ types. The separate
`capture.hh` parser API requires the native FlatZinc component and its matching
configuration headers; the standalone optimization library does not provide it. Parser capture and the opt-in file driver are separate integration components.

The backend-free suite covers 3,308 source configurations and 248,201 independent
assignments; the Native/HiGHS build adds two native-only configurations. It
compares original-source and generated-model feasible sets, both senses and
constant objectives, aliases/conflicting domains, all admitted Boolean forms,
malformed/unknown records, resource/time/cancellation limits, identity/masks,
owned history and complete output. Actual Native and HiGHS solves are checked
against tiny independently known optima. Normal backend-free, Native/HiGHS and
fully instrumented native/HiGHS ASan+UBSan runs pass (LeakSanitizer is unavailable
on this macOS configuration). See `test/optimize/flatzinc.cpp`.

The independent oracle existentially enumerates every generated helper slot for
each original source assignment; it never assumes private gates are zero. Table
tests enumerate every relation on binary operands of arities one through three,
with perturbed tuple order and duplicates. Domain tests exhaust all 1,024 pairs
of subsets of a signed five-element universe. Additional tests cover alias chains,
assigned conflicts, empty lists/relations, literal-only tables, raw source history,
±2^53 sparse gaps, contiguity after intersection, invalid relation shapes/types,
zero-arity rejection, and exact work/cell/variable/constraint caps without partial
artifacts. Min/max native solves combine tables, holes, reification, AllDifferent
and Element; explicit HiGHS rejection and missing-backend contracts are checked.
The older reification/global regressions retain their negative coefficients,
strict complements, empty/repeated/aliased operands, out-of-range Element indices,
and corrupted-helper checks. Source mapping/output contains only original
variables. Pre-cancel and zero-deadline cases test interruption admission; there is
no timing-sensitive mid-normalization cancellation test.

Circuit tests independently generate Hamiltonian cycles from permutations and
compare them against every successor assignment for sizes 1–5 and offsets 0, 1
and 3, including values just outside the legal range. They cover singleton
cycles, subtours/self-loops, aliases, repeated operands, literal-only circuits,
wrong signatures/namespaces, endpoint overflow, exact-range compilation versus
Native range rejection, and precise work/cell/variable/constraint caps. Min/max
fixtures combine Circuit with Table, holey domains, reification, AllDifferent and
Element, preserving shifted original objectives. Normal backend-free and
Native/HiGHS checks pass, as does the complete Native/HiGHS source sanitizer
configuration. These are correctness gates; no performance gain is claimed.

Cumulative tests enumerate bounded starts for sizes 0–4 against a direct
integer-time usage oracle, exhaust all duration/height combinations in `{0,1,2}`
through two tasks, and cover both selected spellings. They include touching
endpoints, negative/coincident/aliased starts, zero duration/demand/capacity,
original singleton parameter aliases and assigned values, exact set intersections,
empty-domain and ordinary-equality non-inference, and preserved source outputs.
Separate min/max cases combine scheduling with Table, holes, reification,
AllDifferent and Element. Arithmetic fixtures distinguish source admission from
the existing Native endpoint/energy envelope. Resource boundaries reserve exactly
`3*n+1` cells; wrong 4/6/7 signatures retain distinct outcomes.

The actual bundled `fzn-gecode` executable reported `UNSATISFIABLE` on the
zero-duration singleton fixture described above. The new compiler's native path
accepts it, and the independent half-open oracle verifies its feasibility.
Normal backend-free/Native+HiGHS and full-source ASan+UBSan checks cover these
extensions; parser/CLI registration and integration fixtures are separate gates.

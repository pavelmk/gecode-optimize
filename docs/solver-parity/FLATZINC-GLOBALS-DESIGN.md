# FlatZinc tables, circuits, fixed cumulative tasks and finite holey domains

Design written 2026-09-05. Original source baseline:
`8ae59d5c1946abf47203172ba3cb89fbf5ea0a8b`. The table/finite-domain,
explicit-offset circuit and four-argument fixed cumulative slices below are now
implemented with separate independent correctness gates. No parser, native solver
or public model changes were needed for these compiler extensions. Current implemented admission
is described in [FLATZINC-COMPILER.md](FLATZINC-COMPILER.md).

## Recommended next slice

Reuse the existing typed `TableData`, `CircuitData` and `CumulativeData`; extend
only the owning FlatZinc compiler and independent original-source evaluator.
Keep the original raw predicates/domains and source-slot mapping intact. Publish
an artifact only when every predicate is admitted and all resource checks pass.
Do not use a broad `gecode_`/`fzn_` prefix-stripping rule.

Implement in this order:

1. Positive-arity integer tables and finite enumerated integer domains. A unary
   typed table represents holes without new selector variables or an exponential
   conversion to inequalities. Preserve intervals symbolically.
2. The explicit-offset `gecode_circuit(offset, successors)` predicate, initially
   nonempty and with nonnegative literal offset. Preserve repeated source terms.
3. Four-argument fixed-data `gecode_cumulatives` and the explicitly selected
   legacy spelling `cumulatives`; durations, heights and capacity must be integer
   literals or original declaration/domain values already proved singleton.
   Use documented half-open cumulative semantics, including zero-duration tasks.

Keep reified tables, Boolean/optional tables, subcircuits, cost circuits,
six-/seven-argument multi-machine scheduling, optional tasks, variable scheduling
parameters, and unbounded integer variables explicitly unsupported. Table and
holey-domain admission should land and pass its independent oracle before adding
scheduling. No backend defaults or existing workflow policy changes are needed.

## Evidence and version boundary

The authoritative implementation vocabulary is this repository's bundled Gecode
MiniZinc library and registry at the source baseline above. Relevant local sources:

- `gecode/flatzinc/mznlib/fzn_table_int.mzn:35`: a two-dimensional MiniZinc table
  wrapper calls `gecode_table_int(x, array1d(t))`.
- `gecode/flatzinc/mznlib/fzn_circuit.mzn:35`: explicit-offset low-level circuit;
  the MiniZinc wrapper supplies its actual index-set minimum, shifting values when
  that minimum is negative.
- `gecode/flatzinc/mznlib/fzn_cumulative.mzn:35` and `fzn_cumulatives.mzn:1`:
  distinct four-argument single-resource and six-/seven-argument multi-machine
  interfaces, despite overlapping names.
- `gecode/flatzinc/registry.cpp:69`, `:1269`, `:1333`, `:1543`, `:1915`:
  actual registration, shape dispatch, alias unsharing and native calls.
- `gecode/flatzinc/flatzinc.cpp:2396`: flattened table reconstruction.
- `gecode/optimize/globals.cpp:58`, `:99`: typed payload validation and independent
  integer predicates; `gecode/optimize/native.cpp:165`, `:485`: native numeric
  admission, protected zero/singleton cases and lowering.

External primary references were read on 2026-09-05. The stable Handbook scheduling,
Table and Circuit pages reported **2.10.1**; the FlatZinc specification and Gecode
index still reported **2.10.0**. Stable URLs are rolling documentation, so these are
observed page versions, not a claim that every solver-specific declaration belongs
to a downloaded 2.10.1 source distribution. Release-tag raw source URLs were not
retrievable in this research session. Pin the exact MiniZinc binary, bundled solver
library path/version and generated `.fzn` fixture hash before integration tests.
Do not label a mutable `master` source as a release-pinned specification.

- [FlatZinc specification](https://docs.minizinc.dev/en/stable/fzn-spec.html):
  parameter/variable distinction, finite set literals, aliases and source-order
  one-dimensional arrays. It does not turn arbitrary similarly named globals into
  equivalent predicates.
- [Table semantics](https://docs.minizinc.dev/en/stable/lib-globals-extensional.html#table):
  the assigned vector must match a row of the parameter relation; Boolean,
  integer and optional variants are distinct.
- [Circuit semantics](https://docs.minizinc.dev/en/stable/lib-globals-graph.html#circuit):
  values denote successor node indices; optional variants have different
  participation semantics.
- [Scheduling semantics](https://docs.minizinc.dev/en/stable/lib-globals-scheduling.html#cumulative):
  ordinary cumulative uses nonnegative durations/resources; multi-machine
  cumulatives also admits production and resource lower bounds, so it is not the
  same constraint.
- [Current standard cumulative decomposition](https://raw.githubusercontent.com/MiniZinc/libminizinc/master/share/minizinc/std/fzn_cumulative.mzn)
  explicitly tests `start <= time < start + duration` and excludes zero-duration
  activity. This mutable source corroborates the half-open convention.
- [Current high-level cumulative wrapper](https://raw.githubusercontent.com/MiniZinc/libminizinc/master/share/minizinc/std/cumulative.mzn)
  guards an individual resource requirement with zero duration. It checks matching
  array index sets before flattening. Do not infer original index-set identity
  from array lengths when capture no longer retains those dimensions.

## Exact admission table

`VI` below means a flat array of integer literals or integer variable references;
`PI` means a flat parameter array of integer literals. Booleans do not become
integer literals merely because the target Model also supports Binary variables.
Captured parameter references have already been expanded by the parser.

| Source predicate/form | Verified contract | Initial compiler response |
|---|---|---|
| `gecode_table_int(VI x, PI t)` | Two arguments; `t` is row-major flat storage, tuple arity is `len(x)` | Admit `len(x)>0`, `len(t)%len(x)==0`; materialize typed tuples after checked count admission |
| `gecode_table_int([], [])` | No tuple-count field remains after flattening | Explicit `Unsupported` initially; do not manufacture an empty tuple |
| `gecode_table_int([], nonempty)` | Cannot form a tuple of zero arity | `InvalidInput`, before division/indexing |
| `table_int`, `fzn_table_int`, `fzn_gecode_table_int`, `gecode_gecode_table_int` | Prefix aliases are not a general interface contract; MiniZinc `fzn_table_int` has a 2-D argument | Keep unsupported until an exact separate signature is documented; do not strip prefixes |
| Table Boolean, reified, implication or optional forms | Different argument types or truth/occurrence semantics | Unsupported in this slice |
| `gecode_circuit(PI scalar offset, VI successors)` | Literal offset first, successor array second | Admit nonempty array and nonnegative offset within the exact source range; check native range when solving |
| `fzn_circuit(successors)` | MiniZinc wrapper derives the original array index minimum | Unsupported as a direct low-level capture form without an explicit preserved index contract |
| Cost circuit and subcircuit names | Cost channels or permitted excluded/self-loop nodes change semantics | Unsupported |
| `gecode_cumulatives(VI s, VI d, VI r, int-or-var-int b)` | Four-argument single-resource poster | Admit equal array lengths, nonnegative fixed `d`, `r`, `b`; preserve source references used as fixed data |
| `cumulatives(s,d,r,b)` | Verified legacy alias of that same four-argument poster | Admit only exact four-argument shape under the same fixed-data contract |
| `gecode_cumulatives(s,d,r,m,PI bounds,bool upper)` | Six arguments: machine decisions and per-machine bounds, allowing different resource semantics | Unsupported, never truncate to four arguments |
| `fzn_cumulatives(s,d,r,m,b,upper,min_m)` | Bundled MiniZinc wrapper has seven arguments and shifts machine indices | Unsupported; not equivalent to the registry's synthetic `fzn_cumulatives` alias |
| `gecode_schedule_cumulative_optional` | Presence array and different five-argument order | Unsupported |
| Declared `var {v1,...,vk}` and existing `int_in(x, set)` | Exact finite-set membership | Admit bounded normalized finite membership, retaining all holes |
| `set_in(int x, parameter set)` | Standard integer membership spelling, overloaded locally with set-variable posting | Optional explicit spelling only for an integer operand and literal set; never admit set-variable membership or reification by name alone |

`Registry::add(id,p)` registers `id`, `gecode_+id` and `fzn_+id`. For an already
prefixed name it even produces double-prefixed names. Thus `gecode_table_int` and
`gecode_circuit` registrations do **not** establish unprefixed `table_int` or
`circuit`. The scheduling registration `cumulatives` creates three spellings, but
its six-argument branch and the separate seven-argument MiniZinc wrapper still
need different contracts. A literal whitelist is safer and more reviewable.

Malformed shape/type/arity for a specifically admitted interface is `InvalidInput`.
A known but unsupported overload or data class is `Unsupported`. Resource caps
produce `ResourceLimit`; cancellation/time limits keep their own statuses. Do not
label unsupported domains or arithmetic overflow as an infeasible model.

## Tables and information preservation

For arity `n>0`, evaluate a table by testing whether any **complete original row**
`tuple[j] == source_value(x[j])` holds for every column. The original evaluator must
read the original flat relation, not ask `Detail::global_satisfied` about generated
metadata. This provides an independent check on row reconstruction and mapping.

Reject noninteger tuple entries, nested arrays, wrong namespaces, and remainder
cells before posting. Duplicated tuples are harmless. Repeated variables are
positional equality requirements: `[x,x]` with only tuple `[0,1]` is infeasible;
`[0,0]` is feasible at `x=0`. Do not deduplicate argument positions or silently
replace repeated source variables with independent decisions. Fixed literals in
`x` use the compiler's private fixed-slot cache and never appear as source outputs.

An empty relation with positive arity is exact false; post a typed empty table or
an explicit false row. Every input still passes type and resource admission before
constant folding. Compilation `Complete` means faithfully represented, not SAT.

Zero arity needs a deliberate representation boundary. `TableData({}, {})` is
false and `TableData({}, {{}})` is true. A flattened `[]` loses this distinction.
The current `arg2tupleset` chooses zero tuples when its flat input is empty, and
otherwise divides by arity; it also silently floors a nondivisible cell count.
Those implementation shortcuts are not a sufficient contract for reconstructing
an arbitrary MiniZinc 2-D relation. Initial rejection avoids both invented truth
and division by zero. A future counted-table predicate or retained original 2-D
shape can support both zero-arity cases; that change requires its own parser and
source-evaluator contract, not a guessed row count.

## Finite domains with holes

Replace the compiler's interval-only declaration accumulator with a bounded
intersection representation: optional lower/upper limits plus, when present, a
sorted unique vector of allowed integers. Do not enumerate a large interval.
Intersect listed values with intervals and other listed sets, processing every
original restriction on its declaration-alias representative. A finite member
list can establish finite bounds for an otherwise `var int` representative.
Clipping a list must not turn it into its hull unless every hull value is present.

Validate every original listed integer with the compiler's exact representation
check before sorting/deduplicating. Normalize once per restriction, charge input
cells, sort/merge work and stored allowed values. Use a metered deterministic sort
or conservative precharged comparison budget with a checkpoint around the sort;
a library sort is not a hard cancellation-latency guarantee. Avoid multiplying
large counts before checking storage/work ceilings.

After intersection:

- Empty domain: keep the existing safe dummy variable plus an exact contradiction;
  preserve source slots and complete the remaining input admission.
- Singleton or contiguous domain: use exact bounds alone.
- Noncontiguous finite set: create its hull variable and a unary `TableData` with
  one row per allowed value. No selector/helper variables are necessary.
- Still unbounded: return `Unsupported`; no implicit native integer-limit domain.

Declared aliases may carry restrictions through synthesized raw-domain rows;
collect those before posting. Ordinary `int_eq` rows remain original constraints,
even if normalized parser records mark an alias equality. Do not use normalized
records to discard raw membership predicates. The existing source evaluator's
literal-set membership already supports holes; retain it independently of the
lowered unary tables. Original Boolean declaration domains remain intersected with
`{0,1}`; do not generalize Boolean-to-int predicate coercion beyond the existing
captured/synthesized domain contract.

## Circuit contract

For `n>0` and offset `o`, legal successors lie in `[o,o+n-1]`. Starting from node
position zero, visit exactly `n` previously unvisited positions and require the
next position to be zero. Out-of-range values, a premature repeated node, multiple
cycles, or an unvisited node make the original predicate false. A singleton is
feasible exactly when its sole successor equals `o`. A self-loop for `n>1` cannot
satisfy a full circuit. This is not a subcircuit or merely AllDifferent.

Evaluate the original successor array in source order, including aliased or
literal terms. Bound-check before subtracting offset or indexing. `o+n-1`, the
normalizing shifts and all source arithmetic use checked integer operations.
Initial `gecode_circuit` admission rejects negative offsets because its bundled
native low-level interface explicitly requires nonnegative offset. The generic
typed Model supports negative bases by safe normalization; admitting that broader
class under the low-level predicate's name should be a separate documented choice.
The high-level bundled wrapper shifts negative index sets before emitting a
nonnegative low-level offset. Do not infer a base of one from output dimensions.

Repeated handles are retained; the native bridge has its own equality-preserving
argument preparation. Neither deduplication nor accidental independent clones may
change the solution set. An empty successor array is `InvalidInput` for the admitted low-level signature,
never vacuously a solved circuit.

## Fixed cumulative contract and known legacy disagreement

All `s`, `d` and `r` arrays have equal lengths. Each `d[i]`, `r[i]`, and `b` must
be a literal or resolve to a singleton from original declarations and exact domain
intersections. Do not run a solver to discover whether they happen to be fixed.
Their referenced source variables remain mapped and independently checked. Fixed
negative durations/heights violate the declared assumptions and are `InvalidInput`.
Negative capacity is `Unsupported` in this initial typed-global scope, including
empty schedules where another high-level convention might be vacuous. Nonfixed
parameters are unsupported, rather than copied from a current lower bound.

Task `i` contributes `r[i]` precisely when `s[i] <= t < s[i]+d[i]`.
Zero duration or zero resource contributes nothing. Equal end/start times do not
overlap. Repeated start handles still describe separate tasks, so demands add;
identical tasks are not deduplicated. For the source evaluator, compute checked
integer endpoints, sort/group events at equal time, remove ending demands and add
starting demands before checking the interval following that time. An alternative
independent tiny-instance oracle checks all integer times in the bounded test
horizon; integer endpoints make that exhaustive for continuous time as well.

The old four-argument `p_cumulatives` has a singleton shortcut imposing
`height[0] <= bound` without checking zero duration. For `d=[0], r=[2], b=1`, it
rejects an assignment that the standard half-open predicate and current typed
`CumulativeData` accept. The improved compiler should use the intended documented
predicate, record this specific legacy disagreement in tests, and avoid treating
the old executable as the sole oracle. This is a semantic bug fixture, not a
performance comparison or permission to ignore other discrepancies.

For nonnegative capacity, an empty schedule is true. A positive-duration task
whose height exceeds capacity makes the model infeasible regardless of start.
Do not replace cumulative with AllDifferent or unary scheduling merely because
some heights are large; the native adapter already implements guarded choices.

## Resource, backend and proof boundaries

Keep current public compiler signatures unchanged if practical. Existing
`max_variables`, `max_constraints`, `max_nonzeros`, `max_work`, depth, deadline and
cancellation controls can cap the new representations with explicit accounting:

| Representation | Storage/work to charge before allocation/posting |
|---|---|
| Flat table | Source arguments + every relation cell; typed row count and copied cells; one global constraint; private literal variables |
| Holey domain | Original and normalized members; intersection/sort work; unary table rows/cells; one global per noncontiguous representative |
| Circuit | Successor occurrences including repeats; one global; literal slots; source-evaluator visited array |
| Cumulative | All three arrays and scalar; fixed-value lookup; one global; start literal slots; at most two checker events per active task and bounded sorting storage |

The current public `validate_flatzinc` has no time/cancellation option. Its original
checker allocations and work are bounded by the already admitted payload, but an
outer caller can only checkpoint before/after it. Do not claim an internally
interruptible checker or hard validation deadline without a separate interface
change. Compiler-side normalization/copying continues to use its own Meter.

Global argument occurrences and table cells count toward `max_nonzeros` even
though they are not matrix nonzeros. This extends the existing compiler's global
payload accounting; document the meaning. No unchecked `n*tuple_count`, `2*n`,
`offset+n-1`, interval width or cumulative energy calculation may precede checks.
Caps include constants/helpers; a partial failed artifact never escapes.

Compilation need not require a native build. Typed global constants retain the
Model's exact `[-2^53,2^53]` boundary, while actual Native solves additionally use
`Int::Limits::min/max` (`±(INT_MAX-1)` here). Native preflight already checks global
argument/tuple counts, values and index endpoints. Cumulative has stricter
endpoint, total-energy, task-count-squared and propagation-envelope admission:
for retained positive-demand tasks it guards integer sums/products and the bound
`2*capacity*time_magnitude + total_energy <= native_max*minimum_height` where
applicable. Reuse this code; do not claim that individually representable inputs
alone guarantee a supported schedule. Overflow or a failed envelope guard yields
`Unsupported`, not false infeasibility. Large literal/domain models can compile
but remain unsupported by the selected backend.

Any remaining active Table/Circuit/Cumulative global causes explicit HiGHS solve
rejection under the existing full-model capability check. Auto chooses Native for
active typed globals. No continuous relaxation, omitted membership constraint, or
silent decomposition is allowed. A holey-domain intersection that becomes
contiguous may use only bounds and retain ordinary linear HiGHS capability; a
remaining unary table does not. Missing Native must remain explicit unsupported.
A separately folded constant contradiction may have no active globals and can be
handled by either backend, with the original source check still retained.

The final result is accepted only after current `validate_flatzinc` checks owner,
revision, full helper-inclusive slot layout, active mask, integral source values,
all original declarations/aliases/domains and every admitted original predicate.
Generated helper values are existential witnesses, not extra user decisions or
source outputs. Source validation checks feasibility/objective only; it does not
upgrade a Numerical vendor bound into an Exact proof. Satisfy/optimal/limit markers
remain the existing driver's responsibility.

## Conformance gates before implementation is considered complete

1. **Signature matrix:** use owning records and real parser fixtures for every
   exact admitted spelling. Wrong arities, nested arrays, Boolean tuple cells,
   variable parameter tuples, foreign references, six-/seven-argument scheduling,
   cost/subcircuits and double prefixes must fail explicitly. Pin the MiniZinc
   binary/version/library path and generated source hash for generator fixtures.
2. **Two-way table oracle:** arities 1–3, all assignments in tiny signed domains,
   arbitrary row order/duplicates, empty relations, fixed literals, repeated
   aliases and impossible repeated-position rows. Compare original row membership
   with existence of a satisfying compiled helper assignment in both directions.
   Zero-arity tests verify explicit rejection and the existing typed API's
   distinct false/true empty-tuple cases; never pass them through division by zero.
3. **Domains:** unsorted/duplicate members, negative and noncontiguous sets,
   interval/list/list intersections, aliases with disjoint/overlapping domains,
   singleton/empty sets, contradictory assigned values, finite sets bounding
   `var int`, and very large sparse gaps without hull enumeration. An exact source
   oracle must reject every hole, including a forged otherwise-valid witness.
4. **Circuits:** independently enumerate successor assignments for sizes 1–5 and
   offsets 0, 1, 3; reject subtours/self-loops/out-of-range values; include repeated
   handles, fixed literals, wrong argument order, empty arrays, negative offset
   admission and endpoint overflow. Add min/max objectives with offsets so source
   values and optimality results are tested together.
5. **Cumulative:** sizes 0–4; durations/heights/capacity including zero; endpoint
   touching, coincident starts, alias starts with additive resource, over-capacity
   singleton, the zero-duration legacy disagreement, negative start times,
   singleton parameter aliases and unfixed/negative parameters. Enumerate every
   start assignment and compare a direct integer-time resource oracle. Check
   arithmetic boundaries and the native envelope guard separately.
6. **Integration:** combine each new global with existing reification, AllDifferent,
   Element, source aliasing and holey domains; independently enumerate helper slots.
   Keep original records immutable; destroy input/parser lifetime; verify source
   output never exposes literal/helper slots. Forged owner/revision/mask/fractional
   values and violated original predicates must be rejected by the source checker.
7. **Limits/configurations:** exact cap boundaries and cancellation/time tests in
   normalization, tuple copying, fixed-parameter resolution and final publication;
   no partial artifact or guessed infeasibility on interruption. Run backend-free,
   Native+HiGHS and fully instrumented suites. Explicit HiGHS must reject every
   retained global. Retest the opt-in CLI markers and unchanged legacy fixture
   smoke panel; do not weaken original-predicate checks to make a differential
   test pass.

After these correctness gates, add small representative table/domain/scheduling
cases to the existing bounded fast regression panel and benchmark the new
admission against the existing native FlatZinc route. Performance measurements
must use comparable source problems/configurations and run after concurrent builds
and solver tests have stopped. This document itself makes no executed-test or
performance claim.

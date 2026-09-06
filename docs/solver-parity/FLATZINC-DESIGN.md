# W4 FlatZinc capture: first implementation design

Status: design and source audit only, 2026-09-05. No parser changes, builds,
solver executions or performance measurements were made for this audit.
The audited sources are the branch at `23aaa32ac`; the parent integration has
additional Optimize features but the Model record layouts used here agree.
Source references below give repository paths and line numbers at that revision.

Implement a separate, opt-in **parser capture path**, followed by a compiler from
owned semantic records to `Optimize::Model`. Keep `fzn-gecode`, its configuration,
existing `parse` overloads, registry dispatch, search and native output unchanged.
The first vertical slice should cover bounded integer/Boolean linear models,
selected reified comparisons, AllDifferent and Element, and complete objective
and output reconstruction. An unsupported predicate must prevent publication or
solving of the captured model. Reading back posted Gecode actors cannot establish
that the full FlatZinc model was retained.

The original W4 planning criteria were to preserve aliases, reification and
globals, keep old examples passing, and check MiniZinc cases. The common model
must be usable from normal frontends without losing native semantics. This
design covers the initial capture boundary, not the full global registry or
MiniZinc packaging; see [the implemented compiler](FLATZINC-COMPILER.md) and
[current MiniZinc registration](MINIZINC.md) for the delivered scope.

## Why the capture boundary belongs in the parser

| Source hook | Observed behavior | Required design consequence |
|---|---|---|
| `gecode/flatzinc/parser.hh:184` | ParserState owns symbol/array tables, separate int/bool/set/float VarSpec vectors, domain constraints, constraints and output nodes. | Keep capture state local to one parse. No global recorder or state attached to cloned spaces. |
| `gecode/flatzinc/parser.yxx:791`, `:823`, `:967` | Declarations can create literals or aliases; array declarations reuse existing slots, create literal slots and synthesize domain constraints. | Retain the complete slot-to-variable mapping, including repeated array entries and non-output variables. Names alone are not unique identities. |
| `parser.yxx:200` and `:210` | Declaration restrictions become `int_in`, `float_le`, and related ConExpr records. | Capture both domainConstraints and constraints. Capturing only explicit constraint items loses declaration restrictions. |
| `parser.yxx:230` and `:1631` | Equality between two int variables is consumed into an alias. The discarded representative's domain becomes an `int_in` record; Boolean equality is handled similarly at `:1656`. | Capture final alias representatives and the generated domain records before disposal. A registry observer never sees these equality constraints. |
| `parser.yxx:1570` | Restart/status/last-value predicates are consumed before normal constraint dispatch. | Record every original predicate name and location before this switch, and classify every consumed item. An unsupported restart predicate cannot disappear from coverage accounting. |
| `parser.yxx:272` | `initfg` constructs native variables, then deletes VarSpecs at `:287`, `:299`, `:310`, `:322`. Later it posts restart actors and both constraint vectors at `:463`. | Freeze capture records at the entry to initfg. Capture-only mode must bypass the entire native initialization/posting block. |
| `gecode/flatzinc/flatzinc.cpp:1027` | Constraints are sorted by arity, dispatched, then deleted. | Freeze before posting; preserve original sequence/provenance separately from posting order. |
| `gecode/flatzinc/registry.cpp:60`, `:70` | Registry holds native posting callbacks, and automatically registers `gecode_` and `fzn_` aliases. Plugins can replace entries through `add`. | Use an independent, explicit capture whitelist with exact signatures. Do not infer support by stripping arbitrary prefixes or by the existence of a native poster. |
| `gecode/flatzinc.hh:591` | Initialization, variable construction, posting and solve methods are nonvirtual. | A FlatZincSpace subclass does not intercept the parser's calls. Do not add fake overriding methods or inspect actors afterward. |
| `parser.yxx:2023` | Variable objectives preserve a typed slot, but literal and parameter objectives at `:2037`, `:2058`, `:2065` become a new **zero-valued** integer variable. | Capture the actual solve expression in its grammar action before normalization. `minimize 7` must retain offset 7, even though the legacy path does not need its value to find a satisfying assignment. |
| `parser.hh:245`, `:249`; `flatzinc.cpp:3014` | Output construction sorts names and transfers AST ownership; Printer later rewrites variable indices during shrinking. | Freeze a separate typed output plan before getOutput/shrinkArrays. Never use shrunk indices to address Optimize values. |
| `tools/flatzinc/fzn-gecode.cpp:57` | Legacy execution is parse → createBranchers → shrinkArrays → run. | The opt-in driver must route before this sequence, not bolt another solver onto an already-shrunk space. |

The current model supports owning sparse rows, five variable domains, indicators
and five typed globals, but no FlatZinc namespaces or output descriptions
(`gecode/optimize/model.hpp:100`, `:130`, `:167`). Keep frontend provenance and
output records in a companion artifact; do not overload Model variable names or
introduce AST pointers into ModelSnapshot.

## Proposed interfaces and ownership

Use two layers so the existing FlatZinc library does not acquire a mandatory
Optimize/HiGHS dependency:

1. **Parser-owned records**, in new `gecode/flatzinc/capture.hh/.cpp`. Define a
   noncopyable parse context and an immutable `CapturedFlatZinc` result with
   typed literals/references/arrays, declarations, normalized constraints,
   source coverage records, SolveGoal and OutputPlan. No Optimize types and no
   live Space, VarSpec, ConExpr, AST, scanner, input stream or plugin callback
   survive publication. Set/float values can be recorded for diagnostics even
   when the first compiler rejects their use.
2. **Optimize bridge**, in new `gecode/optimize/flatzinc.hpp/.cpp`. Compile the
   captured artifact into a private local Model plus maps. Publish it only after
   all declarations, predicates, annotations, objectives and outputs have been
   classified and checked. Return a typed outcome such as Complete,
   Unsupported, InvalidInput or ResourceLimit, with location/reason. Unsupported
   is a frontend outcome, not an infeasibility proof. A partial Model is never
   returned as usable. Allocation failures remain explicit exceptions/outcomes.

A new `parse_capture(std::istream&, CaptureOptions)` entry point invokes the
same generated parser with an explicit capture mode in ParserState. Existing
parse entry points construct a context with capture disabled. Do not change the
layout or public virtual interface of FlatZincSpace or introduce capture members
into search clones. The capture result is a historical frontend artifact, not a
mutable alias of ParserState.

Concrete parser changes for that path:

- Before the `constraint_item` optimization switch, classify the exact predicate
  and check the argument counts/types that the switch will inspect. Preserve
  source item ordinal, literal identifier, full copied typed arguments and annotations.
  Ordinary constraints remain in the existing vectors; the coverage ledger
  records which original equalities became aliases and which special items
  would be consumed. Reject unsupported restart/blackbox/plugin semantics here,
  before native callbacks or external processes could be invoked.
- At the start of initfg, freeze final VarSpecs, alias edges, both constraint
  vectors and the coverage ledger. Resolve aliases with checked indices and a
  cycle guard. In capture-only mode skip **all** native initialization, restart
  posting and registry calls, then dispose temporary objects exactly once.
  Do not create a partially initialized FlatZincSpace and use it as a result.
- Record the original objective kind/value/slot in `solve_expr` and the method
  and annotations in `solve_item`. Capture mode does not call `fg->solve`,
  `minimize` or `maximize`. All paths accessing `pp->fg` are in initfg and these
  solve actions today; guard them explicitly, not with a null-space convention.
- Preserve `_output` as typed owned entries before getOutput transfers nodes.
  At scalar/array declaration actions, retain the original domain/initializer
  and annotation records before alias/domain normalization and destruction.
  These support an original-source checker independent of the normalized
  compiler input, as well as output dimensions and control classification.
  This is additional declaration plumbing, not information recoverable from
  only the final VarSpecs. After getOutput, `_output` contains old pointers;
  cleanup must never treat it and the transferred tree as separate owners.
- Capture-mode cleanup must cover syntax errors, invalid aliases, rejected
  predicates, exceptions, empty models and EOF after a partial declaration.
  Existing ConExpr owns/deletes its args and annotations
  (`gecode/flatzinc/conexpr.hh:72`). Avoid duplicate ownership when copying and
  when deleting an alias's displaced domain. Alias constructors do not initialize
  every non-alias VarSpec field (`varspec.hh:86`, `:108`); branch on `alias`
  **before** reading assigned/domain data. Equality rewrites can also leave
  `assigned=true` while replacing `i` with an alias index: the old value belongs
  to the synthesized domain relation, not the alias's `i`. A generated `int_in`
  may address a BoolVar; preserve its namespace rather than indexing intvars.

Record an item ordinal and parser filename for every object. The current grammar
uses scanner line numbers for errors, rather than Bison location tracking
(`parser.yxx:67`, `:78`). Add a token-start location or `%locations` if start lines
are promised; the current scanner line at reduction is only an end/nearby line.
Do not report an invented exact source span. Synthesized constraints point back
to their declaration/equality and carry a distinct synthesized marker.

### Lexical and input-size gate

The current integer lexer calls `strtol(text, NULL, 0)` and checks the numeric
range (`gecode/flatzinc/lexer.lxx:60`), while accepting `0o` spellings at `:101`.
The missing end-pointer check means that accepted spelling can be partially
consumed; leading-zero decimal spellings can also be interpreted with C's radix
rules. This is source evidence, not a reproduced runtime claim in this audit.
The AST integer is already too late to recover the lexeme.

Capture mode must either perform checked full-lexeme conversion according to the
lexer alternative before assigning the semantic value, or explicitly reject
noncanonical decimal/hex/octal spellings it cannot preserve. Prefer correct
checked conversion for all accepted alternatives and tests for `0o10`, `010`,
`08`, signed forms, boundary values and trailing junk. Keep any change in legacy
lexical behavior a separately reviewed fix; the initial capture mode can guard
its own accepted spelling. The current lexer already limits integer literals to
Gecode's native range; the first capture API must disclose that it is not an
arbitrary int64 FlatZinc reader. Float conversion uses unchecked `strtod` at
`:110`; the first compiler rejects floating data rather than accepting overflow
or quietly changing FloatVar semantics.

Bound input bytes/counts before converting to ParserState's unsigned/int sizes
(`parser.hh:185`, `:197`) and before creating arrays. Validate objective array
indices and symbol lookup before the legacy `solve_expr` array access at
`parser.yxx:2072`; its current zero/upper-bound check is not sufficient for a
capture path accepting negative literals. Error paths must not dereference an
uninitialized SymbolEntry. A deadline/cancellation check before and after parse
is useful, but a claimed whole-command parse deadline additionally needs token
or input-loop checks; do not claim it from a solver-only timer.

## First admitted semantic subset

The first executable should be a distinct opt-in tool, tentatively
`fzn-gecode-optimize`, initially with explicit Native/Exact and HiGHS/Numerical
routes. The normal `fzn-gecode` remains the default. Do not publish a MiniZinc
solver configuration that advertises arbitrary FlatZinc support yet.

| Construct | First compiler behavior |
|---|---|
| Bounded `var int`, fixed int, `var bool`, fixed bool | Create Integer/Binary variables with exact bounds. Same-type aliases reuse the representative handle; fixed aliases preserve their restrictions. Require a finite interval after declaration/alias-domain intersections for this first slice. Do not substitute Gecode's implicit Int::Limits for an unbounded mathematical declaration. |
| Integer/Boolean arrays, literal entries, repeated references | Preserve per-type source slots and array order. Literal entries become fixed hidden variables only when a global/helper requires a handle; ordinary linear literals fold into an exact checked RHS. |
| Interval `int_in` and contiguous explicit finite domains | Intersect restrictions across aliases before emitting IR. Empty restrictions become an explicit constant contradiction, with a harmless fixed placeholder for a source slot if needed; never an invalid IR bound pair. Preserve the original empty-domain record for source validation. Nonconvex domains are initially Unsupported, never replaced by their hull. |
| `int_eq`, `int_le`, `int_lt`, `int_ge`, `int_gt` | Equality/ranged rows; strict integer inequalities shift the bound by one with checked arithmetic. Constants on either side are supported. Normalized equality aliases still appear in coverage accounting. |
| `int_lin_eq`, `int_lin_le`; `bool_lin_eq`, `bool_lin_le` | Exact checked sparse rows; equal coefficient/variable lengths, mixed fixed entries, empty rows and duplicate aliases supported. `bool_lin_eq` permits a variable integer RHS; move it to the LHS instead of assuming a constant RHS. |
| `int_plus`, `int_minus`, `bool_eq`, `bool_le`, `bool_not`, `bool2int` | Direct linear equalities/inequalities, including typed constants. `bool2int` is a channel equality between an Integer and a Binary variable, not a reason to overwrite the original variable's domain/type. |
| `bool_and`, `bool_or`, `array_bool_and`, `array_bool_or`, `bool_clause` | Use existing helpers or exact Boolean linear rows; handle empty lists and repeated literals. Do not infer XOR support from an OR helper. |
| `int_le_reif`, `int_lin_le_reif`, corresponding `_imp`, and `int_eq_imp` | Preserve the direction rules below. Boolean literal guards are handled semantically. All required indicator activity bounds must be finite and conservatively representable, otherwise Unsupported. |
| `all_different_int`; `array_int_element`, `array_var_int_element` | Preserve typed AllDifferent/Element records. Plain FlatZinc element uses `index_base=1`; keep duplicate positions and aliases, including index/result aliases. Do not deduplicate a global's variable array. |
| Satisfy, integer variable/array-element objective, integer constant/parameter objective | Keep an explicit SAT/MIN/MAX method. Variable objective is coefficient 1 on its mapped handle; a constant objective is its actual offset. Preserve source objective identity even when aliased or hidden. |
| `output_var`, integer/Boolean `output_array`, declaration/constraint metadata | Freeze a typed output plan. Keep modern 1-D output and existing legacy multidimensional array descriptors. Validate dimension cardinality with checked multiplication. |

This is a whitelist, including explicitly tested registry aliases where desired.
It does not automatically admit every `fzn_`/`gecode_` spelling. The capture
compiler's signature table is authoritative for the accelerated route; plugins
that override native posters do not silently override that table. Plugin-enabled
or custom semantic routes must select the legacy frontend until a versioned
capture implementation exists.

The integer source evaluator should accumulate coefficients, literals, alias
coalescing and strict-bound shifts using checked exact arithmetic. Require every
value eventually stored as a double to round-trip exactly (including objective
constants and summed coefficients). Reject overflow/unrepresentable conversion
with a location; do not rely on long-double accumulation as a proof of integer
exactness. The existing Model's numerical normalization remains a second check,
not the frontend's exact source representation. Native's own narrower activity
checks can still return Unsupported after successful capture
(`gecode/optimize/native.cpp:32`, `:104`, `:134`).

### Reification is a semantic requirement

For an integer expression `L` and integer bound `k`, compile:

- `int_lin_le_imp(a,x,k,b)`: `b=1 ⇒ L≤k`; impose no converse when `b=0`.
- `int_lin_le_reif(a,x,k,b)`: both `b=1 ⇒ L≤k` and `b=0 ⇒ L≥k+1`.
- `int_eq_imp(x,y,b)`: `b=1 ⇒ x−y=0`, one ranged indicator.

These use `add_indicator`'s original logical metadata and finite-bound checks
(`gecode/optimize/constraints.hpp:17`). Build the whole compiled artifact locally:
a failure while adding the second direction must not publish the first direction
as a completed constraint. Evaluate constant guards without fabricating a Binary
handle unless a helper needs one. In particular false `_imp` is true, while false
`_reif` requires the negated relation. The guard for a linear comparison is the
**fourth** argument; validate arity before indexing. The native registry itself
uses `ce[3]` for posting (`registry.cpp:252`, `:267`), so do not copy a suspicious
literal-guard shortcut at `:230` as a specification.

Full equality/disequality reification, XOR, reified globals and arbitrary
nonlinear reification remain explicitly Unsupported in the first slice.
`b ⇔ L=k` requires a disjunction for its false branch; two oppositely activated
equality indicators are incorrect. A later extension may introduce exact
less/equal/greater selectors with an exhaustive truth-table gate. Integer
complement shifts do not generalize to continuous strict inequalities.

The primary definition confirms that reification is equivalence and `_imp` is
one-way implication; integer linear reification has a final Boolean argument.
[MiniZinc reification rules](https://docs.minizinc.dev/en/2.9.7/fzn-spec.html#reified-and-half-reified-predicates),
[integer builtins](https://docs.minizinc.dev/en/stable/lib-flatzinc-int.html#int-lin-le-reif).
The Boolean builtin signatures also distinguish the variable RHS of
`bool_lin_eq` and the Boolean-to-integer channel.
[Boolean builtins](https://docs.minizinc.dev/en/stable/lib-flatzinc-bool.html#bool-lin-eq).

## Globals and routing: no incomplete model may run

A Complete capture requires accounting for **every** declared variable, source
predicate, generated domain constraint, solve item and requested output.
A coverage entry must be a compiled relation, a checked alias/domain equivalent,
a proven constant relation, or an explicit Unsupported item. Merely marking a
poster as known is insufficient. Constant-false constraints remain contradictions;
constant-true constraints retain provenance even if they emit no row.

Routing rules:

- **Legacy native (default):** existing full native parse/search path, unchanged.
- **Optimize Native/Exact:** requires Complete capture, then the current native
  compiler; retains typed globals and returns explicit Unsupported if it cannot
  compile a retained record.
- **Optimize HiGHS/Numerical:** requires Complete capture and backend capability
  checks. Any retained active global unsupported by HiGHS rejects the full route.
  An AllDifferent plus linear rows never becomes a linear-only MIP.
- **Optimize Auto, if exposed later:** means the current complete Model route
  selector, not permission to discard unsupported frontend constructs. Current
  Model Auto chooses Native when globals are present, otherwise HiGHS.
- Do not add automatic retry against a partially built model. An optional future
  legacy fallback must reparse the **original immutable input** into a fresh
  legacy context, report the selected route, and preserve all constraints. Syntax
  errors, numeric conversion errors and contradictory status claims are not
  fallback triggers. No fallback is needed for the first vertical slice.

First-slice rejection fixtures must include set/float variables, nonconvex
integer domains, unknown/plugin/blackbox predicates, restart-state predicates,
`regular`, variable-duration cumulative, reified AllDifferent, nonlinear
multiplication, unhandled search controls and unsupported output types.

Subsequent typed-global extensions should be individually admitted:

| Candidate | Exact correspondence to verify before enabling |
|---|---|
| `gecode_table_int` / bool table | Registry flattens row-major tuples and calls unshare before posting (`registry.cpp:1269`). Validate arity/divisibility and retain repeated source variables. A zero-arity flattened array cannot distinguish zero from one empty tuple without an explicit convention; reject that form until specified/tested. |
| `gecode_circuit` | Native poster expects explicit offset plus successor array (`registry.cpp:1543`), matching CircuitData's index base. Do not route costed circuit variants into the uncosted record. |
| Fixed-duration/height cumulative | Model supports nonnegative fixed durations/heights/capacity and zero-duration no-resource semantics. The existing `cumulatives` poster is overloaded and has special empty/singleton paths (`registry.cpp:1333`, `:1409`). Admit only a separately pinned signature and reconciled zero-duration convention; do not label all `cumulatives` calls supported. |
| Holey integer domains | Unary TableData can preserve membership on Native, but makes the HiGHS route unsupported unless a verified exact encoding is added. Limit table size; never enumerate huge intervals to recover an interval representation. |
| Linear floats / continuous recourse | Define numerical FlatZinc input and output tolerances, strict/reified predicate exclusions, lexical finite-value checks and source validation first. A posted native FloatVar interval is not an Optimize Continuous value. |

## Objective, output and status reconstruction

The compiled artifact owns raw declaration/predicate records for independent
checking alongside normalized compiler input: per-type source-slot → Optimize Variable mappings;
canonical aliases; literal entries; output names/dimensions/order; actual solve
method and objective expression; full source relations for checking; and the
compiled snapshot's model ID/revision. Hidden literal/helper variables are not
source output variables. Integer and Boolean slot zero are distinct namespaces.
`bool2int` does not merge these namespaces, even when their values are equal.

Print directly from the captured OutputPlan and a validated full assignment.
Do not construct a fake solved FlatZincSpace merely to call Printer, and do not
borrow Printer's mutable AST. Preserve old multidimensional descriptors used by
`test/flatzinc/test_flatzinc_output_anns.cpp:45` as well as modern one-dimensional
arrays. Arrays with repeated aliases must print repeated positions. Validate
all model variables, including hidden/non-output ones, before any solution is
emitted. Buffer the full solution text first so a late invalid output node cannot
leave a partial apparent solution on stdout.

The primary interface specifies output annotations, complete satisfying
assignments, solution separators and distinct completion/unknown/unbounded
markers; modern MiniZinc output arrays are 1-based and one-dimensional, while
older arrayNd forms remain relevant to this repository's fixtures.
[FlatZinc output contract](https://docs.minizinc.dev/en/2.9.7/fzn-spec.html#output).

For a captured discrete model, check numerical candidate rounding explicitly:
each source Integer/Binary value must be within the documented tolerance of a
representable integer, then evaluate **all original** domains, channels, rows,
reified relations and globals exactly on that rounded assignment. Recompute the
source objective, including offsets, and compare with the solver result. Do not
turn a numerically near-integer value into a valid output merely by formatting it
with no decimal digits. Keep the numerical backend's guarantee separate from the
exact feasible-point check; checking a point does not certify its bound.

First-driver status policy:

| Outcome | FlatZinc behavior |
|---|---|
| SAT request, valid point | Emit requested assignments and `----------`; a constant-zero optimizer reporting Optimal does **not** prove enumeration complete, so do not emit `==========` for an ordinary one-solution SAT request. |
| MIN/MAX, valid final optimal result | Emit point and separator; use `==========` only according to the configured route's completed optimization contract. Native/Exact is the first strict completion gate. Numerical mode must be explicit, use zero requested MIP gaps for this frontend and report its numerical guarantee in comments/metadata. It is not a proof certificate. |
| Proven infeasible | `=====UNSATISFIABLE=====`; distinguish source contradiction and solver outcome in diagnostics. |
| Unbounded | `=====UNBOUNDED=====`; the initial finite discrete subset should not produce this, but do not remap it to infeasible. |
| Time/node/cancel limit with checked point | Emit point/separator, no completion marker. |
| Limit with no point | `=====UNKNOWN=====`. |
| Unsupported / invalid input / unavailable selected backend / validation failure | Actionable error on stderr and nonzero exit; no fabricated solution, no UNSAT marker. |

Initially support one satisfaction solution and final optimization output only.
Reject `-a`, multi-solution `-n`, intermediate-output `-i`, LNS/restart callbacks,
and incompatible fixed-search controls until implemented. Retaining an annotation
as text does not implement its requested search behavior. Known harmless
metadata such as `defines_var`, `is_defined_var`, `var_is_introduced`, `mzn_path`
and specifically whitelisted propagation-strength hints can be recorded without
altering the feasible set; unknown annotations are Unsupported initially; free-search permission must
be explicit when ignoring search-order annotations. Do not advertise unsupported
standard flags in a new `.msc` file. The existing
`tools/flatzinc/gecode.msc.in` describes the legacy solver and must remain intact.

## Conformance fixtures and release gates

Add small standalone `.fzn` files with independent witness/feasible-set oracles.
Do not derive the oracle by reading back the generated Optimize rows. Enumerate
original source variables, then existentially quantify frontend helper variables
when comparing feasible sets. Tests must verify a positive fixture count and
identify the admitted signature/route, so rejecting every file cannot pass.

| Fixture family | Required expected behavior |
|---|---|
| Declaration aliases | Chain aliases, narrower initialized alias, equality-induced alias, alias-to-fixed value, conflicting domains; same full feasible set and output names. |
| Boolean/integer channels | Bool slot 0 and int slot 0 independent until bool2int; conflicting int domain is infeasible; arrays mixing constants and repeated aliases preserve order. |
| Sparse linear rows | Duplicate alias coefficients, cancellation, mixed literals, variable RHS bool_lin_eq, zero terms, strict boundaries, negative coefficients, overflow/unrepresentable-data rejection. |
| Reification truth tables | Enumerate x,y in −2..2 and both guard values for each admitted `_imp`/`_reif`; false guards differ. Empty linear expressions and literal guards true/false. Reject equality `_reif` rather than weakening it. |
| Objectives | Satisfy; minimize/maximize variable and alias; array element objective; literal/parameter 7 and −3; source objective represented through a defining linear equality with a nonzero constant. Constant objectives must report their real value. |
| Output mapping | A named hidden variable precedes outputs; two scalar aliases; repeated array positions; empty output array; legacy array2d indices; modern output_var/array; no output variables; model destroyed before formatting retained results. |
| Globals | AllDifferent([x,x]) infeasible; Element with repeated entries and index/result aliases, 1-based boundary indices, constant array entries. Add an AllDifferent that removes the linear relaxation's otherwise optimal solution: explicit HiGHS must reject the complete model. |
| Coverage and failures | Unknown predicate, each consumed restart family, registered custom plugin name, malformed arity, domain-only constraint, unsupported set/float/nonconvex domain. Verify no backend invocation, native poster call or subprocess creation in capture mode. |
| Lexer/parser lifecycle | Decimal/hex/octal boundaries, negative objective array index, absent symbol, oversized dimensions/input, malformed/truncated input, parse twice independently, exceptions/allocation failures and sanitizer cleanup. |
| Status/limits | Fake compiler/backend results for Unsupported, invalid full assignment, wrong owner/revision, interrupted candidate/no candidate, SAT Optimal-with-one-point, and numerical versus exact completion claims. |

Compatibility gate: run the existing legacy FlatZinc tests unchanged, including
`output_test.cpp`, `test_flatzinc_output_anns.cpp`, `sat_cmp_reif.cpp`,
`sat_eq_reif.cpp`, empty-domain, restart and blackbox fixtures. These are legacy
compatibility tests, not a claim that capture admits those whole files.
`shared_array_element.cpp` also includes unsupported `count` at line 102, so the
first captured route should reject that complete file; create a small original
Element fixture instead of deleting its `count` constraint for benchmarking.
The current test harness supports a semantic output checker in addition to exact
text (`test/flatzinc.cpp:157`). Preserve exact legacy output where promised;
compare full assignments/objectives for cross-backend correctness instead of
requiring identical search order.

Integration gates, in order:

1. Parser-record tests and independent source-evaluator tests, including rejected
   syntax cleanup under ASan/UBSan. Capture-only instrumentation proves zero
   native variable/poster/search calls.
2. Complete capture → Optimize Native/Exact → reconstructed output for the
   whitelist, with exhaustive small feasible-set equality and alias/reification
   cases. A captured unsupported global must never be omitted.
3. Same complete linear files → HiGHS/Numerical, zero requested MIP gaps, original
   integer point validation and known optima. Off builds return explicit
   Unsupported. Retained globals reject HiGHS; ordinary native remains usable.
4. Legacy parser/search regressions pass; installed consumer exercises the new
   optional bridge without making HiGHS mandatory for the legacy FlatZinc target.
5. Compile pinned MiniZinc source fixtures with a pinned, deliberately limited
   mznlib, then solve/check them. Freeze generated `.fzn`, compiler/library
   versions and hashes; report flattening, parsing/IR and solve costs separately.
   The current 56-fixture historical panel is a compatibility seed, not evidence
   of modern FlatZinc or MiniZinc Challenge coverage.
6. Only after flag/output/mznlib conformance: add a separate solver `.msc`, a small
   FAST gate case, and broader MiniZinc corpus evaluation. No performance claim
   before a quiet repeated comparison with fixed/free search reported separately.

## Concrete implementation ownership and ordering

| Slice | Exclusive files | Deliverable and dependency |
|---|---|---|
| A: capture records and parser plumbing | New `gecode/flatzinc/capture.hh/.cpp`; `parser.hh`, `parser.yxx`; generated `parser.tab.cpp/.hpp`; capture-only lexical guard in `lexer.lxx` and regenerated `lexer.yy.cpp`; new `test/flatzinc/capture.cpp` | Immutable records, checked lexical/argument boundaries, original objective, output plan and cleanup. No Optimize dependency. One owner must edit grammar and generated files together. |
| B: semantic compiler/checker | New `gecode/optimize/flatzinc.hpp/.cpp`; new `test/optimize/flatzinc.cpp` and fixtures under `test/optimize/flatzinc-fixtures/` | Whitelist, aliases/domains, linear/reified/global compilation, coverage closure and original-source witness checker. Can develop against hand-built A records while A's parser work proceeds. No changes to native registry semantics. |
| C: optional driver/distribution | New `tools/flatzinc/fzn-gecode-optimize.cpp`, later new dedicated `.msc.in`/limited mznlib; root CMake/install wiring | Route selection, limits and status/output contract. Depends on A+B. Root owns build/install files; no change to legacy driver/config by another agent. |
| D: independent review | Read-only A/B source and independent exhaustive fixture generator/checker tests | Review alias-domain losses, each reification direction, unsupported closure and source/IR identity; review generated-parser parity before enabling the tool. |

The first accepted vertical implementation is A+B plus a narrow driver: bounded
int/bool declarations, the listed linear/channel/Boolean primitives, ≤
reification/implication, AllDifferent/Element, constant/variable objectives and
integer/Boolean output. If that is too large for one change, land A's immutable
capture with rejection tests first, then B's linear/channel/objective slice;
keep reification/globals explicitly rejected until their own fixtures pass. Do
not weaken a semantic gate to fit an estimate. Table/Circuit/cumulative, general
finite domains, floats, full equality reification, search annotations, complete
MiniZinc packaging and automatic legacy fallback are separate increments.

Generated parser maintenance is an implementation dependency: the existing
Makefile regenerates `parser.tab.cpp/.hpp` with Bison and the scanner with Flex
when available (`Makefile.in:1562`); otherwise it consumes checked-in generated
sources. Record tool versions and keep generated sources aligned. Parser
plumbing and ownership cleanup are the main schedule risks; claiming this is
only a few registry callbacks would omit the actual semantic work.

Independent read-only hook review confirmed the capture-only boundary and
identified the alias/assigned precedence, BoolVar-typed synthesized domains,
pre-rewrite arity checks, objective array validation, input-size limits and
transferred-output ownership issues incorporated above. No runtime claims are
based on that review.

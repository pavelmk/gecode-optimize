# Explicit root LP cover loop

`gecode/minimodel/lp-cut-loop.hpp` adds a bounded, opt-in root LP/cover loop to
the experimental integer LP module. It does not change native search, Optimize
facades, solver selection, presets or default propagation. It uses the original
source/proof contracts in [CUTS.md](CUTS.md) and native arithmetic restrictions in
[SPARSE-LP.md](SPARSE-LP.md). This is root strengthening, not branch-and-cut.

```cpp
#include <gecode/minimodel/lp-cut-loop.hpp>
namespace LP = Gecode::Experimental::LpRelaxation;
namespace Cuts = LP::Cuts;

LP::BoundedIntegerModel input;
input.linear.row_start = {0,2}; input.linear.column = {0,1};
input.linear.a = {-3,-3}; input.linear.b = {-5}; // 3*x+3*y <= 5
input.linear.c = {-2,-2};
input.lower = {0,0}; input.upper = {1,1};
Cuts::SourceModel original(std::move(input));
Cuts::RootLoopOptions options;
options.max_rounds = 4;
options.deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
auto result = Cuts::root_cover_loop(original,options);
// The verified x+y<=1 cover changes the checked integer lower bound -3 to -2.
// result.model owns original rows followed by the negated <= cover rows.
```

## Numerical suggestions and exact proof boundary

`BoundResult` has a new optional `primal_suggestion`, an owning `vector<double>`.
Existing three-argument `bound(lower,upper,retain_certificate)` overloads remain
available with unchanged default behavior and no primal-copy cost. A new
four-argument overload requests the copy with `retain_primal=true`. The backend
copies only after an actual HiGHS call without error, when `value_valid` is true,
the column count matches and every value is finite. A missing dual certificate
does not invalidate this selection-only hint. Zero matrices, which skip HiGHS,
do not invent a primal suggestion. The immutable model and serialized sibling
bound-restoration behavior are unchanged.

The loop projects a finite suggestion into the **original** box and counts
projected coordinates. `rational_selection_point` rounds the projected vector
to the nearest grid point, with ties away from zero. The common denominator
must be a power of two between 1 and 1,048,576. Validated native endpoints times
that denominator have magnitude below 2^51, so endpoint conversion and scaling
are exact in double and the checked int64 numerator conversion is safe. Invalid
shape, nonfinite values and unsupported denominators are rejected.

This vector need not satisfy the original rows and is never an integer solution,
primal bound, cut proof or optimality claim. Projection and grid rounding can
miss useful cuts, which affects strength only. Every separated cut is verified
against the immutable **original** `SourceModel` with `Scope::global()`. Later
rounds never use added rows as proof premises, never use a tightened/local box,
and never promote local records. Floating infeasibility reports are diagnostic
counts only; they do not authorize pruning or an infeasible completion status.

## Augmentation and bound ownership

Each successful round stages a fresh sparse model and backend. Original domain
arrays, objective coefficients, row order, row bounds and CSR entries are kept
exactly. Canonical global covers are deduplicated by the existing `CutPool`.
For each accepted `sum(a*x)<=upper`, the appended row is
`sum(-a*x)>=-upper`. Original row `i` retains its index, and appended row
`original_row_count+k` is attributed to `result.cuts[k]`.

Before publication the loop checks total dimensions and structural storage
limits, uses checked negation, runs the full bounded-integer native
coefficient/activity preflight, constructs another immutable `SourceModel`, and
successfully builds its new backend. Only then are model, backend and record
vector moved/swapped into the result. A failure during staging leaves the last
published augmentation intact. Previously supplied source models and backends
are never modified. New backend workspaces are independent; their per-call
serialization remains safe when callers later share one backend.

`result.best_bound` retains the strongest checked lower bound seen, its exact
immutable augmented model, its certificate and the corresponding original-source
cut records. It does not borrow the loop's latest backend matrix. After one LP
round, for example, the result may already contain a new cut while its best
bound still comes from the original unaugmented matrix. The retained provenance
distinguishes those states. Every such augmented feasible integer set equals
the original feasible set, so an earlier checked lower bound remains valid.
Keeping the maximum of checked lower bounds prevents reported regression if a
later numerical solve proposes a weaker certificate. No raw LP objective enters
this bound selection.

All retained cuts own their source identity. Source-handle destruction, input
mutation and later loop calls cannot change existing models, records or bound
evidence. Public result fields are ordinary C++ values; callers must preserve
their association rather than overwrite fields and treat the edited object as
an independently checked result.

## Budgets and completion

Default limits are four root LP attempts, four million structural work units,
200,000 columns, 200,000 augmented rows and two million augmented nonzeros.
Existing `PoolLimits` and `SeparationOptions` impose additional bounded cut,
term, row, candidate and per-separation work limits. A limit never evicts a
proof, removes an original row or weakens an inequality to fit.

Work is reserved for coordinate conversion, full model copy/preflight shapes,
pool comparison/copy shapes and the separator's deterministic work meter.
Copy/preflight reservations count three column-array values, two row-array
values, two nonzero-array values and one CSR sentinel per scan. This bounds
structural work; it is not a CPU-time, byte-allocation or RSS measurement.
HiGHS' internal work is separately bounded by its existing 10,000 simplex
iterations and 0.2-second allowance per LP call. Source construction/validation
precedes the loop and is not charged to its budget. Temporary staged storage is
bounded by the shape limits, but multiple original, current, staged and retained
bound snapshots can coexist; the limits do not mean only one matrix is resident.

An optional absolute `steady_clock` deadline composes with an outer solve. The
optional `stop_requested` predicate is checked before/after LP work, separation,
copies/preflights and publication gates. These are cooperative checks: an active
LP or bounded separation step can return after the requested stop. A callback
must be thread safe if shared between simultaneous calls and must not mutate
structural/work options while the loop reads them. The executing predicate may
shorten its borrowed deadline; it must not race another thread's option access.
Predicate exceptions, including
`bad_alloc`, return `CallbackError`; they never publish completion or discard
an earlier model/bound. Model/backend allocation failures return
`AllocationFailure`, and other operational exceptions return `BackendError`.

`RootLoopCompletion` distinguishes:

- `NoNewCuts`: this configured heuristic inserted no new cuts. It does not
  prove complete separation, LP optimality or integer feasibility.
- `RoundLimit`, `WorkLimit`, `StorageLimit`, `SeparationLimit`: the named bound
  stopped further work. Returned augmentation and evidence remain valid.
- `Cancelled`, `TimeLimit`: cooperative external stops.
- `NoPrimalSuggestion`, `InvalidSuggestion`: no usable selection vector.
- `CallbackError`, `BackendError`, `AllocationFailure`: operational failure
  with the previous published state retained.

Unsupported free nonbinary source rows, oversized rows and arithmetic-rejected
candidates are skipped and counted. When a separator work cap is reached, only
already verified cuts can be staged; exhausting total work before publication
discards that pending round. A storage cap can publish an accepted prefix if its
complete new backend fits before stopping. Zero rounds/work do not create a
backend. Malformed options and moved-from source handles throw before work.

## Validation

`experiments/lp-relaxation/tests/cut-loop.cpp` independently enumerates original
finite integer boxes and compares full feasible sets with every returned
augmentation and retained bound matrix. It reconstructs cut proofs and verifies
appended-row attribution, original CSR prefixes, domains and objectives. It
also checks the actual fractional HiGHS fixture above, 180 generated signed
models at three round budgets, nondecreasing retained checked bounds, finite
projection and exact rounding boundaries, unsupported rows, empty/contradictory
models, all total work limits 0–649, round/storage/separation caps, cancellation,
deadline and throwing predicates at every checkpoint, immutable old certificates,
concurrent loops and restored sibling bounds on a shared augmented backend.

Optional `GECODE_LP_CUT_LOOP_TEST_HOOKS` enables targeted allocation/backend
exception injection around LP, bound publication and augmentation construction
and publication. Optional `GECODE_LP_CUT_LOOP_TEST_NATIVE` posts returned models
through the actual native integer interface and compares every enumerated native
solution and cost with the original independent oracle. Neither macro changes a
normal consumer build.

Build with C++17, warnings and assertions, configured Gecode/HiGHS include paths,
and the pinned HiGHS library. Add matching native int/search/kernel/support
libraries when enabling native checks. HiGHS may additionally require zlib and
platform thread libraries. For ASan/UBSan, instrument the complete test/header
code **and HiGHS**, plus native libraries when enabled. Mixing instrumented
libc++ vector code with an uninstrumented dependency can invalidate sanitizer
results. No sanitizer suppressions are needed; the macOS run disables leak
detection and halts on address/undefined-behavior errors.

The normal and fully instrumented native+HiGHS runs pass 1,650 configurations
and 7,319 exact feasible-set checks with both optional test macros enabled.
The final-round post-publication cancellation regression retains its completed
augmentation and earlier bound evidence while reporting `Cancelled`.
The unchanged binary and bounded-integer backend suites also pass normal and
full-HiGHS ASan/UBSan rebuilds, including 40 and 80 serialized sibling calls.

The default-off native-facade integration is described in
[NATIVE-LP.md](NATIVE-LP.md#optional-verified-root-covers) and
[NATIVE-SEARCH.md](NATIVE-SEARCH.md#optional-checked-lp). It retains the full loop
evidence, re-evaluates the current backend and combines root totals with later
backend deltas. The loop now reports rejected-bound totals, including completed
backend work when a bound call throws before returning. Dynamic local tree cuts
and performance evaluation remain separate work. No solver default or timing
benchmark changed in this slice.

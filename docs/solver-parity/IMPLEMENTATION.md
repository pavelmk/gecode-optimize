# Implementation ledger

Work is on `codex/solver-parity` in the independent checkout at
`implementation/gecode`. The original solver checkout, branch, uncommitted
source and benchmark binaries remain untouched. The enhanced source/test/input
snapshot is `e10562fd9`; `source-snapshot.json` records 2,963 input hashes. All
2,963 original files matched when checked after integration.

This ledger covers the implemented slices of the ongoing W0–W14 roadmap. The
validation record identifies the exact source used for each completed gate.
They provide numerical LP/MILP modeling and workflows, persistent numerical
sessions, typed native globals, weighted feasibility repair, C/Python bindings,
an explicit bounded integer compiler to native Gecode search, ranked solution
pools, checked integer LP deductions, exact integer presolve/reconstruction,
interruption-safe native frontier bounds, bounded reliability branching,
verified root covers, continuous weighted-square QP and an owning FlatZinc
capture/compiler with a separate command-line solver.
Commercial-solver parity and the larger native search improvements remain
incomplete. The [algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md) adds bounded
native binary capacity optimization after [the ninth checkpoint](NINTH-CHECKPOINT.md).
Further roadmap implementation is on hold. Each report identifies its own
tested source, artifacts and prior-version comparison.

## Implemented in this batch

| Area | Delivered behavior | Where to start |
| --- | --- | --- |
| Native binary capacity optimization | Bounded exact dynamic programming supplies a checked witness preference and objective bound for one-row Binary capacity models; other search defaults are preserved | [Algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md) |
| Isolation and dependencies | Independent clone/branch, separate agent worktrees/build directories, preserved enhanced baseline, pinned HiGHS source | `source-snapshot.json`, `dependencies.json` |
| Sparse owning model | Five explicit variable domains; ranged linear rows; min/max/offsets; canonical sparse terms; stable model-aware handles, tombstones, revisions and snapshots | `gecode/optimize/model.hpp` |
| Bulk construction | Atomic variable/row batches and explicit CSR input, strong allocation-failure guarantee, geometric growth and no dense matrix allocation | [Bulk API](BULK.md) |
| Result and budget contract | Status separate from incumbent; backend/version attribution; numerical guarantee; missing-bound semantics; normalized/native gaps; shared time/cancellation and node budget primitives | `gecode/optimize/result.hpp` |
| Numerical backend | Optional HiGHS LP/MILP route, explicit unsupported classes/guarantees/scales, deadline-aware candidate capture, one worker per solve | `gecode/optimize/solve.hpp` |
| Independent checking | Structural trust boundary; original bounds, rows, integrality, objective and logical indicators; original-slot solution mapping | `gecode/optimize/validate.hpp` |
| Starts and edits | Numerical partial/complete starts; native exact complete starts with live indicator gate completion and strict improvement search; model edits and historical result ownership | `SolveOptions::primal_start`, `Model` |
| Persistent sessions | Compatible cost/bound/RHS edits retain LP bases; structural/type/owner changes reload; MIP witnesses are revalidated before reuse; fresh options, budgets and callback lifetime per solve | [Sessions](SESSIONS.md) |
| Explicit LP basis starts | Immutable original-model basis records, precise compatibility rejection and accepted/repaired submission reporting, with C/Python ownership | [Basis API](LP-BASIS.md), [Bindings](LP-BASIS-BINDINGS.md) |
| Serial scenario batches | Sparse coefficient, offset, variable-bound and row-side overrides; independent historical results, shared time/cancellation and optional private HiGHS session reuse, with C/Python ownership | [Scenarios](SCENARIOS.md), [Bindings](SCENARIO-BINDINGS.md) |
| Numerical LP evidence | Explicit private auxiliary solves recover checked original feasible bases/improving rays or signed Farkas contradictions; separate availability and raw stage history, with C/Python ownership | [LP evidence](LP-EVIDENCE.md), [Bindings](LP-EVIDENCE-BINDINGS.md) |
| Selected-basis LP sensitivity | Numerical objective-coefficient and equality-RHS intervals, private checked basis factorization without optimization runs, owning results and C/Python lifetime/cancellation behavior | [Sensitivity](LP-SENSITIVITY.md), [Bindings](LP-SENSITIVITY-BINDINGS.md) |
| Local Python wheel | Self-contained macOS arm64 C ABI, automatic package-relative loading, pinned notices and RECORD checks; isolated Python 3.12/3.14 installation tests | [Wheels](WHEELS.md) |
| Continuous LP observations | Owning original activities, two-sided slacks, duals, reduced costs and basis export with independent numerical KKT checking and C/Python access | [LP observations](LP-OBSERVATIONS.md) |
| Native integer route | Explicit `Backend::Native`, actual Space/IntVarArray and branch-and-bound, native reified indicators, exact original-integer witness checking within documented activity limits | [Native bridge](NATIVE.md) |
| Native global registry | Typed all-different, element, table, cumulative, circuit and Regular records; aliases/index bases retained; independent predicates and native compiler; automatic native dispatch for active globals | [Globals](GLOBALS.md) |
| Sparse checked integer LP | Binary and bounded-integer CSR storage, exact dual bounds and interval reductions, sibling-bound restoration and explicit native hybrid API; dense compatibility retained | [Sparse LP](SPARSE-LP.md), [Native LP](NATIVE-LP.md) |
| Native search frontier | Explicit best-bound or depth-first coordinator; exact interrupted global bounds, retained incumbents and bounded live regions, optional checked LP and opt-in bounded binary reliability probes | [Native search](NATIVE-SEARCH.md) |
| Native incumbent neighborhood | Explicit C++ BinaryHamming attempt after a checked incumbent, original-model improvement validation and shared bounded frontier accounting | [Neighborhoods](NATIVE-NEIGHBORHOODS.md) |
| Verified root covers | Budgeted binary cover separation, independent exact cut validation and explicit handoff to native LP/frontier search; separate cut and LP accounting | [Root covers](NATIVE-LP.md#optional-verified-root-covers) |
| Continuous quadratic models | Distinct owning weighted-affine-square model, bounded convex min/concave max through HiGHS QP, original primal/KKT checks and outward tangent bound; C/Python bindings | [Quadratic API](QUADRATIC.md) |
| FlatZinc pipeline | Owning capture, strict whole-model integer/Boolean compiler, supported implications/reifications, all-different/element, table/holey domains, explicit-offset circuit fixed-data cumulative and literal deterministic Regular; independent raw-source witness validation and explicit `fzn-gecode-optimize` CLI | [Compiler](FLATZINC-COMPILER.md), [Driver](FLATZINC-DRIVER.md) |
| Experimental MiniZinc route | Opt-in separate solver identity and dedicated library, explicit millisecond protocol, relocatable build/install registration and real pinned compiler/output checks | [MiniZinc](MINIZINC.md) |
| Exact presolve/postsolve | Signed interval implications, fixed substitution, redundant rows and immutable original/reduced mappings; explicit utility with exact historical witness reconstruction | [Presolve](PRESOLVE.md) |
| Solution pools | Ranked representatives over finite discrete projections, continuous recourse, original witness validation and separate RequestedLimit/Exhausted evidence | [Pools](POOLS.md) |
| Feasibility repair | Explicit weighted L1 row/bound relaxation on a distinct private model; optional ordered original-objective refinement; original residual reporting and separate proof/completion fields | [Repair](RELAXATION.md) |
| C and Python | Versioned C99 owning-handle boundary, immutable results, cancellation, sessions and model I/O; Python ctypes package; installed C consumer and backend-enabled/disabled conformance | [Bindings](BINDINGS.md) |
| Conflict diagnostics | Numerical deletion-minimal groups for rows, bounds, integrality and domains; original attribution and optional deletion witnesses; interruption cannot promote an incomplete conflict | [Diagnostics](DIAGNOSTICS.md) |
| Fast regression gate | Required native CP and numerical cases, plus sessions, diagnostics and exact native bridge; a 28-second whole-command budget and explicit incomplete-case failures | [Fast gate](FAST-REGRESSION.md) |
| Bounded indicators | Conservative domain-derived M, separate binary inactivity gate, preserved original logic, atomic posting, mutation/domain guards and checked removal | [Constraint helpers](CONSTRAINTS.md) |
| Boolean helpers | AND/OR equality, empty/single/multiple inputs, aliases and duplicates; atomic posting | [Constraint helpers](CONSTRAINTS.md) |
| Multiple objectives | Ordered linear stages, explicit degradation, one outer deadline, retained original-model feasible result, no false completion after interrupted stages | [Workflows](WORKFLOWS.md) |
| Model exchange | Strict numerical LP/free-MPS readers; 17-digit output; checked round trips; atomic replacement; explicit unsupported dialects | [I/O](IO.md) |
| Distribution and CLI | Standalone or opt-in native CMake component; installed package aliases; umbrella header; JSON file solver; isolated exact-check benchmark harness | [Build and API guide](README.md) |
| Verification and CI | Independent component tests, full-source sanitizers, cross-feature integration, native regressions, installed consumers, five existing MIPLIB models; added platform CI workflow | [Validation](VALIDATION.md) |

The backend's search, presolve, cuts and heuristics in this new route are HiGHS
capabilities. Native Gecode CP and the checked sparse relaxation remain available through
their original interfaces. The explicit native hybrid adds certificate-checked
LP deductions to native propagation; its results identify both engines. Ordinary
numerical solves continue to use HiGHS search and ordinary native routing is unchanged.

## Roadmap status and deferred completion gates

These gates describe unfinished scope; they are not authorization to start a
new batch after the current integration checkpoint.

| Work package | Status after this batch | Next completion gate |
| --- | --- | --- |
| W0 reproducible foundation | Source isolation/pin, correctness harness and bounded fast regression gate implemented; comprehensive performance baseline still outstanding | Freeze cold/warm tracks, machine/environment accounting and untouched holdout inputs; execute Windows containment CI and full timing gate before enabling that platform |
| W1 original-model IR | Linear numerical model, lifecycle, indicator metadata, six native globals and scoped owning FlatZinc capture/reconstruction implemented; broad capture admission remains | Expand native global registry and capture; measure original-model construction memory |
| W2 result/session contract | Results, budgets, capability query, persistent HiGHS sessions and owning continuous LP dual/basis observations and owning explicit basis submission implemented; cumulative backend usage remains | Interrupted-workflow accounting and action callback contracts; native persistent state |
| W3 usable LP/MILP route | First vertical slice implemented and tested; supported I/O dialect is explicit | Broader LP/numerical/general-integer panels, backend-alone comparisons and unsupported-format fixtures |
| W4 native and FlatZinc integration | Bounded integer linear/indicator native bridge and six typed globals; owning FlatZinc capture with explicit CLI and opt-in MiniZinc registration implemented; broader predicates remain | Broader preserved globals with exact raw-source checks and external CP panels |
| W5 native sparse relaxation | CSR binary and bounded-integer certificates/interval cuts, native propagation and explicit public hybrid bridge implemented and independently tested | Measure root/whole-solve benefit across families before changing defaults; expand exact arithmetic portability |
| W6 presolve/postsolve | Exact bounded-integer interval reductions and fixed substitution with owning reconstruction implemented; numerical route also uses HiGHS presolve | Expand mapped constraints and reductions, budgeted solve composition and measured default selection |
| W7 native branch-and-cut | Proof-carrying scoped pool, binary cover separator, verified root loop and explicit native LP/frontier handoff implemented; dynamic local cuts and broader separation remain | Broader separators, dynamic local-cut lifecycle and measurable root/whole-solve benefit |
| W8 native branching/global bounds | Explicit frontier/global bounds and opt-in bounded binary reliability probes implemented; broader branching and measured default selection remain | General integer/LP-informed scoring and whole-solve benefit across families with protected regressions |
| W9 primal portfolio | Numerical starts, exact complete native starts and one explicit bounded binary incumbent neighborhood implemented; partial native completion and repair/diving/RINS/LNS scheduling remain | Cold-start first-feasible gains, broader neighborhood policies and measured benefit with original-model checking |
| W10 learning/explanations | Architecture/source investigation, isolated pinned SAT protocol experiment and private uncompiled reason-contract header retained; 29,160 experiment queries pass normally and with full dependency sanitizers; no product learning runtime | Checked original-row conditional reason kernel; clone/recompute versus trailed learning pilot; representative benefit before defaults |
| W11 application workflows | Edits, starts, bounded logic, ordered objectives, numerical grouped conflicts, weighted repair, ranked pools, serial scenarios and selected-basis coefficient/equality sensitivity implemented; fine-grained indicator IIS, broader sensitivity and action callbacks remain | Workflow-by-workflow conformance and a backend/feature support matrix |
| W12 distribution/Python | C++ packaging, CLI and CI configuration implemented; versioned C ABI/Python including native globals, workflows and LP evidence; local macOS arm64 wheel implemented; other platforms and executed cross-platform CI remain | Expand typed/workflow binding surface, clean platform builds and installed consumers |
| W13 quadratic/nonlinear | Bounded weighted-square continuous QP with C/Python APIs and independent primal/KKT/bound checking implemented; general Hessians, QCP, MIQP and nonlinear support remain | Broader numerical QP panels and carefully scoped convex quadratic constraints before mixed-integer/nonconvex expansion |
| W14 native parallel hybrid | Not started | Worker-local state, sound shared bounds/cuts, race/lifecycle testing and uncontended scaling measurements |

The seventh integrated checkpoint covers basis submission, Regular and C++
scenario execution, including sanitizer, installed-consumer and wheel checks.
Its FAST gate passed 32 cases in 5.69 seconds external wall time. The eighth
checkpoint adds LP evidence, scenario C/Python bindings and MiniZinc registration,
with full sanitizer, installed-consumer and wheel gates. Its FAST gate passes
all 33 cases in 5.73 seconds external wall time, including analytic ray and Farkas
checks. Exact source and artifacts are listed in [the validation record](VALIDATION.md).
The ninth checkpoint integrates selected-basis LP sensitivity with C/Python
bindings and bounded native incumbent neighborhoods. It passes the enlarged
35-case FAST gate in 5.7852 seconds, all three CTest configurations, full native
sanitizers and fresh installed consumers. Its bounded old/new comparison finds
no repeated material case regression among five complete common-workload pairs;
one additional unchanged native case hits its existing deadline. Full results
and the timing limitation are in [the checkpoint report](NINTH-CHECKPOINT.md).
The separate [learning investigation](LEARNING-DESIGN.md)
has a checked external-propagation interface experiment; it is not yet a native
learning engine. Default performance
selection remains outstanding. Broad capture, cold-start primal portfolios,
LCG, quadratic constraints/nonlinear support, fine-grained application workflows
and native parallel hybrid search remain substantial unfinished work. This
ledger does not declare parity from surface API availability.

The full research/source comparison and work-package acceptance criteria remain
in the workspace's `planning/solver-parity-plan.md`, `feature-matrix.md`, and
`research-agenda.md`. This ledger records implemented scope rather than marking
those larger packages complete on the strength of a few successful fixtures.

## Parallel work and contention

Model, result/budget and validation work first ran in independent worktrees.
The next independent pieces were indicators/Boolean logic, multiobjective
coordination and I/O. Each passed its own checks before cherry-picking into
this branch. Reviewers then checked one another's work; concrete defects became
regression tests before the integrated suite was rerun.

No compilation or solver tests started until the preexisting size-scaling run
reported all 3,240 rows complete and its processes exited. Later builds used
bounded parallelism. All new outputs live under the isolated implementation
build directories; the existing benchmark suite was only read by the new
correctness harness. The five-model checks are explicitly not performance
measurements or evidence of native/commercial speed parity.

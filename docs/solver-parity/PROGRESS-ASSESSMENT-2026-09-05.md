# Progress assessment — 5 September 2026

Assessed at approximately 19:09 UTC against the original 63-row capability matrix,
current implementation checkout and saved independent-agent test artifacts.
This is an engineering assessment, not a commercial-solver conformance claim.

The modeling/API foundation and a useful delegated LP/MILP product are largely
implemented. The larger goal remains substantially unfinished: most of the
hard native-search expansion, learning, nonlinear breadth, parallel integration
and performance/default-quality validation are still ahead. A single percentage
would hide both unequal feature sizes and the difference between an exposed API,
a supported subset and a competitively performing solver.

## What is safe to count as delivered

The last complete integration gate is the eighth checkpoint: functional source
`bda86186d`, documentation/package source `158dc0b66`. It includes sparse modeling,
HiGHS LP/MILP, bounded exact native solving, six typed native globals, checked
sparse native LP, frontier bounds, binary reliability branching, verified root
covers, exact integer presolve/postsolve, starts, numerical sessions, LP
observations/bases/evidence, scenarios, ordered objectives, repair, ranked pools,
scoped quadratic solving, C/Python APIs, FlatZinc/MiniZinc and a local wheel.

- Combined CTest: 60/60; numerical Release: 48/48; backend-disabled: 47/47.
- Full native/HiGHS/facade sanitizer tests: 59/59; Python: 75/75.
- Direct FlatZinc: 106/106; actual MiniZinc pipeline: 72/72; legacy FlatZinc:
  140/140 over five repetitions.
- Installed consumers pass; self-contained macOS arm64 wheel passes 75 Python
  tests on each of Python 3.12 and 3.14.
- FAST: **33/33 in 5.7267 seconds external wall time**, within its 28-second
  allowance and the requested under-30-second limit.
- The last isolation verification matched all 2,963 recorded original source
  hashes and the original branch/commit. New work remains on isolated branches.

These suites overlap. Their counts must not be summed into a number of distinct
industrial benchmark instances. The existing MIPLIB check contains five models;
that is useful correctness evidence, not a comprehensive performance panel.
See [validation](VALIDATION.md) and [the implementation ledger](IMPLEMENTATION.md).

## New work beyond that checkpoint

| Slice | Exact current state | Work before calling it integrated |
| --- | --- | --- |
| LP sensitivity C++ | Runtime committed as `d2fb6153a`; focused root tests pass 3/3 numerical, 3/3 combined, 2/2 backend-disabled | Commit build/umbrella/consumer wiring; full combined/sanitizer/install/FAST gates |
| LP sensitivity C/Python | Source/tests saved, uncommitted in results worktree; logs show 83/83 normal/core Python and C99/cleanup sanitizer checks | Resume interrupted owner, review final source-to-test provenance, finish sanitizer Python/lifetime checks, commit and integrate |
| Native BinaryHamming neighborhood | Independently committed `305020c31`, not yet cherry-picked; 3,640 combined/sanitizer configurations and 3,506 production configurations pass | Integrate source/build/API, add representative FAST coverage, cross-feature/installed checks |
| Learning infrastructure | `2505db942` standalone SAT protocol experiment passes 29,160 enumerated queries normally and with full dependency sanitizers | This is not a Gecode learning solver; implement checked reasons, state/replay, literal channeling and learned search |
| Private integer-row reason API | Header-only commit `51f90c62c` in validation worktree | Runtime, independent reason checker, exhaustive tests and architecture comparison |
| Next general-integer branching | Proposed next assignment; no completed runtime | Design, implementation and original-model bound/partition tests |

The root integration wiring is deliberately still uncommitted at this audit;
this report does not upgrade preliminary changes into the eighth tested release.
The goal service currently reports `usageLimited`; one agent explicitly stopped
on the account usage limit. Its work remains saved. This is an execution blocker,
not a repository correctness failure or a completed goal.

## Remaining effort and realistic endpoints

The estimates below are **experienced-engineer effort**, including design,
implementation, independent review, representative testing and integration.
They are broad planning allowances, not measured agent throughput or promised
elapsed times. Additional subagents do not remove the shared `native.cpp`,
C/Python ABI, integration or uncontended-benchmark dependencies.

| Remaining stream | Planning allowance |
| --- | --- |
| Finish current sensitivity/neighborhood integration and bindings | 1–2 engineer-weeks |
| Broad cold/warm performance baseline, holdouts, direct-backend comparisons and default selection | 4–7 |
| Broader model/front-end coverage and capability contracts | 3–6 |
| Native presolve, dynamic cuts and general-integer/LP-informed branching | 6–10 |
| Native partial starts, repair/diving and broader neighborhood portfolio | 3–6 |
| Explanation/LCG pilot with meaningful nonbinary coverage | 8–16 |
| Remaining modeling/workflows: SOS/PWL, public callbacks, finer diagnostics and composition | 5–9 |
| Linux/Windows/macOS packaging, clean installs and executed platform gates | 3–6 |
| Broader quadratic support and a carefully scoped QCP/MIQP adapter | 6–12 |
| Native hybrid parallel ownership, bounds/cuts and scaling gates | 6–12 |
| **Total for these bounded remaining streams** | **45–86 engineer-weeks** |

Some activities overlap. With three experienced engineers and adequate testing
infrastructure, roughly **6–10 months** is a planning range for that bounded
expanded program; dependency discoveries can extend it. This is not an estimate
that literal complete commercial parity will be reached in that time.

A useful, explicitly scoped LP/MILP release is much closer: approximately **3–6
engineer-weeks** to stabilize the current batch, verify target-platform installs,
exercise representative external LP/MIP/CP cohorts and publish tested scope.
That is a subset of the table above, not additional effort. If broad platform
execution or representative benchmarks are unavailable, this milestone remains
blocked regardless of how quickly more APIs are written.

The literal full goal includes arbitrary nonlinear/global optimization,
production-strength learning, automatic decomposition, robust parallel search,
remote/distributed operation, tuning and commercial-scale numerical robustness.
Several of these exceed the bounded adapter/pilot estimates above. Broad
capability parity is a **multi-year program** unless much more is delegated to
mature engines. Competitive native performance has no defensible completion date
without comparative measurements; implementation effort alone cannot establish it.

## What should change in the next phase

The work has advanced API breadth and careful local correctness faster than
representative performance evidence. The highest-value next step is a release
and benchmark gate, not another broad round of API expansion.

1. Finish the two nearly complete slices and produce one ninth integration gate.
   Keep new experimental implementation in separate worktrees meanwhile.
2. Establish uncontended native-versus-native and wrapper-versus-direct-HiGHS
   comparisons, then CP-SAT/Chuffed and commercial baselines where available.
   Separate feasibility, optimization, proof, infeasible and numerical cases;
   preserve unseen family holdouts. Include memory, first solution, time/gap and
   time-to-proof rather than a solved-count-only score.
3. Ship the conservative supported route once its install and external-cohort
   gates pass. Keep native heuristics experimental until they show a measured
   benefit without protected regressions.
4. Focus algorithm work on general-integer branching/cuts and one bounded
   learning pilot. Reuse a mature nonlinear backend for breadth when appropriate;
   building an entire nonlinear global engine is a different scale of project.
5. Make roadmap completion conditional on accepted workload and workflow gates.
   A frozen final scope is essential: matching the union of two evolving solver
   products is not a finite acceptance test by itself.

## Updated disposition of all 63 original comparison rows

“Delivered subset” means useful implemented behavior with the stated boundary,
not complete equivalence to either commercial product. “Preserved” credits
existing Gecode functionality, not newly implemented work. “Missing natively”
does not imply the delegated HiGHS engine lacks that algorithm. This table
updates the implementation side of the original dated comparison; it does not
claim a fresh audit of vendor releases.

| # | Original capability | Current disposition | Evidence boundary / remaining work |
| --- | --- | --- | --- |
| 1 | Binary linear optimization | Delivered subset | Numerical MILP through HiGHS; exact bounded native integer route. Commercial speed comparison outstanding. |
| 2 | General bounded integer optimization | Delivered subset | General integers in numerical MILP and finite integral native subset; hybrid arithmetic admission remains bounded. |
| 3 | Continuous LP and mixed continuous/integer models | Delivered subset | Continuous LP and mixed continuous/integer models through HiGHS, with original-model checks. |
| 4 | Free variables, infinite bounds and unbounded-model status | Delivered subset | Numerical free/infinite domains and distinct unbounded statuses; native route remains finite. |
| 5 | Sparse ranged linear rows and bulk matrix construction | Delivered subset | Canonical sparse ranged rows, CSR batches and stable original mappings. Large-model memory study remains. |
| 6 | Objective sense, offset and coefficient domains | Delivered subset | Min/max, offsets and floating coefficients numerically; explicitly bounded integral native guarantees. |
| 7 | Set variables and CP globals: distinct, table, regular, circuit, cumulative | Partial | Six typed globals and original Gecode facilities preserved. Set domains and full global catalog are not in the additive API. |
| 8 | Scheduling intervals, optional tasks, sequences and calendars | Mostly missing | Fixed-data cumulative exists; interval/optional-task/sequence/calendar facade remains. These are primarily CP Optimizer comparisons. |
| 9 | Reification, indicators, min/max/abs and Boolean logic | Partial | Indicators, AND/OR and scoped FlatZinc reification exist; complete retained min/max/abs/general-constraint surface remains. |
| 10 | SOS1 and SOS2 | Missing | No retained SOS1/SOS2 API or tested backend lowering. |
| 11 | Semi-continuous and semi-integer variables | Delivered subset | Explicit semi-continuous/semi-integer numerical types; bounded SemiInteger native support. |
| 12 | Piecewise-linear functions/objectives | Missing | No retained PWL model/objective API or breakpoint/extrapolation contract. |
| 13 | Continuous convex QP | Partial | Bounded continuous weighted-affine-square QP only; arbitrary Hessians, unbounded domains and workflow composition remain. |
| 14 | Mixed-integer quadratic objective (MIQP) | Missing | MIQP adapter/model class not implemented. |
| 15 | Convex QCP/MIQCP and SOCP | Missing | QCP/MIQCP/SOCP model and solve routes not implemented. |
| 16 | Global nonconvex quadratic objective | Missing | No global nonconvex quadratic solve route. |
| 17 | General nonconvex quadratic constraints | Missing | No general nonconvex quadratic-constraint route. |
| 18 | General multivariate nonlinear optimization | Missing | No nonlinear expression graph/domain/global solver route. |
| 19 | Specialized finite-domain propagation | Preserved/partial | Existing native propagation retained; six typed globals exposed. Explained propagators remain future work. |
| 20 | Sparse LP relaxation, simplex/barrier and hot starts | Partial | HiGHS numerical LP and basis reuse; native sparse checked relaxation. User algorithm selection and broad LP performance panel remain. |
| 21 | Certified LP-derived objective bounds | Delivered subset | Exact checked LP-derived native bounds under bounded integer arithmetic assumptions; not general continuous certification. |
| 22 | Farkas infeasibility and unbounded rays | Partial | Numerical checked original rays/Farkas evidence delivered. Exact Farkas-driven native pruning and full proof chain remain. |
| 23 | Reduced-cost/conditional fixing | Partial | Checked native interval/conditional reductions exist in bounded subset; broader reduced-cost fixing and performance evidence remain. |
| 24 | Presolve and postsolve | Partial | Exact interval/fixed-substitution/postsolve utility plus delegated HiGHS presolve. Probing, aggregation and broader native reductions remain. |
| 25 | Static root strengthening | Delivered subset | Verified binary root covers with explicit budgets and handoff; broader strengthening and measured benefit remain. |
| 26 | Dynamic cut separation, selection and aging | Mostly missing natively | Scoped cut infrastructure exists; dynamic local separation, selection/aging and MIR/GMI/clique breadth remain. HiGHS owns its own cuts. |
| 27 | LP-informed reliability/strong branching | Partial | Bounded binary reliability probing exists. General-integer/LP-informed branching and calibrated policies remain. |
| 28 | Global frontier bounds and best-bound/hybrid node selection | Delivered subset | Explicit native best-bound/depth-first frontier with honest interrupted bounds; broader policies/performance work remains. |
| 29 | Restarts, portfolio search and branch-path nogoods | Preserved/partial | Legacy restart/portfolio/path-nogood mechanisms remain. Full integration with new hybrid coordinator remains. |
| 30 | Propagation explanations, CDCL/LCG and backjumping | Research/header only | 29,160-query external-SAT protocol experiment and private reason header; no product LCG, conflict analysis integration or learned search. |
| 31 | Primal rounding, repair, diving and feasibility heuristics | Mostly missing natively | Checked complete starts exist; native partial completion, repair, rounding/diving and cold-start portfolio remain. HiGHS has its own heuristics. |
| 32 | Large neighborhood search and incumbent improvement | Ready to integrate subset | One bounded BinaryHamming incumbent-improvement attempt passes isolated tests; general LNS/RINS/adaptive scheduling remains. |
| 33 | Symmetry handling | Preserved/mostly missing automation | Legacy explicit symmetry facilities retained; automatic detection and new-API integration remain. |
| 34 | Network simplex/flow structure | Missing specialized route | Generic LP exists; no dedicated network extraction/solve API. |
| 35 | Automatic decomposition, Benders and column-generation infrastructure | Missing | No automatic Benders or column-generation infrastructure. |
| 36 | Retained named model, stable handles, introspection | Delivered subset | Owning named models, stable owner-aware handles, revisions, tombstones and introspection. |
| 37 | Edit/remove/change coefficients and reoptimize | Delivered subset | Safe model edits; numerical sessions reuse compatible bases and checked hints. Native persistent state remains. |
| 38 | Automatic use from ordinary native/FlatZinc clients | Partial | Explicit native/FlatZinc compiler and optional MiniZinc registration. Broad ordinary-client capture and unsupported predicates remain. |
| 39 | Bulk C++/Python model building | Delivered subset | Bulk C++ and Python construction through C ABI; full matrix-shaped modeling conveniences remain workload-driven. |
| 40 | Single and multiple objective workflows | Partial | Ordered linear objectives implemented. Full weighted/prioritized combinations and quadratic workflow composition remain. |
| 41 | Structured status, incumbent, global bound, gap and quality | Delivered subset | Structured statuses, incumbent/bound/gap/quality and provenance; some cumulative backend telemetry remains. |
| 42 | Shared deadlines and cancellation | Delivered subset | Shared monotonic deadlines/cancellation and bounded workflow accounting. Cooperative backend regions are not hard-preemptible. |
| 43 | Starts, hints, priorities and repair | Partial | Numerical partial hints and exact native complete starts; priorities, native partial completion and repair remain. |
| 44 | Basis/primal/dual warm starts | Partial | Owning selected bases and compatible session reuse implemented; broader primal/dual starts and native state remain. |
| 45 | Dual values, reduced costs and sensitivity ranges | Partial/new slice | Duals/reduced costs integrated. Coefficient/equality selected-basis sensitivity C++ integrated with focused tests; bindings/full gate pending. Bound/ranged-side sensitivity remains. |
| 46 | Named IIS/conflict diagnosis | Partial | Grouped numerical deletion-minimal conflicts implemented; fine-grained indicators/globals, assumptions/cores and broader diagnosis remain. |
| 47 | Feasibility relaxation/soft-constraint repair | Partial | Weighted L1 repair with protected constraints and original-objective refinement; full penalty/model-class breadth remains. |
| 48 | Solution pools, diversity and k-best guarantees | Partial | Ranked finite projection pools and recourse/exhaustion semantics implemented; diversity and more efficient pool search remain. |
| 49 | Progress/log/solution callbacks | Missing public API | Internal backend callbacks capture candidates/cancellation; public progress/log/incumbent event contract is not exposed. |
| 50 | Lazy constraints, user cuts and candidate submission | Missing public API | No public lazy-constraint, user-cut or candidate-submission action callbacks. |
| 51 | Scenario analysis/batched modified models | Delivered subset | Serial sparse scenario batches with owning results and optional session reuse; no native multi-scenario tree sharing. |
| 52 | Model/solution/basis import, export and replay | Partial | Strict LP/free-MPS model I/O and FlatZinc capture. Broader dialects and portable solution/basis/replay serialization remain. |
| 53 | Backend/model/workflow capability negotiation | Partial | Backend queries and explicit rejection exist; comprehensive model/workflow-combination negotiation remains. |
| 54 | Robust automatic solver/search defaults | Validation pending | Conservative Auto routing exists; no broad external evidence supporting newly tuned out-of-box native defaults. |
| 55 | Parallel search and worker ownership | Not started for new hybrid | Legacy parallel search retained; new adapter uses one worker and hybrid parallel ownership/bounds/cuts remain. |
| 56 | Reproducibility and deterministic modes | Partial | Deterministic supported one-worker settings; reproducible parallel scheduling and cross-platform gates remain. |
| 57 | Exact versus numerical correctness contract | Partial | Numerical/exact guarantees kept distinct with checked bounded deductions. No end-to-end general proof-certificate route. |
| 58 | Installable API package and dependency isolation | Delivered local subset | CMake installed consumers, independent dependencies and self-contained macOS arm64 wheel pass. Broader clean-machine distribution remains. |
| 59 | Platform/compiler portability | Validation pending | Platform CI configuration exists; recorded execution is local macOS arm64. Linux/Windows/MSVC and other wheel gates remain. |
| 60 | Remote, batch and distributed execution | Not started | No remote/distributed execution service or worker infrastructure. |
| 61 | Parameter tuning and reusable profiles | Not started | No measured automatic tuner or held-out reusable profile program. |
| 62 | Large-model memory and resource controls | Partial | Sparse storage and explicit logical/work/frontier limits; comprehensive large-model/RSS/worker resource testing remains. |
| 63 | Regression testing, proof checking and performance provenance | Partial | Strong local correctness/sanitizer/install evidence and FAST delivered. Broad uncontended external performance and independent full proofs remain. |

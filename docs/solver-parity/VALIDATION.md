# Validation record

## Adaptive native size-boundary method

The [adaptive study](ADAPTIVE-BOUNDARIES.md) has sixteen focused generator and
runner tests covering preserved input blocks, larger original-model validation,
independent version searches, confirmation and budget gates. Each version stops
expanding after a failed size and searches its remaining bracket; later failed
confirmations remain recorded. Independently checked witnesses establish original
feasibility and objective values. Exact optimality remains a backend claim;
there is no independent reference-optimum computation during adaptive trials.
The earlier fixed studies retain their own measurements and validation records.

## Seven-category native scaling measurement

The [category scaling study](CATEGORY-SCALING.md) records all 132 observations
from 33 frozen cases, two paired repetitions and ten-second solver limits.
All returned original-model witnesses validate. Before reports 50 Optimal and
16 TimeLimit results; current reports 58 Optimal and 8 TimeLimit. Whole
invocation: 277.4355438 seconds. Knapsack's main size requires both distributions
and both repeats, rising from 32 to 384 model variables. Assignment, facility,
bin packing, production, routing and queen maxima remain unchanged. The
single-variant 512-item stress group is retained separately and remains capped.

Eight new generator tests and nine runner tests pass. Solver source/product and
the frozen ten-second driver are unchanged; loader and final integrity checks
pass. The earlier 52-run capacity study below remains a separate study,
not additional repetitions of this panel. No censored speed ratio or true
maximum problem size is claimed.

## Native capacity scaling measurement

The [capacity scaling study](CAPACITY-SCALING.md) records all 52 observations
from 13 frozen cases, two alternating paired repetitions and ten-second internal
solver limits. All 52 returned witnesses pass independent original-model checks.
Before proves 16/26 optima; current proves 24/26. Largest tested size proved twice
rises from 32 to 384 variables in both knapsack distributions, while assignment
remains at 256. The 512-variable stress point stays in the capacity calculation;
both versions time out in both repetitions. Whole invocation: 150.1307507 seconds.

Eighteen generator/runner tests pass in 1.430 seconds. All five current runtime
library hashes match the previous algorithm checkpoint; solver source and product
are unchanged. A newly frozen driver accepts the ten-second argument for both
cohorts, preserving the older study's driver. The public record includes every
observation, frozen model/reference, provenance and integrity result. No timing
ratio uses an unfinished solve, and no true maximum size is inferred.

## Bounded native capacity algorithm

The [algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md) supersedes the older
current-version wording below. It adds capped exact binary capacity optimization
and preserves generic search defaults after rejecting an ordering pilot.
Current Release CTest passes 70/70, including Python 84/84; the affected native
ASan/UBSan gate passes 12/12, and the new backend-disabled boundary case passes.
The independent native test covers 1,494 oracle/budget configurations, with
separate deterministic mid-table cancellation/allocation checks. The original
checkout still matches all 2,963 recorded hashes. Final FAST passes 35/35 in
5.8439 seconds; capture fixtures pass 13/13. All 60 paired benchmark witnesses
pass independent checks: before completes 24/30 runs and after 30/30. The
checkpoint retains all timings, control slowdowns and rejected pilot outcomes.

Earlier reports retain their own measured source, configuration and scope.

## Final review and PR preparation

The final review corrects public API comments, documents Python's existing
four-space convention, and replaces workstation-only documentation links.
All C/C++ edits in this follow-up are comments; the measured solver binaries
remain unchanged. Python `Model.read` now allocates its owner before importing
a C model, preventing a handle leak when Python allocation fails. The combined
library passes all **84 Python tests**, including the new allocation regression.

The benchmark reproduction runner now bounds captured output and cleans up
process groups on successful exit, timeout, interruption and exceptions.
Its **seven short Python-fixture tests pass**; these tests run no benchmark
solver. The website separately pins the audited report hashes before importing
its hand-reviewed narrative. Changed evidence is rejected even with Python
assertions disabled, without overwriting the public snapshots. These follow-up
checks do not replace or alter the measurements below.

## Before-project benchmark page and native documentation

The [before/after report](BENCHMARKS.md) records a fresh 54-run comparison of
preserved pre-project binaries and the ninth integrated product: five binary
optimization models and four original native FlatZinc fixtures, three paired
repetitions each, two-second solver limits. Known-optimal binary completion is
3/15 before and 15/15 now, with exact checks of returned integer witnesses.
The twelve unfinished old runs remain censored. Native CP matches all 12/12
expected-output checks per version, while its tiny end-to-end times are longer
in the current shared-library build. No generic speedup is inferred.

The fresh FAST gate passes 35/35 in 5.8003 seconds external wall time. Compiled
product remains `c2fabb78f`; only documentation, benchmark tooling and the
separate website change in this batch. The native Doxygen overview, chapters
and support matrix were checked against current public APIs. Focused Doxygen
1.18.0 generation passes, and 106 local links/assets/anchors across the new guide
and benchmark page resolve. This is not a full original-library documentation
build; legacy references outside the focused preview have documented warnings.
Both CMake and Autoconf documentation targets include the new source and data.

The website imports recorded measurements without solving; its data checks
verify every displayed median, completion count and missing censored time.
Production compilation and TypeScript checks pass. A portable export reuses
the same page component and built CSS, with the generated native guide and
all page data included. Hosting is not claimed while the existing Site is
unavailable to the connected account.

## Ninth batch: integrated sensitivity and native neighborhoods

The [ninth checkpoint report](NINTH-CHECKPOINT.md) records the completed
integration, exact tested source, correctness gates, fresh installed consumers
and matched comparison with the eighth checkpoint. Combined CTest passes
67/67, numerical Release 54/54, backend-disabled Debug 52/52, full native/HiGHS
ASan+UBSan 66/66, and preloaded sanitizer Python 83/83. Installed consumers
pass 8/8 and Python 83/83 in all three configurations. The expanded FAST gate
passes 35/35 in 5.7852 seconds external wall time.

Five complete paired runs of the 33 common FAST cases pass 330/330 executions;
median command time is 5.6303 seconds previously and 5.7401 seconds currently.
No case triggers the repeated >20% and >1 ms diagnostic threshold. One extra
attempted current panel times out in unchanged `cp_distinct` under the existing
four-second cap; its failure is retained and excluded from complete-pair timing
medians. Three paired five-model MIPLIB panels pass all 30 exact witness and
known-optimum checks. See the report for full limitations and artifacts.

This completes the user-requested integration checkpoint. Further roadmap work
is on hold. The earlier records below describe their historical checkpoints;
in particular the eighth wheel has not been rebuilt for these additions.

## Standalone W10 interface experiment after the eighth checkpoint

The separate `tools/research` target passes **29,160 queries** with both the
normal pinned CaDiCaL library and the full dependency/fixture instrumented by
ASan+UBSan. Each run finds 14,936 SAT and 14,224 UNSAT queries, checks 3,693
external lemmas by finite enumeration, streams 64 delayed/on-demand reasons,
and exercises 168 rejected complete models. Ten reason streams occur after
intervening notification/decision events. The eight-variable cancellation and
resume fixture additionally checks the resumed original witness. The counters
are protocol coverage, not a performance comparison or a Gecode learning result.

Evidence is in `build/w10/validation.json`, `cadical-protocol.json`,
`w10-protocol.json`, `w10-protocol-sanitize.json`, and `cmake-*-test.log`;
the aggregate records the final fixture SHA-256
`5f1bd71b7646882f137f128a0286d382412d07339355218635dd95e7676570cb`.
CTest passed 1/1 in each independent build. Both source/header/library provenance
records are retained in `build/w10-protocol*/dependency-provenance.txt`.
The library source is the clean tracked CaDiCaL 3.0.1 commit
`c60730422e758ef1cebe7aeddf2dda31c996bf04`; generated untracked build directories
remain in that separate dependency. Its upstream example also passed normally.
The full sanitizer build uses `-fsanitize=address,undefined`, frame pointers,
assertions and `-O1`; leak detection was disabled, with halt-on-error enabled
for ASan and UBSan. No Gecode product libraries were rebuilt for this experiment.

The first manual fixture run incorrectly asserted that setting `quiet` must
succeed; a dependency compiled with `-DQUIET` omits that option. The fixture now
tolerates that documented compile-mode difference. Upstream configure also
prints errors when creating its convenience `src/makefile` symlink under a path
with spaces. Building explicitly inside each generated build directory succeeds;
the tracked upstream source was not patched. All dependency configure/build logs
are retained in `../deps/CaDiCaL-3.0.1/build-optimize-{spike,sanitize}`.

See [the learning design](LEARNING-DESIGN.md) for interpretation, uncovered
production failure/lifecycle cases and the next checked-reason implementation.
This experiment does not advance the product's eighth integrated checkpoint.

## Eighth batch: LP evidence bindings and MiniZinc registration

Compiled functional source `bda86186d`, with documentation-only head
`158dc0b66f02929c9be957cdcad651581dd7be3f` for the final FAST and wheel gates,
tested 2026-09-05 UTC on the same Apple M1 Pro/macOS/AppleClang host and pinned
HiGHS 1.15.1. This checkpoint adds numerical LP evidence recovery, its C/Python
bindings, scenario C/Python bindings, and the explicit MiniZinc 2.10.1 route.
The sensitivity header/private compile bridge is present but its analyzer and
bindings are subsequent work. Native neighborhoods and LCG are also excluded.

| Check | Result | Local evidence |
| --- | --- | --- |
| Combined native/numerical and FlatZinc boundary tests | 60/60 pass | `build/native-compat/eighth-expanded-ctest.log` |
| Numerical Release | 48/48 pass | `build/optimize/eighth-ctest.log` |
| Backend-disabled Debug | 47/47 pass | `build/optimize-core/eighth-expanded-ctest.log` |
| Full-source HiGHS/facade ASan+UBSan | 47/47 pass | `build/optimize-sanitize/eighth-expanded-ctest.log` |
| Full-source native/HiGHS/facade ASan+UBSan | 59/59 pass; preloaded Python 75/75 | `build/native-sanitize/eighth-ctest.log`, `eighth-python-preloaded-sanitizer.log` |
| Actual direct FlatZinc CLI | 106/106 normal and sanitizer | `build/{native-compat,native-sanitize}/eighth-final-cli.json` |
| Actual generated MiniZinc build registration | 72/72 normal and sanitizer, including compiler/driver/output pipeline; pure JSON encoder 10 cases | `build/{native-compat,native-sanitize}/eighth-final-minizinc.json`, CTest logs |
| Installed MiniZinc registration | 72/72 with actual relative executable/library paths; existing Gecode registration unchanged | `build/native-compat/eighth-final-installed-minizinc.json` |
| Legacy FlatZinc with blackbox fixtures | 140/140, five repetitions each, seed 1701 | `build/native-compat/eighth-legacy-flatzinc.log` |
| Installed C/C++ consumers | Numerical, combined and core: 7/7 each; independent native-only 1/1 | `build/optimize/eighth-installed-consumers.json` |
| Python against installed libraries | 75/75 in each of those three configurations | `build/{optimize,native-compat,optimize-core}/eighth-installed-*.log` |
| Self-contained macOS arm64 wheel | Automatic Native/HiGHS load and 75/75 on both Python 3.12 and 3.14 | `build/eighth-wheel-pack.json`, `eighth-wheel-installed-results.json` |
| Runner and containment contracts | 24 pass, 9 actual-Windows checks explicitly skipped | `build/native-compat/eighth-harness-tests.log` |
| Required FAST gate | **33/33 pass, 5.73 seconds external wall**, 5.68 inside runner | `build/optimize/eighth-fast.json`, `eighth-fast-wall.json` |
| Existing MIPLIB correctness panel | 5/5 exact witness and known-optimum checks pass | `build/optimize/eighth-miplib-correctness.json` |
| Original checkout isolation | All 2,963 hashes, branch and commit unchanged | `build/optimize/eighth-original-isolation.json` |

The new FAST case checks original feasible bases and improving directions for
both objective senses, fixed-column and row recession conditions, historical
ownership, private auxiliary identities and public solve-call counts. Its Farkas
case independently checks signed multipliers `y=1,z=-1`, finite-side selection
and a positive contradiction margin. The output is `evidence_checked`, with no
source objective values invented from slopes or margins. The full suite retains
the 28-second outer allowance and hashes both executables and twelve libraries.
All three agents explicitly paused builds/tests and the root test processes
exited before timing. A read-only process inventory found no competing task
compiler or solver; ordinary desktop background processes remained. This is a
correctness timing gate, not a commercial-solver performance comparison.

Evidence conformance covers independently checked original coordinates and
separate primal-ray/Farkas availability, bad auxiliary identity/scalars/status,
finite-side normalization, tolerance overlap and phase/final cleanup failures.
The C wrapper's separately compiled cleanup fixture cancels after a real accepted
analysis returns: every accepted getter becomes unavailable while raw owning
auxiliary-stage children remain usable. No auxiliary stage becomes an ordinary
original-model result. C99 fixtures explicitly preserve assertions in Release.

MiniZinc tests use the official workspace-local 2.10.1 compiler and matching
standard library. CMake never downloads it. The generated experimental identity
uses Native/Exact with its separate millisecond protocol and dedicated lowering
library. Both build and installed registration files are exercised in place;
configuration and library hashes must remain unchanged. The existing installed
`gecode.msc` matches the seventh checkpoint byte-for-byte (SHA-256
`18e34e3d2dfe96d77e6db410ade28aad2e30c629701c622fb5585e73ab1be463`).
No default solver preference was changed. Supported source-level answers and
emitted predicates are tested; general compiler equivalence is not proved.

The wheel is
`gecode_optimize-0.1.0.dev20260905+g158dc0b66-py3-none-macosx_11_0_arm64.whl`,
SHA-256 `f1506dc6b1c629e104e8903ee5c9960cdeb6978ed5eb42bb0a5b556d79a377a5`.
Its solver-library SHA-256 is
`67cd47986b72fc91fe3c1f5d8b883b911fda81f2193bbe65d81a00b77e52c006`.
The first manual Python 3.12 provenance assertion used a nonexistent private
loader name and failed before tests ran. Correcting that validation command
required no package/source change; final logs assert both module and loaded
library are inside the isolated environment, then pass all 75 tests on each
interpreter. The failed setup log is retained.

No package-index publication, remote CI, actual Windows/Linux runtime gate,
oldest-macOS execution or broad performance baseline is claimed. macOS sanitizer
leak detection remains disabled for the host runtime limitation; ASan/UBSan
error detection is enabled. LP evidence is numerical, not an exact certificate.

## Seventh batch: explicit basis starts, Regular, scenarios and Python wheels

Compiled facade through `77ee30327` and final installed-consumer/FAST source
`b8e3fba7f152a14c4460f3c6946c488ce59093bc`, tested 2026-09-05 UTC on the
same Apple M1 Pro/macOS/AppleClang host with pinned HiGHS 1.15.1. The first full
cohort used `5914ee047`; subsequent fixes keep C consumer assertions enabled,
classify the native Regular FAST case correctly, reject unsupported scenario
guarantees at admission and accept three exact MiniZinc context-marker atoms.
The affected component tests and installed consumers were rerun after those
fixes. All facade and test objects were rebuilt for the enlarged Regular
`GlobalPayload`; no old-layout facade archives were reused.

| Check | Result | Local evidence |
| --- | --- | --- |
| Combined native/numerical plus original regression target | 55/55 pass; assertions-enabled C consumers 2/2; final affected tests 7/7 | `build/native-compat/seventh-integrated-ctest.log`, `seventh-c-assertions-ctest.log`, `seventh-admission-ctest.log` |
| Numerical Release | 43/43 pass; final affected tests 4/4 | `build/optimize/seventh-integrated-ctest.log`, `seventh-admission-ctest.log` |
| Backend-disabled Debug | 42/42 pass; final affected tests 4/4 | `build/optimize-core/seventh-integrated-ctest.log`, `seventh-admission-ctest.log` |
| Full-source HiGHS/facade ASan+UBSan | 42/42 pass; final affected tests 4/4 | `build/optimize-sanitize/seventh-integrated-ctest.log`, `seventh-admission-ctest.log` |
| Full-source native/HiGHS/facade ASan+UBSan | 52/52 pass; final affected tests 7/7; preloaded Python 62/62 | `build/native-sanitize/seventh-integrated-ctest.log`, `seventh-admission-ctest.log`, `seventh-python-preloaded-sanitizer.log` |
| Actual FlatZinc CLI | 106/106 in normal and full sanitizer configurations | `build/{native-compat,native-sanitize}/seventh-final-cli.json` |
| Legacy FlatZinc with configured blackbox fixtures | 140/140 pass | `build/native-compat/seventh-final-legacy-flatzinc.log` |
| Installed C/C++ consumers | Three configurations: 5/5 each, including basis/Regular C consumers and scenario C++ behavior; independent native-only 1/1 | `build/optimize/seventh-installed-consumers.json`, `seventh-final-installed-results.json` |
| Python against installed libraries | 62/62 in each of three configurations | `build/{optimize,native-compat,optimize-core}/seventh-final-installed-*.log` |
| Self-contained macOS arm64 wheel | Automatic Native/HiGHS load, RECORD/bytecode checks and 62/62 methods on both Python 3.12 and 3.14 | `build/seventh-wheel-integrated-pack.json`, `seventh-wheel-integrated-installed-results.json` |
| Runner and containment contracts | 24 pass, 9 actual-Windows checks explicitly skipped | `build/native-compat/seventh-harness-tests.log` |
| Required FAST gate | **32/32 pass, 5.69 seconds external wall**, 5.62 inside runner | `build/optimize/seventh-fast.json`, `seventh-fast-wall.json` |
| Existing MIPLIB correctness panel | 5/5 independent exact witness/known-optimum checks pass | `build/optimize/seventh-miplib-correctness.json` |
| Original checkout isolation | All 2,963 hashes, branch and commit unchanged | `build/optimize/seventh-original-isolation.json` |

The FAST run had a clean source head, explicit quiet acknowledgments from every
agent and a process inventory with no competing compiler or solver. It hashes
both executables and twelve runtime libraries. New cases independently enumerate
a signed Regular parity language (exact objectives -3/1) and check analytic
scenario objectives 5/9/-11/7 with both cold and reused solves. The LP observation
case now also exports and submits an owning basis. The outer budget stays at
28 seconds. This is a bounded correctness regression gate, not evidence of
commercial or native performance parity.

Regular admission/checking covers sparse large state namespaces, signed symbols,
missing edges, aliases, empty words/finals, determinism, native array/hash limits,
FlatZinc literal schemas and original raw-table checks. Scenario tests compare
360 outcomes with 3,840 independent original assignments, and inject bad identity,
status, exact bounds, raw witnesses and interruptions. Unsupported Certified and
Auto/HiGHS Exact requests are rejected before a batch starts. Basis tests cover
status/owner/revision/matrix compatibility, rejected or repaired submissions,
original optimality checks and session recovery.

The initial new C consumer targets inherited Release `NDEBUG`; their source now
explicitly enables assertions and their Release checks were rerun. The first
manual legacy selection omitted optional blackbox environment variables and
selected only 118 tests. A second attempt used an incorrect local fixture-library
path and stopped at that fixture; the final run uses the configured executable
and library paths, separate log files and seed 1701, passing all 140 tests.
These setup attempts are retained in the local logs.

The wheel artifact is
`gecode_optimize-0.1.0.dev20260905+g2e19db01d-py3-none-macosx_11_0_arm64.whl`
(SHA-256 `108a5b81b57aa6c6ebe66c1b668fa4bd3f0d3ffe6b418aa62eba72dae1a16701`).
It was built with macOS 11.0 deployment settings and tested on this newer host;
oldest-OS compatibility is not claimed as tested. Ten portable adversarial
packager tests also pass, including staged-byte inspection during source
replacement, dependency traversal and corrupt/missing RECORD entries. No package
index publication, actual Windows execution, remote CI or broad performance
baseline was performed. macOS sanitizer leak detection remains disabled because
of the host runtime limitation; ASan/UBSan error detection remains enabled.

Scenario C/Python bindings, explicit LP evidence and experimental MiniZinc
registration are subsequent isolated work and are excluded from this checkpoint.

## Sixth batch: starts, original LP observations and preserved FlatZinc globals

Integrated source through `5e22c417f6824981f8a705b29af1b7c352717f10`, tested
2026-09-05 UTC on the same Apple M1 Pro/macOS/AppleClang host with pinned HiGHS
1.15.1. Compiled changes are through `7364d7a77`; subsequent commits add
cumulative CLI fixtures and scenario design only. This gate adds exact complete
native starts, owning continuous LP observations with C/Python access, and
FlatZinc table/holey-domain, circuit and fixed-data cumulative admission.
Basis submission, scenario execution and regular-language constraints are
separate subsequent work and are excluded from this gate.

| Check | Result | Local evidence |
| --- | --- | --- |
| Combined native/numerical plus original regression target | 48/48 pass | `build/native-compat/sixth-observations-ctest.log` |
| Numerical Release | 36/36 pass | `build/optimize/sixth-observations-ctest.log` |
| Backend-disabled Debug | 36/36 pass | `build/optimize-core/sixth-observations-ctest.log` |
| Full-source HiGHS/facade ASan+UBSan | 35/35 C/C++ tests pass | `build/optimize-sanitize/sixth-observations-ctest.log` |
| Full-source native/HiGHS/facade ASan+UBSan | 45/45 optimization/capture tests pass; 47 Python methods pass with runtime preloaded | `build/native-sanitize/sixth-observations-final-ctest.log`, `sixth-python-preloaded-sanitizer.log` |
| Expanded actual FlatZinc CLI | 79/79 cases pass in normal and full-source sanitizer builds | `build/{native-compat,native-sanitize}/sixth-cumulative-cli-final.json` |
| Complete legacy FlatZinc selection | 140/140 pass | `build/native-compat/sixth-final-legacy-flatzinc.log` |
| Fresh installed C/C++ consumers | Standalone numerical, combined and backend-disabled: 3/3 each; independent native-only: 1/1 | `build/consumer-*-sixth/`, `build/optimize/sixth-installed-consumers.json` |
| Python against freshly installed libraries | 47/47 methods pass in each of three configurations | `build/{optimize,native-compat,optimize-core}/sixth-installed-*.log` |
| Runner and containment contracts | 24 pass; 9 actual-Windows checks explicitly skipped | `build/native-compat/sixth-harness-final-tests.log` |
| Required FAST gate | **30/30 pass, 5.48 seconds external wall**, 5.40 seconds inside runner | `build/optimize/sixth-fast.json`, `sixth-fast-wall.json` |
| Existing MIPLIB correctness panel | 5/5 independent exact witness/known-optimum checks pass | `build/optimize/sixth-miplib-correctness.json` |
| Original checkout isolation | All 2,963 hashes, original branch and commit unchanged | `build/optimize/sixth-final-original-isolation.json` |

The final FAST run used a clean source head, explicit quiet acknowledgments from
all three agents, and a process inventory showing no competing build or solver
workload. Both executables and twelve runtime libraries are hashed. The new
native-start case checks gate completion and strict min/max improvement to
enumerated optima -4/7. The LP observation case checks analytic optima 15/19,
original dual signs, reduced costs, slacks, basis availability and independent
KKT acceptance. The outer budget remains 28 seconds. This local correctness
timing is not a commercial/native performance comparison.

Normal and core/numerical tests were run after source integration. The later
CLI-only commit expands 64 cases to 79 without changing the compiled solver;
the final 79-case checks were rerun in both normal and sanitizer configurations.
Cumulative compiler tests independently evaluate 248,201 assignments. Actual
legacy CLI execution rejects a zero-duration singleton with height above
capacity; the new path accepts it because its half-open resource interval is
empty. The positive-duration counterpart is infeasible. Raw original-source
checking and independent integer-time oracles cover both behaviors, aliases,
overlap, shared endpoints, malformed shapes and unsupported machine variants.

Native starts are checked before incumbent publication, including exact
original feasibility, live indicator gate derivation, explicit retained gates,
historical ownership, interrupted search and strict improvement completion.
LP observations check original row/column mapping, min/max conventions, large
offset cancellation, malformed backend data, independent KKT residuals, basis
availability, copied ownership and final-budget publication. Fresh installs
include the public LP observation header and exclude its private detail header.

The initial native sanitizer CTest command also selected an unnecessary rebuild
of the legacy test harness. That owned process tree was stopped before running
the established optimization/capture selection, which passed all 45 tests.
Legacy regression evidence in this batch comes from the normal combined build;
the solver modules and dependencies used by the sanitizer selection are fully
instrumented. No sanitizer detector was disabled beyond the existing macOS
leak-detection limitation. The combined installed consumer initially omitted
its separately installed HiGHS dependency prefix; configuring it with the fresh
standalone-sixth HiGHS install passed. Logs retain both attempts. No remote CI,
actual-Windows gate, or broad performance baseline was executed.

## Fifth batch: quadratic models, FlatZinc and native search extensions

Integrated implementation `8ae59d5c1946abf47203172ba3cb89fbf5ea0a8b`, tested
2026-09-05 UTC on the same Apple M1 Pro/macOS/AppleClang host and pinned HiGHS
1.15.1. Subsequent commits through `a747330805cf1fed4c082a42900d9194c9f849b8`
change documentation only; that clean head is recorded by the final FAST run.
This batch adds verified root-cover handoff, opt-in bounded binary reliability
branching, bounded weighted-square continuous QP with C/Python APIs, owning
FlatZinc capture, scoped integer/Boolean compilation and the separate
`fzn-gecode-optimize` command. W9 starts, LP observations and broader FlatZinc
global admission are subsequent work, excluded from this gate.

| Check | Result | Local evidence |
| --- | --- | --- |
| Combined native/numerical plus original regression target | 43/43 pass | `build/native-compat/fifth-final-ctest.log` |
| Numerical Release | 32/32 pass | `build/optimize/fifth-final-ctest.log` |
| Backend-disabled Debug | 32/32 pass | `build/optimize-core/fifth-final-ctest.log` |
| Full-source HiGHS/facade ASan+UBSan | 31/31 C/C++ tests pass | `build/optimize-sanitize/fifth-final-ctest.log` |
| Full-source native/HiGHS/facade ASan+UBSan | 40/40 tests pass, including FlatZinc capture/CLI; 37 Python methods pass with runtime preloaded | `build/native-sanitize/fifth-final-ctest.log`, `fifth-python-preloaded-sanitizer.log` |
| Complete legacy FlatZinc selection | 140/140 pass | `build/native-compat/fifth-final-legacy-flatzinc.log` |
| Fresh installed C/C++ consumers | Standalone numerical, combined, backend-disabled: 2/2 each; independent native-only: 1/1 | `build/consumer-*-fifth/`, `build/optimize/fifth-installed-consumers.json` |
| Python against freshly installed libraries | 37/37 methods pass in each of three configurations | `build/{optimize,native-compat,optimize-core}/fifth-installed-python.log` |
| Runner and containment contracts | 24 pass; 9 actual-Windows checks explicitly skipped | `build/native-compat/fifth-harness-final-tests.log` |
| Required FAST gate | **28/28 pass, 5.55 seconds external wall**, 5.52 seconds inside runner | `build/optimize/fifth-fast.json`, `fifth-fast-wall.json` |
| Existing MIPLIB correctness panel | 5/5 independent exact witness/known-optimum checks pass | `build/optimize/fifth-miplib-correctness.json` |
| Original checkout isolation | All 2,963 hashes, original branch and commit unchanged | `build/optimize/fifth-final-original-isolation.json` |

FAST ran after every root build/test process exited and all three agents
confirmed a quiet window. A process inventory found no build/solver workloads;
both executables and twelve runtime libraries are hashed. The unchanged outer
budget is 28 seconds, including startup, hashing, checking and cleanup. The
5.55-second observation is a local correctness gate, not a solver-performance
comparison. The new cases independently check QP optima 3.5/2.5, root-cover
optima 15/19 and reliability-branching optima -17/17, including actual cut/probe
accounting rather than merely accepting an optimal status.

The expanded native sanitizer build initially exhausted disk space while
linking FlatZinc executables. Superseded generated agent objects/archives and
executables were removed; source, current inputs and validation logs were
preserved. The serialized retry built all targets and the final 40-test gate
passed. Native, integer/set/float, minimodel, search, FlatZinc, HiGHS and facade
sources were instrumented with matching generated configuration. The original
checkout was not used as a build/output directory. macOS leak detection remains
unavailable (`detect_leaks=0`); address and undefined-behavior checks halt on
errors. No additional detector was disabled.

Broader legacy testing exposed one existing restart-output expectation:
`on_restart_sol_float` required `y=1.0` for an initially unconstrained finite
float. Both the frozen fourth-batch executable and the current one printed
`-DBL_MAX` there. The test now validates any finite first value and still requires
the exact later remembered values, sequence and completion markers; adversarial
output fixtures check that it rejects malformed or semantically wrong output.
The model and search settings are unchanged. This test-only correction is
included in the 140/140 final legacy result; it is not evidence of a solver
behavior regression or a relaxation of later restart checks.

Quadratic tests validate original primal values, objective/gradient, dual signs,
KKT residuals and an independently checked outward tangent/box bound, including
large-offset cancellation, interrupted backend data and fast-math rejection.
They do not claim arbitrary-Hessian, mixed-integer quadratic or nonlinear
support. Native reliability tests use exhaustive finite-product oracles and
fault/interruption checks; probes rank candidates but never publish proofs or
incumbents. FlatZinc tests use independent raw-source predicates and whole-model
admission, including CLI status/identity/output corruption fixtures. Fresh
installs contain the public quadratic header and exclude its private bound
header. No remote CI or actual-Windows containment gate has run locally.

## Fourth batch: checked native search, presolve, pools and bulk bindings

Integrated source `cf95a6167342953ddb386a9a87b18e58c7672eb5`, tested
2026-09-05 UTC on the same Apple M1 Pro/macOS/AppleClang host and pinned HiGHS.
This gate includes native LP deductions, scoped cover proof checking, explicit
native search with interrupted frontier bounds, exact integer presolve/postsolve,
ranked pools, C/Python pool and repair workflows, and atomic C++/C/Python batches.
The root cut loop and subsequent QP/FlatZinc work are separate later slices.

| Check | Result | Local evidence |
| --- | --- | --- |
| Combined native/numerical plus original regression target | 31/31 pass | `build/native-compat/fourth-final-ctest.log` |
| Numerical Release | 26/26 pass | `build/optimize/fourth-final-ctest.log` |
| Backend-disabled Debug | 26/26 pass | `build/optimize-core/fourth-final-ctest.log` |
| Full-source HiGHS/facade ASan+UBSan | 25/25 C/C++ tests pass | `build/optimize-sanitize/fourth-final-ctest.log` |
| Full-source native/HiGHS/facade ASan+UBSan | All 28 C/C++ tests pass; 28 Python methods pass with the sanitizer runtime preloaded | `build/native-sanitize/fourth-final-ctest.log`, `fourth-python-preloaded-sanitizer.log` |
| Fresh installed C/C++ consumers | Standalone numerical, combined, backend-disabled: 2/2 each; independent native-only: 1/1 | `build/consumer-*-fourth/`, `build/optimize/fourth-installed-consumers.json` |
| Python against freshly installed libraries | 28/28 methods pass in each of standalone numerical, combined and backend-disabled configurations | `build/{optimize,native-compat,optimize-core}/fourth-installed-python.log` |
| Runner and containment contracts | 24 pass; 9 actual-Windows checks explicitly skipped | `build/native-compat/fourth-harness-final-tests.log` |
| Required FAST gate | **25/25 pass, 5.57 seconds external wall**, 5.50 seconds inside runner | `build/optimize/fourth-fast.json`, `fourth-fast-wall.json` |
| Existing MIPLIB correctness panel | 5/5 independent exact witness/optimum checks pass | `build/optimize/fourth-miplib-correctness.json` |
| Original checkout isolation | All 2,963 hashes, original branch and commit unchanged | `build/optimize/fourth-final-original-isolation.json` |

All root and agent builds/tests had exited before FAST ran, with explicit agent
acknowledgments and a saved process inventory. Both executables and twelve
runtime libraries are hashed. Normal desktop services remained; this single
correctness-gate observation is not a solver-performance comparison. The outer
runner budget remains 28 seconds. No original benchmark output was modified.

The native sanitizer CTest invocation initially also registered an ordinary
Python host. That one launch failed before the tests because AddressSanitizer
loaded too late through ctypes. The native C/C++ tests all passed. Running the
Framework Python application executable with the matching sanitizer runtime
preloaded then passed every Python test; the ordinary Python registration is
disabled in this sanitizer build. No sanitizer detector was suppressed. Local
leak detection remains unavailable (`detect_leaks=0`); address, container and
undefined-behavior checking use halt-on-error.

Native LP tests independently enumerate 320 configurations. Frontier tests
exercise complete and interrupted minimization/maximization, queued and active
parent-region coverage, storage and node limits, cancellation/deadlines,
allocation failures, original witness checks, and optional checked LP. The
separate coordinator executable compiles test hooks into its own implementation;
the production library contains no test hooks. Presolve tests enumerate full
original/reduced feasible sets and add actual native/HiGHS reconstruction checks.
Bulk tests inject allocation failures before every allocation in all three C++
operations, verify unchanged revisions/contents/reference addresses, and check
sparse construction without dense allocation. C/Python tests cover output
capacity, foreign/deleted handles, UTF-8, sparse dimensions and owning historical
workflow results. These are correctness gates; default native performance
selection and broader benchmark-family comparisons remain outstanding.

## Third batch: globals, sparse LP, repairs, bindings and native lifecycle

Integrated source through `0c6d9462d`, tested 2026-09-05 UTC on Apple M1 Pro,
macOS 15.7.4 and AppleClang 17. The HiGHS pin remains unchanged. Later work,
including solution pools and bounded-integer sparse certificates, has separate
acceptance checks and is not included in this recorded gate.

| Check | Result | Local evidence |
| --- | --- | --- |
| Numerical Release conformance | 19/19 pass, including 13 Python conformance methods | `build/optimize/third-batch-ctest.log` |
| Backend-free conformance | 19/19 pass; expanded binding checks also pass after their final addition | `build/optimize-core/third-batch-final-ctest.log`, `third-batch-bindings-ctest.log` |
| Combined native/numerical and original regression target | 22/22 pass | `build/native-compat/third-batch-final-green-ctest.log` |
| Full HiGHS and facade ASan/UBSan | 18/18 pass with halt-on-error; Python host excluded from this instrumented CTest configuration | `build/optimize-sanitize/third-batch-final-ctest.log` |
| Full native engine ASan/UBSan | 4/4 pass: globals, native solve, brancher lifecycle, C ABI; 8.22 seconds | `build/native-sanitize/third-batch-final-ctest.log` |
| Clean installed C/C++ consumers | Standalone numerical, combined native/numerical, backend-free and separate native-only consumers pass | `build/consumer-*-third/`, local `/private/tmp/gecode-third-installed-*.log` |
| Installed Python | 13/13 methods pass against standalone numerical and combined native/numerical libraries | `build/optimize/third-batch-installed-python.log`, `build/native-compat/third-batch-installed-python.log` |
| Package ownership | Six collision/repeat cases plus standalone-native boundary pass | `build/native-compat/third-batch-package-origin.log` |
| Fast runner contracts | 11 tests pass, including new native-global provenance checks | `build/native-compat/third-batch-final-runner-tests.log` |
| Required fast gate | 21/21 pass; **5.53 seconds external wall**, 5.45 seconds inside the runner | `build/optimize/third-batch-fast.json`, `third-batch-fast-wall.json` |
| Existing MIPLIB correctness panel | 5/5 pass with independent original witness checker; clean recorded source tree | `build/optimize/third-batch-miplib-correctness.json` |
| Original checkout isolation | All 2,963 input/source hashes plus original branch and commit unchanged | `build/optimize/third-batch-original-isolation.json` |

The fast command ran after build/test processes finished and agents confirmed
a quiet window. It includes all startup, validation, cleanup and output work,
both executable hashes and twelve shared-library hashes. This is one local
correctness-gate timing, not a solver-performance comparison. All required cases
must finish within the unchanged 28-second runner budget. See [the fast panel](FAST-REGRESSION.md)
for independent schedule, recourse, repair and native integer oracles.

Native global tests enumerate finite products with independent predicates,
including aliases, negative index bases, empty tables/elements, zero-resource
tasks and circuit subtours. Resource preflight now bounds native envelope,
edge-finding and index arithmetic; targeted extreme-value fixtures must reject
unsupported ranges before calling those propagators. The sparse binary LP slice
has independent 3,000-model dense/CSR certificate comparisons, 8,640 native
propagation configurations and a 16K-square allocation guard; see [sparse LP](SPARSE-LP.md)
for exact scope and the isolated-worktree instrumentation used for those tests.

Cross-review fixed residual cancellation across large row bounds and objective
offsets, invalid stage evidence, and lost raw-stage provenance on interruptions.
Repair tests use 21 deterministic coordinator scenarios in addition to actual
HiGHS and exhaustive small-model checks. Repairs retain a distinct private model
and cannot claim that an original infeasible point became feasible.

Full native instrumentation first exposed invalid downcasts of intrusive list
sentinels to Brancher/Propagator. The kernel now retains ActorLink cursors and
casts only actual actors after the sentinel check. Lifecycle tests cover empty
lists, forward and wrapped lookup, absent middle actors, deletion, archive
choices, cloning, propagator iteration and recomputed DFS solution sets.
Final runs retain the vptr detector and use `UBSAN_OPTIONS=halt_on_error=1`;
no undefined-behavior detector was suppressed. macOS leak detection is unavailable,
so `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1` was used locally. The added Linux
native sanitizer job enables leak detection, but remote CI has not been run here.

All native components and consumers must be rebuilt together after the cursor
representation change. The C layout remains independent of C++ internals.
ELF static native dependencies are compiled as PIC when embedded in the shared
C wrapper. A native-enabled binding fixture incorrectly expected a numerical
session to fall back to native execution; it now checks the documented
Unsupported result. Standalone native/global calls pass through both bindings.

## Second batch: sessions, native bridge, diagnostics and fast gate

Tested solver implementation: `6a7544e85`, on `codex/solver-parity`,
2026-09-05 UTC. Host: Apple M1 Pro, macOS 15.7.4, AppleClang 17. HiGHS remains
pinned to 1.15.1, commit `04024d701f79feb8e2f18bc3df0dffc04ef05088`.

| Check | Result | Local evidence |
| --- | --- | --- |
| Numerical Release conformance | 14/14 pass | `build/optimize/integrated-ctest.log` |
| Backend-free conformance | 14/14 pass | `build/optimize-core/integrated-ctest.log` |
| Combined native Gecode and optimization | 16/16 pass, including the enabled native bridge and original native regression target | `build/native-compat/integrated-ctest.log` |
| Full-source Debug ASan/UBSan, including HiGHS | 14/14 pass; 41.61 seconds for the complete conformance run | `build/optimize-sanitize/integrated-ctest.log` |
| Four installed consumers | Standalone numerical, combined native/numerical, native-only without HiGHS discovery, and backend-free all pass | `build/consumer-*/integrated-ctest.log` |
| Fast regression command | 18/18 required cases pass; **5.49 seconds external wall time**, 5.37 seconds reported inside runner, against a 28-second budget | `build/optimize/second-batch-fast.json`, `second-batch-fast-wall.json` |
| Fast-runner failure regressions | 11 tests pass | `build/optimize/fast-runner-tests.log` |
| Package ownership/support boundaries | Four configure-only ownership cases plus standalone-native rejection pass | `build/optimize/package-origin-tests.log` |
| Existing MIPLIB correctness inputs | 5/5 pass with the original separate exact witness checker | `build/optimize/second-batch-miplib-correctness.json` |
| Original checkout isolation | All 2,963 hashes, original branch and commit unchanged | `build/optimize/second-batch-original-isolation.json` |

The fast measurement ran alone after builds and solver tests finished; no
original benchmark process was observed. It includes Python startup, child
startup, source/binary hashing, eleven shared-library hashes, all cases,
validation, cleanup and report writing. This is one local timing observation,
not a performance ranking or a guarantee about slower machines. Every required
case must complete within the runner's outer budget or the command fails.
The native bridge case has explicit native backend/version and Exact guarantee
attribution; its two optima are independently enumerated.

The new tests compare persistent edits with cold solves and exhaustive integer
oracles, exercise active/zero semi domains and indicators, and check bounds,
costs, objective senses, matrix/type/owner changes, starts and historical values.
A nontrivial 48-binary MIP is still unresolved after one node both cold and with
a retained hint; removing the node-limit reset in a temporary mutation makes
the unlimited-session regression fail. Node-limit termination after callback
registration also exercises callback teardown before a fresh model. That
conformance test has a separate 180-second timeout for slow Debug sanitizer
builds and is not part of the fast gate.

Conflict tests reconstruct reported subsets independently and check deletion
witnesses; deterministic oracle substitutes cover ambiguous and interrupted
results. Native bridge tests exhaustively check finite integer models,
reification, offsets, semi domains, unsupported ranges and interrupted search.
Separate native-bridge ASan/UBSan tests instrumented the bridge and its test
sources; the legacy native libraries used by those tests were not instrumented.
The full-source HiGHS sanitizer configuration uses the disabled native bridge
stub. A full native-library sanitizer configuration remains additional coverage.

Integration found a Debug HiGHS assertion when a diagnostic reduction left
integer variables and only constant rows. The adapter now decides constant rows
using the original numerical checker's absolute feasibility tolerance and omits
them from the backend matrix, while retaining them in the original model.
The regression covers feasible, contradictory and tolerance-boundary constants.
The full-source sanitizer run passes without suppressing backend assertions.

The package tests prevent silent target collisions between different standalone
prefixes or a combined and standalone installation. The added Linux static and
Windows shared native CI configurations were checked locally at configure time;
their remote CI jobs have not run. Windows fast-runner process containment is
still pending. Generated build reports are local artifacts, not committed
benchmark results. The MIPLIB report's dirty flag reflects temporary Python
bytecode files from the runner tests, subsequently removed; solver source was
committed at the recorded hash.

## First-batch evidence

Completed on 2026-09-05 UTC (2026-09-04 local time). Tested implementation commit:
`8c45e7b30`, on `codex/solver-parity`. Documentation was completed afterward.
Host: Apple M1 Pro, macOS, AppleClang 17, C++17. Backend: separately pinned HiGHS
1.15.1, commit `04024d701f79feb8e2f18bc3df0dffc04ef05088`.

## First-batch checks

| Configuration or check | Result | Local evidence |
| --- | --- | --- |
| Standalone numerical Release build | 9/9 CTest targets pass | `build/optimize/final-ctest.log` |
| Full-source Debug ASan + UBSan, including HiGHS | 9/9 pass, no sanitizer suppression | `build/optimize-sanitize/final-ctest.log` |
| Standalone backend-disabled build | 9/9 pass | `build/optimize-core/final-ctest.log` |
| Combined native Gecode + optimization | 11/11 pass, including native regression target and its build fixture | `build/native-compat/final-ctest.log` |
| Installed standalone numerical consumer | Configure, build and runtime pass | `build/consumer-standalone/final-ctest.log` |
| Installed native + numerical consumer | Configure, build and runtime pass | `build/consumer-combined/final-ctest.log` |
| Installed native-only consumer, HiGHS discovery disabled | Configure, build and runtime pass | `build/consumer-native-only/final-ctest.log` |
| Installed backend-disabled optimization consumer | Configure, build and expected Unsupported runtime contract pass | `build/consumer-core/final-ctest.log` |
| Explicit native static-only selection | `gecodeoptimize` builds as a static library, honoring Gecode linkage options | `build/static-configuration/build.log` |
| Existing five-model MIPLIB correctness harness | 5/5 pass, independently exact-checked witnesses and known optima | `build/optimize/final-miplib-correctness.json` |
| Original checkout isolation | All 2,963 file hashes, original branch and original commit unchanged | `build/optimize/original-isolation.json` |
| Changelog tidy and whitespace | Changelog checks pass; `git diff --check` passes | Checker details below |
| Added platform CI | YAML and all shell steps checked locally; remote jobs not executed | `.github/workflows/optimize.yml` |

The build logs and JSON reports are generated local artifacts, not committed
benchmark results. The MIPLIB report records the binary hash, input hashes,
backend version and tested source commit. Its dirty-worktree flag reflects the
implementation-ledger documentation being edited during the run; solver code
was committed at the hash above.

The nine component targets cover model lifecycle; result/gap/budget semantics;
independent validation; indicators/Boolean logic; I/O; actual solver integration;
ordered objectives; public-file I/O; and a deterministic multiobjective
coordinator with a substitute backend. Assertions remain enabled in Release
test executables.

Independent worktree checks preceded integration: normal C++17 builds with
`-Wall -Wextra -pedantic`, then address/undefined sanitizer runs for the owned
components. Cross-review fixes were tested again in the combined suite.
The actual solver test combines indicators, partial starts, lexicographic locks
and indicator removal, in addition to LP/MILP objectives, edits, bounds, limits,
semi-variable starts, deleted handles and tiny differential integer models.

An initial sanitizer configuration mixed instrumented adapter code with an
uninstrumented static HiGHS library and reported a libc++ vector-container
annotation error. Rebuilding **both** with the same instrumentation passes all
tests. Container checking was not disabled. The CI sanitizer job therefore
builds the entire dependency from source with matching C and C++ flags.

## Existing benchmark inputs

The five unchanged cached MIPLIB3 models were solved cold, with one worker,
seed zero, zero native MIP gaps and a 30-second per-case limit. Reference
objectives were used for checking only, never supplied as starts or targets.

| Model | Variables | Original rows | Published and independently checked optimum |
| --- | ---: | ---: | ---: |
| p0033 | 33 | 16 | 3089 |
| p0201 | 201 | 133 | 7615 |
| p0282 | 282 | 241 | 258411 |
| p0548 | 548 | 176 | 8691 |
| lseu | 89 | 28 | 1120 |

`experiments/optimize/verify_miplib.py` reads the original MPS using the existing
suite's separate exact parser, verifies pinned payload hashes, maps returned
values by column name, checks numerical integrality, then checks rounded binary
witnesses with the existing exact assignment validator. Independently recovered
objectives must match both the published optimum and the adapter's result;
reported bounds must close at that optimum. Unsupported, failed or timed-out
cases fail the correctness check rather than disappearing from the denominator.
The report records external process wall time as well as the CLI's internal
timing fields, and rejects nonfinite JSON numbers.

These are correctness checks on five small historical instances. They are not
a commercial-solver comparison, a full MIPLIB2017 result, a performance baseline,
or evidence for changing native search defaults. The original 3,240-row
size-scaling run completed before any implementation compilation or solver
testing started. Its suite and output files were not changed by this work.

## Import/export regressions

I/O tests compare every active domain, row, coefficient, objective and display
name after local round trips, including all five public models through both
formats. Backend-enabled tests also read exported files with the independent
pinned HiGHS reader and compare their mathematical content; dropping an
unconstrained free row is permitted in that external comparison only.

Cross-review reproduced and fixed:

- 15-digit output merging distinct coefficients and changing integer feasibility.
- Lost semi-integer declarations and omitted cost-free columns.
- Duplicate objective terms and LP constants on constraint left sides.
- Cancellation across a large LHS constant and RHS, preserving `x >= -1` in
  `x + 1 - 1e16 >= -1e16`.
- Conflicting MPS domain declarations silently dropping integrality.
- MPS binary bounds that passed local round trips but were ignored by another
  reader. Nondefault binary bounds now require LP export; MPS rejection leaves
  an existing destination unchanged.
- Original-indicator metadata being lost through linear file exchange. Active
  original indicators are rejected by these exporters.

The independent reviewer reran the cancellation, conflicting-type, destination
preservation and narrowed-binary LP fallback reproductions successfully after
the fixes. See [I/O scope](IO.md) for syntax and portability restrictions.

## Reproduction and remaining release work

Build instructions are in the [API guide](README.md). For a fully instrumented
local run, use a fresh build directory and supply the pinned source path:

```sh
cmake -S gecode/optimize -B build/optimize-sanitize \
  -DCMAKE_BUILD_TYPE=Debug -DBUILD_SHARED_LIBS=OFF \
  -DGECODE_OPTIMIZE_HIGHS_SOURCE="$PWD/../deps/HiGHS" \
  '-DCMAKE_C_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer' \
  '-DCMAKE_CXX_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer' \
  '-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address,undefined'
cmake --build build/optimize-sanitize -j 2
ctest --test-dir build/optimize-sanitize --output-on-failure
```

The changelog-only `misc/tidy.py` checks were run through installed Python 3.14,
with its two `uv run` generator launches directed to that interpreter because
`uv` was unavailable. The generators are standard-library-only, require Python
3.11+, and their checking logic and source files were unchanged.

Windows and Linux CI execution, C ABI/Python packaging, broad numerical and
general-integer panels, and an uncontended cold-start performance baseline
remain release work. The added CI workflow covers static/shared core packages
on three platforms, numerical packages, installed consumers, and full-source
sanitizers, but no remote success is claimed. Native/FlatZinc compilation,
native sparse LP/cuts/branching, explanations/learning, quadratic/nonlinear
models and native parallel hybrid solving remain separate roadmap work.

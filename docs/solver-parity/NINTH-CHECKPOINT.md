# Ninth integrated checkpoint — 2026-09-05

The work recorded at this historical checkpoint is integrated on `codex/solver-parity` in
`implementation/gecode`. This checkpoint finishes selected-basis LP sensitivity
and bounded native incumbent improvement, validates their integration, and
compares existing workloads with the preceding working checkpoint. Further
roadmap implementation is on hold. The later bounded algorithm work is recorded
separately in the [algorithm checkpoint](ALGORITHMIC-CHECKPOINT.md).

Compiled product source is `c2fabb78f1fc3bcfd7432eb71cfdb22656cd3f60`.
The final FAST runner and performance measurement use
`db7eb0b85b2970e20e8a3d965559fd31a94c73b4`; that follow-up changes only the
runner's expected BinaryHamming backend identity. Later checkpoint documentation
does not change the tested product. The original checkout remains on
`experiment/llm-search` at `3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e`, with
all 2,963 recorded source/test/input hashes unchanged.

## Completed scope

- [LP sensitivity](LP-SENSITIVITY.md) computes original-coordinate objective
  coefficient and equality-RHS intervals for a selected optimal continuous LP
  basis. The numerical analyzer checks the basis and source observations,
  factors a private system without running another optimization, and retains
  owning history and explicit incomplete/unavailable outcomes.
  [C and Python bindings](LP-SENSITIVITY-BINDINGS.md) include lifetime,
  cancellation and cleanup behavior.
- [Native neighborhoods](NATIVE-NEIGHBORHOODS.md) adds an explicit C++ API for
  one bounded binary Hamming-distance improvement attempt after a checked
  incumbent. It checks a proposed improvement against the original model and
  shares the outer search budget without promoting a local proof to a global
  one. Existing default solve routes remain unchanged. This experimental
  slice does not include a C/Python neighborhood wrapper or a full heuristic
  portfolio.
- Both features are integrated into normal/backend-disabled/sanitizer builds,
  installed consumers, and the expanded 35-case FAST gate. Sensitivity's private
  factorization headers are excluded from installed headers.
- Previously started learning research is retained as an isolated experiment
  and private reason-contract header. The header is excluded from installation;
  no CaDiCaL dependency or learning runtime was added to Gecode.

## Correctness and installation

All results below are from the local Apple M1 Pro, macOS 15.7.4, AppleClang host,
with pinned HiGHS 1.15.1 and MiniZinc 2.10.1 where applicable. These are different
configurations of overlapping tests; their counts should not be added as unique
test coverage.

| Gate | Result | Evidence relative to repository root |
| --- | --- | --- |
| Combined native/numerical and FlatZinc boundary CTest selection | 67/67 pass | `build/native-compat/ninth-ctest.log` |
| Numerical Release | 54/54 pass | `build/optimize/ninth-ctest.log` |
| Backend-disabled Debug | 52/52 pass | `build/optimize-core/ninth-final-ctest.log` |
| Full native/HiGHS/facade ASan+UBSan configuration | 66/66 pass | `build/native-sanitize/ninth-ctest.log` |
| Python with the sanitizer runtime preloaded | 83/83 pass | `build/native-sanitize/ninth-python-preloaded-sanitizer.log` |
| Installed C/C++ consumers | 8/8 each: numerical, core, combined; native-only 1/1 | `build/optimize/ninth-installed-consumers.json`; `build/native-compat/ninth-native-only-test.log` |
| Python against installed libraries | 83/83 in each of those three configurations | `build/optimize/ninth-installed-consumers.json` |
| Actual FlatZinc CLI | 106/106 in normal and sanitizer configurations | `build/{native-compat,native-sanitize}/ninth-cli.json` |
| Actual MiniZinc build registration | 72/72 in normal and sanitizer configurations | `build/{native-compat,native-sanitize}/ninth-minizinc.json` |
| Actual installed MiniZinc registration | 72/72 pass | `build/native-compat/ninth-installed-minizinc.log` |
| Legacy FlatZinc including optional blackbox fixtures | 140 fixture instances, five repetitions each, seed 1701 | `build/native-compat/ninth-legacy-summary.json` |
| Regression-runner/containment unit tests | 24 pass; 9 actual-Windows tests skipped | `build/native-compat/ninth-harness-tests.log` |
| Expanded FAST gate | **35/35 pass; 5.7852 s external wall** within its unchanged 28 s outer budget | `build/optimize/ninth-fast.json`, `ninth-fast-wall.json` |
| Original checkout isolation | 2,963 hashes plus branch and HEAD unchanged | `build/optimize/ninth-original-isolation.json` |

The new FAST sensitivity case checks 63 analytic/lifecycle conditions for both
objective senses. The neighborhood case checks 14 conditions, including an
actual incumbent improvement and the independent eight-assignment optimum
of −29. Private coordinator tests cover interruptions, accounting and cleanup;
installed consumers exercise the public APIs. The original full native test
corpus was not rerun: the retained CP gate and the selected legacy FlatZinc
fixtures provide the bounded original-code regression coverage.

The first legacy selection omitted the log environment variable, selecting 136
fixture instances. A follow-up with the proper blackbox environment ran the
four missing fixtures and repeated seven shared controls. Two distinct legacy
fixtures both register as `tenpenki::1`, so there are 139 distinct display names
among the 140 fixture instances. This matches the preceding checkpoint's fixture
set. An initial new FAST fixture compile used the wrong LP observation options
type; that test setup was corrected before the final rebuild. The runner's
expected neighborhood backend identity was also corrected before the final FAST
run. Those preliminary failures are retained in local logs.

## Existing-workload performance comparison

The prior checkpoint is compiled source `bda86186d`, with source/report head
`158dc0b66f02929c9be957cdcad651581dd7be3f`. Both cohorts use the same preserved
eighth-checkpoint test executables and the same frozen 33-case runner and 70
fingerprinted source/fixture files. Only explicitly selected solver libraries
change. Dynamic-loader probes verified all 11 loaded Gecode libraries came
from the intended cohort, and artifact hashes were checked again afterward.
All task builds/tests stopped before timing; ordinary desktop processes remained.

| Panel | Complete pairs | Prior median external wall | Current median external wall | Median paired current/prior ratio | Geometric mean of per-case paired median ratios |
| --- | ---: | ---: | ---: | ---: | ---: |
| 33 common FAST cases | 5 | 5.6303 s | 5.7401 s | 1.0195 | 1.0024 |
| Five existing MIPLIB inputs | 3 | 1.7816 s | 1.5935 s | 0.9421 | 0.9608 |

The ten complete FAST panels passed 330/330 case executions. The six MIPLIB
panels passed 30/30 solves with independent exact witness and known-optimum
checks on p0033, p0201, p0282, p0548 and lseu. No case triggered the predeclared
diagnostic threshold: its median must slow by both more than 20% and more than
1 ms, and the joint condition must recur in at least half its paired runs.
This is a diagnostic rule, not a statistical significance test.

**One additional attempted panel failed its deadline.** Six FAST pairs were
planned; the current-library panel starting pair six timed out in `cp_distinct`
at 4.0046 s under the existing four-second cap. Its other 32 cases passed.
The failure is preserved, was not retried, and is excluded from the five
complete paired medians. The final comparison explicitly records
`all_attempted_fast_panels_passed: false`. Successful runs of that case ranged
from 3.29 to 3.55 s. Its executable and all nine native-library instruction
sections are byte-identical between cohorts. This shows a deadline-margin and
repeatability limitation in unchanged code; it does not identify the cause of
the timing variability. No limit was relaxed to obtain a pass.

The common FAST results suggest little change on these workloads. The MIP
panel's lower measured times do not establish a general speedup. This short
comparison includes process startup, loading, polling and desktop noise; it has
no large-instance holdout, confidence intervals or memory analysis. It compares
with the preceding integrated checkpoint, not CPLEX/Gurobi or the entire original
benchmark corpus. New-feature correctness is covered by the separate 35-case
gate; this comparison does not measure new-feature performance benefits.

Full raw measurements, per-case times, provenance and the failed sixth panel
are in `build/comparison-eighth/results-final/`. The interpretation is
`interpretation.md`; the full machine-readable record is `comparison.json`.
The preserved comparison script and preparation manifest are in its parent
directory. A committed compact record is [checkpoints/ninth.json](checkpoints/ninth.json).

## Usable artifacts and boundaries

The combined executable is `build/native-compat/bin/fzn-gecode-optimize` and
the combined facade is under `build/native-compat/gecode/optimize/`. Fresh
tested installation prefixes are `build/stage/combined-ninth`,
`build/stage/standalone-ninth` and `build/stage/core-ninth`. The
[build/API guide](README.md), [MiniZinc guide](MINIZINC.md) and
[FAST command](FAST-REGRESSION.md) describe their use. Exact executed FAST
arguments and library hashes are in `build/optimize/ninth-fast-wall.json` and
`ninth-fast.json`. Existing eighth-checkpoint stages and binaries were preserved.

This batch did not rebuild the Python wheel; the existing eighth-checkpoint
wheel does not contain these additions. No package publication, remote CI,
actual Windows/Linux runtime validation or oldest-macOS execution is claimed.
The full native sanitizer configuration instruments the native libraries,
HiGHS and facade; leak detection is disabled, with ASan/UBSan halt-on-error
enabled. No further branching, learning, nonlinear or parallel-search work is
started by this checkpoint. The broader parity roadmap remains incomplete.

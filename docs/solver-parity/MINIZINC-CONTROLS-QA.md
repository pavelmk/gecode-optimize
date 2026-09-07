# MiniZinc native controls: QA walkthrough

Verified locally on macOS ARM64 with pinned MiniZinc **2.10.1**, its matching
standard library, and an isolated Release build. This is correctness, dispatch,
resource and packaging QA; no new performance benchmark or speedup claim is made.

## Results

- Full Release regression: **75/75 CTest entries pass**, including FAST, source
  truth tables, frontend fault injection, native algorithms and Python bindings.
- Actual MiniZinc build registration: **135 process checks pass**, including
  26 successful native-control scenarios and independent six-decision oracles.
- Installed registration: **135 checks pass** against the actual installed
  executable and library using relative `.msc` paths. The executable resolves
  libraries through `@loader_path/../lib`, without the build directory.
- Checked-LP-disabled harness: **135 MiniZinc checks plus three native tests
  pass**. Runtime inspection confirms the isolated optimization library loads.
  Explicit LP requests fail clearly; automatic/native/racing routes still work.
  This harness disables native checked LP while retaining other HiGHS APIs.
- Backend-free build: **3/3** automatic, racing and presolve tests pass, including
  backend-independent objective-reconstruction and malformed-result checks.
- JSON registration encoder: **10 cases pass**, preserving all 21 controls,
  escaped paths and relocatable install paths.

All optimization witnesses below are checked against independent exhaustive
source-model oracles, including tied optima. The two small six-decision fixtures
both have optimum **12**. The tests check actual work rather than only acceptance
of command-line options.

| Walkthrough | Observed activity |
|---|---|
| Integer `0..1` knapsack, default auto | Objective auxiliary restored; eligible exact knapsack DP selected. |
| Same model, automatic knapsack disabled | Same optimum; DP route absent. |
| Racing with four nodes per probe | Two probes and selection of automatic route; one shared cumulative node budget. |
| Zero exploration / retained all-different global | Explicit race skip, correct result. |
| Configured reliability | 24 actual probe status calls. |
| Configured Hamming, radius 1 | One attempt and three local status calls; completion reason reported. |
| Configured root LP plus covers | Five LP calls, five checked bounds, four verified cover cuts. |
| Configured updated LP, cuts, reliability, Hamming | 31 checked bounds, four cuts and 20 branching probes. |

These are small-fixture activity counts, not recommended tuning constants or
general performance predictions. Hamming distance counts flattened binary slots;
the Boolean fixture also contains integer aliases, so one logical Boolean change
can require radius two. Optional mechanisms may correctly skip or do no useful
work on other models.

The gate verifies flag discovery and forwarding through the real MiniZinc parser,
all four modes, individual/all automatic switches, explicit dependencies,
zero optional allowances, global node limits of zero and one, zero frontier
storage, malformed/overflowing/repeated controls and whole-frontend timeouts.
Every printed completion marker must match the independently computed optimum;
interruptions may print only a checked witness or UNKNOWN. Diagnostic control
characters are sanitized before writing protocol comments.

The compiler tests verify that internal binary recognition preserves integer
source typing, output, aliases and domains. Native tests cover both signs of the
objective-defining equality, minimization/maximization, objective offsets,
restrictive auxiliary domains, disabled presolve/DP, original model identity and
active mask, supplied starts, shared budgets, cancellation and invalid child
results. No declaration name or `defines_var` annotation is trusted as proof of
equivalence.

Packaging QA caught a stale configure-time install registration in an existing
build. CMake now tracks the registration template and encoder as configure
dependencies, so changing advertised controls updates both build and install
registrations. The installed artifact contains all 21 controls and passes the
same real-compiler gate in place.

## Reproduce

From the solver repository, using the configured build described in
[the MiniZinc setup guide](MINIZINC.md#build-and-installation):

```sh
cmake --build build/native-structure/native-build -j 4
ctest --test-dir build/native-structure/native-build --output-on-failure
python3 -B test/optimize/minizinc_registration.py \
  --minizinc ../deps/MiniZinc-2.10.1-aarch64-apple-darwin/bin/minizinc \
  --binary build/native-structure/native-build/bin/fzn-gecode-optimize \
  --registration build/native-structure/native-build/minizinc/Release/gecode-optimize.msc
```

To inspect the actual algorithm choices interactively:

```sh
mzn=../deps/MiniZinc-2.10.1-aarch64-apple-darwin/bin/minizinc
solver="$PWD/build/native-structure/native-build/minizinc/Release/gecode-optimize.msc"
"$mzn" --solver "$solver" --native-diagnostics on \
  test/optimize/minizinc-fixtures/mzn-native-knapsack.mzn
"$mzn" --solver "$solver" --native-mode race \
  --native-race-seconds 0.05 --native-race-nodes 4 --native-diagnostics on \
  test/optimize/minizinc-fixtures/mzn-native-controls.mzn
"$mzn" --solver "$solver" --native-mode configured --native-lp root \
  --native-root-cuts on --native-diagnostics on \
  test/optimize/minizinc-fixtures/mzn-native-controls.mzn
```

Select `org.gecode.optimize.experimental` explicitly; the stock Gecode solver
registration does not expose these flags. Racing can increase CPU work or solve
time through exploration and restarting, even when a later strategy is faster.

The local JSON reports retain process checks, source/compiler/driver/configuration
and MiniZinc library hashes, requested settings, actual policy and work counters:

- `build/native-structure/native-build/minizinc-controls-registration.json`
- `build/native-structure/native-build/minizinc-controls-installed-registration.json`
- `build/native-structure/native-build/minizinc-controls-ctest.log`
- `build/minizinc-controls-no-lp/summary.json` and `reproduce.py`
- `build/optimize-core/minizinc-controls-ctest.log`

Build-tree driver SHA256:
`3efb21d82322aff323bd05add9ef9b5b34898a5478d8766df06fb8fd13538669`.
The compiler SHA256 is
`a8489069d77793862102ca5bab5b2e24822d4445226e4262b8d35287a9af702f`.
Other machines need not produce identical binaries or work counts. Remote CI,
Windows runtime behavior and a new sanitizer run are not claimed here.

# Experimental MiniZinc registration

This opt-in solver identity connects MiniZinc 2.10.1 to the explicit
`fzn-gecode-optimize` frontend and Native/Exact search. It does not replace the
existing `org.gecode.gecode` registration, change solver preferences, or select
itself as the default. The small compatibility suite establishes correctness for
the tested subset; it makes no performance claim or general MiniZinc/FlatZinc
coverage claim.

The compiler and matching standard library are external trusted translation
components. The optimization frontend independently checks the complete emitted
FlatZinc model and every published assignment against its retained source records.
It does not independently prove that the MiniZinc compiler preserves an arbitrary
original `.mzn` model. Tests therefore also check source-level answers and the
actual emitted predicates.

## Registration and invocation

`tools/flatzinc/gecode-optimize.msc.in` defines
`org.gecode.optimize.experimental`, displayed as **Gecode Optimize (experimental)**.
Its executable is a JSON argument array containing the driver and `--minizinc`;
its solver library is `tools/flatzinc/mznlib-optimize`. The only advertised solver
standard flag is `-t`. Tags are `cp`, `int`, and `experimental`; there are no float,
set, restart, MIP, or default tags.

A configured registration can be selected by its explicit path:

```sh
minizinc --solver /path/to/gecode-optimize.msc model.mzn data.dzn
minizinc --solver /path/to/gecode-optimize.msc --solver-time-limit 1000 model.mzn
```

## Native algorithm controls

The experimental registration now exposes native algorithm controls through
MiniZinc's solver `extraFlags`. No model annotations are needed. The default
`--native-mode auto` uses bounded structural selection, exact preprocessing and
eligible knapsack DP; it does not run a race unless requested.

```sh
# Default automatic selection, with an explanation of the actual route.
minizinc --solver /path/to/gecode-optimize.msc \
  --native-diagnostics on model.mzn

# Compare automatic selection with ordinary search within one solve budget.
minizinc --solver /path/to/gecode-optimize.msc \
  --native-mode race --native-race-seconds 8 --native-race-nodes 50000 \
  --solver-time-limit 120000 --native-diagnostics on model.mzn

# Explicit checked LP, cuts, reliability branching and a bounded neighborhood.
minizinc --solver /path/to/gecode-optimize.msc \
  --native-mode configured --native-search dfs --native-lp updated \
  --native-root-cuts on --native-branching reliability \
  --native-neighborhood hamming --native-diagnostics on model.mzn
```

| Mode | Behavior |
|---|---|
| `auto` (default) | Conservative structural selection; enabled mechanisms still require eligible model structure. |
| `race` | Up to two bounded sequential probes, automatic versus ordinary BAB; restart the selected route if unresolved. |
| `plain` | Direct native BAB, including its existing eligible exact knapsack DP. |
| `configured` | Explicit LP/frontier/branching/neighborhood settings; default is DFS without LP, reliability or neighborhoods. Automatic transformations are omitted. |

**Racing may increase total CPU work or solve time.** Exploration and restarting
repeat work, and early progress can favor a strategy that eventually loses.
Several seconds or longer may nevertheless identify a much more effective route
for a long solve. Probes run sequentially, with one worker. The nominal exploration
allowance is capped at 25% of the remaining finite solve time; all probes and the
restart share the global deadline and cumulative node allowance. Zero exploration
skips the race and runs the automatic policy. Globals/indicators also skip racing.
This is a heuristic, not a performance guarantee.

All controls take an explicit value. The following table gives defaults when
omitted; MiniZinc does not forward the advertised defaults as explicit arguments.

| Flag | Values / default | Scope |
|---|---|---|
| `--native-mode` | `auto`, `race`, `plain`, `configured`; `auto` | All native solves |
| `--native-diagnostics` | `on`, `off`; `off` | All native solves |
| `--native-node-limit` | Unsigned count; unlimited | All native solves; zero permits no search node admissions |
| `--native-auto-presolve` | `on`, `off`; `on` | `auto` / automatic candidate in `race` |
| `--native-auto-components` | `on`, `off`; `on` | `auto` / automatic candidate in `race` |
| `--native-auto-symmetry` | `on`, `off`; `on` | `auto` / automatic candidate in `race` |
| `--native-auto-knapsack` | `on`, `off`; `on` | `auto` / automatic candidate in `race` |
| `--native-race-seconds` | Finite nonnegative seconds; `2` | `race` |
| `--native-race-nodes` | Positive count per probe; `4096` | `race` |
| `--native-search` | `bab`, `dfs`, `best-bound`; `dfs` | `configured` |
| `--native-lp` | `off`, `root`, `updated`; `off` | `configured`; requires checked LP capability when enabled |
| `--native-root-cuts` | `on`, `off`; `off` | `configured` with LP |
| `--native-bound-tightening` | `on`, `off`; `on` | `configured` with LP |
| `--native-lp-interval` | Positive observed bound-change count; `1` | `configured` with updated LP |
| `--native-branching` | `default`, `reliability`; `default` | `configured` frontier search |
| `--native-branching-probes` | Nonnegative status-call count; `128` | Reliability branching |
| `--native-max-open-nodes` | Nonnegative stored-space count; `100000` | `configured` frontier search; not a byte limit |
| `--native-neighborhood` | `off`, `hamming`; `off` | `configured` frontier search |
| `--native-neighborhood-radius` | Nonnegative binary Hamming distance; `1` | Hamming neighborhood |
| `--native-neighborhood-nodes` | Nonnegative local status-call count; `128` | Hamming neighborhood |
| `--native-neighborhood-seconds` | Finite nonnegative local seconds; `0.05` | Hamming neighborhood |

Automatic switches permit a mechanism; they do not force it onto unsuitable
models. A disabled switch skips that mechanism throughout automatic reduced and
component solves. In racing, `--native-auto-*` affects the automatic candidate;
the ordinary comparator keeps its existing behavior, including eligible DP.
Configured reliability considers eligible binary variables. Hamming search makes
at most one bounded attempt after an incumbent and may skip if there is no
incumbent, no eligible binary decision, or proof finishes first. Hamming distance
counts flattened binary slots: a Boolean and its `bool2int` integer alias count
separately. Such an aliased decision can require radius `2` to change its value.
LP deductions
and cover cuts retain their checked integer contracts. Explicit LP without its
required HiGHS/checked arithmetic support is an error, not a silent fallback.

Diagnostics are FlatZinc `%` comments reporting the requested mode/settings,
actual backend/policy and available work counters. A request is not evidence that
optional work ran; counters and skip explanations make that distinction visible.
Diagnostics do not enable enumeration or intermediate solutions. The default
solution protocol remains unchanged. Conflicting, irrelevant, duplicated,
malformed and overflowing options are rejected before solving, including
configured-only settings in automatic mode and frontier-only settings with BAB.

Integer source domains contained in `0..1` are represented as binary decisions
internally while retaining integer output and original domain checks. The
automatic presolve path can remove a narrowly eligible linear objective auxiliary
introduced by MiniZinc, restore its value, and check the original model before
publishing a result. Its domain restrictions are preserved. More complicated
flattened models may still choose ordinary native search; diagnostics explain
the selected route.

This change exposes **native integer solver controls**. It does not add numerical
LP/MILP or quadratic MiniZinc model support, multiobjective/session/repair/pool
workflows, conflict learning, parallel racing or general search annotations.
Those broader APIs remain separate from this experimental registration.

## Build and installation

Enable `GECODE_OPTIMIZE_MINIZINC_REGISTRATION=ON` in a top-level build with the
optimization FlatZinc driver and native backend enabled. The option defaults to
OFF. Optionally set `GECODE_OPTIMIZE_MINIZINC_EXECUTABLE` to an existing pinned
compiler to enable the real compiler CTest; configuration never downloads one.

```sh
cmake -S . -B build/native-compat \
  -DGECODE_OPTIMIZE_MINIZINC_REGISTRATION=ON \
  -DGECODE_OPTIMIZE_MINIZINC_EXECUTABLE=/path/to/minizinc
cmake --build build/native-compat --target gecode-optimize-minizinc-config
ctest --test-dir build/native-compat --output-on-failure -R '^optimize-minizinc-'
```

The `gecode-optimize-minizinc-config` target is part of the default build and
depends on the actual driver. It generates
`build/native-compat/minizinc/<configuration>/gecode-optimize.msc`, with absolute
build-tree executable/library paths and the Gecode version. For a Release build,
`<configuration>` is `Release`; an empty single-configuration build type omits it.

With `GECODE_INSTALL=ON`, normal CMake installation also installs the dedicated
library at `share/minizinc/gecode-optimize-experimental` and the registration at
`share/minizinc/solvers/gecode-optimize.msc`. The installed JSON uses paths relative
to its own directory, so `cmake --install ... --prefix /chosen/prefix` works.
Customized relative GNU install bindir/datadir values are supported; absolute
values are rejected for this relocatable registration. The existing Gecode
registration and library remain unchanged.

The pure CMake script escapes JSON paths after target-file expansion; it can also
be invoked independently:

```sh
cmake -DTEMPLATE=/source/tools/flatzinc/gecode-optimize.msc.in \
  -DVERSION=6.4.0 -DDRIVER=../../../bin/fzn-gecode-optimize \
  -DMZNLIB=../gecode-optimize-experimental -DOUTPUT=/install/solvers/gecode-optimize.msc \
  -P /source/tools/flatzinc/configure-optimize-msc.cmake
```

It takes the maintained JSON template, escapes quotes/backslashes and all non-NUL
ASCII controls in the three substituted strings, preserves relative paths and
UTF-8, and replaces the output only after writing a separate temporary file.
NUL cannot occur in an OS command-line argument/CMake string. The script does not
build targets, download dependencies, inspect solvers, or change preferences.
The template itself must be valid JSON with the maintained placeholders.
`test/optimize/minizinc_configure.py --cmake /path/to/cmake` independently decodes
encoded JSON and tests failure publication; it requires no MiniZinc or driver.

For temporary discovery by ID, a caller may set `MZN_SOLVER_PATH` to the directory
containing this `.msc`. The tests scope that environment change to their own
process. Neither the driver nor the registration writes `Preferences.json` or
`tagDefaults`.

## Solver protocol

The explicit mode accepts:

```text
fzn-gecode-optimize --minizinc [-t MILLISECONDS] [--native-mode MODE ...] MODEL.fzn|-
```

`-t` can precede or follow the filename. `--` ends option parsing, allowing a
filename beginning with a hyphen. Exactly one filename and at most one `-t` are
required; unsupported flags, missing values, fractional/negative counts, duplicate
options, and unsigned-count overflow are errors. Native time settings allow
finite nonnegative fractional seconds. This mode always uses Native
with the exact guarantee and zero requested gaps. No backend override is accepted.

`-t` is an unsigned decimal count of milliseconds. Zero means unlimited, matching
MiniZinc 2.10.1's convention: its external-solver adapter only forwards a time flag
and creates a solver watchdog when the limit is nonzero. Positive values become
the shared frontend seconds budget; argument/file opening precedes that budget,
and capture, compilation, solve, output validation, and rendering share it.
Capture has cooperative stage boundaries, so the surrounding MiniZinc process
may enforce its own watchdog after its cleanup allowance. No late assignment is
published after the driver's overall deadline.

An ordinary interruption prints `=====UNKNOWN=====` or a validated incomplete
solution stream and returns **0** in this protocol. Errors remain nonzero and
never print a success/proof marker. This matters because MiniZinc treats nonzero
child exit as `ERROR`, including when the child printed `UNKNOWN`.

The direct driver interface remains separate: `MODEL.fzn --time-limit SECONDS`
retains its existing filename-first syntax, immediate zero deadline, optional
explicit HiGHS route, and exit **1** for an ordinary incomplete solve.
It also accepts the native controls above; supplying them with `--backend highs`
is an error. `--node-limit` and `--native-node-limit` are aliases and cannot both
be supplied.

The `.msc` does not advertise enumeration, intermediate incumbents, parallel
search, randomness, or solver statistics. The driver rejects such flags if
forwarded. MiniZinc itself may consume `--statistics` for compilation/output
statistics or consume `--parallel` without forwarding it to an unsupported solver;
absence from `stdFlags` is not a promise that MiniZinc rejects every such outer
option. Actual 2.10.1 tests reject `--all-solutions` and
`--intermediate-solutions`, and force `-s`/`-p` forwarding to check the driver
boundary.

## Library lowering and rejection

The dedicated library overrides only these native global entry points:

| Standard library entry | Emitted predicate | Preserved boundary |
|---|---|---|
| `fzn_all_different_int` | `all_different_int` | Original positions and aliases; no legacy registry alias inference |
| `fzn_table_int` | `gecode_table_int` | Row-major tuple flattening, positive arity; zero arity rejected because flat cells lose tuple count |
| `fzn_regular` | `gecode_regular` | Literal `Q/S/d/q0/F`, row-major transitions, one-based source states and failure state zero |
| `fzn_circuit` | `gecode_circuit` | Nonempty arrays; nonnegative original index bases retained, negative bases translated by subtracting the original minimum index from every successor |
| `fzn_cumulative` | four-argument `gecode_cumulatives` | Original starts, durations, demands and capacity; no substitution from `lb`/`ub`; fixed data required by the frontend |

Cumulative durations/demands/capacity must be literals or singleton domains in the
emitted original FlatZinc declarations. The wrapper does not infer them from
propagation. Fixed zero-duration tasks consume no resource, and intervals are
half-open. Native scheduling arithmetic limits still apply. MiniZinc's standard
library may first simplify high-level cumulative models into other equivalent
constraints; the tests deliberately force the native wrapper as well as exercise
standard simplification.

Remaining standard-library decompositions are accepted only when their *complete*
emitted model passes frontend admission. For example, the pinned library can
lower reified Regular to a larger ordinary Regular and exact Boolean/linear
constraints; positive and complement witnesses are tested. This is not a new
native reified-Regular API. There is no direct registry alias fallback.

The narrow `redefinitions.mzn` declares only supported integer implications and
provides explicit compiler errors for variable multiplication/division/modulo and
unsupported reified integer/linear equalities. It deliberately does not copy
Gecode's broad redefinitions. Unsupported float/set variables, search annotations,
nonlinear or unknown predicates, malformed records, unbounded/native-out-of-range
domains, and unsupported global shapes remain explicit frontend errors whenever
they survive compilation. Constant simplification or a supported exact standard
library decomposition can eliminate a higher-level unsupported construct; no
claim is made that all such source syntax is categorically rejected.

MiniZinc's atom-only `ctx_pos`, `ctx_neg`, and `ctx_mix` context annotations are
admitted explicitly. Calls with these names and unknown annotations remain
rejected. Their presence does not weaken the relation or original checker.

The default tested MiniZinc pipeline is its ordinary single pass. Options such as
`--use-gecode`/`-O3`, shaving, and SAC invoke another solver during compilation and
are outside this registration's verified route; in particular they have not been
audited against the documented legacy zero-duration cumulative discrepancy.

## Reproduction and acceptance gates

Provision a compiler manually from the **official** pinned release; CMake and the
test never fetch dependencies. `tools/flatzinc/minizinc-release.json` records the
2.10.1 macOS ARM64 package source and its official SHA256. Verify the downloaded
archive before extraction, and keep the compiler and its bundled standard library
together. Local installation was entirely under `implementation/deps`.

Run the committed gate against a prebuilt driver:

```sh
python3 -B test/optimize/minizinc_registration.py \
  --minizinc /workspace/implementation/deps/MiniZinc-2.10.1-aarch64-apple-darwin/bin/minizinc \
  --binary /path/to/fzn-gecode-optimize
```

Add `--registration /path/to/gecode-optimize.msc` to exercise an actual configured
build/install artifact **in place**. The runner does not rewrite that file or
substitute its library. It resolves relative paths against the registration's
directory, requires the executable plus `--minizinc` to match `--binary`, and
rejects a `-G` library alias. Reports include the actual configuration SHA256,
every dedicated library file's SHA256 and a deterministic aggregate library hash.
Both configuration and library must remain unchanged throughout the gate.

The gate requires version 2.10.1, otherwise creates a temporary `.msc`, checks discovery,
compiles every supported fixture, audits emitted predicate names, and sends each
model through the real compiler/driver/`.ozn` output pipeline. Independent tiny
integer oracles cover signed objectives and offsets, aliases/holey domains,
all-different, table aliases, Regular including compiler-generated reification,
negative/nonunit circuit bases, Element index shifts, cumulative half-open and
zero-duration semantics, and fixed parameters. It also checks explicit errors,
filename ordering, count overflow, zero-time conventions, and actual finite parser
workloads under a 1ms timeout. These timeout checks are conformance tests, not
solver-performance measurements. A machine completing the entire parser workload
within 1ms will fail the fixture rather than silently omit the timeout gate.

There are per-child and aggregate deadlines. On POSIX the test starts a new process
group and terminates it during cleanup, including MiniZinc's driver child. On
Windows it uses the existing creation-time Job Object containment helper and
fails closed if containment cannot be established. The release gate must exercise
this path on a real Windows host before claiming Windows runtime verification.
JSON reports contain all required cases plus driver/compiler and fixture hashes.
The existing direct CLI suite must also continue to pass.

Local results and exact commands are reported with the feature commit; remote CI
and non-macOS execution are not implied by the local gate.

## Primary references

- [MiniZinc 2.10.1 official release](https://github.com/MiniZinc/libminizinc/releases/tag/2.10.1)
- [Solver configuration format](https://docs.minizinc.dev/en/2.10.1/fzn-spec.html#solver-configuration-files)
- [FlatZinc standard flags](https://docs.minizinc.dev/en/2.10.1/fzn-spec.html#command-line-interface-and-standard-options)
- [FlatZinc error and warning output](https://docs.minizinc.dev/en/2.10.1/fzn-spec.html#error-and-warning-output)
- [Pinned MiniZinc external-solver implementation](https://github.com/MiniZinc/libminizinc/blob/2.10.1/solvers/fzn/fzn_solverinstance.cpp) (`solve`: nonzero-only time flag/watchdog, exit-status mapping)
- [Pinned context annotation declarations](https://github.com/MiniZinc/libminizinc/blob/2.10.1/share/minizinc/std/stdlib/stdlib_ann.mzn)
- [Pinned high-level cumulative simplifications](https://github.com/MiniZinc/libminizinc/blob/2.10.1/share/minizinc/std/cumulative.mzn)

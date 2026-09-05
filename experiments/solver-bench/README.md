# Gecode local optimization laboratory

A reproducible local benchmark and an opt-in binary-linear optimization extension for Gecode. The extension combines Gecode's finite-domain search with continuous HiGHS LP relaxations; it does not run HiGHS MIP search. Development-only configuration selection is compiled into a small C++ decision tree. No LLM or network call occurs inside measured solving.

See `PROTOCOL.md` for the evaluation design, `COVERAGE.md` for existing benchmark suites and coverage gaps, `SOFTWARE.md` for APIs and implementation limits, and `ANALYSIS.md` for score definitions. The final `REPORT.md` and `reports/` are generated/published after the measured batches complete. Raw runs are always retained in `results/`.

## Build

From the repository root, with Python 3.12+, Git, CMake and a C++17 compiler available:

```sh
python3 experiments/solver-bench/build.py --jobs 4
```

The builder extracts the exact upstream baseline from Git commit `3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e`, verifies original source bytes, builds matched Release libraries, and fetches the pinned HiGHS source if it is missing. HiGHS is commit `04024d701f79feb8e2f18bc3df0dffc04ef05088` (v1.15.1). It installs nothing system-wide. The source cache makes later builds local. `--skip-libraries` reuses existing libraries after cache/source checks and records their hashes; it is not a claim to re-establish the provenance of an arbitrary cached binary.

Four drivers and focused correctness tests are written into `build/solver-bench/bin`. Build metadata records commands, flags, machine, source and binary hashes. Each build also snapshots its drivers, selected policy, LP headers and modified search headers under the output's `source/` directory. FlatZinc compatibility needs its separate int/set/float-enabled builds:

```sh
python3 experiments/solver-bench/fzn-build.py --jobs 4
```

The delivered snapshot's `iterations/` binaries are local-machine evidence, not portable executables. Rebuild to evaluate another platform and keep its results in a separate cohort.

## Correctness checks

Inspect the focused check plan, then run it when no benchmark is active:

```sh
python3 experiments/solver-bench/tests/run.py
python3 experiments/solver-bench/tests/run.py --execute
```

The runner executes six C++ tests, Python import/schema checks, and tiny native-controller checks with independently enumerated optima. It launches no performance batch, build or download. Use `--bin` to select an iteration, `--groups cpp,python` to omit native-controller subprocess checks, and `--output` to preserve a separate result. Default behavior prints commands only; `--execute` starts the checks.

The native-controller checker can also compare default-mode assignments and search counts with a prior build:

```sh
python3 experiments/solver-bench/tests/native_controller.py \
  --bin build/solver-bench/iterations/v2 \
  --legacy-bin build/solver-bench/iterations/v1-final
```

`--legacy-bin` is optional. Six tiny input files are generated locally; no external corpus is required. Python assertions must remain enabled.

## Fast local loop

```sh
python3 experiments/solver-bench/suite.py quick
python3 experiments/solver-bench/suite.py development
```

The quick preset runs one small development instance per family in each representation with a 250ms cutoff. The development preset runs all 108 binary development cases against several explicit configurations with a one-second cutoff. Presets do not build or download implicitly. Run one benchmark process at a time, with no concurrent builds or stress tests. Use `--dry-run` to inspect commands, `--output-dir` for a fresh run, or `--resume` for a stopped run whose protocol has not changed.

The general runner supports custom immutable manifests, family/instance filters, repetitions and budgets:

```sh
python3 experiments/solver-bench/bench.py \
  --split dev --kinds binary --configs stock,fix4,lns-fix4 \
  --repeats 3 --limit-ms 1000 --output experiments/solver-bench/results/my-dev.jsonl
```

Never tune on held-out, public or scale results and then present those same results as an untouched test. Train a new development-only structural policy with complete action coverage:

```sh
python3 experiments/solver-bench/train_policy.py \
  --runs experiments/solver-bench/results/my-dev.jsonl \
  --configs stock,fix4,lns-fix4
```

Rebuild after changing `policy.hpp`. The trainer audits source/input/binary identities, validates results and features, selects tree depth with three development seed folds, and records all provenance. It optimizes configuration choice, not the mathematical problem definition. An offline LLM can propose another implementation or safe action; the deterministic validators, exhaustive tests and development benchmark decide whether to retain it. An unvalidated candidate solution never becomes an incumbent, and heuristic neighborhoods never constrain the later unrestricted proof search.

## Evaluation presets

```sh
python3 experiments/solver-bench/suite.py test
python3 experiments/solver-bench/suite.py public
python3 experiments/solver-bench/suite.py cold
python3 experiments/solver-bench/suite.py scale
python3 experiments/solver-bench/suite.py flatzinc
```

The main generated test has five held-out seeds per family/size and three repeated timings. `public` runs whole cached OR-Library and legacy MIPLIB instances; `cold` disables common initial solutions; `scale` tests mechanically larger sizes; `flatzinc` keeps upstream compatibility fixtures separate. The supplied starting solutions are feasible witnesses, not published optima. Some public MIPLIB cases have no starting solution. The runner reports that per instance.

For an explicit extension-disabled control, pass `--configs stock,disabled,lp,portfolio`. `lp` is the preceding bound-only implementation, `portfolio` is the new frozen selector, and `stock` uses unchanged upstream libraries. Native CP modes can be compared with `--kinds native --configs stock,native-lns,native-incumbent`; these are controller policies using existing Gecode search/propagation capabilities.

## Analyze and share

```sh
python3 experiments/solver-bench/analyze.py \
  --runs experiments/solver-bench/results/local/test.jsonl \
  --out-dir experiments/solver-bench/reports/my-test
```

The output includes a standalone HTML leaderboard, machine-readable JSON, per-instance CSV and paired comparison CSV. Development reports require `--exploratory`. Incomplete batches additionally require `--allow-incomplete` and remain visibly exploratory. `--manifest` accepts relocated immutable manifests if the original absolute paths are unavailable; content hashes must match. No hosting or remote publication is required to use the leaderboard locally.

Keep a submission's JSONL together with its `.meta.json`, corpus, build metadata and policy/source snapshot. The analyzer rejects missing runs, inconsistent inputs, invalid witnesses, mismatched binary provenance and conflicting optima. FlatZinc exact-output regression summaries remain separate from optimization proof statistics because alternate valid outputs need semantic review.

## Separate HiGHS MIP reference

An optional reference competitor uses HiGHS's native MIP solver to contextualize the Gecode results. It is a separate executable with no Gecode linkage; the enhanced Gecode extension continues to use continuous LPs only. After building the pinned HiGHS dependency, compile and run the reference explicitly:

```sh
python3 experiments/solver-bench/reference_bench.py build
python3 experiments/solver-bench/reference_bench.py run \
  --warm 1 --limit-ms 1000 --repeats 3 \
  --output experiments/solver-bench/results/highs-mip-public-warm.jsonl
python3 experiments/solver-bench/reference_bench.py run \
  --warm 0 --limit-ms 1000 --repeats 3 \
  --output experiments/solver-bench/results/highs-mip-public-cold.jsonl
```

The default reference cohort contains the 17 whole public binary instances. `--manifest` and `--split` select another binary cohort. Construction, supplied-start injection, search, witness checking and teardown share the stated budget; input parsing is excluded as in the Gecode driver. Only one solver process runs at a time. HiGHS receives one thread and zero requested absolute/relative MIP gaps. Its optimality and infeasibility statuses remain numerical claims: final and within-budget binary witnesses are checked exactly, but no exact dual certificate is produced. Reference JSONL and summaries belong to a separate comparison track and are not accepted as enhanced-Gecode results.

## What the result can establish

This benchmark measures a controlled change to selected Gecode models and policies. Gecode is a constraint-programming toolkit, not an open-source clone of CPLEX or Gurobi. Native global constraints, AFC branching, restarts and LNS primitives already exist upstream. Our new LP certificates, conditional variable fixing, root strengthening and primal generation target the binary-linear subset; an arbitrary FlatZinc or native model does not automatically receive them.

A timeout becoming an optimal proof is a useful practical improvement at the stated cutoff. It does not make an NP-hard problem class polynomial, demonstrate superiority over commercial solvers that were not run, or establish speedups on every formulation. See the report for regressions and the difference between warm-start proof, cold feasibility, larger sizes and public-instance transfer.

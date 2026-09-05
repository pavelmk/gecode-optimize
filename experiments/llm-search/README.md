# Experimental Gecode improvements and reproducible measurements

This directory accompanies two opt-in changes to Gecode 6.4.0. They were written
and evaluated with coding agents; no LLM call runs inside the solver. The goal is
to test concrete solver-development hypotheses, including negative results.

The measured result is mixed. Clique inference removes an exponential-looking
binary search on designed Hall contradictions, while adding overhead on small
random coloring instances. Propagation-count checkpointing improves some default
search runs, but Gecode's existing copy-at-every-branch configuration matches the
gain. These experiments do **not** establish a generally faster Gecode release.

Read [the complete report](results/REPORT.md), [all per-instance comparisons](results/comparison.csv),
and [the recorded parameter selection](results/selection.json).

## Implemented features

### Propagation-count checkpoints

```cpp
Gecode::Search::Options options;
options.threads = 1;
options.c_p = 10; // additional checkpoint after >=10 propagator invocations
Gecode::BAB<MyModel> search(model, options);
```

`c_p=0` is the unchanged default. Sequential DFS/BAB preserve their existing
copy-distance and adaptive-recomputation behavior, and can additionally clone a
stable branch state after sufficiently many propagator invocations in its latest
status call. This is a work proxy, not a measurement of nanoseconds or all replay
work. It trades potentially less repeated propagation for more copying and memory.
Parallel search and LDS ignore this experimental option.

Code: `gecode/search.hh`, `gecode/search/options.hpp`,
`gecode/search/seq/dfs.hpp`, `gecode/search/seq/bab.hpp`.
Adding an Options member changes the C++ ABI; rebuild clients and libraries
together, and do not mix headers from one build with another build's libraries.

### Automatic clique inference for disequality graphs

```cpp
#include <gecode/minimodel/experimental-cliques.hpp>
Gecode::IntArgs edges({0, 1, 1, 2, 0, 2});
Gecode::Experimental::rel_with_cliques(home, variables, edges, Gecode::IPL_DOM);
```

The helper posts the supplied `x[u] != x[v]` constraints, discovers up to one
greedy clique per vertex, deduplicates them, and posts redundant `distinct`
constraints. This reuses the existing domain-consistent allDifferent propagator.
For example, three mutually different variables with domains `{0,1}`, `{0,1}`,
and `{0,1,2}` force the last variable to 2. Separate binary propagation misses
that deduction at the root.

This is an explicit experimental posting API, not a transparent rewrite of
arbitrary existing Gecode models. An expert who already models the clique with
`distinct` does not need the inference pass. The pass can add unnecessary work
on easy or triangle-free graphs. All original feasible solutions are preserved.

## Reproduce

Requires CMake 3.21+, a C++17 compiler, and Python 3.12+. No Python packages,
LLM API key, commercial solver, or system-wide Gecode installation is required.
On this machine Python is available at `/opt/homebrew/bin/python3`.

From the repository root:

```sh
python3 experiments/llm-search/run.py
```

The script extracts the pinned stock source from Git commit
`3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e`, builds stock and modified static
libraries with matching Release settings, and compiles the same model driver
against each. It runs correctness checks before measuring performance.

If using the supplied binaries on the same compatible Mac:

```sh
/opt/homebrew/bin/python3 experiments/llm-search/run.py --skip-build
```

The full upstream search registry contains 25,808 cases and may take several
minutes. The 180 focused enabled-checkpoint configurations and 3,300 clique
combinations are separate tests. The initial upstream result is preserved in
`results/checkpoint-validation.json`; a fresh full run writes a per-case log.

For a single before/after demonstration:

```sh
build/llm-search/bin/stock experiments/llm-search/demonstrations/demo_pigeonhole_11_into_10.txt 0 0 8 size 1000 1
build/llm-search/bin/modified experiments/llm-search/demonstrations/demo_pigeonhole_11_into_10.txt 1 0 8 size 1000 1
```

Arguments are: instance, clique inference on/off, checkpoint threshold,
copy distance, branching (`size`, `degree`, or `afc`), time limit in milliseconds,
and repeat count. JSON output includes assignment, status, objective, solver
time, model-build time, node and propagation counts, and process peak RSS.

## Automated candidate evaluation

The implemented development race evaluates checkpoint thresholds 1, 5, 10, 25,
and 100, plus stock controls. It selects an experimental threshold on 18
development instances and freezes it before seven repetitions on 18 new-seed
instances. This is automated parameter selection for an LLM-written code change;
it is not an autonomous loop that continually generates new source patches.

The same runner can evaluate further compiled variants. Changes to native code
must pass correctness checks, including exact optimum checks, before their
times are eligible for comparison. Do not feed held-out results back into the
selection loop and continue calling that set held out.

## Data and evidence

- `generator.py`, `manifest.json`, `instances/`: deterministic random and structured
  instances for coloring, makespan scheduling, and weighted vertex cover. There
  are 36 medium cases, 24 tiny exact checks, and two controls.
- `generate_demos.py`, `demo-manifest.json`, `demonstrations/`: four deliberately
  favorable pigeonhole contradictions and one unfavorable sparse-cycle control.
- `validate.py`, `certify.py`: independent assignment checks and exact reference
  computations. Reference answers are stored in JSON and never given to the
  solver, which reads only the companion text problem.
- `bench.py`: serial randomized paired comparisons, independent validation,
  raw JSONL, and per-instance summaries. Timeouts remain visible.
- `analyze.py`: CSV and report generation retaining gains and regressions.
- `results/`: raw measurements, metadata and executable hashes, correctness
  evidence, independent references, selected threshold, and final report.

The datasets are synthetic and small, the held-out families are the same as the
development families, and testing was on one machine. Tiny correctness-case
timings are not used as performance evidence. LP relaxations, cutting planes,
and explanation-based conflict learning were not implemented in this prototype.

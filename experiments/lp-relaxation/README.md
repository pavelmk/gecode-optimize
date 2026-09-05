# Certified LP bounds inside Gecode

This experiment adds an optional **LP relaxation bound propagator** to Gecode.
Gecode still searches over binary variables and checks all integer constraints.
HiGHS solves continuous relaxations to identify branches that cannot improve
the incumbent. It never runs its mixed-integer solver.

This implements one important technique used by CPLEX and Gurobi. It is not a
reimplementation of their entire MIP engines. Gecode is a constraint programming
solver; it is not an open-source clone of either product. Its native propagation
and search do not automatically solve a joint LP relaxation of these rows.

See [RESULTS.md](results/RESULTS.md) for measured outcomes, including regressions, and
[DATA_FORMAT.md](DATA_FORMAT.md) for the generated problems and independent oracles.

## Why this feature

Suppose a knapsack branch has already selected several items. Each remaining
item has a profit and consumes two limited resources. Native constraint
propagation rules out individually impossible choices. The LP also considers
all remaining choices together, temporarily allowing fractional items. If even
this optimistic fractional packing cannot beat the best known integer packing,
Gecode can discard the whole branch.

For minimization, the relaxation supplies a lower bound. If that bound is
greater than the current allowed objective maximum, the propagator fails the
space. Otherwise it raises the objective minimum. Existing Gecode propagation
then uses the stronger bound. This can trade thousands of cheap, unproductive
nodes for a much smaller number of more expensive nodes.

Both commercial solvers use relaxation bounds in their mixed-integer search:
[CPLEX branch and cut](https://www.ibm.com/docs/en/icos/22.1.1?topic=c-branch-cut-in-cplex),
[Gurobi MIP introduction](https://www.gurobi.com/resources/blog/mixed-integer-programming-an-introduction-to-the-basics).
Their other features, including cut generation, presolve, primal heuristics,
strong branching and parallel search, are outside this implementation.

## Implementation

The public API is in `gecode/minimodel/lp-relaxation.hpp`:

```cpp
namespace LP = Gecode::Experimental::LpRelaxation;
LP::LinearModel matrix;
// Fill row-major matrix.a, row lower bounds matrix.b, costs matrix.c.
// Model: min c*x, A*x >= b, binary x.
auto backend = std::make_shared<LP::Backend>(matrix);
LP::binary_linear_minimize(*this, x, objective, backend,
                          LP::Frequency::EveryNode);
```

The posting function adds native linear constraints and the LP propagator. Do
not post a second copy of those rows. Additional native Gecode constraints may
be posted normally; the supplied LP remains a relaxation if they only restrict
the feasible set further. Clone the application's variables in `Space::copy()`
as usual; the propagator manages its own views and backend lifetime.

- `lp-model.hpp`: shared binary linear model validation and native posting.
- `lp-backend.hpp`: a continuous HiGHS dual-simplex workspace, retained basis,
  per-call column bound updates, runtime limits and statistics.
- `lp-certificate.hpp`: exact arithmetic validation of candidate lower bounds.
- `lp-relaxation.hpp`: native Gecode actor, cloning, subscriptions, disposal and
  objective propagation.

Cheap native propagation runs before the LP actor. The actor reruns the LP when
binary variable domains change; objective-only events reuse its cached bound.
An optional `Frequency::Root` mode solves just the root relaxation. A shared
backend overwrites every column bound on every call, including when returning
to a sibling branch. It serializes calls with a mutex. The experiment uses one
search thread; multi-thread speedup is not evaluated.

## Numerical correctness

A floating-point LP optimum or infeasibility status never directly prunes a
space. For `A*x >= b`, choose any nonnegative multiplier vector `y`. Over a
current binary box `[l,u]`, a valid bound is

```text
y*b + sum_j min((c - A' y)_j * l_j, (c - A' y)_j * u_j).
```

The LP row duals are only suggestions for `y`. We clamp negative values to zero
and quantize finite values to nonnegative multiples of `1/2^20`. The bound is
then computed with checked signed 128-bit integer arithmetic and rounded up
mathematically, since the original objective is integral. This is weak duality
plus exact arithmetic, not an assumption that the numerical LP solution is
accurate. If checking fails, ordinary Gecode propagation continues. Platforms
without signed 128-bit arithmetic get this safe fallback.

Supported models use binary variables, integer coefficients of magnitude at
most 1e9, and objective ranges supported by Gecode's integer variables. The
experiment uses a dense coefficient matrix internally. Very large sparse MIPs,
general continuous variables and automatic extraction from arbitrary Gecode
constraints are not supported. LP calls have a 10,000-iteration and 0.2-second
soft cap; the outer Gecode time limit can be exceeded by a pending LP call.

## Build and run

Requirements: C++17 compiler with signed 128-bit arithmetic for strengthened
bounds, CMake, Git and Python 3.12 or later. The build script downloads pinned
HiGHS sources on first use and builds locally; it does not install globally.

From the repository root:

```sh
python3 experiments/lp-relaxation/build.py
python3 experiments/lp-relaxation/run.py --tests-only
python3 experiments/lp-relaxation/bench.py --split test --repeats 5 \
  --output experiments/lp-relaxation/results/held-out.jsonl
python3 experiments/lp-relaxation/analyze.py
```

The build creates `build/lp-relaxation/bin/stock` from an independently verified
archive of the pinned Gecode commit, and `build/lp-relaxation/bin/lp` from this
source tree. Both have the same optimization and native module settings.

Run an individual problem:

```sh
build/lp-relaxation/bin/stock \
  experiments/lp-relaxation/instances/test_knapsack_710002.txt none afc 3000 1 1
build/lp-relaxation/bin/lp \
  experiments/lp-relaxation/instances/test_knapsack_710002.txt node afc 3000 1 1
```

Arguments are input file, LP mode (`none`, `root`, `node`), variable branching
(`afc`, `size`), time limit in milliseconds, common warm start (`0`, `1`), and
number of repetitions. `afc` uses Gecode's accumulated failure count divided by
domain size. Both binaries use the same objective-aware value order.

For an application using installed packages:

```cmake
# Configure Gecode with -DGECODE_ENABLE_LP_RELAXATION=ON
# and -Dhighs_DIR=<HiGHS build or installed package directory>.
find_package(Gecode CONFIG REQUIRED COMPONENTS lp)
target_link_libraries(your_application PRIVATE Gecode::gecodelp)
target_compile_features(your_application PRIVATE cxx_std_17)
```

The CMake option defaults to OFF. A normal Gecode build has no HiGHS dependency.
The experimental module is header-only and installs with the Gecode headers.

## Experimental protocol

We generate weighted set cover, two-resource knapsack and weighted bipartite
vertex cover, with disjoint development and held-out seeds. The suite retains
all instances, including cases on which LP overhead dominates. Small controls
exercise integrality gaps, infeasibility and signed objectives.

Every result is checked against the original constraints and an independent
exact reference algorithm. Optima are stored only in JSON used by validation;
the C++ solver reads a separate TXT file containing no optimum. A greedy
incumbent is generated before the reference and supplied equally to both
solvers. Greedy generation is offline and excluded from timing. Some greedy
solutions are already optimal, so their solve time measures proof effort.

Timed runs execute serially in shuffled order. They include CP and LP workspace
construction, propagation, search and teardown. They exclude input parsing,
process launch and result serialization; separate process wall times are also
recorded. All methods receive the same per-run limit. Timeouts are censored,
not completed solve times. PAR2 is a score assigning twice the cutoff to a
timeout; it is explicitly separate from observed elapsed time.

Seven configurations separate the effect of the feature from binary and
branching effects: stock AFC, feature compiled but disabled AFC, root LP AFC,
per-node LP AFC, plus stock/root/node with size branching. Development selected
per-node AFC before held-out execution. Existing experimental clique and
propagation-checkpoint features are disabled in these drivers.

An extra propagator can also affect AFC-based branching through its failures
and subscriptions. Consequently the AFC comparison measures the integrated
feature, not an isolated mathematical bound under a fixed search tree. The
size-branching configurations provide a control for that interaction.

## Role of an LLM

The LLM's role here is to propose and implement a reusable solver improvement,
generate tests, and evaluate it. There is no LLM call during search and no API
inference latency hidden outside the clock. The benchmark measures the added
LP technique; it does not establish that an LLM performs mathematical search
better than Gecode, or that GPT-6 is uniquely needed to write this code.

These synthetic instances can establish a mechanism and a useful class of
speedups, not broad superiority on real workloads or parity with commercial
MIP solvers. The natural next study is a larger public benchmark suite and an
adaptive policy for when to pay for another LP relaxation.

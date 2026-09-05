# Experimental Gecode extensions: software and correctness

This checkout adds an opt-in binary linear optimization module to Gecode 6.4.0, based on upstream commit `3e0e8ee76fb4ba01c53616dce02c0bb1a53f159e`. Gecode still performs propagation, branching, and proof search. HiGHS 1.15.1 supplies continuous LP solutions; a separate exact integer checker decides which LP-derived deductions Gecode may use. The additions are reusable C++ code, not per-instance answers or a call to an LLM during search.

The implemented scope is `min c*x`, subject to `A*x >= b` and binary `x`. It is a prototype for this model class, not a general replacement for CPLEX or Gurobi. Performance results and benchmark coverage belong in the experiment report and [COVERAGE.md](COVERAGE.md); fewer nodes alone do not establish a speedup.

## What was added

| Addition | Implementation | Actual scope |
| --- | --- | --- |
| Native binary linear model adapter | [lp-model.hpp](../../gecode/minimodel/lp-model.hpp) | Posts the complete matrix, binary domains, and `objective == c*x` using existing Gecode propagators. |
| Continuous LP lower bounds inside propagation | [lp-backend.hpp](../../gecode/minimodel/lp-backend.hpp), [lp-relaxation.hpp](../../gecode/minimodel/lp-relaxation.hpp) | A real Gecode propagator tightens the integer objective or fails the current space only from checked bounds. HiGHS uses simplex with a reusable basis and one thread. |
| Exact bound certificates and conditional variable fixing | [lp-certificate.hpp](../../gecode/minimodel/lp-certificate.hpp) | Converts candidate dual multipliers into exact rational bounds. Tests both values of each unassigned binary variable against the current objective upper bound. No floating-point reduced cost is trusted. |
| LP call scheduling and certificate reuse | [lp-relaxation.hpp](../../gecode/minimodel/lp-relaxation.hpp) | Root-only or repeated LP solves, with an optional interval measured in additional assigned binary variables. Cached certificates are evaluated between solves. This is one actor's schedule, not a new global propagation scheduler. |
| Root row normalization and redundant cuts | [lp-strengthening.hpp](../../gecode/minimodel/lp-strengthening.hpp) | Integer gcd normalization, duplicate/tautology removal, simple infeasibility detection, overweight-literal fixings, pair conflicts, greedy cliques, and greedy covers. Signed coefficients are handled with complemented literals. Variables and objective retain their original mapping. |
| Bounded LP-guided candidate generation | [lp-primal.hpp](../../gecode/minimodel/lp-primal.hpp) | Rounds LP solutions, alternates with a distance-to-binary-target LP objective, and perturbs repeated targets. Every accepted candidate passes the exact original-matrix checker. This is a small feasibility-pump-style heuristic, not a complete commercial heuristic portfolio. |
| Disequality graph strengthening | [experimental-cliques.hpp](../../gecode/minimodel/experimental-cliques.hpp) | An opt-in helper finds graph cliques and posts redundant existing `distinct` constraints. It does not implement a new all-different propagator. |
| Propagation-aware search checkpoint option | [search.hh](../../gecode/search.hh), [seq/dfs.hpp](../../gecode/search/seq/dfs.hpp), [seq/bab.hpp](../../gecode/search/seq/bab.hpp) | `Search::Options::c_p` allows sequential DFS/BAB to clone a branching space after an expensive propagation call. Default zero preserves the previous clone policy. Parallel engines and LDS ignore this option. |

The benchmark [driver.cpp](driver.cpp) also implements a bounded incumbent-repair stage using ordinary Gecode neighborhood searches, followed by a fresh unrestricted BAB proof search. Its `auto` mode uses a small policy generated from development data and matrix statistics. Those are application-level experimental policies, not automatically installed solver defaults. [policy.hpp](policy.hpp) is explicit about the selected actions.

CPLEX and Gurobi publicly document LP relaxations, presolve, primal heuristics, and several cut families as MIP machinery. The closest inspiration here is their combination of better bounds, better feasible solutions, and stronger formulations. Their documented repertoire is much broader: for example CPLEX also lists MIR, Gomory, disjunctive, flow, and lift-and-project cuts. We do not claim to reproduce their private implementations or overall capabilities. See [CPLEX's explanation and catalog of cuts](https://www.ibm.com/docs/en/cofz/22.1.2?topic=cuts-what-are), [Gurobi's parameter groups](https://docs.gurobi.com/projects/optimizer/en/current/concepts/parameters/groups.html), and [Gurobi's guidance on relaxations, heuristics, cuts, and presolve](https://docs.gurobi.com/projects/optimizer/en/current/concepts/parameters/guidelines.html).

## What upstream Gecode already provides

Gecode already has integer, Boolean, set, and floating-point domains; specialized global propagators; customizable branching including AFC and CHB; DFS, BAB, LDS, restart and portfolio engines; path nogoods; parallel search; and cloning/recomputation. Its driver and examples already support neighborhood-search patterns. It also has a FlatZinc frontend. These capabilities are visible in the checked-out upstream-derived [integer API](../../gecode/int.hh), [search API](../../gecode/search.hh), [driver API](../../gecode/driver.hh), [search implementation](../../gecode/search), and [FlatZinc sources](../../gecode/flatzinc).

In particular, the new code uses upstream `linear`, `distinct`, and BAB rather than replacing them. AFC/CHB scores and path nogoods should not be described as a newly added SAT conflict-analysis engine. We have not added explanation-producing propagation, general clause learning, or lazy clause generation.

## Library invocation

The LP module is header-only. CMake option `GECODE_ENABLE_LP_RELAXATION` defaults to `OFF`; when enabled it requires the HiGHS CMake package version 1.15 or later and exposes `Gecode::gecodelp`. The benchmark pins HiGHS 1.15.1 rather than assuming all future versions behave identically. A source-tree application can use:

```cmake
set(GECODE_ENABLE_LP_RELAXATION ON CACHE BOOL "" FORCE)
# Point highs_DIR at the directory containing highs-config.cmake.
add_subdirectory(path/to/gecode gecode-build)
add_executable(my_solver main.cpp)
target_compile_features(my_solver PRIVATE cxx_std_17)
target_link_libraries(my_solver PRIVATE Gecode::gecodelp)
```

For an installed package, use `find_package(Gecode CONFIG REQUIRED COMPONENTS lp)` and the same target. A Gecode installation built with the LP option currently resolves HiGHS even when a downstream application requests only a native component. A build with the option disabled has no HiGHS dependency.

The following posting helper can be called from a `Space` constructor. It solves a weighted binary covering model and returns the backend for diagnostics; the actor also retains ownership. The objective variable must have a domain containing every objective value the caller intends to permit. For this example the complete natural domain is `0..9`.

```cpp
#include <gecode/minimodel/lp-relaxation.hpp>
#include <gecode/minimodel/lp-strengthening.hpp>

namespace LP = Gecode::Experimental::LpRelaxation;

std::shared_ptr<LP::Backend>
post_example(Gecode::Home home, const Gecode::IntVarArgs& x,
             Gecode::IntVar objective) {
  // Three binary variables; two rows; dense, row-major A.
  LP::LinearModel model;
  model.a = {1, 1, 0,
             0, 1, 1};
  model.b = {1, 1};
  model.c = {3, 2, 4};

  auto strengthened = LP::Strengthening::strengthen(model);
  auto backend = std::make_shared<LP::Backend>(
      std::move(strengthened.model));
  LP::Options options;
  options.frequency = LP::Frequency::EveryNode;
  options.reduced_cost_fixing = true;
  options.assignment_interval = 4;
  LP::binary_linear_minimize(home, x, objective, backend, options);
  return backend;
}
```

The caller supplies exactly three variables here, posts a brancher, implements the normal Gecode copying/cost interface, and runs BAB. The default `binary_linear_minimize(..., backend)` call uses repeated bounds without conditional fixing and with interval one. `Frequency::Root` without fixing performs a single bound computation; with fixing it retains that root certificate for later domain/objective events. “EveryNode” is an API name: actual LP calls are triggered by bound events and the assignment interval, not unconditionally once for each search node.

`LP::post_native(home, x, objective, model)` is the direct control path without any LP dependency. `LP::Strengthening::strengthen(model)` also works without HiGHS and can feed that path. To inspect an LP-guided candidate independently, include `lp-primal.hpp` and call `LP::Primal::generate(model, options)`; inspect `result.found`, `result.assignment`, and `result.cost`.

The primal checker verifies only the supplied matrix. If the surrounding Gecode model has additional constraints, restricted domains, or aliased columns, the candidate must also satisfy them before it is used as an incumbent. In contrast, an LP lower bound remains valid when extra constraints narrow the feasible set, because the supplied matrix is then a relaxation. Never convert a mere candidate-generation failure into an infeasibility claim.

## Why the LP deductions are safe

Let `S = 2^20`. For each finite proposed row multiplier, the checker clips negative values to zero and quantizes to a nonnegative integer `q_i`; set `y_i = q_i/S`. Every nonnegative multiplier vector is admissible. Neither LP optimality nor proximity of the numerical dual solution to a true optimum is required.

For any feasible point in the current box `l <= x <= u`, define

```text
r = S*c - A^T*q
N(l,u) = q^T*b + sum_j min(r_j*l_j, r_j*u_j).
```

Since `q >= 0` and `A*x >= b`, `S*c^T*x >= N(l,u)`. The integer objective therefore satisfies `c^T*x >= ceil(N/S)`. Products, sums, subtractions, and rounding are checked with signed 128-bit integer arithmetic. A NaN, infinity, invalid box, dimension error, overflow, or unsupported arithmetic implementation produces no deduction. Negative objectives use mathematical ceiling, not truncation toward zero.

For conditional fixing, substitute `x_j=0` or `x_j=1` in the same box expression. If that exact numerator exceeds `S*objective.max()`, the value cannot occur in any feasible solution allowed by the current objective domain. All values are checked against the original box before deductions are posted, so simultaneous fixings remain valid. This is reduced-cost-style reasoning implemented through an explicit certificate, not rounding a numerical reduced cost.

The native constraints remain posted. A numerical LP infeasibility status is recorded but is never sufficient to fail a space; no Farkas infeasibility-certificate checker was added. An LP primal objective is diagnostic only. Likewise, a numerical LP solution becomes an incumbent only after exact validation of every original matrix row and its objective.

The backend's model is immutable and its HiGHS state is protected by a mutex. Each call replaces every column bound, including bounds that become looser when search moves to a sibling. The reused simplex basis is a performance hint. Each Gecode space copies its own cached bound and certificate state. A certificate derived from any box remains valid when evaluated on another box of the same model, while an already evaluated bound is reused only along that space's narrowing history. These properties keep search recomputation and sibling traversal independent of numerical workspace history. The actor registers disposal and explicitly destroys its `shared_ptr` members when Gecode frees it.

## Why the root strengthening preserves binary solutions

For an integer row `a*x >= b`, division by the positive gcd `g` of its coefficients gives the equivalent row `(a/g)*x >= ceil(b/g)`. Identical coefficient rows retain the strongest right-hand side; a row below its binary minimum is a tautology, and one above its binary maximum proves infeasibility. The implementation keeps the input order of surviving original rows.

A signed row can be written as a packing row `sum w_j*l_j <= C` with positive weights: use literal `x_j` for negative `a_j`, literal `1-x_j` for positive `a_j`, and `C = sum(a_j > 0) a_j - b`. A literal with weight greater than `C` must be zero. Two weights whose sum exceeds `C` cannot both be one. A set of pairwise-conflicting literals admits at most one selected literal. Any cover whose total weight exceeds `C` admits at most `|cover|-1` selected literals. Those arguments justify the fixing, pair, clique, and cover cuts, including complemented literals.

The cuts are translated back to the original columns using checked integer arithmetic. Greedy discovery, cut caps, and deduplication limit work and can miss useful cuts; they do not affect validity. Failure in arithmetic on an original row throws rather than dropping it. Failure while constructing an optional derived cut skips that cut. There is no variable elimination, automatic sparse reformulation, cover lifting, iterative propagation-to-fixpoint presolve, or dynamic LP-violation separation here.

## Validation and remaining limitations

[v1-final-tests.json](results/v1-final-tests.json) records successful runs of all six focused suites with executable hashes and the verified source snapshot: 3,000 certificate models; backend bounds/sibling/thread checks; 2,160 exhaustive native/root/repeated propagator configurations; 10,800 conditional-fixing/cutoff/recomputation configurations; 4,000 strengthening configurations over 2,000 models; and 900 randomized primal cutoff models with independently checked accepted witnesses. These are finite tests supporting the algebra and lifecycle review, not a formal verification of Gecode or HiGHS.

Sanitizer executables were linked against existing uninstrumented dependency libraries. The reduced-cost control and enhanced versions both encountered the documented libc++ container-annotation report, and passed with that annotation check disabled. [reduced-cost-tests.json](results/reduced-cost-tests.json) and [primal-tests.json](results/primal-tests.json) preserve this qualification; this is not a fully instrumented dependency pass.

Important limits are:

- The public matrix API is dense and binary-only, with exact integer coefficients bounded in magnitude by `1e9` and natural objective bounds inside Gecode's integer range. It does not accept continuous or general integer decision variables, quadratic models, or arbitrary global constraints as LP rows.
- HiGHS time allowances and the outer Gecode stop check are soft. A long propagation call or model construction can overrun a requested wall-clock search limit. Each LP call currently has a 0.2-second allowance and an iteration cap; large models need further budget integration.
- Repeated certificate preparation is dense work. Conditional evaluation is linear in columns. Shared numerical state is serialized; single-thread benchmark results do not demonstrate scalable parallel LP search.
- The supported exact arithmetic path is GCC/Clang with checked `__int128`. Other compilers safely decline LP certificates, but still require a compatible HiGHS build if that module is enabled.
- The existing FlatZinc executable does not automatically discover matrices and post this LP actor. Its compatibility track tests existing frontend behavior separately. The strict experimental MPS importer accepts a bounded binary linear subset and explicitly rejects unsupported constructs; it is not a general MPS/MIP frontend.
- The additions do not provide general cut management, learned conflict explanations, branch-and-cut callbacks, pseudo-cost/strong branching, a commercial-scale primal portfolio, or a global optimality-gap API. They do not change the worst-case hardness of binary optimization.
- No GPT-6 inference, external tool protocol, or network request occurs inside the solver. The LLM's role in this experiment is proposing and implementing changes and organizing controlled evaluation. Any future online LLM policy should propose search choices; checked mathematics must remain responsible for pruning and accepting solutions.


# Learning to improve constraint solving: what this experiment investigates

The project discussed here is **Gecode**, the constraint-programming toolkit; “G-code” usually refers to machine-control instructions. Gecode is extensible open-source optimization software, but its architecture is not simply an open-source copy of CPLEX or Gurobi. That distinction determines where learning can help.

The implemented experiment adds reusable binary-linear optimization machinery to Gecode: continuous LP bounds, exact conditional deductions, root strengthening, and a bounded primal heuristic. An LLM coding agent proposed and implemented code and helped organize its evaluation. **The measured solver makes no LLM or network calls.** A development-trained decision tree selects among explicit configurations. Thus these measurements can compare implementations and policies; they cannot isolate the causal advantage of using an LLM rather than a human, random program search, or another coding system. See [SOFTWARE.md](SOFTWARE.md) for APIs/proofs and [PROTOCOL.md](PROTOCOL.md) for the measurement design.

## CP, MIP, and simplex

Linear programming optimizes a linear objective over continuous variables constrained by linear inequalities. Mixed-integer programming adds discrete variable restrictions. MIP solvers commonly solve continuous relaxations inside branch-and-bound, add valid cuts, and seek feasible integer incumbents. Simplex is important, particularly when reusing a basis after a small model change; it is not the only LP algorithm. Polynomial-time interior-point methods exist, and current solvers offer different root-relaxation methods. See [Karmarkar's original LP paper](https://www.stat.uchicago.edu/~lekheng/courses/302/classics/karmarkar.pdf) and [Gurobi's algorithm guidance](https://docs.gurobi.com/projects/optimizer/en/current/concepts/parameters/guidelines.html).

Finite-domain constraint programming instead maintains allowed values and runs propagators that infer smaller domains. Constraints such as all-different, circuit, cumulative resource use, or non-overlapping tasks can have specialized algorithms. Gecode's normal integer search is based on propagation and search rather than a mandatory simplex solve. A CP solver can nevertheless use LP relaxations, and a MIP solver can use domain propagation and combinatorial heuristics. These are complementary techniques, not mutually exclusive mathematical worlds. Gecode's [integer API](../../gecode/int.hh) and [search API](../../gecode/search.hh) show the facilities being reused here.

CP can therefore be an effective **local optimizer**: fix most decisions to a current solution, release a selected subset, and let propagation plus bounded search optimize that neighborhood. A local search can make a coordinated change that single-variable hill climbing cannot make. Gecode already documents LNS through restart-based search; it was not invented by this experiment. Its manual also describes custom propagators, branching, choices and recomputation. [Modeling and Programming with Gecode](https://www.gecode.dev/doc-latest/MPG.pdf), particularly sections 9.4.5 and 32.2.

## The solver loop and the available learning decisions

The following is a conceptual sequence; propagation, relaxation and incumbent events may interleave. The source references identify the actual implementation rather than implying that every optional feature runs in every configuration.

| Stage | Conventional role | Potential learned decision | What this experiment changes |
| --- | --- | --- | --- |
| Model construction | Choose variables, domains and constraints; a strong formulation can matter more than search tuning. | Recognize structure; propose an equivalent formulation or extra redundant constraints. | A common binary matrix adapter and independent encoding checks keep comparisons controlled. Arbitrary native/FlatZinc models are not automatically converted to LP. |
| Root simplification | Remove redundancy, tighten bounds and detect easy contradictions. | Choose transformations or their budget from model features. | [lp-strengthening.hpp](../../gecode/minimodel/lp-strengthening.hpp) normalizes integer rows, removes duplicates/tautologies and adds proven binary cuts. |
| Propagation | Domain changes schedule affected propagators; repeat until no more scheduled deductions or a failure. | Select strength, priority or an expensive check's frequency. | [lp-relaxation.hpp](../../gecode/minimodel/lp-relaxation.hpp) adds a low-priority expensive actor and schedules its LP calls by new assignments. Native propagator algorithms and the global scheduler remain unchanged. |
| Relaxation and lower bounds | Bound the best possible cost in a partial assignment; reject branches that cannot beat the incumbent. | Choose whether to solve a relaxation, which one, or how much effort to spend. | [lp-backend.hpp](../../gecode/minimodel/lp-backend.hpp) runs continuous HiGHS simplex; [lp-certificate.hpp](../../gecode/minimodel/lp-certificate.hpp) checks the bound exactly. |
| Cuts and conditional deduction | Add valid inequalities or exclude variable values that cannot meet the objective bound. | Rank candidate cut families, cuts or probing variables. | Root pair/clique/cover cuts and exact binary conditional bounds are implemented. No learned model is trusted to declare a cut valid. |
| Branching | Choose a variable/value split and explore alternatives. | Imitate strong branching or learn scores from graph/search features. | The paired core comparisons retain common native branching. No neural brancher was implemented. |
| Failure, backtracking and reconstruction | Detect contradiction and visit another branch, restoring state by copying/recomputation. | Predict where keeping a copy avoids expensive replay. | The separate opt-in `Search::Options::c_p` checkpoint option addresses this. It defaults to zero and is not evidence of a new conflict-learning engine. |
| Incumbent discovery | Find a complete feasible solution; its cost strengthens the upper bound. | Predict candidate assignments or choose primal heuristics. | [lp-primal.hpp](../../gecode/minimodel/lp-primal.hpp) proposes LP-guided binary candidates, then checks original rows exactly. |
| Neighborhood repair | Optimize a restricted region around an incumbent. | Choose released variables, neighborhood size, repair solver and effort. | [driver.cpp](driver.cpp) has bounded deterministic/randomized repair followed by unrestricted proof search. This controller uses existing Gecode engines. |
| Configuration/restarts | Spend effort across competing strategies and react to stagnation. | Train a small policy or adapt operator weights from outcomes. | [train_policy.py](train_policy.py) fits a development-only structural selector. It chooses a configuration; it is not a deep network or online LLM. |

For “propagator conflict time,” several distinct metrics are useful: time until a contradiction is discovered, cost per propagation, total propagator invocations, search failures/nodes, time to a good incumbent, and time to optimality proof. More conflicts can mean useful early pruning or simply a worse search. The practical target is better objective quality or more proofs within a budget, with elapsed time and overhead measured. A heavy new propagator can reduce nodes and still slow the solver.

## A concrete generated neighborhood

Consider a set-cover problem with four items and five available sets:

| Set | Items covered | Cost |
| --- | --- | ---: |
| A | 1, 2 | 4 |
| B | 3, 4 | 4 |
| C | 1, 3 | 3 |
| D | 2, 4 | 3 |
| E | 1, 2, 3, 4 | 5 |

Let each set have a binary selection variable. Every item must be covered, and the objective is total cost. Suppose the incumbent selects A and B, costing 8. Removing A or B alone violates coverage; adding another set alone increases cost.

A neighborhood operator proposes “release A, B, C and D; leave E at its incumbent value zero.” The repair solver keeps every original coverage constraint, imposes only `E=0` as a neighborhood restriction, and searches for cost below 8. It can replace A+B with C+D, costing 6. A one-variable improving move could not perform that exchange. But even an exhaustive proof inside this neighborhood would not prove the global optimum: choosing E alone costs 5 and lies outside it.

An LLM could generate the operator's **code**, for example selecting expensive chosen sets together with overlapping alternatives. A small network could score variables in a variable/constraint graph. A generic controller could instead use recent improvement rates to choose among several operators. The output needed by Gecode is modest: a list of released variable indices and a time budget, not a natural-language solution.

Correctness depends on simple invariants:

1. Original feasibility constraints and the original objective remain unchanged during repair. “Relax the neighborhood” normally means removing temporary incumbent fixings, not removing coverage/capacity constraints.
2. A candidate is checked against the complete original model before becoming an incumbent. If a heuristic deliberately relaxes original constraints, its output needs repair and validation first.
3. A failed or exhausted neighborhood establishes only a local result. The later proof search must be unrestricted except for valid incumbent objective bounds and proven deductions.
4. If changing the operator during a running search, stored branch choices must remain replayable. Freeze the actual selected index/value in the choice; do not reinterpret old choices using a newly updated external policy.

The example describes a possible learned operator, not a claim that this exact semantic operator was implemented. The current repair controller releases subsets using fixed, auditable rules. Its overhead is included in solver timing.

## Evidence for learning and program generation

Several published directions closely match the available decisions, while supporting different kinds of claims:

| Primary work | What it demonstrates | Relevant limit |
| --- | --- | --- |
| [Gasse et al., NeurIPS 2019](https://arxiv.org/abs/1906.01629) | A graph convolutional network on the variable/constraint bipartite graph learns branching by imitating strong branching, with reported gains on the studied MILP distributions. | Branching guidance retains exact solver search; it is not a theorem that a neural rule wins on arbitrary MILPs. Inference overhead matters. |
| [Song et al., NeurIPS 2020](https://arxiv.org/abs/2004.00422) | Learned neighborhood selection lets an existing integer solver repair selected subproblems; the work studies imitation and reinforcement learning. | Generality of the interface does not imply distribution-free performance. |
| [Sonnerat et al., 2021/2022](https://arxiv.org/abs/2107.10201) | Learned LNS for mixed-integer programs directly studies learning which parts of an incumbent to reoptimize. | Better primal progress is different from faster global optimality proof. |
| [Ropke and Pisinger, Transportation Science 2006](https://pubsonline.informs.org/doi/10.1287/trsc.1050.0135) | Adaptive LNS uses multiple destroy/repair operators and adjusts their use from performance. | This is an important non-deep-learning baseline; operator adaptation does not require an LLM. |
| [FunSearch, Nature 2024](https://www.nature.com/articles/s41586-023-06924-6) | An LLM proposes executable programs, systematic evaluators score them, and evolutionary search retains useful variants; online bin packing is one application. | The LLM is used in algorithm discovery, while the resulting heuristic is executable code. The paper does not establish GPT-6/Gecode speedups. |
| [Evolution of Heuristics, ICML 2024](https://proceedings.mlr.press/v235/liu24bs.html) | Co-evolves heuristic descriptions and code, evaluated on combinatorial optimization tasks. | A generated operator must be compared to strong hand-designed and simpler search baselines under equal evaluation budgets. |
| [AlphaEvolve technical report, 2025](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf) | Extends LLM/evaluator/evolution workflows to larger algorithmic code changes. | Its reported results concern its own applications and Gemini-based system; they are not a result for this Gecode extension or GPT-6. |

Other plausible targets include cut ranking, initial incumbent generation, restart policies, and choosing propagation strength. The key distinction is whether learning changes **search effort** or asserts **mathematical truth**. Selecting an exhaustive branch order can be heuristic. Removing a feasible region, accepting a solution, or declaring infeasibility requires sound logic or validation. Here numerical LP output is also treated as a proposal: only exact rational certificates may prune.

## Where an LLM could enter a live system

Gecode is a C++ toolkit. A host application can collect a snapshot and consult an external service between search episodes, or a custom brancher can consume precomputed scores. No built-in generic LLM tool-call protocol was added to this checkout. The practical first integration is an outer controller: observe model/search statistics, request a structured policy or operator, validate it, then run a bounded solver episode with a deterministic fallback.

Calling an LLM for every propagator execution is unlikely to be an economical default. Native propagation deliberately consists of many small incremental operations; serializing state and waiting for inference adds a new cost at each call. As an **illustration, not a measured latency claim**, 10,000 synchronous calls taking 0.1 seconds each add 1,000 seconds before accounting for any saved search. A remote response would need to save more work than its full latency/cost. Per-node calls can have the same problem.

Three progressively more expensive interfaces are worth separating:

- **Offline code generation:** evolve branch scores, cut-selection policies, neighborhood operators, or core implementations using a test/evaluation harness; compile the chosen result. Inference cost is amortized across later solves.
- **Occasional runtime guidance:** ask at the root, after stagnation, or between neighborhoods/restarts; pass compact statistics and accept only a restricted action schema. The solver remains usable when the call fails or is late.
- **Frequent learned decisions:** train or distill a compact local model that can score nodes/variables cheaply, batch inference where possible, and benchmark its complete overhead. This is closer to neural branching than to a text conversation at each propagation event.

An LLM could also propose a stronger propagator implementation, but testing examples does not prove that arbitrary pruning code is sound. A useful engineering boundary is to expose proposal/ranking hooks around a trusted library of sound deductions. For new deductions, derive the invariant and test it exhaustively on small instances before performance evaluation. Our exact certificate checker and cut proofs are examples of that separation.

## General strategies, tractable structure, and limits

Binary linear optimization contains SAT: each clause can be encoded as a linear inequality over binary literals. Thus a polynomial-time exact solver for all such inputs would also solve NP-complete SAT in polynomial time. Learning does not remove this worst-case barrier; it may exploit the distributions, repeated structure and useful formulations that matter in practice. An incumbent can be easy to verify while proving that no better one exists remains expensive.

Tractable structure is still valuable. Continuous LP admits polynomial-time algorithms. Tree-structured finite-domain CSPs and bounded-width graph decompositions admit dynamic programming with cost exponential in the structural width rather than necessarily in all variables; a bound on width/domain size is part of that statement. Fixed finite constraint languages have an algebraic tractability classification, but it does not say that every modeling-language program or optimization objective is easy. See [Freuder's k-tree CSP result](https://www.aiinternational.org/Library/AAAI/1990/aaai90-001.php) and [Bulatov's finite-domain CSP dichotomy theorem](https://arxiv.org/abs/1703.03021).

Learning can help recognize a decomposition, select a useful representation, prioritize variables in a constrained region, or choose a neighborhood with manageable internal structure. It cannot safely declare a region irrelevant because it resembles easy training examples. Likewise, a policy that works for repeated rostering models may transfer poorly to arbitrary MPS files. The interface may be generic while the benefit is highly class-dependent.

The present LP/cut implementation is algebraically generic within its binary matrix scope: it does not need labels such as “knapsack” or “set cover” to remain correct. Performance is a separate empirical question. Cover/clique cuts need useful packing/conflict structure; LP bounds need to be informative enough to justify their cost; LNS needs a usable incumbent and neighborhoods that can be repaired. Native global constraints may already be the better representation for scheduling or all-different structure.

## What remains absent, and what the experiment can claim

Commercial MIP solvers integrate many more mechanisms: broad presolve and sparsification, many cut families and cut management, probing, sophisticated branching, numerous primal heuristics, numerical recovery, parallel search strategies and general mixed-variable frontends. Their public documentation describes that repertoire, but does not justify assuming they beat Gecode on every CP workload. This experiment did not run CPLEX or Gurobi. [CPLEX's cut catalog](https://www.ibm.com/docs/en/cofz/22.1.2?topic=cuts-what-are) illustrates the gap between a few implemented cut families and a full MIP system.

Our remaining software gaps include general integer/continuous variables, automatic frontend-to-LP extraction, sparse matrix infrastructure, verified LP infeasibility certificates, dynamic cut separation, budget-aware LP interruption, and explanation-producing learning. Gecode already had global propagation, AFC/CHB branching, branch-and-bound, restarts, path nogoods, LNS building blocks, and parallel/recomputation facilities. Adding those existing facilities to a comparison is a controller/configuration change, not evidence of inventing them.

A targeted primary-source search conducted for this note did **not identify a verified published benchmark specifically showing GPT-6 improving Gecode solve times**. That is a bounded search result, not proof that nobody has tried it. Published work on neural branching, learned LNS and LLM-generated heuristics provides relevant precedents without establishing that model-specific claim.

The strongest next research design is therefore to freeze a sound operator/API boundary and compare candidate-generation methods under the same development budget: expert rules, random/evolutionary mutations, an LLM, and a compact learned policy. Keep inference and evaluation cost, failed candidates, regressions and untouched public/size holdouts. The current experiment supplies a useful local testing platform and implemented optimization mechanisms; attributing their discovery or speed to a particular LLM requires that additional controlled comparison.


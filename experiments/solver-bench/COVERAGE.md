# Public benchmark coverage and the local evaluation loop

The local suite currently has **23 named encodings covering 21 problem concepts**: TSP and graph coloring each have both binary-linear and native CP encodings. These counts describe this suite, not coverage of all constraint programming. Public regression fixtures, satisfaction tests, and optimization benchmarks are reported separately.

## Existing evaluation suites

| Suite | What it contributes | Practical local route | Limits |
|---|---|---|---|
| [MiniZinc Challenge 2025](https://www.minizinc.org/challenge/2025/results/) and [2024](https://www.minizinc.org/challenge/2024/results/) | Each year's public catalog has 20 problem classes; the official pages identify their global constraints and distinguish satisfaction from optimization. | Select small whole instances by published size before tuning; compile once for development, preserving models and data. | Official contest timing includes compilation. A cached FlatZinc timing is a different metric and cannot establish contest rank. |
| [MiniZinc Challenge archive](https://github.com/MiniZinc/mzn-challenge) | Source models/data and compiler-version provenance: 2.9.3 for 2025; 2.8.5 for 2024. | Fetch only selected problem directories, then compile with compatible Gecode definitions. | Inspected [Mondoku](https://github.com/MiniZinc/mzn-challenge/tree/develop/2025/mondoku) and [TSPTW](https://github.com/MiniZinc/mzn-challenge/tree/develop/2025/tsptw) directories contain `.mzn`/`.dzn`, not ready `.fzn` payloads. Individual problem licenses must be checked; the archive explicitly warns that older licensing varies. |
| [MIPLIB 2017](https://miplib.zib.de/) | Standard mixed-integer evaluation; its benchmark set contains 240 selected instances, plus a broader collection and a solution checker. | The local MPS bridge first imports five small whole binary classics from **MIPLIB3.0**, preserving objective sense, bounds and numeric coefficients. These are not presented as the2017 benchmark set. | Current experimental binary LP integration does not support general integer columns, continuous decision variables, or arbitrary floating-point formulations. FlatZinc float regression support does not remove that limitation. |
| [OR-Library](https://people.brunel.ac.uk/~mastjjb/jeb/info.html) | Established optimization data across covering, assignment, packing, location, scheduling, routing and other classes. | The importer now includes complete `mknap1` and `gap1` collections; job-shop instances were already imported from Gecode's copy. | Formats and objective directions differ by collection. [The official license page](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/legal.html) provides an MIT notice; it is cached and preserved with the imports. |
| [CSPLib](https://www.csplib.org/Problems/) | Problem specifications and models: car sequencing, quasigroups, social golfers, curriculum balancing, steel slabs, RCPSP and many others. | Use the specifications to define meaningful family coverage; start with Gecode's bundled implementations/data. | A related model is not the same instance or encoding. A problem catalog does not itself define one universal timing or scoring protocol. |
| [XCSP competitions](https://www.xcsp.org/competitions/) | Public models, instances, results, and separate CSP/COP/Fast COP/Mini tracks. Since 2022 models have been compiled through PyCSP3 into XCSP3. | Add a small compatibility corpus if an XCSP3 frontend is integrated later. | The present harness has no XCSP3 parser; do not mark the XML instances runnable through the binary or FlatZinc input readers. |

## Mapping the existing local encodings

These are correspondences between problem classes, not claims that our generated instances reproduce competition instances.

| Local encoding names | Existing public class or catalog connection | Present evidence |
|---|---|---|
| `set_cover`, `multicover` | OR-Library set covering and multi-demand coverage | Generated optimization cases |
| `set_packing`, `auction` | Set packing; CSPLib 063 winner determination | Generated optimization cases |
| `knapsack`, `multidimensional_knapsack` | OR-Library multidimensional knapsack | Generated cases plus all seven original `mknap1` instances |
| `vertex_cover`, `independent_set`, `maxcut`, `coloring`, `native_coloring` | Graph optimization; OR-Library graph coloring and MaxCut links | Generated cases; two distinct coloring encodings |
| `facility_location`, `pmedian` | OR-Library warehouse location/p-median; CSPLib 034 warehouse location | Generated cases plus upstream FlatZinc warehouse regression models |
| `assignment`, `generalized_assignment` | OR-Library assignment and generalized assignment | Generated cases plus all five original `gap1` instances |
| `bin_packing` | OR-Library one-dimensional packing | Generated binary model; upstream cutting/packing fixtures are a separate track |
| `tsp`, `native_tsp` | Traveling salesman; adjacent to Challenge 2025 `atsp` | Generated cases with separate encodings; no time windows or vehicle capacities |
| `rostering` | Scheduling/rostering; adjacent to Challenge 2025 work-task variation | Generated shift and rest constraints, without a regular-language model |
| `production` | OR-Library lot sizing; CSPLib 058 discrete lot sizing | Generated discrete production/inventory model |
| `job_shop`, `native_rcpsp` | OR-Library job shop; CSPLib 061 RCPSP | Generated cases, six complete public job shops, two-resource cumulative scheduling |
| `weighted_queens` | CSPLib 054 n-queens, with our additional objective | Generated weighted variant; not an unmodified standard n-queens benchmark |

## Material gaps highlighted by the catalogs

| Missing or incomplete area | Representative published examples | Status and next useful addition |
|---|---|---|
| Geometric packing and placement | 2025 carpet cutting, products-and-shelves, stripboard; 2024 airport capacity | Five unchanged geometry/cutting FlatZinc regression fixtures imported. Full challenge-scale geometry remains untested. |
| Sequence constraints and finite automata | CSPLib car sequencing; 2025 work-task variation | Six sequence/planning fixtures imported, but this does **not** establish regular-constraint or car-sequencing coverage. Gecode `examples/car-sequencing.cpp` contains six instance arrays for a future native adapter. |
| Rich routing | 2025 TSP time windows; 2024 tiny CVRP | Missing time windows, vehicle capacity, and multiple vehicles. Ordinary TSP is only partial structural coverage. |
| Logic, tables, and combinatorial designs | 2025 black-hole/protein design; CSPLib quasigroups and solitaire battleships | Eight battleship and six Latin/magic/Sudoku fixtures imported. These are public regression instances, not replacements for the named Challenge models. |
| Scheduling beyond simple unary/cumulative resources | 2025 hospital scheduling; 2024 train scheduling and aircraft disassembly | Native RCPSP tests cumulative resources, while optional tasks, complex staffing and calendar rules remain gaps. |
| Clustering, network decisions, and connectivity | 2024 community detection/network models; 2025 hitori | No corresponding full application models in the current optimization corpus. |
| General mixed-integer and continuous optimization | MIPLIB mixed-integer applications | Unsupported by the experimental binary-linear adapter. The new limited MPS reader rejects unsupported columns/sections and scales supported finite decimal coefficients exactly. |
| Set-variable models | CSPLib block designs and set-based formulations | Gecode set-enabled FlatZinc compatibility includes upstream Steiner triples; performance breadth remains limited. |

## Imported data and validation

`public-binary-manifest.json` contains **12 whole OR-Library instances**: all seven `mknap1` cases (6–50 binary columns), and all five `gap1` cases (75 columns). Both original collections maximize profit; the imported model minimizes its negative. `mknap1` case 2 has decimal profits, so its objective is multiplied by 10 using exact rational arithmetic. The recorded scale converts results back to source units. Source files are hash-pinned. Published optima appear only in JSON reference metadata, while common greedy incumbents use actual coefficients only. Matrix/domain comparisons and complete enumeration of the two smallest knapsack cases validate sign, decimal scaling and the import.

The original formats and optimum conventions are documented by [OR-Library's knapsack page](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/mknapinfo.html) and [assignment page](https://people.brunel.ac.uk/~mastjjb/jeb/orlib/gapinfo.html). In particular, `gap1` is a **maximization** collection; the later `gapa`–`gapd` files use minimization.

`public-manifest.json` contains the six complete job-shop instances `ft06`, `la01`–`la05`. Their serial feasible initial schedules do not use published optima.

`miplib-manifest.json` adds five **MIPLIB3.0 classics**: `p0033`, `p0201`, `p0282`, `p0548`, and `lseu` (33–548 binary columns). Their official [1996 catalogue](https://miplib2010.zib.de/miplib3/miplib3_cat.txt) identifies the optimum values and pure-binary status; original compressed MPS files and catalogue headers are cached. No published solution is used as a warm start. None of the trivial all-zero/all-one assignments is feasible, so these cases start cold. The parser converts equality rows into two inequalities, tracks objective sense/constant, scales each decimal row and objective with exact rational arithmetic, and preserves column names. It rejects continuous/general-integer columns, nonbinary bounds, multiple RHS/bound vectors, ranged rows, SOS, indicators, quadratic sections and unsupported syntax. Tiny semantic/rejection tests cover those restrictions. It is a deliberately limited reader, not a general MPS implementation.

`fzn-manifest.json` contains **56 unchanged Gecode FlatZinc fixtures: 32 optimization regressions and 24 satisfaction compatibility tests**. Broad metadata groups include five geometry/cutting, six Latin/magic design, eight battleship and six sequence/planning cases. The source, model and expected-output hashes and original MIT notices are preserved. Fourteen sources needing custom construction or hooks are explicitly listed as skipped. These fixtures provide a fast bridge to existing CP models without downloading a compiler or corpus. They must not inflate the generated-family headline count.

Exact upstream output is a regression oracle under the original annotated search. It is **not an independent mathematical checker**: a different valid solution can have different text. Report exact matches, differences needing semantic review, timeouts, and errors separately. The importer preserves optimization versus satisfaction mode and all-solutions settings. Custom benchmark policies may need a semantic checker before alternate output can be accepted as validated.

## Keep the iteration loop local and fast

1. Run bounded correctness tests: exact certificate arithmetic, binary strengthening equivalence, importer checks, and a few FlatZinc fixtures exercising each required domain.
2. Develop policies only on the existing development split. Use a fixed short budget and stable per-family coverage; include setup and any heuristic/LP cost in measured time.
3. Freeze policies before evaluating complete public and held-out instances. Preserve known references; do not relabel timeouts as solved or replace unknown references with unverified solver claims.
4. Report optimization quality/proofs, timeouts, and regressions separately from SAT compatibility. A model that parses is not necessarily fully validated or fast.
5. Cache public source files and flattened models with hashes. Report parsing/solving time separately from MiniZinc compilation when compilation is cached. Add larger competition instances only in a slower periodic run, without making the daily loop depend on network downloads or a global installation.

Useful next whole-data additions are five bundled 50-item Scholl bin-packing arrays (`n1c1w1_a`–`e`), more OR-Library set-cover instances, and selected licensed MiniZinc TSPTW/geometry models. These candidates were identified from format/size and coverage gaps, not selected after observing a favorable speedup.

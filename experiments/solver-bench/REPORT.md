# Gecode improvement experiment

The frozen enhanced policy proved **227/230 held-out instances**, versus **172/230 for stock Gecode**, with no lost proofs. Binary-linear completion improved **125/180→180/180**; native CP stayed **47/50**. The corpus, code, measurements and local leaderboard are available in this directory.

**Performance results are provisional because of a timing interruption/discontinuity.** The main batch records827.87seconds on its monotonic timer but spans6,219.19seconds in UTC. The cause is unconfirmed. The host clock advanced beyond the requested two-hour window; feature development stopped when that was detected, followed by final checks and packaging. An uninterrupted rerun is needed before a publication-grade speed claim. Witness/reference validation passed independently of this timing concern.

## Main measured comparison

230 held-out instances, three repetitions each,2,000ms per solve, one search thread;2,760 validated runs. An instance below counts as proved only if all three repetitions completed within the logged cutoff.

| Configuration | Reliably proved | Capped shifted-geometric time score |
|---|---:|---:|
| Stock Gecode |172/230|47.27ms|
| Modified build, features disabled |172/230|47.19ms|
| Earlier LP-bound-only extension |223/230|12.94ms|
| New frozen automatic policy |227/230|5.49ms|

The capped score retains timeouts and uses a10ms shift; it is **not an estimate of eventual solve time**. On the same172 instances both stock and the new policy completed, the paired geometric speed ratio was1.37× (instance-bootstrap interval1.13–1.66×). Ninety became faster and82 slower. The bootstrap interval does not account for the clock anomaly. See [RESULTS.md](RESULTS.md) for per-family gains, exact counterexamples, reference coverage and score definitions.

[Open the primary interactive leaderboard](reports/final-test/leaderboard.html). Its CSV and JSON files retain all instances, configurations, regressions and provenance. The main track has common feasible starting solutions, so its55 new proofs demonstrate better improvement/proof within the cutoff, not first-feasible discovery.

## What was implemented

- Exact-arithmetic certification of continuous LP bounds and conditional variable fixing.
- Reuse of valid certificates between less frequent LP solves.
- Safe row normalization/deduplication and bounded clique/cover cuts.
- A bounded feasibility pump with exact candidate checks.
- Short neighborhood repairs followed by unrestricted Gecode proof search.
- A small structural configuration selector trained only on development data.
- Optional native CP neighborhood and incumbent-ordering controllers, tested but rejected as defaults after development regressions.

The new default policy selects stock search, LP fixing frequencies, neighborhood repair or a feasibility pump. Cut generation remains an explicit ablation because it did not earn selection on development data. Gecode already has global constraints, AFC search, restarts and LNS primitives; the work does not claim to invent those. No LLM runs inside measured solving, and HiGHS is used only for continuous relaxations in the enhanced Gecode solver. [SOFTWARE.md](SOFTWARE.md) documents the library API, safety arguments and limitations; [RESEARCH.md](RESEARCH.md) answers the original CP/MIP/LLM questions.

## Coverage and additional measured tracks

There are589 catalogued input artifacts:138 development,230 held-out,12 tiny correctness controls,90 larger-size binary cases,23 published optimization cases,40 paired encodings of20 semantic problems, and56 FlatZinc fixtures. The core contains23 representations of21 distinct problem concepts, with three development and five held-out seeds per family/size. This is broad local coverage, not every optimization class.

Existing suites informed the protocol: MiniZinc Challenge, MIPLIB, OR-Library, CSPLib and XCSP. Runnable local imports include whole OR-Library knapsack/assignment collections, published job shops, five classic MIPLIB3.0 instances, and unchanged Gecode FlatZinc regressions. MIPLIB2017 and full MiniZinc Challenge instances were not substituted into a frontend that cannot faithfully represent them. [COVERAGE.md](COVERAGE.md) documents sources and gaps; [the corpus inventory](reports/corpus/CORPUS.md) gives exact counts.

The following are **single-repetition secondary checks**, deliberately separate from the main repeated test:

| Track | Budget | Stock completion | Enhanced completion |
|---|---:|---:|---:|
|23 public optimization cases|1,000ms|13/23|15/23|
|90 larger binary cases|250ms|10/90|58/90|
|40 paired binary/native formulations|250ms|40/40|40/40|
|56 upstream FlatZinc fixtures|1,000ms|55/56 exact matches|55/56 exact matches|

The same FlatZinc fixture timed out in both builds; no exact-output mismatch or solver error was observed. That is a compatibility result, not evidence that the LP extension accelerates arbitrary FlatZinc models. Public LP-only completion was14/23. Larger-size timing and formulation comparisons need repetitions and longer budgets before strong claims.

Secondary dashboards: [public](reports/secondary-public/leaderboard.html), [larger sizes](reports/secondary-scale/leaderboard.html), [paired formulations](reports/secondary-formulation/leaderboard.html). Raw FlatZinc outputs and its summary are in `results/secondary-fzn-quick.*`.

## Use and continue locally

The actual checkout is `/Users/pavel/Documents/code/gecode`. From that checkout, run:

```sh
python3 experiments/solver-bench/suite.py quick
python3 experiments/solver-bench/suite.py test --output-dir experiments/solver-bench/results/rerun
```

The first command is a small local development loop; the second reruns the primary held-out preset. To reproduce all four primary configurations, add `--configs stock,disabled,lp,portfolio`. Use fresh output directories unless resuming an identical interrupted protocol. See [README.md](README.md) for builds, tests, policy training, analysis and all presets.

All six focused C++ test programs and the packaged Python/import/controller test runner passed. Original formulations, accepted primal candidates and returned witnesses are checked independently where described; unknown optima remain labeled unknown. Not every Gecode optimality claim has an independent exact optimum reference.

The BoolVar and native-HiGHS-MIP reference drivers are **unbuilt, untested drafts**, with no reported performance results. A full cold-start test and repeated/longer public/scale/formulation evaluations remain future work. Optional static figure export requires Matplotlib, which was not installed here; the standalone HTML includes interactive SVG charts. [UNFINISHED.md](UNFINISHED.md) and the delivery handoff preserve these next steps. No usage reset was needed; the last usage check showed37% consumed and one reset credit available.

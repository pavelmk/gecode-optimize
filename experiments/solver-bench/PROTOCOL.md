# Local Gecode benchmark protocol

Protocol drafted on 2026-09-05 before any held-out generated or public performance results were inspected. The experiment began at 01:22:43 UTC with a two-hour development budget. This is an exploratory engineering evaluation, not a claim to have reproduced a competition or commercial solver.

## Questions

1. Does the opt-in binary linear relaxation extension increase the number of instances proved optimal within a fixed time budget?
2. How much does it change elapsed time on instances completed by both implementations?
3. Do primal heuristics improve feasible objectives or time to a first solution, including without supplied incumbents?
4. Which problem classes regress, and which obtain proofs on previously unfinished instances?
5. Do stock native CP and FlatZinc models still work correctly after the software additions?

“Newly solved” means a proof completed within this experiment's cutoff. It does not mean a mathematically new tractable class. Finding a feasible solution, proving optimality, and establishing infeasibility are separate outcomes.

## Inputs and splits

The frozen generated collection uses 18 binary-linear families and five native CP representations. Each has two sizes, three development seeds and five held-out seeds: 138 development and 230 held-out instances. Twelve smaller binary controls support independent exhaustive checks. TSP and graph coloring have two representations, so there are 23 representations of 21 distinct concepts. New seeds test interpolation within generator families and sizes; they do not establish transfer to unseen applications or larger sizes.

Public cases are selected by source format, problem coverage and small size before solver timing. Whole instances are retained, objective sense/scales are explicit, and source files are cached with hashes and notices. Current imports include OR-Library and classic MIPLIB 3.0 cases. The local MIPLIB subset is not the MIPLIB 2017 benchmark set. Gecode FlatZinc test fixtures form a separate regression track; exact output agreement is a compatibility oracle, not an independent proof checker.

## Development and selection

Only development results may guide code, budgets, hyperparameters or algorithm selection. The binary controller receives twelve algebraic features of the original model. A small cost-sensitive tree is selected with three development seed folds and then fitted on the full development split. Its actions are explicit solver configurations. No family label, seed or reference optimum is supplied to runtime selection. Features can still identify generator templates; this is not a family-independent generalization claim.

Development comparisons use a 1,000ms cutoff. Final policies, source hashes and binary hashes are frozen before held-out evaluation. The chosen tree's cross-validation score is tuning evidence, not an unbiased estimate of final performance. Any later change motivated by held-out results must be labeled exploratory and evaluated on a new holdout before a confirmatory claim.

## Main comparisons

The generated held-out track uses three repeated serial runs per instance/configuration and a 2,000ms solve budget. Configurations include unmodified Gecode libraries, the preceding LP-bound-only extension, and the newly selected controller. Public comparisons use the same primary budget where feasible; separately labeled longer runs may be added without replacing short-cutoff failures. An all-cold sensitivity track compares stock and the final controller without supplied incumbents. Native controller ablations and the extension-disabled build provide controls.

Stock and enhanced executables compile the same model builder with matched optimization flags. The stock executable links the pinned upstream library build. This is a controlled implementation comparison, not a claim that the selected common encoding/search is the best hand-tuned Gecode model for each family. Both use the same initial feasible witness when one is supplied; none uses a published optimum as a starting solution. The primary warm-start track therefore mainly measures improvement and proof, not first-feasible discovery.

## Timing and execution

One solver process and one search thread run at a time. Do not compile, run stress tests or launch competing solver work during timed batches. Instance and configuration order is deterministically shuffled within each repetition. Both configurations solve exactly the same parsed data.

Solver time includes feature computation, optional strengthening, LP workspace creation, primal candidates, neighborhood repair, root construction, search, and solver teardown. Parsing, correctness validation, offline shared incumbent generation, process startup and result serialization are excluded; process wall time is also recorded. The reported solver metric is not end-to-end MiniZinc compilation time.

Engine and LP calls have soft cancellation boundaries. A proof returned after the cutoff is recorded but does not count as completed within budget. Objective-at-cutoff is reconstructed from timestamped improvements and the common initial solution. Overshoot is reported. Hardware, software, commit, compiler flags, binary hashes, corpus hashes and complete raw results accompany each batch. Interrupted batches are resumable only with identical protocol/input/binary/platform identities and cannot be silently published as complete.

## Validation and statistics

Every returned witness is checked against the original instance. Binary models have independently implemented original-domain checks on small templates; native models have separate feasibility checks. Known exact optima come from independent algorithms, exhaustive enumeration, or published source references. A solver proof on an instance with no external reference remains labeled solver-proven. Conflicting proofs, invalid witnesses and malformed outputs fail the batch rather than becoming speedups.

Take the median of repeated elapsed times for each instance/configuration before paired aggregate comparisons. Report solved counts, feasible-at-cutoff counts, final objective quality, new proofs, lost proofs, common-completion timing ratios, individual regressions, and per-family results. Use a 10ms shifted geometric mean for stable aggregation and PAR-2 as a separate timeout-penalized score. Neither timeout substitution nor a censored ratio is an observed solve-time speedup. Bootstrap intervals resample instances, not duplicate timing repetitions. A missing run or timeout remains visible.

All raw JSONL, immutable metadata, source snapshots, generators, imports, validators and report scripts are retained locally. The standalone leaderboard is a view of these records, not a manually edited score table. Cross-machine submissions must form separate cohorts. A release-quality external leaderboard should also require a pinned machine image, independently rerun submissions, longer budgets, larger real-world data, memory limits, and a broader general-MIP/frontend implementation.

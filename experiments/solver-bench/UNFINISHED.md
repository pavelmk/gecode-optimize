# Prepared work and next steps

The principal frozen comparison is complete:230 held-out instances ×4 configurations ×3 repetitions at2,000ms,2,760 validated runs. Additional public, scale, formulation and FlatZinc checks are explicitly short single-repetition secondary tracks. They do not replace the main protocol or support equally strong timing claims.

The host UTC clock advanced much more than the monotonic benchmark clock: the main batch began at01:59:20 UTC, finished at03:42:59 UTC, and recorded827.87seconds of active monotonic elapsed time. The requested two-hour session window ended at03:22:43 UTC. The next clock check was04:19:35 UTC. Suspension or a clock discontinuity is possible, but the cause is not established. Do not describe this as an uninterrupted two-hour experiment, and do not use UTC span as solver time. New feature work stopped when this was detected; final checks and packaging followed.

## Unbuilt reference drafts

`stock-bool-driver.cpp` and `bool_bench.py` prepare a stronger stock Boolean-variable modeling baseline. `highs-mip-driver.cpp` and `reference_bench.py` prepare a separate native HiGHS MIP baseline. These files have not been compiled or tested in this session and have no reported performance results. They are not part of the enhanced Gecode binary and must pass compilation, exact witness checks, known-optimum cases and budget checks before use. HiGHS numerical MIP optimality must not be relabeled an exact Gecode/dual-certificate proof.

## Highest-value continuation

1. Re-run the primary comparison on an uninterrupted, otherwise idle host with the same binaries and corpus. Keep the existing records; create a new cohort if inputs, binaries or platform differ.
2. Run the full cold-start test to measure first-feasible discovery, not only warm-start improvement/proof. The existing primary track supplies common feasible solutions.
3. Run three or more timing repetitions and longer budgets for the public, larger-size and paired-formulation tracks. Preserve the short-cutoff failures.
4. Compile/validate the stock BoolVar and HiGHS MIP reference drafts, then compare them on the same binary cases. Neither currently supports a performance claim.
5. Add a semantic paired-formulation report from `paired_problem_id`; assert cross-encoding optima agree. Do not treat the virtual best formulation as a free deployable selector.
6. Extend the adapter beyond binary linear models only with explicit domain/aliasing checks, exact arithmetic safeguards and independent correctness tests. FlatZinc currently does not automatically use the LP extension.
7. Broaden real-world coverage: richer routing, automata, optional-task scheduling, geometric packing, larger licensed MiniZinc/CSPLib instances, and general mixed-integer/continuous models. Read COVERAGE.md before claiming comprehensive field-wide coverage.
8. Explore conflict explanations/learning, reliable pseudocost branching, dynamic cut management, primal solution pools and parallel portfolios. These are substantial projects, not features claimed to have been reimplemented here.

Any policy tuned from present test/scale/public outcomes requires fresh held-out data for a new confirmatory comparison. Keep original corpus/results immutable.

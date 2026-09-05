# Held-out results

The frozen portfolio proved **227 of 230 instances in every repetition**, compared with **172 for stock Gecode**: 55 additional reliably proved instances, with no previously reliable proof lost. All gains in completion came from binary-linear models: **125→180 of 180**. Native CP remained **47/50** for every configuration.

This complete held-out batch contains **2,760 runs**: 230 fixed instances, four configurations and three repetitions, using a recorded 2,000 ms solver budget and one search thread. The 23 representation labels correspond to 21 normalized domain/model concepts, with alternate TSP/coloring encodings counted separately. All configurations received the same supplied incumbent per instance. Policies were selected using development data; all held-out cases, timeouts and regressions are retained.

## Completion and timeout-inclusive scores

| Configuration | Instances proved in all 3 runs | Timely proof runs / 690 | Proof runs matching independent optimum references | Capped SGM score, ms | PAR2 penalty score, ms |
|---|---:|---:|---:|---:|---:|
| Stock | 172/230 | 516 | 219 | 47.269 | 1,033.786 |
| Features disabled | 172/230 | 516 | 219 | 47.192 | 1,033.749 |
| LP bound always enabled | 223/230 | 671 | 258 | 12.937 | 144.226 |
| Frozen portfolio | 227/230 | 681 | 258 | 5.488 | 62.622 |

An instance counts as reliably proved only when **every repetition** finishes within the recorded budget. The LP configuration additionally completed one instance in two of its three repetitions, explaining why its proof-run total is not three times its reliable-instance count.

These scores retain every timeout. Capped SGM uses a 10 ms shift and assigns the cutoff to an incomplete run, then takes a median per instance and a shifted geometric mean across instances. PAR2 assigns twice the cutoff to an incomplete run, then takes an instance median and an arithmetic mean. **Neither score estimates unobserved completion times.** The near-identical disabled control provides a useful comparison for build/controller overhead.

## Where completion improved

- Knapsack and multidimensional knapsack each improved from **0/10 to 10/10**. These are newly proved sampled families within this budget, not newly tractable mathematical classes.
- Auction, bin packing, generalized assignment, independent set, rostering, set packing and vertex cover each improved from **5/10 to 10/10**.
- Three larger native RCPSP instances remained unproved by every configuration. Native LNS/branching variants were rejected using development evidence, and the final native policy retained ordinary AFC search.

All runs had a feasible incumbent at the deadline; this primarily measures improvement and proof, not finding an initial feasible solution. Of the portfolio's 681 timely proof runs, **258 agree with independent optimum references**; the remaining 423 have checked feasible witnesses and Gecode proof claims without an independent optimum reference. All 2,760 rows underwent feasibility, objective, hash, deadline and reference-consistency audits; this does not independently certify every proof.

## Speed and regressions

On the **same 172 instances completed in every repetition by both stock and portfolio**, the portfolio was faster on 90 and slower on 82. The geometric mean of paired stock/portfolio median-time ratios was **1.37×**, with a family-stratified instance bootstrap 95% interval of 1.13–1.66×. This is conditional on common completed cases; it excludes censored completion times and does not measure generalization to unseen families or account for the timing anomaly below.

The arithmetic means of those same instance medians were **33.55→5.06 ms**. Large gains on some cases coexist with substantial regressions: `test_bin_packing_small_2202004` worsened **1.287→33.441 ms**, and `test_tsp_large_2412002` worsened **29.954→66.577 ms**. Always enabling LP also slowed 105 of 172 common completed cases, supporting selective activation rather than a universal LP speedup claim.

For previously unproved cases, only censored lower bounds are justified. For example, stock proved none of the repetitions of `test_multidimensional_knapsack_large_1412001` within 2,000 ms; portfolio's completed median was 454.129 ms. The ratio **exceeds 4.40×** under the recorded cutoff—it is not a measurement of stock's eventual completion time.

## Timing provenance and limits

**The batch has a material clock/provenance anomaly.** Metadata spans 01:59:20–03:42:59 UTC on 2026-09-05, or 6,219.19 seconds, while the harness records 827.87 seconds from its monotonic session timer. The cause is unconfirmed; suspension or a clock discontinuity is possible. Per-run times and budget classifications above are reported as logged. They should be treated as provisional performance measurements pending an uninterrupted rerun; the bootstrap interval does not resolve this issue. Feasible-witness and reference checks remain separate evidence.

These are modest, generated instances on one machine, using a common matrix formulation and fixed search settings. Held-out seeds test new instances from known templates and sizes. They do not establish superiority over specialized algorithms, different CP formulations, CPLEX/Gurobi, industrial workloads, or all constraint programming. The public, scale, paired-formulation and FlatZinc tracks are separate evidence and are not pooled into this primary table; any single-repetition secondary run must retain that label.

The audited source is `reports/final-test/leaderboard.json`; complete tables and interactive charts are in `reports/final-test/leaderboard.html`, `instance-results.csv` and `comparisons.csv`. Raw log SHA-256: `48fdba27fec07695a9e7f0448bd41e7e4a25e451a0a092bae2452d1f875762a5`.

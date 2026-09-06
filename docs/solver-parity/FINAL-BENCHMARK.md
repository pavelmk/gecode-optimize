# Final native algorithm comparison

All three cohorts use the same deterministic original models, one thread, and ten seconds per owning solve. The automatic clock includes every sequential racing probe and selected restart. Measured processes ran serially.

Original Gecode is the preserved optimization-facade baseline before the algorithm changes, not a pristine upstream release. Auto + race combines exact structural preprocessing, compact DP, checked LP/branching selection, and opt-in sequential exploration. Configured uses the frozen family presets; no strategy was changed in response to this final study.

| Problem | Original solved / failed upper | Auto + race solved / failed upper | Configured solved / failed upper |
|---|---:|---:|---:|
| Knapsack | 33 items / 34 | 2304 items / 2336 | 2304 items / 2336 |
| Assignment | 17 tasks / 18 | 64 tasks / 66 | 31 tasks / 32 |
| Facility location | 8 sites / 9 | 44 sites / 45 | 54 sites / 56 |
| Bin packing | 17 items / 18 | 47 items / 48 | 30 items / 31 |
| Production planning | 11 periods / 12 | 27 periods / 29 | 28 periods / 29 |
| Routing | 21 cities / 22 | 21 cities / 22 | 21 cities / 22 |
| Weighted queens | 23 queens / 24 | 23 queens / 24 | 23 queens / 24 |

356 measured attempts plus three runtime-loader probes; cumulative active study wall time 2044.41 seconds (preparation between phases excluded).

The user removed the initial study ceilings after discovery had started. The original phase is preserved by hash, and every prior observation was retained. Each cohort was extended until a failed upper input was observed in both repetitions. Bisection narrows large brackets to approximately 2% of the solved lower size (one-unit brackets for small sizes). Any unresolved wider bracket caused by mixed confirmations is explicitly flagged in the export. No harness cap is reported as solver failure.

Bars show the largest sampled size passing both repetitions and every variant. The table also reports the observed failed upper. Seeded-instance difficulty need not be monotonic: reversals and mixed confirmations remain in the raw report, so these are sampled brackets, not mathematical maximum-size guarantees.

Every returned original witness was independently checked. Exact optimal status is backend-reported; no independent optimum oracle is claimed. The same seeded families informed the earlier frozen configured policy, so this is not a holdout study.

Automatic diagnostics across measured attempts: 18 races skipped for direct-path compatibility; 66 one-probe results; 68 two-probe results; 114 selected automatic; 20 selected ordinary. Counts are parsed from the saved solver diagnostics, and runtime probes are excluded.

This comparison measures combined policies, not an ablation. A first automatic probe that proves optimality does not establish a benefit from racing; the gains may come from DP, preprocessing, LP bounds or branching. A separate ablation would be required to isolate individual contributions.

Racing may increase total CPU burden or solve time because exploration and restarting repeat work. Several seconds or longer can still be worthwhile when exploration identifies a much more effective strategy for the remaining solve. Early progress is a heuristic, not a promise of future speedup.

The public JSON retains every initial and extension probe/attempt, wall time, objective, bound, original witness, frozen model hash, policy, source hash, phase amendment, and verified loader identity.

Original source: 530a3b7837205d8255c6640425018831d3f8ee0e
Current source / extension runner: 95b54f2f5553fb078502bff483fb9067c4b37887
Report SHA256: f0635189a62c78e69d36f11d562751153924ee8afec22d0dc530b8d9da25bb9b

The interrupted automatic result at 4096 knapsack items omitted its optional backend-version string. The raw packet was preserved and revalidated with all original model, witness, bound, gap and clock checks; driver and loaded-library hashes establish runtime identity. No solve was repeated for this metadata correction.

Assignment at 128 tasks initially exceeded the driver's 10,000-variable TXT transport guard before entering solve. That rejected invocation is archived separately under `harness-attempts` and in the report protocol, and is not a solver failure. A driver rebuild changed parser guards only; all solver library hashes stayed identical. Earlier timings remain comparable because their clocks surround the owning solve call and exclude parsing/model construction. The larger driver then performed the actual solve at 128.

The configured knapsack preset remains compact native DP with ordinary BAB fallback after DP admission or its local time cap fails. It was not changed to LP based on extension results. Production auto has a 27/29 observed bracket: size 28 had mixed confirmations, so its two-unit interval remains explicitly unresolved against the one-unit target.

Reproduction (from the solver checkout; the preserved original runtime and build manifests are required):

```sh
python3 experiments/optimize/build_final_benchmark.py
python3 experiments/optimize/benchmark_final.py --output-dir build/final-benchmark/results --binary build/final-benchmark/optimize-final-benchmark --runtime-build build/native-structure/native-build
python3 experiments/optimize/continue_final_benchmark.py --report build/final-benchmark/results/report.json --output-dir build/final-benchmark/extended-results --binary build/final-benchmark/optimize-final-benchmark --runtime-build build/native-structure/native-build
python3 experiments/optimize/resume_final_benchmark.py --report build/final-benchmark/extended-results/report.json --output-dir build/final-benchmark/resumed-results --binary build/final-benchmark/optimize-final-benchmark --runtime-build build/native-structure/native-build
python3 experiments/optimize/build_large_final_benchmark.py
python3 experiments/optimize/resume_large_final_benchmark.py --report build/final-benchmark/resumed-results/report.json --output-dir build/final-benchmark/final-results --binary build/final-benchmark/large-driver/optimize-final-benchmark --runtime-build build/native-structure/native-build
python3 experiments/optimize/resume_large_final_benchmark.py --report build/final-benchmark/final-results/report.json --export-only
```

These phase commands record the actual amended study and guarded resumptions; their preconditions deliberately reject unexpected failures. Exporting the saved final report invokes no solver. Output directories must be new for a fresh measurement.

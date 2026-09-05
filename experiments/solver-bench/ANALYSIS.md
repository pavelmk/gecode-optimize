# Audited benchmark reports

`analyze.py` reads completed `bench.py` JSONL logs and their sibling `.meta.json` files. It never launches a solver. The report has no external JavaScript, fonts, chart libraries, or network dependencies.

From this directory:

```sh
python3 analyze.py --runs results/held-out.jsonl results/public.jsonl --out-dir reports/final
```

Publication defaults to `test,public`. Development requires an explicit flag:

```sh
python3 analyze.py --runs results/v0-development.jsonl --exploratory --out-dir reports/v0-development
```

An incomplete batch is rejected by default. `--allow-incomplete` is allowed only with `--exploratory` and the development split; missing data suppresses affected aggregate scores and rankings. Historical manifests must retain exactly the recorded contents. Supply relocated snapshots with repeated `--manifest PATH` arguments.

Outputs:

- `leaderboard.html`: sortable configuration and instance tables; cohort, family and configuration filters; native SVG completion curves and family bars; paired comparisons and audit methods.
- `leaderboard.json`: all aggregates, per-instance/configuration summaries, binary/source hashes and metric definitions.
- `instance-results.csv`: every instance/configuration, including timeouts, deadline solution counts, reference status, counters, and censored ratios.
- `comparisons.csv`: overall and per-family aggregates for every configuration in each protocol cohort.

Different budgets, warm starts, platforms, configuration sets, or binary versions form separate cohorts. Both binary-linear and native CP families are accepted; native RCPSP has an independently parsed text encoding.

## Interpretation

The observation unit is an independent instance. All timing summaries first take a median over that instance's repetitions. The report displays the actual repetition counts; it does not assume that a development pilot has three runs.

The primary rank is the number of instances proved within budget **in every repetition**, then the shifted geometric mean of capped per-instance median milliseconds, with a 10 ms shift. An incomplete run contributes the cutoff to this capped score. PAR2 is separate: an incomplete run contributes twice the cutoff, followed by an instance median and an arithmetic mean across instances. Neither score estimates unobserved completion times.

Proofs finishing after the deadline never count as completed within budget. Common-case speed ratios and arithmetic means use only the identical subset solved in every repetition by both configurations. The optional bootstrap resamples paired instance log ratios within family strata; it is conditional on this common solved subset. Disable it with `--bootstrap-samples 0` when only a quick audit is needed.

"Newly proved" requires zero timely baseline proofs and timely comparison proofs in every repetition. "Newly reliable" also includes partial baseline completion. A family with zero baseline proofs and at least one comparison proof is described as newly solvable **on this sample within this budget**; no mathematical change of problem class is implied.

Known exact references distinguish independent optimum verification from Gecode-only proof claims. When no independent reference exists, objective quality is a distance from the best incumbent observed within budget across configurations, **not a true optimality gap**. Initial and final assignment witnesses are checked. If a deadline objective appears only in an intermediate trace whose assignment is absent from the log, its feasibility is trace-supported rather than independently rechecked; corresponding witness-check counts are retained in the JSON/CSV.

## Independent references

Pass `--references references.json` to incorporate cross-solver references. Accepted envelopes are a list, a `results` list, a `references` list or ID-keyed mapping, or a single record. An independently verified optimal reference requires:

```json
{
  "id": "the-instance-id",
  "status": "optimal",
  "objective": 17,
  "input_sha256": "canonical mathematical instance hash",
  "independent": true,
  "solver": "named independent exact solver or oracle",
  "assignment": [1, 0, 1]
}
```

`assignment` is optional; when present it is checked against the original model. `independent: true` must be explicitly asserted and the named solver cannot be Gecode. The assertion and optimum certificate remain the responsibility of that independent oracle. Every external optimum, including one without independent provenance, must agree with available solver proof claims. Stale input hashes fail closed. External reference files themselves are SHA-256 recorded.

## Integrity checks

Before publishing, the analyzer checks complete expected instance/configuration/repetition coverage, source and input hashes, JSON/TXT mathematical and incumbent agreement, original-domain feasibility, recorded validation, binary hashes, embedded and external reference hashes, objective trajectories, and the exact deadline proof flag. Conflicting duplicate runs or optimality claims fail closed.

The fast integrity tests cover post-deadline proofs and incumbents, changed hashes/references, invalid assignments, incomplete batches, timeout scoring, common-subset conditioning, partially completed baselines and external-reference provenance:

```sh
python3 -m unittest test_analyze.py
```

The tests do not run a solver or generate benchmark timing observations. Browser rendering should be checked separately when a permitted browser preview is available; Python and JavaScript syntax validation alone is not visual QA.

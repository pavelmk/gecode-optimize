#!/usr/bin/env python3
"""Revalidate completed LP/CP benchmark logs and produce CSV plus RESULTS.md.

This script reads results only; it never launches solver runs or oracle timings.
It refuses partial datasets and keeps censored observations and PAR-2 scores
separate from completed solve times.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from generator import to_text
from validate import input_hash, validate_result


HERE = Path(__file__).resolve().parent
CONFIG_ORDER = ("stock-afc", "disabled-afc", "root-afc", "node-afc", "stock-size", "root-size", "node-size")
NUMERIC_FIELDS = ("elapsed_ms", "process_wall_ms", "build_ms", "lp_ms", "nodes", "lp_calls",
                  "certified_bounds", "rejected_bounds", "lp_infeasible_statuses", "failures",
                  "propagations", "peak_rss_kb")


def complete(row):
    return row["status"] in ("optimal", "infeasible")


def load_dataset(name, directory, manifest_path, manifest, records):
    path = directory / (name + ".jsonl")
    metadata = json.loads(path.with_suffix(".meta.json").read_text())
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if metadata["manifest_sha256"] != manifest_digest:
        raise ValueError(f"{name}: current manifest differs from recorded manifest hash")
    configurations, repetitions = metadata["configs"], metadata["repeats"]
    if len(configurations) != len(set(configurations)) or repetitions < 1:
        raise ValueError(f"{name}: invalid configurations or repetition count")
    splits = metadata["split"].split(",")
    expected_ids = {r["id"] for r in manifest["instances"] if r["split"] in splits}
    expected = {(identity, config, rep) for identity in expected_ids
                for config in configurations for rep in range(repetitions)}
    lines = path.read_text().splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    if len(rows) != len(expected):
        raise ValueError(f"{name}: incomplete/unexpected dataset: {len(rows)} rows, expected {len(expected)}; wait for all runs")
    instances = {}
    seen = set()
    validation_counts = Counter()
    for row in rows:
        key = row["id"], row["config"], row["repetition"]
        if key not in expected or key in seen:
            raise ValueError(f"{name}: unexpected or duplicate row {key}")
        seen.add(key)
        record = records[row["id"]]
        if row["id"] not in instances:
            instance = json.loads((manifest_path.parent / record["json"]).read_text())
            if input_hash(instance) != record["input_sha256"]:
                raise ValueError(f"{name}: stale mathematical input hash for {row['id']}")
            if (manifest_path.parent / record["txt"]).read_text() != to_text(instance):
                raise ValueError(f"{name}: JSON/TXT input disagreement for {row['id']}")
            instances[row["id"]] = instance
        instance = instances[row["id"]]
        if row["family"] != instance["family"] or row["split"] != instance["split"]:
            raise ValueError(f"{name}: wrong family/split for {row['id']}")
        checked = validate_result(instance, row)
        if not checked["valid"]:
            raise ValueError(f"{name}: invalid result {key}: {checked}")
        if checked != row.get("validation"):
            raise ValueError(f"{name}: stored validation differs from fresh validation for {key}")
        if row.get("reference_objective") != instance.get("reference", {}).get("objective"):
            raise ValueError(f"{name}: wrong recorded reference objective for {key}")
        expected_initial = instance.get("incumbent_objective") if metadata["warm_start"] else None
        if row.get("initial_objective") != expected_initial:
            raise ValueError(f"{name}: wrong recorded incumbent objective for {key}")
        if complete(row) and row.get("stopped"):
            raise ValueError(f"{name}: result both complete and stopped for {key}")
        for field in NUMERIC_FIELDS:
            value = row[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name}: invalid {field} for {key}")
        if row["elapsed_ms"] + 1e-6 < row["build_ms"]:
            raise ValueError(f"{name}: build time exceeds elapsed time for {key}")
        validation_counts["rows"] += 1
        validation_counts["claims_verified"] += bool(checked.get("claims_verified"))
        validation_counts["completed"] += complete(row)
        validation_counts["completed_claims_verified"] += complete(row) and bool(checked.get("claims_verified"))
    if seen != expected:
        raise ValueError(f"{name}: missing result groups")
    return {"name": name, "rows": rows, "metadata": metadata,
            "instances": instances, "validation_counts": dict(validation_counts)}


def summarize(dataset):
    groups = defaultdict(list)
    for row in dataset["rows"]:
        groups[row["id"], row["config"]].append(row)
    result = {}
    limit = dataset["metadata"]["limit_ms"]
    for key, rows in groups.items():
        completed = [row for row in rows if complete(row)]
        entry = {"dataset": dataset["name"], "id": key[0], "config": key[1],
                 "family": rows[0]["family"], "runs": len(rows), "completed_runs": len(completed),
                 "all_runs_completed": len(completed) == len(rows), "limit_ms": limit,
                 "warm_start": dataset["metadata"]["warm_start"],
                 "reference_objective": rows[0]["reference_objective"],
                 "initial_objective": rows[0]["initial_objective"],
                 "reported_objectives": json.dumps(sorted({row.get("objective") for row in rows},
                                                           key=lambda x: (x is None, x))),
                 "claims_verified_runs": sum(row["validation"].get("claims_verified", False) for row in rows),
                 "median_completed_elapsed_ms": statistics.median(row["elapsed_ms"] for row in completed) if completed else None,
                 "median_par2_score_ms": statistics.median(row["elapsed_ms"] if complete(row) else 2 * limit for row in rows)}
        for field in NUMERIC_FIELDS:
            entry["median_" + field] = statistics.median(row[field] for row in rows)
        entry["median_observed_elapsed_ms"] = entry.pop("median_elapsed_ms")
        result[key] = entry
    return result


def classify_pair(baseline, candidate):
    """Return relation and a correctly censored ratio of median solve times."""
    b_full, c_full = baseline["all_runs_completed"], candidate["all_runs_completed"]
    b_none, c_none = baseline["completed_runs"] == 0, candidate["completed_runs"] == 0
    b_time, c_time = baseline["median_observed_elapsed_ms"], candidate["median_observed_elapsed_ms"]
    if b_full and c_full:
        if c_time == 0:
            return "inconclusive", "— (zero clock reading)"
        ratio = b_time / c_time
        relation = "tie" if math.isclose(ratio, 1.0, rel_tol=1e-9) else ("win" if ratio > 1 else "regression")
        return relation, f"{ratio:.3f}×"
    if b_none and c_full and c_time > 0:
        ratio = baseline["limit_ms"] / c_time
        display_bound = math.floor(ratio * 1000) / 1000
        return ("win" if ratio >= 1 else "inconclusive"), f">{display_bound:.3f}× (lower bound)"
    if b_full and c_none:
        ratio = b_time / candidate["limit_ms"]
        display_bound = math.ceil(ratio * 1000) / 1000
        return ("regression" if ratio <= 1 else "inconclusive"), f"<{display_bound:.3f}× (upper bound)"
    return "inconclusive", "— (censored/mixed)"


def time_cell(entry):
    completed, total = entry["completed_runs"], entry["runs"]
    if entry["all_runs_completed"]:
        return f"{entry['median_observed_elapsed_ms']:.3f} ({completed}/{total})"
    if completed == 0:
        return f">{entry['limit_ms']:g} limit ({completed}/{total})"
    return f"mixed completion ({completed}/{total})"


def disabled_control(dataset):
    pairs = defaultdict(dict)
    for row in dataset["rows"]:
        if row["config"] in ("stock-afc", "disabled-afc"):
            pairs[row["id"], row["repetition"]][row["config"]] = row
    checked, matching, zero_lp = 0, 0, 0
    mismatches = []
    for key, pair in pairs.items():
        if len(pair) != 2:
            continue
        stock, disabled = pair["stock-afc"], pair["disabled-afc"]
        checked += 1
        # Time-limited runs need not stop at the same node, even with identical code.
        if complete(stock) and complete(disabled):
            fields = ("status", "objective", "nodes", "propagations", "failures")
            differences = [field for field in fields if stock[field] != disabled[field]]
            matching += not differences
            if differences:
                mismatches.append({"id": key[0], "repetition": key[1], "fields": differences})
        zero_lp += disabled["lp_calls"] == 0
    fully_completed_pairs = sum(complete(pair["stock-afc"]) and complete(pair["disabled-afc"])
                                for pair in pairs.values() if len(pair) == 2)
    return {"paired_runs": checked, "fully_completed_pairs": fully_completed_pairs,
            "matching_completed_pairs": matching, "disabled_zero_lp_call_runs": zero_lp,
            "mismatches": mismatches}


def write_csv(path, summaries):
    fields = ["dataset", "id", "family", "config", "runs", "completed_runs", "all_runs_completed",
              "reference_objective", "initial_objective", "reported_objectives", "warm_start", "limit_ms",
              "median_observed_elapsed_ms", "median_completed_elapsed_ms", "median_process_wall_ms",
              "median_build_ms", "median_nodes", "median_failures", "median_propagations", "median_lp_calls",
              "median_lp_ms", "median_certified_bounds", "median_rejected_bounds", "median_lp_infeasible_statuses",
              "median_peak_rss_kb", "median_par2_score_ms", "claims_verified_runs"]
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        entries = [entry for summary in summaries for entry in summary.values()]
        for entry in sorted(entries, key=lambda e: (e["dataset"], e["family"], e["id"], CONFIG_ORDER.index(e["config"]))):
            writer.writerow({field: entry.get(field) for field in fields})


def report(held, held_summary, development, dev_summary):
    meta = held["metadata"]
    repeats, limit = meta["repeats"], meta["limit_ms"]
    ids = sorted(held["instances"], key=lambda identity: (held["instances"][identity]["family"], identity))
    required = {"stock-afc", "root-afc", "node-afc"}
    if not required.issubset(meta["configs"]):
        raise ValueError("held-out table requires stock-afc, root-afc, and node-afc")
    stock_full = sum(held_summary[(identity, "stock-afc")]["all_runs_completed"] for identity in ids)
    node_full = sum(held_summary[(identity, "node-afc")]["all_runs_completed"] for identity in ids)
    lines = ["# LP relaxation inside Gecode: measured results", "",
             f"On this generated held-out sample, `node-afc` completed every repetition on {node_full}/{len(ids)} instances; "
             f"`stock-afc` did so on {stock_full}/{len(ids)}. The tables retain every instance and configuration.", "",
             "## Measurement and interpretation", "",
             f"Each held-out timing below is the median of **{repeats} runs**, with a per-run limit of **{limit:g} ms**. "
             f"The CSV also retains development summaries using their actual {development['metadata']['repeats']} repetitions. "
             "Development results are excluded from the held-out tables.", "",
             meta["timing"], "",
             f"Common greedy warm starts: {'enabled' if meta['warm_start'] else 'disabled'}. "
             "The same witness is supplied to all configurations. The LP backend solves continuous relaxations; it is not used as a MIP solver.", "",
             "A complete run establishes optimality or infeasibility. A timed-out feasible incumbent remains useful but is not a completed solve. "
             "`>limit` records right-censoring, not a measured completed solve time. Speed ratios compare stock AFC with the named configuration; "
             "values above 1 favor the new configuration. A ratio beginning `>` or `<` is only a bound. Mixed-completion pairs have no asserted ratio.", "",
             "## Every held-out instance", "",
             "Times are milliseconds; parentheses give completed runs / total runs. Optima come from independent exact algorithms.", "",
             "| Instance | Exact optimum | Stock AFC ms | Root LP AFC ms | Stock / root | Node LP AFC ms | Stock / node |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for identity in ids:
        stock, root, node = (held_summary[(identity, config)] for config in ("stock-afc", "root-afc", "node-afc"))
        root_ratio, node_ratio = classify_pair(stock, root)[1], classify_pair(stock, node)[1]
        lines.append(f"| {identity} | {stock['reference_objective']} | {time_cell(stock)} | {time_cell(root)} | "
                     f"{root_ratio} | {time_cell(node)} | {node_ratio} |")
    lines.extend(["", "## Completion and paired outcomes by family", "",
                  "Wins/regressions use paired per-instance medians when both configurations finish; a censored pair is classified only when its bound "
                  "establishes the ordering. Other pairs are inconclusive. These counts are descriptive and do not establish statistical significance.", "",
                  "| Family | Configuration | Completed runs | Instances completing all runs | Wins vs stock AFC | Regressions | Ties | Inconclusive |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"])
    families = sorted({instance["family"] for instance in held["instances"].values()})
    for family in families:
        family_ids = [identity for identity in ids if held["instances"][identity]["family"] == family]
        for config in ("stock-afc", "root-afc", "node-afc"):
            entries = [held_summary[(identity, config)] for identity in family_ids]
            outcomes = Counter(classify_pair(held_summary[(identity, "stock-afc")], held_summary[(identity, config)])[0]
                               for identity in family_ids) if config != "stock-afc" else Counter()
            completed = sum(e["completed_runs"] for e in entries)
            total = sum(e["runs"] for e in entries)
            full = sum(e["all_runs_completed"] for e in entries)
            outcome_cells = " | ".join(str(outcomes[key]) for key in ("win", "regression", "tie", "inconclusive")) if config != "stock-afc" else "— | — | — | —"
            lines.append(f"| {family} | {config} | {completed}/{total} | {full}/{len(entries)} | {outcome_cells} |")
    lines.extend(["", "## All configurations: PAR-2 penalty scores", "",
                  f"PAR-2 is a **score, not an estimated solve time**: each completed run contributes its measured elapsed time, and each incomplete run "
                  f"contributes {2 * limit:g} ms-equivalent (twice the limit). We take the median score over {repeats} runs per instance, "
                  "then the arithmetic mean across instances. Lower scores are better. Actual observed times, process wall times, nodes, LP calls and "
                  "objectives remain separate columns in `comparison.csv`.", "",
                  "| Configuration | Completed runs | Instances completing all runs | Mean median PAR-2 score (ms-equivalent) |",
                  "|---|---:|---:|---:|"])
    for config in CONFIG_ORDER:
        if config not in meta["configs"]:
            continue
        entries = [held_summary[(identity, config)] for identity in ids]
        lines.append(f"| {config} | {sum(e['completed_runs'] for e in entries)}/{sum(e['runs'] for e in entries)} | "
                     f"{sum(e['all_runs_completed'] for e in entries)}/{len(entries)} | "
                     f"{statistics.mean(e['median_par2_score_ms'] for e in entries):.3f} |")
    control = disabled_control(held)
    lines.extend(["", "## Disabled-feature control and independent validation", "",
                  f"Among {control['fully_completed_pairs']} paired runs where both stock AFC and disabled AFC completed, "
                  f"{control['matching_completed_pairs']} matched status, objective, node count, propagation count and failure count. "
                  f"Disabled AFC made zero LP calls in {control['disabled_zero_lp_call_runs']}/{control['paired_runs']} paired runs. "
                  "Time-limited runs are excluded from exact node-count equivalence because clock cutoffs can stop identical search at different nodes.", ""])
    if control["mismatches"]:
        lines.append("**Control mismatches require investigation:** " + json.dumps(control["mismatches"], sort_keys=True))
        lines.append("")
    for dataset in (development, held):
        counts = dataset["validation_counts"]
        lines.append(f"- {dataset['name']}: revalidated {counts['rows']}/{counts['rows']} rows; "
                     f"{counts['claims_verified']}/{counts['rows']} returned claims independently verified, including "
                     f"{counts['completed_claims_verified']}/{counts['completed']} completed-result claims. "
                     "Verifying a feasible timed-out incumbent does not certify its optimality.")
    lines.extend(["", "Input/manifest hashes, JSON/TXT agreement, all assignments, objective values, reference optima and stored validation records "
                  "were checked again before this report was written. Exact references use set-cover subset DP, knapsack DP, bipartite mincut, "
                  "or exhaustive enumeration; they are independent of Gecode and the LP backend.", "",
                  "## Scope", "",
                  "This is a small generated study on one machine and shared problem families. LP setup and solving can cost more than they save on easy "
                  "instances, and fractional relaxations can leave an integrality gap. The results do not establish a universally faster solver. "
                  "Sub-millisecond differences can be noise; no significance test is claimed. Controls and development cases are retained in raw artifacts, "
                  "and development/held-out medians for every configuration are preserved in the CSV.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=HERE / "results")
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument("--held-out", default="held-out")
    parser.add_argument("--development", default="development")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    records = {record["id"]: record for record in manifest["instances"]}
    development = load_dataset(args.development, args.results_dir, args.manifest, manifest, records)
    held = load_dataset(args.held_out, args.results_dir, args.manifest, manifest, records)
    dev_summary, held_summary = summarize(development), summarize(held)
    markdown = report(held, held_summary, development, dev_summary)
    # All validation and report construction finish before either output is replaced.
    write_csv(args.results_dir / "comparison.csv", (dev_summary, held_summary))
    (args.results_dir / "RESULTS.md").write_text(markdown)
    print(json.dumps({"comparison_csv": str(args.results_dir / "comparison.csv"),
                      "report": str(args.results_dir / "RESULTS.md"),
                      "held_out": held["validation_counts"], "development": development["validation_counts"],
                      "disabled_control": disabled_control(held)}, sort_keys=True))


if __name__ == "__main__":
    main()

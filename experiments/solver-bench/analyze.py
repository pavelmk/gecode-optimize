#!/usr/bin/env python3
"""Audited, budget-aware benchmark reports. Never launches a solver.

Default publication scope is test/public. Dev and incomplete batches require
explicit exploratory flags. Differing budgets, warm starts and build protocols
are separated into cohorts instead of being pooled into a misleading ranking.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
from datetime import datetime
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

import native
import validate


HERE = Path(__file__).resolve().parent
SHIFT_MS = 10.0
CONFIG_NUMBERS = ("nodes", "failures", "propagations", "lp_calls", "lp_ms", "build_ms",
                  "peak_rss_kb", "certified_bounds", "rejected_bounds", "lp_infeasible_statuses",
                  "conditional_checks", "variable_fixings", "cuts", "clique_cuts", "cover_cuts",
                  "gcd_rows", "heuristic_nodes", "neighborhoods", "total_nodes", "primal_ms", "primal_calls",
                  "primal_lp_calls", "primal_exact_checks", "heuristic_ms", "heuristic_failures",
                  "heuristic_propagations", "pre_proof_ms")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mathematical_hash(instance, kind):
    return native.mathematical_hash(instance) if kind == "native" else validate.input_hash(instance)


def assignment_check(instance, assignment, kind):
    return (native.validate_assignment if kind == "native" else validate.validate_assignment)(instance, assignment)


def txt_matches(instance, path, kind):
    """Independent parser; checks the precise mathematical input and warm start."""
    tokens = iter(path.read_text().split())
    try:
        if kind == "native":
            family, size, machines, count = next(tokens), int(next(tokens)), int(next(tokens)), int(next(tokens))
            if family == "native_rcpsp":
                data = {"capacities": [int(next(tokens)) for _ in range(machines)],
                        "tasks": [[int(next(tokens)) for _ in range(machines + 1)] for _ in range(size)],
                        "precedences": [[int(next(tokens)), int(next(tokens))] for _ in range(count)]}
                expected_count = len(instance["data"]["precedences"])
            else:
                data = [[int(next(tokens)) for _ in row] for row in instance["data"]]
                expected_count = len(instance["data"])
            witness = [int(next(tokens)) for _ in range(instance["n"])]
            if (family, size, machines, count, data, witness) != (instance["family"], instance["size"],
                    instance.get("machines", 0), expected_count, instance["data"], instance["incumbent"]):
                raise ValueError("native JSON/TXT disagreement")
        else:
            n, count = int(next(tokens)), int(next(tokens))
            costs = [int(next(tokens)) for _ in range(n)]
            rows = []
            for _ in range(count):
                rhs, nonzeros = int(next(tokens)), int(next(tokens))
                rows.append({"a": [[int(next(tokens)), int(next(tokens))] for _ in range(nonzeros)], "b": rhs})
            if next(tokens) != "incumbent":
                raise ValueError("missing incumbent marker")
            flag = int(next(tokens))
            if flag not in (0, 1):
                raise ValueError("invalid incumbent flag")
            witness = [int(next(tokens)) for _ in range(n)] if flag else []
            if (n, costs, rows, witness) != (instance["n"], instance["c"], instance["rows"], instance.get("incumbent") or []):
                raise ValueError("binary JSON/TXT disagreement")
        if list(tokens):
            raise ValueError("unexpected trailing input tokens")
    except StopIteration as exc:
        raise ValueError(f"truncated TXT input: {path}") from exc


def resolve_manifest(recorded, expected_sha, overrides):
    original = Path(recorded)
    candidates = [original, *overrides, HERE / original.name]
    for candidate in candidates:
        if candidate.is_file() and sha(candidate) == expected_sha:
            return candidate.resolve()
    raise ValueError(f"Cannot find unchanged manifest {recorded}; pass its relocated path with --manifest")


def external_references(paths):
    output = {}
    for path in paths:
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            records = payload
        elif "results" in payload:
            records = payload["results"]
        elif "references" in payload:
            value = payload["references"]
            records = [dict(reference, id=identity) for identity, reference in value.items()] if isinstance(value, dict) else value
        else:
            records = [payload]
        for reference in records:
            if reference.get("status") != "optimal":
                continue
            identity = reference["id"]
            if identity in output and output[identity]["objective"] != reference["objective"]:
                raise ValueError(f"Conflicting external exact references for {identity}")
            value = dict(reference)
            value["reference_file"] = str(path)
            value["reference_file_sha256"] = sha(path)
            output[identity] = value
    return output


def independent_external(reference):
    """Require an explicit provenance assertion for external cross-solver claims."""
    solver = str(reference.get("solver", reference.get("backend", ""))).lower()
    return reference.get("independent") is True and bool(solver) and "gecode" not in solver


def cohort_key(protocol):
    fields = ("limit_ms", "warm", "configs", "binaries", "platform", "machine", "threads_per_search",
              "parallel_solver_runs", "highs_mip_used", "timing")
    return {field: protocol.get(field) for field in fields}


def expected_binary(protocol, config, kind):
    specification = protocol["configs"][config]
    if isinstance(specification, dict):
        name = specification["native_binary"] if kind == "native" else specification["binary"]
    else:
        name = specification[3] if kind == "native" else specification[0]
    return name, protocol["binaries"][name]


def finite_number(value, name, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"invalid {name}: {value!r}")
    if minimum is not None and value < minimum:
        raise ValueError(f"negative/out-of-range {name}: {value!r}")


def audit_row(row, protocol, instance, kind):
    if "completed_within_budget" not in row or "objective_at_limit" not in row:
        raise ValueError("Deadline columns are required; do not infer proof-at-deadline from final status")
    if type(row["completed_within_budget"]) is not bool:
        raise ValueError("completed_within_budget must be Boolean")
    _, binary_hash = expected_binary(protocol, row["config"], kind)
    if row.get("binary_sha256") != binary_hash:
        raise ValueError("row binary hash does not match immutable protocol")
    limit = protocol["limit_ms"]
    if row["limit_ms"] != limit or bool(row["warm"]) != bool(protocol["warm"]):
        raise ValueError("row budget/warm-start differs from protocol")
    finite_number(row["elapsed_ms"], "elapsed_ms", 0)
    finite_number(row["process_wall_ms"], "process_wall_ms", 0)
    for field in CONFIG_NUMBERS:
        if field in row:
            finite_number(row[field], field, 0)
    if "primal_found" in row and type(row["primal_found"]) is not bool:
        raise ValueError("primal_found must be Boolean")
    if "primal_calls" in row and "primal_lp_calls" in row and row["primal_calls"] != row["primal_lp_calls"]:
        raise ValueError("legacy primal_calls differs from primal_lp_calls")
    if row["completed_within_budget"] != (row["status"] in ("optimal", "infeasible") and row["elapsed_ms"] <= limit):
        raise ValueError("deadline proof flag disagrees with status and elapsed time")
    checker = native.validate_result if kind == "native" else validate.validate_result
    checked = checker(instance, row)
    if not checked["valid"]:
        raise ValueError(f"invalid original-instance result: {checked}")
    if row.get("validation") != checked:
        raise ValueError("stored validation differs from fresh validation")
    initial = instance.get("incumbent_objective") if protocol["warm"] else None
    if row.get("initial_objective") != initial:
        raise ValueError("wrong initial objective recorded")
    reference = instance.get("reference", {})
    if row.get("reference_status") != reference.get("status") or row.get("reference_objective") != reference.get("objective"):
        raise ValueError("recorded reference differs from original instance")
    observed = initial
    prior_time, prior_objective = -math.inf, initial
    for improvement in row.get("improvements", []):
        if len(improvement) < 2:
            raise ValueError("malformed improvement trace")
        timestamp, objective = improvement[:2]
        finite_number(timestamp, "improvement time", 0)
        if not validate.integer(objective) or timestamp < prior_time:
            raise ValueError("invalid/nonmonotone improvement trace")
        if prior_objective is not None and objective > prior_objective:
            raise ValueError("minimization trajectory worsened")
        if timestamp <= limit:
            observed = objective if observed is None else min(observed, objective)
        prior_time, prior_objective = timestamp, objective
    at_limit = row["objective_at_limit"]
    if at_limit is not None and not validate.integer(at_limit):
        raise ValueError("objective_at_limit must be an integer or null")
    if observed != at_limit:
        raise ValueError(f"deadline objective disagrees with common incumbent/improvement trace: {observed} != {at_limit}")
    if row["completed_within_budget"] and row["status"] == "optimal" and at_limit != row["objective"]:
        raise ValueError("timely optimal result has a different deadline incumbent")
    if at_limit is not None and row.get("objective") is not None and at_limit < row["objective"]:
        raise ValueError("deadline objective improves on the final best incumbent")
    deadline_witness_checked = at_limit is not None and (
        at_limit == initial or (at_limit == row.get("objective") and bool(row.get("assignment"))))
    return checked, deadline_witness_checked


def load_runs(paths, splits, overrides, references, allow_incomplete=False):
    cohorts, provenance = {}, []
    for path in paths:
        metadata = json.loads(path.with_suffix(".meta.json").read_text())
        protocol = metadata["protocol"]
        if not set(protocol["split"].split(",")) & splits:
            continue
        if not metadata.get("completed") and not allow_incomplete:
            raise ValueError(f"Batch is not complete: {path}; finish/resume it before publishing")
        records = {}
        for recorded, expected_sha in protocol["manifests"].items():
            manifest_path = resolve_manifest(recorded, expected_sha, overrides)
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("generation_status") == "in_progress" or manifest.get("ready") is False:
                raise ValueError("input manifest is incomplete")
            for record in manifest["instances"]:
                if record["id"] in records:
                    raise ValueError("duplicate instance IDs across input manifests")
                value = dict(record, directory=manifest_path.parent)
                value.setdefault("kind", "native" if manifest_path.name.startswith("native") else "binary")
                records[record["id"]] = value
        config_names = sorted(protocol["configs"])
        expected = {(identity, config, rep) for identity in protocol["inputs"] for config in config_names
                    for rep in range(protocol["repeats"])}
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if metadata["expected_runs"] != len(expected) or (not allow_incomplete and len(rows) != len(expected)):
            raise ValueError(f"Incomplete or inconsistent row count for {path}: {len(rows)} / {len(expected)}")
        if metadata.get("completed") and metadata.get("completed_runs") != len(rows):
            raise ValueError("completed metadata count disagrees with JSONL row count")
        key_data = cohort_key(protocol)
        cohort_id = "cohort-" + digest(key_data)[:12]
        cohort = cohorts.setdefault(cohort_id, {"id": cohort_id, "protocol": key_data, "inputs": {},
                                                "rows": {}, "expected": set(), "source_files": [], "incomplete": False})
        cohort["source_files"].append(str(path))
        cohort["incomplete"] |= not bool(metadata.get("completed"))
        selected_ids = {identity for identity in protocol["inputs"] if records[identity]["split"] in splits}
        cohort["expected"].update(key for key in expected if key[0] in selected_ids)
        for identity, hashes in protocol["inputs"].items():
            if identity not in selected_ids:
                continue
            record = records[identity]
            instance_path, txt_path = record["directory"] / record["json"], record["directory"] / record["txt"]
            if sha(instance_path) != hashes["json"] or sha(txt_path) != hashes["txt"]:
                raise ValueError(f"changed input {identity}")
            instance = json.loads(instance_path.read_text())
            kind = record["kind"]
            txt_matches(instance, txt_path, kind)
            if "incumbent" in instance:
                checked = assignment_check(instance, instance["incumbent"], kind)
                if not checked["valid"] or checked["objective"] != instance.get("incumbent_objective"):
                    raise ValueError(f"invalid common incumbent {identity}")
            known = copy.deepcopy(instance.get("reference", {}))
            if known and known.get("input_sha256") != mathematical_hash(instance, kind):
                raise ValueError(f"stale embedded reference {identity}")
            independent = known.get("status") == "optimal"
            known_source = "embedded independent oracle" if independent else None
            if identity in references:
                external = references[identity]
                if external.get("input_sha256") != mathematical_hash(instance, kind):
                    raise ValueError(f"stale external reference {identity}")
                if "assignment" in external:
                    checked = assignment_check(instance, external["assignment"], kind)
                    if not checked["valid"] or checked["objective"] != external["objective"]:
                        raise ValueError(f"invalid independent reference witness {identity}")
                if known.get("status") == "optimal" and known["objective"] != external["objective"]:
                    raise ValueError(f"independent references disagree for {identity}")
                if independent_external(external):
                    known, independent = external, True
                    known_source = external.get("solver", external.get("method", "external independent exact solver"))
            entry = {"record": record, "instance": instance, "kind": kind,
                     "independent_reference": known if independent else None,
                     "independent_reference_source": known_source, "external_claim": references.get(identity)}
            if identity in cohort["inputs"] and mathematical_hash(cohort["inputs"][identity]["instance"], kind) != mathematical_hash(instance, kind):
                raise ValueError("same ID names differing mathematical instances")
            cohort["inputs"][identity] = entry
        seen = set()
        for row in rows:
            key = row["id"], row["config"], row["repetition"]
            if key not in expected or key in seen:
                raise ValueError(f"duplicate/unexpected row in {path}: {key}")
            seen.add(key)
            if row["split"] != records[row["id"]]["split"]:
                raise ValueError("row split differs from original instance manifest")
            if row["split"] not in splits:
                continue
            entry = cohort["inputs"][row["id"]]
            if (row["family"] != entry["instance"]["family"] or row["kind"] != entry["kind"] or
                    row["split"] != entry["record"]["split"] or row.get("tier") != entry["record"].get("tier")):
                raise ValueError("wrong recorded instance family/kind/split/tier")
            checked, witness_checked = audit_row(row, protocol, entry["instance"], entry["kind"])
            row = dict(row, _fresh_validation=checked, _deadline_witness_checked=witness_checked)
            reference = entry["independent_reference"]
            if reference:
                if row.get("objective") is not None and row["objective"] < reference["objective"]:
                    raise ValueError("feasible result beats independent optimum")
                if row["status"] == "optimal" and row["objective"] != reference["objective"]:
                    raise ValueError("solver optimum contradicts independent reference")
            if key in cohort["rows"] and cohort["rows"][key] != row:
                raise ValueError(f"conflicting duplicate run across logs: {key}")
            cohort["rows"][key] = row
        if seen != expected and not allow_incomplete:
            raise ValueError(f"missing runs in {path}")
        clock_note = {}
        if metadata.get("finished_utc") and metadata.get("started_utc") and metadata.get("session_wall_seconds") is not None:
            utc_span = (datetime.fromisoformat(metadata["finished_utc"]) - datetime.fromisoformat(metadata["started_utc"])).total_seconds()
            monotonic_span = metadata["session_wall_seconds"]
            clock_note = {"utc_span_seconds": utc_span, "monotonic_session_seconds": monotonic_span,
                          "clock_anomaly": abs(utc_span-monotonic_span) > max(60, .1*monotonic_span)}
        provenance.append({**clock_note, "file": str(path), "sha256": sha(path), "metadata_sha256": sha(path.with_suffix(".meta.json")),
                           "protocol_sha256": digest(protocol), "completed": metadata.get("completed"),
                           "rows": len(rows), "expected_rows": len(expected)})
    if not cohorts:
        raise ValueError("no runs match the requested publication split")
    for cohort in cohorts.values():
        for identity, entry in cohort["inputs"].items():
            rows = [row for key, row in cohort["rows"].items() if key[0] == identity]
            claimed = {row["objective"] for row in rows if row["status"] == "optimal"}
            if len(claimed) > 1:
                raise ValueError(f"configurations disagree on claimed optimum: {identity}")
            feasible = [row["objective"] for row in rows if row.get("objective") is not None]
            if claimed and feasible and min(feasible) < next(iter(claimed)):
                raise ValueError(f"feasible result contradicts another configuration's proof: {identity}")
            external = entry.get("external_claim")
            if external and claimed and external["objective"] != next(iter(claimed)):
                raise ValueError(f"cross-solver optimality claims disagree: {identity}")
            deadline = [row["objective_at_limit"] for row in rows if row["objective_at_limit"] is not None]
            entry["best_observed_at_limit"] = min(deadline) if deadline else None
            entry["gecode_claimed_optimum"] = next(iter(claimed)) if claimed else None
    return cohorts, provenance


def median(values):
    values = list(values)
    return statistics.median(values) if values else None


def summarize_instances(cohort):
    groups = defaultdict(list)
    expected_counts = Counter((identity, config) for identity, config, _ in cohort["expected"])
    for key, row in cohort["rows"].items():
        groups[key[:2]].append(row)
    output = []
    limit = cohort["protocol"]["limit_ms"]
    for (identity, config), expected in sorted(expected_counts.items()):
        rows = groups[identity, config]
        source = cohort["inputs"][identity]
        record, instance = source["record"], source["instance"]
        independent = source["independent_reference"]
        known = independent["objective"] if independent else None
        quality_reference = known if independent else source["best_observed_at_limit"]
        timely = [r for r in rows if r["completed_within_budget"]]
        feasible = [r for r in rows if r["objective_at_limit"] is not None]
        objective_values = [r["objective_at_limit"] for r in feasible]
        capped = [min(r["elapsed_ms"], limit) if r["completed_within_budget"] else limit for r in rows]
        par2 = [r["elapsed_ms"] if r["completed_within_budget"] else 2 * limit for r in rows]
        optimum_hits = sum(known is not None and r["objective_at_limit"] == known for r in rows)
        independently_proved = sum(known is not None and r["completed_within_budget"] and r["status"] == "optimal" for r in rows)
        claimed_only = sum(known is None and r["completed_within_budget"] and r["status"] == "optimal" for r in rows)
        entry = {"cohort": cohort["id"], "id": identity, "family": record["family"], "tier": record.get("tier"),
                 "kind": source["kind"], "split": record["split"], "seed": record.get("seed"), "config": config,
                 "paired_problem_id": record.get("paired_problem_id", instance.get("paired_problem_id")),
                 "semantic_problem": record.get("semantic_problem", instance.get("semantic_problem")),
                 "semantic_input_sha256": record.get("semantic_input_sha256", instance.get("semantic_input_sha256")),
                 "input_sha256": mathematical_hash(instance, source["kind"]), "n": instance["n"],
                 "expected_runs": expected, "observed_runs": len(rows), "missing_runs": expected - len(rows),
                 "limit_ms": limit, "feasible_at_limit_runs": len(feasible), "completed_within_budget_runs": len(timely),
                 "feasible_all_runs": len(feasible) == expected, "completed_all_runs": len(timely) == expected,
                 "completed_majority_runs": len(timely) > expected / 2,
                 "independently_optimal_at_limit_runs": optimum_hits,
                 "independently_verified_proof_runs": independently_proved,
                 "gecode_only_optimal_proof_runs": claimed_only,
                 "late_proof_runs": sum(r["status"] in ("optimal", "infeasible") and not r["completed_within_budget"] for r in rows),
                 "deadline_witness_checked_runs": sum(r["_deadline_witness_checked"] for r in rows),
                 "primal_found_runs": sum(r.get("primal_found") is True for r in rows),
                 "primal_observed_runs": sum("primal_found" in r for r in rows),
                 "heuristic_active_runs": sum(r.get("heuristic_nodes", 0) > 0 or r.get("neighborhoods", 0) > 0 for r in rows),
                 "independent_optimum": known, "independent_reference_source": source["independent_reference_source"],
                 "gecode_claimed_optimum": source["gecode_claimed_optimum"],
                 "best_observed_at_limit": source["best_observed_at_limit"],
                 "quality_reference_kind": "independent optimum" if independent else "best observed; not optimum",
                 "quality_reference": quality_reference, "median_objective_at_limit": median(objective_values),
                 "best_objective_at_limit": min(objective_values) if objective_values else None,
                 "median_completed_time_ms": median(r["elapsed_ms"] for r in rows) if len(timely) == expected else None,
                 "median_observed_time_ms": median(r["elapsed_ms"] for r in rows),
                 "median_capped_time_ms": median(capped), "median_par2_score_ms": median(par2),
                 "median_process_wall_ms": median(r["process_wall_ms"] for r in rows),
                 "median_initial_objective": median(r["initial_objective"] for r in rows if r["initial_objective"] is not None),
                 "generation_timing": instance.get("generation_timing", {"construction_ms": instance.get("construction_ms")})}
        difference = None if quality_reference is None or not objective_values else median(v - quality_reference for v in objective_values)
        entry["median_distance_to_quality_reference"] = difference
        entry["median_normalized_distance"] = None if difference is None else difference / max(1, abs(quality_reference))
        for field in CONFIG_NUMBERS:
            entry["median_" + field] = median(r[field] for r in rows if field in r)
        # Preserve the earlier report field while using the actual driver name.
        entry["median_primal_calls"] = median(r.get("primal_lp_calls", r.get("primal_calls"))
                                              for r in rows if "primal_lp_calls" in r or "primal_calls" in r)
        output.append(entry)
    return output


def shifted_gm(values, shift=SHIFT_MS):
    values = [value for value in values if value is not None]
    return math.exp(statistics.mean(math.log(value + shift) for value in values)) - shift if values else None


def percentile(values, p):
    values = sorted(values)
    position = (len(values) - 1) * p
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def bootstrap_ratio(common, samples, seed):
    """Family-stratified resampling of independent instance median log ratios."""
    groups = defaultdict(list)
    for family, baseline, candidate in common:
        if baseline > 0 and candidate > 0:
            groups[family].append(math.log(baseline / candidate))
    values = [v for group in groups.values() for v in group]
    point = math.exp(statistics.mean(values)) if values else None
    if not samples or len(values) < 5 or sum(max(0, len(group) - 1) for group in groups.values()) < 2:
        return {"point": point, "ci95": None, "instances": len(values), "samples": 0,
                "reason": "disabled or insufficient within-family replication"}
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = [rng.choice(group) for group in groups.values() for _ in range(len(group))]
        estimates.append(math.exp(statistics.mean(draw)))
    return {"point": point, "ci95": [percentile(estimates, .025), percentile(estimates, .975)],
            "instances": len(values), "samples": samples,
            "method": "percentile bootstrap of paired instance median log ratios, stratified by family"}


def compare_entries(entries, baseline_name, samples, seed):
    by_config = defaultdict(dict)
    for entry in entries:
        by_config[entry["config"]][entry["id"]] = entry
    baseline = by_config.get(baseline_name, {})
    if not baseline:
        raise ValueError(f"baseline configuration {baseline_name!r} absent from cohort")
    universe = set(baseline)
    output = []
    for config, group in sorted(by_config.items()):
        if set(group) != universe:
            raise ValueError("unbalanced instance coverage: put different configuration sets in separate cohorts")
        items = list(group.values())
        common = []
        faster = slower = tied = newly_proved = newly_feasible = newly_reliable = lost_proofs = 0
        baseline_families, candidate_families = defaultdict(int), defaultdict(int)
        for identity in sorted(universe):
            before, after = baseline[identity], group[identity]
            baseline_families[before["family"]] += before["completed_within_budget_runs"]
            candidate_families[after["family"]] += after["completed_within_budget_runs"]
            newly_proved += after["completed_all_runs"] and before["completed_within_budget_runs"] == 0
            newly_reliable += after["completed_all_runs"] and not before["completed_all_runs"]
            newly_feasible += after["feasible_all_runs"] and before["feasible_at_limit_runs"] == 0
            lost_proofs += before["completed_all_runs"] and after["completed_within_budget_runs"] == 0
            if before["completed_all_runs"] and after["completed_all_runs"]:
                b, a = before["median_completed_time_ms"], after["median_completed_time_ms"]
                common.append((after["family"], b, a))
                if math.isclose(b, a, rel_tol=1e-9):
                    tied += 1
                elif a < b:
                    faster += 1
                else:
                    slower += 1
        full_data = all(not item["missing_runs"] for item in items)
        sgm = shifted_gm(item["median_capped_time_ms"] for item in items) if full_data else None
        scores = [item["median_par2_score_ms"] for item in items]
        entry = {"config": config, "baseline": baseline_name, "instances": len(items),
                 "observed_runs": sum(i["observed_runs"] for i in items), "expected_runs": sum(i["expected_runs"] for i in items),
                 "missing_runs": sum(i["missing_runs"] for i in items),
                 "feasible_at_limit_instances": sum(i["feasible_all_runs"] for i in items),
                 "feasible_at_limit_runs": sum(i["feasible_at_limit_runs"] for i in items),
                 "completed_instances": sum(i["completed_all_runs"] for i in items),
                 "majority_completed_instances": sum(i["completed_majority_runs"] for i in items),
                 "completed_within_budget_runs": sum(i["completed_within_budget_runs"] for i in items),
                 "independently_optimal_at_limit_runs": sum(i["independently_optimal_at_limit_runs"] for i in items),
                 "independently_verified_proof_runs": sum(i["independently_verified_proof_runs"] for i in items),
                 "gecode_only_optimal_proof_runs": sum(i["gecode_only_optimal_proof_runs"] for i in items),
                 "late_proof_runs": sum(i["late_proof_runs"] for i in items),
                 "deadline_witness_checked_runs": sum(i["deadline_witness_checked_runs"] for i in items),
                 "primal_found_runs": sum(i["primal_found_runs"] for i in items),
                 "primal_observed_runs": sum(i["primal_observed_runs"] for i in items),
                 "heuristic_active_runs": sum(i["heuristic_active_runs"] for i in items),
                 "newly_proved_instances": newly_proved, "newly_reliably_solved_instances": newly_reliable,
                 "newly_feasible_instances": newly_feasible, "lost_proof_instances": lost_proofs,
                 "common_completed_instances": len(common), "faster_common_completed_instances": faster,
                 "regressions_common_completed_instances": slower, "tied_common_completed_instances": tied,
                 "common_completed_mean_baseline_ms": statistics.mean(b for _, b, _ in common) if common else None,
                 "common_completed_mean_config_ms": statistics.mean(a for _, _, a in common) if common else None,
                 "shifted_geometric_mean_capped_ms": sgm, "sgm_shift_ms": SHIFT_MS,
                 "mean_median_par2_score_ms": statistics.mean(scores) if full_data and scores else None,
                 "paired_common_solved_speedratio": bootstrap_ratio(common, samples, seed + int(digest(config)[:8], 16)),
                 "newly_solvable_families_in_budget": sorted(f for f, count in candidate_families.items() if count and baseline_families[f] == 0)}
        output.append(entry)
    output.sort(key=lambda x: (-x["completed_instances"], x["shifted_geometric_mean_capped_ms"] if x["shifted_geometric_mean_capped_ms"] is not None else math.inf, x["config"]))
    for rank, entry in enumerate(output, 1):
        entry["rank"] = rank if not entry["missing_runs"] else None
    return output


def compact_protocol(protocol):
    return {key: protocol.get(key) for key in ("limit_ms", "warm", "platform", "machine", "threads_per_search",
                                             "parallel_solver_runs", "highs_mip_used", "timing", "configs", "binaries")}


def build_report(cohorts, provenance, baseline, samples, exploratory):
    reports, all_instances, comparisons = [], [], []
    for cohort in sorted(cohorts.values(), key=lambda c: c["id"]):
        instances = summarize_instances(cohort)
        baseline_instances = {item["id"]: item for item in instances if item["config"] == baseline}
        for item in instances:
            before = baseline_instances.get(item["id"])
            item["baseline_completed_within_budget_runs"] = before["completed_within_budget_runs"] if before else None
            item["paired_completed_speed_ratio"] = None
            item["censored_speed_ratio_lower_bound"] = None
            if before and before["completed_all_runs"] and item["completed_all_runs"]:
                item["paired_completed_speed_ratio"] = before["median_completed_time_ms"] / item["median_completed_time_ms"] if item["median_completed_time_ms"] > 0 else None
            elif (before and before["completed_within_budget_runs"] == 0 and before["observed_runs"] == before["expected_runs"]
                  and before["median_observed_time_ms"] >= before["limit_ms"] and item["completed_all_runs"]
                  and item["median_completed_time_ms"] > 0):
                item["censored_speed_ratio_lower_bound"] = before["limit_ms"] / item["median_completed_time_ms"]
        overall = compare_entries(instances, baseline, samples, 59183)
        by_family = {}
        for family in sorted({entry["family"] for entry in instances}):
            selected = [entry for entry in instances if entry["family"] == family]
            by_family[family] = compare_entries(selected, baseline, samples, 59183 + int(digest(family)[:8], 16))
        for scope, entries in [("overall", overall), *by_family.items()]:
            for entry in entries:
                comparisons.append(dict(entry, cohort=cohort["id"], scope=scope))
        all_instances.extend(instances)
        reports.append({"id": cohort["id"], "protocol": compact_protocol(cohort["protocol"]),
                        "source_files": cohort["source_files"], "incomplete": cohort["incomplete"],
                        "instance_count": len(cohort["inputs"]), "family_count": len(by_family),
                        "splits": sorted({entry["split"] for entry in instances}),
                        "repetitions": sorted({entry["expected_runs"] for entry in instances}),
                        "overall": overall, "families": by_family})
    reference_sources = {entry["external_claim"]["reference_file"]: entry["external_claim"]["reference_file_sha256"]
                         for cohort in cohorts.values() for entry in cohort["inputs"].values() if entry.get("external_claim")}
    return {"schema_version": 1, "title": "Solver benchmark results", "exploratory": exploratory,
            "baseline": baseline, "cohorts": reports, "instances": all_instances, "comparisons": comparisons,
            "provenance": provenance, "external_reference_sources": reference_sources,
            "methodology": {
                "unit": "One independently generated instance; timing observations are medians of its repetitions.",
                "primary_rank": "Instances completed within budget in every repetition, then shifted geometric mean of capped median times.",
                "deadline": "Only completed_within_budget counts as timely proof. Late proofs never count as solved within the budget.",
                "feasible": "An objective_at_limit counts as a deadline incumbent. Final and initial witnesses are independently checked; intermediate-only trace witnesses may not be retained.",
                "independent": "Embedded exact oracles and explicitly independent external exact references are separate from Gecode-only optimum claims.",
                "capped_time": "Every incomplete run contributes its cutoff to the capped-time score; timely completions contribute min(elapsed, cutoff).",
                "sgm": "exp(mean(log(median capped milliseconds + 10))) - 10. This capped score is not an estimate of censored completion times.",
                "par2": "Each incomplete run contributes twice its cutoff; timely completions contribute elapsed time. Take the median per instance, then arithmetic mean. This is a penalty score, not a solve-time estimate.",
                "arithmetic_means": "Reported only for the identical subset completed in every repetition by both the baseline and comparison configuration.",
                "censored_ratios": "Per-instance speed ratios are reported only when both configurations complete every repetition. If no baseline repetition proves within budget, its median observed runtime reaches the cutoff, and the comparison completes every repetition, cutoff/comparison median is reported only as a lower bound.",
                "newly_proved": "Comparison completed every repetition while stock proved zero repetitions. More reliable completion and completely lost proof counts are also separate.",
                "newly_solvable_families": "At least one proof within budget under the comparison and zero under stock. This concerns the sample and budget, not a mathematical change of problem class.",
                "bootstrap": "95% percentile bootstrap of paired per-instance median log speed ratios on common solved cases; independent instances resampled within each family. It does not quantify generalization to new families or only hardware noise.",
                "unknown_optima": "Best observed objective means best feasible objective logged within the cutoff across configurations; distance to it is not a true optimality gap.",
                "cohorts": "Different budgets, warm starts, platform/settings, configuration lists or binary versions are never pooled into a primary ranking.",
                "scope": "Generated/public sampled instances on one machine. No universal solver superiority or statistical significance for each individual instance is claimed."}}


def flat_csv(path, entries):
    fields = list(dict.fromkeys(key for entry in entries for key in entry))
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow({key: json.dumps(value, sort_keys=True, separators=(",", ":")) if isinstance(value, (dict, list)) else value
                             for key, value in entry.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--manifest", type=Path, action="append", default=[], help="relocated immutable manifest")
    parser.add_argument("--references", type=Path, action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=HERE / "reports")
    parser.add_argument("--split", default=None)
    parser.add_argument("--baseline", default="stock")
    parser.add_argument("--exploratory", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    args = parser.parse_args()
    splits = set((args.split or ("dev" if args.exploratory else "test,public")).split(","))
    if "dev" in splits and not args.exploratory:
        parser.error("development results require --exploratory")
    if args.allow_incomplete and (not args.exploratory or splits != {"dev"}):
        parser.error("--allow-incomplete is permitted only for explicit exploratory dev analysis")
    if args.bootstrap_samples < 0:
        parser.error("bootstrap sample count must be nonnegative")
    references = external_references(args.references)
    cohorts, provenance = load_runs(args.runs, splits, args.manifest, references, args.allow_incomplete)
    report = build_report(cohorts, provenance, args.baseline, args.bootstrap_samples, args.exploratory)
    template = (HERE / "leaderboard.template.html").read_text()
    encoded = json.dumps(report, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")
    html = template.replace("__BENCHMARK_JSON__", encoded)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "leaderboard.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (args.out_dir / "leaderboard.html").write_text(html)
    flat_csv(args.out_dir / "instance-results.csv", report["instances"])
    flat_csv(args.out_dir / "comparisons.csv", report["comparisons"])
    print(json.dumps({"output": str(args.out_dir), "cohorts": len(report["cohorts"]),
                      "instance_configuration_summaries": len(report["instances"]),
                      "audited_rows": sum(item["rows"] for item in provenance),
                      "exploratory": args.exploratory}, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reproducible binary-linear benchmark families and independent exact references.

Default: 4 dev + 4 test cases per family, 8 tiny cases per family, 4 controls.
The default 52 instances test mechanisms; hardness/speedups are not guaranteed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random

from validate import check_instance, exact_reference, input_hash, validate_assignment, validate_result


FAMILIES = ("set_cover", "knapsack", "bipartite_cover")


def positive_cover_incumbent(instance):
    """Greedy cost/newly-covered-row heuristic, followed by redundant-set removal.

    Uses only original coefficients and costs, never a reference optimum.
    Also supports positive unit-coefficient multicover rows.
    """
    n, rows = instance["n"], instance["rows"]
    covers = [[] for _ in range(n)]
    for i, row in enumerate(rows):
        for j, coefficient in row["a"]:
            if coefficient != 1:
                raise ValueError("cover greedy requires unit positive coefficients")
            covers[j].append(i)
    selected, coverage = [0] * n, [0] * len(rows)
    while any(coverage[i] < row["b"] for i, row in enumerate(rows)):
        candidates = []
        for j in range(n):
            if selected[j]:
                continue
            gain = sum(coverage[i] < rows[i]["b"] for i in covers[j])
            if gain:
                candidates.append((instance["c"][j] / gain, instance["c"][j], j))
        if not candidates:
            raise ValueError("generated cover instance is infeasible")
        j = min(candidates)[2]
        selected[j] = 1
        for i in covers[j]:
            coverage[i] += 1
    for j in sorted(range(n), key=lambda v: (-instance["c"][v], v)):
        if selected[j] and all(coverage[i] - 1 >= rows[i]["b"] for i in covers[j]):
            selected[j] = 0
            for i in covers[j]:
                coverage[i] -= 1
    return selected


def make_instance(family, split, seed, index, scale=1.0, set_density=0.24,
                  bipartite_density=0.25, capacity_ratio=0.25):
    rng = random.Random(seed)
    tiny, stress = split == "tiny", split == "stress"
    multiplier = scale * (1.65 if stress else 1)
    instance = {"id": f"{split}_{family}_{seed}", "family": family, "split": split,
                "seed": seed, "generator_version": 1,
                "label": "tiny-exact" if tiny else ("larger-stress" if stress else "moderate-generated")}
    if family == "set_cover":
        n = 8 + index % 4 if tiny else max(4, round((32 + 4 * (index % 4)) * multiplier))
        elements = 5 + index % 3 if tiny else 14 + 2 * (index % 4) + (4 if stress else 0)
        demand = 2 if tiny and index % 4 == 3 else 1
        rows = []
        for _ in range(elements):
            providers = {j for j in range(n) if rng.random() < set_density}
            if len(providers) < demand + 1:
                providers.update(rng.sample(range(n), min(n, demand + 1)))
            rows.append({"a": [[j, 1] for j in sorted(providers)], "b": demand})
        instance.update(n=n, c=[rng.randint(1, 25) for _ in range(n)], rows=rows,
                        construction={"elements": elements, "density": set_density, "demand": demand})
        if demand == 2:
            instance["label"] = "tiny-multicover"
        instance["incumbent"] = positive_cover_incumbent(instance)
        instance["incumbent_method"] = "cost/new coverage greedy with redundant-column removal"
    elif family == "knapsack":
        n = 8 + index % 4 if tiny else max(4, round((28 + 4 * (index % 4)) * multiplier))
        weights = [[rng.randint(1, 8 if tiny else 20) for _ in range(n)] for _ in range(2)]
        capacities = [max(max(w), round(sum(w) * capacity_ratio)) for w in weights]
        profits = [rng.randint(1, 20 if tiny else 100) for _ in range(n)]
        rows = [{"a": [[j, -w] for j, w in enumerate(weight)], "b": -capacity}
                for weight, capacity in zip(weights, capacities)]
        instance.update(n=n, c=[-profit for profit in profits], rows=rows,
                        construction={"capacities": capacities, "capacity_ratio": capacity_ratio})
        order = sorted(range(n), key=lambda j: (-profits[j] / (weights[0][j] / capacities[0]
                                                               + weights[1][j] / capacities[1]), j))
        assignment, used = [0] * n, [0, 0]
        for j in order:
            if all(used[k] + weights[k][j] <= capacities[k] for k in range(2)):
                assignment[j] = 1
                for k in range(2):
                    used[k] += weights[k][j]
        instance["incumbent"] = assignment
        instance["incumbent_method"] = "profit/normalized-resource greedy"
    else:
        n = 8 + 2 * (index % 2) if tiny else max(4, 2 * round((13 + 2 * (index % 4)) * multiplier))
        left = n // 2
        permutation = list(range(n))
        rng.shuffle(permutation)
        edges = {tuple(sorted((permutation[u], permutation[v]))) for u in range(left)
                 for v in range(left, n) if rng.random() < bipartite_density}
        # Matching edges avoid isolated variables without compromising bipartiteness.
        edges.update(tuple(sorted((permutation[u], permutation[left + u]))) for u in range(left))
        rows = [{"a": [[u, 1], [v, 1]], "b": 1} for u, v in sorted(edges)]
        instance.update(n=n, c=[rng.randint(1, 25) for _ in range(n)], rows=rows,
                        construction={"density": bipartite_density, "left_size": left,
                                      "shuffled_variable_ids": True})
        instance["incumbent"] = positive_cover_incumbent(instance)
        instance["incumbent_method"] = "cost/new coverage greedy with redundant-column removal"
    check_instance(instance)
    checked = validate_assignment(instance, instance["incumbent"])
    if not checked["valid"]:
        raise AssertionError((instance["id"], "invalid greedy incumbent"))
    instance["incumbent_objective"] = checked["objective"]
    return instance


def controls():
    triangle_rows = []
    for offset in range(0, 12, 3):
        triangle_rows.extend({"a": [[offset + u, 1], [offset + v, 1]], "b": 1}
                             for u, v in ((0, 1), (0, 2), (1, 2)))
    output = [
        {"id": "control_four_disjoint_triangles", "family": "binary_linear", "n": 12,
         "c": [1] * 12, "rows": triangle_rows, "incumbent": [1, 1, 0] * 4,
         "incumbent_method": "explicit two-vertices-per-triangle witness",
         "label": "fractional-LP-gap-control", "known_lp_relaxation_value": 6},
        {"id": "control_no_rows", "family": "binary_linear", "n": 10,
         "c": list(range(1, 11)), "rows": [], "incumbent": [0] * 10,
         "incumbent_method": "zero vector", "label": "trivial-unfavorable-overhead-control"},
        {"id": "control_infeasible_binary_bounds", "family": "binary_linear", "n": 4,
         "c": [1, 2, 3, 4], "rows": [{"a": [[0, 1]], "b": 1}, {"a": [[0, -1]], "b": 0}],
         "label": "infeasible-bound-control"},
        {"id": "control_negative_free_objective", "family": "binary_linear", "n": 8,
         "c": [-1, -2, -3, -4, 1, 2, 3, 4], "rows": [], "incumbent": [1, 1, 1, 1, 0, 0, 0, 0],
         "incumbent_method": "objective-sign witness", "label": "signed-objective-control"},
    ]
    for instance in output:
        instance.update(split="control", seed=None, generator_version=1)
        if "incumbent" in instance:
            instance["incumbent_objective"] = validate_assignment(instance, instance["incumbent"])["objective"]
    return output


def to_text(instance):
    lines = [f"{instance['n']} {len(instance['rows'])}", " ".join(map(str, instance["c"]))]
    for row in instance["rows"]:
        values = [row["b"], len(row["a"])]
        for j, coefficient in row["a"]:
            values.extend((j, coefficient))
        lines.append(" ".join(map(str, values)))
    if "incumbent" in instance:
        lines.extend(("incumbent 1", " ".join(map(str, instance["incumbent"]))))
    else:
        lines.append("incumbent 0")
    return "\n".join(lines) + "\n"


def write_suite(directory, per_split=4, tiny_per_family=8, stress_per_family=0,
                scale=1.0, set_density=0.24, bipartite_density=0.25,
                capacity_ratio=0.25, oracle_time_limit=10.0, oracle_max_states=5_000_000):
    directory = Path(directory)
    instance_directory = directory / "instances"
    instance_directory.mkdir(parents=True, exist_ok=True)
    instances = []
    for split, offset, count in (("tiny", 500_000, tiny_per_family), ("dev", 600_000, per_split),
                                 ("test", 700_000, per_split), ("stress", 800_000, stress_per_family)):
        for family_index, family in enumerate(FAMILIES):
            for index in range(count):
                seed = offset + family_index * 10_000 + index
                instances.append(make_instance(family, split, seed, index, scale, set_density,
                                               bipartite_density, capacity_ratio))
    instances.extend(controls())
    crosschecks = 0
    oracle_methods = {}
    records = []
    for instance in instances:
        reference = exact_reference(instance, oracle_max_states, oracle_time_limit)
        if reference["status"] == "unknown" and instance["split"] != "stress":
            raise RuntimeError((instance["id"], "independent oracle did not finish", reference))
        instance["reference"] = reference
        if instance["split"] == "tiny":
            enumerated = exact_reference(instance, oracle_max_states, oracle_time_limit, exhaustive=True)
            if (enumerated["status"], enumerated.get("objective")) != (reference["status"], reference.get("objective")):
                raise AssertionError((instance["id"], "specialized oracle / enumeration mismatch"))
            crosschecks += reference["method"] != "exhaustive enumeration"
        if reference["status"] != "unknown":
            checked = validate_result(instance, reference)
            if not checked["valid"] or not checked["claims_verified"]:
                raise AssertionError((instance["id"], "reference failed validation", checked))
        oracle_methods[reference["method"]] = oracle_methods.get(reference["method"], 0) + 1
        if "incumbent" in instance:
            # Recorded after construction; never used to select or improve incumbents.
            instance["incumbent_matches_optimum"] = (reference["status"] == "optimal"
                                                        and instance["incumbent_objective"] == reference["objective"])
        json_path = instance_directory / (instance["id"] + ".json")
        txt_path = instance_directory / (instance["id"] + ".txt")
        json_path.write_text(json.dumps(instance, indent=2, sort_keys=True) + "\n")
        txt_path.write_text(to_text(instance))
        record = {key: instance[key] for key in ("id", "family", "split", "seed", "label", "n")}
        record.update(json=str(json_path.relative_to(directory)), txt=str(txt_path.relative_to(directory)),
                      rows=len(instance["rows"]), input_sha256=input_hash(instance),
                      reference_status=reference["status"])
        records.append(record)
    manifest = {"schema_version": 1, "generator_version": 1,
                "parameters": {"per_split": per_split, "tiny_per_family": tiny_per_family,
                               "stress_per_family": stress_per_family, "scale": scale,
                               "set_density": set_density, "bipartite_density": bipartite_density,
                               "capacity_ratio": capacity_ratio, "oracle_time_limit": oracle_time_limit,
                               "oracle_max_states": oracle_max_states},
                "validation": {"tiny_specialized_vs_exhaustive_comparisons": crosschecks,
                               "oracle_methods": oracle_methods},
                "notes": ["All constraints have form sparse a*x >= b; x is binary and c*x is minimized.",
                          "Greedy incumbent computation never reads an optimum reference; both drivers get identical witnesses.",
                          "Seeds are disjoint across split and family. Do not tune on held-out timing results.",
                          "References and hashes validate optima independently; TXT omits references.",
                          "Labels are construction descriptions, not promised solver difficulty or gains.",
                          "Oracle counters are not Gecode search nodes; no solver timings are generated here.",
                          "Bipartite-cover LPs are integral; disjoint triangles explicitly illustrate an integrality gap."],
                "instances": records}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--per-split", type=int, default=4)
    parser.add_argument("--tiny-per-family", type=int, default=8)
    parser.add_argument("--stress-per-family", type=int, default=0)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--set-density", type=float, default=0.24)
    parser.add_argument("--bipartite-density", type=float, default=0.25)
    parser.add_argument("--capacity-ratio", type=float, default=0.25)
    parser.add_argument("--oracle-time-limit", type=float, default=10.0)
    parser.add_argument("--oracle-max-states", type=int, default=5_000_000)
    args = parser.parse_args()
    if any(not 0 <= count < 10_000 for count in (args.per_split, args.tiny_per_family, args.stress_per_family)):
        parser.error("counts must lie in [0,9999] to preserve disjoint seed ranges")
    if args.scale <= 0 or not 0 <= args.set_density <= 1 or not 0 <= args.bipartite_density <= 1:
        parser.error("positive scale and densities in [0,1] are required")
    if not 0 < args.capacity_ratio <= 1 or args.oracle_time_limit <= 0 or args.oracle_max_states < 1:
        parser.error("invalid capacity ratio or oracle budget")
    manifest = write_suite(args.out_dir, args.per_split, args.tiny_per_family, args.stress_per_family,
                           args.scale, args.set_density, args.bipartite_density, args.capacity_ratio,
                           args.oracle_time_limit, args.oracle_max_states)
    print(json.dumps({"out_dir": str(args.out_dir), "instances": len(manifest["instances"]),
                      "validation": manifest["validation"], "solver_timings_performed": False}, sort_keys=True))


if __name__ == "__main__":
    main()

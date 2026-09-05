#!/usr/bin/env python3
"""Native cumulative scheduling inputs, independent validation, and safe bounds.

Text format: native_rcpsp tasks resources precedence_edges; capacities; then
one [duration,demand_per_resource...] row per task; precedence pairs; start times.
The objective is minimum max(start+duration), with nonpreemptive tasks, integer
starts, DAG finish-before-start precedences and renewable cumulative capacities.
"""
from __future__ import annotations
import argparse
import heapq
import json
from pathlib import Path
import random
import time

HERE = Path(__file__).resolve().parent


def mathematical_hash(p):
    # Native's canonical mathematical fields include the complete data dict.
    from native import mathematical_hash as canonical
    return canonical(p)


def check_instance(p):
    n, resources, data = p["n"], p["machines"], p["data"]
    integer = lambda v: type(v) is int
    if p["family"] != "native_rcpsp" or p["size"] != n or not integer(n) or not 1 <= n <= 100:
        raise ValueError("RCPSP task dimensions")
    if not integer(resources) or not 1 <= resources <= 10:
        raise ValueError("RCPSP resource dimensions")
    capacities, tasks, edges = data["capacities"], data["tasks"], data["precedences"]
    if len(capacities) != resources or any(not integer(c) or not 1 <= c <= 100000 for c in capacities):
        raise ValueError("RCPSP capacities")
    if len(tasks) != n:
        raise ValueError("RCPSP task count")
    for task in tasks:
        if len(task) != resources + 1 or not integer(task[0]) or not 1 <= task[0] <= 100000:
            raise ValueError("RCPSP task duration")
        if any(not integer(d) or not 0 <= d <= c for d, c in zip(task[1:], capacities)):
            raise ValueError("RCPSP demands")
    following = [[] for _ in range(n)]
    indegree = [0] * n
    seen = set()
    for edge in edges:
        if len(edge) != 2 or any(not integer(v) or not 0 <= v < n for v in edge):
            raise ValueError("RCPSP precedence index")
        a, b = edge
        if a == b or (a, b) in seen:
            raise ValueError("RCPSP duplicate/self precedence")
        seen.add((a, b)); following[a].append(b); indegree[b] += 1
    ready = [j for j in range(n) if not indegree[j]]
    heapq.heapify(ready)
    order = []
    while ready:
        a = heapq.heappop(ready); order.append(a)
        for b in following[a]:
            indegree[b] -= 1
            if not indegree[b]: heapq.heappush(ready, b)
    if len(order) != n:
        raise ValueError("RCPSP precedence cycle")
    return order


def validate_assignment(p, x):
    check_instance(p)
    n, data = p["n"], p["data"]
    tasks = data["tasks"]
    horizon = sum(task[0] for task in tasks)
    if not isinstance(x, list) or len(x) != n or any(type(v) is not int or not 0 <= v <= horizon for v in x):
        return {"valid": False, "error": "RCPSP start domain"}
    ends = [start + task[0] for start, task in zip(x, tasks)]
    if any(ends[a] > x[b] for a, b in data["precedences"]):
        return {"valid": False, "error": "RCPSP precedence violation"}
    for r, capacity in enumerate(data["capacities"]):
        events = {}
        for j, task in enumerate(tasks):
            events[x[j]] = events.get(x[j], 0) + task[r + 1]
            events[ends[j]] = events.get(ends[j], 0) - task[r + 1]
        load = 0
        for at in sorted(events):
            load += events[at]
            if load > capacity:
                return {"valid": False, "error": "RCPSP resource overload"}
    return {"valid": True, "objective": max(ends)}


def lower_bound(p):
    order = check_instance(p)
    tasks, capacities, edges = (p["data"][key] for key in ("tasks", "capacities", "precedences"))
    earliest = [0] * p["n"]
    following = [[] for _ in range(p["n"])]
    for a, b in edges: following[a].append(b)
    for a in order:
        for b in following[a]: earliest[b] = max(earliest[b], earliest[a] + tasks[a][0])
    critical_path = max(start + task[0] for start, task in zip(earliest, tasks))
    energy = max((sum(task[0] * task[r + 1] for task in tasks) + cap - 1) // cap
                 for r, cap in enumerate(capacities))
    return max(critical_path, energy)


def validate_result(p, result):
    check_instance(p)
    status, x = result.get("status"), result.get("assignment", [])
    if status not in ("optimal", "feasible", "unknown", "infeasible"):
        return {"valid": False, "error": "RCPSP result status"}
    reference = p["reference"]
    if reference.get("input_sha256") != mathematical_hash(p):
        return {"valid": False, "error": "stale RCPSP reference"}
    if status in ("unknown", "infeasible"):
        if x or result.get("objective") is not None:
            return {"valid": False, "error": "unexpected RCPSP witness"}
        if status == "infeasible":
            return {"valid": False, "error": "RCPSP DAG and individually feasible tasks admit a serial schedule"}
        return {"valid": True, "claims_verified": True, "optimality_independent": False}
    checked = validate_assignment(p, x)
    objective = result.get("objective")
    if not checked["valid"] or type(objective) is not int or objective != checked["objective"]:
        return {"valid": False, "error": "RCPSP witness/objective mismatch"}
    if objective < lower_bound(p):
        return {"valid": False, "error": "RCPSP objective violates independent lower bound"}
    known = reference["status"] == "optimal"
    if known and (objective < reference["objective"] or (status == "optimal" and objective != reference["objective"])):
        return {"valid": False, "error": "RCPSP optimum contradicts independent reference"}
    # A valid witness matching the independently computed bound certifies itself.
    proved = objective == lower_bound(p) or (known and objective == reference["objective"])
    return {"valid": True, "claims_verified": status != "optimal" or proved,
            "optimality_independent": status == "optimal" and proved}


def make(tier, seed):
    started = time.perf_counter(); rng = random.Random(seed)
    n = 14 if tier == "large" else 8
    capacities = [5, 6]
    tasks = [[rng.randint(2, 9), rng.randint(1, 4), rng.randint(1, 5)] for _ in range(n)]
    edges = [[a, b] for a in range(n) for b in range(a + 1, n) if rng.random() < .15]
    p = {"family": "native_rcpsp", "kind": "native", "size": n, "n": n, "machines": 2,
         "tier": tier, "seed": seed,
         "data": {"capacities": capacities, "tasks": tasks, "precedences": edges}}
    witness, clock = [0] * n, 0
    for j in check_instance(p): witness[j] = clock; clock += tasks[j][0]
    checked = validate_assignment(p, witness)
    if not checked["valid"] or checked["objective"] != clock: raise AssertionError("RCPSP serial witness")
    p.update(incumbent=witness, incumbent_objective=clock,
             incumbent_method="serial schedule in deterministic topological order")
    bound = lower_bound(p)
    p["reference"] = {"status": "optimal" if bound == clock else "unknown", "lower_bound": bound,
                      "method": "critical path and renewable resource energy bound; exact only if matched by witness",
                      "input_sha256": mathematical_hash(p)}
    if bound == clock: p["reference"].update(objective=clock, assignment=witness)
    p["construction_ms"] = (time.perf_counter() - started) * 1000
    return p


def encode(p):
    check_instance(p)
    data = p["data"]
    return (f"native_rcpsp {p['n']} {p['machines']} {len(data['precedences'])}\n"
            + " ".join(map(str, data["capacities"])) + "\n"
            + "\n".join(" ".join(map(str, task)) for task in data["tasks"]) + "\n"
            + " ".join(str(v) for edge in data["precedences"] for v in edge) + "\n"
            + " ".join(map(str, p["incumbent"])) + "\n")


def generate(output=HERE):
    output = Path(output); directory = output / "rcpsp-instances"; directory.mkdir(parents=True, exist_ok=True)
    records = []
    for t, tier in enumerate(("small", "large")):
        for split, count, offset in (("dev", 3, 1000), ("test", 5, 2000)):
            for rep in range(count):
                seed = 9400000 + t * 10000 + offset + rep
                p = make(tier, seed); identity = f"{split}_native_rcpsp_{tier}_{seed}"
                p.update(id=identity, split=split, label=f"native_rcpsp {tier} seed {seed}")
                stem = directory / identity
                stem.with_suffix(".json").write_text(json.dumps(p, indent=2) + "\n")
                stem.with_suffix(".txt").write_text(encode(p))
                records.append({key: p[key] for key in ("id", "family", "tier", "split", "seed", "label", "kind")}
                               | {"json": str(stem.with_suffix(".json").relative_to(output)),
                                  "txt": str(stem.with_suffix(".txt").relative_to(output))})
    (output / "rcpsp-manifest.json").write_text(json.dumps({"schema_version": 1, "instances": records}, indent=2) + "\n")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    print(f"Generated {len(generate(args.output))} native RCPSP cases; no optimizer called")

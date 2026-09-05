#!/usr/bin/env python3
"""Independent exact weighted vertex cover references using bitmask MWIS.

This is an exact recurrence oracle, not a Gecode wrapper or a formal proof-log
checker. Its references validate numerical optima using a different algorithm.
For each vertex subset S, MWIS(S) is the larger of MWIS(S-v) and
weight(v) + MWIS(S - ({v} union N(v))). Isolated vertices always belong to an
optimal independent set because generated weights are positive. Complementing
an optimal independent set gives an optimal weighted vertex cover.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from functools import lru_cache
from pathlib import Path

from validate import check_instance, exact_solve, validate_assignment


class OracleBudgetExceeded(Exception):
    pass


def instance_hash(instance):
    mathematical_data = {key: instance[key] for key in ("family", "n", "weights", "edges")}
    encoded = json.dumps(mathematical_data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def exact_vertex_cover(instance, time_limit=10.0, max_states=2_000_000):
    """Return an optimal cover and independent-set witness, or a budget timeout."""
    check_instance(instance)
    if instance["family"] != "vertex_cover":
        raise ValueError("this oracle only supports vertex_cover")
    if time_limit <= 0 or max_states < 1:
        raise ValueError("time_limit and max_states must be positive")
    started = time.perf_counter()
    deadline = started + time_limit
    n, weights = instance["n"], instance["weights"]
    adjacency = [0] * n
    for u, v in instance["edges"]:
        adjacency[u] |= 1 << v
        adjacency[v] |= 1 << u
    counters = {"states_evaluated": 0, "branch_states": 0, "isolate_states": 0}

    @lru_cache(maxsize=None)
    def mwis(mask):
        counters["states_evaluated"] += 1
        count = counters["states_evaluated"]
        if count > max_states:
            raise OracleBudgetExceeded("state limit")
        # Check every 64 cache misses and on the first; bounded tiny overrun is possible.
        if (count == 1 or count % 64 == 0) and time.perf_counter() >= deadline:
            raise OracleBudgetExceeded("time limit")
        if mask == 0:
            return 0, 0
        remaining, isolates, isolated_weight = mask, 0, 0
        pivot, max_degree = None, -1
        while remaining:
            bit = remaining & -remaining
            vertex = bit.bit_length() - 1
            degree = (adjacency[vertex] & mask).bit_count()
            if degree == 0:
                isolates |= bit
                isolated_weight += weights[vertex]
            elif degree > max_degree:
                max_degree, pivot = degree, vertex
            remaining ^= bit
        if isolates:
            counters["isolate_states"] += 1
            value, independent_set = mwis(mask ^ isolates)
            return value + isolated_weight, independent_set | isolates
        counters["branch_states"] += 1
        bit = 1 << pivot
        skipped_value, skipped_set = mwis(mask ^ bit)
        taken_value, taken_set = mwis(mask & ~(adjacency[pivot] | bit))
        taken_value += weights[pivot]
        if taken_value >= skipped_value:
            return taken_value, taken_set | bit
        return skipped_value, skipped_set

    base = {"id": instance.get("id"), "family": "vertex_cover", "n": n,
            "split": instance.get("split"), "seed": instance.get("seed"),
            "input_sha256": instance_hash(instance), "time_limit_seconds": time_limit,
            "max_states": max_states, "algorithm": "exact memoized bitmask MWIS recurrence"}
    try:
        independent_weight, independent_bits = mwis((1 << n) - 1)
        assignment = [int(not (independent_bits & (1 << v))) for v in range(n)]
        checked = validate_assignment(instance, assignment)
        objective = sum(weights) - independent_weight
        if not checked["valid"] or checked["objective"] != objective:
            raise AssertionError("independent recurrence produced an invalid cover witness")
        base.update(status="optimal", objective=objective, assignment=assignment,
                    independent_set=[v for v in range(n) if independent_bits & (1 << v)],
                    independent_set_weight=independent_weight,
                    witness_validated=True, optimality_method="completed exact recurrence")
    except OracleBudgetExceeded as exc:
        base.update(status="unknown", reason=str(exc), witness_validated=False)
    finally:
        info = mwis.cache_info()
        base.update(counters, cache_hits=info.hits, cache_misses=info.misses,
                    cached_states=info.currsize, elapsed_seconds=time.perf_counter() - started)
        mwis.cache_clear()
    return base


def crosscheck_tiny(manifest, directory, time_limit):
    """Compare two independent exact algorithms, then check returned witnesses."""
    checked_ids = []
    for item in manifest["instances"]:
        if item["family"] != "vertex_cover" or item["split"] not in ("tiny", "control"):
            continue
        instance = json.loads((directory / item["json"]).read_text())
        recurrence = exact_vertex_cover(instance, time_limit=time_limit)
        exhaustive = exact_solve(instance)
        if recurrence["status"] != "optimal" or exhaustive["status"] != "optimal":
            raise AssertionError(f"tiny oracle did not complete: {item['id']}")
        if recurrence["objective"] != exhaustive["objective"]:
            raise AssertionError(f"oracle objective mismatch: {item['id']}")
        checked_ids.append(item["id"])
    # Include isolated vertices, which test the recurrence's reduction explicitly.
    isolates = {"family": "vertex_cover", "n": 4, "weights": [2, 5, 7, 11], "edges": [[0, 1]]}
    if exact_vertex_cover(isolates, time_limit=time_limit)["objective"] != 2:
        raise AssertionError("isolated-vertex reduction failed")
    return {"status": "passed", "exhaustive_comparisons": len(checked_ids),
            "instance_ids": checked_ids, "additional_isolated_vertex_check": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parent / "manifest.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--max-states", type=int, default=2_000_000)
    args = parser.parse_args()
    if args.time_limit <= 0 or args.max_states < 1:
        parser.error("time-limit and max-states must be positive")
    directory = args.manifest.resolve().parent
    output = args.output or directory / "results" / "wvc-certificates.json"
    manifest = json.loads(args.manifest.read_text())
    checks = crosscheck_tiny(manifest, directory, args.time_limit)
    results = []
    for item in manifest["instances"]:
        if item["family"] != "vertex_cover" or item["split"] not in ("dev", "test"):
            continue
        instance = json.loads((directory / item["json"]).read_text())
        result = exact_vertex_cover(instance, args.time_limit, args.max_states)
        results.append(result)
        print(json.dumps({key: result.get(key) for key in
                          ("id", "status", "objective", "states_evaluated", "elapsed_seconds")}), flush=True)
    payload = {"schema_version": 1, "algorithm": "weighted vertex cover via exact bitmask MWIS",
               "notes": ["Independent algorithm; no Gecode calls.",
                         "These are independently computed exact references, not a formal proof log.",
                         "Input hashes cover only family,n,weights,edges with canonical compact sorted-key JSON.",
                         "Oracle timings are diagnostic only and are excluded from solver speed comparisons."],
               "tiny_crosschecks": checks, "results": results,
               "completed": sum(r["status"] == "optimal" for r in results), "attempted": len(results)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "completed": payload["completed"],
                      "attempted": payload["attempted"], "tiny_crosschecks": checks["exhaustive_comparisons"]}), flush=True)
    return 0 if payload["completed"] == payload["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

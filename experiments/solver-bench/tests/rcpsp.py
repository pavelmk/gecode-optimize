#!/usr/bin/env python3
"""Tiny independent checks for cumulative semantics and RCPSP metadata."""
import copy
import itertools
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_rcpsp as r


def require(condition, text):
    if not condition: raise AssertionError(text)


def main():
    # Compare event-based resource checking with an independent time-slot oracle.
    p = {"family": "native_rcpsp", "size": 3, "n": 3, "machines": 2,
         "data": {"capacities": [3, 2], "tasks": [[2, 2, 1], [1, 1, 2], [2, 2, 1]],
                  "precedences": [[0, 2]]}}
    best = 100
    for starts in itertools.product(range(6), repeat=3):
        tasks = p["data"]["tasks"]
        feasible = starts[0] + 2 <= starts[2]
        for at in range(8):
            for resource, cap in enumerate(p["data"]["capacities"]):
                load = sum(task[resource + 1] for start, task in zip(starts, tasks) if start <= at < start + task[0])
                feasible = feasible and load <= cap
        checked = r.validate_assignment(p, list(starts))
        require(checked["valid"] == feasible, "event and time-slot feasibility differ")
        if feasible: best = min(best, checked["objective"])
    require(r.lower_bound(p) <= best, "independent lower bound exceeds exact tiny optimum")
    for change in ("cycle", "negative-demand", "oversized-demand", "duplicate"):
        bad = copy.deepcopy(p)
        if change == "cycle": bad["data"]["precedences"].append([2, 0])
        if change == "duplicate": bad["data"]["precedences"].append([0, 2])
        if change == "negative-demand": bad["data"]["tasks"][0][1] = -1
        if change == "oversized-demand": bad["data"]["tasks"][0][1] = 4
        try: r.check_instance(bad)
        except ValueError: pass
        else: raise AssertionError("invalid resource/precedence data accepted")
    for tier in ("small", "large"):
        for seed in range(8):
            p = r.make(tier, seed)
            result = {"status": "feasible", "assignment": p["incumbent"], "objective": p["incumbent_objective"]}
            require(r.validate_result(p, result)["valid"], "generated serial schedule invalid")
            require(r.mathematical_hash(p) == p["reference"]["input_sha256"], "stale generated reference")
            for key in ("capacities", "tasks", "precedences"):
                changed = copy.deepcopy(p)
                if key == "capacities": changed["data"][key][0] += 1
                elif key == "tasks": changed["data"][key][0][0] += 1
                else: changed["data"][key] = [] if p["data"][key] else [[0, 1]]
                require(r.mathematical_hash(changed) != r.mathematical_hash(p), "mathematical data omitted from hash")
            result["status"] = "optimal"
            checked = r.validate_result(p, result)
            if p["reference"]["status"] == "unknown":
                require(checked["valid"] and not checked["claims_verified"], "unknown optimum was independently certified")
    print("PASS RCPSP 216 tiny schedules, 16 generated witnesses, resource/precedence validation, complete hashes, unknown-reference handling")


if __name__ == "__main__": main()

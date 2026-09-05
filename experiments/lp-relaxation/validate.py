#!/usr/bin/env python3
"""Independent validation and exact references for binary min c*x, A*x >= b.

All implementations use only Python's standard library and never invoke Gecode
or an LP solver. Reference hashes cover the original mathematical input only.
"""
from __future__ import annotations

import argparse
from collections import deque
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path
import time


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_instance(instance):
    n, c, rows = instance.get("n"), instance.get("c"), instance.get("rows")
    if not integer(n) or n < 1:
        raise ValueError("n must be a positive integer")
    if not isinstance(c, list) or len(c) != n or any(not integer(v) for v in c):
        raise ValueError("c must contain n integer objective coefficients")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    for row in rows:
        if not integer(row.get("b")) or not isinstance(row.get("a"), list):
            raise ValueError("each row needs integer b and sparse coefficient list a")
        previous = -1
        for pair in row["a"]:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("sparse coefficient entries must be [index, coefficient]")
            j, coefficient = pair
            if not integer(j) or not previous < j < n or not integer(coefficient) or coefficient == 0:
                raise ValueError("row indices must be unique/sorted/in range; coefficients nonzero integers")
            previous = j


def input_hash(instance):
    data = {key: instance[key] for key in ("n", "c", "rows")}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_assignment(instance, assignment):
    check_instance(instance)
    if not isinstance(assignment, list) or len(assignment) != instance["n"]:
        return {"valid": False, "error": "assignment must contain n binary integers"}
    if any(not integer(v) or v not in (0, 1) for v in assignment):
        return {"valid": False, "error": "assignment values must be integer 0 or 1"}
    for i, row in enumerate(instance["rows"]):
        lhs = sum(coefficient * assignment[j] for j, coefficient in row["a"])
        if lhs < row["b"]:
            return {"valid": False, "error": f"row {i} violated", "lhs": lhs, "rhs": row["b"]}
    return {"valid": True, "objective": sum(c * x for c, x in zip(instance["c"], assignment))}


class BudgetExceeded(Exception):
    pass


def exact_reference(instance, max_states=5_000_000, time_limit=10.0, exhaustive=False):
    """Exact tiny enumeration, set-cover subset DP, knapsack DP or bipartite mincut.

    These references are exact algorithm results with witnesses, not formal proof
    logs. Unsupported larger inputs and budget exhaustion return unknown.
    """
    check_instance(instance)
    started = time.perf_counter()
    deadline = started + time_limit
    count = 0
    method = "exhaustive enumeration"

    def tick(amount=1):
        nonlocal count
        count += amount
        if count > max_states:
            raise BudgetExceeded("state budget")
        if time.perf_counter() > deadline:
            raise BudgetExceeded("time budget")

    def enumerate_binary():
        nonlocal method
        method = "exhaustive enumeration"
        n = instance["n"]
        if 2 ** n > max_states:
            raise BudgetExceeded("enumeration state budget")
        best, witness = math.inf, None
        for i, assignment in enumerate(itertools.product((0, 1), repeat=n)):
            if i % 256 == 0:
                tick(min(256, 2 ** n - i))
            objective = sum(c * x for c, x in zip(instance["c"], assignment))
            if objective >= best:
                continue
            if all(sum(a * assignment[j] for j, a in row["a"]) >= row["b"] for row in instance["rows"]):
                best, witness = objective, list(assignment)
        return best, witness

    def set_cover():
        nonlocal method
        method = "exact DP over remaining covered-element subsets"
        if any(c < 0 for c in instance["c"]) or any(row["b"] != 1 or any(a != 1 for _, a in row["a"])
                                                          for row in instance["rows"]):
            return enumerate_binary()
        covers = [0] * instance["n"]
        providers = []
        for i, row in enumerate(instance["rows"]):
            providers.append([j for j, _ in row["a"]])
            for j, _ in row["a"]:
                covers[j] |= 1 << i

        @lru_cache(maxsize=None)
        def solve(remaining):
            tick()
            if not remaining:
                return 0, 0
            elements = [i for i in range(len(providers)) if remaining & (1 << i)]
            element = min(elements, key=lambda i: len(providers[i]))
            best, selected = math.inf, 0
            for j in providers[element]:
                value, subset = solve(remaining & ~covers[j])
                value += instance["c"][j]
                if value < best:
                    best, selected = value, subset | (1 << j)
            return best, selected

        value, selected = solve((1 << len(providers)) - 1)
        if math.isinf(value):
            return value, None
        return value, [int(bool(selected & (1 << j))) for j in range(instance["n"])]

    def knapsack():
        nonlocal method
        method = "exact two-capacity zero-one knapsack dynamic program"
        rows = instance["rows"]
        if (len(rows) != 2 or any(c > 0 for c in instance["c"])
                or any(row["b"] > 0 or any(a > 0 for _, a in row["a"]) for row in rows)):
            return enumerate_binary()
        cap1, cap2 = -rows[0]["b"], -rows[1]["b"]
        w1, w2 = [0] * instance["n"], [0] * instance["n"]
        for j, a in rows[0]["a"]:
            w1[j] = -a
        for j, a in rows[1]["a"]:
            w2[j] = -a
        size = (cap1 + 1) * (cap2 + 1)
        if size > max_states:
            raise BudgetExceeded("capacity table budget")
        values, selections = [0] * size, [0] * size
        width = cap2 + 1
        for j, cost in enumerate(instance["c"]):
            tick(max(0, cap1 - w1[j] + 1) * max(0, cap2 - w2[j] + 1))
            for capacity1 in range(cap1, w1[j] - 1, -1):
                base, source = capacity1 * width, (capacity1 - w1[j]) * width
                for capacity2 in range(cap2, w2[j] - 1, -1):
                    target, previous = base + capacity2, source + capacity2 - w2[j]
                    candidate = values[previous] - cost
                    if candidate > values[target]:
                        values[target] = candidate
                        selections[target] = selections[previous] | (1 << j)
        selected = selections[-1]
        return -values[-1], [int(bool(selected & (1 << j))) for j in range(instance["n"])]

    def bipartite_cover():
        nonlocal method
        method = "exact integral-capacity maxflow/mincut for weighted bipartite cover"
        n = instance["n"]
        if any(c < 0 for c in instance["c"]):
            return enumerate_binary()
        adjacency = [[] for _ in range(n)]
        for row in instance["rows"]:
            if row["b"] != 1 or len(row["a"]) != 2 or any(a != 1 for _, a in row["a"]):
                return enumerate_binary()
            u, v = (j for j, _ in row["a"])
            adjacency[u].append(v)
            adjacency[v].append(u)
        colors = [-1] * n
        for start in range(n):
            if colors[start] >= 0:
                continue
            colors[start] = 0
            queue = deque([start])
            while queue:
                u = queue.popleft()
                for v in adjacency[u]:
                    if colors[v] == -1:
                        colors[v] = 1 - colors[u]
                        queue.append(v)
                    elif colors[v] == colors[u]:
                        return enumerate_binary()
        source, sink = n, n + 1
        graph = [[] for _ in range(n + 2)]

        def add_edge(u, v, capacity):
            graph[u].append([v, capacity, len(graph[v])])
            graph[v].append([u, 0, len(graph[u]) - 1])

        infinity = sum(instance["c"]) + 1
        for u in range(n):
            if colors[u] == 0:
                add_edge(source, u, instance["c"][u])
                for v in adjacency[u]:
                    add_edge(u, v, infinity)
            else:
                add_edge(u, sink, instance["c"][u])
        flow = 0
        while True:
            tick()
            level = [-1] * len(graph)
            level[source] = 0
            queue = deque([source])
            while queue:
                u = queue.popleft()
                for v, capacity, _ in graph[u]:
                    if capacity and level[v] < 0:
                        level[v] = level[u] + 1
                        queue.append(v)
            if level[sink] < 0:
                break
            positions = [0] * len(graph)

            def push(u, limit):
                if u == sink:
                    return limit
                while positions[u] < len(graph[u]):
                    edge = graph[u][positions[u]]
                    v, capacity, reverse = edge
                    if capacity and level[v] == level[u] + 1:
                        sent = push(v, min(limit, capacity))
                        if sent:
                            edge[1] -= sent
                            graph[v][reverse][1] += sent
                            return sent
                    positions[u] += 1
                return 0

            while True:
                sent = push(source, infinity)
                if not sent:
                    break
                flow += sent
                tick()
        reachable = {source}
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v, capacity, _ in graph[u]:
                if capacity and v not in reachable:
                    reachable.add(v)
                    queue.append(v)
        selected = [int((colors[u] == 0 and u not in reachable) or (colors[u] == 1 and u in reachable))
                    for u in range(n)]
        return flow, selected

    try:
        if exhaustive:
            value, assignment = enumerate_binary()
        elif instance.get("family") == "set_cover":
            value, assignment = set_cover()
        elif instance.get("family") == "knapsack":
            value, assignment = knapsack()
        elif instance.get("family") == "bipartite_cover":
            value, assignment = bipartite_cover()
        else:
            value, assignment = enumerate_binary()
        if assignment is None:
            result = {"status": "infeasible"}
        else:
            checked = validate_assignment(instance, assignment)
            if not checked["valid"] or checked["objective"] != value:
                raise AssertionError("exact algorithm returned an invalid witness/objective")
            result = {"status": "optimal", "objective": value, "assignment": assignment}
    except BudgetExceeded as exc:
        result = {"status": "unknown", "reason": str(exc)}
    result.update(input_sha256=input_hash(instance), method=method, states_evaluated=count)
    return result


def validate_result(instance, result):
    check_instance(instance)
    status = result.get("status")
    if status not in ("feasible", "optimal", "infeasible", "unknown"):
        return {"valid": False, "error": "unrecognized status"}
    reference = instance.get("reference", {})
    if reference and reference.get("input_sha256") != input_hash(instance):
        return {"valid": False, "error": "stale reference hash"}
    if status == "infeasible":
        if result.get("assignment") not in (None, []):
            return {"valid": False, "error": "infeasible result has an assignment"}
        if reference.get("status") == "optimal":
            return {"valid": False, "error": "infeasibility contradicts exact feasible reference"}
        verified = reference.get("status") == "infeasible"
        return {"valid": True, "claims_verified": verified, "infeasibility_verified": verified}
    if status == "unknown" and result.get("assignment") in (None, []):
        return {"valid": True, "claims_verified": True, "solution_checked": False}
    checked = validate_assignment(instance, result.get("assignment"))
    if not checked["valid"]:
        return checked
    if "objective" in result and (not integer(result["objective"]) or result["objective"] != checked["objective"]):
        return {"valid": False, "error": "reported objective differs from recomputed objective"}
    if reference.get("status") == "infeasible":
        return {"valid": False, "error": "assignment contradicts exact infeasibility reference"}
    verified = False
    if reference.get("status") == "optimal":
        if checked["objective"] < reference["objective"]:
            return {"valid": False, "error": "objective beats exact reference"}
        verified = checked["objective"] == reference["objective"]
        if status == "optimal" and not verified:
            return {"valid": False, "error": "claimed optimum differs from exact reference"}
    checked.update(solution_checked=True, optimality_verified=verified,
                   claims_verified=status != "optimal" or verified)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("result", type=Path, nargs="?")
    parser.add_argument("--certify", action="store_true")
    parser.add_argument("--exhaustive", action="store_true")
    parser.add_argument("--max-states", type=int, default=5_000_000)
    parser.add_argument("--time-limit", type=float, default=10)
    args = parser.parse_args()
    try:
        instance = json.loads(args.instance.read_text())
        if args.certify or args.exhaustive:
            output = exact_reference(instance, args.max_states, args.time_limit, args.exhaustive)
        elif args.result:
            output = validate_result(instance, json.loads(args.result.read_text()))
        else:
            check_instance(instance)
            output = {"valid": True, "input_sha256": input_hash(instance)}
        print(json.dumps(output, sort_keys=True))
        return 0 if output.get("valid", True) else 1
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

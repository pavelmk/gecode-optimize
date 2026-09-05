#!/usr/bin/env python3
"""Independent mathematical/domain validators for the broad binary-linear suite."""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def input_hash(instance):
    data = {key: instance[key] for key in ("n", "c", "rows")}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_instance(instance):
    n, costs, rows = instance.get("n"), instance.get("c"), instance.get("rows")
    if not integer(n) or n < 1:
        raise ValueError("n must be a positive integer")
    if not isinstance(costs, list) or len(costs) != n or any(not integer(c) for c in costs):
        raise ValueError("c must contain n integer coefficients")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    for row in rows:
        if not integer(row.get("b")) or not isinstance(row.get("a"), list):
            raise ValueError("each row needs integer b and sparse a")
        previous = -1
        for pair in row["a"]:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError("coefficient entry must be [index,value]")
            j, value = pair
            if not integer(j) or not previous < j < n or not integer(value) or value == 0:
                raise ValueError("row indices must be sorted unique/in range; values nonzero integers")
            previous = j


def linear_check(instance, assignment):
    if len(assignment) != instance["n"] or any(not integer(x) or x not in (0, 1) for x in assignment):
        return False, None
    feasible = all(sum(value * assignment[j] for j, value in row["a"]) >= row["b"] for row in instance["rows"])
    return feasible, sum(c * x for c, x in zip(instance["c"], assignment))


def domain_check(instance, x):
    """Check original domain meaning independently of generated sparse rows.

    Returns (feasible, objective), or None for external models with no known
    domain. Stated color/bin prefix and TSP-start symmetry restrictions are
    included so tiny tests can compare encoded and domain feasibility exactly.
    """
    p, family = instance.get("parameters"), instance.get("family")
    if p is None:
        return None
    n = instance["n"]
    if len(x) != n or any(not integer(v) or v not in (0, 1) for v in x):
        return False, None
    if family in ("set_cover", "multicover"):
        coverage = [0] * len(p["demands"])
        for j, chosen in enumerate(x):
            if chosen:
                for item in p["sets"][j]:
                    coverage[item] += 1
        return all(a >= b for a, b in zip(coverage, p["demands"])), sum(c * v for c, v in zip(p["costs"], x))
    if family in ("set_packing", "auction"):
        used = [0] * p["items"]
        for j, chosen in enumerate(x):
            if chosen:
                for item in p["bundles"][j]:
                    used[item] += 1
        return all(v <= 1 for v in used), -sum(profit * v for profit, v in zip(p["profits"], x))
    if family in ("knapsack", "multidimensional_knapsack"):
        ok = all(sum(w * v for w, v in zip(weights, x)) <= cap
                 for weights, cap in zip(p["weights"], p["capacities"]))
        return ok, -sum(profit * v for profit, v in zip(p["profits"], x))
    if family == "vertex_cover":
        return all(x[u] or x[v] for u, v in p["edges"]), sum(w * v for w, v in zip(p["weights"], x))
    if family == "independent_set":
        return all(not (x[u] and x[v]) for u, v in p["edges"]), -sum(w * v for w, v in zip(p["weights"], x))
    if family == "maxcut":
        v = p["vertices"]
        ok = all(x[v + i] == int(x[u] != x[w]) for i, (u, w) in enumerate(p["edges"]))
        return ok, -sum(weight * int(x[u] != x[w]) for weight, (u, w) in zip(p["weights"], p["edges"]))
    if family in ("facility_location", "pmedian"):
        f, customers = p["facilities"], p["customers"]
        opened = x[:f]
        ok = family != "pmedian" or sum(opened) == p["p"]
        cost = sum(c * v for c, v in zip(p["opening_costs"], opened))
        for customer in range(customers):
            choices = x[f + customer * f:f + (customer + 1) * f]
            ok = ok and sum(choices) == 1 and all(not choices[j] or opened[j] for j in range(f))
            cost += sum(c * v for c, v in zip(p["assignment_costs"][customer], choices))
        return ok, cost
    if family == "assignment":
        q = p["size"]
        ok = all(sum(x[i * q:(i + 1) * q]) == 1 for i in range(q))
        ok = ok and all(sum(x[i * q + j] for i in range(q)) == 1 for j in range(q))
        return ok, sum(p["costs"][i][j] * x[i * q + j] for i in range(q) for j in range(q))
    if family == "generalized_assignment":
        jobs, machines = p["jobs"], p["machines"]
        ok = all(sum(x[j * machines:(j + 1) * machines]) == 1 for j in range(jobs))
        ok = ok and all(sum(p["resources"][j][m] * x[j * machines + m] for j in range(jobs)) <= p["capacities"][m]
                        for m in range(machines))
        cost = sum(p["costs"][j][m] * x[j * machines + m] for j in range(jobs) for m in range(machines))
        return ok, cost
    if family == "bin_packing":
        items, bins = p["items"], p["bins"]
        opened = x[items * bins:]
        ok = all(sum(x[j * bins:(j + 1) * bins]) == 1 for j in range(items))
        for b in range(bins):
            load = sum(p["weights"][j] * x[j * bins + b] for j in range(items))
            ok = ok and load <= p["capacity"] * opened[b]
            ok = ok and all(not x[j * bins + b] or opened[b] for j in range(items))
        ok = ok and all(opened[b] >= opened[b + 1] for b in range(bins - 1))
        return ok, sum(opened)
    if family == "coloring":
        vertices, colors = p["vertices"], p["colors"]
        enabled = x[vertices * colors:]
        ok = all(sum(x[v * colors:(v + 1) * colors]) == 1 for v in range(vertices))
        ok = ok and all(not x[v * colors + c] or enabled[c] for v in range(vertices) for c in range(colors))
        ok = ok and all(not (x[u * colors + c] and x[v * colors + c]) for u, v in p["edges"] for c in range(colors))
        ok = ok and all(enabled[c] >= enabled[c + 1] for c in range(colors - 1))
        return ok, sum(enabled)
    if family == "tsp":
        cities = p["cities"]
        positions = []
        ok = all(sum(x[v * cities:(v + 1) * cities]) == 1 for v in range(cities))
        for t in range(cities):
            cities_at_t = [v for v in range(cities) if x[v * cities + t]]
            if len(cities_at_t) != 1:
                return False, None
            positions.append(cities_at_t[0])
        ok = ok and positions[0] == 0 and len(set(positions)) == cities
        tour_arcs = {(positions[t], positions[(t + 1) % cities]) for t in range(cities)}
        ok = ok and all(x[cities * cities + i] == int((u, v) in tour_arcs) for i, (u, v) in enumerate(p["arcs"]))
        return ok, sum(p["distances"][u][v] for u, v in tour_arcs)
    if family == "rostering":
        employees, days, shifts = p["employees"], p["days"], p["shifts"]
        get = lambda e, d, s: x[(e * days + d) * shifts + s]
        ok = all(sum(get(e, d, s) for s in range(shifts)) <= 1 for e in range(employees) for d in range(days))
        ok = ok and all(sum(get(e, d, s) for e in range(employees)) >= p["requirements"][d][s]
                        for d in range(days) for s in range(shifts))
        ok = ok and all(sum(get(e, d, s) for d in range(days) for s in range(shifts)) <= p["max_days"]
                        for e in range(employees))
        ok = ok and all(sum(get(e, d, s) for d in range(start, start + 3) for s in range(shifts)) <= 2
                        for e in range(employees) for start in range(days - 2))
        ok = ok and all(get(e, d, shifts - 1) + get(e, d + 1, 0) <= 1 for e in range(employees) for d in range(days - 1))
        ok = ok and all(not x[j] or p["available"][j] for j in range(n))
        return ok, sum(cost * v for cost, v in zip(p["costs"], x))
    if family == "production":
        periods, options = p["periods"], p["options"]
        inventory, physical_cost = 0, 0
        for t in range(periods):
            chosen = [q for q in range(options) if x[t * options + q]]
            if len(chosen) != 1:
                return False, None
            quantity = chosen[0]
            inventory += quantity - p["demands"][t]
            if not 0 <= inventory <= p["storage"]:
                return False, None
            physical_cost += p["production_costs"][t][quantity] + p["holding_cost"] * inventory
        return inventory == 0, physical_cost - p["objective_constant"]
    return None


def validate_assignment(instance, assignment):
    check_instance(instance)
    if not isinstance(assignment, list):
        return {"valid": False, "error": "assignment must be a binary integer list"}
    valid, objective = linear_check(instance, assignment)
    if not valid:
        return {"valid": False, "error": "binary domain or original linear constraint violated"}
    domain = domain_check(instance, assignment)
    if domain is not None and (not domain[0] or domain[1] != objective):
        return {"valid": False, "error": "domain semantics/objective disagrees with sparse formulation"}
    return {"valid": True, "objective": objective, "domain_semantics_checked": domain is not None}


def validate_result(instance, result, external_reference=None):
    check_instance(instance)
    reference = external_reference if external_reference is not None else instance.get("reference", {})
    if reference and reference.get("input_sha256") != input_hash(instance):
        return {"valid": False, "error": "stale reference hash"}
    status = result.get("status")
    if status not in ("optimal", "feasible", "infeasible", "unknown"):
        return {"valid": False, "error": "invalid result status"}
    if status == "infeasible":
        if result.get("assignment") not in (None, []):
            return {"valid": False, "error": "infeasible result carries an assignment"}
        if reference.get("status") in ("optimal", "feasible") or "incumbent" in instance:
            return {"valid": False, "error": "infeasibility contradicts an original-instance feasible witness"}
        verified = reference.get("status") == "infeasible"
        return {"valid": True, "claims_verified": verified, "infeasibility_verified": verified}
    if status == "unknown" and result.get("assignment") in (None, []):
        return {"valid": True, "claims_verified": True, "solution_checked": False}
    checked = validate_assignment(instance, result.get("assignment"))
    if not checked["valid"]:
        return checked
    if "objective" in result and (not integer(result["objective"]) or result["objective"] != checked["objective"]):
        return {"valid": False, "error": "reported objective differs from recomputed value"}
    verified = False
    if reference.get("status") == "optimal":
        if checked["objective"] < reference["objective"]:
            return {"valid": False, "error": "reported objective beats exact reference"}
        verified = checked["objective"] == reference["objective"]
        if status == "optimal" and not verified:
            return {"valid": False, "error": "claimed optimum differs from exact reference"}
    if reference.get("status") == "infeasible":
        return {"valid": False, "error": "feasible result contradicts exact infeasibility reference"}
    checked.update(solution_checked=True, optimality_verified=verified,
                   claims_verified=status != "optimal" or verified)
    return checked


def exact_reference(instance, max_states=1_000_000, force_enumeration=False):
    """Return an exact reference where a modest independent oracle is available.

    No general solver is invoked. All other cases explicitly return unknown.
    """
    check_instance(instance)
    n, p, family = instance["n"], instance.get("parameters", {}), instance.get("family")
    result = {"status": "unknown", "reason": "no inexpensive independent exact oracle for this case",
              "input_sha256": input_hash(instance)}
    witness, best, method = None, math.inf, None
    if force_enumeration or n <= 18:
        if 2 ** n > max_states:
            return dict(result, reason="enumeration budget")
        for assignment in itertools.product((0, 1), repeat=n):
            objective = sum(c * x for c, x in zip(instance["c"], assignment))
            if objective < best and all(sum(a * assignment[j] for j, a in row["a"]) >= row["b"] for row in instance["rows"]):
                best, witness = objective, list(assignment)
        method = "exhaustive binary enumeration"
        if witness is None:
            return dict(result, status="infeasible", method=method)
    elif family == "knapsack":
        capacity, weights = p["capacities"][0], p["weights"][0]
        if n * (capacity + 1) > max_states:
            return dict(result, reason="knapsack DP budget")
        values, masks = [0] * (capacity + 1), [0] * (capacity + 1)
        for j, (weight, profit) in enumerate(zip(weights, p["profits"])):
            for cap in range(capacity, weight - 1, -1):
                value = values[cap - weight] + profit
                if value > values[cap]:
                    values[cap], masks[cap] = value, masks[cap - weight] | (1 << j)
        witness = [int(bool(masks[-1] & (1 << j))) for j in range(n)]
        best, method = -values[-1], "one-dimensional zero-one knapsack DP"
    elif family == "assignment":
        q = p["size"]
        @lru_cache(maxsize=None)
        def matching(mask):
            worker = mask.bit_count()
            if worker == q:
                return 0, ()
            choices = []
            for job in range(q):
                if not mask & (1 << job):
                    value, tail = matching(mask | (1 << job))
                    choices.append((value + p["costs"][worker][job], (job,) + tail))
            return min(choices)
        best, assignment = matching(0)
        witness = [int(assignment[i] == j) for i in range(q) for j in range(q)]
        method = "subset dynamic program for bipartite assignment"
    elif family in ("facility_location", "pmedian"):
        f = p["facilities"]
        for mask in range(1, 1 << f):
            selected = [j for j in range(f) if mask & (1 << j)]
            if family == "pmedian" and len(selected) != p["p"]:
                continue
            assignments = [min(selected, key=lambda j: (costs[j], j)) for costs in p["assignment_costs"]]
            value = sum(p["opening_costs"][j] for j in selected)
            value += sum(p["assignment_costs"][i][j] for i, j in enumerate(assignments))
            if value < best:
                best = value
                witness = [int(j in selected) for j in range(f)]
                witness += [int(assignments[i] == j) for i in range(p["customers"]) for j in range(f)]
        method = "enumerate facility subsets and independently assign each customer"
    elif family == "tsp":
        cities = p["cities"]
        @lru_cache(maxsize=None)
        def tour(last, remaining):
            if not remaining:
                return p["distances"][last][0], ()
            values = []
            for v in range(1, cities):
                if remaining & (1 << v):
                    value, tail = tour(v, remaining ^ (1 << v))
                    values.append((p["distances"][last][v] + value, (v,) + tail))
            return min(values)
        best, rest = tour(0, ((1 << cities) - 1) ^ 1)
        order = (0,) + rest
        arcs = {(order[t], order[(t + 1) % cities]) for t in range(cities)}
        witness = [int(order[t] == v) for v in range(cities) for t in range(cities)]
        witness += [int((u, v) in arcs) for u, v in p["arcs"]]
        method = "Held-Karp subset dynamic program"
    elif family == "production":
        @lru_cache(maxsize=None)
        def production(t, inventory):
            if t == p["periods"]:
                return (0, ()) if inventory == 0 else (math.inf, ())
            best_local, schedule = math.inf, ()
            for quantity in range(p["options"]):
                following = inventory + quantity - p["demands"][t]
                if 0 <= following <= p["storage"]:
                    value, tail = production(t + 1, following)
                    value += instance["c"][t * p["options"] + quantity]
                    if value < best_local:
                        best_local, schedule = value, (quantity,) + tail
            return best_local, schedule
        best, schedule = production(0, 0)
        witness = [int(schedule[t] == q) for t in range(p["periods"]) for q in range(p["options"])]
        method = "inventory-state production dynamic program"
    elif family == "bin_packing":
        lower_bound = (sum(p["weights"]) + p["capacity"] - 1) // p["capacity"]
        incumbent = instance.get("incumbent")
        if incumbent and sum(incumbent[p["items"] * p["bins"]:]) == lower_bound:
            witness, best, method = list(incumbent), lower_bound, "feasible witness meets total-weight capacity lower bound"
    if witness is not None:
        checked = validate_assignment(instance, witness)
        if not checked["valid"] or checked["objective"] != best:
            raise AssertionError((instance.get("id"), "independent oracle failed domain validation", checked))
        return {"status": "optimal", "objective": best, "assignment": witness,
                "method": method, "input_sha256": input_hash(instance)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("result", type=Path, nargs="?")
    parser.add_argument("--reference", type=Path, help="one external reference object with matching input_sha256")
    parser.add_argument("--certify", action="store_true")
    parser.add_argument("--enumerate", action="store_true")
    parser.add_argument("--max-states", type=int, default=1_000_000)
    args = parser.parse_args()
    try:
        instance = json.loads(args.instance.read_text())
        if args.certify or args.enumerate:
            output = exact_reference(instance, args.max_states, args.enumerate)
        elif args.result:
            reference = json.loads(args.reference.read_text()) if args.reference else None
            output = validate_result(instance, json.loads(args.result.read_text()), reference)
        else:
            check_instance(instance)
            output = {"valid": True, "input_sha256": input_hash(instance)}
        print(json.dumps(output, sort_keys=True))
        return 0 if output.get("valid", True) else 1
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Eighteen reproducible binary-linear benchmark families with domain validators.

Default suite: 18 families x 2 sizes x (3 dev + 5 test) = 288 cases, plus
12 tiny controls. Generation never runs a solver or selects cases by performance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
import math
from pathlib import Path
import random
import time

from validate import (check_instance, domain_check, exact_reference, input_hash,
                      linear_check, validate_assignment, validate_result)


FAMILIES = ("set_cover", "multicover", "set_packing", "knapsack", "multidimensional_knapsack",
            "vertex_cover", "independent_set", "maxcut", "facility_location", "pmedian",
            "assignment", "generalized_assignment", "bin_packing", "coloring", "tsp", "auction",
            "rostering", "production")
TIERS = ("small", "large")


class Builder:
    def __init__(self, costs):
        self.c = list(costs)
        self.rows = []

    def ge(self, terms, rhs):
        coefficients = {}
        for j, value in terms:
            coefficients[j] = coefficients.get(j, 0) + value
        self.rows.append({"a": [[j, value] for j, value in sorted(coefficients.items()) if value], "b": rhs})

    def le(self, terms, rhs):
        self.ge([(j, -value) for j, value in terms], -rhs)

    def eq(self, terms, rhs):
        terms = list(terms)
        self.ge(terms, rhs)
        self.le(terms, rhs)

    def finish(self, parameters):
        return {"n": len(self.c), "c": self.c, "rows": self.rows, "parameters": parameters}


def dimension(tier, tiny, small, large):
    return tiny if tier == "tiny" else small if tier == "small" else large


def graph(rng, vertices, density):
    return [[u, v] for u in range(vertices) for v in range(u + 1, vertices) if rng.random() < density]


def first_fit(weights, capacity):
    loads, assignment = [], [0] * len(weights)
    for j in sorted(range(len(weights)), key=lambda i: (-weights[i], i)):
        available = next((b for b, load in enumerate(loads) if load + weights[j] <= capacity), len(loads))
        if available == len(loads):
            loads.append(0)
        loads[available] += weights[j]
        assignment[j] = available
    return assignment, loads


def make_model(family, tier, seed):
    rng = random.Random(seed)
    if family in ("set_cover", "multicover"):
        n = dimension(tier, 8, 40, 100 if family == "set_cover" else 90)
        elements = dimension(tier, 4, 16, 30 if family == "set_cover" else 28)
        demand = 1 if family == "set_cover" else dimension(tier, 2, 2, 3)
        costs = [rng.randint(1, 30) for _ in range(n)]
        sets = [set() for _ in range(n)]
        model = Builder(costs)
        for item in range(elements):
            providers = {j for j in range(n) if rng.random() < (0.22 if family == "set_cover" else 0.27)}
            if len(providers) < demand + 1:
                providers.update(rng.sample(range(n), demand + 1))
            for j in providers:
                sets[j].add(item)
            model.ge([(j, 1) for j in providers], demand)
        return model.finish({"sets": [sorted(s) for s in sets], "demands": [demand] * elements, "costs": costs})
    if family in ("set_packing", "auction"):
        n = dimension(tier, 8, 40, 100 if family == "set_packing" else 120)
        items = dimension(tier, 5, 20, 50 if family == "set_packing" else 35)
        bundles = [sorted(rng.sample(range(items), rng.randint(1, min(items, 5 if family == "auction" else 4)))) for _ in range(n)]
        item_values = [rng.randint(3, 15) for _ in range(items)]
        profits = ([rng.randint(5, 50) for _ in range(n)] if family == "set_packing" else
                   [sum(item_values[i] for i in bundle) + rng.randint(0, 15) for bundle in bundles])
        model = Builder([-v for v in profits])
        for item in range(items):
            model.le([(j, 1) for j, bundle in enumerate(bundles) if item in bundle], 1)
        return model.finish({"items": items, "bundles": bundles, "profits": profits})
    if family in ("knapsack", "multidimensional_knapsack"):
        n = dimension(tier, 10, 40, 80)
        resources = 1 if family == "knapsack" else dimension(tier, 3, 3, 5)
        weights = [[rng.randint(1, 30) for _ in range(n)] for _ in range(resources)]
        capacities = [max(max(w), math.ceil(sum(w) * 0.27)) for w in weights]
        profits = [rng.randint(1, 100) for _ in range(n)]
        model = Builder([-v for v in profits])
        for w, cap in zip(weights, capacities):
            model.le(list(enumerate(w)), cap)
        return model.finish({"weights": weights, "capacities": capacities, "profits": profits})
    if family in ("vertex_cover", "independent_set"):
        n = dimension(tier, 9, 40, 100)
        edges = graph(rng, n, 0.28 if tier == "tiny" else 0.13 if tier == "small" else 0.065)
        weights = [rng.randint(1, 30) for _ in range(n)]
        model = Builder(weights if family == "vertex_cover" else [-w for w in weights])
        for u, v in edges:
            if family == "vertex_cover":
                model.ge([(u, 1), (v, 1)], 1)
            else:
                model.le([(u, 1), (v, 1)], 1)
        return model.finish({"edges": edges, "weights": weights})
    if family == "maxcut":
        vertices = dimension(tier, 4, 14, 24)
        target_edges = dimension(tier, 5, 30, 90)
        edges = {tuple(sorted((v, (v + 1) % vertices))) for v in range(vertices)}
        candidates = list(itertools.combinations(range(vertices), 2))
        rng.shuffle(candidates)
        for edge in candidates:
            if len(edges) >= target_edges:
                break
            edges.add(edge)
        edges = sorted(edges)
        weights = [rng.randint(1, 20) for _ in edges]
        model = Builder([0] * vertices + [-w for w in weights])
        for i, (u, v) in enumerate(edges):
            z = vertices + i
            model.ge([(z, 1), (u, -1), (v, 1)], 0)
            model.ge([(z, 1), (u, 1), (v, -1)], 0)
            model.ge([(u, 1), (v, 1), (z, -1)], 0)
            model.ge([(u, -1), (v, -1), (z, -1)], -2)
        return model.finish({"vertices": vertices, "edges": [list(e) for e in edges], "weights": weights})
    if family in ("facility_location", "pmedian"):
        facilities = dimension(tier, 2 if family == "facility_location" else 3, 5, 8)
        customers = dimension(tier, 3, 6, 15)
        sites = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(facilities)]
        demands = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(customers)]
        assignment_costs = [[abs(a - x) + abs(b - y) + 1 for x, y in sites] for a, b in demands]
        opening = [rng.randint(15, 60) if family == "facility_location" else 0 for _ in range(facilities)]
        model = Builder(opening + [cost for row in assignment_costs for cost in row])
        for customer in range(customers):
            model.eq([(facilities + customer * facilities + j, 1) for j in range(facilities)], 1)
            for j in range(facilities):
                model.ge([(j, 1), (facilities + customer * facilities + j, -1)], 0)
        parameters = {"facilities": facilities, "customers": customers, "opening_costs": opening,
                      "assignment_costs": assignment_costs}
        if family == "pmedian":
            parameters["p"] = dimension(tier, 1, 2, 3)
            model.eq([(j, 1) for j in range(facilities)], parameters["p"])
        return model.finish(parameters)
    if family == "assignment":
        size = dimension(tier, 3, 6, 12)
        costs = [[rng.randint(1, 100) for _ in range(size)] for _ in range(size)]
        model = Builder([c for row in costs for c in row])
        for i in range(size):
            model.eq([(i * size + j, 1) for j in range(size)], 1)
        for j in range(size):
            model.eq([(i * size + j, 1) for i in range(size)], 1)
        return model.finish({"size": size, "costs": costs})
    if family == "generalized_assignment":
        jobs, machines = dimension(tier, 4, 12, 28), dimension(tier, 2, 3, 5)
        resources = [[rng.randint(1, 10) for _ in range(machines)] for _ in range(jobs)]
        costs = [[rng.randint(1, 70) for _ in range(machines)] for _ in range(jobs)]
        order = list(range(jobs)); rng.shuffle(order)
        planted = [0] * jobs
        for index, j in enumerate(order):
            planted[j] = index % machines
        capacities = [sum(resources[j][m] for j in range(jobs) if planted[j] == m) + rng.randint(0, 4)
                      for m in range(machines)]
        model = Builder([c for row in costs for c in row])
        for j in range(jobs):
            model.eq([(j * machines + m, 1) for m in range(machines)], 1)
        for m in range(machines):
            model.le([(j * machines + m, resources[j][m]) for j in range(jobs)], capacities[m])
        return model.finish({"jobs": jobs, "machines": machines, "resources": resources,
                             "costs": costs, "capacities": capacities, "planted_machines": planted})
    if family == "bin_packing":
        items, bins = dimension(tier, 4, 10, 20), dimension(tier, 3, 4, 6)
        weights = [rng.randint(2, 10) for _ in range(items)]
        capacity = max(max(weights), math.ceil(sum(weights) / (bins - 1)))
        while len(first_fit(weights, capacity)[1]) > bins:
            capacity += 1
        model = Builder([0] * (items * bins) + [1] * bins)
        for j in range(items):
            model.eq([(j * bins + b, 1) for b in range(bins)], 1)
            for b in range(bins):
                model.ge([(items * bins + b, 1), (j * bins + b, -1)], 0)
        for b in range(bins):
            model.ge([(items * bins + b, capacity)] + [(j * bins + b, -weights[j]) for j in range(items)], 0)
        for b in range(bins - 1):
            model.ge([(items * bins + b, 1), (items * bins + b + 1, -1)], 0)
        return model.finish({"items": items, "bins": bins, "weights": weights, "capacity": capacity,
                             "symmetry": "enabled bins form a prefix"})
    if family == "coloring":
        vertices, colors = dimension(tier, 4, 8, 20), dimension(tier, 3, 4, 6)
        planted = [v % colors for v in range(vertices)]; rng.shuffle(planted)
        edges = [[u, v] for u in range(vertices) for v in range(u + 1, vertices)
                 if planted[u] != planted[v] and rng.random() < (0.35 if tier != "large" else 0.30)]
        model = Builder([0] * (vertices * colors) + [1] * colors)
        for v in range(vertices):
            model.eq([(v * colors + c, 1) for c in range(colors)], 1)
            for c in range(colors):
                model.ge([(vertices * colors + c, 1), (v * colors + c, -1)], 0)
        for u, v in edges:
            for c in range(colors):
                model.le([(u * colors + c, 1), (v * colors + c, 1)], 1)
        for c in range(colors - 1):
            model.ge([(vertices * colors + c, 1), (vertices * colors + c + 1, -1)], 0)
        return model.finish({"vertices": vertices, "colors": colors, "edges": edges,
                             "planted_colors": planted, "symmetry": "enabled colors form a prefix"})
    if family == "tsp":
        cities = dimension(tier, 3, 5, 8)
        coordinates = [(rng.randint(0, 50), rng.randint(0, 50)) for _ in range(cities)]
        distances = [[0 if u == v else abs(coordinates[u][0] - coordinates[v][0])
                      + abs(coordinates[u][1] - coordinates[v][1]) + 1 for v in range(cities)] for u in range(cities)]
        arcs = [(u, v) for u in range(cities) for v in range(cities) if u != v]
        arc_index = {arc: cities * cities + i for i, arc in enumerate(arcs)}
        model = Builder([0] * (cities * cities) + [distances[u][v] for u, v in arcs])
        for v in range(cities):
            model.eq([(v * cities + t, 1) for t in range(cities)], 1)
            model.eq([(arc_index[(v, w)], 1) for w in range(cities) if w != v], 1)
            model.eq([(arc_index[(w, v)], 1) for w in range(cities) if w != v], 1)
        for t in range(cities):
            model.eq([(v * cities + t, 1) for v in range(cities)], 1)
        model.ge([(0, 1)], 1)
        for u, v in arcs:
            for t in range(cities):
                model.ge([(arc_index[(u, v)], 1), (u * cities + t, -1), (v * cities + (t + 1) % cities, -1)], -1)
        return model.finish({"cities": cities, "distances": distances, "arcs": [list(a) for a in arcs],
                             "symmetry": "city 0 occupies position 0"})
    if family == "rostering":
        employees, days, shifts = dimension(tier, 3, 5, 8), dimension(tier, 2, 4, 6), dimension(tier, 1, 2, 3)
        n = employees * days * shifts
        order = list(range(employees)); rng.shuffle(order)
        planted = [0] * n
        for d in range(days):
            for s in range(shifts):
                e = order[(d * shifts + s) % employees]
                planted[(e * days + d) * shifts + s] = 1
        available = [int(planted[j] or rng.random() >= 0.12) for j in range(n)]
        costs = [rng.randint(1, 20) + (5 if j % shifts == shifts - 1 else 0) for j in range(n)]
        max_days = math.ceil(days * shifts / employees) + 1
        requirements = [[1] * shifts for _ in range(days)]
        model = Builder(costs)
        index = lambda e, d, s: (e * days + d) * shifts + s
        for e in range(employees):
            for d in range(days):
                model.le([(index(e, d, s), 1) for s in range(shifts)], 1)
            model.le([(index(e, d, s), 1) for d in range(days) for s in range(shifts)], max_days)
            for start in range(days - 2):
                model.le([(index(e, d, s), 1) for d in range(start, start + 3) for s in range(shifts)], 2)
            for d in range(days - 1):
                model.le([(index(e, d, shifts - 1), 1), (index(e, d + 1, 0), 1)], 1)
        for d in range(days):
            for s in range(shifts):
                model.ge([(index(e, d, s), 1) for e in range(employees)], 1)
        for j in range(n):
            if not available[j]:
                model.le([(j, 1)], 0)
        return model.finish({"employees": employees, "days": days, "shifts": shifts,
                             "requirements": requirements, "max_days": max_days, "available": available,
                             "costs": costs, "planted_assignment": planted})
    if family == "production":
        periods, options = dimension(tier, 3, 4, 6), dimension(tier, 4, 10, 20)
        demands = [rng.randint(1, min(options - 1, 8)) for _ in range(periods)]
        storage, holding = rng.randint(3, 10), rng.randint(1, 4)
        costs = []
        for _ in range(periods):
            fixed, unit, normal = rng.randint(5, 20), rng.randint(2, 12), max(1, options // 2)
            costs.append([0 if q == 0 else fixed + unit * q + max(0, q - normal) * 5 for q in range(options)])
        coefficients = [costs[t][q] + holding * (periods - t) * q for t in range(periods) for q in range(options)]
        model = Builder(coefficients)
        for t in range(periods):
            model.eq([(t * options + q, 1) for q in range(options)], 1)
            prefix = [(s * options + q, q) for s in range(t + 1) for q in range(1, options)]
            demand = sum(demands[:t + 1])
            model.ge(prefix, demand)
            model.le(prefix, demand + storage)
        model.eq([(t * options + q, q) for t in range(periods) for q in range(1, options)], sum(demands))
        constant = -holding * sum(sum(demands[:t + 1]) for t in range(periods))
        return model.finish({"periods": periods, "options": options, "demands": demands, "storage": storage,
                             "holding_cost": holding, "production_costs": costs, "objective_constant": constant})
    raise ValueError(f"unknown family {family}")


def cover_greedy(instance):
    n = instance["n"]
    selected = [0] * n
    uncovered = [row["b"] for row in instance["rows"]]
    covers = [[] for _ in range(n)]
    for i, row in enumerate(instance["rows"]):
        for j, value in row["a"]:
            if value != 1:
                raise ValueError("cover incumbent expects positive unit coefficients")
            covers[j].append(i)
    while any(value > 0 for value in uncovered):
        choices = []
        for j in range(n):
            if not selected[j]:
                gain = sum(uncovered[i] > 0 for i in covers[j])
                if gain:
                    choices.append((instance["c"][j] / gain, instance["c"][j], j))
        if not choices:
            raise AssertionError("planted cover unexpectedly infeasible")
        j = min(choices)[2]
        selected[j] = 1
        for i in covers[j]:
            uncovered[i] -= 1
    for j in sorted(range(n), key=lambda j: (-instance["c"][j], j)):
        if selected[j] and all(uncovered[i] < 0 for i in covers[j]):
            selected[j] = 0
            for i in covers[j]:
                uncovered[i] += 1
    return selected, "cost-per-new-coverage greedy and redundant-column removal"


def make_incumbent(instance):
    p, family = instance["parameters"], instance["family"]
    n = instance["n"]
    if family in ("set_cover", "multicover", "vertex_cover"):
        return cover_greedy(instance)
    if family in ("set_packing", "auction"):
        selected, used = [0] * n, set()
        for j in sorted(range(n), key=lambda j: (-p["profits"][j] / len(p["bundles"][j]), j)):
            if not used.intersection(p["bundles"][j]):
                selected[j] = 1
                used.update(p["bundles"][j])
        return selected, "profit-per-bundle-size greedy"
    if family in ("knapsack", "multidimensional_knapsack"):
        selected, used = [0] * n, [0] * len(p["capacities"])
        order = sorted(range(n), key=lambda j: (-p["profits"][j] / sum(w[j] / cap for w, cap in zip(p["weights"], p["capacities"])), j))
        for j in order:
            if all(used[k] + weights[j] <= p["capacities"][k] for k, weights in enumerate(p["weights"])):
                selected[j] = 1
                for k, weights in enumerate(p["weights"]):
                    used[k] += weights[j]
        return selected, "profit-per-normalized-resource greedy"
    if family == "independent_set":
        adjacency = [set() for _ in range(n)]
        for u, v in p["edges"]:
            adjacency[u].add(v); adjacency[v].add(u)
        selected, available = [0] * n, set(range(n))
        while available:
            v = min(available, key=lambda j: (-p["weights"][j] / (1 + len(adjacency[j] & available)), j))
            selected[v] = 1
            available.difference_update(adjacency[v] | {v})
        return selected, "weighted-degree independent-set greedy"
    if family == "maxcut":
        side = [0] * p["vertices"]
        while True:
            gains = [sum(w if side[u] == side[v] else -w for (u, v), w in zip(p["edges"], p["weights"]) if j in (u, v))
                     for j in range(p["vertices"])]
            vertex = max(range(p["vertices"]), key=lambda j: (gains[j], -j))
            if gains[vertex] <= 0:
                break
            side[vertex] ^= 1
        return side + [int(side[u] != side[v]) for u, v in p["edges"]], "strict-improvement single-vertex cut flips"
    if family in ("facility_location", "pmedian"):
        f = p["facilities"]
        def total(opened):
            return sum(p["opening_costs"][j] for j in opened) + sum(min(costs[j] for j in opened) for costs in p["assignment_costs"])
        selected = {min(range(f), key=lambda j: (total({j}), j))}
        while len(selected) < (p["p"] if family == "pmedian" else f):
            candidate = min((j for j in range(f) if j not in selected), key=lambda j: (total(selected | {j}), j))
            if family != "pmedian" and total(selected | {candidate}) >= total(selected):
                break
            selected.add(candidate)
        assignments = [min(selected, key=lambda j: (costs[j], j)) for costs in p["assignment_costs"]]
        result = [int(j in selected) for j in range(f)] + [int(assignments[i] == j) for i in range(p["customers"]) for j in range(f)]
        return result, "greedy facility additions and cheapest open assignment"
    if family == "assignment":
        q = p["size"]
        available, assignments = set(range(q)), []
        for i in range(q):
            j = min(available, key=lambda j: (p["costs"][i][j], j))
            available.remove(j); assignments.append(j)
        return [int(assignments[i] == j) for i in range(q) for j in range(q)], "row-ordered cheapest remaining assignment"
    if family == "generalized_assignment":
        jobs, machines = p["jobs"], p["machines"]
        assignments = list(p["planted_machines"])
        used = [sum(p["resources"][j][m] for j in range(jobs) if assignments[j] == m) for m in range(machines)]
        for j in range(jobs):
            old = assignments[j]
            for m in sorted(range(machines), key=lambda m: (p["costs"][j][m], m)):
                if p["costs"][j][m] >= p["costs"][j][old]:
                    break
                if used[m] + p["resources"][j][m] <= p["capacities"][m]:
                    used[old] -= p["resources"][j][old]; used[m] += p["resources"][j][m]
                    assignments[j] = m
                    break
        return [int(assignments[j] == m) for j in range(jobs) for m in range(machines)], "planted feasible allocation plus one greedy reassignment pass"
    if family == "bin_packing":
        assignment, loads = first_fit(p["weights"], p["capacity"])
        result = [int(assignment[j] == b) for j in range(p["items"]) for b in range(p["bins"])]
        result += [int(b < len(loads)) for b in range(p["bins"])]
        return result, "first-fit decreasing"
    if family == "coloring":
        vertices, colors = p["vertices"], p["colors"]
        adjacency = [set() for _ in range(vertices)]
        for u, v in p["edges"]:
            adjacency[u].add(v); adjacency[v].add(u)
        assignment = [-1] * vertices
        for _ in range(vertices):
            v = max((j for j in range(vertices) if assignment[j] < 0),
                    key=lambda j: (len({assignment[k] for k in adjacency[j] if assignment[k] >= 0}), len(adjacency[j]), -j))
            used = {assignment[k] for k in adjacency[v]}
            available = [c for c in range(colors) if c not in used]
            if not available:
                assignment = list(p["planted_colors"])
                break
            assignment[v] = available[0]
        relabel = {old: new for new, old in enumerate(sorted(set(assignment)))}
        assignment = [relabel[c] for c in assignment]
        result = [int(assignment[v] == c) for v in range(vertices) for c in range(colors)]
        result += [int(c < len(relabel)) for c in range(colors)]
        return result, "DSATUR-style greedy with planted coloring fallback"
    if family == "tsp":
        cities = p["cities"]
        order, remaining = [0], set(range(1, cities))
        while remaining:
            following = min(remaining, key=lambda v: (p["distances"][order[-1]][v], v))
            order.append(following); remaining.remove(following)
        arcs = {(order[t], order[(t + 1) % cities]) for t in range(cities)}
        result = [int(order[t] == v) for v in range(cities) for t in range(cities)]
        result += [int((u, v) in arcs) for u, v in p["arcs"]]
        return result, "nearest-neighbor tour from city zero"
    if family == "rostering":
        return list(p["planted_assignment"]), "balanced cyclic planted roster respecting availability/rest"
    if family == "production":
        return [int(q == p["demands"][t]) for t in range(p["periods"]) for q in range(p["options"])], "just-in-time zero-inventory production"
    raise ValueError(family)


def to_text(instance):
    lines = [f"{instance['n']} {len(instance['rows'])}", " ".join(map(str, instance["c"]))]
    for row in instance["rows"]:
        parts = [row["b"], len(row["a"])]
        for j, value in row["a"]:
            parts.extend((j, value))
        lines.append(" ".join(map(str, parts)))
    if "incumbent" in instance:
        lines.extend(("incumbent 1", " ".join(map(str, instance["incumbent"]))))
    else:
        lines.append("incumbent 0")
    return "\n".join(lines) + "\n"


def plan_records(per_dev=3, per_test=5):
    records = []
    for fi, family in enumerate(FAMILIES):
        for ti, tier in enumerate(TIERS):
            for split, offset, count in (("dev", 1000, per_dev), ("test", 2000, per_test)):
                for index in range(count):
                    seed = 1_000_000 + fi * 100_000 + ti * 10_000 + offset + index
                    identity = f"{split}_{family}_{tier}_{seed}"
                    records.append({"id": identity, "family": family, "tier": tier, "split": split,
                                    "seed": seed, "json": f"instances/{identity}.json", "txt": f"instances/{identity}.txt", "ready": False})
    for fi, family in enumerate(FAMILIES[:12]):
        seed = 9_000_000 + fi
        identity = f"tiny_{family}_{seed}"
        records.append({"id": identity, "family": family, "tier": "tiny", "split": "tiny", "seed": seed,
                        "json": f"instances/{identity}.json", "txt": f"instances/{identity}.txt", "ready": False})
    return records


def build_instance(record, references=True):
    started = time.perf_counter()
    instance = make_model(record["family"], record["tier"], record["seed"])
    construction_seconds = time.perf_counter() - started
    instance.update({key: record[key] for key in ("id", "family", "tier", "split", "seed")})
    instance.update(generator_version=1, label=f"{record['family']}:{record['tier']}")
    initial = time.perf_counter()
    assignment, method = make_incumbent(instance)
    incumbent_seconds = time.perf_counter() - initial
    checked = validate_assignment(instance, assignment)
    if not checked["valid"]:
        raise AssertionError((instance["id"], "invalid construction witness", checked))
    instance.update(incumbent=assignment, incumbent_objective=checked["objective"], incumbent_method=method)
    reference_started = time.perf_counter()
    if references or record["split"] == "tiny":
        instance["reference"] = exact_reference(instance)
    else:
        instance["reference"] = {"status": "unknown", "reason": "reference generation disabled", "input_sha256": input_hash(instance)}
    reference_seconds = time.perf_counter() - reference_started
    if instance["reference"]["status"] == "optimal":
        checked_reference = validate_result(instance, instance["reference"])
        if not checked_reference["valid"] or not checked_reference["claims_verified"]:
            raise AssertionError((instance["id"], "invalid independent reference", checked_reference))
    instance["generation_timing"] = {"construction_seconds": construction_seconds,
                                     "incumbent_seconds": incumbent_seconds,
                                     "reference_seconds": reference_seconds,
                                     "total_seconds": time.perf_counter() - started}
    return instance


def encoding_checks():
    """Exhaustively compare every tiny assignment with independent domain logic."""
    results = []
    for fi, family in enumerate(FAMILIES):
        instance = make_model(family, "tiny", 9_100_000 + fi)
        instance.update(family=family, id=f"encoding_check_{family}")
        if instance["n"] > 18:
            raise AssertionError((family, "tiny encoding check unexpectedly large"))
        feasible = 0
        for assignment in itertools.product((0, 1), repeat=instance["n"]):
            linear, objective = linear_check(instance, assignment)
            domain, original_objective = domain_check(instance, assignment)
            if linear != domain or (linear and objective != original_objective):
                raise AssertionError((family, "encoding/domain mismatch", assignment, linear, domain, objective, original_objective))
            feasible += linear
        if feasible == 0:
            raise AssertionError((family, "tiny template unexpectedly infeasible"))
        results.append({"family": family, "n": instance["n"], "assignments_checked": 2 ** instance["n"],
                        "feasible_assignments": feasible, "passed": True})
    return results


def write_manifest(path, payload):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def generate(directory, per_dev=3, per_test=5, references=True, check_encodings=True):
    directory = Path(directory)
    (directory / "instances").mkdir(parents=True, exist_ok=True)
    records = plan_records(per_dev, per_test)
    manifest = {"schema_version": 1, "generator_version": 1, "generation_status": "in_progress",
                "families": list(FAMILIES), "tiers": list(TIERS), "per_family_tier_dev": per_dev,
                "per_family_tier_test": per_test, "instances": records,
                "notes": ["Fixed seeds are disjoint across family, size and split; no selection by measured performance.",
                          "Every instance includes a feasible constructive/greedy witness supplied identically to all solvers.",
                          "Unknown references are deliberate; do not treat incumbent objectives as optima.",
                          "Generation/greedy/reference runtime metadata is excluded from solver timing but retained explicitly.",
                          "Auction and set packing share mathematical structure; domain families are not claimed independent complexity classes.",
                          "Small/large labels describe model sizes, not guaranteed solve difficulty."]}
    write_manifest(directory / "manifest.json", manifest)
    started = time.perf_counter()
    for index, record in enumerate(records):
        instance = build_instance(record, references)
        (directory / record["json"]).write_text(json.dumps(instance, indent=2, sort_keys=True) + "\n")
        (directory / record["txt"]).write_text(to_text(instance))
        record.update(ready=True, n=instance["n"], row_count=len(instance["rows"]), label=instance["label"],
                      input_sha256=input_hash(instance), incumbent_objective=instance["incumbent_objective"],
                      reference_status=instance["reference"]["status"], generation_timing=instance["generation_timing"])
        if (index + 1) % 16 == 0:
            write_manifest(directory / "manifest.json", manifest)
            print(json.dumps({"generated": index + 1, "planned": len(records), "last_family": record["family"]}), flush=True)
    if check_encodings:
        manifest["encoding_checks"] = encoding_checks()
    else:
        manifest["encoding_checks"] = {"status": "not run"}
    manifest["generation_status"] = "complete"
    manifest["generation_seconds"] = time.perf_counter() - started
    manifest["reference_counts"] = dict(Counter(record["reference_status"] for record in records))
    manifest["benchmark_instances"] = sum(record["split"] != "tiny" for record in records)
    manifest["tiny_controls"] = sum(record["split"] == "tiny" for record in records)
    write_manifest(directory / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--dev-seeds", type=int, default=3)
    parser.add_argument("--test-seeds", type=int, default=5)
    parser.add_argument("--no-references", action="store_true")
    parser.add_argument("--skip-encoding-checks", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.dev_seeds < 1000 or not 1 <= args.test_seeds < 1000:
        parser.error("seed counts must be 1..999 to preserve disjoint ranges")
    manifest = generate(args.out_dir, args.dev_seeds, args.test_seeds, not args.no_references, not args.skip_encoding_checks)
    print(json.dumps({"directory": str(args.out_dir), "generation_status": manifest["generation_status"],
                      "instances": len(manifest["instances"]), "references": manifest["reference_counts"],
                      "generation_seconds": manifest["generation_seconds"], "solver_runs": 0}, sort_keys=True))


if __name__ == "__main__":
    main()

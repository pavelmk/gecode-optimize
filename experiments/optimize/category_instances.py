#!/usr/bin/env python3
"""Seven bounded benchmark categories; no solver calls or performance selection.

The existing capacity/assignment inputs are preserved semantically. Other
families use the existing solver-bench formulations and original-domain
validators. Reference preparation is separate from measurement. Native TXT
ends in a syntactic zero vector that the existing driver parses and discards;
neither that vector nor the independent optimum is submitted as a primal start.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import random


HERE = Path(__file__).resolve().parent
LEGACY = HERE.parent / "solver-bench"
SOURCE_DEPENDENCIES = (HERE / "scaling_instances.py", LEGACY / "validate.py", LEGACY / "native.py")
TIERS = ("sanity", "small", "medium", "large")
FACILITY_SIZES = ((2, 3), (4, 6), (8, 12), (12, 24))
BIN_SIZES = ((4, 3), (8, 4), (12, 5), (16, 6))
PRODUCTION_SIZES = (3, 6, 12, 24)
ROUTING_SIZES = (4, 8, 12, 16)
QUEENS_SIZES = (4, 8, 10, 12)
SEEDS = {"facility_location": 20260909, "bin_packing": 20260910,
         "production": 20260911, "native_tsp": 20260912, "weighted_queens": 20260913}
CATEGORIES = ("knapsack", "assignment", "facility_location", "bin_packing",
              "production", "native_tsp", "weighted_queens")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scaling = _load("category_scaling_instances", SOURCE_DEPENDENCIES[0])
binary_validator = _load("category_binary_validator", SOURCE_DEPENDENCIES[1])
native_validator = _load("category_native_validator", SOURCE_DEPENDENCIES[2])


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value):
    return type(value) is int


class _Rows:
    """Canonical Ax>=b builder, matching the existing binary TXT convention."""
    def __init__(self, costs):
        self.costs, self.rows = list(costs), []

    def ge(self, terms, bound):
        coefficients = {}
        for column, value in terms:
            coefficients[column] = coefficients.get(column, 0) + value
        self.rows.append({"a": [[j, v] for j, v in sorted(coefficients.items()) if v], "b": bound})

    def le(self, terms, bound):
        self.ge(((j, -v) for j, v in terms), -bound)

    def eq(self, terms, bound):
        terms = list(terms)
        self.ge(terms, bound)
        self.le(terms, bound)


def _formulation(family, p):
    if family == "facility_location":
        f, customers = p["facilities"], p["customers"]
        rows = _Rows(p["opening_costs"] + [c for row in p["assignment_costs"] for c in row])
        for customer in range(customers):
            rows.eq(((f + customer * f + j, 1) for j in range(f)), 1)
            for j in range(f):
                rows.ge(((j, 1), (f + customer * f + j, -1)), 0)
    elif family == "bin_packing":
        items, bins = p["items"], p["bins"]
        rows = _Rows([0] * (items * bins) + [1] * bins)
        for item in range(items):
            rows.eq(((item * bins + b, 1) for b in range(bins)), 1)
            for b in range(bins):
                rows.ge(((items * bins + b, 1), (item * bins + b, -1)), 0)
        for b in range(bins):
            rows.ge([(items * bins + b, p["capacity"])] +
                    [(item * bins + b, -p["weights"][item]) for item in range(items)], 0)
        for b in range(bins - 1):
            rows.ge(((items * bins + b, 1), (items * bins + b + 1, -1)), 0)
    elif family == "production":
        periods, options = p["periods"], p["options"]
        rows = _Rows([p["production_costs"][t][q] + p["holding_cost"] * (periods - t) * q
                      for t in range(periods) for q in range(options)])
        for t in range(periods):
            rows.eq(((t * options + q, 1) for q in range(options)), 1)
            prefix = [(s * options + q, q) for s in range(t + 1) for q in range(1, options)]
            demand = sum(p["demands"][:t + 1])
            rows.ge(prefix, demand)
            rows.le(prefix, demand + p["storage"])
        rows.eq(((t * options + q, q) for t in range(periods) for q in range(1, options)), sum(p["demands"]))
    else:
        raise ValueError("unsupported binary category")
    return {"n": len(rows.costs), "c": rows.costs, "rows": rows.rows}


def _scaling_view(model):
    result = dict(model)
    result["dimensions"] = {"variables": model["n"], "rows": len(model["rows"]),
                            "nonzeros": sum(len(row["a"]) for row in model["rows"])}
    return result


def semantic_hash(model):
    if model["kind"] == "binary":
        return scaling.semantic_hash(model)
    return native_validator.mathematical_hash(model)


input_hash = semantic_hash


def _dimensions(model):
    n = model["n"]
    if model["kind"] == "binary":
        return {"input_variables": n, "variables": n, "rows": len(model["rows"]),
                "nonzeros": sum(len(row["a"]) for row in model["rows"]), "globals": 0}
    routing = model["kind"] == "native_tsp"
    return {"input_variables": n, "variables": (2 if routing else 4) * n,
            "rows": 0 if routing else 2 * n, "nonzeros": 0 if routing else 4 * n,
            "globals": n + (1 if routing else 3)}


def _check_model(model):
    _require(type(model) is dict and model.get("category") in CATEGORIES, "invalid category model")
    n = model.get("n")
    _require(_integer(n) and 1 <= n <= 512, "invalid input variable count")
    family, kind = model.get("family"), model.get("kind")
    if kind == "binary":
        if family in ("capacity_uncorrelated", "capacity_correlated", "assignment"):
            scaling._check_model(_scaling_view(model))
        else:
            _require(family in ("facility_location", "bin_packing", "production"), "unknown binary family")
            binary_validator.check_instance(model)
            p = model.get("parameters")
            _require(type(p) is dict, "missing original parameters")
            if family == "facility_location":
                f, c = p.get("facilities"), p.get("customers")
                _require(_integer(f) and 1 <= f <= 12 and _integer(c) and 1 <= c <= 24, "facility dimensions")
                _require(type(p.get("opening_costs")) is list and len(p["opening_costs"]) == f and
                         all(_integer(v) and v >= 0 for v in p["opening_costs"]), "facility opening costs")
                matrix = p.get("assignment_costs")
                _require(type(matrix) is list and len(matrix) == c and
                         all(type(row) is list and len(row) == f and all(_integer(v) and v >= 0 for v in row)
                             for row in matrix), "facility assignment costs")
            elif family == "bin_packing":
                items, bins, capacity = p.get("items"), p.get("bins"), p.get("capacity")
                _require(_integer(items) and 1 <= items <= 16 and _integer(bins) and 1 <= bins <= 16 and
                         _integer(capacity) and capacity > 0, "bin dimensions")
                _require(type(p.get("weights")) is list and len(p["weights"]) == items and
                         all(_integer(w) and 0 < w <= capacity for w in p["weights"]), "bin weights")
            else:
                periods, options = p.get("periods"), p.get("options")
                _require(_integer(periods) and 1 <= periods <= 24 and _integer(options) and 2 <= options <= 8,
                         "production dimensions")
                _require(_integer(p.get("storage")) and 0 <= p["storage"] <= 10 and
                         _integer(p.get("holding_cost")) and p["holding_cost"] >= 0, "production storage/holding")
                _require(type(p.get("demands")) is list and len(p["demands"]) == periods and
                         all(_integer(v) and 0 <= v < options for v in p["demands"]), "production demands")
                matrix = p.get("production_costs")
                _require(type(matrix) is list and len(matrix) == periods and
                         all(type(row) is list and len(row) == options and all(_integer(v) and v >= 0 for v in row)
                             for row in matrix), "production costs")
                constant = -p["holding_cost"] * sum(sum(p["demands"][:t + 1]) for t in range(periods))
                _require(p.get("objective_constant") == constant, "production objective constant")
            expected = _formulation(family, p)
            _require(all(model[key] == expected[key] for key in ("n", "c", "rows")),
                     "original family parameters disagree with sparse formulation")
    else:
        _require(kind in ("native_tsp", "weighted_queens") and family == kind and
                 model.get("size") == n and model.get("machines") == 0 and 4 <= n <= (16 if kind == "native_tsp" else 12),
                 "native family dimensions")
        matrix = model.get("data")
        _require(type(matrix) is list and len(matrix) == n and
                 all(type(row) is list and len(row) == n and all(_integer(c) and 0 <= c <= 100000 for c in row)
                     for row in matrix), "native cost matrix")
    expected_category = {"capacity_uncorrelated": "knapsack", "capacity_correlated": "knapsack"}.get(family, family)
    variant = {"capacity_uncorrelated": "uncorrelated", "capacity_correlated": "correlated"}.get(family, "single")
    _require(model["category"] == expected_category and model.get("variant") == variant, "category/variant mismatch")
    dimensions = _dimensions(model)
    _require(model.get("dimensions") == dimensions and model.get("modelled_variables") == dimensions["variables"],
             "compiled dimension metadata mismatch")


def validate_assignment(model, assignment):
    try:
        _check_model(model)
        _require(type(assignment) is list and len(assignment) == model["n"] and all(_integer(v) for v in assignment),
                 "original assignment must contain exact integers")
        if model["family"] in ("capacity_uncorrelated", "capacity_correlated", "assignment"):
            return scaling.validate_assignment(_scaling_view(model), assignment)
        validator = binary_validator if model["kind"] == "binary" else native_validator
        return validator.validate_assignment(model, assignment)
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {"valid": False, "error": str(error)}


def bin_reference(weights, capacity, bins):
    """Exact subset DP over (used bins, last load), unrelated to solver search.

    For each item subset retain its lexicographically best state. A lower last
    load dominates at equal bin count. An item is appended to the current bin
    when it fits, otherwise a new bin starts. Every packing has such an item
    order; reconstruction records each appended item and bin boundary.
    """
    _require(type(weights) is list and 1 <= len(weights) <= 16 and
             _integer(capacity) and capacity > 0 and _integer(bins) and bins > 0 and
             all(_integer(w) and 0 < w <= capacity for w in weights), "bin reference domain")
    size = 1 << len(weights)
    states, item, new_bin = [None] * size, [-1] * size, bytearray(size)
    states[0] = (1, 0)
    for mask in range(1, size):
        for j, weight in enumerate(weights):
            if not mask & (1 << j):
                continue
            count, load = states[mask ^ (1 << j)]
            opens = load + weight > capacity
            candidate = (count + 1, weight) if opens else (count, load + weight)
            if states[mask] is None or candidate < states[mask]:
                states[mask], item[mask], new_bin[mask] = candidate, j, opens
    _require(states[-1][0] <= bins, "model has too few bins for the exact optimum")
    order, mask = [], size - 1
    while mask:
        order.append((item[mask], bool(new_bin[mask])))
        mask ^= 1 << item[mask]
    assigned, current = [0] * len(weights), 0
    for j, opens in reversed(order):
        current += int(opens)
        assigned[j] = current
    witness = [int(assigned[j] == b) for j in range(len(weights)) for b in range(bins)]
    witness += [int(b < states[-1][0]) for b in range(bins)]
    return {"status": "optimal", "objective": states[-1][0], "assignment": witness,
            "method": "exact item-subset minimum-bin/last-load dynamic programming"}


def _reference(model):
    family = model["family"]
    if family in ("capacity_uncorrelated", "capacity_correlated", "assignment"):
        return scaling._reference(_scaling_view(model))
    if family == "bin_packing":
        p = model["parameters"]
        reference = bin_reference(p["weights"], p["capacity"], p["bins"])
    elif family in ("facility_location", "production"):
        reference = binary_validator.exact_reference(model)
    else:
        oracle = native_validator.tsp_reference if family == "native_tsp" else native_validator.queens_reference
        best, witness = oracle(model["data"])
        reference = {"status": "optimal", "objective": best, "assignment": witness,
                     "method": "Held-Karp subset dynamic programming" if family == "native_tsp"
                     else "independent exhaustive weighted-queen enumeration"}
    reference["input_sha256"] = semantic_hash(model)
    checked = validate_assignment(model, reference.get("assignment"))
    _require(reference.get("status") == "optimal" and checked["valid"] and
             checked["objective"] == reference["objective"], "exact reference original witness failed")
    return reference


def verify_reference(model, *, recompute=False):
    """Cheap frozen identity/original witness check; exact reproof is opt-in."""
    try:
        _check_model(model)
        reference = model["reference"]
        identity = semantic_hash(model)
        _require(type(reference) is dict and reference.get("status") == "optimal" and
                 _integer(reference.get("objective")) and reference.get("input_sha256") == identity and
                 type(reference.get("method")) is str and reference["method"], "reference identity/status mismatch")
        checked = validate_assignment(model, reference.get("assignment"))
        _require(checked["valid"] and checked["objective"] == reference["objective"], "reference witness mismatch")
        if recompute:
            _require(_reference(model)["objective"] == reference["objective"], "reference optimum mismatch")
        return {"valid": True, "input_sha256": identity, "witness_checked": True,
                "optimality_recomputed": bool(recompute), "objective": reference["objective"]}
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {"valid": False, "witness_checked": False, "optimality_recomputed": False, "error": str(error)}


def encode_txt(model):
    _check_model(model)
    if model["kind"] == "binary":
        lines = [f"{model['n']} {len(model['rows'])}", " ".join(map(str, model["c"]))]
        for row in model["rows"]:
            lines.append(" ".join(map(str, [row["b"], len(row["a"])] +
                                      [v for pair in row["a"] for v in pair])))
        return "\n".join(lines) + "\nincumbent 0\n"
    n = model["n"]
    return (f"{model['family']} {n} 0 {n}\n" +
            " ".join(str(c) for row in model["data"] for c in row) + "\n" +
            " ".join("0" for _ in range(n)) + "\n")


expected_binary_text = encode_txt
expected_native_text = encode_txt


def _finish(model, with_references):
    family = model["family"]
    model["category"] = {"capacity_uncorrelated": "knapsack", "capacity_correlated": "knapsack"}.get(family, family)
    model["variant"] = {"capacity_uncorrelated": "uncorrelated", "capacity_correlated": "correlated"}.get(family, "single")
    model["stress"] = family == "capacity_uncorrelated" and model["n"] == 512
    model["size_unit"] = {"native_tsp": "cities", "weighted_queens": "queens"}.get(family, "binary variables")
    model["dimensions"] = _dimensions(model)
    model["modelled_variables"] = model["dimensions"]["variables"]
    _check_model(model)
    if with_references and "reference" not in model:
        model["reference"] = _reference(model)
    return model


def _first_fit(weights, capacity):
    loads = []
    for weight in sorted(weights, reverse=True):
        index = next((j for j, load in enumerate(loads) if load + weight <= capacity), len(loads))
        if index == len(loads):
            loads.append(0)
        loads[index] += weight
    return len(loads)


def generate_suite(*, with_references=True):
    """Return 33 fixed cases. No timings, file writes or solver-derived choices."""
    result = [_finish(copy.deepcopy(m), with_references)
              for m in scaling.generate_suite(with_references=with_references)]
    rng = random.Random(SEEDS["facility_location"])
    sites = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(12)]
    customers = [(rng.randint(0, 30), rng.randint(0, 30)) for _ in range(24)]
    opening = [rng.randint(15, 60) for _ in range(12)]
    for tier, (f, c) in zip(TIERS, FACILITY_SIZES):
        p = {"facilities": f, "customers": c, "opening_costs": opening[:f],
             "assignment_costs": [[abs(a - x) + abs(b - y) + 1 for x, y in sites[:f]] for a, b in customers[:c]]}
        model = dict(_formulation("facility_location", p), parameters=p, family="facility_location", kind="binary",
                     id=f"facility_location_{tier}_{f}x{c}", tier=tier, tier_size=f, seed=SEEDS["facility_location"])
        result.append(_finish(model, with_references))
    rng = random.Random(SEEDS["bin_packing"])
    weights = [rng.randint(2, 10) for _ in range(16)]
    for tier, (items, bins) in zip(TIERS, BIN_SIZES):
        selected = weights[:items]
        capacity = max(max(selected), (sum(selected) + bins - 2) // (bins - 1))
        while _first_fit(selected, capacity) > bins:
            capacity += 1
        p = {"items": items, "bins": bins, "weights": selected, "capacity": capacity,
             "symmetry": "enabled bins form a prefix"}
        model = dict(_formulation("bin_packing", p), parameters=p, family="bin_packing", kind="binary",
                     id=f"bin_packing_{tier}_{items}x{bins}", tier=tier, tier_size=items, seed=SEEDS["bin_packing"])
        result.append(_finish(model, with_references))
    rng = random.Random(SEEDS["production"])
    demands = [rng.randint(1, 7) for _ in range(24)]
    storage, holding = rng.randint(3, 10), rng.randint(1, 4)
    costs = []
    for _ in range(24):
        fixed, unit = rng.randint(5, 20), rng.randint(2, 12)
        costs.append([0 if q == 0 else fixed + unit * q + max(0, q - 4) * 5 for q in range(8)])
    for tier, periods in zip(TIERS, PRODUCTION_SIZES):
        p = {"periods": periods, "options": 8, "demands": demands[:periods], "storage": storage,
             "holding_cost": holding, "production_costs": costs[:periods],
             "objective_constant": -holding * sum(sum(demands[:t + 1]) for t in range(periods))}
        model = dict(_formulation("production", p), parameters=p, family="production", kind="binary",
                     id=f"production_{tier}_{periods}x8", tier=tier, tier_size=periods, seed=SEEDS["production"])
        result.append(_finish(model, with_references))
    for family, sizes in (("native_tsp", ROUTING_SIZES), ("weighted_queens", QUEENS_SIZES)):
        rng = random.Random(SEEDS[family])
        if family == "native_tsp":
            points = [(rng.randrange(100), rng.randrange(100)) for _ in range(16)]
            matrix = [[abs(a - x) + abs(b - y) + (i != j) for j, (x, y) in enumerate(points)]
                      for i, (a, b) in enumerate(points)]
        else:
            matrix = [[rng.randint(1, 50) for _ in range(12)] for _ in range(12)]
        for tier, n in zip(TIERS, sizes):
            model = dict(family=family, kind=family, id=f"{family}_{tier}_{n}", tier=tier, tier_size=n,
                         seed=SEEDS[family], n=n, size=n, machines=0, data=[row[:n] for row in matrix[:n]],
                         parameters={"size": n})
            result.append(_finish(model, with_references))
    _require(len(result) == 33 and len({m["id"] for m in result}) == 33, "category panel dimensions")
    return result

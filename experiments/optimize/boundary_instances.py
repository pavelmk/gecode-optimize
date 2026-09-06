#!/usr/bin/env python3
"""Deterministic adaptive-size inputs; no references, solver calls or starts.

Version 1 preserves the old random master blocks, extending their streams only
after those blocks are complete. Facility customers are now twice the sites;
candidate bin count is ceil(items/3). Those dimensions deliberately differ from
some earlier fixed cases. Native n counts input variables, while model_variables
also counts the existing driver's diagonal/cost auxiliaries. Their full-value
validation remains the runner's responsibility.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import random


_spec = importlib.util.spec_from_file_location("boundary_category_instances",
                                             Path(__file__).resolve().with_name("category_instances.py"))
category = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(category)


GENERATOR_VERSION = "boundary-prefix-v1"
BOUNDS = {"knapsack": (8, 512), "assignment": (3, 32),
          "facility_location": (2, 16), "bin_packing": (4, 32),
          "production": (3, 48), "native_tsp": (4, 96), "weighted_queens": (4, 32)}
SOURCE_DEPENDENCIES = (category.HERE / "category_instances.py",) + category.SOURCE_DEPENDENCIES
_require = category._require


def _admit(name, size, variant):
    _require(type(name) is str and name in BOUNDS, "unknown boundary category")
    low, high = BOUNDS[name]
    _require(type(size) is int and low <= size <= high, f"{name} size must be an integer in [{low},{high}]")
    _require(variant in (("uncorrelated", "correlated") if name == "knapsack" else ("single",)),
             "knapsack needs an explicit distribution; other categories use single")


def _extended_matrix(seed, original, maximum, upper):
    rng = random.Random(seed)
    matrix = [[0] * maximum for _ in range(maximum)]
    for i in range(original):
        for j in range(original):
            matrix[i][j] = rng.randint(1, upper)
    for i in range(maximum):
        for j in range(maximum):
            if i >= original or j >= original:
                matrix[i][j] = rng.randint(1, upper)
    return matrix


def make(name, size, variant="single"):
    """Build one bounded original model, without computing a reference optimum."""
    _admit(name, size, variant)
    family = "capacity_" + variant if name == "knapsack" else name
    seed = category.scaling.FAMILY_SEEDS.get(family, category.SEEDS.get(family))
    rng = random.Random(seed)
    model = {"id": f"{name}_{variant}_{size}", "category": name, "family": family,
             "variant": variant, "kind": "binary", "tier": "adaptive", "tier_size": size,
             "natural_size": size, "seed": seed, "generator_version": GENERATOR_VERSION,
             "prefix_policy": "preserve old master blocks, then extend the same seeded stream"}
    if name == "knapsack":
        items = []
        for _ in range(512):
            weight = rng.randint(1, 31)
            profit = rng.randint(1, 100) if variant == "uncorrelated" else weight + rng.randint(0, 10)
            items.append((weight, profit))
        weights, profits = [w for w, _ in items[:size]], [p for _, p in items[:size]]
        capacity, cells = 6 * size, (size + 1) * (6 * size + 1)
        p = {"weights": [weights], "profits": profits, "capacities": [capacity], "capacity": capacity,
             "table_cells": cells, "dp_eligible": cells <= 1000000,
             "dp_eligibility_reason": "eligible" if cells <= 1000000 else "full_table_cell_cap_exceeded"}
        model.update(n=size, c=[-p for p in profits], rows=category.scaling._capacity_rows(weights, capacity))
    elif name == "assignment":
        master = _extended_matrix(seed, 16, 32, 100)
        matrix = [row[:size] for row in master[:size]]
        p = {"size": size, "costs": matrix, "table_cells": None, "dp_eligible": False,
             "dp_eligibility_reason": "multiple_assignment_equality_rows"}
        model.update(n=size * size, c=[c for row in matrix for c in row],
                     rows=category.scaling._assignment_rows(size))
    elif name == "facility_location":
        point = lambda: (rng.randint(0, 30), rng.randint(0, 30))
        sites = [point() for _ in range(12)]
        customers = [point() for _ in range(24)]
        opening = [rng.randint(15, 60) for _ in range(12)]
        sites += [point() for _ in range(4)]
        customers += [point() for _ in range(8)]
        opening += [rng.randint(15, 60) for _ in range(4)]
        p = {"facilities": size, "customers": 2 * size, "opening_costs": opening[:size],
             "assignment_costs": [[abs(a - x) + abs(b - y) + 1 for x, y in sites[:size]]
                                  for a, b in customers[:2 * size]]}
    elif name == "bin_packing":
        weights = [rng.randint(2, 10) for _ in range(32)][:size]
        bins = (size + 2) // 3
        capacity = max(max(weights), (sum(weights) + bins - 2) // (bins - 1))
        while category._first_fit(weights, capacity) > bins:
            capacity += 1
        p = {"items": size, "bins": bins, "weights": weights, "capacity": capacity,
             "symmetry": "enabled bins form a prefix"}
    elif name == "production":
        demands = [rng.randint(1, 7) for _ in range(24)]
        storage, holding = rng.randint(3, 10), rng.randint(1, 4)
        def costs():
            fixed, unit = rng.randint(5, 20), rng.randint(2, 12)
            return [0 if q == 0 else fixed + unit * q + max(0, q - 4) * 5 for q in range(8)]
        matrix = [costs() for _ in range(24)]
        demands += [rng.randint(1, 7) for _ in range(24)]
        matrix += [costs() for _ in range(24)]
        p = {"periods": size, "options": 8, "demands": demands[:size], "storage": storage,
             "holding_cost": holding, "production_costs": matrix[:size],
             "objective_constant": -holding * sum(sum(demands[:t + 1]) for t in range(size))}
    else:
        if name == "native_tsp":
            points = [(rng.randrange(100), rng.randrange(100)) for _ in range(96)][:size]
            matrix = [[abs(a - x) + abs(b - y) + (i != j) for j, (x, y) in enumerate(points)]
                      for i, (a, b) in enumerate(points)]
        else:
            master = _extended_matrix(seed, 12, 32, 50)
            matrix = [row[:size] for row in master[:size]]
        p = {"size": size}
        model.update(kind=name, n=size, size=size, machines=0, data=matrix)
    if name in ("facility_location", "bin_packing", "production"):
        model.update(category._formulation(name, p))
        p.update(table_cells=None, dp_eligible=False, dp_eligibility_reason="multiple_original_rows")
    model["parameters"] = p
    model["dimensions"] = category._dimensions(model)
    model["input_variables"] = model["n"]
    model["model_variables"] = model["modelled_variables"] = model["dimensions"]["variables"]
    model["size_unit"] = {"knapsack": "items", "assignment": "tasks", "facility_location": "sites",
                          "bin_packing": "items", "production": "periods",
                          "native_tsp": "cities", "weighted_queens": "queens"}[name]
    return model


def _check_model(model):
    _require(type(model) is dict, "model must be an object")
    expected = make(model.get("category"), model.get("natural_size"), model.get("variant"))
    # Canonical JSON distinguishes booleans/floats from exact integer fields.
    actual = {key: model.get(key) for key in expected}
    _require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
             json.dumps(expected, sort_keys=True, allow_nan=False),
             "boundary metadata or original formulation differs from deterministic input")


def semantic_hash(model):
    _check_model(model)
    return category.semantic_hash(model)


input_hash = semantic_hash


def validate_assignment(model, assignment):
    """Check original feasibility/objective only; never certify optimality."""
    try:
        _check_model(model)
        _require(type(assignment) is list and len(assignment) == model["n"] and
                 all(type(v) is int for v in assignment), "expected exact original integer assignment")
        original = dict(model)
        if model["category"] == "knapsack":
            original["family"] = "knapsack"
        validator = category.binary_validator if model["kind"] == "binary" else category.native_validator
        checked = validator.validate_assignment(original, assignment)
        if checked["valid"]:
            checked["domain_semantics_checked"] = True
        return checked
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {"valid": False, "error": str(error)}


def encode_txt(model):
    """Encode the existing sparse/native driver protocol without a warm start."""
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

#!/usr/bin/env python3
"""Frozen deterministic capacity/assignment scaling inputs and exact references.

There is no solver, binding, subprocess or filesystem dependency. Capacity
references minimize weight for each attainable profit, independently of the
product's weight-indexed objective DP. Assignment references use subsets of
columns. Reference witnesses are never included in the driver TXT stream.

``verify_reference`` defaults to cheap record/identity/witness checks. These do
not re-prove a stored optimum: a benchmark must freeze the complete generated
reference bytes before measurement. Pass ``recompute=True`` only outside the
measurement window to repeat the independent exact oracle.
"""
from __future__ import annotations

import hashlib
import json
import random


CAPACITY_TIERS = (("sanity", 8), ("small", 32), ("medium", 128), ("large", 384))
ASSIGNMENT_TIERS = (("sanity", 3), ("small", 5), ("medium", 9), ("large", 16))
FAMILY_SEEDS = {
    "capacity_uncorrelated": 20260906,
    "capacity_correlated": 20260907,
    "assignment": 20260908,
}
MAX_REFERENCE_TRANSITIONS = 16000000


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _integer(value):
    return type(value) is int


def semantic_hash(model):
    """Match solver-bench/validate.input_hash: hash only n/c/rows."""
    data = {key: model[key] for key in ("n", "c", "rows")}
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf8")).hexdigest()


input_hash = semantic_hash


def _capacity_rows(weights, capacity):
    return [{"b": -capacity, "a": [[j, -weight] for j, weight in enumerate(weights)]}]


def _assignment_rows(size):
    rows = []
    for columns in ([i * size + j for j in range(size)] for i in range(size)):
        rows.extend(({"b": 1, "a": [[j, 1] for j in columns]},
                     {"b": -1, "a": [[j, -1] for j in columns]}))
    for columns in ([i * size + j for i in range(size)] for j in range(size)):
        rows.extend(({"b": 1, "a": [[j, 1] for j in columns]},
                     {"b": -1, "a": [[j, -1] for j in columns]}))
    return rows


def _check_model(model):
    _require(type(model) is dict, "model must be an object")
    n, costs, rows = model.get("n"), model.get("c"), model.get("rows")
    _require(_integer(n) and 1 <= n <= 512, "invalid binary column count")
    _require(type(costs) is list and len(costs) == n and all(_integer(c) for c in costs),
             "costs must be n exact integers")
    _require(type(rows) is list, "rows must be a list")
    for row in rows:
        _require(type(row) is dict and _integer(row.get("b")) and type(row.get("a")) is list,
                 "invalid sparse row")
        previous = -1
        for pair in row["a"]:
            _require(type(pair) is list and len(pair) == 2, "invalid sparse term")
            column, value = pair
            _require(_integer(column) and previous < column < n and _integer(value) and value != 0,
                     "sparse terms must be ordered, unique, nonzero and in range")
            previous = column
    parameters = model.get("parameters")
    _require(type(parameters) is dict, "missing original domain parameters")
    family = model.get("family")
    if family in ("capacity_uncorrelated", "capacity_correlated"):
        weights, capacities, profits = (parameters.get(k) for k in ("weights", "capacities", "profits"))
        _require(type(weights) is list and len(weights) == 1 and type(weights[0]) is list and
                 len(weights[0]) == n and all(_integer(w) and w > 0 for w in weights[0]),
                 "invalid original capacity weights")
        _require(type(capacities) is list and len(capacities) == 1 and
                 _integer(capacities[0]) and capacities[0] >= 0, "invalid original capacity")
        _require(type(profits) is list and len(profits) == n and
                 all(_integer(p) and p > 0 for p in profits), "invalid original profits")
        _require(costs == [-p for p in profits] and rows == _capacity_rows(weights[0], capacities[0]),
                 "original capacity semantics differ from sparse model")
        cells = (n + 1) * (capacities[0] + 1)
        eligible = capacities[0] <= 65536 and cells <= 1000000
        _require(parameters.get("capacity") == capacities[0] and parameters.get("table_cells") == cells and
                 type(parameters.get("dp_eligible")) is bool and parameters["dp_eligible"] == eligible and
                 parameters.get("dp_eligibility_reason") ==
                 ("eligible" if eligible else "full_table_cell_cap_exceeded"),
                 "capacity admission metadata differs from original model")
    elif family == "assignment":
        size, matrix = parameters.get("size"), parameters.get("costs")
        _require(_integer(size) and 1 <= size <= 16 and size * size == n,
                 "invalid original assignment size")
        _require(type(matrix) is list and len(matrix) == size and
                 all(type(row) is list and len(row) == size and
                     all(_integer(c) and c >= 0 for c in row) for row in matrix),
                 "invalid original assignment matrix")
        _require(costs == [c for row in matrix for c in row] and rows == _assignment_rows(size),
                 "original assignment semantics differ from sparse model")
        _require(parameters.get("table_cells") is None and parameters.get("dp_eligible") is False and
                 parameters.get("dp_eligibility_reason") == "multiple_assignment_equality_rows",
                 "assignment admission metadata mismatch")
    else:
        raise ValueError("unknown scaling family")
    _require(model.get("dimensions") == {"variables": n, "rows": len(rows),
                                         "nonzeros": sum(len(row["a"]) for row in rows)},
             "model dimensions metadata mismatch")


def validate_assignment(model, assignment):
    """Check binary values, every sparse row and original family semantics."""
    try:
        _check_model(model)
        n = model["n"]
        _require(type(assignment) is list and len(assignment) == n and
                 all(_integer(x) and x in (0, 1) for x in assignment),
                 "assignment must contain n exact binary integers")
        _require(all(sum(a * assignment[j] for j, a in row["a"]) >= row["b"]
                     for row in model["rows"]), "original sparse row violated")
        parameters = model["parameters"]
        if model["family"] == "assignment":
            size = parameters["size"]
            _require(all(sum(assignment[i * size:(i + 1) * size]) == 1 for i in range(size)) and
                     all(sum(assignment[i * size + j] for i in range(size)) == 1 for j in range(size)),
                     "original assignment bijection violated")
            domain_cost = sum(parameters["costs"][i][j] * assignment[i * size + j]
                              for i in range(size) for j in range(size))
        else:
            _require(sum(w * x for w, x in zip(parameters["weights"][0], assignment)) <=
                     parameters["capacities"][0], "original capacity violated")
            domain_cost = -sum(p * x for p, x in zip(parameters["profits"], assignment))
        objective = sum(c * x for c, x in zip(model["c"], assignment))
        _require(domain_cost == objective, "original objective differs from sparse objective")
        return {"valid": True, "objective": objective, "domain_semantics_checked": True}
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {"valid": False, "error": str(error)}


def capacity_reference(weights, profits, capacity):
    """Exact minimum weight by profit, with per-item decisions for reconstruction."""
    _require(type(weights) is list and type(profits) is list and
             1 <= len(weights) <= 512 and len(profits) == len(weights), "reference item count")
    _require(all(_integer(w) and w > 0 for w in weights) and
             all(_integer(p) and p > 0 for p in profits) and
             _integer(capacity) and capacity >= 0, "reference needs positive integer items")
    total_profit = sum(profits)
    prefix, work = 0, 0
    for profit in profits:
        work += prefix + 1
        prefix += profit
    _require(total_profit <= 51200 and work <= MAX_REFERENCE_TRANSITIONS, "reference work cap")
    # Weights above capacity are unreachable for all later positive-weight items.
    unreachable = capacity + 1
    minimum_weight = [unreachable] * (total_profit + 1)
    minimum_weight[0] = 0
    decisions, prefix, transitions = [], 0, 0
    for weight, profit in zip(weights, profits):
        prefix += profit
        chosen = bytearray(prefix + 1)
        for value in range(prefix, profit - 1, -1):
            transitions += 1
            previous = minimum_weight[value - profit]
            if previous <= capacity - weight and previous + weight < minimum_weight[value]:
                minimum_weight[value] = previous + weight
                chosen[value] = 1
        decisions.append(chosen)
    best = max(value for value, weight in enumerate(minimum_weight) if weight <= capacity)
    remaining = best
    assignment = [0] * len(weights)
    for i in range(len(weights) - 1, -1, -1):
        if remaining < len(decisions[i]) and decisions[i][remaining]:
            assignment[i] = 1
            remaining -= profits[i]
    _require(remaining == 0 and sum(w * x for w, x in zip(weights, assignment)) <= capacity and
             sum(p * x for p, x in zip(profits, assignment)) == best, "reference reconstruction")
    return {"status": "optimal", "objective": -best, "assignment": assignment,
            "method": "exact minimum-weight-by-profit dynamic programming",
            "oracle_transitions": transitions}


def assignment_reference(costs):
    """Exact minimum assignment cost over subsets of already used columns."""
    _require(type(costs) is list and 1 <= len(costs) <= 16, "assignment reference size")
    size = len(costs)
    _require(all(type(row) is list and len(row) == size and
                 all(_integer(c) and c >= 0 for c in row) for row in costs), "assignment reference costs")
    values, previous_column = [None] * (1 << size), [-1] * (1 << size)
    values[0] = 0
    transitions = 0
    for mask in range((1 << size) - 1):
        row = mask.bit_count()
        for column in range(size):
            if mask & (1 << column):
                continue
            transitions += 1
            target = mask | (1 << column)
            candidate = values[mask] + costs[row][column]
            if values[target] is None or candidate < values[target]:
                values[target] = candidate
                previous_column[target] = column
    mask = (1 << size) - 1
    assignment = [0] * (size * size)
    for row in range(size - 1, -1, -1):
        column = previous_column[mask]
        _require(column >= 0 and mask & (1 << column), "assignment reference reconstruction")
        assignment[row * size + column] = 1
        mask ^= 1 << column
    _require(mask == 0, "assignment reference incomplete reconstruction")
    return {"status": "optimal", "objective": values[-1], "assignment": assignment,
            "method": "exact subset-column assignment dynamic programming",
            "oracle_transitions": transitions}


def _reference(model):
    _check_model(model)
    p = model["parameters"]
    reference = assignment_reference(p["costs"]) if model["family"] == "assignment" else \
        capacity_reference(p["weights"][0], p["profits"], p["capacities"][0])
    reference["input_sha256"] = semantic_hash(model)
    checked = validate_assignment(model, reference["assignment"])
    _require(checked["valid"] and checked["objective"] == reference["objective"], "reference witness failed")
    return reference


def verify_reference(model, *, recompute=False):
    """Validate a frozen reference; recomputation is explicit and never implicit."""
    try:
        _check_model(model)
        reference = model["reference"]
        identity = semantic_hash(model)
        _require(type(reference) is dict and reference.get("status") == "optimal" and
                 reference.get("input_sha256") == identity and _integer(reference.get("objective")),
                 "reference status/identity/objective mismatch")
        expected_method = ("exact subset-column assignment dynamic programming" if model["family"] == "assignment"
                           else "exact minimum-weight-by-profit dynamic programming")
        _require(reference.get("method") == expected_method and
                 _integer(reference.get("oracle_transitions")) and reference["oracle_transitions"] >= 0,
                 "reference method/work mismatch")
        checked = validate_assignment(model, reference.get("assignment"))
        _require(checked["valid"] and checked["objective"] == reference["objective"], "reference witness mismatch")
        if recompute:
            _require(_reference(model)["objective"] == reference["objective"], "reference optimum mismatch")
        return {"valid": True, "input_sha256": identity, "witness_checked": True,
                "optimality_recomputed": bool(recompute), "objective": reference["objective"]}
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {"valid": False, "error": str(error), "witness_checked": False,
                "optimality_recomputed": False}


def encode_txt(model):
    """Encode the fixed binary driver protocol, always without a primal start."""
    _check_model(model)
    lines = [f"{model['n']} {len(model['rows'])}", " ".join(map(str, model["c"]))]
    for row in model["rows"]:
        tokens = [row["b"], len(row["a"])] + [value for pair in row["a"] for value in pair]
        lines.append(" ".join(map(str, tokens)))
    return "\n".join(lines) + "\nincumbent 0\n"


expected_binary_text = encode_txt


def _complete(model, with_references):
    model["kind"] = "binary"
    model["dimensions"] = {"variables": model["n"], "rows": len(model["rows"]),
                           "nonzeros": sum(len(row["a"]) for row in model["rows"])}
    _check_model(model)
    if with_references:
        model["reference"] = _reference(model)
    return model


def generate_suite(*, with_references=True):
    """Return the 13 prespecified models in stable order, without file writes.

    ``with_references=False`` is for cheap generator/schema tests only; such
    records must not be frozen for a measured comparison.
    """
    result = []
    for family in ("capacity_uncorrelated", "capacity_correlated"):
        rng = random.Random(FAMILY_SEEDS[family])
        items = []
        for _ in range(512):
            weight = rng.randint(1, 31)
            profit = rng.randint(1, 100) if family == "capacity_uncorrelated" else weight + rng.randint(0, 10)
            items.append((weight, profit))
        tiers = CAPACITY_TIERS + (("cap_overflow", 512),) if family == "capacity_uncorrelated" else CAPACITY_TIERS
        for tier, size in tiers:
            weights, profits = [w for w, _ in items[:size]], [p for _, p in items[:size]]
            capacity = 6 * size
            cells = (size + 1) * (capacity + 1)
            eligible = capacity <= 65536 and cells <= 1000000
            parameters = {"weights": [weights], "profits": profits, "capacities": [capacity],
                          "capacity": capacity, "table_cells": cells, "dp_eligible": eligible,
                          "dp_eligibility_reason": "eligible" if eligible else "full_table_cell_cap_exceeded"}
            model = {"id": f"{family}_{tier}_{size}", "family": family, "tier": tier,
                     "tier_size": size, "seed": FAMILY_SEEDS[family], "n": size,
                     "c": [-p for p in profits], "rows": _capacity_rows(weights, capacity), "parameters": parameters}
            result.append(_complete(model, with_references))
    rng = random.Random(FAMILY_SEEDS["assignment"])
    master = [[rng.randint(1, 100) for _ in range(16)] for _ in range(16)]
    for tier, size in ASSIGNMENT_TIERS:
        matrix = [row[:size] for row in master[:size]]
        model = {"id": f"assignment_{tier}_{size}", "family": "assignment", "tier": tier,
                 "tier_size": size, "seed": FAMILY_SEEDS["assignment"], "n": size * size,
                 "c": [c for row in matrix for c in row], "rows": _assignment_rows(size),
                 "parameters": {"size": size, "costs": matrix, "table_cells": None, "dp_eligible": False,
                                "dp_eligibility_reason": "multiple_assignment_equality_rows"}}
        result.append(_complete(model, with_references))
    return result

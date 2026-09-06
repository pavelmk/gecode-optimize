#!/usr/bin/env python3
"""Extend the frozen boundary generators without imposing a study-size ceiling.

Every input inside the old domain is returned byte-for-byte unchanged. Larger
inputs continue the old random stream; matrix extensions add one outer shell at
a time, so requesting a larger matrix cannot change an earlier prefix. No
reference optimum or solver is used. Actual allocation failures, driver transport
guards and native numeric admission remain distinct from measured solve failure.
The inherited dp_eligible metadata describes the historical full-table DP only.
"""
import importlib.util
import json
from pathlib import Path
import random

_path = Path(__file__).resolve().with_name('boundary_instances.py')
_spec = importlib.util.spec_from_file_location('final_legacy_boundary', _path)
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)
category = legacy.category
GENERATOR_VERSION = 'boundary-prefix-v2-extension'
SOURCE_DEPENDENCIES = (_path,) + legacy.SOURCE_DEPENDENCIES


def _matrix(seed, original, old_maximum, size, upper):
    rng = random.Random(seed)
    matrix = [[0] * old_maximum for _ in range(old_maximum)]
    for i in range(original):
        for j in range(original):
            matrix[i][j] = rng.randint(1, upper)
    for i in range(old_maximum):
        for j in range(old_maximum):
            if i >= original or j >= original:
                matrix[i][j] = rng.randint(1, upper)
    for k in range(old_maximum, size):
        matrix.append([rng.randint(1, upper) for _ in range(k + 1)])
        for i in range(k):
            matrix[i].append(rng.randint(1, upper))
    return matrix


def make(name, size, variant='single'):
    category._require(type(name) is str and name in legacy.BOUNDS, 'unknown final category')
    minimum, old_maximum = legacy.BOUNDS[name]
    category._require(type(size) is int and size >= minimum, 'size must be an integer above family minimum')
    category._require(variant in (('uncorrelated', 'correlated') if name == 'knapsack' else ('single',)),
                      'invalid family variant')
    if size <= old_maximum:
        return legacy.make(name, size, variant)
    model = legacy.make(name, old_maximum, variant)
    rng = random.Random(model['seed'])
    p = model['parameters']
    if name == 'knapsack':
        items = []
        for _ in range(size):
            weight = rng.randint(1, 31)
            profit = rng.randint(1, 100) if variant == 'uncorrelated' else weight + rng.randint(0, 10)
            items.append((weight, profit))
        weights, profits = [w for w, _ in items], [p for _, p in items]
        capacity, cells = 6 * size, (size + 1) * (6 * size + 1)
        p.update(weights=[weights], profits=profits, capacities=[capacity], capacity=capacity,
                 table_cells=cells, dp_eligible=False, dp_eligibility_reason='full_table_cell_cap_exceeded')
        model.update(n=size, c=[-v for v in profits], rows=category.scaling._capacity_rows(weights, capacity))
    elif name == 'assignment':
        matrix = _matrix(model['seed'], 16, 32, size, 100)
        p.update(size=size, costs=matrix)
        model.update(n=size * size, c=[v for row in matrix for v in row],
                     rows=category.scaling._assignment_rows(size))
    elif name == 'facility_location':
        point = lambda: (rng.randint(0, 30), rng.randint(0, 30))
        sites = [point() for _ in range(12)]
        customers = [point() for _ in range(24)]
        opening = [rng.randint(15, 60) for _ in range(12)]
        sites += [point() for _ in range(4)]
        customers += [point() for _ in range(8)]
        opening += [rng.randint(15, 60) for _ in range(4)]
        for _ in range(16, size):
            sites.append(point()); customers.extend((point(), point()))
            opening.append(rng.randint(15, 60))
        p.update(facilities=size, customers=2 * size, opening_costs=opening,
                 assignment_costs=[[abs(a-x) + abs(b-y) + 1 for x, y in sites] for a, b in customers])
    elif name == 'bin_packing':
        weights = [rng.randint(2, 10) for _ in range(size)]
        bins = (size + 2) // 3
        capacity = max(max(weights), (sum(weights) + bins - 2) // (bins - 1))
        while category._first_fit(weights, capacity) > bins:
            capacity += 1
        p.update(items=size, bins=bins, weights=weights, capacity=capacity)
    elif name == 'production':
        demands = [rng.randint(1, 7) for _ in range(24)]
        storage, holding = rng.randint(3, 10), rng.randint(1, 4)
        def costs():
            fixed, unit = rng.randint(5, 20), rng.randint(2, 12)
            return [0 if q == 0 else fixed + unit*q + max(0, q-4)*5 for q in range(8)]
        matrix = [costs() for _ in range(24)]
        demands += [rng.randint(1, 7) for _ in range(24)]
        matrix += [costs() for _ in range(24)]
        for _ in range(48, size):
            demands.append(rng.randint(1, 7)); matrix.append(costs())
        p.update(periods=size, demands=demands, storage=storage, holding_cost=holding,
                 production_costs=matrix,
                 objective_constant=-holding * sum((size-i)*d for i, d in enumerate(demands)))
    else:
        if name == 'native_tsp':
            points = [(rng.randrange(100), rng.randrange(100)) for _ in range(size)]
            matrix = [[abs(a-x)+abs(b-y)+(i != j) for j, (x, y) in enumerate(points)]
                      for i, (a, b) in enumerate(points)]
        else:
            matrix = _matrix(model['seed'], 12, 32, size, 50)
        p.update(size=size)
        model.update(n=size, size=size, data=matrix)
    if name in ('facility_location', 'bin_packing', 'production'):
        model.update(category._formulation(name, p))
    model.update(id=f'{name}_{variant}_{size}', tier_size=size, natural_size=size,
                 generator_version=GENERATOR_VERSION,
                 prefix_policy='preserve legacy master blocks, then append stream values or matrix shells')
    model['dimensions'] = category._dimensions(model)
    model['input_variables'] = model['n']
    model['model_variables'] = model['modelled_variables'] = model['dimensions']['variables']
    return model


def _check_model(model):
    category._require(type(model) is dict, 'model must be an object')
    expected = make(model.get('category'), model.get('natural_size'), model.get('variant'))
    category._require(json.dumps({k: model.get(k) for k in expected}, sort_keys=True, allow_nan=False) ==
                      json.dumps(expected, sort_keys=True, allow_nan=False),
                      'final metadata or original formulation differs from deterministic input')


def semantic_hash(model):
    _check_model(model)
    return category.semantic_hash(model)


input_hash = semantic_hash


def validate_assignment(model, assignment):
    try:
        _check_model(model)
        category._require(type(assignment) is list and len(assignment) == model['n'] and
                          all(type(v) is int for v in assignment), 'expected exact integer assignment')
        original = dict(model)
        if model['category'] == 'knapsack':
            original['family'] = 'knapsack'
        validator = category.binary_validator if model['kind'] == 'binary' else category.native_validator
        checked = validator.validate_assignment(original, assignment)
        if checked['valid']:
            checked['domain_semantics_checked'] = True
        return checked
    except (ValueError, KeyError, TypeError, IndexError) as error:
        return {'valid': False, 'error': str(error)}


def encode_txt(model):
    _check_model(model)
    if model['kind'] == 'binary':
        lines = [f"{model['n']} {len(model['rows'])}", ' '.join(map(str, model['c']))]
        for row in model['rows']:
            lines.append(' '.join(map(str, [row['b'], len(row['a'])] + [v for pair in row['a'] for v in pair])))
        return '\n'.join(lines) + '\nincumbent 0\n'
    n = model['n']
    return (f"{model['family']} {n} 0 {n}\n" +
            ' '.join(str(c) for row in model['data'] for c in row) + '\n' +
            ' '.join('0' for _ in range(n)) + '\n')


expected_binary_text = encode_txt
expected_native_text = encode_txt

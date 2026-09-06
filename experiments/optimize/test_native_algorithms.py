#!/usr/bin/env python3
"""Pure trust-boundary checks; no solver, process or reference search is run."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
SOURCE = Path(__file__).with_name('benchmark_native_algorithms.py')
SPEC = importlib.util.spec_from_file_location('native_algorithms', SOURCE)
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class OriginalWitnessChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, _, cls.binary, cls.native = panel.prepare_inputs()

    def fixture(self, index=0, route='native'):
        unit = dict(panel.FROZEN_INPUTS[index], route=route)
        model = self.models[unit['id']]
        assignment = model['reference']['assignment'][:]
        n = len(assignment)
        full = assignment[:]
        rows = len(model['rows']) if unit['kind']=='binary' else 0
        globals_count = 0
        if unit['kind']=='weighted_queens':
            full += [value for row, col in enumerate(assignment)
                     for value in (col+row, col-row)]
            rows = 2*n
        if unit['kind']!='binary':
            full += [model['data'][row][col] for row, col in enumerate(assignment)]
            globals_count = n+(1 if unit['kind']=='native_tsp' else 3)
        raw = dict(
            schema_version=1, kind=unit['kind'], route=route,
            backend='Gecode native' if route=='native' else 'Gecode native frontier',
            backend_version='fixture', guarantee='exact', start_submitted=False,
            model_id=1, revision=1, model_columns=len(full), model_rows=rows,
            model_globals=globals_count, status='optimal', has_solution=True,
            solution_validated=True, assignment=assignment, full_values=full,
            objective=unit['objective'], best_bound=unit['objective'],
            absolute_gap=0, relative_gap=0, build_seconds=0.001,
            solve_seconds=0.002, driver_seconds=0.004,
        )
        for key in ('nodes', 'expanded_nodes', 'budget_nodes',
                    'peak_open_nodes', 'unresolved_regions'):
            raw[key] = None if route=='native' else 0
        return unit, model, raw

    def check(self, fixture):
        unit, model, raw = fixture
        return panel.checked_result(raw, unit, model, self.binary, self.native)

    def test_stored_binary_and_global_witnesses(self):
        for index in (0, 6, 7):
            with self.subTest(index=index):
                accepted = self.check(self.fixture(index))
                self.assertTrue(accepted['completed'])
                self.assertTrue(accepted['witness_checked'])
        self.assertTrue(self.check(self.fixture(route='dfs'))['completed'])

    def test_infeasible_source_assignment_is_rejected(self):
        unit, model, raw = self.fixture()
        raw['assignment'] = raw['full_values'] = [1]*model['n']
        # All items exceed the original knapsack's capacity.
        self.assertFalse(self.binary.validate_assignment(model, raw['assignment'])['valid'])
        raw['objective'] = sum(model['c'])
        raw['best_bound'] = raw['objective']
        with self.assertRaises(ValueError):
            self.check((unit, model, raw))

    def test_wrong_objective_or_substituted_model_is_rejected(self):
        for field, delta in (('objective', 1), ('model_columns', 1),
                             ('model_rows', 1), ('model_globals', 1)):
            with self.subTest(field=field):
                fixture = self.fixture()
                fixture[2][field] += delta
                with self.assertRaises(ValueError):
                    self.check(fixture)

    def test_feasible_suboptimal_point_cannot_claim_optimal(self):
        unit, model, raw = self.fixture()
        raw['assignment'] = raw['full_values'] = [0]*model['n']
        # Selecting no items is feasible but is strictly worse than -2464.
        self.assertEqual(self.binary.validate_assignment(model, raw['assignment']),
                         dict(valid=True, objective=0, domain_semantics_checked=True))
        raw['objective'] = raw['best_bound'] = 0
        with self.assertRaises(ValueError):
            self.check((unit, model, raw))
        raw.update(status='time_limit', best_bound=-2464, absolute_gap=2464, relative_gap=1)
        result = self.check((unit, model, raw))
        self.assertFalse(result['completed'])
        self.assertTrue(result['witness_checked'])

    def test_empty_limited_result_is_censored(self):
        fixture = self.fixture()
        fixture[2].update(status='time_limit', has_solution=False,
                          solution_validated=False, assignment=[], full_values=[],
                          objective=None, absolute_gap=None, relative_gap=None)
        result = self.check(fixture)
        self.assertFalse(result['completed'])
        self.assertFalse(result['witness_checked'])
        self.assertIsNone(result['objective'])
        self.assertIsNone(result['absolute_primal_gap_to_oracle'])

    def test_global_semantics_and_auxiliary_values_are_checked(self):
        for index in (6, 7):
            unit, model, raw = self.fixture(index)
            bad = copy.deepcopy(raw)
            bad['assignment'][0] = bad['assignment'][1]
            bad['full_values'][0] = bad['assignment'][0]
            self.assertFalse(self.native.validate_assignment(model, bad['assignment'])['valid'])
            with self.assertRaises(ValueError):
                self.check((unit, model, bad))
            raw['full_values'][-1] += 1
            with self.assertRaises(ValueError):
                self.check((unit, model, raw))

    def test_malformed_protocol_and_impossible_claims_are_rejected(self):
        for field, value in (
            ('objective', float('nan')), ('best_bound', float('inf')),
            ('backend', 'HiGHS'), ('start_submitted', True),
            ('status', 'infeasible'), ('status', 'invented'),
            ('schema_version', True), ('solution_validated', False),
            ('solve_seconds', 1), ('nodes', 1),
        ):
            with self.subTest(field=field, value=value):
                fixture = self.fixture()
                fixture[2][field] = value
                with self.assertRaises(ValueError):
                    self.check(fixture)
        for text in ('{"x":NaN}', '{"x":1,"x":2}'):
            with self.assertRaises(ValueError):
                panel.strict_json(text)


if __name__=='__main__':
    unittest.main()

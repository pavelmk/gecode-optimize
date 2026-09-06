#!/usr/bin/env python3
"""Pure adaptive-runner conformance: no solver or subprocess execution."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('boundary_runner_test', Path(__file__).with_name('benchmark_boundaries.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def fixture(category='knapsack'):
    size = 8 if category=='knapsack' else 4
    model = runner.generator.make(category, size, 'uncorrelated' if category=='knapsack' else 'single')
    if category=='knapsack':
        values = [0]*size
    elif category=='native_tsp':
        values = [1, 2, 3, 0]
    else:
        values = [1, 3, 0, 2]
    check = runner.generator.validate_assignment(model, values)
    assert check['valid']
    full = values[:]
    if category=='weighted_queens':
        full += [v for i, x in enumerate(values) for v in (x+i, x-i)]
    if model['kind']!='binary':
        full += [model['data'][i][x] for i, x in enumerate(values)]
    raw = dict(schema_version=1, kind=model['kind'], route='native', backend='Gecode native',
               backend_version='fixture', guarantee='exact', start_submitted=False,
               model_id=1, revision=1, model_columns=model['model_variables'],
               model_rows=model['dimensions']['rows'], model_globals=model['dimensions']['globals'],
               status='optimal', has_solution=True, solution_validated=True,
               assignment=values, full_values=full, objective=check['objective'],
               best_bound=check['objective'], absolute_gap=0, relative_gap=0,
               build_seconds=0.001, solve_seconds=0.1, driver_seconds=0.102,
               nodes=None, expanded_nodes=None, budget_nodes=None,
               peak_open_nodes=None, unresolved_regions=None)
    return model, raw


class FakeSearch(runner.Search):
    def __init__(self, surface):
        self.surface = surface
        self.records, self.decisions, self.models = [], [], {}
        self.sources, self.runtime_sources, self.provenance = {}, {}, {}
        self.expected = {c: {'libraries': []} for c in runner.COHORTS}
        self.directories = {c: [] for c in runner.COHORTS}
        self.binary = Path('fake-driver')
        self.output = Path('unused')
        self.started = time.monotonic()
        self.complete = False

    def publish(self):
        pass

    def execute(self, category, size, variant, cohort, repetition, probe=False):
        self.records.append(dict(category=category, size=size, variant=variant,
                                 cohort=cohort, repetition=repetition, probe=probe,
                                 passed=self.surface(category, size, cohort, repetition)))


class BoundaryTests(unittest.TestCase):
    def test_no_oracle_claim_even_for_plausible_backend_optimum(self):
        model, raw = fixture()
        # All-zero knapsack is feasible. Deliberately do not establish optimality.
        checked = runner.validate(raw, model)
        self.assertTrue(checked['passed'])
        self.assertTrue(checked['primal_checked'])
        self.assertTrue(checked['backend_reported_optimal'])
        self.assertFalse(checked['independent_optimality_verified'])
        self.assertNotIn('reference', model)

    def test_native_original_and_full_auxiliary_witnesses(self):
        for category in ('native_tsp', 'weighted_queens'):
            model, raw = fixture(category)
            self.assertTrue(runner.validate(raw, model)['primal_checked'])
            wrong = copy.deepcopy(raw)
            wrong['full_values'][-1] += 1
            with self.assertRaises(ValueError):
                runner.validate(wrong, model)
            wrong = copy.deepcopy(raw)
            wrong['assignment'][0] = wrong['assignment'][1]
            with self.assertRaises(ValueError):
                runner.validate(wrong, model)
            wrong = copy.deepcopy(raw)
            wrong['model_columns'] = model['n']
            with self.assertRaises(ValueError):
                runner.validate(wrong, model)

    def test_protocol_nonfinite_objective_and_gap_faults(self):
        model, raw = fixture()
        for field, value in [('schema_version', True), ('guarantee', 'numerical'),
                             ('start_submitted', True), ('model_id', True),
                             ('objective', float('nan')), ('objective', 1),
                             ('best_bound', 1), ('relative_gap', 1), ('nodes', 0)]:
            with self.subTest(field=field, value=value):
                wrong = dict(raw, **{field: value})
                with self.assertRaises(ValueError):
                    runner.validate(wrong, model)

    def test_budget_boundary_and_limit_absent_point(self):
        model, raw = fixture()
        raw.update(solve_seconds=10, driver_seconds=10.01)
        self.assertTrue(runner.validate(raw, model)['passed'])
        raw['solve_seconds'] = 10.000001
        self.assertFalse(runner.validate(raw, model)['passed'])
        raw.update(status='time_limit', has_solution=False, solution_validated=False,
                   assignment=[], full_values=[], objective=None, best_bound=None,
                   absolute_gap=None, relative_gap=None)
        checked = runner.validate(raw, model)
        self.assertFalse(checked['passed'])
        self.assertFalse(checked['primal_checked'])

    def test_better_limited_witness_rejects_peer_reported_optimum(self):
        model, raw = fixture()
        raw['assignment'][0] = 1
        raw['full_values'][0] = 1
        checked = runner.generator.validate_assignment(model, raw['assignment'])
        self.assertTrue(checked['valid'])
        self.assertLess(checked['objective'], 0)
        raw.update(status='time_limit', objective=checked['objective'], best_bound=None,
                   absolute_gap=None, relative_gap=None)
        with tempfile.TemporaryDirectory() as directory:
            search = FakeSearch(lambda *args: True)
            search.output = Path(directory)
            key = 'knapsack-8-uncorrelated'
            search.records.append(dict(case=key, backend_reported_optimal=True,
                                       objective=0, best_bound=0))
            search.model = lambda *args: (key, model)
            outcome = dict(stdout=json.dumps(raw).encode(), stderr=b'', returncode=0,
                           hard_timeout=False, output_limit=False, external_seconds=0.01)
            with mock.patch.object(runner, 'capture', return_value=outcome):
                with self.assertRaisesRegex(ValueError, 'Feasible peer'):
                    runner.Search.execute(search, 'knapsack', 8, 'uncorrelated', 'after', 1)
            self.assertEqual(search.records[-1]['status'], 'error')
            self.assertFalse(search.records[-1]['passed'])

    def test_final_publication_expiry_clears_completion(self):
        search = FakeSearch(lambda *args: True)
        def publish():
            if search.complete:
                search.started -= runner.WHOLE_SECONDS
        search.publish = publish
        with mock.patch.object(runner, 'LIMITS', {'assignment': (2, 4, 8)}), \
             mock.patch.object(runner, 'sha', return_value=runner.DRIVER_HASH), \
             mock.patch('builtins.print'):
            with self.assertRaisesRegex(ValueError, 'during publication'):
                search.run()
        self.assertFalse(search.complete)

    def run_search(self, surface, category='assignment', limits=(2, 4, 16)):
        search = FakeSearch(surface)
        with mock.patch.object(runner, 'LIMITS', {category: limits}), \
             mock.patch.object(runner, 'sha', return_value=runner.DRIVER_HASH), \
             mock.patch('builtins.print'):
            search.run()
        return search

    def test_independent_cached_bisection_and_neighbor_confirmation(self):
        search = self.run_search(lambda c, n, cohort, r: n <= (7 if cohort=='before' else 11))
        self.assertTrue(search.complete)
        for cohort, maximum in [('before', 7), ('after', 11)]:
            confirmed = [n for n in search.sizes('assignment') if search.passed('assignment', n, cohort, True)]
            self.assertEqual(max(confirmed), maximum)
            self.assertEqual(len(search.rows('assignment', maximum+1, cohort)), 2)
        keys = [(r['category'], r['size'], r['variant'], r['cohort'], r['repetition']) for r in search.records]
        self.assertEqual(len(keys), len(set(keys)))
        for n in search.sizes('assignment'):
            if n <= 8:
                first = [x for x in search.records if x['size']==n and x['repetition']==1]
                self.assertEqual({x['cohort'] for x in first}, set(runner.COHORTS))
            else:
                self.assertEqual(search.rows('assignment', n, 'before'), [])
                self.assertTrue(search.rows('assignment', n, 'after'))
        self.assertEqual(max(x['size'] for x in search.records if x['cohort']=='before'), 8)
        self.assertTrue(any(x['size']>8 and x['cohort']=='after' for x in search.records))
        for decision in search.decisions:
            if decision['reason']=='shared timing point within smaller boundary':
                self.assertLessEqual(decision['size'], 8)
                self.assertEqual(decision['cohorts'], list(runner.COHORTS))

    def test_unprobed_nonmonotonic_island_is_unknown_not_failure(self):
        # A passing island above the first failure exists mathematically, but
        # this heuristic is intentionally not authorized to explore it.
        search = self.run_search(lambda c, n, cohort, r: n<=4 or n==16)
        for cohort in runner.COHORTS:
            self.assertTrue(search.passed('assignment', 4, cohort, True))
            self.assertEqual(search.rows('assignment', 16, cohort), [])
            self.assertEqual(search.rows('assignment', 15, cohort), [])
            self.assertFalse(search.passed('assignment', 16, cohort, True))
        self.assertNotIn(16, search.sizes('assignment'))
        self.assertTrue(all(d['size']!=16 for d in search.decisions))
        self.assertEqual(max(search.sizes('assignment')), 8)

    def test_expansion_reaches_cap_only_for_passing_cohort(self):
        search = self.run_search(lambda c, n, cohort, r: n<=5 if cohort=='before' else True)
        self.assertTrue(search.passed('assignment', 5, 'before', True))
        self.assertTrue(search.passed('assignment', 16, 'after', True))
        self.assertEqual(search.rows('assignment', 16, 'before'), [])
        self.assertEqual(max(r['size'] for r in search.records if r['cohort']=='before'), 8)

    def test_failed_confirmation_downgrades_without_retrying(self):
        search = self.run_search(lambda c, n, cohort, r: n<=7 and not (n==7 and r==2))
        for cohort in runner.COHORTS:
            self.assertFalse(search.passed('assignment', 7, cohort, True))
            self.assertTrue(search.passed('assignment', 6, cohort, True))
            self.assertEqual([r['passed'] for r in search.rows('assignment', 7, cohort)], [True, False])

    def test_knapsack_confirmation_requires_both_variants_twice(self):
        search = self.run_search(lambda c, n, cohort, r: n<=5, 'knapsack', (2, 4, 8))
        for cohort in runner.COHORTS:
            rows = search.rows('knapsack', 5, cohort)
            self.assertEqual({(r['variant'], r['repetition']) for r in rows},
                             {(v, r) for v in ('uncorrelated', 'correlated') for r in (1, 2)})
            self.assertTrue(search.passed('knapsack', 5, cohort, True))
            rows[0]['passed'] = False
            self.assertFalse(search.passed('knapsack', 5, cohort, True))


if __name__=='__main__':
    unittest.main()

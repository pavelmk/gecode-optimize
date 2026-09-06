#!/usr/bin/env python3
"""Untimed runner checks: reject incomplete evidence and keep searches independent."""
import copy
import importlib.util
import itertools
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('configured_runner_tested',
    Path(__file__).with_name('benchmark_configured.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def zeros(names, **extra):
    return dict.fromkeys(names.split(), 0) | extra


def native_result(model):
    feasible = [list(p) for p in itertools.product((0, 1), repeat=model['n'])
                if runner.generator.validate_assignment(model, list(p))['valid']]
    values = min(feasible, key=lambda p: sum(a*b for a, b in zip(model['c'], p)))
    objective = sum(a*b for a, b in zip(model['c'], values))
    return dict(schema_version=1, kind='binary', route='native', guarantee='exact',
        start_submitted=False, backend='Gecode native', backend_version='test-fixture', model_id=1, revision=3,
        solve_seconds=0.02, backend_solve_seconds=0.01, build_seconds=0.01, driver_seconds=0.04,
        model_columns=model['n'], model_rows=len(model['rows']), model_globals=0,
        status='optimal', has_solution=True, solution_validated=True, assignment=values,
        full_values=values[:], objective=objective, best_bound=objective, absolute_gap=0, relative_gap=0,
        nodes=None, expanded_nodes=None, budget_nodes=None, peak_open_nodes=None, unresolved_regions=None,
        algorithm_configuration=dict(entry_point='solve_native', search_order='native_bab',
            checked_lp=False, lp_frequency=None, bound_tightening=False, bound_change_interval=None,
            root_cover_cuts=False, binary_reliability=False, neighborhoods=False,
            knapsack_dp_eligible_route=True, presolve=False, max_open_nodes=None,
            cover_settings=None, branching_settings=None, neighborhood_settings=None),
        relaxation=zeros('lp_calls valid_bounds rejected_bounds numerical_infeasibility_reports '
            'certificate_evaluations conditional_checks variable_fixings variable_bound_tightenings lp_seconds',
            root_cover=zeros('rounds augmentations cuts nonzeros work projected_coordinates unsupported_rows '
                'oversized_rows separated_cuts duplicate_cuts arithmetic_rejections lp_calls valid_bounds '
                'rejected_bounds numerical_infeasibility_reports lp_seconds', requested=False, completion='NotRequested')),
        branching=zeros('decisions manual_splits fallback_decisions probe_status_calls completed_pairs '
            'published_pairs finite_samples zero_gain_samples failed_directions reliable_candidates '
            'probe_propagations budget_nodes work history_entries probe_lp_calls probe_lp_seconds', requested=False),
        neighborhood=zeros('attempts eligible_variables source_entries coordinator_work status_attempts '
            'completed_status_calls failed_nodes feasible_candidates accepted_improvements peak_local_spaces '
            'peak_total_spaces budget_nodes elapsed_seconds', requested=False, completion='NotStarted', stop_reason=None))


class EvidenceValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = runner.generator.make('knapsack', 8, 'uncorrelated')
        cls.good = native_result(cls.model)

    def test_checked_original_witness_is_a_pass(self):
        result = runner.validate(copy.deepcopy(self.good), self.model, 'native')
        self.assertTrue(result['passed'])
        self.assertTrue(result['primal_checked'])
        self.assertFalse(result['independent_optimality_verified'])

    def test_no_partial_or_fabricated_protocol(self):
        mutations = [
            ('schema_version', True), ('backend', 'Gecode native + invented'),
            ('backend_version', ''), ('start_submitted', True), ('revision', True),
            ('status', 'unsupported'), ('has_solution', 1), ('solution_validated', False),
            ('assignment', [0]*8), ('full_values', []), ('best_bound', self.good['objective']+1),
            ('relative_gap', 1), ('model_columns', True), ('solve_seconds', float('nan')),
            ('backend_solve_seconds', 1), ('relaxation', {}), ('branching', {}), ('neighborhood', {}),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                raw = copy.deepcopy(self.good)
                raw[key] = value
                with self.assertRaises((ValueError, TypeError, KeyError)):
                    runner.validate(raw, self.model, 'native')
        for key in self.good:
            with self.subTest(missing=key):
                raw = copy.deepcopy(self.good)
                del raw[key]
                with self.assertRaises((ValueError, TypeError, KeyError)):
                    runner.validate(raw, self.model, 'native')

    def test_flags_do_not_replace_mechanism_observations(self):
        paths = [('relaxation', 'lp_calls'), ('branching', 'probe_status_calls'),
                 ('neighborhood', 'status_attempts')]
        for group, counter in paths:
            for value in (None, -1, 1.5, True, 1):
                with self.subTest(group=group, value=value):
                    raw = copy.deepcopy(self.good)
                    raw[group][counter] = value
                    with self.assertRaises(ValueError):
                        runner.validate(raw, self.model, 'native')
        for key, value in [('presolve', True), ('checked_lp', 0), ('entry_point', 'solve_native_lp')]:
            with self.subTest(configuration=key):
                raw = copy.deepcopy(self.good)
                raw['algorithm_configuration'][key] = value
                with self.assertRaises(ValueError):
                    runner.validate(raw, self.model, 'native')

    def test_timeout_and_late_optimum_remain_failures(self):
        raw = copy.deepcopy(self.good)
        raw.update(status='time_limit', solve_seconds=10, driver_seconds=10.02)
        self.assertFalse(runner.validate(raw, self.model, 'native')['passed'])
        raw.update(status='optimal', solve_seconds=10.001)
        self.assertFalse(runner.validate(raw, self.model, 'native')['passed'])


class ObservationAndPolicyTest(unittest.TestCase):
    def setUp(self):
        self.search = runner.ConfiguredSearch.__new__(runner.ConfiguredSearch)
        self.search.records = []
        self.search.pilot = False
        self.search.policy = {'families': {family: {'route': 'native'} for family in runner.legacy.LIMITS}}
        self.search.policy['families']['knapsack']['outside_dp_route'] = 'lp-cuts'
        self.search.policy['families']['assignment']['route'] = 'lp-root'

    @staticmethod
    def row(variant='uncorrelated', repetition=1, **updates):
        return dict(category='knapsack', size=8, cohort='after', variant=variant, repetition=repetition,
                    probe=False, passed=True, status='optimal', primal_checked=True,
                    backend_reported_optimal=True, solve_seconds=0.1) | updates

    def test_variant_and_repetition_completeness(self):
        rows = [self.row(v, r) for v in ('uncorrelated', 'correlated') for r in (1, 2)]
        self.search.records = rows
        self.assertTrue(self.search.passed('knapsack', 8, 'after', confirmed=True))
        for index in range(4):
            self.search.records = rows[:index]+rows[index+1:]
            self.assertFalse(self.search.passed('knapsack', 8, 'after', confirmed=True))
        self.search.records = [self.row(), self.row()]
        self.assertFalse(self.search.passed('knapsack', 8, 'after'))
        self.search.records = [self.row(v, 1) for v in ('uncorrelated', 'correlated')]*2
        self.assertFalse(self.search.passed('knapsack', 8, 'after', confirmed=True))
        self.search.records = [self.row(v, 2) for v in ('uncorrelated', 'correlated')]
        self.assertFalse(self.search.passed('knapsack', 8, 'after'))

    def test_pending_partial_failed_and_other_cohort_do_not_count(self):
        good = [self.row(v) for v in ('uncorrelated', 'correlated')]
        self.search.records = good
        self.assertTrue(self.search.passed('knapsack', 8, 'after'))
        for updates in ({'status': 'pending'}, {'status': 'error'}, {'passed': False},
                        {'primal_checked': None}, {'backend_reported_optimal': None},
                        {'solve_seconds': None}, {'solve_seconds': 10.01}, {'cohort': 'before'}, {'probe': True}):
            with self.subTest(updates=updates):
                self.search.records = [good[0], good[1] | updates]
                self.assertFalse(self.search.passed('knapsack', 8, 'after'))
        self.search.records = good + [self.row('correlated', 2, passed=False, status='time_limit')]
        self.assertFalse(self.search.passed('knapsack', 8, 'after'))

    def test_frozen_family_dispatch_and_dp_boundary(self):
        eligible = runner.generator.make('knapsack', 407, 'uncorrelated')
        outside = runner.generator.make('knapsack', 408, 'uncorrelated')
        self.assertEqual(self.search.route('knapsack', eligible, 'after'), 'native')
        self.assertEqual(self.search.route('knapsack', outside, 'after'), 'lp-cuts')
        self.assertEqual(self.search.route('knapsack', outside, 'before'), 'native')
        assignment = runner.generator.make('assignment', 3)
        self.assertEqual(self.search.route('assignment', assignment, 'after'), 'lp-root')
        self.assertEqual(self.search.route('assignment', assignment, 'before'), 'native')
        self.search.pilot = True
        self.assertEqual(self.search.route('assignment', assignment, 'after'), 'native')


if __name__ == '__main__':
    unittest.main(verbosity=2)

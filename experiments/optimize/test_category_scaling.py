#!/usr/bin/env python3
"""Pure runner checks with original reference witnesses; no solver subprocesses."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

sys.dont_write_bytecode = True
PATH = Path(__file__).with_name('benchmark_category_scaling.py').resolve()
SPEC = importlib.util.spec_from_file_location('category_scaling_runner', PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class CategoryRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.frozen = cls.root/'frozen'
        cls.pin = runner.freeze(cls.frozen)['manifest_sha256']
        cls.common, cls.generator = runner.modules()
        cls.manifest, cls.models, _ = runner.read_frozen(
            cls.frozen, cls.pin, cls.common, cls.generator)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_fixed_categories_shapes_and_alternating_slots(self):
        units = self.manifest['records']
        self.assertEqual([(u['category'], u['variant'], u['input_variables']) for u in units], runner.PLANNED)
        self.assertEqual(len(units), 33)
        self.assertEqual(len({u['category'] for u in units}), 7)
        self.assertEqual(self.manifest['protocol']['solver_seconds'], 10)
        self.assertEqual(self.manifest['protocol']['process_seconds'], 11)
        self.assertEqual(self.manifest['protocol']['whole_seconds'], 1500)
        self.assertEqual(self.manifest['protocol']['expected_measured_runs'], 132)
        slots = list(runner.planned_slots(self.manifest))
        self.assertEqual(len(slots), 132)
        self.assertEqual([(c, r) for _, c, r in slots[:2]], [('before', 1), ('after', 1)])
        self.assertEqual([(c, r) for _, c, r in slots[66:68]], [('after', 2), ('before', 2)])
        tsp = [u for u in units if u['category']=='native_tsp']
        queens = [u for u in units if u['category']=='weighted_queens']
        self.assertEqual([(u['input_variables'], u['model_variables']) for u in tsp],
                         [(4, 8), (8, 16), (12, 24), (16, 32)])
        self.assertEqual([(u['input_variables'], u['model_variables']) for u in queens],
                         [(4, 16), (8, 32), (10, 40), (12, 48)])

    def test_measured_preflight_does_not_recompute_optima(self):
        original = self.generator.verify_reference
        def cheap(model, **kwargs):
            self.assertFalse(kwargs.get('recompute', False))
            result = original(model, **kwargs)
            self.assertFalse(result['optimality_recomputed'])
            return result
        with mock.patch.object(self.generator, 'verify_reference', side_effect=cheap) as checked:
            _, models, hashes = runner.read_frozen(self.frozen, self.pin, self.common, self.generator)
        self.assertEqual(checked.call_count, 33)
        self.assertEqual(len(models), 33)
        self.assertEqual(len(hashes), 68)

    def test_frozen_hash_source_and_dimensions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'manifest hash'):
            runner.read_frozen(self.frozen, '0'*64, self.common, self.generator)
        changed = self.root/'changed'
        shutil.copytree(self.frozen, changed)
        path = changed/self.manifest['records'][0]['txt']
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError, 'model bytes'):
            runner.read_frozen(changed, self.pin, self.common, self.generator)
        with mock.patch.object(runner, 'source_hashes', return_value={}):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                runner.read_frozen(self.frozen, self.pin, self.common, self.generator)
        models = copy.deepcopy(list(self.models.values()))
        next(m for m in models if m['kind']=='native_tsp')['modelled_variables'] = 4
        with self.assertRaisesRegex(ValueError, 'variable counts'):
            runner.ordered_models(models)

    def observation_fixture(self, kind='binary'):
        unit = next(u for u in self.manifest['records'] if u['kind']==kind)
        model = self.models[unit['id']]
        assignment = model['reference']['assignment'][:]
        full = assignment[:]
        if kind=='weighted_queens':
            full += [v for i, x in enumerate(assignment) for v in (x+i, x-i)]
        if kind!='binary':
            full += [model['data'][i][x] for i, x in enumerate(assignment)]
        raw = dict(schema_version=1, kind=kind, route='native', backend='Gecode native',
                   backend_version='fixture', guarantee='exact', start_submitted=False,
                   model_id=1, revision=1, model_columns=unit['model_variables'],
                   model_rows=unit['dimensions']['rows'], model_globals=unit['dimensions']['globals'],
                   status='optimal', has_solution=True, solution_validated=True,
                   assignment=assignment, full_values=full, objective=unit['objective'],
                   best_bound=unit['objective'], absolute_gap=0, relative_gap=0,
                   build_seconds=0.001, solve_seconds=10, driver_seconds=10.1,
                   nodes=None, expanded_nodes=None, budget_nodes=None,
                   peak_open_nodes=None, unresolved_regions=None)
        return unit, model, raw

    def test_binary_and_native_original_witnesses_and_auxiliaries(self):
        for kind in ('binary', 'native_tsp', 'weighted_queens'):
            with self.subTest(kind=kind):
                unit, model, raw = self.observation_fixture(kind)
                checked = runner.checked_observation(raw, unit, model, self.common, self.generator)
                self.assertTrue(checked['proved_within_limit'])
                wrong = copy.deepcopy(raw)
                wrong['full_values'][-1] += 1
                with self.assertRaises(ValueError):
                    runner.checked_observation(wrong, unit, model, self.common, self.generator)
                wrong = copy.deepcopy(raw)
                wrong['model_columns'] -= 1
                with self.assertRaisesRegex(ValueError, 'dimensions'):
                    runner.checked_observation(wrong, unit, model, self.common, self.generator)

    def test_exact_ten_second_boundary_and_censored_no_solution(self):
        unit, model, raw = self.observation_fixture()
        raw['solve_seconds'] = 10.000001
        result = runner.checked_observation(raw, unit, model, self.common, self.generator)
        self.assertTrue(result['completed'])
        self.assertFalse(result['proved_within_limit'])
        raw.update(status='time_limit', has_solution=False, solution_validated=False,
                   assignment=[], full_values=[], objective=None, best_bound=None,
                   absolute_gap=None, relative_gap=None, solve_seconds=10)
        result = runner.checked_observation(raw, unit, model, self.common, self.generator)
        self.assertFalse(result['completed'])
        self.assertFalse(result['proved_within_limit'])

    def records(self):
        return [dict(runner.pending_record(unit, cohort, repetition), attempted=True,
                     proved_within_limit=True, status='optimal', solve_seconds=1,
                     external_seconds=1.01, objective=unit['objective'], best_bound=unit['objective'])
                for unit, cohort, repetition in runner.planned_slots(self.manifest)]

    def test_knapsack_requires_every_variant_repeat_and_keeps_stress_separate(self):
        records = self.records()
        units = {u['id']: u for u in self.manifest['records']}
        for record in records:
            unit = units[record['case']]
            if (unit['category']=='knapsack' and unit['variant']=='correlated' and
                unit['tier']=='large' and record['cohort']=='before' and record['repetition']==2):
                record.update(proved_within_limit=False, status='time_limit', solve_seconds=10)
        summary = runner.summarize(records, self.manifest, {}, True, 1)
        knapsack = summary['categories'][0]
        self.assertEqual(knapsack['before']['largest_main_group_proved_model_variables'], 128)
        self.assertEqual(knapsack['after']['largest_main_group_proved_model_variables'], 384)
        self.assertEqual(knapsack['ratio_of_largest_main_group_proved_model_variables'], 3)
        large = knapsack['main_groups'][-1]
        self.assertEqual(large['variant_count'], 2)
        self.assertEqual(large['before']['required_runs'], 4)
        self.assertEqual(large['before']['proved'], 3)
        self.assertFalse(large['before']['proved_all'])
        for cohort in ('before', 'after'):
            self.assertEqual(knapsack[cohort]['largest_any_sampled_group_proved_model_variables'], 512)
            self.assertEqual(knapsack[cohort]['largest_any_sampled_group_variant_count'], 1)
            self.assertTrue(knapsack[cohort]['largest_any_sampled_group_stress'])
        case = next(c for c in summary['cases'] if c['category']=='knapsack' and
                    c['variant']=='correlated' and c['tier']=='large')
        self.assertIsNone(case['median_paired_solve_seconds_ratio_after_before'])
        self.assertEqual(case['before']['internal_seconds'], [1, 10])

    def test_duplicate_repetitions_or_failed_integrity_cannot_prove_capacity(self):
        records = self.records()
        target = self.manifest['records'][-2]['id']
        for r in records:
            if r['case']==target and r['cohort']=='before':
                r['repetition'] = 1
        summary = runner.summarize(records, self.manifest, {}, True, 1)
        case = next(c for c in summary['cases'] if c['id']==target)
        self.assertFalse(case['before']['proved_all'])
        invalid = runner.summarize(records, self.manifest, {}, False, 1)
        for category in invalid['categories']:
            self.assertIsNone(category['ratio_of_largest_main_group_proved_model_variables'])
            self.assertIsNone(category['after']['largest_any_sampled_group_proved_model_variables'])

    def probe_fixture(self, name):
        work = self.root/name
        before, after = work/'before/lib', work/'after/lib'
        before.mkdir(parents=True)
        after.mkdir(parents=True)
        for path, contents in ((before/'libgecodeoptimize.dylib', 'before'),
                               (after/'libgecodeoptimize.dylib', 'after')):
            path.write_text(contents)
        binary = work/'driver'
        binary.write_text('not executed')
        baseline = work/'before/manifest.json'
        runner.write(baseline, dict(
            source_head=self.common.BASELINE_SOURCE, compiled_product=self.common.BASELINE_COMPILED,
            files=[dict(copy='lib/libgecodeoptimize.dylib', sha256=runner.sha(before/'libgecodeoptimize.dylib'))]))
        args = SimpleNamespace(freeze_dir=self.frozen, manifest_sha256=self.pin, binary=binary,
                               before_libraries=[before], after_libraries=[after],
                               baseline_manifest=baseline, output_dir=work/'results')
        _, _, raw = self.observation_fixture()
        raw.update(solve_seconds=0.001, driver_seconds=0.003)
        def outcome(cohort):
            path = before if cohort=='before' else after
            return dict(returncode=0, hard_timeout=False, output_limit=False, external_seconds=0.01,
                        stdout=json.dumps(raw).encode(), stderr=(str(path/'libgecodeoptimize.dylib')+'\n').encode())
        return args, outcome

    def test_failed_probe_retains_all_required_unattempted_slots(self):
        args, outcome = self.probe_fixture('probe-test')
        capture = mock.Mock(side_effect=[outcome('before'), dict(
            returncode=2, hard_timeout=False, output_limit=False, external_seconds=0.01,
            stdout=b'', stderr=b'fixture loader rejection')])
        real_load = runner.load_module
        def load(name, path):
            return SimpleNamespace(capture_command=capture) if name=='category_capture' else real_load(name, path)
        with mock.patch.object(runner, 'load_module', side_effect=load), \
             mock.patch.object(runner.subprocess, 'check_output', return_value='fixture-head\n'):
            self.assertEqual(runner.measure(args, time.monotonic()), 1)
        self.assertEqual(capture.call_count, 2)
        report = json.loads((args.output_dir/'report.json').read_text())
        self.assertFalse(report['comparison_valid'])
        self.assertEqual([p['status'] for p in report['loader_probes']], ['validated', 'failed'])
        self.assertEqual(len(report['records']), 132)
        self.assertTrue(all(r['status']=='not_run_preflight' and not r['attempted'] for r in report['records']))
        self.assertEqual((args.output_dir/'provenance-after.stderr').read_bytes(), b'fixture loader rejection')
        summary = json.loads((args.output_dir/'summary.json').read_text())
        self.assertEqual(summary['required_runs'], 132)
        self.assertEqual(summary['recorded_runs'], 132)
        self.assertTrue(all(not c['after']['proved_all'] for c in summary['cases']))

    def test_whole_deadline_keeps_all_cases_without_launching_them(self):
        args, outcome = self.probe_fixture('deadline-test')
        clock = [0.0]
        count = [0]
        def capture(*args, **kwargs):
            count[0] += 1
            result = outcome('before' if count[0]==1 else 'after')
            if count[0]==2:
                clock[0] = 1501.0
            return result
        real_load = runner.load_module
        def load(name, path):
            return SimpleNamespace(capture_command=capture) if name=='category_capture' else real_load(name, path)
        with mock.patch.object(runner, 'load_module', side_effect=load), \
             mock.patch.object(runner.subprocess, 'check_output', return_value='fixture-head\n'), \
             mock.patch.object(runner.time, 'monotonic', side_effect=lambda: clock[0]), \
             mock.patch('builtins.print'):
            self.assertEqual(runner.measure(args, 0), 1)
        self.assertEqual(count[0], 2)
        report = json.loads((args.output_dir/'report.json').read_text())
        self.assertEqual(len(report['records']), 132)
        self.assertTrue(all(r['status']=='not_run_whole_limit' and not r['attempted'] for r in report['records']))
        self.assertFalse(report['comparison_valid'])


if __name__=='__main__':
    unittest.main()

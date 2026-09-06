#!/usr/bin/env python3
"""Small runner conformance checks; no subprocesses or solver timings."""
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
PATH = Path(__file__).with_name('benchmark_capacity_scaling.py').resolve()
SPEC = importlib.util.spec_from_file_location('capacity_scaling', PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ScalingRunnerTests(unittest.TestCase):
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

    def test_freeze_has_exact_preregistered_shapes_and_ten_second_budget(self):
        pairs = [(record['family'], record['variables']) for record in self.manifest['records']]
        self.assertEqual(pairs, runner.PLANNED)
        self.assertEqual(len(pairs), 13)
        self.assertEqual(self.manifest['protocol']['solver_seconds'], 10)
        self.assertEqual(self.manifest['protocol']['expected_measured_runs'], 52)
        self.assertTrue(self.manifest['records'][-1]['stress'])
        self.assertFalse(self.manifest['records'][-1]['parameters']['dp_eligible'])
        with self.assertRaises(ValueError):
            runner.freeze(self.frozen)

    def test_measured_preflight_never_recomputes_oracles(self):
        with mock.patch.object(self.generator, 'capacity_reference', side_effect=AssertionError('oracle rerun')), \
             mock.patch.object(self.generator, 'assignment_reference', side_effect=AssertionError('oracle rerun')):
            manifest, models, hashes = runner.read_frozen(
                self.frozen, self.pin, self.common, self.generator)
        self.assertEqual(len(models), 13)
        self.assertEqual(len(hashes), 28)
        self.assertEqual(manifest, self.manifest)

    def test_hash_pin_source_and_file_mutations_fail_closed(self):
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

    def observation_fixture(self):
        unit = self.manifest['records'][0]
        model = self.models[unit['id']]
        assignment = model['reference']['assignment'][:]
        raw = dict(schema_version=1, kind='binary', route='native',
                   backend='Gecode native', backend_version='fixture', guarantee='exact',
                   start_submitted=False, model_id=1, revision=1, model_columns=model['n'],
                   model_rows=len(model['rows']), model_globals=0, status='optimal',
                   has_solution=True, solution_validated=True, assignment=assignment,
                   full_values=assignment, objective=unit['objective'], best_bound=unit['objective'],
                   absolute_gap=0, relative_gap=0, build_seconds=0.001, solve_seconds=10,
                   driver_seconds=10.1, nodes=None, expanded_nodes=None, budget_nodes=None,
                   peak_open_nodes=None, unresolved_regions=None)
        return unit, model, raw

    def test_original_witness_and_exact_limit_boundary(self):
        unit, model, raw = self.observation_fixture()
        checked = runner.checked_observation(raw, unit, model, self.common, self.generator)
        self.assertTrue(checked['proved_within_limit'])
        raw['solve_seconds'] = 10.000001
        checked = runner.checked_observation(raw, unit, model, self.common, self.generator)
        self.assertTrue(checked['completed'])
        self.assertFalse(checked['proved_within_limit'])
        raw['objective'] += 1
        with self.assertRaises(ValueError):
            runner.checked_observation(raw, unit, model, self.common, self.generator)

    def records(self):
        records = []
        for repetition in (1, 2):
            for unit in self.manifest['records']:
                for cohort in ('before', 'after'):
                    records.append(dict(case=unit['id'], cohort=cohort, repetition=repetition,
                                        proved_within_limit=True, status='optimal', solve_seconds=1,
                                        external_seconds=1.01, objective=unit['objective'],
                                        best_bound=unit['objective']))
        return records

    def test_largest_size_includes_stress_and_requires_both_repetitions(self):
        records = self.records()
        boundary = self.manifest['records'][-1]['id']
        for record in records:
            if record['cohort']=='before' and record['case']==boundary and record['repetition']==2:
                record.update(proved_within_limit=False, status='time_limit', solve_seconds=10)
        summary = runner.summarize(records, self.manifest, {}, True, 1)
        family = summary['families'][0]
        self.assertEqual(family['tested_variables'], [8, 32, 128, 384, 512])
        self.assertEqual(family['before']['largest_tested_proved_variables'], 384)
        self.assertEqual(family['after']['largest_tested_proved_variables'], 512)
        self.assertEqual(family['before']['larger_tested_unproved_variables'], [512])
        stress = next(case for case in summary['cases'] if case['stress'])
        self.assertIsNone(stress['median_paired_solve_seconds_ratio_after_before'])
        self.assertEqual(stress['before']['internal_seconds'], [1, 10])

    def test_capacity_ratio_is_sampled_size_and_integrity_failure_clears_it(self):
        records = self.records()
        ids = {unit['id']: unit for unit in self.manifest['records']}
        for record in records:
            unit = ids[record['case']]
            if unit['family']=='capacity_uncorrelated' and (
                (record['cohort']=='before' and unit['variables']>8) or unit['stress']
            ):
                record.update(proved_within_limit=False, status='time_limit', solve_seconds=10)
        summary = runner.summarize(records, self.manifest, {}, True, 1)
        self.assertEqual(summary['families'][0]['ratio_of_largest_tested_proved_variables'], 48)
        invalid = runner.summarize(records, self.manifest, {}, False, 1)
        self.assertIsNone(invalid['families'][0]['ratio_of_largest_tested_proved_variables'])
        self.assertTrue(all(not case['before']['proved_all'] and not case['after']['proved_all']
                            for case in invalid['cases']))

    def test_unsafe_frozen_paths_are_rejected(self):
        for path in ('../outside', str(self.frozen/'manifest.json')):
            with self.assertRaises(ValueError):
                runner.inside(self.frozen, path)

    def test_failed_second_loader_probe_preserves_both_outcomes(self):
        work = self.root/'probe-test'
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
            files=[dict(copy='lib/libgecodeoptimize.dylib', sha256=runner.sha(before/'libgecodeoptimize.dylib'))],
        ))
        _, _, raw = self.observation_fixture()
        raw.update(solve_seconds=0.001, driver_seconds=0.003)
        outcomes = [
            dict(returncode=0, hard_timeout=False, output_limit=False, external_seconds=0.01,
                 stdout=json.dumps(raw).encode(), stderr=(str(before/'libgecodeoptimize.dylib')+'\n').encode()),
            dict(returncode=2, hard_timeout=False, output_limit=False, external_seconds=0.01,
                 stdout=b'', stderr=b'fixture loader rejection'),
        ]
        capture = mock.Mock(side_effect=outcomes)
        real_load = runner.load_module
        def load(name, path):
            return SimpleNamespace(capture_command=capture) if name=='capacity_capture' else real_load(name, path)
        args = SimpleNamespace(freeze_dir=self.frozen, manifest_sha256=self.pin, binary=binary,
                               before_libraries=[before], after_libraries=[after],
                               baseline_manifest=baseline, output_dir=work/'results')
        with mock.patch.object(runner, 'load_module', side_effect=load), \
             mock.patch.object(runner.subprocess, 'check_output', return_value='fixture-head\n'):
            self.assertEqual(runner.measure(args, time.monotonic()), 1)
        self.assertEqual(capture.call_count, 2)
        report = json.loads((args.output_dir/'report.json').read_text())
        self.assertFalse(report['comparison_valid'])
        self.assertTrue(report['preflight_failure'])
        self.assertEqual([probe['status'] for probe in report['loader_probes']], ['validated', 'failed'])
        self.assertEqual(report['loader_probes'][1]['returncode'], 2)
        self.assertEqual(report['records'], [])
        self.assertEqual((args.output_dir/'provenance-after.stderr').read_bytes(), b'fixture loader rejection')
        summary = json.loads((args.output_dir/'summary.json').read_text())
        self.assertFalse(summary['comparison_valid'])
        self.assertEqual(summary['required_runs'], 52)


if __name__=='__main__':
    unittest.main()
